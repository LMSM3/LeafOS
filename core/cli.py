#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import ConfigError, Settings, load_settings, resolve_llama_cli
from core.control import ControlError, ControlService, EpochManager, ProjectStore, RecoveryManager, discover_project, render_context_packet
from core.control.recovery import DEFAULT_SOAK_HOURS, FAULT_KINDS
from core.control.scheduler import DEFAULT_LEASE_SECONDS, DEFAULT_WORKER_SLOTS, Scheduler
from core.models.inventory import ModelError, load_inventory, local_model_path, resolve_model, save_inventory, scan_model_dirs
from core.routing.packs import PackError, find_pack, load_pack, pack_files, route_lane, use_pack, validate_pack
from core.runtime.llama import process_alive, run_model, runtime_identity
from core.state import read_json


VERSION = (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()


def emit(value: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, ensure_ascii=False))
    elif isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, indent=2, ensure_ascii=False))


def status(settings: Settings, project_root: Path | None = None) -> dict[str, Any]:
    runtime = runtime_identity(settings)
    inventory = load_inventory(settings.inventory_path)
    usable = [model for model in inventory.get("models", []) if model.get("runtime_compatible") and local_model_path(model["path"]).is_file()]
    state = read_json(settings.state_path, {})
    running = process_alive(state.get("pid"))
    active_pack = state.get("active_pack")
    pack_ok = None
    if active_pack:
        try:
            _, pack = find_pack(settings.packs_dir, active_pack)
            pack_ok = not validate_pack(pack, inventory)
        except PackError:
            pack_ok = False
    ready = bool(runtime["reachable"] and usable and pack_ok is not False)
    control = None
    if project_root is not None:
        project_store = ProjectStore(project_root)
        if project_store.initialized:
            try:
                control = project_store.summary()
            except ControlError as error:
                control = {"status": "degraded", "project": str(project_root), "error": str(error)}
                ready = False
    scheduler = None
    if project_root is not None and ProjectStore(project_root).scheduler_path.is_file():
        try:
            scheduler = Scheduler(settings, project_root).status()
        except ControlError as error:
            scheduler = {"status": "degraded", "error": str(error)}
            ready = False
    epoch = None
    if project_root is not None:
        project_store = ProjectStore(project_root)
        if (project_store.state_dir / "epochs.json").is_file():
            try:
                epoch = EpochManager(project_store).status()
            except ControlError as error:
                epoch = {"status": "degraded", "error": str(error)}
                ready = False
    recovery = None
    if project_root is not None:
        recovery_manager = RecoveryManager(settings, project_root)
        if recovery_manager.state_path.is_file():
            try:
                recovery = recovery_manager.status()
            except ControlError as error:
                recovery = {"status": "degraded", "error": str(error)}
                ready = False
    glyph = "🍃" if running else ("🌿" if ready else ("🌱" if not settings.inventory_path.exists() else "🍂"))
    active_model = None
    if state.get("model_id"):
        try:
            active_model = resolve_model(inventory, state["model_id"], require_usable=False)
        except ModelError:
            pass
    if active_model is None and usable:
        active_model = usable[0]
    return {
        "glyph": glyph,
        "version": VERSION,
        "ready": ready,
        "runtime": "working" if running else ("ready" if runtime["reachable"] else "unreachable"),
        "backend": "llama.cpp" + (f" / {runtime['device'].split(':', 1)[0]}" if runtime.get("device") else ""),
        "pack": active_pack or "none",
        "model": active_model.get("name") if active_model else "none",
        "quant": active_model.get("quant") if active_model else None,
        "context": settings.context,
        "memory": "fit policy" if settings.gpu_layers is None else f"{settings.gpu_layers} GPU layers",
        "gpu": runtime.get("device") or "unavailable",
        "pid": state.get("pid") if running else None,
        "models": inventory.get("summary", {"found": 0, "usable": 0, "invalid": 0}),
        "control": control,
        "scheduler": scheduler,
        "epoch": epoch,
        "recovery": recovery,
    }


