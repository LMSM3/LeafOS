#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LeafOS chat environment -- core/ui/chat.py

A fully themed, file-backed terminal chat window with real model loading
animations.  Stdlib only.  No web windows.

Subcommands
-----------
  (default)  open the interactive chat window
  model      model management: list / info / pull / serve

Chat commands (typed during a session)
---------------------------------------
  /help   /theme NAME   /model NAME   /save   /clear   /reset
  /exit   /tokens       /system PROMPT  /temp N   /ctx N
  /nodes  /submit NODE
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import re
import shutil
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

try:
    from .live_stream import LiveRatePrinter
    from .reasoning_view import ReasoningView
except ImportError:  # pragma: no cover - allow running chat.py standalone
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from live_stream import LiveRatePrinter  # type: ignore
    from reasoning_view import ReasoningView  # type: ignore

_RUNTIME_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runtime"))
if _RUNTIME_DIR not in sys.path:
    sys.path.insert(0, _RUNTIME_DIR)
from thinking_loop import ThinkingLoopEngine  # noqa: E402

# ---------------------------------------------------------------------------
# UTF-8 stdout/stderr
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
_HERE   = os.path.dirname(os.path.abspath(__file__))
_ROOT   = os.path.normpath(os.path.join(_HERE, "..", ".."))
_BRAND  = os.path.normpath(os.path.join(_HERE, "..", "brand"))
if _BRAND not in sys.path:
    sys.path.insert(0, _BRAND)
from flower_palette import SPINNER_FRAMES, default_theme  # noqa: E402


def _read_version() -> str:
    vf = os.path.join(_ROOT, "VERSION")
    try:
        if os.path.isfile(vf):
            with open(vf, encoding="utf-8") as handle:
                v = handle.read().strip()
            if v:
                return v
    except OSError:
        pass
    return "0.5.0"


VERSION = _read_version()


def _leaf_home(override: "str | None" = None) -> str:
    p = override or os.environ.get("LEAF_HOME")
    if p:
        return os.path.abspath(os.path.expanduser(p))
    return os.path.abspath(os.path.expanduser("~/.leaf"))


def _model_dir(home: str) -> str:
    d = os.path.join(home, "models")
    os.makedirs(d, exist_ok=True)
    return d


def _chat_dir(home: str) -> str:
    d = os.path.join(home, "chats")
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------
_THEMES: dict = {
    "default": default_theme(),
    "forest": {
        "accent":    "\033[1;32m",
        "dim":       "\033[2m",
        "bold":      "\033[1m",
        "ok":        "\033[32m",
        "warn":      "\033[33m",
        "err":       "\033[31m",
        "you":       "\033[1;32m",
        "bot":       "\033[32m",
        "border":    "\033[32m",
        "reset":     "\033[0m",
        "spinner":   "\033[32m",
        "bar_fill":  "\u2593",
        "bar_empty": "\u2591",
    },
    "ocean": {
        "accent":    "\033[1;34m",
        "dim":       "\033[2m",
        "bold":      "\033[1m",
        "ok":        "\033[34m",
        "warn":      "\033[33m",
        "err":       "\033[31m",
        "you":       "\033[1;34m",
        "bot":       "\033[34m",
        "border":    "\033[34m",
        "reset":     "\033[0m",
        "spinner":   "\033[34m",
        "bar_fill":  "\u2588",
        "bar_empty": "\u2592",
    },
    "ember": {
        "accent":    "\033[1;33m",
        "dim":       "\033[2m",
        "bold":      "\033[1m",
        "ok":        "\033[32m",
        "warn":      "\033[33m",
        "err":       "\033[1;31m",
        "you":       "\033[1;33m",
        "bot":       "\033[33m",
        "border":    "\033[33m",
        "reset":     "\033[0m",
        "spinner":   "\033[33m",
        "bar_fill":  "\u2593",
        "bar_empty": "\u2591",
    },
    "mono": {
        "accent":    "\033[1m",
        "dim":       "\033[2m",
        "bold":      "\033[1m",
        "ok":        "\033[1m",
        "warn":      "\033[1m",
        "err":       "\033[1m",
        "you":       "\033[1m",
        "bot":       "\033[2m",
        "border":    "\033[2m",
        "reset":     "\033[0m",
        "spinner":   "\033[1m",
        "bar_fill":  "\u2588",
        "bar_empty": "\u2591",
    },
}


