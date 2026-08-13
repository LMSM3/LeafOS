from __future__ import annotations

from pathlib import Path
from typing import Any

from . import evidence_gate, storage, transition_gate


def _run(run_dir: Path) -> dict[str, Any]:
    value = storage.read_json(run_dir / "run.json")
    if not isinstance(value, dict):
        raise storage.CCISError(f"missing CCIS run metadata: {run_dir}")
    return value


def _selected_candidate(run_dir: Path) -> dict[str, Any]:
    values = storage.read_json(run_dir / "candidates.json", [])
    if not isinstance(values, list) or not values:
        raise storage.CCISError("CCIS run has no candidate")
    candidate = values[-1]
    if candidate.get("status") != "READY":
        raise storage.CCISError("latest candidate is not READY")
    return candidate


def stage_accepted_candidate(run_dir: Path, operator: str, confirmation: str) -> dict[str, Any]:
    """Explicitly stage an accepted patch in Git's index; never touch the worktree."""
    run_dir = run_dir.resolve()
    state = storage.resume(run_dir)
    if state["state"] != "ACCEPTED":
        raise storage.CCISError(f"task acceptance requires ACCEPTED state, found {state['state']}")
    metadata = _run(run_dir)
    task_id = metadata["task_id"]
    if not operator.strip() or confirmation != task_id:
        raise storage.CCISError("explicit acceptance requires an operator and exact task-id confirmation")
    repo = Path(metadata["repository"])
    if storage.index_tree(repo) != metadata["baseline_index_tree"]:
        raise storage.CCISError("Git index changed since CCIS initialization; refusing to stage over operator work")
    before_worktree = storage.tracked_worktree_snapshot(repo)
    candidate = _selected_candidate(run_dir)
    patch_path = run_dir / candidate["artifact"]["path"]
    if not patch_path.is_file() or storage.file_digest(patch_path) != candidate["artifact"]["sha256"]:
        raise storage.CCISError("candidate patch is missing or hash-invalid")
    decision = storage.read_json(run_dir / "decision.json", {})
    evidence_ref = decision.get("evidence_bundle_ref", "evidence://pending")
    transition_id = evidence_ref.rsplit("/", 1)[-1]
    evidence_gate.verify_evidence_bundle(
        run_dir / "evidence" / transition_id / "evidence-bundle.json"
    )
    storage.git(repo, "apply", "--cached", "--check", str(patch_path))
    storage.git(repo, "apply", "--cached", str(patch_path))
    after_worktree = storage.tracked_worktree_snapshot(repo)
    if after_worktree != before_worktree:
        raise storage.CCISError("working-tree content changed during index-only acceptance")

    result = transition_gate.advance(
        run_dir,
        "STAGED",
        f"leafos task accept by {operator}",
        evidence_bundle_ref=evidence_ref,
        decision_ref=decision.get("decision_id"),
    )
    result["staging"] = {
        "operator": operator,
        "index_tree_before": metadata["baseline_index_tree"],
        "index_tree_after": storage.index_tree(repo),
        "working_tree_hash_before": before_worktree,
        "working_tree_hash_after": after_worktree,
        "working_tree_merged": False,
    }
    storage.atomic_json(run_dir / "staging-receipt.json", result["staging"])
    return result


def rollback_rejected_candidate(run_dir: Path) -> dict[str, Any]:
    """Close a rejected isolated candidate after hash-verifying original state."""
    run_dir = run_dir.resolve()
    state = storage.resume(run_dir)
    if state["state"] != "REJECTED":
        raise storage.CCISError(f"rollback requires REJECTED state, found {state['state']}")
    metadata = _run(run_dir)
    repo = Path(metadata["repository"])
    restored = storage.tracked_worktree_snapshot(repo)
    target = metadata["baseline_worktree_hash"]
    if restored != target:
        raise storage.CCISError("original worktree hash changed; refusing destructive rollback")
    return transition_gate.advance(
        run_dir,
        "ROLLED_BACK",
        "rejected isolated candidate discarded",
        evidence_bundle_ref=storage.read_json(run_dir / "decision.json", {}).get("evidence_bundle_ref", "evidence://pending"),
        rollback={"target_hash": target, "restored_hash": restored, "verified": True},
    )
