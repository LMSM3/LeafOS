from __future__ import annotations

import hashlib
import json
import os
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.config import Settings
from core.control.epochs import EPOCH_STATE_SCHEMA, EpochManager
from core.control.scheduler import SCHEDULER_SCHEMA, Scheduler
from core.control.store import (
    CURRENT_CONTROL_PHASE,
    OBJECTIVE_SCHEMA,
    TASKGRAPH_SCHEMA,
    ControlError,
    ProjectStore,
    _host_session_id,
    _lease_process_alive,
    _pid_alive,
)
from core.state import utc_now


RECOVERY_STATE_SCHEMA = "leafos.recovery-state.v1"
CHECKPOINT_SCHEMA = "leafos.recovery-checkpoint.v1"
CHECKPOINT_MANIFEST_SCHEMA = "leafos.recovery-checkpoint-manifest.v1"
TELEMETRY_SCHEMA = "leafos.recovery-telemetry.v1"
DEFAULT_SOAK_HOURS = 6.0
DEFAULT_SAMPLE_SECONDS = 30.0
REQUIRED_RELEASE_FAULTS = {
    "worker-kill",
    "controller-restart",
    "failed-model-load",
    "tool-failure",
    "interrupted-generation",
}
FAULT_KINDS = REQUIRED_RELEASE_FAULTS | {"terminal-closure", "model-unload", "wsl-restart"}


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RecoveryManager:
    """Durable Phase E checkpoints, recovery invariants, and soak telemetry."""

    def __init__(self, settings: Settings, project_root: Path) -> None:
        self.settings = settings
        self.store = ProjectStore(project_root)
        self.scheduler = Scheduler(settings, project_root)
        self.epochs = EpochManager(self.store)
        self.state_path = self.store.state_dir / "recovery.json"
        self.telemetry_path = self.store.state_dir / "telemetry.jsonl"
        self.checkpoints_dir = self.store.leaf_dir / "checkpoints"

    def _load(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            raise ControlError("recovery state is not initialized; run 'leafctl swarm soak'")
        value = self.store._read_document(self.state_path, RECOVERY_STATE_SCHEMA)
        if value.get("project_id") != self.store.project_identity["id"]:
            raise ControlError("recovery state belongs to a different project")
        return value

    def _save(self, state: dict[str, Any]) -> dict[str, Any]:
        state["revision"] = int(state.get("revision", 0)) + 1
        state["updated_at"] = utc_now()
        return self.store._write_document(self.state_path, state)

    def _accepted_snapshot(self, graph: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
        graph = graph or self.store.load_taskgraph()
        accepted: dict[str, dict[str, Any]] = {}
        for task_id, task in graph["tasks"].items():
            if task.get("status") != "accepted":
                continue
            evidence_ids = sorted({str(value) for value in task.get("evidence", [])})
            decision = task.get("decision")
            if not isinstance(decision, str) or not decision or not evidence_ids:
                raise ControlError(f"accepted task is detached from its decision or evidence: {task_id}")
            accepted[task_id] = {"decision": decision, "evidence_ids": evidence_ids}
        return accepted

    def _assert_acceptance_invariants(
        self, required: dict[str, dict[str, Any]] | None = None
    ) -> dict[str, dict[str, Any]]:
        self.store.audit()
        graph = self.store.load_taskgraph()
        current = self._accepted_snapshot(graph)
        for task_id, expected in (required or {}).items():
            if current.get(task_id) != expected:
                raise ControlError(f"accepted task was lost, changed, or detached from evidence: {task_id}")
        acceptance_counts: dict[str, int] = {}
        for decision in self.store._read_records(self.store.decisions_path):
            if decision.get("kind") != "acceptance" or not isinstance(decision.get("task_id"), str):
                continue
            task_id = str(decision["task_id"])
            acceptance_counts[task_id] = acceptance_counts.get(task_id, 0) + 1
        duplicate = sorted(task_id for task_id, count in acceptance_counts.items() if count > 1)
        if duplicate:
            raise ControlError("accepted task has duplicate acceptance decisions: " + ", ".join(duplicate))
        return current

    def initialize(
        self,
        *,
        hours: float = DEFAULT_SOAK_HOURS,
        sample_seconds: float = DEFAULT_SAMPLE_SECONDS,
        replace: bool = False,
    ) -> dict[str, Any]:
        if not 1 / 3600 <= hours <= 168:
            raise ControlError("soak hours must be between 0.000278 and 168")
        if not 0.05 <= sample_seconds <= 3600:
            raise ControlError("sample seconds must be between 0.05 and 3600")
        if not self.store.initialized:
            raise ControlError("project control state is not initialized; run 'leafctl swarm plan --objective ...'")
        self.store._prepare()
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.store.advance_phase(CURRENT_CONTROL_PHASE)
        self.epochs.initialize()
        if self.state_path.is_file() and not replace:
            return self._load()
        previous_checkpoints: list[str] = []
        previous_latest: str | None = None
        if self.state_path.is_file() and replace:
            current = self._load()
            previous_checkpoints = [str(value) for value in current.get("checkpoints", [])]
            previous_latest = current.get("latest_checkpoint") if isinstance(current.get("latest_checkpoint"), str) else None
            owner = current.get("owner") if isinstance(current.get("owner"), dict) else {}
            same_session = owner.get("host_session_id") in {None, _host_session_id()}
            if current.get("status") == "running" and same_session and _pid_alive(owner.get("pid")):
                raise ControlError(f"soak is already running with PID {owner.get('pid')}")
        now = utc_now()
        state = {
            "schema": RECOVERY_STATE_SCHEMA,
            "revision": 1,
            "project_id": self.store.project_identity["id"],
            "status": "ready",
            "target_seconds": int(round(hours * 3600)),
            "sample_seconds": float(sample_seconds),
            "started_at": None,
            "deadline_at": None,
            "completed_at": None,
            "owner": {"pid": None, "host_session_id": _host_session_id()},
            "samples": 0,
            "resume_count": 0,
            "epoch_boundaries": [],
            "checkpoints": previous_checkpoints,
            "latest_checkpoint": previous_latest,
            "faults": [],
            "baseline_accepted": self._accepted_snapshot(),
            "last_error": None,
            "gate_failures": [],
            "created_at": now,
            "updated_at": now,
        }
        return self.store._write_document(self.state_path, state)

    @staticmethod
    def _stream_marker(path: Path) -> dict[str, Any]:
        data = path.read_bytes() if path.is_file() else b""
        records = len([line for line in data.splitlines() if line.strip()])
        return {"path": path.name, "bytes": len(data), "records": records, "sha256": _sha256(data)}

    def checkpoint(self, reason: str) -> dict[str, Any]:
        reason = reason.strip()
        if not reason:
            raise ControlError("checkpoint reason cannot be empty")
        state = self._load()
        accepted = self._assert_acceptance_invariants()
        checkpoint_number = len(state.get("checkpoints", [])) + 1
        checkpoint_id = f"checkpoint-{checkpoint_number:06d}"
        directory = self.checkpoints_dir / checkpoint_id
        if directory.exists():
            raise ControlError(f"immutable checkpoint already exists: {directory}")
        directory.mkdir(parents=True)
        documents: dict[str, Any] = {
            "objective": self.store.load_objective(),
            "taskgraph": self.store.load_taskgraph(),
        }
        if self.store.scheduler_path.is_file():
            documents["scheduler"] = self.store._read_document(self.store.scheduler_path, SCHEDULER_SCHEMA)
        epoch_state_path = self.store.state_dir / "epochs.json"
        if epoch_state_path.is_file():
            documents["epochs"] = self.store._read_document(epoch_state_path, EPOCH_STATE_SCHEMA)
        snapshot = self.store._write_document(
            directory / "snapshot.json",
            {
                "schema": CHECKPOINT_SCHEMA,
                "id": checkpoint_id,
                "project_id": self.store.project_identity["id"],
                "observed_at": utc_now(),
                "reason": reason,
                "documents": documents,
                "accepted": accepted,
            },
        )
        snapshot_data = (directory / "snapshot.json").read_bytes()
        streams = {
            "journal": self._stream_marker(self.store.journal_path),
            "decisions": self._stream_marker(self.store.decisions_path),
        }
        manifest = self.store._write_document(
            directory / "manifest.json",
            {
                "schema": CHECKPOINT_MANIFEST_SCHEMA,
                "id": checkpoint_id,
                "project_id": self.store.project_identity["id"],
                "observed_at": utc_now(),
                "reason": reason,
                "snapshot": {
                    "path": "snapshot.json",
                    "bytes": len(snapshot_data),
                    "sha256": _sha256(snapshot_data),
                    "integrity": snapshot["integrity"],
                },
                "streams": streams,
            },
        )
        state = self._load()
        state.setdefault("checkpoints", []).append(checkpoint_id)
        state["latest_checkpoint"] = checkpoint_id
        self._save(state)
        self.store._journal("recovery.checkpoint", checkpoint_id=checkpoint_id, reason=reason)
        return manifest

    def verify_checkpoint(self, checkpoint_id: str | None = None) -> dict[str, Any]:
        state = self._load()
        selected = checkpoint_id or state.get("latest_checkpoint")
        if not isinstance(selected, str) or not selected:
            raise ControlError("no recovery checkpoint exists")
        directory = self.checkpoints_dir / selected
        manifest = self.store._read_document(directory / "manifest.json", CHECKPOINT_MANIFEST_SCHEMA)
        snapshot_path = directory / str(manifest.get("snapshot", {}).get("path") or "snapshot.json")
        snapshot_data = snapshot_path.read_bytes()
        expected = manifest.get("snapshot", {})
        if len(snapshot_data) != expected.get("bytes") or _sha256(snapshot_data) != expected.get("sha256"):
            raise ControlError(f"recovery checkpoint integrity check failed: {snapshot_path}")
        snapshot = self.store._read_document(snapshot_path, CHECKPOINT_SCHEMA)
        if snapshot.get("integrity") != expected.get("integrity"):
            raise ControlError(f"recovery checkpoint seal does not match: {snapshot_path}")
        if snapshot.get("project_id") != self.store.project_identity["id"]:
            raise ControlError(f"recovery checkpoint belongs to another project: {selected}")
        graph = snapshot.get("documents", {}).get("taskgraph")
        if not isinstance(graph, dict):
            raise ControlError(f"recovery checkpoint has no task graph: {selected}")
        if self._accepted_snapshot(graph) != snapshot.get("accepted"):
            raise ControlError(f"recovery checkpoint acceptance index is detached: {selected}")
        stream_paths = {"journal": self.store.journal_path, "decisions": self.store.decisions_path}
        for name, marker in manifest.get("streams", {}).items():
            path = stream_paths.get(name)
            if path is None:
                continue
            data = path.read_bytes() if path.is_file() else b""
            size = int(marker.get("bytes", -1))
            if size < 0 or len(data) < size or _sha256(data[:size]) != marker.get("sha256"):
                raise ControlError(f"append-only {name} prefix no longer matches checkpoint {selected}")
        return {"manifest": manifest, "snapshot": snapshot}

    def recover(self) -> dict[str, Any]:
        recovered = self.store.recover()
        state = self._load()
        checkpoint = None
        required = state.get("baseline_accepted") if isinstance(state.get("baseline_accepted"), dict) else {}
        if state.get("latest_checkpoint"):
            verified = self.verify_checkpoint(str(state["latest_checkpoint"]))
            checkpoint = verified["manifest"]["id"]
            required = {**required, **verified["snapshot"].get("accepted", {})}
        accepted = self._assert_acceptance_invariants(required)
        graph = self.store.load_taskgraph()
        orphaned = []
        for task_id, task in graph["tasks"].items():
            for key in ("lease", "verification_lease"):
                lease = task.get(key) if isinstance(task.get(key), dict) else {}
                if lease and _lease_process_alive(lease, "runtime_pid") and not _lease_process_alive(lease):
                    orphaned.append({"task_id": task_id, "runtime_pid": lease.get("runtime_pid")})
        if orphaned:
            raise ControlError(f"orphaned model process remains after recovery: {orphaned}")
        manifest = self.checkpoint("recovery verified")
        self.store._journal("recovery.completed", recovered_tasks=recovered, checkpoint_id=manifest["id"])
        return {
            "status": "recovered",
            "tasks": recovered,
            "accepted": len(accepted),
            "verified_checkpoint": checkpoint,
            "checkpoint": manifest["id"],
            "orphans": orphaned,
        }

    def record_fault(self, kind: str, outcome: str, detail: str) -> dict[str, Any]:
        if kind not in FAULT_KINDS:
            raise ControlError("fault kind must be one of: " + ", ".join(sorted(FAULT_KINDS)))
        if outcome not in {"passed", "failed", "observed"}:
            raise ControlError("fault outcome must be passed, failed, or observed")
        detail = detail.strip()
        if not detail:
            raise ControlError("fault detail cannot be empty")
        state = self._load()
        since = _parse_time(state.get("started_at"))
        proof: list[str] = []
        if kind == "controller-restart" and int(state.get("resume_count", 0)) > 0:
            proof.append(f"resume-count:{state['resume_count']}")
        if kind in {"worker-kill", "terminal-closure", "wsl-restart"}:
            for index, event in enumerate(self.store._read_records(self.store.journal_path), start=1):
                observed = _parse_time(event.get("time"))
                if since and observed and observed < since:
                    continue
                if kind == "worker-kill" and (
                    event.get("kind") == "task.leases_recovered"
                    or (
                        event.get("kind") == "task.lease_released"
                        and "worker exited with code" in str(event.get("reason") or "")
                    )
                ):
                    proof.append(f"journal:{index}:{event.get('integrity')}")
                if kind == "terminal-closure" and event.get("kind") == "recovery.completed":
                    proof.append(f"journal:{index}:{event.get('integrity')}")
                if kind == "wsl-restart" and event.get("kind") == "task.leases_recovered":
                    proof.append(f"journal:{index}:{event.get('integrity')}")
        if kind in {"failed-model-load", "tool-failure"}:
            for path in sorted(self.store.evidence_dir.glob("evidence-*.json")):
                evidence = self.store._read_document(path, "leafos.evidence.v1")
                observed = _parse_time(evidence.get("observed_at"))
                if since and observed and observed < since:
                    continue
                if kind == "failed-model-load" and evidence.get("kind") == "local-model-inference" and evidence.get("exit_code") not in {0, 130}:
                    proof.append(str(evidence.get("id")))
                if kind == "tool-failure" and evidence.get("kind") == "tool-execution" and evidence.get("exit_code") != 0:
                    proof.append(str(evidence.get("id")))
        if kind in {"interrupted-generation", "model-unload"} and self.settings.events_path.is_file():
            for index, line in enumerate(self.settings.events_path.read_text(encoding="utf-8").splitlines(), start=1):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                observed = _parse_time(event.get("time"))
                if since and observed and observed < since:
                    continue
                exit_code = event.get("exit_code")
                if event.get("kind") == "runtime.stopped" and (
                    (kind == "interrupted-generation" and exit_code == 130)
                    or (kind == "model-unload" and exit_code not in {None, 0})
                ):
                    proof.append(f"runtime-event:{index}")
        verified = bool(proof)
        if outcome == "passed" and not verified:
            raise ControlError(f"fault cannot be marked passed without post-soak runtime or audit proof: {kind}")
        record = {
            "kind": kind,
            "outcome": outcome,
            "verified": verified,
            "proof": proof,
            "detail": detail,
            "observed_at": utc_now(),
        }
        state.setdefault("faults", []).append(record)
        self._save(state)
        self.store._journal(
            "recovery.fault_recorded",
            fault_kind=kind,
            outcome=outcome,
            verified=verified,
            proof=proof,
            detail=detail,
            observed_at=record["observed_at"],
        )
        return record

    def _record_telemetry(self, tick: dict[str, Any], tick_ms: float) -> dict[str, Any]:
        scheduler_state = self.scheduler._load()
        graph = self.store.load_taskgraph()
        counts: dict[str, int] = {}
        for task in graph["tasks"].values():
            status = str(task.get("status", "unknown"))
            counts[status] = counts.get(status, 0) + 1
        record = {
            "schema": TELEMETRY_SCHEMA,
            "observed_at": utc_now(),
            "tick_ms": round(tick_ms, 3),
            "started": list(tick.get("started", [])),
            "preempted": list(tick.get("preempted", [])),
            "pressure": tick.get("pressure"),
            "queue": dict(tick.get("queue", {})),
            "tasks": counts,
            "workers": len(scheduler_state.get("workers", {})),
            "foreground": bool(scheduler_state.get("foreground", {}).get("active")),
            "resources": scheduler_state.get("resources", {}),
        }
        self.store._append_record(self.telemetry_path, record)
        return record

    def _running_owner_is_live(self, state: dict[str, Any]) -> bool:
        owner = state.get("owner") if isinstance(state.get("owner"), dict) else {}
        return owner.get("host_session_id") in {None, _host_session_id()} and _pid_alive(owner.get("pid"))

    def run(
        self,
        *,
        hours: float = DEFAULT_SOAK_HOURS,
        sample_seconds: float | None = None,
        max_samples: int | None = None,
        replace: bool = False,
    ) -> dict[str, Any]:
        effective_sample_seconds = DEFAULT_SAMPLE_SECONDS if sample_seconds is None else sample_seconds
        state = self.initialize(hours=hours, sample_seconds=effective_sample_seconds, replace=replace)
        if state.get("status") == "completed":
            return self.status()
        owner = state.get("owner") if isinstance(state.get("owner"), dict) else {}
        if state.get("status") == "running" and owner.get("pid") != os.getpid() and self._running_owner_is_live(state):
            raise ControlError(f"soak is already running with PID {owner.get('pid')}")
        if sample_seconds is not None:
            if not 0.05 <= sample_seconds <= 3600:
                raise ControlError("sample seconds must be between 0.05 and 3600")
            state["sample_seconds"] = float(sample_seconds)
        now = datetime.now(timezone.utc)
        started = _parse_time(state.get("started_at")) or now
        deadline = _parse_time(state.get("deadline_at")) or (started + timedelta(seconds=int(state["target_seconds"])))
        if state.get("started_at") and owner.get("pid") not in {None, os.getpid()}:
            state["resume_count"] = int(state.get("resume_count", 0)) + 1
        state.update(
            {
                "status": "running",
                "started_at": started.isoformat(),
                "deadline_at": deadline.isoformat(),
                "owner": {"pid": os.getpid(), "host_session_id": _host_session_id()},
                "last_error": None,
            }
        )
        self._save(state)
        completed_in_call = 0
        try:
            while datetime.now(timezone.utc) < deadline:
                tick_started = time.perf_counter()
                tick = self.scheduler.tick()
                tick_ms = (time.perf_counter() - tick_started) * 1000.0
                epoch_id = None
                epoch_status = self.epochs.status()
                if epoch_status.get("due"):
                    reviewed = self.epochs.review()
                    epoch_id = str(reviewed["manifest"]["id"])
                state = self._load()
                required = state.get("baseline_accepted") if isinstance(state.get("baseline_accepted"), dict) else {}
                self._assert_acceptance_invariants(required)
                self._record_telemetry(tick, tick_ms)
                state = self._load()
                state["samples"] = int(state.get("samples", 0)) + 1
                if epoch_id and epoch_id not in state.setdefault("epoch_boundaries", []):
                    state["epoch_boundaries"].append(epoch_id)
                self._save(state)
                if epoch_id:
                    self.checkpoint(f"epoch boundary {epoch_id}")
                completed_in_call += 1
                if max_samples is not None and completed_in_call >= max_samples:
                    self.scheduler.stop()
                    state = self._load()
                    state["status"] = "paused"
                    state["owner"] = {"pid": None, "host_session_id": _host_session_id()}
                    self._save(state)
                    self.checkpoint("soak paused at sample limit")
                    return self.status()
                remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
                if remaining > 0:
                    time.sleep(min(float(state["sample_seconds"]), remaining))
        except KeyboardInterrupt:
            self.scheduler.stop()
            state = self._load()
            state["status"] = "interrupted"
            state["owner"] = {"pid": None, "host_session_id": _host_session_id()}
            state["last_error"] = "operator interrupted soak"
            self._save(state)
            self.checkpoint("operator interrupted soak")
            return self.status()
        except Exception as error:
            state = self._load()
            state["status"] = "degraded"
            state["owner"] = {"pid": None, "host_session_id": _host_session_id()}
            state["last_error"] = str(error)
            self._save(state)
            raise
        self.scheduler.stop()
        state = self._load()
        self._assert_acceptance_invariants(
            state.get("baseline_accepted") if isinstance(state.get("baseline_accepted"), dict) else {}
        )
        gate_failures = []
        if int(state["target_seconds"]) >= int(DEFAULT_SOAK_HOURS * 3600):
            if len(state.get("epoch_boundaries", [])) < 2:
                gate_failures.append("fewer than two epoch boundaries")
            passed_faults = {
                value.get("kind")
                for value in state.get("faults", [])
                if value.get("outcome") == "passed" and value.get("verified") is True
            }
            missing = sorted(REQUIRED_RELEASE_FAULTS - passed_faults)
            if missing:
                gate_failures.append("missing passed fault injections: " + ", ".join(missing))
        state["status"] = "failed" if gate_failures else "completed"
        state["gate_failures"] = gate_failures
        state["completed_at"] = utc_now()
        state["owner"] = {"pid": None, "host_session_id": _host_session_id()}
        self._save(state)
        self.checkpoint("soak completed" if not gate_failures else "soak gate failed")
        return self.status()

    def status(self) -> dict[str, Any]:
        state = self._load()
        telemetry = self.store._read_records(self.telemetry_path)
        tick_values = [float(value["tick_ms"]) for value in telemetry if isinstance(value.get("tick_ms"), (int, float))]
        p95 = None
        if tick_values:
            ordered = sorted(tick_values)
            p95 = ordered[min(len(ordered) - 1, max(0, int(round(0.95 * len(ordered) + 0.5)) - 1))]
        latest_checkpoint = None
        if state.get("latest_checkpoint"):
            latest_checkpoint = self.verify_checkpoint(str(state["latest_checkpoint"]))["manifest"]["id"]
        return {
            "status": state["status"],
            "target_seconds": state["target_seconds"],
            "started_at": state.get("started_at"),
            "deadline_at": state.get("deadline_at"),
            "completed_at": state.get("completed_at"),
            "samples": state.get("samples", 0),
            "resume_count": state.get("resume_count", 0),
            "epoch_boundaries": list(state.get("epoch_boundaries", [])),
            "faults": list(state.get("faults", [])),
            "latest_checkpoint": latest_checkpoint,
            "gate_failures": list(state.get("gate_failures", [])),
            "last_error": state.get("last_error"),
            "telemetry": {
                "records": len(telemetry),
                "tick_ms_median": round(statistics.median(tick_values), 3) if tick_values else None,
                "tick_ms_p95": round(p95, 3) if p95 is not None else None,
            },
        }
