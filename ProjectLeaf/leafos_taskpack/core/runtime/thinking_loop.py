#!/usr/bin/env python3
"""Structured, observable reasoning phases for LeafOS streamed output.

The engine classifies explicit output markers. It does not infer or expose
private hidden chain-of-thought; unmarked output is retained as a bounded
``thinking`` phase so no streamed text is silently discarded.
"""

from __future__ import annotations

import hashlib
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


UI_DIR = Path(__file__).resolve().parents[1] / "ui"
if str(UI_DIR) not in sys.path:
    sys.path.insert(0, str(UI_DIR))

from live_stream import DEFAULT_EMA_ALPHA, smooth_rate  # noqa: E402


PHASES = {"thinking", "acting", "coding", "error"}
MARKER_RE = re.compile(
    r"(<think>|</think>|<action>|</action>|<code>|</code>|<error>|</error>|"
    r"\[THOUGHT\]|\[ACTION\]|\[CODE\]|\[ERROR\])",
    flags=re.IGNORECASE,
)
MARKER_PHASE = {
    "<think>": "thinking",
    "[thought]": "thinking",
    "</think>": "acting",
    "<action>": "acting",
    "[action]": "acting",
    "</action>": "thinking",
    "<code>": "coding",
    "[code]": "coding",
    "</code>": "acting",
    "<error>": "error",
    "[error]": "error",
    "</error>": "acting",
}


def token_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


@dataclass(frozen=True)
class PhaseEvent:
    phase: str
    text: str
    tokens: int
    elapsed_seconds: float
    generation_tk_s: float
    sequence: int

    def as_dict(self, include_text: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if not include_text:
            value.pop("text", None)
        return value


class ThinkingLoopEngine:
    def __init__(
        self,
        run_id: str,
        *,
        ema_alpha: float = DEFAULT_EMA_ALPHA,
        clock: Callable[[], float] = time.monotonic,
        on_event: Callable[[PhaseEvent], None] | None = None,
    ) -> None:
        self.run_id = run_id
        self.ema_alpha = min(max(ema_alpha, 0.01), 1.0)
        self.clock = clock
        self.on_event = on_event
        self.started_at = clock()
        self.current_phase = "thinking"
        self._phase_started = self.started_at
        self._phase_tokens = 0
        self._phase_rate = 0.0
        self._last_event_at = self.started_at
        self._events: list[PhaseEvent] = []
        self._text_by_phase: dict[str, list[str]] = {phase: [] for phase in PHASES}

    def _set_phase(self, phase: str, now: float) -> None:
        if phase not in PHASES or phase == self.current_phase:
            return
        self.current_phase = phase
        self._phase_started = now
        self._phase_tokens = 0
        self._phase_rate = 0.0
        self._last_event_at = now

    def _emit(self, text: str, now: float) -> PhaseEvent | None:
        if not text:
            return None
        tokens = token_count(text)
        elapsed_delta = max(now - self._last_event_at, 0.001)
        instantaneous = tokens / elapsed_delta if tokens else 0.0
        self._phase_rate = smooth_rate(
            self._phase_rate,
            instantaneous,
            self.ema_alpha,
            first_sample=self._phase_tokens == 0,
        )
        self._phase_tokens += tokens
        self._last_event_at = now
        self._text_by_phase[self.current_phase].append(text)
        event = PhaseEvent(
            phase=self.current_phase,
            text=text,
            tokens=tokens,
            elapsed_seconds=round(max(now - self._phase_started, 0.0), 6),
            generation_tk_s=round(self._phase_rate, 3),
            sequence=len(self._events) + 1,
        )
        self._events.append(event)
        if self.on_event:
            self.on_event(event)
        return event

    def feed(self, chunk: str) -> PhaseEvent | None:
        """Consume one streamed chunk and return its last emitted phase event."""
        if not isinstance(chunk, str):
            raise TypeError("chunk must be text")
        cursor = 0
        last_event: PhaseEvent | None = None
        for match in MARKER_RE.finditer(chunk):
            now = self.clock()
            emitted = self._emit(chunk[cursor:match.start()], now)
            if emitted:
                last_event = emitted
            self._set_phase(MARKER_PHASE[match.group(0).lower()], now)
            cursor = match.end()
        emitted = self._emit(chunk[cursor:], self.clock())
        return emitted or last_event

    def finalize(self) -> dict[str, Any]:
        finished = self.clock()
        phases: list[dict[str, Any]] = []
        for phase in ("thinking", "acting", "coding", "error"):
            text = "".join(self._text_by_phase[phase])
            matching = [event for event in self._events if event.phase == phase]
            if not matching:
                continue
            phases.append({
                "phase": phase,
                "tokens": sum(event.tokens for event in matching),
                "seconds": round(sum(max(event.elapsed_seconds, 0.001) for event in matching), 6),
                "generation_tk_s": round(matching[-1].generation_tk_s, 3),
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "event_count": len(matching),
            })
        return {
            "schema": "leafos.thinking-loop.v1",
            "run_id": self.run_id,
            "phases": phases,
            "events": [event.as_dict(include_text=False) for event in self._events],
            "total_tokens": sum(event.tokens for event in self._events),
            "total_seconds": round(max(finished - self.started_at, 0.0), 6),
        }
