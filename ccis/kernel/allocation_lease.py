from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from . import allocation_events, allocation_heap, allocation_reducer, storage, task_registry


class Allocator:
    """Serialized writer over an authoritative allocation journal."""

    def __init__(self, allocation_root: Path):
        self.root = allocation_root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _change(self, operation: Callable[[list[dict[str, Any]], dict[str, Any]], Any]) -> Any:
        with storage.run_lock(self.root):
            events = allocation_events.read_events(self.root)
            state = allocation_reducer.reduce_events(events)
            result = operation(events, state)
            allocation_heap.write_snapshot(self.root, events)
            return result

    @staticmethod
    def _append(events: list[dict[str, Any]], root: Path, event: dict[str, Any]) -> None:
        allocation_events.append_event_unlocked(root, event)
        events.append(event)

    def admit(self, proposal: dict[str, Any]) -> dict[str, Any]:
        task = task_registry.admit_task(proposal)

        def operation(events: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
            if task["task_id"] in state["tasks"]:
                raise storage.CCISError(f"allocation task already exists: {task['task_id']}")
            event = allocation_events.make_event(
                events, "task.admitted", {"task": task}, logical_tick=state["logical_tick"], task_id=task["task_id"]
            )
            self._append(events, self.root, event)
            storage.atomic_json(self.root / "tasks" / f"{task['task_id'].replace(':', '_')}.json", task)
            return task

        return self._change(operation)

    def queue(self, task_id: str, reason: str = "ADMITTED") -> None:
        def operation(events: list[dict[str, Any]], state: dict[str, Any]) -> None:
            if task_id not in state["tasks"]:
                raise storage.CCISError(f"cannot queue unknown allocation task: {task_id}")
            event = allocation_events.make_event(
                events, "task.queued", {"reason": reason}, logical_tick=state["logical_tick"], task_id=task_id
            )
            self._append(events, self.root, event)

        self._change(operation)

    def observe_clock(self, to_tick: int, reason: str) -> None:
        def operation(events: list[dict[str, Any]], state: dict[str, Any]) -> None:
            if isinstance(to_tick, bool) or not isinstance(to_tick, int) or to_tick <= state["logical_tick"]:
                raise storage.CCISError("logical clock observation must advance by a positive recorded amount")
            event = allocation_events.make_event(
                events, "allocation.clock_observed",
                {"from_tick": state["logical_tick"], "to_tick": to_tick, "reason": reason}, logical_tick=to_tick,
            )
            self._append(events, self.root, event)

        self._change(operation)

    def age_priority(self, task_id: str, to_priority: int, reason: str) -> None:
        def operation(events: list[dict[str, Any]], state: dict[str, Any]) -> None:
            record = state["tasks"].get(task_id)
            if not record:
                raise storage.CCISError(f"cannot age unknown allocation task: {task_id}")
            event = allocation_events.make_event(
                events, "task.priority_aged",
                {"from_priority": record["effective_priority"], "to_priority": to_priority, "reason": reason},
                logical_tick=state["logical_tick"], task_id=task_id,
            )
            self._append(events, self.root, event)

        self._change(operation)

    def claim_next(self, worker_id: str, lease_ticks: int = 10) -> dict[str, Any] | None:
        def operation(events: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any] | None:
            queues = allocation_heap.project(state)
            if not queues["ready"]:
                return None
            task_id = queues["ready"][0]["task_id"]
            task = state["tasks"][task_id]["task"]
            sequence = len(events) + 1
            lease = {
                "lease_id": f"lease-{sequence:08d}", "task_id": task_id, "worker_id": worker_id,
                "acquired_tick": state["logical_tick"], "expires_tick": state["logical_tick"] + max(1, lease_ticks),
                "claims": task["resource_claims"],
            }
            event = allocation_events.make_event(
                events, "lease.acquired", {"lease": lease}, logical_tick=state["logical_tick"], task_id=task_id
            )
            self._append(events, self.root, event)
            return lease

        return self._change(operation)

    def start(self, task_id: str, lease_id: str) -> int:
        def operation(events: list[dict[str, Any]], state: dict[str, Any]) -> int:
            record = state["tasks"].get(task_id)
            if not record:
                raise storage.CCISError(f"cannot start unknown allocation task: {task_id}")
            attempt = record["attempts"] + 1
            event = allocation_events.make_event(
                events, "task.started", {"lease_id": lease_id, "attempt": attempt},
                logical_tick=state["logical_tick"], task_id=task_id,
            )
            self._append(events, self.root, event)
            return attempt

        return self._change(operation)

    def finish(self, task_id: str, lease_id: str, status: str, reason: str, result_digest: str) -> None:
        event_types = {
            "SUCCEEDED": "task.succeeded", "FAILED": "task.failed", "BLOCKED": "task.blocked",
            "REVISE": "task.revise", "REJECTED": "task.rejected", "ESCALATED": "task.escalated",
        }
        if status not in event_types:
            raise storage.CCISError(f"unsupported typed task disposition: {status}")

        def operation(events: list[dict[str, Any]], state: dict[str, Any]) -> None:
            outcome = allocation_events.make_event(
                events, event_types[status], {"reason": reason, "result_digest": result_digest},
                logical_tick=state["logical_tick"], task_id=task_id,
            )
            self._append(events, self.root, outcome)
            release = allocation_events.make_event(
                events, "lease.released", {"lease_id": lease_id, "reason": "TASK_FINISHED"},
                logical_tick=state["logical_tick"], task_id=task_id,
            )
            self._append(events, self.root, release)

        self._change(operation)

    def expire_due(self) -> list[str]:
        def operation(events: list[dict[str, Any]], state: dict[str, Any]) -> list[str]:
            expired: list[str] = []
            for lease_id, lease in sorted(state["leases"].items()):
                if lease["state"] != "ACTIVE" or lease["expires_tick"] > state["logical_tick"]:
                    continue
                record = state["tasks"][lease["task_id"]]
                maximum = record["task"]["retry_policy"]["max_attempts"]
                next_state = "QUEUED" if record["attempts"] < maximum else "BLOCKED"
                event = allocation_events.make_event(
                    events, "lease.expired", {"lease_id": lease_id, "next_state": next_state},
                    logical_tick=state["logical_tick"], task_id=lease["task_id"],
                )
                self._append(events, self.root, event)
                state = allocation_reducer.apply_event(state, event)
                expired.append(lease_id)
            return expired

        return self._change(operation)

    def status(self) -> dict[str, Any]:
        snapshot, cache_action = allocation_heap.verify_or_rebuild(self.root)
        return {"cache_action": cache_action, "snapshot": snapshot}


def run_ccis_validator_task(
    allocation_root: Path, run_dir: Path, workspace: Path, *, worker_id: str = "local-ccis"
) -> dict[str, Any]:
    allocator = Allocator(allocation_root)
    task = task_registry.adapt_ccis_validator(run_dir, workspace)
    allocator.admit(task)
    allocator.queue(task["task_id"])
    lease = allocator.claim_next(worker_id, lease_ticks=max(1, task["budget"]["wall_time_seconds"]))
    if lease is None or lease["task_id"] != task["task_id"]:
        raise storage.CCISError("adapted CCIS validator could not acquire its declared resources")
    allocator.start(task["task_id"], lease["lease_id"])
    try:
        result = task_registry.execute_typed_task(task, {"run_dir": str(run_dir), "workspace": str(workspace)})
    except Exception as error:
        failure = {
            "ccis_object": "ccis.typed_result", "schema_version": 1,
            "task_id": task["task_id"], "task_digest": task["task_digest"],
            "task_type": task["task_type"], "task_version": task["task_version"],
            "status": "FAILED", "summary": f"Native validator adapter failed: {error}",
            "started_at": storage.now(), "completed_at": storage.now(), "evidence_refs": [],
            "resource_use": [], "output": {"error_type": type(error).__name__},
        }
        task_registry.validate_contract("typed-result", failure)
        storage.atomic_json(allocator.root / "results" / f"{task['task_id'].replace(':', '_')}.json", failure)
        allocator.finish(task["task_id"], lease["lease_id"], "FAILED", failure["summary"], storage.digest(failure))
        raise
    storage.atomic_json(allocator.root / "results" / f"{task['task_id'].replace(':', '_')}.json", result)
    allocator.finish(task["task_id"], lease["lease_id"], result["status"], result["summary"], storage.digest(result))
    return result


def run_evidence_integrity_task(
    allocation_root: Path,
    target_ref: Path,
    target_kind: str,
    *,
    evidence_bytes: int,
    wall_time_seconds: int = 30,
    expected_digest: str | None = None,
    task_id: str | None = None,
    worker_id: str = "local-evidence-debugger",
) -> dict[str, Any]:
    allocation_scope = allocation_root.expanduser().resolve(strict=False)
    target = target_ref.expanduser().resolve(strict=False)
    target_scope = target if target.is_dir() else target.parent
    if (
        allocation_scope == target_scope
        or allocation_scope in target_scope.parents
        or target_scope in allocation_scope.parents
    ):
        raise storage.CCISError("evidence allocation output cannot overlap the read-only inspection target")
    task = task_registry.adapt_evidence_integrity(
        target,
        target_kind,
        evidence_bytes=evidence_bytes,
        wall_time_seconds=wall_time_seconds,
        expected_digest=expected_digest,
        task_id=task_id,
    )
    allocator = Allocator(allocation_scope)
    allocator.admit(task)
    allocator.queue(task["task_id"])
    lease = allocator.claim_next(worker_id, lease_ticks=wall_time_seconds)
    if lease is None or lease["task_id"] != task["task_id"]:
        raise storage.CCISError("evidence integrity task could not acquire its allocation lease")
    allocator.start(task["task_id"], lease["lease_id"])
    try:
        result = task_registry.execute_typed_task(task, {})
    except Exception as error:
        failure = {
            "ccis_object": "ccis.typed_result", "schema_version": 1,
            "task_id": task["task_id"], "task_digest": task["task_digest"],
            "task_type": task["task_type"], "task_version": task["task_version"],
            "status": "FAILED", "summary": f"Evidence integrity debugger failed: {error}",
            "started_at": storage.now(), "completed_at": storage.now(), "evidence_refs": [],
            "resource_use": [], "output": {"error_type": type(error).__name__},
        }
        task_registry.validate_contract("typed-result", failure)
        storage.atomic_json(allocator.root / "results" / f"{task['task_id'].replace(':', '_')}.json", failure)
        allocator.finish(task["task_id"], lease["lease_id"], "FAILED", failure["summary"], storage.digest(failure))
        raise
    storage.atomic_json(allocator.root / "results" / f"{task['task_id'].replace(':', '_')}.json", result)
    allocator.finish(task["task_id"], lease["lease_id"], result["status"], result["summary"], storage.digest(result))
    return result
