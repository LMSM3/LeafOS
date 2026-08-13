#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LeafOS node engine -- the local half of the Leaf SSH node system.

One leaf install plays two roles. This module is the *receiver* engine plus the
JSON helpers the *distributor* bash layer needs (so we avoid a hard jq
dependency on the hot path).

Receiver responsibilities:
    init / status / hardware
    task state machine: inbox -> queued -> running -> done | failed
    runners: echo, shell, hardware
    JSONL task logs + results/<TASK_ID>/result.json

Distributor helpers:
    new-task-id, stamp-task   (build a task descriptor with a TASK_ID)
    registry-add/list/get     (nodes.json read/write)

Transport (ssh/scp/local) lives in core/remote/remote.sh. This file never opens
a socket; it just manages files and runs local subprocesses.
"""

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime


def _force_utf8_streams():
    """Emit UTF-8 regardless of console code page (cp1252 capture safety)."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (ValueError, OSError):
                pass


_force_utf8_streams()

_HERE_NODE = os.path.dirname(os.path.abspath(__file__))

def _read_version():
    for candidate in (
        os.path.join(_HERE_NODE, "..", "..", "VERSION"),
        os.path.join(_HERE_NODE, "..", "..", "..", "VERSION"),
    ):
        try:
            p = os.path.normpath(candidate)
            if os.path.isfile(p):
                v = open(p, encoding="utf-8").read().strip()
                if v:
                    return v
        except OSError:
            pass
    return "0.5.0"

VERSION = _read_version()
STATE_DIRS = ["inbox", "queued", "running", "done", "failed"]
ALL_DIRS = STATE_DIRS + ["logs", "results"]
TERMINAL_EVENTS = ("done", "failed", "cancelled")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def leaf_home(override=None):
    """Resolve the node workspace: --home > $LEAF_HOME > ~/.leaf."""
    if override:
        return os.path.abspath(os.path.expanduser(override))
    env = os.environ.get("LEAF_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.abspath(os.path.expanduser("~/.leaf"))


def _ts():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _ensure_dirs(home):
    for d in ALL_DIRS:
        os.makedirs(os.path.join(home, d), exist_ok=True)


# ---------------------------------------------------------------------------
# JSONL logging
# ---------------------------------------------------------------------------
class TaskLog(object):
    """Append-only JSONL writer for one task."""

    def __init__(self, home, task_id):
        self.path = os.path.join(home, "logs", "{}.jsonl".format(task_id))
        self.task_id = task_id

    def event(self, event, **fields):
        record = {"time": _ts(), "event": event, "task_id": self.task_id}
        record.update(fields)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record


# ---------------------------------------------------------------------------
# Task file location / movement
# ---------------------------------------------------------------------------
def _task_path(home, task_id, state):
    return os.path.join(home, state, "{}.json".format(task_id))


def _find_task(home, task_id):
    """Return (state, path) for a task, searching all state dirs."""
    for state in STATE_DIRS:
        path = _task_path(home, task_id, state)
        if os.path.exists(path):
            return state, path
    return None, None


def _move_task(home, task_id, from_state, to_state):
    src = _task_path(home, task_id, from_state)
    dst = _task_path(home, task_id, to_state)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)
    return dst


def _cancel_flag(home, task_id):
    return os.path.join(home, "running", "{}.cancel".format(task_id))


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------
def run_echo(home, task, log):
    """Echo runner: sleep then emit the message. Honors cancellation."""
    payload = task.get("payload", {})
    message = payload.get("message", "hello from node")
    duration = float(payload.get("duration_sec", 0) or 0)

    waited = 0.0
    step = 0.25
    while waited < duration:
        if os.path.exists(_cancel_flag(home, task["task_id"])):
            return 130, "cancelled", {"message": None}
        time.sleep(min(step, duration - waited))
        waited += step

    log.event("stdout", text=message)
    return 0, "ok", {"message": message}


