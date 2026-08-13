"""Durable installer state discovery and resume inspection.

This module is read-only with respect to active transfers. It reads resolved
plans, event logs, manifest files, and destination directories to report what
can safely resume, verify, or continue.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .catalog import MODEL_CATALOG
from .orchestrator import InstallPlan, read_plan, verify_item, verify_plan


STATE_DIR_NAME = MODEL_CATALOG.storage.get("state_directory", ".leafos-installer")


@dataclass(frozen=True)
class DiscoveredTransfer:
    plan_path: Path
    resolved_plan_path: Path
    state_root: Path
    destination_root: Path
    plan_id: str
    plan_profile: str
    is_running: bool
    active_pids: list[int]
    completed_items: int
    total_items: int
    completed_bytes: int
    total_bytes: Optional[int]
    log_path: Optional[Path]
    next_actions: list[str]


def _state_root_from_destination(destination_root: Path) -> Path:
    return destination_root / STATE_DIR_NAME


def _find_resolved_plans(*, roots: list[Path]) -> list[Path]:
    """Locate resolved-plan JSON files without scanning protected live dirs."""
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for candidate in root.rglob("*.json"):
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if (
                isinstance(data, dict)
                and data.get("schema_version") == 1
                and data.get("resolved") is True
                and "items" in data
                and "plan_id" in data
            ):
                found.append(candidate)
    return found


def _active_pids_for_plan(plan_path: Path, state_root: Path) -> list[int]:
    """Check for running processes referencing this resolved plan path."""
    active: list[int] = []
    try:
        import psutil
    except Exception:  # noqa: BLE001
        return active

    # Match either the absolute path or the relative path from the repo root.
    cwd = Path(__file__).resolve().parent.parent.parent.parent
    candidates = [str(plan_path).replace("\\", "/")]
    try:
        candidates.append(str(plan_path.relative_to(cwd)).replace("\\", "/"))
    except ValueError:
        pass

    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            raw_cmdline = proc.info.get("cmdline") or []
            joined = " ".join(raw_cmdline).replace("\\", "/")
            if not joined:
                continue
            executable = str(raw_cmdline[0] if raw_cmdline else "")
            is_python = "python" in Path(executable).name.lower()
            matches_plan = any(c.lower() in joined.lower() for c in candidates)
            if is_python and matches_plan:
                active.append(proc.info["pid"])
        except Exception:  # noqa: BLE001
            continue
    # Also guard against stale lock file with a live pid.
    lock_path = state_root / "install.lock"
    if lock_path.is_file():
        try:
            text = lock_path.read_text(encoding="ascii")
            m = re.match(r"(\d+)", text)
            if m:
                pid = int(m.group(1))
                if psutil.pid_exists(pid) and pid not in active:
                    active.append(pid)
        except Exception:  # noqa: BLE001
            pass
    return active


def _completed_bytes(plan: InstallPlan) -> int:
    total = 0
    for item in plan.items:
        target = Path(plan.destination_root) / item.local_dir
        if not item.expected_files:
            continue
        for expected in item.expected_files:
            local = target / expected["path"]
            if local.is_file():
                total += local.stat().st_size
    return total


def _count_complete_items(plan: InstallPlan) -> int:
    complete = 0
    for item in plan.items:
        if not item.expected_files:
            continue
        report = verify_item(plan, item)
        if report["success"]:
            complete += 1
    return complete


def discover_resume_state(
    *,
    search_roots: Optional[list[Path]] = None,
) -> list[DiscoveredTransfer]:
    """Scan for resumable installation plans without mutating them."""
    if search_roots is None:
        search_roots = []
    default_root = Path(MODEL_CATALOG.storage["environment_variable"]) if MODEL_CATALOG.storage.get("environment_variable") in {} else None
    if default_root is None:
        default_root = MODEL_CATALOG.storage.get("default_relative_to_home", ".leaf/models")
    # Start from known destination roots: env, default, installer-local.
    candidates = [Path(r).expanduser().resolve() for r in search_roots]
    installer_local = Path(__file__).resolve().parent.parent / "models"
    if installer_local not in candidates:
        candidates.append(installer_local)

    discovered: list[DiscoveredTransfer] = []
    seen: set[Path] = set()
    for plan_file in _find_resolved_plans(roots=candidates):
        if plan_file in seen:
            continue
        seen.add(plan_file)
        try:
            plan = read_plan(plan_file)
        except Exception:  # noqa: BLE001
            continue
        if not plan.resolved:
            continue
        destination = Path(plan.destination_root).expanduser().resolve()
        state_root = _state_root_from_destination(destination)
        active_pids = _active_pids_for_plan(plan_file, state_root)
        completed = _count_complete_items(plan)
        completed_bytes = _completed_bytes(plan)
        total_bytes = plan.estimated_bytes
        next_actions = []
        if active_pids:
            next_actions.append("monitor")
        elif completed < len(plan.items):
            next_actions.append("resume")
        next_actions.append("verify")
        discovered.append(
            DiscoveredTransfer(
                plan_path=Path(plan_file),
                resolved_plan_path=Path(plan_file),
                state_root=state_root,
                destination_root=destination,
                plan_id=plan.plan_id,
                plan_profile=plan.profile,
                is_running=bool(active_pids),
                active_pids=active_pids,
                completed_items=completed,
                total_items=len(plan.items),
                completed_bytes=completed_bytes,
                total_bytes=total_bytes,
                log_path=None,
                next_actions=next_actions,
            )
        )
    return discovered


def inspect_store(destination_root: Path) -> dict:
    """Produce a verification summary for every artifact in a destination tree."""
    root = destination_root.expanduser().resolve()
    discovered = discover_resume_state(search_roots=[root])

    reports: list[dict] = []
    for transfer in discovered:
        try:
            plan = read_plan(transfer.resolved_plan_path)
            if plan.resolved:
                report = verify_plan(plan, compute_hash=False)
                reports.append(report)
        except Exception as exc:  # noqa: BLE001
            reports.append({"plan_path": str(transfer.resolved_plan_path), "error": str(exc)})

    # Also enumerate GGUF artifacts under root.
    artifacts: list[dict] = []
    if root.is_dir():
        for path in sorted(root.rglob("*.gguf")):
            artifacts.append(
                {
                    "path": str(path.relative_to(root)),
                    "bytes": path.stat().st_size,
                }
            )

    return {
        "ok": True,
        "operation": "inspect-store",
        "destination_root": str(root),
        "transfers": [_transfer_to_dict(t) for t in discovered],
        "verification_reports": reports,
        "artifacts": artifacts,
        "next_actions": ["verify", "resume"] if discovered else ["verify"],
    }


def _transfer_to_dict(t: DiscoveredTransfer) -> dict:
    return {
        "plan_id": t.plan_id,
        "profile": t.plan_profile,
        "resolved_plan_path": str(t.resolved_plan_path),
        "state_root": str(t.state_root),
        "destination_root": str(t.destination_root),
        "is_running": t.is_running,
        "active_pids": t.active_pids,
        "completed_items": t.completed_items,
        "total_items": t.total_items,
        "completed_bytes": t.completed_bytes,
        "total_bytes": t.total_bytes,
        "next_actions": t.next_actions,
    }


def inspect_resume_state(search_roots: Optional[list[Path]] = None) -> dict:
    discovered = discover_resume_state(search_roots=search_roots or [])
    state = "running" if any(t.is_running for t in discovered) else ("resumable" if discovered else "empty")
    return {
        "ok": True,
        "operation": "inspect-resume",
        "state": state,
        "transfers": [_transfer_to_dict(t) for t in discovered],
        "next_actions": ["monitor" if state == "running" else "resume", "verify"],
    }