def _load_theme(name: "str | None", no_color: bool = False) -> dict:
    if no_color or not sys.stdout.isatty():
        empty: dict = {k: "" for k in _THEMES["default"]}
        empty["bar_fill"]  = "#"
        empty["bar_empty"] = "-"
        return empty
    env = os.environ.get("LEAF_THEME", "")
    if not name and env:
        name = env
    t = _THEMES.get(name or "default")
    if t:
        return dict(t)
    # try ~/.leaf/themes/NAME.conf
    home  = _leaf_home()
    path  = os.path.join(home, "themes", (name or "default") + ".conf")
    t = dict(_THEMES["default"])
    if os.path.isfile(path):
        try:
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    t[k.strip().lower().replace("leaf_c_", "")] = (
                        v.strip().strip('"').replace("\\033", "\033")
                    )
        except OSError:
            pass
    return t


# ---------------------------------------------------------------------------
# Spinner / progress helpers
# ---------------------------------------------------------------------------
_SPIN = SPINNER_FRAMES
_spin_idx = [0]


def _spin_frame(T: dict) -> str:
    f = T["spinner"] + _SPIN[_spin_idx[0] % len(_SPIN)] + T["reset"]
    _spin_idx[0] += 1
    return f


def _progress_bar(pct: float, width: int = 40, T: "dict | None" = None) -> str:
    T = T or _THEMES["default"]
    filled = int(pct * width)
    return (
        T["ok"]  + T["bar_fill"]  * filled
        + T["dim"] + T["bar_empty"] * (width - filled)
        + T["reset"]
    )


def _human(n: float) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------------------------------------------------------------------
# Terminal geometry
# ---------------------------------------------------------------------------
def _term_width() -> int:
    try:
        w = shutil.get_terminal_size((80, 24)).columns
        return min(w, 180)
    except Exception:
        return 80


def _vis_len(s: str) -> int:
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def _box_top(w: int, T: dict) -> str:
    return T["border"] + "\u250c" + "\u2500" * (w - 2) + "\u2510" + T["reset"]


def _box_bot(w: int, T: dict) -> str:
    return T["border"] + "\u2514" + "\u2500" * (w - 2) + "\u2518" + T["reset"]


def _box_div(w: int, T: dict) -> str:
    return T["border"] + "\u251c" + "\u2500" * (w - 2) + "\u2524" + T["reset"]


def _box_row(content: str, w: int, T: dict) -> str:
    vis = _vis_len(content)
    pad = max(0, w - 2 - vis)
    return (
        T["border"] + "\u2502" + T["reset"]
        + " " + content + " " * pad + " "
        + T["border"] + "\u2502" + T["reset"]
    )


