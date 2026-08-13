from __future__ import annotations

import fnmatch
import shutil
import uuid
from pathlib import Path
from typing import Any

from ccis.kernel import evidence_gate, revision_policy, storage, transition_gate


def _task(run_dir: Path) -> dict[str, Any]:
    value = storage.read_json(run_dir / "task-envelope.json")
    if not isinstance(value, dict) or value.get("ccis_object") != "ccis.task_envelope":
        raise storage.CCISError("run task envelope is missing or invalid")
    return value


def _metadata(run_dir: Path) -> dict[str, Any]:
    value = storage.read_json(run_dir / "run.json")
    if not isinstance(value, dict):
        raise storage.CCISError("run metadata is missing")
    return value


def initialize(task_envelope_path: Path, run_root: Path | None = None) -> Path:
    envelope = storage.read_json(task_envelope_path)
    if not isinstance(envelope, dict) or envelope.get("ccis_object") != "ccis.task_envelope":
        raise storage.CCISError("expected a CCIS task envelope")
    task_id = str(envelope.get("task_id", ""))
    if not task_id:
        raise storage.CCISError("task envelope has no task_id")
    authority = envelope.get("authority", {})
    if (
        authority.get("acceptance_mode") != "explicit_operator"
        or authority.get("automatic_working_tree_merge") is not False
        or authority.get("may_merge") is not False
    ):
        raise storage.CCISError("CCIS requires explicit operator acceptance and forbids automatic merge")
    repo = Path(envelope["scope"]["repository"]).expanduser().resolve()
    root = (run_root or repo / ".leafos" / "ccis" / "runs").resolve()
    run_dir = root / task_id
    if run_dir.exists():
        raise storage.CCISError(f"CCIS run already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    storage.atomic_json(run_dir / "task-envelope.json", envelope)
    storage.atomic_json(run_dir / "task.json", envelope)
    storage.atomic_json(run_dir / "objective.json", envelope["objective"])
    metadata = {
        "ccis_object": "ccis.run",
        "schema_version": 1,
        "task_id": task_id,
        "repository": str(repo),
        "created_at": storage.now(),
        "baseline_revision": storage.git(repo, "rev-parse", "HEAD").stdout.decode("ascii").strip(),
        "baseline_index_tree": storage.index_tree(repo),
        "baseline_worktree_hash": storage.tracked_worktree_snapshot(repo),
        "events_authority": "events.jsonl",
        "sqlite_role": "cache_only",
    }
    storage.atomic_json(run_dir / "run.json", metadata)
    with storage.run_lock(run_dir):
        event = storage.make_event([], task_id, "ccis.task.created", {
            "state": "CREATED",
            "task_envelope_hash": storage.file_digest(run_dir / "task-envelope.json"),
            "baseline_revision": metadata["baseline_revision"],
        })
        storage.append_event_unlocked(run_dir, event)
        storage.write_projection(run_dir, [event])
    transition_gate.advance(
        run_dir,
        "SNAPSHOTTED",
        "Authoritative repository snapshot and hashes recorded.",
        artifact_hash=storage.digest(metadata),
    )
    transition_gate.advance(
        run_dir,
        "OBJECTIVE_DEFINED",
        "Objective, invariants, tolerances, and stopping conditions recorded.",
        artifact_hash=storage.file_digest(run_dir / "objective.json"),
    )
    return run_dir


def _path_allowed(path: str, envelope: dict[str, Any]) -> bool:
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    scope = envelope["scope"]
    if any(fnmatch.fnmatch(normalized, pattern) for pattern in scope.get("denied_paths", [])):
        return False
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in scope["allowed_paths"])