def print_status(value: dict[str, Any]) -> None:
    print(f"{value['glyph']} LeafOS {value['version']}")
    print()
    rows = [
        ("Runtime", value["runtime"]), ("Backend", value["backend"]), ("Pack", value["pack"]),
        ("Model", f"{value['model']} {value['quant'] or ''}".rstrip()),
        ("Context", value["context"]), ("Memory", value["memory"]),
        ("GPU", value["gpu"]),
    ]
    if value.get("pid"):
        rows.append(("PID", value["pid"]))
    control = value.get("control")
    if isinstance(control, dict):
        if control.get("status") == "degraded":
            rows.append(("Control", f"degraded: {control.get('error')}"))
        else:
            task_counts = ", ".join(f"{count} {name}" for name, count in sorted(control.get("tasks", {}).items())) or "0"
            rows.extend([
                ("Project", control.get("project", {}).get("name", "unknown")),
                ("Objective", control.get("objective", "none")),
                ("Tasks", task_counts),
            ])
    scheduler = value.get("scheduler")
    if isinstance(scheduler, dict):
        if scheduler.get("status") == "degraded":
            rows.append(("Scheduler", f"degraded: {scheduler.get('error')}"))
        else:
            policy = scheduler.get("policy", {})
            workers = scheduler.get("workers", {})
            queue = scheduler.get("queue", {})
            rows.extend([
                ("Supervisor", scheduler.get("status", "stopped")),
                ("Workers", f"{len(workers)}/{policy.get('worker_slots', 0)} + {policy.get('verifier_slots', 0)} verifier"),
                ("Queue", ", ".join(f"{value} {key}" for key, value in sorted(queue.items())) or "empty"),
            ])
    epoch = value.get("epoch")
    if isinstance(epoch, dict):
        if epoch.get("status") == "degraded":
            rows.append(("Epoch", f"degraded: {epoch.get('error')}"))
        else:
            rows.append((
                "Epoch",
                f"{epoch.get('latest_epoch') or 'none'} / {epoch.get('interval_minutes')} min / "
                f"{'due' if epoch.get('due') else 'scheduled'}",
            ))
    recovery = value.get("recovery")
    if isinstance(recovery, dict):
        if recovery.get("status") == "degraded" and recovery.get("error"):
            rows.append(("Soak", f"degraded: {recovery.get('error')}"))
        else:
            rows.append((
                "Soak",
                f"{recovery.get('status', 'unknown')} / {recovery.get('samples', 0)} samples / "
                f"{len(recovery.get('epoch_boundaries', []))} epochs",
            ))
    for key, item in rows:
        print(f"{key:<12} {item}")


