from __future__ import annotations

import copy
from typing import Any

from . import storage, task_registry


REDUCER_VERSION = 1
TERMINAL_STATES = {"SUCCEEDED", "FAILED", "BLOCKED", "REVISE", "REJECTED", "ESCALATED", "CANCELLED"}
OUTCOME_STATES = {
    "task.succeeded": "SUCCEEDED", "task.failed": "FAILED", "task.blocked": "BLOCKED",
    "task.revise": "REVISE", "task.rejected": "REJECTED", "task.escalated": "ESCALATED",
    "task.cancelled": "CANCELLED",
}


def initial_state() -> dict[str, Any]:
    return {"logical_tick": 0, "tasks": {}, "leases": {}}


def _task(state: dict[str, Any], task_id: str | None) -> dict[str, Any]:
    if not task_id or task_id not in state["tasks"]:
        raise storage.CCISError(f"allocation event refers to unknown task: {task_id}")
    return state["tasks"][task_id]


def apply_event(state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(state)
    event_type = event["event_type"]
    task_id = event["task_id"]
    payload = event["payload"]
    if event_type == "allocation.clock_observed":
        if payload.get("from_tick") != result["logical_tick"] or payload.get("to_tick") != event["logical_tick"]:
            raise storage.CCISError("allocation clock event is incompatible with reducer state")
        result["logical_tick"] = event["logical_tick"]
        return result
    if event["logical_tick"] != result["logical_tick"]:
        raise storage.CCISError("non-clock allocation event cannot advance logical time")

    if event_type == "task.admitted":
        if not task_id or task_id in result["tasks"]:
            raise storage.CCISError(f"task admission is duplicate or invalid: {task_id}")
        task = payload.get("task")
        if not isinstance(task, dict) or task.get("task_digest") != task_registry.task_digest(task):
            raise storage.CCISError("admitted task contract or digest is invalid")
        if task["task_id"] != task_id:
            raise storage.CCISError("admitted task ID differs from event task ID")
        result["tasks"][task_id] = {
            "task": task, "state": "ADMITTED", "effective_priority": task["priority"],
            "enqueue_sequence": None, "attempts": 0, "lease_id": None,
            "last_reason": None, "last_event_sequence": event["sequence"],
        }
        return result

    record = _task(result, task_id)
    if event_type == "task.queued":
        if record["state"] != "ADMITTED":
            raise storage.CCISError(f"task {task_id} cannot be queued from {record['state']}")
        record["state"] = "QUEUED"
        record["enqueue_sequence"] = event["sequence"]
        record["last_reason"] = payload.get("reason")
    elif event_type == "task.priority_aged":
        if record["state"] != "QUEUED":
            raise storage.CCISError(f"task {task_id} priority cannot age from {record['state']}")
        if payload.get("from_priority") != record["effective_priority"]:
            raise storage.CCISError(f"priority-aging event does not match task {task_id}")
        record["effective_priority"] = int(payload["to_priority"])
    elif event_type == "lease.acquired":
        if record["state"] != "QUEUED" or record["lease_id"] is not None:
            raise storage.CCISError(f"task {task_id} cannot acquire a lease from {record['state']}")
        lease = payload.get("lease")
        if not isinstance(lease, dict) or lease.get("task_id") != task_id:
            raise storage.CCISError("lease acquisition payload is invalid")
        task_registry.validate_contract("allocation-lease", lease)
        lease_id = lease.get("lease_id")
        if not isinstance(lease_id, str) or lease_id in result["leases"]:
            raise storage.CCISError("lease identity is duplicate or invalid")
        result["leases"][lease_id] = {**lease, "state": "ACTIVE"}
        record["lease_id"] = lease_id
        record["state"] = "LEASED"
    elif event_type == "task.started":
        if record["state"] != "LEASED" or payload.get("lease_id") != record["lease_id"]:
            raise storage.CCISError(f"task {task_id} cannot start without its active lease")
        attempt = int(payload.get("attempt", 0))
        if attempt != record["attempts"] + 1:
            raise storage.CCISError(f"task {task_id} attempt sequence is invalid")
        record["attempts"] = attempt
        record["state"] = "RUNNING"
    elif event_type in OUTCOME_STATES:
        if record["state"] not in {"RUNNING", "LEASED"}:
            raise storage.CCISError(f"task {task_id} cannot finish from {record['state']}")
        record["state"] = OUTCOME_STATES[event_type]
        record["last_reason"] = payload.get("reason")
    elif event_type == "lease.released":
        lease_id = payload.get("lease_id")
        lease = result["leases"].get(lease_id)
        if not lease or lease["state"] != "ACTIVE" or lease["task_id"] != task_id:
            raise storage.CCISError(f"lease release is invalid for task {task_id}")
        lease["state"] = "RELEASED"
        lease["released_tick"] = result["logical_tick"]
        record["lease_id"] = None
    elif event_type == "lease.expired":
        lease_id = payload.get("lease_id")
        lease = result["leases"].get(lease_id)
        if not lease or lease["state"] != "ACTIVE" or lease["task_id"] != task_id:
            raise storage.CCISError(f"lease expiry is invalid for task {task_id}")
        if lease["expires_tick"] > result["logical_tick"]:
            raise storage.CCISError(f"lease {lease_id} has not reached its recorded expiry tick")
        next_state = payload.get("next_state")
        if next_state not in {"QUEUED", "BLOCKED"}:
            raise storage.CCISError("lease expiry must explicitly select QUEUED or BLOCKED")
        lease["state"] = "EXPIRED"
        lease["expired_tick"] = result["logical_tick"]
        record["lease_id"] = None
        record["state"] = next_state
        record["last_reason"] = "LEASE_EXPIRED"
        if next_state == "QUEUED":
            record["enqueue_sequence"] = event["sequence"]
    else:
        raise storage.CCISError(f"allocation reducer has no event handler for {event_type}")
    record["last_event_sequence"] = event["sequence"]
    return result


def reduce_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    state = initial_state()
    for event in events:
        state = apply_event(state, event)
    return state


def dependency_blockers(state: dict[str, Any], task: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for dependency in task["dependencies"]:
        record = state["tasks"].get(dependency["task_id"])
        if record is None:
            blockers.append(f"missing:{dependency['task_id']}")
        elif record["state"] != dependency["required_disposition"]:
            blockers.append(f"state:{dependency['task_id']}={record['state']}")
    return blockers


def claim_conflicts(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left["resource"] == right["resource"] and (left["mode"] == "exclusive" or right["mode"] == "exclusive")


def resource_blockers(state: dict[str, Any], task: dict[str, Any]) -> list[str]:
    blockers: set[str] = set()
    for lease in state["leases"].values():
        if lease["state"] != "ACTIVE" or lease["task_id"] == task["task_id"]:
            continue
        for wanted in task["resource_claims"]:
            for held in lease["claims"]:
                if claim_conflicts(wanted, held):
                    blockers.add(f"resource:{wanted['resource']}@{lease['lease_id']}")
    return sorted(blockers)
