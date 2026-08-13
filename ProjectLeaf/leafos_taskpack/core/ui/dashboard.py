#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LeafOS dashboard -- core/ui/dashboard.py

The canonical read-only status surface for the full Leaf system.

Layout (80+ columns):
┌──────────────────────────────────────────────────────────────────────────────┐
│  LeafOS  vX.X.X      NODE: hostname          ROLE: worker   STATE: ready     │
├───────────────────────┬──────────────────────────────────────────────────────┤
│  TASK QUEUE           │  CLUSTER REGISTRY                                    │
│  inbox      0         │  name          target              transport  state   │
│  queued     0         │  gpu1          sm@192.168.1.41     ssh        ready   │
│  running    0         │  local1        /tmp/w              local      ready   │
│  done      12         │                                                      │
│  failed     0         ├──────────────────────────────────────────────────────│
│                       │  RECENT EVENTS                                       │
├───────────────────────┤  14:01:00 task_001  queued                          │
│  HARDWARE             │  14:01:02 task_001  started  runner=echo             │
│  cpu        32 cores  │  14:01:04 task_001  stdout   hello from node         │
│  ram        47.8 GB   │  14:01:05 task_001  done     exit_code=0             │
│  gpus       0         ├──────────────────────────────────────────────────────│
│                       │  ARP TABLE (LAN)                                     │
├───────────────────────┤  192.168.1.1  192.168.1.41  192.168.1.42            │
│  paths                │                                                      │
│  home  ~/.leaf        └──────────────────────────────────────────────────────┘
└───────────────────────┘

Data sources: files only (no subprocess for status reads).
ARP read: /proc/net/arp or `arp -n` (one subprocess, <50ms).
Hardware: live probe_hardware() on first render, cached thereafter.