def doctor(settings: Settings, project_root: Path | None = None) -> tuple[dict[str, Any], bool]:
    runtime = runtime_identity(settings)
    inventory = load_inventory(settings.inventory_path)
    usable = int(inventory.get("summary", {}).get("usable", 0))
    inventory_exists = settings.inventory_path.is_file()
    checks = {
        "configuration": {"level": "pass", "detail": str(settings.root / "config" / "leaf.conf")},
        "llama.cpp": {"level": "pass" if runtime["reachable"] else "fail", "detail": runtime.get("path") or "llama-cli not found"},
        "models": {
            "level": "pass" if usable > 0 else ("warn" if not inventory_exists else "fail"),
            "detail": f"{usable} usable GGUF model(s); run 'leafctl models scan' after changes" if inventory_exists else "not scanned; run 'leafctl models scan'",
        },
    }
    state = read_json(settings.state_path, {})
    if state.get("active_pack"):
        try:
            _, pack = find_pack(settings.packs_dir, state["active_pack"])
            errors = validate_pack(pack, inventory)
            checks["pack"] = {"level": "fail" if errors else "pass", "detail": "; ".join(errors) if errors else pack["id"]}
        except PackError as error:
            checks["pack"] = {"level": "fail", "detail": str(error)}
    if project_root is not None:
        project_store = ProjectStore(project_root)
        if project_store.initialized:
            try:
                summary = project_store.summary()
                audit = project_store.audit()
                checks["control"] = {
                    "level": "pass",
                    "detail": (
                        f"{summary['phase']} / {summary['mode']} / "
                        f"{audit['tasks']} task(s) / {audit['evidence']} evidence record(s)"
                    ),
                }
            except ControlError as error:
                checks["control"] = {"level": "fail", "detail": str(error)}
            if project_store.scheduler_path.is_file():
                try:
                    scheduler = Scheduler(settings, project_root).status()
                    reasons = scheduler.get("degraded_reasons", [])
                    checks["scheduler"] = {
                        "level": "warn" if reasons else "pass",
                        "detail": (
                            f"{scheduler['policy']['worker_slots']} workers + 1 verifier; "
                            + ("; ".join(reasons) if reasons else "resource probes and leases valid")
                        ),
                    }
                except ControlError as error:
                    checks["scheduler"] = {"level": "fail", "detail": str(error)}
            epoch_state = project_store.state_dir / "epochs.json"
            if epoch_state.is_file():
                try:
                    epoch = EpochManager(project_store).status()
                    latest = epoch.get("latest_epoch")
                    if latest:
                        EpochManager(project_store).verify_epoch(str(latest))
                    checks["epoch"] = {
                        "level": "pass",
                        "detail": (
                            f"{latest or 'no completed review'} / "
                            f"{epoch['interval_minutes']} minute interval / immutable records valid"
                        ),
                    }
                except ControlError as error:
                    checks["epoch"] = {"level": "fail", "detail": str(error)}
            recovery_manager = RecoveryManager(settings, project_root)
            if recovery_manager.state_path.is_file():
                try:
                    recovery = recovery_manager.status()
                    failures = recovery.get("gate_failures", [])
                    checks["recovery"] = {
                        "level": "fail" if recovery.get("status") == "failed" else ("warn" if failures else "pass"),
                        "detail": (
                            f"{recovery.get('status')} / {recovery.get('samples')} telemetry samples / "
                            f"{len(recovery.get('epoch_boundaries', []))} epoch boundaries"
                            + (f"; {'; '.join(failures)}" if failures else "")
                        ),
                    }
                except ControlError as error:
                    checks["recovery"] = {"level": "fail", "detail": str(error)}
    return {"version": VERSION, "checks": checks}, all(item["level"] != "fail" for item in checks.values())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="leafctl", description="One reliable LeafOS control surface")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--project", help="project root for persistent .leaf control state")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version")
    sub.add_parser("status")
    sub.add_parser("doctor")
    models = sub.add_parser("models")
    models_sub = models.add_subparsers(dest="models_command", required=True)
    models_sub.add_parser("scan")
    models_sub.add_parser("list")
    model_show = models_sub.add_parser("show")
    model_show.add_argument("model")
    run = sub.add_parser("run")
    run.add_argument("model")
    run.add_argument("--prompt")
    run.add_argument("--tokens", type=int, default=128)
    run.add_argument("--context", type=int)
    run.add_argument("--cpu", action="store_true")
    pack = sub.add_parser("pack")
    pack_sub = pack.add_subparsers(dest="pack_command", required=True)
    pack_sub.add_parser("list")
    pack_show = pack_sub.add_parser("show")
    pack_show.add_argument("pack")
    pack_use = pack_sub.add_parser("use")
    pack_use.add_argument("pack")
    route = sub.add_parser("route")
    route.add_argument("lane")
    route.add_argument("--prompt")
    route.add_argument("--tokens", type=int, default=128)
    route.add_argument("--cpu", action="store_true")
    swarm = sub.add_parser("swarm")
    swarm_sub = swarm.add_subparsers(dest="swarm_command", required=True)
    swarm_plan = swarm_sub.add_parser("plan")
    swarm_plan.add_argument("--objective", required=True)
    swarm_plan.add_argument("--replace", action="store_true")
    swarm_status = swarm_sub.add_parser("status")
    swarm_status.set_defaults(swarm_action="status")
    swarm_run = swarm_sub.add_parser("run")
    swarm_run.add_argument("--workers", type=int, default=DEFAULT_WORKER_SLOTS)
    swarm_run.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)
    swarm_run.add_argument("--max-ticks", type=int)
    swarm_run.add_argument("--interval", type=float, default=0.25)
    swarm_foreground = swarm_sub.add_parser("foreground")
    swarm_foreground.add_argument("state", choices=("on", "off"))
    swarm_sub.add_parser("stop")
    swarm_recover = swarm_sub.add_parser("recover")
    swarm_recover.set_defaults(swarm_action="recover")
    swarm_checkpoint = swarm_sub.add_parser("checkpoint")
    swarm_checkpoint.add_argument("--reason", required=True)
    swarm_soak = swarm_sub.add_parser("soak")
    swarm_soak.add_argument("--hours", type=float, default=DEFAULT_SOAK_HOURS)
    swarm_soak.add_argument("--sample-seconds", type=float)
    swarm_soak.add_argument("--max-samples", type=int)
    swarm_soak.add_argument("--replace", action="store_true")
    swarm_fault = swarm_sub.add_parser("fault")
    swarm_fault.add_argument("--kind", choices=sorted(FAULT_KINDS), required=True)
    swarm_fault.add_argument("--outcome", choices=("passed", "failed", "observed"), required=True)
    swarm_fault.add_argument("--detail", required=True)
    task = sub.add_parser("task")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    task_submit = task_sub.add_parser("submit")
    task_submit.add_argument("--goal", required=True)
    task_submit.add_argument("--lane", default="fast")
    task_submit.add_argument("--prompt")
    task_submit.add_argument("--input", action="append", default=[], help="bounded read-only project source path")
    task_submit.add_argument("--depends-on", action="append", default=[])
    task_submit.add_argument("--tokens", type=int, default=128)
    task_submit.add_argument("--context", type=int)
    task_submit.add_argument("--timeout", type=int, default=300)
    task_submit.add_argument("--attempts", type=int, default=2)
    task_submit.add_argument("--tool-attempts", type=int, default=3)
    task_submit.add_argument("--verifier-attempts", type=int, default=2)
    task_submit.add_argument("--priority", type=int, default=50)
    task_submit.add_argument(
        "--class", dest="schedule_class",
        choices=("interactive", "critical", "verifier", "speculative", "compression"),
        default="critical",
    )
    task_submit.add_argument("--cpu", action="store_true")
    task_submit.add_argument("--defer", action="store_true")
    task_inspect = task_sub.add_parser("inspect")
    task_inspect.add_argument("task_id")
    task_tool = task_sub.add_parser("tool")
    task_tool.add_argument("task_id")
    task_tool.add_argument("--tool", choices=("artifact", "inspect", "search", "test"), required=True)
    task_tool.add_argument("--path")
    task_tool.add_argument("--query")
    task_tool.add_argument("--selector")
    task_tool.add_argument("--timeout", type=int, default=120)
    task_verify = task_sub.add_parser("verify")
    task_verify.add_argument("task_id")
    task_verify.add_argument("--lane", default="verifier")
    task_verify.add_argument("--tokens", type=int, default=256)
    task_verify.add_argument("--context", type=int)
    task_verify.add_argument("--timeout", type=int, default=300)
    task_verify.add_argument("--cpu", action="store_true")
    task_accept = task_sub.add_parser("accept")
    task_accept.add_argument("task_id")
    task_accept.add_argument("--reason", required=True)
    task_dispute = task_sub.add_parser("dispute")
    task_dispute.add_argument("task_id")
    task_dispute.add_argument("--evidence", action="append", required=True)
    task_dispute.add_argument("--reason", required=True)
    task_cancel = task_sub.add_parser("cancel")
    task_cancel.add_argument("task_id")
    task_cancel.add_argument("--reason", required=True)
    context_command = sub.add_parser("context")
    context_sub = context_command.add_subparsers(dest="context_command", required=True)
    context_sub.add_parser("export")
    epoch = sub.add_parser("epoch")
    epoch_sub = epoch.add_subparsers(dest="epoch_command", required=True)
    epoch_sub.add_parser("status")
    epoch_configure = epoch_sub.add_parser("configure")
    epoch_configure.add_argument("--minutes", required=True, type=int)
    epoch_review = epoch_sub.add_parser("review")
    epoch_review.add_argument("--manual", action="store_true")
    return parser


