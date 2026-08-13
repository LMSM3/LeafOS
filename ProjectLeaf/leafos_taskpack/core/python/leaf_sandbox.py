#!/usr/bin/env python3
"""Stage and inspect isolated LeafOS overnight sandbox runs without starting a model."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import leaf_telemetry
import leaf_monday_report
import leaf_dual_harness

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SANDBOX = ROOT / "sandbox" / "overnight-01"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in {path}: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def load_manifest(sandbox: Path) -> dict[str, Any]:
    manifest = load_json(sandbox / "manifest.json")
    if manifest.get("run_id") != "overnight-01":
        raise ValueError("manifest run_id must be overnight-01")
    if manifest.get("mode") != "sequential":
        raise ValueError("manifest mode must be sequential")
    if manifest.get("task_budget_minutes") != 182:
        raise ValueError("manifest task_budget_minutes must be 182")
    transition = manifest.get("transition", {})
    if transition.get("cleanup_seconds") != 60:
        raise ValueError("transition cleanup must be 60 seconds")
    if transition.get("loading_animation_seconds") != 20:
        raise ValueError("transition loading animation must be 20 seconds")
    if manifest.get("checkpoint_policy", {}).get("first_validated_checkpoint_due_minutes") != 30:
        raise ValueError("manifest checkpoint policy must require a 30-minute checkpoint")
    projects = manifest.get("coding_projects", []) + manifest.get("game_projects", [])
    if len(projects) != 6:
        raise ValueError("manifest must define exactly six projects")
    return manifest


def project_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return manifest["coding_projects"] + manifest["game_projects"]


def task_order(sandbox: Path) -> list[dict[str, Any]]:
    schedule = load_json(sandbox / "schedule.json")
    assignments = schedule.get("assignments", [])
    if len(assignments) != 6 or schedule.get("execution") != "sequential":
        raise ValueError("schedule must define six sequential assignments")
    return sorted(assignments, key=lambda item: item["sequence"])


def task_path(sandbox: Path, entry: dict[str, Any]) -> Path:
    return sandbox / entry["target"]


def write_status(sandbox: Path, manifest: dict[str, Any], staged: list[str]) -> Path:
    status = {
        "leafos_object": "overnight_sandbox_status",
        "run_id": manifest["run_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": manifest["mode"],
        "task_budget_minutes": manifest["task_budget_minutes"],
        "transition": manifest["transition"],
        "checkpoint_policy": manifest["checkpoint_policy"],
        "staged_tasks": staged,
        "worker_started": False,
        "model_downloads": False,
    }
    output = sandbox / "run-status.json"
    output.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    return output


def cmd_validate(sandbox: Path, _args: argparse.Namespace) -> int:
    try:
        manifest = load_manifest(sandbox)
        entries = {entry["id"]: entry for entry in project_entries(manifest)}
        for assignment in task_order(sandbox):
            if assignment.get("task_id") not in entries:
                raise ValueError(f"schedule references unknown task: {assignment.get('task_id')}")
            if assignment.get("budget_minutes") != 182:
                raise ValueError("each assignment budget must be 182 minutes")
        for entry in entries.values():
            work_order = sandbox / entry["work_order"]
            if not work_order.is_file():
                raise ValueError(f"work order missing: {work_order}")
            work_order_data = load_json(work_order)
            if work_order_data.get("id") != entry["id"]:
                raise ValueError(f"work order id mismatch: {work_order}")
        print("overnight sandbox is valid")
        return 0
    except ValueError as error:
        print(f"invalid sandbox: {error}", file=sys.stderr)
        return 1

def cmd_harness(sandbox: Path, args: argparse.Namespace) -> int:
    config = ROOT / "config" / "dual_harness.json"
    harness = leaf_dual_harness.Harness(sandbox / "harness", leaf_dual_harness.read(config, {}))
    if args.action == "init": harness.save(); harness.say("status", "dual harness initialized")
    elif args.action == "tick": harness.tick()
    elif args.action == "post": harness.post(args.message or "")
    else: print(json.dumps(harness.state, indent=2))
    return 0


def cmd_telemetry(sandbox: Path, args: argparse.Namespace) -> int:
    log = Path(args.log) if args.log else sandbox / "telemetry.jsonl"
    if args.action == "append":
        if not args.event:
            raise ValueError("telemetry append requires --event")
        return leaf_telemetry.cmd_append(argparse.Namespace(log=str(log), event=args.event))
    if args.action == "tensor":
        if not args.tensor or not args.run_id:
            raise ValueError("telemetry tensor requires --tensor and --run-id")
        return leaf_telemetry.cmd_tensor(argparse.Namespace(
            log=str(log), tensor=args.tensor, run_id=args.run_id,
            task_id=args.task_id, elapsed_seconds=args.elapsed_seconds,
        ))
    return leaf_telemetry.cmd_summary(argparse.Namespace(log=str(log), output=args.output))


def cmd_report(sandbox: Path, args: argparse.Namespace) -> int:
    if args.watch:
        while True:
            print(leaf_monday_report.report_once(sandbox, not args.no_open), flush=True)
            time.sleep(max(1, args.interval_minutes * 60))
    print(leaf_monday_report.report_once(sandbox, not args.no_open))
    return 0


def cmd_plan(sandbox: Path, _args: argparse.Namespace) -> int:
    manifest = load_manifest(sandbox)
    entries = {entry["id"]: entry for entry in project_entries(manifest)}
    transition = manifest["transition"]
    print(f"run: {manifest['run_id']} ({manifest['nominal_duration_minutes']} minutes sequential)")
    print(f"between tasks: {transition['cleanup_seconds']}s cleanup + {transition['loading_animation_seconds']}s loading animation")
    for assignment in task_order(sandbox):
        entry = entries[assignment["task_id"]]
        source = (sandbox / entry["source"]).resolve()
        print(f"{assignment['sequence']}. {entry['id']} — {assignment['budget_minutes']} min")
        print(f"   source: {source}")
        print(f"   target: {task_path(sandbox, entry)}")
    print("No model is started by this command.")
    return 0


def cmd_transition(sandbox: Path, args: argparse.Namespace) -> int:
    manifest = load_manifest(sandbox)
    transition = manifest["transition"]
    if not args.execute:
        print(
            f"dry transition: {transition['cleanup_seconds']}s cleanup + "
            f"{transition['loading_animation_seconds']}s loading animation"
        )
        print("No files are deleted and no model is started. Re-run with --execute to wait.")
        return 0

    cleanup_seconds = transition["cleanup_seconds"]
    loading_seconds = transition["loading_animation_seconds"]
    print(f"cleanup: {cleanup_seconds}s")
    time.sleep(cleanup_seconds)
    print("loading: ", end="", flush=True)
    for second in range(loading_seconds):
        time.sleep(1)
        print(".", end="", flush=True)
    print(" complete")
    return 0


def cmd_stage(sandbox: Path, args: argparse.Namespace) -> int:
    manifest = load_manifest(sandbox)
    entries = {entry["id"]: entry for entry in project_entries(manifest)}
    selected = [args.task] if args.task else [item["task_id"] for item in task_order(sandbox)]
    unknown = sorted(set(selected) - set(entries))
    if unknown:
        print("unknown task id: " + ", ".join(unknown), file=sys.stderr)
        return 1
    if not args.yes:
        print("Dry run only. Re-run with --yes to copy sources into isolated work directories.")
        return cmd_plan(sandbox, args)

    staged: list[str] = []
    for task_id in selected:
        entry = entries[task_id]
        source = (sandbox / entry["source"]).resolve()
        target = task_path(sandbox, entry)
        if not source.is_dir():
            print(f"source directory missing: {source}", file=sys.stderr)
            return 1
        if target.exists():
            print(f"refusing to overwrite existing staged directory: {target}", file=sys.stderr)
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        staged.append(task_id)
    status = write_status(sandbox, manifest, staged)
    print(f"staged {len(staged)} task(s); status: {status}")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--sandbox", default=str(DEFAULT_SANDBOX), help="sandbox directory")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    commands.add_parser("plan")
    transition = commands.add_parser("transition")
    transition.add_argument("--execute", action="store_true", help="run the 60-second cleanup and 20-second animation")
    telemetry = commands.add_parser("telemetry")
    telemetry.add_argument("action", choices=["append", "tensor", "summary"])
    telemetry.add_argument("--log")
    telemetry.add_argument("--event")
    telemetry.add_argument("--tensor")
    telemetry.add_argument("--run-id")
    telemetry.add_argument("--task-id")
    telemetry.add_argument("--elapsed-seconds", type=float, default=0)
    telemetry.add_argument("--output")
    report = commands.add_parser("report")
    report.add_argument("--watch", action="store_true")
    report.add_argument("--interval-minutes", type=float, default=30)
    report.add_argument("--no-open", action="store_true")
    harness = commands.add_parser("harness")
    harness.add_argument("action", choices=["init", "tick", "post", "status"])
    harness.add_argument("--message")
    stage = commands.add_parser("stage")
    stage.add_argument("--task", help="stage one task id instead of all six")
    stage.add_argument("--yes", action="store_true", help="confirm source copying into work directories")
    return result


def main() -> int:
    args = parser().parse_args()
    sandbox = Path(args.sandbox).resolve()
    handlers = {"validate": cmd_validate, "plan": cmd_plan, "transition": cmd_transition, "telemetry": cmd_telemetry, "report": cmd_report, "harness": cmd_harness, "stage": cmd_stage}
    return handlers[args.command](sandbox, args)


if __name__ == "__main__":
    raise SystemExit(main())