def register_candidate(
    run_dir: Path,
    candidate_id: str,
    patch_path: Path,
    changes: list[dict[str, Any]],
    *,
    revision: int = 0,
    created_by: str = "leafos.ccis.candidate_builder",
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    state = storage.resume(run_dir)
    if state["state"] not in {"OBJECTIVE_DEFINED", "REVISE", "INSPECTING"}:
        raise storage.CCISError(f"candidate registration is not allowed from {state['state']}")
    envelope = _task(run_dir)
    candidates = storage.read_json(run_dir / "candidates.json", [])
    revision_policy.assert_candidate_budget(envelope, len(candidates))
    revision_policy.assert_revision_allowed(envelope, revision)
    if not patch_path.is_file():
        raise storage.CCISError(f"candidate patch does not exist: {patch_path}")
    if not changes or any(not _path_allowed(str(change.get("path", "")), envelope) for change in changes):
        raise storage.CCISError("candidate contains an empty or out-of-scope path")
    if len(changes) > int(envelope["budget"]["max_changed_files"]):
        raise storage.CCISError("candidate exceeds max_changed_files")
    if state["state"] != "INSPECTING":
        transition_gate.advance(run_dir, "INSPECTING", f"Inspecting scope for {candidate_id}.")
    destination = run_dir / "candidates" / f"{candidate_id}.patch"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(patch_path, destination)
    metadata = _metadata(run_dir)
    candidate = {
        "ccis_object": "ccis.candidate",
        "schema_version": 1,
        "candidate_id": candidate_id,
        "task_id": envelope["task_id"],
        "parent_candidate_id": candidates[-1]["candidate_id"] if candidates else None,
        "revision": revision,
        "created_at": storage.now(),
        "created_by": created_by,
        "base_revision": metadata["baseline_revision"],
        "workspace_mode": "isolated",
        "working_tree_applied": False,
        "status": "READY",
        "declared_invariants": envelope["objective"]["invariants"],
        "changes": changes,
        "artifact": {
            "path": str(destination.relative_to(run_dir)).replace("\\", "/"),
            "sha256": storage.file_digest(destination),
            "media_type": "text/x-diff",
        },
    }
    candidates.append(candidate)
    storage.atomic_json(run_dir / "candidates.json", candidates)
    transition_gate.advance(
        run_dir,
        "CANDIDATES_GENERATED",
        f"Candidate set includes {candidate_id}.",
        artifact_hash=storage.file_digest(run_dir / "candidates.json"),
    )
    roundtable = {
        "ccis_object": "ccis.roundtable_record",
        "schema_version": 1,
        "task_id": state["task_id"],
        "recorded_at": storage.now(),
        "participants": [created_by],
        "candidate_ids": [item["candidate_id"] for item in candidates],
        "selected_candidate_id": candidate_id,
        "selection_reason": "Smallest declared candidate within scope and budget.",
        "dissent": [],
    }
    storage.atomic_json(run_dir / "roundtable-record.json", roundtable)
    transition_gate.advance(
        run_dir,
        "CANDIDATE_SELECTED",
        f"Roundtable selected {candidate_id}.",
        artifact_hash=storage.file_digest(run_dir / "roundtable-record.json"),
    )
    return candidate


def evaluate_candidate(
    run_dir: Path,
    questions: list[dict[str, Any]],
    validator_results: list[dict[str, Any]],
    *,
    evaluator: str = "leafos.ccis.evidence_gate",
    requested_failure: str = "REVISE",
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    state = storage.resume(run_dir)
    if state["state"] not in {"CANDIDATE_SELECTED", "MUTATING", "VALIDATING"}:
        raise storage.CCISError(f"evaluation requires a selected or validating candidate, found {state['state']}")
    candidates = storage.read_json(run_dir / "candidates.json", [])
    candidate = candidates[-1]
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
            f"Validating {candidate['candidate_id']} against declared gates.",
            artifact_hash=candidate["artifact"]["sha256"],
        )
    evaluation_id = f"evaluation_{uuid.uuid4().hex}"
    evaluation = {
        "ccis_object": "ccis.evaluation",
        "schema_version": 1,
        "evaluation_id": evaluation_id,
        "task_id": state["task_id"],
        "candidate_id": candidate["candidate_id"],
        "evaluated_at": storage.now(),
        "evaluator": evaluator,
        "gate_state": "GATED",
        "constitutional_questions": questions,
        "validator_results": validator_results,
        "recommendation": "BLOCKED",
        "evidence_refs": [f"evidence://{state['task_id']}/evaluation.json"],
    }
    required = {item["validator_id"] for item in _task(run_dir)["validators"] if item["required"]}
    evidence_gate.assert_evaluation_gate(evaluation, required)
    evaluation["recommendation"] = evidence_gate.recommendation(evaluation, requested_failure)
    storage.atomic_json(run_dir / "evaluation.json", evaluation)
    roundtable = storage.read_json(run_dir / "roundtable-record.json", {})
    roundtable["evaluated_at"] = storage.now()
    roundtable["participants"] = list(dict.fromkeys(roundtable.get("participants", []) + [evaluator]))
    roundtable["question_results"] = questions
    storage.atomic_json(run_dir / "roundtable-record.json", roundtable)
    transition_gate.advance(
        run_dir,
        "GATED",
        f"Four-question CCIS gate recorded {evaluation_id}.",
        artifact_hash=storage.file_digest(run_dir / "evaluation.json"),
    )
    return evaluation


def decide(
    run_dir: Path,
    outcome: str,
    decided_by: str,
    reasons: list[str],
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    state = storage.resume(run_dir)
    if state["state"] != "GATED":
        raise storage.CCISError(f"decision requires GATED state, found {state['state']}")
    evaluation = storage.read_json(run_dir / "evaluation.json", {})
    if outcome != evaluation.get("recommendation"):
        raise storage.CCISError("decision outcome must match the evidence-gate recommendation")
    if not decided_by.strip() or not reasons:
        raise storage.CCISError("decision requires an actor and at least one reason")
    candidates = storage.read_json(run_dir / "candidates.json", [])
    candidate = candidates[-1]
    transition_id = f"transition_{uuid.uuid4().hex}"
    evidence_ref = f"evidence://{state['task_id']}/{transition_id}"
    next_actions = {
        "ACCEPTED": f"Stage with leafos task accept {state['task_id']}.",
        "REVISE": "Generate one revised candidate within the remaining budget.",
        "REJECTED": "Hash-verify the original state and close the isolated candidate.",
        "BLOCKED": "Resolve the recorded blocker before validation resumes.",
        "ESCALATED": "Escalate to an authorized human reviewer.",
    }
    decision = {
        "ccis_object": "ccis.decision",
        "schema_version": 1,
        "decision_id": f"decision_{uuid.uuid4().hex}",
        "task_id": state["task_id"],
        "candidate_id": candidate["candidate_id"],
        "evaluation_id": evaluation["evaluation_id"],
        "decided_at": storage.now(),
        "decided_by": decided_by,
        "outcome": outcome,
        "reasons": reasons,
        "staging_required": outcome == "ACCEPTED",
        "working_tree_merged": False,
        "authority_ref": f"authority://{state['task_id']}/explicit-operator",
        "evidence_bundle_ref": evidence_ref,
        "next_action": next_actions[outcome],
    }
    storage.atomic_json(run_dir / "decision.json", decision)
    bundle_path, _ = evidence_gate.write_evidence_bundle(
        run_dir,
        transition_id,
        candidates,
        storage.read_json(run_dir / "roundtable-record.json", {}),
        evaluation,
        decision,
    )
    result = transition_gate.advance(
        run_dir,
        transition_gate.OUTCOME_STATE[outcome],
        decision["decision_id"],
        outcome=outcome,
        transition_id=transition_id,
        evidence_bundle_ref=evidence_ref,
        decision_ref=decision["decision_id"],
    )
    result["decision"] = decision
    result["evidence_bundle"] = str(bundle_path)
    return result
