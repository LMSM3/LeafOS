from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import evidence_gate, storage


TARGET_KINDS = {"ccis-run", "ccis-evidence-bundle", "benchmark-run"}
TAMPER_DISPOSITIONS = {"ARTIFACT_TAMPERED", "MANIFEST_TAMPERED", "EVENT_TAMPERED"}
MAX_INSPECTED_FILES = 4096
_BARE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PREFIXED_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class InspectionBudgetExceeded(storage.CCISError):
    """A read-only inspection exhausted its declared budget."""

    def __init__(self, message: str, path: Path | None = None):
        super().__init__(message)
        self.path = path


class InvalidEvidenceReference(storage.CCISError):
    """An evidence reference is missing, malformed, or escapes its declared root."""

    def __init__(self, message: str, path: Path | None = None):
        super().__init__(message)
        self.path = path


@dataclass
class InspectionBudget:
    maximum_bytes: int
    wall_time_seconds: int
    started: float = field(default_factory=time.monotonic)
    inspected_bytes: int = 0
    inspected_files: int = 0
    _seen: set[Path] = field(default_factory=set)
    _cache: dict[Path, bytes] = field(default_factory=dict)

    def _check_time(self) -> None:
        if time.monotonic() - self.started > self.wall_time_seconds:
            raise InspectionBudgetExceeded("evidence inspection wall-time budget exhausted")

    def read(self, path: Path, root: Path) -> bytes:
        self._check_time()
        resolved_root = _resolve_existing(root)
        resolved = _resolve_existing(path)
        if resolved != resolved_root and resolved_root not in resolved.parents:
            raise InvalidEvidenceReference("evidence reference escapes its declared root", path)
        if path.is_symlink() or not resolved.is_file():
            raise InvalidEvidenceReference("evidence reference is not a regular file", path)
        if resolved in self._cache:
            return self._cache[resolved]
        if self.inspected_files + 1 > MAX_INSPECTED_FILES:
            raise InspectionBudgetExceeded("evidence inspection file-count safety limit exhausted", path)
        remaining = self.maximum_bytes - self.inspected_bytes
        before = resolved.stat()
        if before.st_size > remaining:
            raise InspectionBudgetExceeded("evidence inspection byte budget exhausted", path)
        with resolved.open("rb") as stream:
            data = stream.read(remaining + 1)
        after = resolved.stat()
        if len(data) > remaining:
            raise InspectionBudgetExceeded("evidence inspection byte budget exhausted", path)
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or len(data) != after.st_size
        ):
            raise InvalidEvidenceReference("evidence changed during read-only inspection", path)
        self.inspected_files += 1
        self.inspected_bytes += len(data)
        self._seen.add(resolved)
        self._cache[resolved] = data
        self._check_time()
        return data


def _resolve_existing(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=True)
    except OSError as error:
        raise InvalidEvidenceReference(f"evidence reference does not exist: {path}", path) from error


