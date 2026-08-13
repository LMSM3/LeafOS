from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from . import storage


REQUIRED_ARTIFACTS = {
    "task": "task.json",
    "objective": "objective.json",
    "candidates": "candidates.json",
    "roundtable_record": "roundtable-record.json",
    "plan": "plan.json",
    "workspace_manifest": "workspace-manifest.json",
    "before_hash": "before-hash.json",
    "after_hash": "after-hash.json",
    "candidate_diff": "candidate.diff",
    "commands": "commands.jsonl",
    "stdout": "stdout.log",
    "stderr": "stderr.log",
    "test_results": "test-results.json",
    "lint_results": "lint-results.json",
    "evaluation": "evaluation.json",
    "review": "review.json",
    "decision": "decision.json",
    "result": "result.json",
}

QUESTION_AUTHORITY = {
    "constitutional.q1": (
        "principles://ccis/bounded-change",
        "Is the proposed transition bounded?",
    ),
    "constitutional.q2": (
        "principles://ccis/evidence-before-acceptance",
        "Is there sufficient evidence?",
    ),
    "constitutional.q3": (
        "principles://ccis/continual-improvement",
        "Is the new state better, or at least defensibly safer?",
    ),
    "constitutional.q4": (
        "principles://ccis/legal-next-action",
        "What is the only legal next action?",
    ),
}


def _write_json(path: Path, value: Any) -> None:
    storage.atomic_json(path, value)


def _materialize_artifacts(
    run_dir: Path,
    bundle_dir: Path,
    candidates: list[dict[str, Any]],
    roundtable_record: dict[str, Any],
    evaluation: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    task = storage.read_json(run_dir / "task-envelope.json", {})
    metadata = storage.read_json(run_dir / "run.json", {})
    candidate = candidates[-1]
    validation_dir = run_dir / "validation"
    captured_results = storage.read_json(validation_dir / "validator-results.json")
    validator_results = captured_results if isinstance(captured_results, list) else evaluation.get("validator_results", [])
    validation_run = storage.read_json(validation_dir / "run.json", {})
    if isinstance(captured_results, list):
        if captured_results != evaluation.get("validator_results", []):
            raise storage.CCISError("captured validator results differ from the gated evaluation")
        events = storage.read_events(run_dir)
        storage.verify_events(events)
        validation_events = [event for event in events if event.get("event_type") == "ccis.validation.completed"]
        results_path = validation_dir / "validator-results.json"
        if not validation_events or validation_events[-1]["payload"].get("results_hash") != storage.file_digest(results_path):
            raise storage.CCISError("captured validator results do not match the authoritative event")
    commands = [
        {
            "validator_id": item.get("validator_id"),
            "command": item.get("command", []),
            "required": item.get("required", False),
        }
        for item in task.get("validators", [])
    ]
    json_values = {
        "task": task,
        "objective": task.get("objective", {}),
        "candidates": candidates,
        "roundtable_record": roundtable_record,
        "plan": {
            "task_id": decision["task_id"],
            "selected_candidate_id": candidate["candidate_id"],
            "steps": ["inspect", "select", "mutate", "validate", "gate"],
        },
        "workspace_manifest": {
            "repository": metadata.get("repository"),
            "baseline_revision": metadata.get("baseline_revision"),
            "workspace_mode": candidate.get("workspace_mode"),
            "validator_workspace": validation_run.get("workspace"),
            "validator_workspace_hash_before": validation_run.get("workspace_hash_before"),
            "validator_workspace_hash_after": validation_run.get("workspace_hash_after"),
            "authoritative_repository_modified": False,
        },
        "before_hash": {
            "algorithm": "sha256",
            "tracked_worktree": metadata.get("baseline_worktree_hash"),
            "index_tree": metadata.get("baseline_index_tree"),
        },
        "after_hash": {
            "algorithm": "sha256",
            "candidate_artifact": candidate.get("artifact", {}).get("sha256"),
            "declared_changes": [item.get("after_sha256") for item in candidate.get("changes", [])],
        },
        "test_results": {
            "results": validator_results,
            "required_passed": all(
                item.get("status") == "PASSED"
                for item in validator_results
                if item.get("required")
            ),
        },
        "lint_results": {
            "results": [item for item in validator_results if "lint" in str(item.get("validator_id", "")).lower()],
            "status": "NOT_APPLICABLE" if not any(
                "lint" in str(item.get("validator_id", "")).lower() for item in validator_results
            ) else "RECORDED",
        },
        "evaluation": evaluation,
        "review": {
            "reviewer": evaluation.get("evaluator"),
            "constitutional_questions": evaluation.get("constitutional_questions", []),
            "recommendation": evaluation.get("recommendation"),
        },
        "decision": decision,
        "result": {
            "task_id": decision["task_id"],
            "candidate_id": candidate["candidate_id"],
            "outcome": decision["outcome"],
            "legal_next_action": decision["next_action"],
            "working_tree_merged": False,
        },
    }
    for name, value in json_values.items():
        _write_json(bundle_dir / REQUIRED_ARTIFACTS[name], value)

    patch_path = run_dir / candidate["artifact"]["path"]
    shutil.copyfile(patch_path, bundle_dir / REQUIRED_ARTIFACTS["candidate_diff"])
    captured_commands = validation_dir / "commands.jsonl"
    captured_stdout = validation_dir / "stdout.log"
    captured_stderr = validation_dir / "stderr.log"
    if captured_commands.is_file():
        shutil.copyfile(captured_commands, bundle_dir / REQUIRED_ARTIFACTS["commands"])
    else:
        storage.atomic_text(
            bundle_dir / REQUIRED_ARTIFACTS["commands"],
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in commands),
        )
    if captured_stdout.is_file():
        shutil.copyfile(captured_stdout, bundle_dir / REQUIRED_ARTIFACTS["stdout"])
    else:
        storage.atomic_text(bundle_dir / REQUIRED_ARTIFACTS["stdout"], "")
    if captured_stderr.is_file():
        shutil.copyfile(captured_stderr, bundle_dir / REQUIRED_ARTIFACTS["stderr"])
    else:
        storage.atomic_text(bundle_dir / REQUIRED_ARTIFACTS["stderr"], "")