def run_shell(home, task, log):
    """Shell runner: execute payload.command, streaming output as events."""
    payload = task.get("payload", {})
    command = payload.get("command") or payload.get("cmd")
    if not command:
        log.event("stderr", text="shell runner: missing payload.command")
        return 2, "error", {"error": "missing command"}

    if os.path.exists(_cancel_flag(home, task["task_id"])):
        return 130, "cancelled", {}

    try:
        proc = subprocess.Popen(
            command, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
    except OSError as exc:
        log.event("stderr", text="spawn failed: {}".format(exc))
        return 1, "error", {"error": str(exc)}

    lines = []
    for line in iter(proc.stdout.readline, ""):
        text = line.rstrip("\n")
        lines.append(text)
        log.event("stdout", text=text)
    proc.stdout.close()
    code = proc.wait()
    status = "ok" if code == 0 else "error"
    return code, status, {"exit_code": code, "lines": len(lines)}


def run_hardware(home, task, log):
    """Hardware runner: probe and emit the report as the result."""
    report = probe_hardware()
    log.event("stdout", text="hardware probe complete")
    return 0, "ok", {"hardware": report}


RUNNERS = {
    "echo": run_echo,
    "shell": run_shell,
    "hardware": run_hardware,
}


# ---------------------------------------------------------------------------
# Hardware probe
# ---------------------------------------------------------------------------
def _probe_ram_bytes():
    try:
        if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names:
            return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError):
        pass
    if platform.system() == "Windows":
        try:
            import ctypes

            class _MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MemStatus()
            stat.dwLength = ctypes.sizeof(_MemStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return int(stat.ullTotalPhys)
        except Exception:
            pass
    return None


def _probe_gpus():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader"],
            stderr=subprocess.DEVNULL, universal_newlines=True, timeout=8,
        )
    except Exception:
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if parts and parts[0]:
            gpus.append({"name": parts[0],
                         "memory_total": parts[1] if len(parts) > 1 else None})
    return gpus


def probe_hardware():
    ram = _probe_ram_bytes()
    return {
        "leafos_object": "hardware_probe",
        "hostname": socket.gethostname(),
        "platform": platform.system() or sys.platform,
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "ram_bytes": ram,
        "ram_gb": round(ram / (1024 ** 3), 2) if ram else None,
        "gpus": _probe_gpus(),
        "probed_at": _ts(),
    }