def _absolute_ref(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def normalize_digest(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.lower()
    if _BARE_SHA256.fullmatch(lowered):
        return "sha256:" + lowered
    if _PREFIXED_SHA256.fullmatch(lowered):
        return lowered
    return None


def manifest_path(target_kind: str, target_ref: str | Path) -> Path:
    reference = _absolute_ref(target_ref)
    if target_kind == "ccis-evidence-bundle":
        if reference.is_dir():
            return reference / "evidence-bundle.json"
        if reference.name != "evidence-bundle.json":
            raise InvalidEvidenceReference("CCIS evidence-bundle references must name evidence-bundle.json", reference)
        return reference
    if target_kind == "benchmark-run":
        if reference.is_dir():
            return reference / "run.json"
        if reference.name != "run.json":
            raise InvalidEvidenceReference("benchmark-run references must name run.json", reference)
        return reference
    if target_kind == "ccis-run":
        if not reference.is_dir():
            raise InvalidEvidenceReference("CCIS run references must name a run directory", reference)
        return reference / "events.jsonl"
    raise InvalidEvidenceReference(f"unsupported evidence target kind: {target_kind}", reference)


def _base_diagnostic(task: dict[str, Any], budget: InspectionBudget) -> dict[str, Any]:
    target = task["target"]
    return {
        "ccis_object": "ccis.evidence_integrity_diagnostic",
        "schema_version": 1,
        "disposition": "CLEAN",
        "target_kind": target["kind"],
        "target_ref": str(_absolute_ref(target["ref"])),
        "first_bad_artifact": None,
        "expected_digest": None,
        "actual_digest": None,
        "declaring_manifest": None,
        "affected_decision_or_event": None,
        "inspected_files": budget.inspected_files,
        "inspected_bytes": budget.inspected_bytes,
        "read_only": True,
    }


def _finish(
    task: dict[str, Any],
    budget: InspectionBudget,
    disposition: str,
    *,
    first_bad_artifact: str | None = None,
    expected_digest: str | None = None,
    actual_digest: str | None = None,
    declaring_manifest: Path | None = None,
    affected: str | None = None,
) -> dict[str, Any]:
    diagnostic = _base_diagnostic(task, budget)
    diagnostic.update({
        "disposition": disposition,
        "first_bad_artifact": first_bad_artifact,
        "expected_digest": normalize_digest(expected_digest),
        "actual_digest": normalize_digest(actual_digest),
        "declaring_manifest": str(declaring_manifest.resolve(strict=False)) if declaring_manifest else None,
        "affected_decision_or_event": affected,
        "inspected_files": budget.inspected_files,
        "inspected_bytes": budget.inspected_bytes,
    })
    return diagnostic


def _json(data: bytes) -> Any:
    return json.loads(data.decode("utf-8-sig"))


def _bundle_diagnostic(task: dict[str, Any], budget: InspectionBudget) -> dict[str, Any]:
    target = task["target"]
    manifest = manifest_path(target["kind"], target["ref"])
    root = manifest.parent
    data = budget.read(manifest, root)
    actual_manifest_digest = _sha256(data)
    expected_target_digest = normalize_digest(target.get("digest"))
    if expected_target_digest != actual_manifest_digest:
        return _finish(
            task, budget, "MANIFEST_TAMPERED", first_bad_artifact=manifest.name,
            expected_digest=expected_target_digest, actual_digest=actual_manifest_digest,
            declaring_manifest=manifest,
        )
    try:
        value = _json(data)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _finish(
            task, budget, "MANIFEST_TAMPERED", first_bad_artifact=manifest.name,
            expected_digest=expected_target_digest, actual_digest=actual_manifest_digest,
            declaring_manifest=manifest,
        )
    if not isinstance(value, dict) or value.get("ccis_object") != "ccis.evidence_bundle":
        return _finish(
            task, budget, "MANIFEST_TAMPERED", first_bad_artifact=manifest.name,
            expected_digest=expected_target_digest, actual_digest=actual_manifest_digest,
            declaring_manifest=manifest,
        )
    affected = f"decision:{value.get('transition_id', value.get('task_id', 'unknown'))}"
    unsigned = {key: item for key, item in value.items() if key != "bundle_hash"}
    expected_bundle_hash = normalize_digest(value.get("bundle_hash"))
    actual_bundle_hash = storage.digest(unsigned)
    if expected_bundle_hash != actual_bundle_hash:
        return _finish(
            task, budget, "MANIFEST_TAMPERED", first_bad_artifact=manifest.name,
            expected_digest=expected_bundle_hash, actual_digest=actual_bundle_hash,
            declaring_manifest=manifest, affected=affected,
        )
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(evidence_gate.REQUIRED_ARTIFACTS):
        return _finish(
            task, budget, "MANIFEST_TAMPERED", first_bad_artifact="artifacts",
            expected_digest=storage.digest(sorted(evidence_gate.REQUIRED_ARTIFACTS)),
            actual_digest=storage.digest(sorted(artifacts) if isinstance(artifacts, dict) else artifacts),
            declaring_manifest=manifest, affected=affected,
        )
    for name, filename in evidence_gate.REQUIRED_ARTIFACTS.items():
        declaration = artifacts.get(name)
        if not isinstance(declaration, dict) or declaration.get("path") != filename:
            return _finish(
                task, budget, "MANIFEST_TAMPERED", first_bad_artifact=name,
                expected_digest=storage.digest(filename), actual_digest=storage.digest(declaration),
                declaring_manifest=manifest, affected=affected,
            )
        expected = normalize_digest(declaration.get("sha256"))
        if expected is None:
            return _finish(
                task, budget, "MANIFEST_TAMPERED", first_bad_artifact=filename,
                actual_digest=storage.digest(declaration), declaring_manifest=manifest, affected=affected,
            )
        artifact_path = root / filename
        try:
            artifact_data = budget.read(artifact_path, root)
        except InvalidEvidenceReference:
            return _finish(
                task, budget, "ARTIFACT_TAMPERED", first_bad_artifact=filename,
                expected_digest=expected, declaring_manifest=manifest, affected=affected,
            )
        actual = _sha256(artifact_data)
        if expected != actual:
            return _finish(
                task, budget, "ARTIFACT_TAMPERED", first_bad_artifact=filename,
                expected_digest=expected, actual_digest=actual,
                declaring_manifest=manifest, affected=affected,
            )
        if filename.endswith(".json"):
            try:
                _json(artifact_data)
            except (UnicodeDecodeError, json.JSONDecodeError):
                return _finish(
                    task, budget, "ARTIFACT_TAMPERED", first_bad_artifact=filename,
                    expected_digest=expected, actual_digest=actual,
                    declaring_manifest=manifest, affected=affected,
                )
        elif filename.endswith(".jsonl"):
            try:
                for line in artifact_data.decode("utf-8-sig").splitlines():
                    if line.strip():
                        json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                return _finish(
                    task, budget, "ARTIFACT_TAMPERED", first_bad_artifact=filename,
                    expected_digest=expected, actual_digest=actual,
                    declaring_manifest=manifest, affected=affected,
                )
    return _finish(task, budget, "CLEAN", declaring_manifest=manifest, affected=affected)


def _benchmark_diagnostic(task: dict[str, Any], budget: InspectionBudget) -> dict[str, Any]:
    target = task["target"]
    manifest = manifest_path(target["kind"], target["ref"])
    root = manifest.parent
    data = budget.read(manifest, root)
    actual_manifest_digest = _sha256(data)
    expected_manifest_digest = normalize_digest(target.get("digest"))
    if expected_manifest_digest != actual_manifest_digest:
        return _finish(
            task, budget, "MANIFEST_TAMPERED", first_bad_artifact=manifest.name,
            expected_digest=expected_manifest_digest, actual_digest=actual_manifest_digest,
            declaring_manifest=manifest,
        )
    try:
        value = _json(data)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _finish(
            task, budget, "MANIFEST_TAMPERED", first_bad_artifact=manifest.name,
            expected_digest=expected_manifest_digest, actual_digest=actual_manifest_digest,
            declaring_manifest=manifest,
        )
    if not isinstance(value, dict) or not isinstance(value.get("run_id"), str) or not isinstance(value.get("results"), list):
        return _finish(
            task, budget, "MANIFEST_TAMPERED", first_bad_artifact=manifest.name,
            expected_digest=expected_manifest_digest, actual_digest=actual_manifest_digest,
            declaring_manifest=manifest,
        )
    run_id = value["run_id"]
    for index, result in enumerate(value["results"]):
        if not isinstance(result, dict):
            return _finish(
                task, budget, "MANIFEST_TAMPERED", first_bad_artifact=f"results[{index}]",
                expected_digest=storage.digest("object"), actual_digest=storage.digest(result),
                declaring_manifest=manifest, affected=f"benchmark-run:{run_id}",
            )
        entry_id = str(result.get("entry_id", index))
        affected = f"benchmark-run:{run_id}/{entry_id}"
        for stream_name in ("stdout", "stderr"):
            declaration = result.get(stream_name)
            if not isinstance(declaration, dict) or not isinstance(declaration.get("path"), str):
                return _finish(
                    task, budget, "MANIFEST_TAMPERED", first_bad_artifact=f"results[{index}].{stream_name}",
                    expected_digest=storage.digest("path-and-sha256"), actual_digest=storage.digest(declaration),
                    declaring_manifest=manifest, affected=affected,
                )
            expected = normalize_digest(declaration.get("sha256"))
            if expected is None:
                return _finish(
                    task, budget, "MANIFEST_TAMPERED", first_bad_artifact=declaration["path"],
                    actual_digest=storage.digest(declaration), declaring_manifest=manifest, affected=affected,
                )
            declared_path = Path(declaration["path"])
            artifact_path = declared_path if declared_path.is_absolute() else root / declared_path
            try:
                artifact_data = budget.read(artifact_path, root)
            except InvalidEvidenceReference:
                return _finish(
                    task, budget, "ARTIFACT_TAMPERED", first_bad_artifact=declaration["path"],
                    expected_digest=expected, declaring_manifest=manifest, affected=affected,
                )
            actual = _sha256(artifact_data)
            if expected != actual:
                return _finish(
                    task, budget, "ARTIFACT_TAMPERED", first_bad_artifact=str(artifact_path),
                    expected_digest=expected, actual_digest=actual,
                    declaring_manifest=manifest, affected=affected,
                )
    return _finish(
        task, budget, "CLEAN", declaring_manifest=manifest,
        affected=f"benchmark-run:{run_id}",
    )


def _event_diagnostic(task: dict[str, Any], budget: InspectionBudget) -> dict[str, Any]:
    target = task["target"]
    run_root = _absolute_ref(target["ref"])
    event_path = manifest_path(target["kind"], target["ref"])
    data = budget.read(event_path, run_root)
    expected_stream_digest = normalize_digest(target.get("digest"))
    actual_stream_digest = _sha256(data)
    try:
        lines = data.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError:
        return _finish(
            task, budget, "EVENT_TAMPERED", first_bad_artifact=event_path.name,
            actual_digest=_sha256(data), declaring_manifest=event_path,
        )
    events: list[tuple[int, dict[str, Any]]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return _finish(
                task, budget, "EVENT_TAMPERED", first_bad_artifact=f"{event_path.name}#{line_number}",
                actual_digest=_sha256(line.encode("utf-8")), declaring_manifest=event_path,
                affected=f"event:line-{line_number}",
            )
        if not isinstance(event, dict):
            return _finish(
                task, budget, "EVENT_TAMPERED", first_bad_artifact=f"{event_path.name}#{line_number}",
                expected_digest=storage.digest("object"), actual_digest=storage.digest(event),
                declaring_manifest=event_path, affected=f"event:line-{line_number}",
            )
        events.append((line_number, event))
    if not events:
        return _finish(
            task, budget, "EVENT_TAMPERED", first_bad_artifact=event_path.name,
            expected_digest=storage.digest("non-empty-event-stream"), actual_digest=_sha256(data),
            declaring_manifest=event_path,
        )
    previous: str | None = None
    for sequence, (line_number, event) in enumerate(events, 1):
        affected = f"event:{event.get('event_id', f'line-{line_number}')}"
        artifact = f"{event_path.name}#{line_number}"
        if event.get("sequence") != sequence:
            return _finish(
                task, budget, "EVENT_TAMPERED", first_bad_artifact=artifact,
                expected_digest=storage.digest(sequence), actual_digest=storage.digest(event.get("sequence")),
                declaring_manifest=event_path, affected=affected,
            )
        if event.get("previous_event_hash") != previous:
            return _finish(
                task, budget, "EVENT_TAMPERED", first_bad_artifact=artifact,
                expected_digest=storage.digest(previous), actual_digest=storage.digest(event.get("previous_event_hash")),
                declaring_manifest=event_path, affected=affected,
            )
        expected_payload_hash = normalize_digest(event.get("payload_hash"))
        actual_payload_hash = storage.digest(event.get("payload", {}))
        if expected_payload_hash != actual_payload_hash:
            return _finish(
                task, budget, "EVENT_TAMPERED", first_bad_artifact=artifact,
                expected_digest=expected_payload_hash, actual_digest=actual_payload_hash,
                declaring_manifest=event_path, affected=affected,
            )
        unsigned = {key: value for key, value in event.items() if key != "event_hash"}
        expected_event_hash = normalize_digest(event.get("event_hash"))
        actual_event_hash = storage.digest(unsigned)
        if expected_event_hash != actual_event_hash:
            return _finish(
                task, budget, "EVENT_TAMPERED", first_bad_artifact=artifact,
                expected_digest=expected_event_hash, actual_digest=actual_event_hash,
                declaring_manifest=event_path, affected=affected,
            )
        previous = event["event_hash"]
    if expected_stream_digest != actual_stream_digest:
        last_event = events[-1][1]
        return _finish(
            task, budget, "EVENT_TAMPERED", first_bad_artifact=event_path.name,
            expected_digest=expected_stream_digest, actual_digest=actual_stream_digest,
            declaring_manifest=event_path,
            affected=f"event:{last_event.get('event_id', 'unknown')}",
        )
    return _finish(
        task, budget, "CLEAN", declaring_manifest=event_path,
        affected=f"event:{events[-1][1].get('event_id', 'unknown')}",
    )


def inspect_task(task: dict[str, Any]) -> dict[str, Any]:
    budget = InspectionBudget(
        maximum_bytes=task["budget"]["evidence_bytes"],
        wall_time_seconds=task["budget"]["wall_time_seconds"],
    )
    try:
        target_kind = task["target"]["kind"]
        if target_kind == "ccis-evidence-bundle":
            return _bundle_diagnostic(task, budget)
        if target_kind == "benchmark-run":
            return _benchmark_diagnostic(task, budget)
        if target_kind == "ccis-run":
            return _event_diagnostic(task, budget)
        raise InvalidEvidenceReference(f"unsupported evidence target kind: {target_kind}")
    except InspectionBudgetExceeded as error:
        return _finish(
            task, budget, "BUDGET_EXCEEDED",
            first_bad_artifact=str(error.path) if error.path else None,
        )
    except (InvalidEvidenceReference, OSError) as error:
        path = getattr(error, "path", None)
        return _finish(
            task, budget, "INVALID_REFERENCE",
            first_bad_artifact=str(path) if path else None,
        )