def write_evidence_bundle(
    run_dir: Path,
    transition_id: str,
    candidates: list[dict[str, Any]],
    roundtable_record: dict[str, Any],
    evaluation: dict[str, Any],
    decision: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    bundle_dir = run_dir / "evidence" / transition_id
    bundle_dir.mkdir(parents=True, exist_ok=True)
    _materialize_artifacts(run_dir, bundle_dir, candidates, roundtable_record, evaluation, decision)
    artifacts = {
        name: {"path": filename, "sha256": storage.file_digest(bundle_dir / filename)}
        for name, filename in REQUIRED_ARTIFACTS.items()
    }
    manifest = {
        "ccis_object": "ccis.evidence_bundle",
        "schema_version": 1,
        "bundle_id": f"bundle_{transition_id}",
        "task_id": decision["task_id"],
        "transition_id": transition_id,
        "created_at": storage.now(),
        "artifacts": artifacts,
    }
    manifest["bundle_hash"] = storage.digest(manifest)
    path = bundle_dir / "evidence-bundle.json"
    storage.atomic_json(path, manifest)
    verify_evidence_bundle(path)
    return path, manifest


def verify_evidence_bundle(path: Path) -> dict[str, Any]:
    manifest = storage.read_json(path)
    if not isinstance(manifest, dict) or manifest.get("ccis_object") != "ccis.evidence_bundle":
        raise storage.CCISError(f"invalid evidence bundle manifest: {path}")
    unsigned = {key: value for key, value in manifest.items() if key != "bundle_hash"}
    if manifest.get("bundle_hash") != storage.digest(unsigned):
        raise storage.CCISError("evidence bundle manifest hash mismatch")
    artifacts = manifest.get("artifacts", {})
    if set(artifacts) != set(REQUIRED_ARTIFACTS):
        raise storage.CCISError("evidence bundle is incomplete")
    for name, filename in REQUIRED_ARTIFACTS.items():
        artifact = artifacts[name]
        if artifact.get("path") != filename:
            raise storage.CCISError(f"unexpected evidence artifact path for {name}")
        artifact_path = path.parent / filename
        if not artifact_path.is_file() or artifact.get("sha256") != storage.file_digest(artifact_path):
            raise storage.CCISError(f"evidence artifact hash mismatch: {filename}")
        if filename.endswith(".json"):
            try:
                json.loads(artifact_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise storage.CCISError(f"invalid evidence JSON: {filename}") from error
        elif filename.endswith(".jsonl"):
            for line in artifact_path.read_text(encoding="utf-8").splitlines():
                try:
                    json.loads(line)
                except json.JSONDecodeError as error:
                    raise storage.CCISError(f"invalid evidence JSONL: {filename}") from error
    return manifest


def assert_evaluation_gate(evaluation: dict[str, Any], required_validators: set[str]) -> None:
    questions = evaluation.get("constitutional_questions", [])
    if len(questions) != 4 or {item.get("question_id") for item in questions} != set(QUESTION_AUTHORITY):
        raise storage.CCISError("CCIS evaluation requires each of the four constitutional questions exactly once")
    for item in questions:
        expected_ref, expected_text = QUESTION_AUTHORITY[item["question_id"]]
        if item.get("question_ref") != expected_ref or item.get("question") != expected_text:
            raise storage.CCISError(f"constitutional authority mismatch: {item['question_id']}")
    results = {item.get("validator_id"): item for item in evaluation.get("validator_results", [])}
    missing = sorted(required_validators - set(results))
    if missing:
        raise storage.CCISError(f"required validator results are missing: {', '.join(missing)}")


def recommendation(evaluation: dict[str, Any], requested_failure: str = "REVISE") -> str:
    question_results = {item["result"] for item in evaluation["constitutional_questions"]}
    required_results = [item["status"] for item in evaluation["validator_results"] if item.get("required")]
    if "UNKNOWN" in question_results:
        return "ESCALATED"
    if any(status in {"ERROR", "SKIPPED"} for status in required_results):
        return "BLOCKED"
    if "FAIL" in question_results or "FAILED" in required_results:
        if requested_failure not in {"REVISE", "REJECTED"}:
            raise storage.CCISError("failed evidence can only recommend REVISE or REJECTED")
        return requested_failure
    return "ACCEPTED"
