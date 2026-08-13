#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/ui/live_stream.py -- shared live "thinking loop" + smoothed rate printer.

Provides a small, dependency-free ANSI live-refresh printer used by both the
LeafOS chat CLI (tokens/second while streaming a model response) and the
board-game-lab training loop (games or generations/second while training).

Design goals
------------
- High, smooth refresh rate: redraws at a fixed interval (default ~20 Hz,
  i.e. every 50ms) regardless of how often new units arrive, so the rate
  readout does not visibly stutter even when tokens/updates arrive in
  bursts.
- EMA-smoothed throughput: instantaneous unit deltas are noisy (a single
  slow token skews an instantaneous rate wildly), so the rate shown is an
  exponential moving average blended with the overall run-average.
- Two phases:
    * "thinking": before the first unit has arrived, show a spinner and
      elapsed time (this is the model/engine "thinking" period).
    * "streaming": once units start arriving, show live content plus a
      right-aligned smoothed rate readout.
- In-place refresh via carriage-return (single line) or ANSI cursor-up
  (multi-line), following the same technique already used elsewhere in
  this workspace (viz_host.py's "\\r" status line and viz_web.py's
  "\\033[{n}A" multi-line refresh).
- Stdlib only. Safe to import even when stdout is not a TTY (falls back to
  simple periodic prints without cursor control).
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

_BRAND_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "brand"))
if _BRAND_DIR not in sys.path:
    sys.path.insert(0, _BRAND_DIR)
from flower_palette import SPINNER_FRAMES  # noqa: E402

_SPIN_FRAMES = SPINNER_FRAMES

# Default refresh interval for a smooth, high refresh-rate readout.
DEFAULT_REFRESH_SECONDS = 0.05  # 20 Hz
# EMA smoothing factor: higher = more responsive, lower = smoother.
DEFAULT_EMA_ALPHA = 0.35


def smooth_rate(previous: float, instantaneous: float, alpha: float, first_sample: bool = False) -> float:
    """Shared EMA primitive for live and phase-aware throughput counters."""
    bounded_alpha = min(max(alpha, 0.01), 1.0)
    if first_sample:
        return max(0.0, instantaneous)
    return bounded_alpha * max(0.0, instantaneous) + (1.0 - bounded_alpha) * max(0.0, previous)


def _term_width(default: int = 100) -> int:
    try:
        return shutil.get_terminal_size(fallback=(default, 24)).columns
    except OSError:
        return default


@dataclass
class _RateState:
    started: float
    last_refresh: float
    last_unit_count: int = 0
    total_units: int = 0
    ema_rate: float = 0.0
    first_unit_at: Optional[float] = None


