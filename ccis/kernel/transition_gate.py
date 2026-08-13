from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from . import storage


OUTCOME_STATE = {
    "ACCEPTED": "ACCEPTED",
    "REVISE": "REVISE",
    "REJECTED": "REJECTED",
    "BLOCKED": "BLOCKED",
    "ESCALATED": "ESCALATED",
}

LEGAL_TRANSITIONS = {
    "CREATED": {"SNAPSHOTTED"},
    "SNAPSHOTTED": {"OBJECTIVE_DEFINED"},
    "OBJECTIVE_DEFINED": {"INSPECTING"},
    "INSPECTING": {"CANDIDATES_GENERATED"},
    "CANDIDATES_GENERATED": {"CANDIDATE_SELECTED"},
    "CANDIDATE_SELECTED": {"MUTATING"},
    "MUTATING": {"VALIDATING"},
    "VALIDATING": {"GATED"},
    "GATED": set(OUTCOME_STATE.values()),
    "REVISE": {"INSPECTING"},
    "ACCEPTED": {"STAGED"},
    "REJECTED": {"ROLLED_BACK"},
    "BLOCKED": {"VALIDATING", "ESCALATED"},
    "ESCALATED": set(),
    "STAGED": set(),
    "ROLLED_BACK": set(),
}


def advance(
    run_dir: Path,
    to_state: str,
    trigger: str,
    *,
    outcome: str | None = None,
    transition_id: str | None = None,
    evidence_bundle_ref: str = "evidence://pending",
    decision_ref: str | None = None,
    rollback: dict[str, Any] | None = None,
    worker_id: str = "leafos.ccis.control-plane",
    artifact_hash: str | None = None,
) -> dict[str, Any]:
    """Validate and commit one authoritative state transition."""
    run_dir = run_dir.resolve()
    with storage.run_lock(run_dir):
        events = storage.read_events(run_dir)
        storage.verify_events(events)
        state = storage.project_state(events)
        from_state = state["state"]
        if to_state not in LEGAL_TRANSITIONS.get(from_state, set()):
            raise storage.CCISError(f"illegal CCIS transition: {from_state} -> {to_state}")
        if outcome is not None:
            expected = OUTCOME_STATE.get(outcome)
            if expected != to_state:
                raise storage.CCISError(f"outcome {outcome} cannot transition to {to_state}")
        elif from_state == "GATED":
            raise storage.CCISError("a transition out of GATED requires an explicit outcome")

        transition_id = transition_id or f"transition_{uuid.uuid4().hex}"
        transition = {
            "ccis_object": "ccis.transition",
            "schema_version": 1,
            "transition_id": transition_id,
            "task_id": state["task_id"],
            "sequence": state["event_sequence"] + 1,
            "occurred_at": storage.now(),
            "from_state": from_state,
            "to_state": to_state,
            "worker_id": worker_id,
            "artifact_hash": artifact_hash or storage.digest({"trigger": trigger, "to_state": to_state}),
            "reason": trigger,
            "outcome": outcome,
            "trigger": trigger,
            "state_hash_before": storage.digest(state),
            "state_hash_after": storage.digest({**state, "state": to_state}),
            "checkpoint_ref": f"checkpoint://{state['task_id']}/event-{state['event_sequence'] + 1}",
            "evidence_bundle_ref": evidence_bundle_ref,
            "decision_ref": decision_ref,
            "rollback": rollback,
        }
        transition_path = run_dir / "transitions" / f"{transition_id}.json"
        storage.atomic_json(transition_path, transition)
        event = storage.make_event(
            events,
            state["task_id"],
            "ccis.transition.committed",
            transition,
            [evidence_bundle_ref],
            transition_id,
        )
        storage.append_event_unlocked(run_dir, event)
        events.append(event)
        projected = storage.write_projection(run_dir, events)
        return {"transition": transition, "state": projected, "event": event}