def _normalize_global_options(argv: list[str]) -> list[str]:
    globals_: list[str] = []
    remainder: list[str] = []
    project_seen = False
    index = 0
    while index < len(argv):
        value = argv[index]
        if value == "--json":
            if "--json" not in globals_:
                globals_.append("--json")
            index += 1
            continue
        if value == "--project":
            if project_seen or index + 1 >= len(argv):
                remainder.append(value)
                index += 1
                continue
            globals_.extend(["--project", argv[index + 1]])
            project_seen = True
            index += 2
            continue
        if value.startswith("--project=") and not project_seen:
            globals_.append(value)
            project_seen = True
            index += 1
            continue
        remainder.append(value)
        index += 1
    return [*globals_, *remainder]


def main(argv: list[str] | None = None) -> int:
    argv = _normalize_global_options(list(sys.argv[1:] if argv is None else argv))
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings()
        project_root = None
        if args.command in {"status", "doctor", "swarm", "task", "context", "epoch"}:
            project_root = discover_project(explicit=args.project)
        if args.command == "version":
            emit(VERSION, args.json)
            return 0
        if args.command == "status":
            value = status(settings, project_root)
            emit(value, True) if args.json else print_status(value)
            return 0 if value["ready"] else 1
        if args.command == "doctor":
            value, ok = doctor(settings, project_root)
            if args.json:
                emit(value, True)
            else:
                for name, check in value["checks"].items():
                    print(f"{check['level'].upper():<5} {name:<14} {check['detail']}")
            return 0 if ok else 1
        if args.command in {"swarm", "task", "context", "epoch"}:
            assert project_root is not None
            control = ControlService(settings, project_root)
            if args.command == "swarm":
                scheduler = Scheduler(settings, project_root)
                if args.swarm_command == "plan":
                    value = control.plan(args.objective, replace=args.replace)
                    value["scheduler"] = scheduler.initialize()
                elif args.swarm_command == "status":
                    value = scheduler.status()
                elif args.swarm_command == "run":
                    scheduler.initialize(args.workers, args.lease_seconds)
                    value = scheduler.drive(max_ticks=args.max_ticks, interval=args.interval)
                elif args.swarm_command == "foreground":
                    value = scheduler.set_foreground(args.state == "on")
                elif args.swarm_command == "recover":
                    value = RecoveryManager(settings, project_root).recover()
                elif args.swarm_command == "checkpoint":
                    value = RecoveryManager(settings, project_root).checkpoint(args.reason)
                elif args.swarm_command == "soak":
                    value = RecoveryManager(settings, project_root).run(
                        hours=args.hours,
                        sample_seconds=args.sample_seconds,
                        max_samples=args.max_samples,
                        replace=args.replace,
                    )
                elif args.swarm_command == "fault":
                    value = RecoveryManager(settings, project_root).record_fault(args.kind, args.outcome, args.detail)
                else:
                    value = scheduler.stop()
                emit(value, args.json)
                return 0
            if args.command == "task":
                if args.task_command == "inspect":
                    emit(control.inspect(args.task_id), args.json)
                    return 0
                if args.task_command == "tool":
                    value = control.run_tool(
                        args.task_id,
                        args.tool,
                        path=args.path,
                        query=args.query,
                        selector=args.selector,
                        timeout_seconds=args.timeout,
                    )
                    emit(value, args.json)
                    return 0 if value["evidence"].get("exit_code") == 0 else 1
                if args.task_command == "verify":
                    value = control.verify(
                        args.task_id,
                        lane=args.lane,
                        tokens=args.tokens,
                        context=args.context,
                        timeout_seconds=args.timeout,
                        cpu=args.cpu,
                    )
                    emit(value, args.json)
                    return 0 if value["evidence"].get("verdict") != "invalid" else 1
                if args.task_command == "accept":
                    emit(control.accept(args.task_id, args.reason), args.json)
                    return 0
                if args.task_command == "dispute":
                    emit(control.dispute(args.task_id, args.evidence, args.reason), args.json)
                    return 0
                if args.task_command == "cancel":
                    emit(Scheduler(settings, project_root).cancel(args.task_id, args.reason), args.json)
                    return 0
                value = control.submit(
                    args.goal,
                    args.lane,
                    prompt=args.prompt,
                    input_paths=args.input,
                    dependencies=args.depends_on,
                    tokens=args.tokens,
                    context=args.context,
                    timeout_seconds=args.timeout,
                    attempts=args.attempts,
                    tool_attempts=args.tool_attempts,
                    verifier_attempts=args.verifier_attempts,
                    priority=args.priority,
                    schedule_class=args.schedule_class,
                    cpu=args.cpu,
                    defer=args.defer,
                )
                emit(value, args.json)
                return 1 if value.get("status") == "failed" else 0
            if args.command == "epoch":
                if args.epoch_command == "status":
                    value = control.epoch_status()
                elif args.epoch_command == "configure":
                    value = control.configure_epoch(args.minutes)
                else:
                    value = control.review_epoch(manual=args.manual)
                emit(value, args.json)
                return 0
            value = control.export_context()
            emit(value, True) if args.json else print(render_context_packet(value), end="")
            return 0
        inventory = load_inventory(settings.inventory_path)
        if args.command == "models":
            if args.models_command == "scan":
                previous = {model.get("path"): model for model in inventory.get("models", [])}
                inventory = scan_model_dirs(settings.model_dirs, resolve_llama_cli(settings) is not None)
                for model in inventory["models"]:
                    prior = previous.get(model.get("path"))
                    if not prior:
                        continue
                    unchanged = (
                        prior.get("size_bytes") == model.get("size_bytes")
                        and prior.get("mtime_ns") is not None
                        and prior.get("mtime_ns") == model.get("mtime_ns")
                    )
                    if unchanged and prior.get("runtime_compatibility") == "verified":
                        for key in ("runtime_compatibility", "load_status", "last_exit_code", "last_load_at"):
                            model[key] = prior.get(key)
                save_inventory(settings.inventory_path, inventory)
                emit(inventory if args.json else inventory["summary"], args.json)
                return 0 if inventory["summary"]["usable"] else 1
            if args.models_command == "list":
                emit(inventory.get("models", []), True if args.json else False)
                return 0
            emit(resolve_model(inventory, args.model, require_usable=False), args.json)
            return 0
        if args.command == "run":
            model = resolve_model(inventory, args.model)
            scheduler = None
            try:
                candidate = discover_project()
                store = ProjectStore(candidate)
                if store.initialized and store.scheduler_path.is_file():
                    scheduler = Scheduler(settings, candidate)
                    scheduler.set_foreground(True)
            except ControlError:
                scheduler = None
            try:
                return run_model(settings, model, args.prompt, args.tokens, args.context, args.cpu)
            finally:
                if scheduler is not None:
                    scheduler.set_foreground(False)
        if args.command == "pack":
            if args.pack_command == "list":
                values = []
                for path in pack_files(settings.packs_dir):
                    try:
                        candidate = load_pack(path)
                        errors = validate_pack(candidate, inventory)
                        values.append({"id": candidate["id"], "name": candidate["name"], "usable": not errors, "errors": errors})
                    except PackError as error:
                        values.append({"id": path.stem, "name": path.stem, "usable": False, "errors": [str(error)]})
                emit(values, True if args.json else False)
                return 0
            _, candidate = find_pack(settings.packs_dir, args.pack)
            errors = validate_pack(candidate, inventory)
            if args.pack_command == "show":
                emit({**candidate, "usable": not errors, "errors": errors}, args.json)
                return 0 if not errors else 1
            state = use_pack(candidate, inventory, settings.state_path)
            emit({"active_pack": state["active_pack"], "active_lane": state["active_lane"], "model_id": state["model_id"]}, args.json)
            return 0
        if args.command == "route":
            state = read_json(settings.state_path, {})
            if not state.get("active_pack"):
                raise PackError("no active pack; run 'leafctl pack use <pack>'")
            _, candidate = find_pack(settings.packs_dir, state["active_pack"])
            model = route_lane(candidate, args.lane, inventory)
            if args.prompt is None:
                emit({"pack": candidate["id"], "lane": args.lane, "model": model}, args.json)
                return 0
            return run_model(settings, model, args.prompt, args.tokens, None, args.cpu)
    except (ConfigError, ControlError, ModelError, PackError, RuntimeError, OSError, ValueError) as error:
        print(f"leafctl: {error}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
