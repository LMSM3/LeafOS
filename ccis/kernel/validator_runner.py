from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from . import storage, transition_gate


def _task(run_dir: Path) -> dict[str, Any]:
    value = storage.read_json(run_dir / "task-envelope.json")
    if not isinstance(value, dict) or value.get("ccis_object") != "ccis.task_envelope":
        raise storage.CCISError("run task envelope is missing or invalid")
    return value


def _metadata(run_dir: Path) -> dict[str, Any]:
    value = storage.read_json(run_dir / "run.json")
    if not isinstance(value, dict):
        raise storage.CCISError("run metadata is missing or invalid")
    return value


def _selected_candidate(run_dir: Path) -> dict[str, Any]:
    values = storage.read_json(run_dir / "candidates.json", [])
    if not isinstance(values, list) or not values:
        raise storage.CCISError("validation requires a selected candidate")
    return values[-1]


def _assert_isolated_workspace(workspace: Path, repository: Path) -> None:
    if not workspace.is_dir():
        raise storage.CCISError(f"validation workspace does not exist: {workspace}")
    try:
        workspace.relative_to(repository)
    except ValueError:
        pass
    else:
        raise storage.CCISError("validators cannot execute in the authoritative repository or its descendants")
    try:
        repository.relative_to(workspace)
    except ValueError:
        pass
    else:
        raise storage.CCISError("validator workspace cannot contain the authoritative repository")


def _workspace_fingerprint(workspace: Path) -> str:
    if (workspace / ".git").exists():
        return storage.repository_snapshot(workspace)
    entries: list[dict[str, Any]] = []
    for path in sorted(item for item in workspace.rglob("*") if item.is_file()):
        relative = str(path.relative_to(workspace)).replace("\\", "/")
        entries.append({"path": relative, "sha256": storage.file_digest(path)})
    return storage.digest(entries)