class LiveRatePrinter:
    """Smooth, high-refresh-rate live printer for a "thinking -> streaming"
    loop, generalized over any countable unit (tokens, games, generations).

    Usage::

        printer = LiveRatePrinter(unit_label="tk/s", theme=T)
        printer.start(label="thinking")
        for token in generator:
            printer.update(text=token, units=1)
        printer.finish(summary="done")
    """

    def __init__(
        self,
        unit_label: str = "tk/s",
        theme: Optional[dict] = None,
        refresh_seconds: float = DEFAULT_REFRESH_SECONDS,
        ema_alpha: float = DEFAULT_EMA_ALPHA,
        stream: Optional[object] = None,
        is_tty: Optional[bool] = None,
    ) -> None:
        self.unit_label = unit_label
        self.theme = theme or {}
        self.refresh_seconds = max(0.01, refresh_seconds)
        self.ema_alpha = min(max(ema_alpha, 0.01), 1.0)
        self.stream = stream or sys.stdout
        self._is_tty = self._detect_tty() if is_tty is None else is_tty
        self._state: Optional[_RateState] = None
        self._buffer: list[str] = []
        self._spin_idx = 0
        self._active_lines = 0
        self._thinking_label = "thinking"

    def _detect_tty(self) -> bool:
        try:
            return bool(self.stream.isatty())
        except (AttributeError, ValueError):
            return False

    def _color(self, key: str) -> str:
        return self.theme.get(key, "") if self.theme else ""

    def _reset(self) -> str:
        return self.theme.get("reset", "") if self.theme else ""

    def _spin(self) -> str:
        frame = _SPIN_FRAMES[self._spin_idx % len(_SPIN_FRAMES)]
        self._spin_idx += 1
        return frame

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self, label: str = "thinking") -> None:
        """Begin the thinking phase: spinner + elapsed time, no units yet."""
        now = time.monotonic()
        self._thinking_label = label
        self._state = _RateState(started=now, last_refresh=0.0)
        self._buffer = []
        self._active_lines = 0
        self._render(force=True)

    def tick(self) -> None:
        """Refresh the thinking spinner without adding units (call in a
        tight loop while waiting for the first byte from a model/process).
        """
        if self._state is None:
            self.start()
        self._render()

    def update(self, text: str = "", units: int = 0, replace: bool = False) -> None:
        """Append streamed text and account for `units` new units (e.g. one
        token, or one completed game). Triggers a throttled re-render.

        If `replace` is True, `text` replaces the current buffer instead of
        being appended -- useful for status-style live lines (e.g. training
        generation progress) rather than character-by-character streaming.
        """
        if self._state is None:
            self.start()
        state = self._state
        now = time.monotonic()
        if units:
            if state.first_unit_at is None:
                state.first_unit_at = now
            state.total_units += units
        if replace:
            self._buffer = [text] if text else []
        elif text:
            self._buffer.append(text)
        self._render()

    def finish(self, summary: str = "") -> dict:
        """Finalize the live line, print a trailing newline, and return
        summary stats (elapsed, total_units, average rate).
        """
        state = self._state
        self._render(force=True)
        if self._is_tty:
            self.stream.write("\n")
        else:
            self.stream.write("\n")
        self.stream.flush()
        if state is None:
            return {"elapsed_seconds": 0.0, "total_units": 0, "average_rate": 0.0}
        elapsed = max(time.monotonic() - state.started, 0.001)
        gen_elapsed = (
            max(time.monotonic() - state.first_unit_at, 0.001)
            if state.first_unit_at is not None
            else elapsed
        )
        average_rate = round(state.total_units / gen_elapsed, 3)
        if summary:
            self.stream.write(summary + "\n")
            self.stream.flush()
        return {
            "elapsed_seconds": round(elapsed, 3),
            "generation_seconds": round(gen_elapsed, 3),
            "total_units": state.total_units,
            "average_rate": average_rate,
            "final_ema_rate": round(state.ema_rate, 3),
        }

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _current_rate(self, state: _RateState, now: float) -> float:
        dt = now - (state.last_refresh or state.started)
        if dt <= 0:
            return state.ema_rate
        delta_units = state.total_units - state.last_unit_count
        instantaneous = delta_units / dt if dt > 0 else 0.0
        state.ema_rate = smooth_rate(
            state.ema_rate,
            instantaneous,
            self.ema_alpha,
            first_sample=state.last_unit_count == 0 and state.ema_rate == 0.0,
        )
        state.last_unit_count = state.total_units
        return state.ema_rate

    def _render(self, force: bool = False) -> None:
        state = self._state
        if state is None:
            return
        now = time.monotonic()
        if not force and (now - state.last_refresh) < self.refresh_seconds:
            return

        rate = self._current_rate(state, now)
        state.last_refresh = now
        elapsed = now - state.started

        dim = self._color("dim")
        accent = self._color("accent")
        ok = self._color("ok")
        reset = self._reset()
        width = _term_width()

        if state.total_units == 0:
            # Thinking phase: spinner + elapsed time only.
            line = "  {spin} {dim}{label}...{reset}  {dim}{elapsed:.1f}s{reset}".format(
                spin=(self._color("spinner") + self._spin() + reset),
                dim=dim, label=self._thinking_label, reset=reset, elapsed=elapsed,
            )
            self._write_line(line, width)
            return

        # Streaming phase: recent text tail + live rate readout.
        text = "".join(self._buffer)
        rate_str = "{ok}{rate:6.1f} {unit}{reset}".format(
            ok=ok, rate=rate, unit=self.unit_label, reset=reset,
        )
        meta = "  {dim}[{elapsed:.1f}s \u00b7 {units} units \u00b7 {rate_str}{dim}]{reset}".format(
            dim=dim, elapsed=elapsed, units=state.total_units, rate_str=rate_str, reset=reset,
        )
        available = max(width - len(_strip_ansi(meta)) - 4, 8)
        tail = text[-available:] if len(text) > available else text
        tail = tail.replace("\n", " \u23ce ")
        line = "  {accent}{tail}{reset}{meta}".format(accent=accent, tail=tail, reset=reset, meta=meta)
        self._write_line(line, width)

    def _write_line(self, line: str, width: int) -> None:
        if self._is_tty:
            padded = line
            visible_len = len(_strip_ansi(line))
            if visible_len < width:
                padded = line + " " * (width - visible_len)
            self.stream.write("\r" + padded)
        else:
            self.stream.write(line + "\n")
        self.stream.flush()


def _strip_ansi(text: str) -> str:
    out = []
    skip = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\x1b":
            skip = True
            i += 1
            continue
        if skip:
            if ch.isalpha():
                skip = False
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def run_with_live_rate(
    unit_label: str,
    generator_factory: Callable[[], "iter"],
    theme: Optional[dict] = None,
    thinking_label: str = "thinking",
) -> tuple[str, dict]:
    """Convenience wrapper: drive a LiveRatePrinter over any iterator of
    text chunks (one chunk == one unit), returning (full_text, stats).
    """
    printer = LiveRatePrinter(unit_label=unit_label, theme=theme)
    printer.start(label=thinking_label)
    chunks: list[str] = []
    for chunk in generator_factory():
        chunks.append(chunk)
        printer.update(text=chunk, units=1)
    stats = printer.finish()
    return "".join(chunks), stats