Usage:
    python3 dashboard.py [--home PATH] [--watch N] [--json] [--no-color]
    leaf dashboard [--watch 2] [--json] [--no-color]
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# UTF-8 safety
# ---------------------------------------------------------------------------
for _s in ("stdout", "stderr"):
    _st = getattr(sys, _s, None)
    _rc = getattr(_st, "reconfigure", None)
    if _rc:
        try:
            _rc(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.join(_HERE, "..", "node", "leaf_node.py")
_DISCOVER = os.path.join(_HERE, "..", "net", "discover.py")
_WEB = os.path.join(_HERE, "..", "web")
if _WEB not in sys.path:
    sys.path.insert(0, _WEB)
try:
    from state import build_state as _build_web_state
except Exception:
    _build_web_state = None

def _read_version():
    """Read version from the repo VERSION file; fallback to 0.5.0."""
    for candidate in (
        os.path.join(_HERE, "..", "..", "VERSION"),        # core/ui -> root
        os.path.join(_HERE, "..", "..", "..", "VERSION"),  # deeper nesting
        os.path.join(os.path.dirname(sys.argv[0]), "..", "VERSION"),
    ):
        try:
            path = os.path.normpath(candidate)
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as handle:
                    v = handle.read().strip()
                if v:
                    return v
        except OSError:
            pass
    return "0.5.0"

VERSION = _read_version()
STATE_DIRS = ["inbox", "queued", "running", "done", "failed"]

# ---------------------------------------------------------------------------
# Boot splash — frame-by-frame ASCII leaf wipe
# ---------------------------------------------------------------------------
_LEAF_FRAMES = [
    # each frame is the cumulative build-up of the logo
    [
        "  ",
    ],
    [
        "  ╻",
    ],
    [
        "  ╻",
        " ╱ ",
    ],
    [
        "  ╻",
        " ╱◈╲",
        "╱   ╲",
    ],
    [
        "    ╻",
        "   ╱◈╲",
        "  ╱ ◈ ╲",
        " ╱_____╲",
    ],
    [
        "    ╻",
        "   ╱◈╲",
        "  ╱ ◈ ╲",
        " ╱_____╲",
        "  LEAF  ",
    ],
    [
        "     ╻",
        "    ╱◈╲",
        "   ╱ ◈ ╲",
        "  ╱_____╲",
        "   LeafOS ",
        "  v{ver}  ",
    ],
]

_SPINNER_FRAMES = ["⠋", "⠙", "⠸", "⠴", "⠦", "⠇"]
_spinner_idx = [0]   # mutable cell so watch_loop can advance it


def _next_spinner():
    f = _SPINNER_FRAMES[_spinner_idx[0] % len(_SPINNER_FRAMES)]
    _spinner_idx[0] += 1
    return f


def _local_ip():
    """Best-effort local LAN IP (not loopback)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return socket.gethostbyname(socket.gethostname())


def _node_uptime(home):
    """Seconds since node.json was created (proxy for node uptime)."""
    p = os.path.join(home, "node.json")
    try:
        age = time.time() - os.path.getmtime(p)
        h, rem = divmod(int(age), 3600)
        m, s  = divmod(rem, 60)
        return "{:02d}:{:02d}:{:02d}".format(h, m, s)
    except OSError:
        return "--:--:--"


_LOCK_PATH = [None]   # set in main(); used by HOST panel


def _write_lock(home):
    """Write ~/.leaf/leaf.lock with PID; return path."""
    path = os.path.join(home, "leaf.lock")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("pid={}\nstarted={}\n".format(
                os.getpid(),
                datetime.now().astimezone().isoformat(timespec="seconds"),
            ))
    except OSError:
        pass
    return path


def _remove_lock(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def boot_splash(no_color=False):
    """Animate ASCII leaf + version wipe, then clear for dashboard."""
    if not sys.stdout.isatty():
        return
    cyan  = "\033[1;36m" if not no_color else ""
    green = "\033[1;32m" if not no_color else ""
    dim   = "\033[2m"    if not no_color else ""
    rst   = "\033[0m"    if not no_color else ""
    hide  = "\033[?25l"  if not no_color else ""
    show  = "\033[?25h"  if not no_color else ""
    sys.stdout.write(hide)
    sys.stdout.flush()
    try:
        for fi, frame in enumerate(_LEAF_FRAMES):
            sys.stdout.write("\033[2J\033[H")
            print()
            for line in frame:
                rendered = line.replace("{ver}", VERSION)
                if "LeafOS" in rendered:
                    rendered = "  " + green + rendered.strip() + rst
                elif "{ver}" in line or "v" in rendered:
                    rendered = "  " + dim + rendered.strip() + rst
                else:
                    rendered = "  " + cyan + rendered + rst
                print(rendered)
            sys.stdout.flush()
            time.sleep(0.10 if fi < len(_LEAF_FRAMES) - 1 else 0.35)
        # final pause so user sees it
        time.sleep(0.25)
    finally:
        sys.stdout.write(show)
        sys.stdout.flush()

# ---------------------------------------------------------------------------
# ANSI colour palette (mirrors brand.sh exactly)
# ---------------------------------------------------------------------------
def _init_colors(no_color=False):
    if no_color or not sys.stdout.isatty():
        return {k: "" for k in (
            "reset", "bold", "dim",
            "green", "cyan", "yellow", "red", "magenta", "blue",
            "green_b", "cyan_b", "yellow_b", "red_b",
        )}
    return {
        "reset":    "\033[0m",
        "bold":     "\033[1m",
        "dim":      "\033[2m",
        "green":    "\033[32m",
        "cyan":     "\033[36m",
        "yellow":   "\033[33m",
        "red":      "\033[31m",
        "magenta":  "\033[35m",
        "blue":     "\033[34m",
        "green_b":  "\033[1;32m",
        "cyan_b":   "\033[1;36m",
        "yellow_b": "\033[1;33m",
        "red_b":    "\033[1;31m",
    }

C = {}  # populated in main()

# ---------------------------------------------------------------------------
# Data readers — all from files, zero subprocesses except ARP
# ---------------------------------------------------------------------------
def leaf_home(override=None):
    if override:
        return os.path.abspath(os.path.expanduser(override))
    ev = os.environ.get("LEAF_HOME")
    if ev:
        return os.path.abspath(os.path.expanduser(ev))
    return os.path.abspath(os.path.expanduser("~/.leaf"))


def _count_dir(home, state):
    d = os.path.join(home, state)
    if not os.path.isdir(d):
        return 0
    return len([f for f in os.listdir(d) if f.endswith(".json")])


def read_queue(home):
    return {s: _count_dir(home, s) for s in STATE_DIRS}


def read_node(home):
    path = os.path.join(home, "node.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            return {}


def read_registry(home):
    path = os.path.join(home, "nodes.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            return {}


def read_recent_events(home, max_events=12):
    """Read the N most-recent JSONL events across all log files."""
    logs_dir = os.path.join(home, "logs")
    if not os.path.isdir(logs_dir):
        return []
    log_files = sorted(
        [os.path.join(logs_dir, f) for f in os.listdir(logs_dir)
         if f.endswith(".jsonl")],
        key=lambda p: os.path.getmtime(p),
        reverse=True,
    )
    events = []
    for lf in log_files[:6]:  # at most 6 log files
        try:
            with open(lf, encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
                if len(events) >= max_events:
                    break
        except OSError:
            pass
        if len(events) >= max_events:
            break
    return events[:max_events]


def _arp_hosts():
    """Read LAN ARP table. Returns list of IPs (Linux / macOS / Windows)."""
    def _is_lan_unicast(ip):
        """Keep only routable unicast LAN IPs; drop broadcast/multicast."""
        try:
            import socket as _s
            packed = _s.inet_aton(ip)
            b = list(packed)
            # multicast: 224-239.x.x.x
            if 224 <= b[0] <= 239:
                return False
            # broadcast
            if b[3] == 255:
                return False
            # loopback
            if b[0] == 127:
                return False
            return True
        except Exception:
            return False
    # Linux: /proc/net/arp
    proc_arp = "/proc/net/arp"
    if os.path.isfile(proc_arp):
        hosts = []
        with open(proc_arp, encoding="ascii", errors="replace") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 4 and parts[0] != "IP" and parts[2] != "0x0":
                    if _is_lan_unicast(parts[0]):
                        hosts.append(parts[0])
        return hosts
    # macOS / BSD: arp -n
    try:
        out = subprocess.check_output(
            ["arp", "-n"], stderr=subprocess.DEVNULL,
            universal_newlines=True, timeout=3,
        )
        hosts = []
        for line in out.splitlines():
            parts = line.split()
            if parts and "." in parts[0] and parts[0] != "Address":
                if len(parts) >= 3 and parts[2] not in ("(incomplete)", "incomplete"):
                    if _is_lan_unicast(parts[0]):
                        hosts.append(parts[0])
        if hosts:
            return hosts
    except Exception:
        pass
    # Windows: arp -a
    try:
        out = subprocess.check_output(
            ["arp", "-a"], stderr=subprocess.DEVNULL,
            universal_newlines=True, timeout=3,
        )
        hosts = []
        import socket as _sock
        for line in out.splitlines():
            parts = line.split()
            if parts and "." in parts[0]:
                try:
                    _sock.inet_aton(parts[0])
                    if len(parts) >= 3 and parts[2].lower() in ("dynamic", "static"):
                        if _is_lan_unicast(parts[0]):
                            hosts.append(parts[0])
                except _sock.error:
                    pass
        return hosts
    except Exception:
        return []


def read_hardware_cached(home, _cache={}):
    """Hardware probe, cached for the session to avoid repeated sysconf calls."""
    if "data" not in _cache:
        # try reading from a cached result.json written by a hardware task
        results_dir = os.path.join(home, "results")
        hw_result = None
        if os.path.isdir(results_dir):
            for tid in sorted(os.listdir(results_dir), reverse=True):
                rpath = os.path.join(results_dir, tid, "result.json")
                if os.path.exists(rpath):
                    try:
                        with open(rpath, encoding="utf-8") as fh:
                            d = json.load(fh)
                        if "hardware" in d.get("output", {}):
                            hw_result = d["output"]["hardware"]
                            break
                    except Exception:
                        pass
        if hw_result:
            _cache["data"] = hw_result
        else:
            # live probe (stdlib only, fast)
            import platform
            import struct
            import ctypes as ct
            cpu = os.cpu_count()
            ram = None
            try:
                if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names:
                    ram = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
            except (ValueError, OSError):
                pass
            if ram is None and platform.system() == "Windows":
                try:
                    class _MS(ct.Structure):
                        _fields_ = [
                            ("dwLength", ct.c_ulong),
                            ("dwMemoryLoad", ct.c_ulong),
                            ("ullTotalPhys", ct.c_ulonglong),
                        ] + [("_pad{}".format(i), ct.c_ulonglong) for i in range(6)]
                    ms = _MS()
                    ms.dwLength = ct.sizeof(_MS)
                    if ct.windll.kernel32.GlobalMemoryStatusEx(ct.byref(ms)):
                        ram = int(ms.ullTotalPhys)
                except Exception:
                    pass
            gpus = []
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=name,memory.total",
                     "--format=csv,noheader"],
                    stderr=subprocess.DEVNULL, universal_newlines=True, timeout=5,
                )
                for line in out.strip().splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if parts and parts[0]:
                        gpus.append({"name": parts[0],
                                     "memory_total": parts[1] if len(parts) > 1 else None})
            except Exception:
                pass
            _cache["data"] = {
                "cpu_count": cpu,
                "ram_gb": round(ram / (1024 ** 3), 1) if ram else None,
                "gpus": gpus,
                "hostname": socket.gethostname(),
            }
    return _cache["data"]


def read_web_state():
    """Read the slowly-growing web/runtime state document with safe fallback."""
    if _build_web_state is None:
        return {
            "leafos_object": "web_state",
            "available": False,
            "coding_backend_choice": {
                "language": "python",
                "model_key": "gemma4-coder",
                "tier": "builder",
                "backend": "python",
            },
            "remote_metadata": {"source": "unavailable"},
        }
    try:
        return _build_web_state(refresh_metadata=False, write_cache=False)
    except Exception as exc:
        return {
            "leafos_object": "web_state",
            "available": False,
            "error": str(exc),
            "coding_backend_choice": {
                "language": "python",
                "model_key": "gemma4-coder",
                "tier": "builder",
                "backend": "python",
            },
            "remote_metadata": {"source": "steady-state-error-fallback"},
        }


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def _ts_short(iso_str):
    """HH:MM:SS from an ISO timestamp string."""
    try:
        return iso_str[11:19]
    except (TypeError, IndexError):
        return "??:??:??"


def _state_color(state):
    m = {
        "ready":   C["green_b"],
        "running": C["cyan_b"],
        "queued":  C["yellow"],
        "failed":  C["red_b"],
        "done":    C["green"],
        "unknown": C["dim"],
    }
    return m.get(state, C["dim"])


def _event_color(event):
    m = {
        "queued":    C["yellow"],
        "started":   C["cyan"],
        "stdout":    C["reset"],
        "stderr":    C["red"],
        "done":      C["green_b"],
        "failed":    C["red_b"],
        "cancelled": C["yellow_b"],
    }
    return m.get(event, C["dim"])


def build_attention_summary(queue):
    """Return the highest-priority local condition and a safe next action."""
    failed = queue.get("failed", 0)
    running = queue.get("running", 0)
    queued = queue.get("queued", 0) + queue.get("inbox", 0)

    if failed:
        return {
            "level": "warning",
            "attention": "{} failed task(s) need review".format(failed),
            "next_action": "leafctl task list",
        }
    if running:
        return {
            "level": "active",
            "attention": "{} task(s) currently running".format(running),
            "next_action": "leafctl task logs",
        }
    if queued:
        return {
            "level": "queued",
            "attention": "{} task(s) waiting to run".format(queued),
            "next_action": "leafctl task list",
        }
    return {
        "level": "ready",
        "attention": "No pending tasks",
        "next_action": "leafctl agent-task \"describe the next goal\"",
    }


def _terminal_width():
    override = os.environ.get("LEAF_DASH_WIDTH")
    if override and override.isdigit():
        return int(override)
    try:
        w = shutil.get_terminal_size((80, 24)).columns
        return min(w, 180)  # cap: piped/background contexts return full buffer
    except Exception:
        return 80


def _hline(width, char="─"):
    return char * width


def _box_top(width):
    return "┌" + _hline(width - 2) + "┐"

def _box_bot(width):
    return "└" + _hline(width - 2) + "┘"

def _box_div(width):
    return "├" + _hline(width - 2) + "┤"

def _col_div(left_w, total_w):
    right_w = total_w - left_w - 3
    return "├" + _hline(left_w) + "┬" + _hline(right_w) + "┤"

def _row(left, right, left_w, total_w):
    """Format one two-column row."""
    right_w = total_w - left_w - 3
    left_str = " {} ".format(_pad_to(left, left_w - 2))
    right_str = " {} ".format(_pad_to(right, right_w - 2))
    return "│" + left_str + "│" + right_str + "│"

def _row_left(text, left_w):
    """One-column left row."""
    inner = " {} ".format(_pad_to(text, left_w - 2))
    return "│" + inner

def _row_right(text, left_w, total_w):
    """One-column right row, left side blank."""
    right_w = total_w - left_w - 3
    right_str = " {} ".format(_pad_to(text, right_w - 2))
    return "│" + " " * left_w + "│" + right_str + "│"

def _row_full(text, total_w):
    inner_w = total_w - 2
    return "│ {} │".format(_pad_to(text, inner_w - 2))


# ---------------------------------------------------------------------------
# Panel builders — return lists of raw strings (no newlines)
# ---------------------------------------------------------------------------
def _strip_ansi(s):
    """Approximate printable width by removing ANSI escape sequences."""
    import re
    return re.sub(r'\033\[[0-9;]*m', '', s)

def _clip_visible(s, width):
    """Clip visible text to width without splitting ANSI escape sequences."""
    if width <= 0:
        return ""
    import re
    out = []
    visible = 0
    pos = 0
    saw_ansi = False
    for match in re.finditer(r'\033\[[0-9;]*m', s):
        if visible < width:
            segment = s[pos:match.start()]
            take = min(width - visible, len(segment))
            out.append(segment[:take])
            visible += take
        out.append(match.group(0))
        saw_ansi = True
        pos = match.end()
    if visible < width:
        segment = s[pos:]
        take = min(width - visible, len(segment))
        out.append(segment[:take])
    clipped = "".join(out)
    if saw_ansi and C.get("reset"):
        clipped += C["reset"]
    return clipped

def _pad_to(s, width):
    """Clip and pad string s (which may contain ANSI codes) to visible width."""
    s = _clip_visible(s, width)
    visible = len(_strip_ansi(s))
    padding = max(0, width - visible)
    return s + " " * padding


def render_dashboard(home, no_color=False):
    """Render the full dashboard and return as a list of lines."""
    global C
    if not C:
        C = _init_colors(no_color=no_color)
    width = max(80, _terminal_width())
    left_w = 26      # left column inner width (including │ padding)
    lines = []

    # --- data reads ---
    node   = read_node(home)
    queue  = read_queue(home)
    attention = build_attention_summary(queue)
    reg    = read_registry(home)
    events = read_recent_events(home, max_events=10)
    arp    = _arp_hosts()
    hw     = read_hardware_cached(home)
    web_state = read_web_state()
    coding_choice = web_state.get("coding_backend_choice", {})
    now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    node_id   = node.get("node_id", "uninitialized")
    role      = node.get("role", "—")
    n_running = queue.get("running", 0)
    state     = "running" if n_running > 0 else ("ready" if node else "uninitialized")
    state_col = _state_color(state)

    # === HEADER ===
    header_left  = "{}{}LeafOS {}v{}{}  NODE: {}{}{}".format(
        C["bold"], C["cyan"], C["reset"],
        C["dim"], VERSION, C["reset"],
        C["cyan_b"], node_id,
    )
    header_right = "{}ROLE:{} {}  {}STATE:{} {}{}{}".format(
        C["dim"], C["reset"], role,
        C["dim"], C["reset"],
        state_col, state, C["reset"],
    )
    header_right += "   " + C["dim"] + now + C["reset"]

    lines.append(_box_top(width))
    header_inner = "  " + header_left + "  " + header_right
    lines.append("│ " + _pad_to(header_inner, width - 4) + " │")

    # === TWO-COLUMN SPLIT ===
    lines.append(_col_div(left_w, width))

    # --- TASK QUEUE (left) + CLUSTER REGISTRY (right) ---
    right_w = width - left_w - 3
    # column headers
    reg_hdr = "{}CLUSTER REGISTRY{}".format(C["bold"], C["reset"])
    lines.append(_row(
        "{}TASK QUEUE{}".format(C["bold"], C["reset"]),
        reg_hdr,
        left_w, width,
    ))

    # registry table header
    reg_col_hdr = "  {:<16} {:<22} {:<8} {}".format(
        C["dim"] + "name" + C["reset"],
        C["dim"] + "target" + C["reset"],
        C["dim"] + "transport" + C["reset"],
        C["dim"] + "state" + C["reset"],
    )

    # state colors for queue
    q_colors = {
        "inbox":   C["yellow"],
        "queued":  C["yellow_b"],
        "running": C["cyan_b"],
        "done":    C["green"],
        "failed":  C["red_b"],
    }

    reg_items = list(reg.items())
    max_rows = max(len(STATE_DIRS) + 2, len(reg_items) + 2)

    # first right row: registry header
    right_rows = [reg_col_hdr]

    # registry rows (name, target, transport, state placeholder)
    for name, cfg in reg_items:
        transport = cfg.get("transport", "ssh")
        target    = cfg.get("target", "?")
        rstate    = "?"  # would require SSH to probe; shown as ? for speed
        row_str = "  {}{:<16}{} {:<22} {}{:<8}{}  {}{}{}".format(
            C["cyan"], name[:16], C["reset"],
            target[:22],
            C["dim"], transport[:8], C["reset"],
            C["dim"], rstate, C["reset"],
        )
        right_rows.append(row_str)

    # pad right column rows to max_rows
    while len(right_rows) < max_rows:
        right_rows.append("")

    # queue rows
    for i, s in enumerate(STATE_DIRS):
        count = queue.get(s, 0)
        col   = q_colors.get(s, C["reset"])
        count_col = col if count > 0 else C["dim"]
        q_str = "  {}{:<10}{} {}{:>4}{}".format(
            C["dim"], s, C["reset"],
            count_col, count, C["reset"],
        )
        r_str = right_rows[i] if i < len(right_rows) else ""
        lines.append(_row(q_str, r_str, left_w, width))

    # remaining right rows (registry overflows queue count)
    for i in range(len(STATE_DIRS), max_rows):
        r_str = right_rows[i] if i < len(right_rows) else ""
        lines.append(_row("", r_str, left_w, width))

    # --- HARDWARE (left) + RECENT EVENTS (right) ---
    right_hdr = _hline(right_w - 1)
    # divider between registry and events
    left_div  = "│" + _hline(left_w) + "├" + _hline(right_w) + "┤"
    lines.append(left_div)
    lines.append(_row(
        "{}HARDWARE{}".format(C["bold"], C["reset"]),
        "{}RECENT EVENTS{}".format(C["bold"], C["reset"]),
        left_w, width,
    ))

    cpu_str = "  {}{:<8}{} {} cores".format(
        C["dim"], "cpu", C["reset"], hw.get("cpu_count", "?"),
    )
    ram_gb  = hw.get("ram_gb")
    ram_str = "  {}{:<8}{} {} GB".format(
        C["dim"], "ram", C["reset"],
        "{:.1f}".format(ram_gb) if ram_gb else "?",
    )
    gpu_count = len(hw.get("gpus", []))
    gpu_str = "  {}{:<8}{} {}".format(
        C["dim"], "gpus", C["reset"],
        gpu_count if gpu_count else "—",
    )
    host_str = "  {}{:<8}{} {}".format(
        C["dim"], "host", C["reset"], hw.get("hostname", socket.gethostname()),
    )

    hw_rows = [cpu_str, ram_str, gpu_str, host_str]

    # event rows
    ev_rows = []
    for ev in events[:10]:
        ts_s = _ts_short(ev.get("time", ""))
        etype = ev.get("event", "?")
        tid   = ev.get("task_id", "")[-12:]  # last 12 chars of task_id
        ecol  = _event_color(etype)
        extra = ""
        if etype == "stdout":
            extra = ev.get("text", "")[:28]
        elif etype == "started":
            extra = "runner=" + ev.get("runner", "")
        elif etype in ("done", "failed"):
            extra = "exit={}".format(ev.get("exit_code", "?"))
        ev_str = "  {}{}{} {}{:<12}{} {}{:<10}{} {}{}{}".format(
            C["dim"], ts_s, C["reset"],
            C["cyan"], tid, C["reset"],
            ecol, etype[:10], C["reset"],
            C["dim"], extra[:28], C["reset"],
        )
        ev_rows.append(ev_str)

    hw_ev_rows = max(len(hw_rows), len(ev_rows), 4)
    for i in range(hw_ev_rows):
        lft = hw_rows[i] if i < len(hw_rows) else ""
        rgt = ev_rows[i] if i < len(ev_rows) else ""
        lines.append(_row(lft, rgt, left_w, width))

    lines.append(_box_div(width))
    attention_color = {
        "warning": C["red_b"],
        "active": C["cyan_b"],
        "queued": C["yellow_b"],
        "ready": C["green_b"],
    }.get(attention["level"], C["dim"])
    lines.append(_row_full(
        "{}ATTENTION:{} {}".format(attention_color, C["reset"], attention["attention"]),
        width,
    ))
    lines.append(_row_full(
        "{}NEXT:{} {}".format(C["bold"], C["reset"], attention["next_action"]),
        width,
    ))

    # --- PATHS (left) + ARP TABLE (right) ---
    left_div2 = "│" + _hline(left_w) + "├" + _hline(right_w) + "┤"
    lines.append(left_div2)
    lines.append(_row(
        "{}PATHS{}".format(C["bold"], C["reset"]),
        "{}ARP TABLE  (LAN hosts){}".format(C["bold"], C["reset"]),
        left_w, width,
    ))

    home_short = home.replace(os.path.expanduser("~"), "~")
    local_ip  = _local_ip()
    uptime    = _node_uptime(home)
    lock_path = _LOCK_PATH[0] or os.path.join(home, "leaf.lock")
    lock_short = lock_path.replace(os.path.expanduser("~"), "~")
    path_rows = [
        "  {}active   {}{}◉ LEAF_NODE ACTIVE{}".format(C["dim"], C["reset"], C["green_b"], C["reset"]),
        "  {}coding  {} {} / {} / {}".format(
            C["dim"], C["reset"],
            coding_choice.get("language", "python"),
            coding_choice.get("model_key", "gemma4-coder"),
            coding_choice.get("tier", "builder"),
        ),
        "  {}{:<8}{} {}".format(C["dim"], "ip",     C["reset"], local_ip),
        "  {}{:<8}{} {}".format(C["dim"], "pid",    C["reset"], str(os.getpid())),
        "  {}{:<8}{} {}".format(C["dim"], "uptime", C["reset"], uptime),
        "  {}{:<8}{} {}".format(C["dim"], "home",   C["reset"], home_short),
        "  {}{:<8}{} {}".format(C["dim"], "lock",   C["reset"], lock_short),
    ]

    # ARP in rows of 3
    arp_sorted = sorted(arp)
    arp_rows = []
    chunk = []
    for ip in arp_sorted:
        chunk.append(ip)
        if len(chunk) == 3:
            arp_rows.append("  " + "  ".join("{:<16}".format(x) for x in chunk))
            chunk = []
    if chunk:
        arp_rows.append("  " + "  ".join("{:<16}".format(x) for x in chunk))

    if not arp_rows:
        arp_rows = ["  {}(no ARP entries){}".format(C["dim"], C["reset"])]

    path_arp_rows = max(len(path_rows), len(arp_rows), 2)
    for i in range(path_arp_rows):
        lft = path_rows[i] if i < len(path_rows) else ""
        rgt = arp_rows[i] if i < len(arp_rows) else ""
        lines.append(_row(lft, rgt, left_w, width))

    # === FOOTER ===
    # join left and right bottom edges
    left_bot  = "└" + _hline(left_w) + "┴" + _hline(right_w) + "┘"
    lines.append(left_bot)

    return lines


# ---------------------------------------------------------------------------
# JSON output mode
# ---------------------------------------------------------------------------
def render_json(home):
    node  = read_node(home)
    queue = read_queue(home)
    attention = build_attention_summary(queue)
    reg   = read_registry(home)
    events = read_recent_events(home, max_events=20)
    hw    = read_hardware_cached(home)
    arp   = _arp_hosts()
    web_state = read_web_state()
    out = {
        "leafos_object": "dashboard",
        "timestamp":     datetime.now().astimezone().isoformat(timespec="seconds"),
        "node":          node,
        "queue":         queue,
        "attention":     attention,
        "registry":      reg,
        "hardware":      hw,
        "arp_hosts":     arp,
        "recent_events": events,
        "web_state":     web_state,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Watch loop
# ---------------------------------------------------------------------------
def _clear():
    # ANSI clear screen + cursor home
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def watch_loop(home, interval, no_color):
    global C
    cyan = "\033[1;36m" if not no_color else ""
    dim  = "\033[2m"    if not no_color else ""
    rst  = "\033[0m"    if not no_color else ""
    while True:
        _clear()
        spin = _next_spinner()
        lines = render_dashboard(home, no_color=no_color)
        # inject spinner into first line (the header row)
        if lines:
            status_line = (
                "{}{}{}  {} LIVE  {}refresh {}{}s{}".format(
                    cyan, spin, rst,
                    "◉",
                    dim, int(interval), rst, "",
                )
            )
            lines[0] = lines[0]  # header box-top unchanged
            # insert status bar between box-top and header content
            lines.insert(1, status_line)
        print("\n".join(lines))
        sys.stdout.flush()
        time.sleep(interval)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="dashboard.py",
        description="LeafOS live status dashboard",
    )
    p.add_argument("--home", default=None,
                   help="LEAF_HOME path (default: $LEAF_HOME or ~/.leaf)")
    p.add_argument("--watch", type=float, metavar="SECONDS", default=None,
                   help="refresh interval for live mode (e.g. --watch 2)")
    p.add_argument("--json", action="store_true",
                   help="emit a JSON snapshot instead of the ANSI dashboard")
    p.add_argument("--no-color", action="store_true",
                   help="disable ANSI colour output")
    p.add_argument("--width", type=int, default=0,
                   help="override terminal width (default: auto-detect, max 180)")
    return p


def main():
    global C
    parser = build_parser()
    args = parser.parse_args()

    home = leaf_home(args.home)
    C = _init_colors(no_color=args.no_color)

    if args.width:
        os.environ["LEAF_DASH_WIDTH"] = str(args.width)

    if args.json:
        render_json(home)
        return 0

    # write lock
    lock = _write_lock(home)
    _LOCK_PATH[0] = lock
    import atexit
    atexit.register(_remove_lock, lock)

    # animated boot splash for interactive sessions
    if sys.stdout.isatty() and not args.no_color:
        boot_splash(no_color=args.no_color)

    if args.watch is not None:
        try:
            watch_loop(home, args.watch, args.no_color)
        except KeyboardInterrupt:
            print()
        return 0

    # single render
    lines = render_dashboard(home, no_color=args.no_color)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