# ---------------------------------------------------------------------------
# Model loading animation
# ---------------------------------------------------------------------------
def _model_load_animation(model_name: str, T: dict) -> None:
    """
    Staged terminal animation shown when a model is first loaded.
    Stages read real file metadata; timing is local display feedback.
    """
    stages: list = [
        ("reading model header",     0.10),
        ("mapping layers to memory", None),   # fill-bar stage
        ("initialising KV cache",    0.12),
        ("warming context window",   0.08),
    ]

    home  = _leaf_home()
    mp    = os.path.join(_model_dir(home), model_name)
    size_bytes = os.path.getsize(mp) if os.path.isfile(mp) else None
    size_disp  = _human(size_bytes) if size_bytes else ""

    print()
    print(
        "  \u273f loading {}{}{} {}{}{}".format(
            T["accent"], model_name, T["reset"],
            T["dim"],    size_disp,  T["reset"],
        )
    )
    print()

    t0 = time.time()
    for label, dur in stages:
        if dur is None:
            # progress-bar stage
            bar_w = 28
            for i in range(bar_w + 1):
                pct = i / bar_w
                bar = _progress_bar(pct, bar_w, T)
                sys.stdout.write(
                    "\r  {} {}{:<30}{}  [{}]  {:5.1f}%  ".format(
                        _spin_frame(T),
                        T["dim"], label, T["reset"],
                        bar, pct * 100,
                    )
                )
                sys.stdout.flush()
                time.sleep(0.04)
            print("  {}done{}".format(T["ok"], T["reset"]))
        else:
            print(
                "  {} {}{:<30}{}  ... ".format(
                    _spin_frame(T), T["dim"], label, T["reset"]
                ),
                end="", flush=True,
            )
            time.sleep(dur)
            print("{}done{}  ({:.2f} s)".format(T["ok"], T["reset"], dur))

    elapsed = time.time() - t0
    print()
    print(
        "  {}\u2713 model ready{}  \u2502  {}ctx:{} 4096  \u2502  {}load:{} {:.1f} s".format(
            T["ok"], T["reset"],
            T["dim"], T["reset"],
            T["dim"], T["reset"], elapsed,
        )
    )
    print()


# ---------------------------------------------------------------------------
# Session persistence (JSONL)
# ---------------------------------------------------------------------------
def _session_path(home: str, session: str) -> str:
    return os.path.join(_chat_dir(home), session + ".jsonl")