def _output_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _persist(
    validation_dir: Path,
    command_records: list[dict[str, Any]],
    stdout_sections: list[str],
    stderr_sections: list[str],
    results: list[dict[str, Any]],
) -> None:
    storage.atomic_text(
        validation_dir / "commands.jsonl",
        "".join(json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n" for item in command_records),
    )
    storage.atomic_text(validation_dir / "stdout.log", "".join(stdout_sections))
    storage.atomic_text(validation_dir / "stderr.log", "".join(stderr_sections))
    storage.atomic_json(validation_dir / "validator-results.json", results)


def run_validators(run_dir: Path, workspace: Path) -> dict[str, Any]:
    """Execute declared validators without a shell in a disjoint workspace."""
    run_dir = run_dir.expanduser().resolve()
    workspace = workspace.expanduser().resolve()
    task = _task(run_dir)
    metadata = _metadata(run_dir)
    validators = task.get("validators")
    if not isinstance(validators, list) or not validators:
        raise storage.CCISError("task declares no validators")
    for validator in validators:
        validator_id = str(validator.get("validator_id", "unknown"))
        if int(validator.get("timeout_seconds", 300)) < 1:
            raise storage.CCISError(f"validator {validator_id} has an invalid timeout")
    repository = Path(metadata["repository"]).resolve()
    _assert_isolated_workspace(workspace, repository)
    candidate = _selected_candidate(run_dir)

    state = storage.resume(run_dir)
    if state["state"] == "CANDIDATE_SELECTED":
        transition_gate.advance(
            run_dir,
            "MUTATING",
            f"Isolated candidate artifact {candidate['candidate_id']} is ready.",
            artifact_hash=candidate["artifact"]["sha256"],
        )
        state = storage.resume(run_dir)
    if state["state"] == "MUTATING":
        transition_gate.advance(
            run_dir,
            "VALIDATING",
            f"Executing declared validators for {candidate['candidate_id']}.",
            artifact_hash=candidate["artifact"]["sha256"],
        )
        state = storage.resume(run_dir)
    if state["state"] != "VALIDATING":
        raise storage.CCISError(f"validator execution requires VALIDATING state, found {state['state']}")

    validation_dir = run_dir / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    started_at = storage.now()
    workspace_hash_before = _workspace_fingerprint(workspace)
    command_records: list[dict[str, Any]] = []
    stdout_sections: list[str] = []
    stderr_sections: list[str] = []
    results: list[dict[str, Any]] = []

    for validator in validators:
        validator_id = str(validator.get("validator_id", "unknown"))
        required = bool(validator.get("required"))
        kind = validator.get("kind")
        command = validator.get("command")
        timeout = int(validator.get("timeout_seconds", 300))
        record: dict[str, Any] = {
            "validator_id": validator_id,
            "kind": kind,
            "command": command or [],
            "required": required,
            "workspace": str(workspace),
            "shell": False,
            "started_at": storage.now(),
            "timeout_seconds": timeout,
        }
        stdout = ""
        stderr = ""
        exit_code: int | None = None
        started = time.monotonic()
        if kind != "command":
            status = "SKIPPED"
            summary = f"validator kind {kind!r} requires a dedicated runner"
        elif not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
            status = "ERROR"
            summary = "command validator has no valid argv array"
        else:
            try:
                completed = subprocess.run(
                    command,
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    check=False,
                    shell=False,
                )
                stdout = completed.stdout
                stderr = completed.stderr
                exit_code = completed.returncode
                status = "PASSED" if exit_code == 0 else "FAILED"
                summary = f"command exited with {exit_code}"
            except subprocess.TimeoutExpired as error:
                stdout = _output_text(error.stdout)
                stderr = _output_text(error.stderr)
                status = "ERROR"
                summary = f"command timed out after {timeout} seconds"
            except OSError as error:
                status = "ERROR"
                summary = f"command could not start: {error}"

        duration_ms = round((time.monotonic() - started) * 1000)
        record.update({
            "completed_at": storage.now(),
            "duration_ms": duration_ms,
            "exit_code": exit_code,
            "status": status,
        })
        command_records.append(record)
        stdout_sections.append(f"=== {validator_id} stdout ===\n{stdout}")
        if stdout and not stdout.endswith("\n"):
            stdout_sections.append("\n")
        stderr_sections.append(f"=== {validator_id} stderr ===\n{stderr}")
        if stderr and not stderr.endswith("\n"):
            stderr_sections.append("\n")
        results.append({
            "validator_id": validator_id,
            "status": status,
            "required": required,
            "exit_code": exit_code,
            "summary": summary,
            "evidence_refs": [
                f"evidence://{task['task_id']}/commands.jsonl",
                f"evidence://{task['task_id']}/stdout.log",
                f"evidence://{task['task_id']}/stderr.log",
            ],
        })
        _persist(validation_dir, command_records, stdout_sections, stderr_sections, results)

    workspace_hash_after = _workspace_fingerprint(workspace)
    validation_run = {
        "ccis_object": "ccis.validation_run",
        "schema_version": 1,
        "task_id": task["task_id"],
        "candidate_id": candidate["candidate_id"],
        "workspace": str(workspace),
        "workspace_hash_before": workspace_hash_before,
        "workspace_hash_after": workspace_hash_after,
        "started_at": started_at,
        "completed_at": storage.now(),
        "validator_count": len(results),
        "required_passed": all(item["status"] == "PASSED" for item in results if item["required"]),
    }
    storage.atomic_json(validation_dir / "run.json", validation_run)
    results_hash = storage.file_digest(validation_dir / "validator-results.json")

    with storage.run_lock(run_dir):
        events = storage.read_events(run_dir)
        storage.verify_events(events)
        projected = storage.project_state(events)
        if projected["state"] != "VALIDATING":
            raise storage.CCISError("validation state changed before evidence could be committed")
        event = storage.make_event(
            events,
            task["task_id"],
            "ccis.validation.completed",
            {
                "workspace": str(workspace),
                "validator_count": len(results),
                "required_passed": validation_run["required_passed"],
                "results_hash": results_hash,
            },
            [f"evidence://{task['task_id']}/validator-results.json"],
        )
        storage.append_event_unlocked(run_dir, event)
        events.append(event)
        state = storage.write_projection(run_dir, events)

    return {
        "ccis_object": "ccis.validation_result",
        "schema_version": 1,
        "run": str(run_dir),
        "workspace": str(workspace),
        "state": state,
        "results": results,
        "validation": validation_run,
        "artifacts": {
            "commands": str(validation_dir / "commands.jsonl"),
            "stdout": str(validation_dir / "stdout.log"),
            "stderr": str(validation_dir / "stderr.log"),
            "results": str(validation_dir / "validator-results.json"),
        },
    }