# ---------------------------------------------------------------------------
# Node commands
# ---------------------------------------------------------------------------
def cmd_init(args):
    home = leaf_home(args.home)
    _ensure_dirs(home)
    node_path = os.path.join(home, "node.json")
    node = {
        "leafos_object": "node",
        "node_id": args.node_id or socket.gethostname(),
        "role": args.role,
        "accepts_tasks": True,
        "hardware_probe": True,
        "version": VERSION,
        "created_by": "leaf",
        "created_at": _ts(),
    }
    with open(node_path, "w", encoding="utf-8") as fh:
        json.dump(node, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    if args.json:
        print(json.dumps(node, ensure_ascii=False))
    else:
        print("node initialized at {}".format(home))
        print("  node_id: {}".format(node["node_id"]))
        print("  role:    {}".format(node["role"]))
    return 0


def _count_state(home, state):
    d = os.path.join(home, state)
    if not os.path.isdir(d):
        return 0
    return len([f for f in os.listdir(d) if f.endswith(".json")])


def cmd_status(args):
    home = leaf_home(args.home)
    node_path = os.path.join(home, "node.json")
    node_id = "uninitialized"
    role = "unknown"
    state = "uninitialized"
    if os.path.exists(node_path):
        try:
            with open(node_path, "r", encoding="utf-8") as fh:
                node = json.load(fh)
            node_id = node.get("node_id", node_id)
            role = node.get("role", role)
            state = "ready"
        except (OSError, ValueError):
            state = "corrupt"
    status = {
        "leafos_object": "node_status",
        "node_id": node_id,
        "role": role,
        "state": state,
        "home": home,
        "tasks_running": _count_state(home, "running"),
        "tasks_queued": _count_state(home, "queued") + _count_state(home, "inbox"),
        "tasks_done": _count_state(home, "done"),
        "tasks_failed": _count_state(home, "failed"),
    }
    if args.json:
        print(json.dumps(status, ensure_ascii=False))
    else:
        for key in ("node_id", "state", "tasks_running", "tasks_queued",
                    "tasks_done", "tasks_failed"):
            print("  {:<14} {}".format(key, status[key]))
    return 0


def cmd_hardware(args):
    report = probe_hardware()
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print("  hostname   {}".format(report["hostname"]))
        print("  platform   {} {}".format(report["platform"], report["machine"]))
        print("  cpu_count  {}".format(report["cpu_count"]))
        print("  ram_gb     {}".format(report["ram_gb"]))
        if report["gpus"]:
            for gpu in report["gpus"]:
                print("  gpu        {} ({})".format(gpu["name"], gpu["memory_total"]))
        else:
            print("  gpu        none detected")
    return 0


# ---------------------------------------------------------------------------
# Task commands (receiver)
# ---------------------------------------------------------------------------
def cmd_task_start(args):
    home = leaf_home(args.home)
    _ensure_dirs(home)
    task_id = args.task_id

    state, path = _find_task(home, task_id)
    if path is None:
        print("task not found: {}".format(task_id), file=sys.stderr)
        return 1
    if state in ("done", "failed"):
        print("task already terminal ({}): {}".format(state, task_id), file=sys.stderr)
        return 1

    try:
        with open(path, "r", encoding="utf-8") as fh:
            task = json.load(fh)
    except (OSError, ValueError) as exc:
        print("bad task file: {}".format(exc), file=sys.stderr)
        return 1
    task.setdefault("task_id", task_id)
    kind = task.get("kind", "echo")

    log = TaskLog(home, task_id)
    log.event("queued", kind=kind)
    if state == "inbox":
        _move_task(home, task_id, "inbox", "queued")
        state = "queued"
    _move_task(home, task_id, state, "running")
    log.event("started", runner=kind)

    runner = RUNNERS.get(kind)
    if runner is None:
        log.event("stderr", text="unknown task kind: {}".format(kind))
        exit_code, status, result = 2, "error", {"error": "unknown kind"}
    else:
        try:
            exit_code, status, result = runner(home, task, log)
        except Exception as exc:  # never let a runner crash the node
            log.event("stderr", text="runner exception: {}".format(exc))
            exit_code, status, result = 1, "error", {"error": str(exc)}

    cancelled = os.path.exists(_cancel_flag(home, task_id)) or status == "cancelled"
    final_state = "failed" if (cancelled or exit_code != 0) else "done"
    _move_task(home, task_id, "running", final_state)

    _write_result(home, task_id, task, kind, exit_code, status, result)

    if cancelled:
        log.event("cancelled", exit_code=exit_code)
    elif final_state == "done":
        log.event("done", exit_code=0)
    else:
        log.event("failed", exit_code=exit_code)

    flag = _cancel_flag(home, task_id)
    if os.path.exists(flag):
        os.remove(flag)

    print("task {} -> {} (exit {})".format(task_id, final_state, exit_code))
    return 0 if final_state == "done" else exit_code


def _write_result(home, task_id, task, kind, exit_code, status, result):
    result_dir = os.path.join(home, "results", task_id)
    os.makedirs(result_dir, exist_ok=True)
    doc = {
        "leafos_object": "task_result",
        "task_id": task_id,
        "kind": kind,
        "exit_code": exit_code,
        "status": status,
        "finished_at": _ts(),
        "output": result,
    }
    with open(os.path.join(result_dir, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def cmd_task_list(args):
    home = leaf_home(args.home)
    rows = []
    states = [args.state] if args.state else STATE_DIRS
    for state in states:
        d = os.path.join(home, state)
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if fname.endswith(".json"):
                rows.append({"task_id": fname[:-5], "state": state})
    if args.json:
        print(json.dumps(rows, ensure_ascii=False))
    else:
        if not rows:
            print("  (no tasks)")
        for row in rows:
            print("  {:<10} {}".format(row["state"], row["task_id"]))
    return 0


def cmd_task_logs(args):
    home = leaf_home(args.home)
    path = os.path.join(home, "logs", "{}.jsonl".format(args.task_id))
    if not args.follow:
        if not os.path.exists(path):
            print("no logs for {}".format(args.task_id), file=sys.stderr)
            return 1
        with open(path, "r", encoding="utf-8") as fh:
            sys.stdout.write(fh.read())
        return 0
    return _follow_logs(path, args.timeout)


def _follow_logs(path, timeout):
    """Stream a jsonl log, stopping on a terminal event or timeout."""
    deadline = time.time() + timeout
    pos = 0
    while time.time() < deadline:
        if not os.path.exists(path):
            time.sleep(0.2)
            continue
        with open(path, "r", encoding="utf-8") as fh:
            fh.seek(pos)
            chunk = fh.read()
            pos = fh.tell()
        terminal = False
        for line in chunk.splitlines():
            if not line.strip():
                continue
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
            try:
                if json.loads(line).get("event") in TERMINAL_EVENTS:
                    terminal = True
            except ValueError:
                pass
        if terminal:
            return 0
        time.sleep(0.25)
    return 0


def cmd_task_result(args):
    home = leaf_home(args.home)
    path = os.path.join(home, "results", args.task_id, "result.json")
    if not os.path.exists(path):
        print("no result for {}".format(args.task_id), file=sys.stderr)
        return 1
    with open(path, "r", encoding="utf-8") as fh:
        if args.json:
            sys.stdout.write(fh.read())
        else:
            doc = json.load(fh)
            for key in ("task_id", "kind", "status", "exit_code", "finished_at"):
                print("  {:<12} {}".format(key, doc.get(key)))
    return 0


def cmd_task_cancel(args):
    home = leaf_home(args.home)
    task_id = args.task_id
    state, path = _find_task(home, task_id)
    if path is None:
        print("task not found: {}".format(task_id), file=sys.stderr)
        return 1
    if state == "running":
        open(_cancel_flag(home, task_id), "w").close()
        print("cancel requested for running task {}".format(task_id))
        return 0
    if state in ("inbox", "queued"):
        _move_task(home, task_id, state, "failed")
        TaskLog(home, task_id).event("cancelled", exit_code=130)
        print("cancelled queued task {}".format(task_id))
        return 0
    print("task already terminal ({}): {}".format(state, task_id))
    return 0


# ---------------------------------------------------------------------------
# Distributor helpers (JSON authoring + registry)
# ---------------------------------------------------------------------------
def cmd_new_task_id(args):
    suffix = ""
    if args.suffix:
        suffix = "_" + args.suffix
    print("task_{}{}".format(datetime.now().strftime("%Y%m%d_%H%M%S"), suffix))
    return 0


def cmd_stamp_task(args):
    with open(args.src, "r", encoding="utf-8") as fh:
        task = json.load(fh)
    task["task_id"] = args.task_id
    task.setdefault("kind", "echo")
    task.setdefault("priority", 5)
    task.setdefault("payload", {})
    os.makedirs(os.path.dirname(os.path.abspath(args.dest)), exist_ok=True)
    with open(args.dest, "w", encoding="utf-8") as fh:
        json.dump(task, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(args.task_id)
    return 0


def _registry_path(args):
    return os.path.join(leaf_home(args.home), "nodes.json")


def _load_registry(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def cmd_registry_add(args):
    path = _registry_path(args)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    reg = _load_registry(path)
    reg[args.name] = {
        "target": args.target,
        "path": args.path,
        "transport": args.transport,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("registered node '{}' ({})".format(args.name, args.transport))
    return 0


def cmd_registry_list(args):
    reg = _load_registry(_registry_path(args))
    if args.json:
        print(json.dumps(reg, ensure_ascii=False))
        return 0
    if not reg:
        print("  (no nodes registered)")
    for name, info in reg.items():
        print("  {:<12} {:<22} {}".format(
            name, info.get("target", "?"), info.get("transport", "?")))
    return 0


def cmd_registry_get(args):
    reg = _load_registry(_registry_path(args))
    info = reg.get(args.name)
    if info is None:
        print("unknown node: {}".format(args.name), file=sys.stderr)
        return 1
    if args.field:
        value = info.get(args.field, "")
        print(value if value is not None else "")
    else:
        print(json.dumps(info, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(prog="leaf_node.py",
                                     description="LeafOS node engine.")
    parser.add_argument("--home", help="override node workspace (default $LEAF_HOME or ~/.leaf)")
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    p = sub.add_parser("init")
    p.add_argument("--node-id")
    p.add_argument("--role", default="worker")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("status")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("hardware")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_hardware)

    p = sub.add_parser("task-start")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_task_start)

    p = sub.add_parser("task-list")
    p.add_argument("--state", choices=STATE_DIRS)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_task_list)

    p = sub.add_parser("task-logs")
    p.add_argument("task_id")
    p.add_argument("--follow", action="store_true")
    p.add_argument("--timeout", type=float, default=120.0)
    p.set_defaults(func=cmd_task_logs)

    p = sub.add_parser("task-result")
    p.add_argument("task_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_task_result)

    p = sub.add_parser("task-cancel")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_task_cancel)

    p = sub.add_parser("new-task-id")
    p.add_argument("--suffix")
    p.set_defaults(func=cmd_new_task_id)

    p = sub.add_parser("stamp-task")
    p.add_argument("src")
    p.add_argument("dest")
    p.add_argument("--task-id", required=True)
    p.set_defaults(func=cmd_stamp_task)

    p = sub.add_parser("registry-add")
    p.add_argument("name")
    p.add_argument("target")
    p.add_argument("--path", default="~/.leaf")
    p.add_argument("--transport", default="ssh", choices=["ssh", "local"])
    p.set_defaults(func=cmd_registry_add)

    p = sub.add_parser("registry-list")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_registry_list)

    p = sub.add_parser("registry-get")
    p.add_argument("name")
    p.add_argument("--field")
    p.set_defaults(func=cmd_registry_get)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