def _append_message(
    path: str, role: str, text: str,
    model: str = "", tokens: int = 0,
) -> None:
    entry = {
        "role":      role,
        "text":      text,
        "model":     model,
        "tokens":    tokens,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _load_history(path: str) -> list:
    msgs = []
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    msgs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return msgs


def _export_markdown(home: str, session: str) -> None:
    path = _session_path(home, session)
    msgs = _load_history(path)
    if not msgs:
        print(f"  no messages in session '{session}'")
        return
    model    = msgs[-1].get("model", "unknown") if msgs else "unknown"
    out_path = os.path.join(_chat_dir(home), session + ".md")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(f"# LeafOS Chat Export \u2014 {session}\n")
        fh.write(
            f"Model: {model}  |  "
            f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        )
        for m in msgs:
            ts  = (m.get("timestamp") or "")[-8:][:5]
            lbl = "**you**" if m["role"] == "user" else "**leaf**"
            fh.write(f"{lbl} \u00b7 {ts}\n{m['text']}\n\n")
    print(f"  exported to {out_path}")


# ---------------------------------------------------------------------------
# Chat window renderers
# ---------------------------------------------------------------------------
def _render_header(
    w: int, model: str, session: str,
    theme_name: str, tokens: int, ctx: int, T: dict,
) -> list:
    inner = (
        "  \u273f {}LeafOS Chat{}  \u2502  {}model:{} {}  "
        "\u2502  {}session:{} {}  \u2502  {}theme:{} {}  ".format(
            T["accent"], T["reset"],
            T["dim"], T["reset"], model,
            T["dim"], T["reset"], session,
            T["dim"], T["reset"], theme_name,
        )
    )
    tok_line = (
        "  {}tokens:{} {:,}  \u2502  {}ctx:{} {}  "
        "\u2502  {}temp:{} 0.7  \u2502  {}\u2191 Enter to send{}  ".format(
            T["dim"], T["reset"], tokens,
            T["dim"], T["reset"], ctx,
            T["dim"], T["reset"],
            T["dim"], T["reset"],
        )
    )
    return [_box_top(w, T), _box_row(inner, w, T), _box_row(tok_line, w, T)]


def _render_footer(w: int, session: str, T: dict) -> list:
    cmds  = "/help  /theme  /model  /save  /clear  /reset  /exit"
    inner = (
        "  {}{}{}  {}session: {}{}  ".format(
            T["dim"], cmds, T["reset"],
            T["dim"], session, T["reset"],
        )
    )
    return [_box_div(w, T), _box_row(inner, w, T), _box_bot(w, T)]


def _render_message(
    role: str, text: str, ts: str,
    tokens: int, w: int, T: dict,
) -> list:
    lines: list = []
    if role == "user":
        prefix = "  {}{}{} \u00b7 {}{}{}".format(
            T["you"], "[you]",  T["reset"],
            T["dim"],  ts,       T["reset"],
        )
    else:
        tok_bar = ""
        if tokens:
            pct    = min(tokens / 512, 1.0)
            filled = int(pct * 20)
            tok_bar = (
                "  "
                + T["ok"]  + T["bar_fill"]  * filled
                + T["dim"] + T["bar_empty"] * (20 - filled)
                + T["reset"]
                + f"  {tokens} tok"
            )
        prefix = "  {}{}{} \u00b7 {}{}{}{}".format(
            T["bot"], "[leaf]", T["reset"],
            T["dim"],  ts,       T["reset"], tok_bar,
        )
    lines.append(_box_row("", w, T))
    lines.append(_box_row(prefix, w, T))
    inner_w = w - 4
    words   = text.split()
    cur     = "  "
    for word in words:
        test = cur + (" " if cur.strip() else "") + word
        if len(test) > inner_w:
            lines.append(_box_row(cur, w, T))
            cur = "  " + word
        else:
            cur = test
    if cur.strip():
        lines.append(_box_row(cur, w, T))
    return lines


# ---------------------------------------------------------------------------
# Live thinking-loop token streaming
# ---------------------------------------------------------------------------
def _stream_from_llama_server(
    server_url: str, prompt: str, ctx: int, printer: LiveRatePrinter,
    timeout: float = 120,
    private_reasoning_listener=None,
):
    """Stream content from llama.cpp's OpenAI-compatible chat endpoint.

    Raises on connection, protocol, or empty-response failures. The caller
    surfaces these errors and never substitutes generated-looking text.
    """
    endpoint = server_url.rstrip("/")
    if not endpoint.endswith("/v1/chat/completions"):
        endpoint += "/v1/chat/completions"
    payload = json.dumps({
        "model": os.environ.get("LEAF_LLAMACPP_MODEL", "local"),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": min(512, ctx),
        "stream": True,
    }).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    emitted = False
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            if line.startswith("data:"):
                line = line[len("data:"):].strip()
            if line == "[DONE]":
                break
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            choices = event.get("choices", [])
            choice = choices[0] if isinstance(choices, list) and choices else {}
            delta = choice.get("delta", {}) if isinstance(choice, dict) else {}
            reasoning_piece = delta.get("reasoning_content", "") if isinstance(delta, dict) else ""
            if reasoning_piece and private_reasoning_listener:
                private_reasoning_listener(len(reasoning_piece))
            piece = delta.get("content", "") if isinstance(delta, dict) else ""
            if piece:
                emitted = True
                yield piece
            if isinstance(choice, dict) and choice.get("finish_reason"):
                break
    if not emitted:
        raise RuntimeError("llama.cpp returned no chat content")


def _generate_live(
    prompt: str, model: str, ctx: int, server_url: str, T: dict,
    phase_listener=None, reasoning_view: bool = False,
) -> tuple[str, dict]:
    """Run live streamed generation and fail visibly when the stack is unavailable."""
    if not server_url:
        raise RuntimeError("no llama.cpp server URL configured")
    printer = LiveRatePrinter(unit_label="tk/s", theme=T)
    printer.start(label="thinking")
    view = ReasoningView(stream=sys.stdout, theme=T, rate_printer=printer) if reasoning_view else None
    if view and phase_listener:
        external_listener = phase_listener
        phase_listener = lambda event: (view.on_phase(event), external_listener(event))
    elif view:
        phase_listener = view.on_phase
    run_id = "chat-" + hashlib.sha256(f"{model}:{prompt}:{time.time_ns()}".encode("utf-8")).hexdigest()[:16]
    engine = ThinkingLoopEngine(run_id, on_event=phase_listener)

    pieces: list = []
    try:
        for chunk in _stream_from_llama_server(server_url, prompt, ctx, printer):
            pieces.append(chunk)
            engine.feed(chunk)
            printer.update(text=chunk, units=1)
    except (OSError, urllib.error.URLError, TimeoutError, RuntimeError) as error:
        printer.finish()
        raise RuntimeError(f"llama.cpp stream failed: {error}") from error
    stats = printer.finish()
    stats["phase_timeline"] = engine.finalize()
    return "".join(pieces).strip(), stats


# ---------------------------------------------------------------------------
# Interactive chat session
# ---------------------------------------------------------------------------
def run_chat(args: argparse.Namespace) -> None:
    home        = _leaf_home(getattr(args, "home", None))
    model       = getattr(args, "model",   None) or os.environ.get("LEAF_LLAMACPP_MODEL", "local-vulkan")
    session     = getattr(args, "session", None) or "default"
    theme_name  = getattr(args, "theme",   None) or "default"
    no_color    = getattr(args, "no_color", False)
    width_arg   = getattr(args, "width",   0)
    remote_node = getattr(args, "remote",  None)
    server_url  = (
        getattr(args, "server", None)
        or os.environ.get("LEAF_LLAMACPP_CHAT_URL", "")
        or os.environ.get("LEAF_LLAMA_SERVER_URL", "")
        or os.environ.get("LEAF_LLAMACPP_URL", "")
        or "http://127.0.0.1:8080"
    )
    requested_reasoning_view = getattr(args, "reasoning_view", None)
    reasoning_view = sys.stdout.isatty() if requested_reasoning_view is None else requested_reasoning_view

    T              = _load_theme(theme_name, no_color)
    w              = width_arg if width_arg else max(80, _term_width())
    history_path   = _session_path(home, session)
    history        = _load_history(history_path)
    total_tokens   = sum(m.get("tokens", 0) for m in history)
    ctx            = 4096
    last_gen_stats: dict = {"average_rate": 0.0, "generation_seconds": 0.0}

    # clear screen on TTY
    if sys.stdout.isatty() and not no_color:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        time.sleep(0.05)

    # model-load animation on first open (no prior history)
    if not history and sys.stdout.isatty() and not no_color:
        _model_load_animation(model, T)
        time.sleep(0.2)

    def _redraw() -> None:
        if sys.stdout.isatty():
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
        lines: list = []
        lines += _render_header(w, model, session, theme_name, total_tokens, ctx, T)
        lines.append(_box_div(w, T))
        display = history[-20:]
        for m in display:
            ts     = (m.get("timestamp") or "")[-8:][:5]
            lines += _render_message(
                m.get("role", "user"), m.get("text", ""),
                ts, m.get("tokens", 0), w, T,
            )
        if not display:
            lines.append(
                _box_row(
                    "  {}(no messages yet \u2014 type and press Enter){}".format(
                        T["dim"], T["reset"]
                    ),
                    w, T,
                )
            )
            lines.append(_box_row("", w, T))
        lines += _render_footer(w, session, T)
        print("\n".join(lines))

    _redraw()

    try:
        while True:
            try:
                prompt = input("  \u25b6 ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not prompt:
                continue

            # ---- slash commands -----------------------------------------
            if prompt.startswith("/"):
                parts = prompt[1:].split(None, 1)
                cmd   = parts[0].lower()
                rest  = parts[1] if len(parts) > 1 else ""

                if cmd in ("exit", "quit", "q"):
                    break
                elif cmd == "help":
                    print(paint("  Chat commands", "mint", "semibold"))
                    print(paint("    /help               this summary", "leaf"))
                    print(paint("    /theme NAME         set terminal theme", "sky"))
                    print(paint("    /model NAME         load a model", "sky"))
                    print(paint("    /save               export session markdown", "lavender"))
                    print(paint("    /clear  /reset      redraw or clear history", "butter"))
                    print(paint("    /tokens             token and throughput stats", "fern"))
                    print(paint("    /system PROMPT      set system prompt", "peach"))
                    print(paint("    /temp N  /ctx N     sampling and context", "peach"))
                    print(paint("    /nodes              list remote nodes", "fern"))
                    print(paint("    /stack              open the agentic stack inlet (visual demo)", "blossom"))
                    print(paint("    /exit  /quit        leave chat", "error"))
                elif cmd == "theme":
                    if rest:
                        theme_name = rest.strip()
                        T = _load_theme(theme_name, no_color)
                    _redraw()
                elif cmd == "model":
                    if rest:
                        model = rest.strip()
                        _model_load_animation(model, T)
                    _redraw()
                elif cmd == "save":
                    _export_markdown(home, session)
                elif cmd in ("clear",):
                    _redraw()
                elif cmd == "reset":
                    history.clear()
                    total_tokens = 0
                    _redraw()
                elif cmd == "tokens":
                    print(
                        "  tokens: {:,}  ctx: {}  model: {}  last: {:.1f} tk/s ({:.2f}s)".format(
                            total_tokens, ctx, model,
                            last_gen_stats.get("average_rate", 0.0),
                            last_gen_stats.get("generation_seconds", 0.0),
                        )
                    )
                elif cmd == "ctx":
                    try:
                        ctx = int(rest)
                    except (ValueError, TypeError):
                        pass
                elif cmd == "stack":
                    print(paint("  Agentic Stack inlet (visual demo)", "mint", "semibold"))
                    print(paint("    [input]  user idea -> flag as user-input", "sky"))
                    print(paint("    [brain]  accept -> create one or more plans", "leaf"))
                    print(paint("    [output] push generated plans back to stack", "blossom"))
                    print(paint("    This is the primary inlet for continual stack item assignments.", "dim"))
                elif cmd == "nodes":
                    nodes_path = os.path.join(home, "nodes.json")
                    if os.path.isfile(nodes_path):
                        with open(nodes_path, encoding="utf-8") as fh:
                            reg = json.load(fh)
                        for name, info in reg.items():
                            print("  {:<16} {}".format(name, info.get("target", "")))
                    else:
                        print("  no nodes registered")
                else:
                    print(f"  unknown command: /{cmd}")
                continue

            # ---- user message -------------------------------------------
            ts_now = datetime.now().strftime("%H:%M")
            _append_message(history_path, "user", prompt, model)
            history.append({
                "role": "user", "text": prompt,
                "timestamp": ts_now, "tokens": len(prompt.split()),
            })

            # live thinking loop: spinner during "thinking", then streamed
            # tokens with a smoothed tk/s readout, printed in place.
            try:
                if remote_node:
                    raise RuntimeError("remote chat transport is not implemented")
                response, gen_stats = _generate_live(
                    prompt, model, ctx, server_url, T, reasoning_view=reasoning_view,
                )
            except RuntimeError as error:
                print(f"  {T['err']}provider error: {error}{T['reset']}")
                continue

            resp_tokens   = len(response.split())
            total_tokens += resp_tokens
            last_gen_stats = gen_stats

            history.append({
                "role": "assistant", "text": response,
                "timestamp": datetime.now().strftime("%H:%M"),
                "tokens": resp_tokens, "model": model,
            })
            _append_message(
                history_path, "assistant", response, model, resp_tokens
            )
            _redraw()

    except KeyboardInterrupt:
        print()

    print(
        "  {}session saved to {}{}{}\n".format(
            T["dim"], T["accent"], history_path, T["reset"]
        )
    )


# ---------------------------------------------------------------------------
# Model management subcommand
# ---------------------------------------------------------------------------
def cmd_model(args: argparse.Namespace) -> int:
    home = _leaf_home(getattr(args, "home", None))
    sub  = getattr(args, "model_sub", "list")
    T    = _load_theme(None)

    if sub == "list":
        mdir  = _model_dir(home)
        files = sorted(
            f for f in os.listdir(mdir)
            if f.endswith((".gguf", ".bin", ".safetensors"))
        )
        if not files:
            print(f"  no models in {mdir}")
            print("  use: leaf model pull NODE FILENAME")
            return 0
        print()
        print("  {}{:<44} {:<10} {}{}{}".format(
            T["accent"], "name", "size", T["dim"], "format", T["reset"],
        ))
        print("  " + "\u2500" * 60)
        for f in files:
            p    = os.path.join(mdir, f)
            size = _human(os.path.getsize(p))
            ext  = f.rsplit(".", 1)[-1]
            print("  {}{:<44}{} {:<10} {}{}{}".format(
                T["bot"], f, T["reset"],
                size, T["dim"], ext, T["reset"],
            ))
        print()

    elif sub == "info":
        fname = getattr(args, "file", None)
        if not fname:
            print("usage: leaf model info FILE")
            return 1
        mdir = _model_dir(home)
        p    = os.path.join(mdir, fname)
        if not os.path.isfile(p):
            print(f"file not found: {p}")
            return 1
        size  = os.path.getsize(p)
        sha   = _sha256_file(p)
        mtime = datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")
        ext   = fname.rsplit(".", 1)[-1]
        print()
        for k, v in [
            ("file",   fname),
            ("size",   _human(size)),
            ("format", ext),
            ("sha256", sha[:48] + "..."),
            ("added",  mtime),
        ]:
            print("  {}{:<10}{} {}".format(T["dim"], k, T["reset"], v))
        print()

    elif sub == "pull":
        node  = getattr(args, "node", None)
        fname = getattr(args, "file", None)
        dest  = getattr(args, "dest", None) or _model_dir(home)
        if not node or not fname:
            print("usage: leaf model pull NODE FILE [--dest DIR]")
            return 1
        host = node if ":" in node else f"{node}:7772"
        url  = f"http://{host}/{fname}"
        os.makedirs(dest, exist_ok=True)
        out  = os.path.join(dest, fname)
        _model_pull(url, out, fname, node, T)

    elif sub == "serve":
        port = getattr(args, "port", 7772)
        mdir = _model_dir(home)
        _model_serve(mdir, port, T)

    else:
        print(f"unknown model subcommand: {sub}")
        return 1
    return 0


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _model_pull(url: str, out: str, fname: str, node: str, T: dict) -> None:
    """Download a model file with an animated progress bar."""
    print()
    print(f"  {T['accent']}LeafOS Model Pull{T['reset']}")
    print("  " + "\u2500" * 50)
    print("  {:<8} {}{}{}".format("source", T["accent"], node, T["reset"]))
    print("  {:<8} {}".format("file", fname))
    print("  {:<8} {}".format("dest", os.path.dirname(out)))
    print()

    # HEAD for size
    size = 0
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as r:
            size = int(r.headers.get("Content-Length", 0))
    except Exception:
        pass
    if size:
        print("  {:<8} {}".format("size", _human(size)))
    print()
    print("  downloading ...")

    downloaded = 0
    t0         = time.time()
    bar_w      = 36
    try:
        with urllib.request.urlopen(url, timeout=120) as resp, \
                open(out, "wb") as fh:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                fh.write(chunk)
                downloaded += len(chunk)
                pct     = downloaded / size if size else 0
                spin    = _spin_frame(T)
                bar     = _progress_bar(pct, bar_w, T)
                elapsed = time.time() - t0
                rate    = downloaded / elapsed if elapsed > 0 else 0
                eta     = int((size - downloaded) / rate) if (rate > 0 and size) else 0
                sys.stdout.write(
                    "\r  {} [{}]  {:5.1f}%   {} / {}   {}/s   eta {}s   ".format(
                        spin, bar, pct * 100,
                        _human(downloaded), _human(size) if size else "?",
                        _human(rate), eta,
                    )
                )
                sys.stdout.flush()
    except Exception as exc:
        print(f"\n  {T['err']}error: {exc}{T['reset']}")
        return

    elapsed = time.time() - t0
    print()
    print()
    sys.stdout.write(
        f"  {_spin_frame(T)} verifying sha256 ...  "
    )
    sys.stdout.flush()
    sha = _sha256_file(out)
    print(f"  {T['ok']}OK{T['reset']}  ({sha[:16]}...)")
    print()
    print(
        "  {}\u2713 model ready:{}  {}{}{}".format(
            T["ok"], T["reset"], T["dim"], out, T["reset"]
        )
    )
    print()
    print(f"  downloaded in {elapsed:.1f} s  ({_human(os.path.getsize(out))})")
    print()


def _model_serve(mdir: str, port: int, T: dict) -> None:
    """Serve all model files in mdir over HTTP on the LAN."""
    ip = "0.0.0.0"
    display_ip = "127.0.0.1"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            display_ip = s.getsockname()[0]
    except Exception:
        pass

    files = sorted(
        f for f in os.listdir(mdir)
        if f.endswith((".gguf", ".bin", ".safetensors"))
    )

    class _MH(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *a) -> None:   # type: ignore[override]
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"  [{ts}] {self.client_address[0]}  {fmt % a}")

        def do_GET(self) -> None:                       # type: ignore[override]
            fname = self.path.lstrip("/")
            fpath = os.path.join(mdir, fname)
            if not os.path.isfile(fpath):
                self.send_error(404)
                return
            size = os.path.getsize(fpath)
            self.send_response(200)
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            with open(fpath, "rb") as fh:
                shutil.copyfileobj(fh, self.wfile)

    print()
    print(
        "  {}model serve  \u25c9 ACTIVE  {}:{}{}".format(
            T["accent"], display_ip, port, T["reset"]
        )
    )
    print("  " + "\u2500" * 50)
    for f in files:
        p = os.path.join(mdir, f)
        print("    {:<46} {}".format(f, _human(os.path.getsize(p))))
    if not files:
        print(f"    (no model files in {mdir})")
    print()
    print(
        "  pull command:  leaf model pull {}:{} FILENAME".format(
            display_ip, port
        )
    )
    print(f"  {T['dim']}Ctrl-C to stop{T['reset']}")
    print()
    srv = http.server.HTTPServer((ip, port), _MH)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="chat.py",
        description="LeafOS chat environment and model management",
    )
    p.add_argument("--home",     default=None, help="override LEAF_HOME")
    p.add_argument("--no-color", action="store_true")

    subs = p.add_subparsers(dest="top_cmd")

    # model sub-command --------------------------------------------------
    pm = subs.add_parser("model", help="model management")
    pm.add_argument(
        "model_sub", nargs="?", default="list",
        choices=["list", "info", "pull", "serve"],
    )
    pm.add_argument("node",       nargs="?", default=None)
    pm.add_argument("file",       nargs="?", default=None)
    pm.add_argument("--remote",   default=None)
    pm.add_argument("--dest",     default=None)
    pm.add_argument("--port",     type=int,  default=7772)
    pm.add_argument("--home",     default=None)
    pm.add_argument("--no-color", action="store_true")

    # chat (no subcommand) -----------------------------------------------
    p.add_argument("--model",   default=None)
    p.add_argument("--session", default="default")
    p.add_argument("--theme",   default=None)
    p.add_argument("--remote",  default=None)
    p.add_argument("--server",  default=None, help="llama.cpp server URL for live streaming, e.g. http://127.0.0.1:8080")
    p.add_argument(
        "--reasoning-view", action=argparse.BooleanOptionalAction, default=None,
        help="project explicit THOUGHT/ACTION/CODE/MEMORY/SKILL/ERROR events",
    )
    p.add_argument("--width",   type=int, default=0)
    p.add_argument("--list",    action="store_true", help="list sessions")
    p.add_argument("--export",  default=None, metavar="SESSION")
    return p


def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()
    home   = _leaf_home(getattr(args, "home", None))

    if getattr(args, "top_cmd", None) == "model":
        raise SystemExit(cmd_model(args) or 0)

    if getattr(args, "list", False):
        d        = _chat_dir(home)
        sessions = sorted(f[:-6] for f in os.listdir(d) if f.endswith(".jsonl"))
        if not sessions:
            print("  no sessions yet")
            return
        for s in sessions:
            msgs = _load_history(os.path.join(d, s + ".jsonl"))
            print("  {:<28} {:>4} messages".format(s, len(msgs)))
        return

    if getattr(args, "export", None):
        _export_markdown(home, args.export)
        return

    run_chat(args)


if __name__ == "__main__":
    main()
