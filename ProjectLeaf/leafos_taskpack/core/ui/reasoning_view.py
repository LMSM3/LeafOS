#!/usr/bin/env python3
"""Live projection of explicit LeafOS reasoning and runtime events."""

from __future__ import annotations

import sys
from typing import Any


PHASE_LABELS = {
    "thinking": "THOUGHT",
    "acting": "ACTION",
    "coding": "CODE",
    "error": "ERROR",
}
LABEL_COLORS = {
    "THOUGHT": "accent",
    "ACTION": "ok",
    "CODE": "warn",
    "MEMORY": "accent",
    "SKILL": "ok",
    "ERROR": "err",
}


class ReasoningView:
    """Render explicit model markers and runtime events without inferring hidden thought."""

    def __init__(self, stream=None, theme: dict | None = None, rate_printer=None) -> None:
        self.stream = stream or sys.stdout
        self.theme = theme or {}
        self.rate_printer = rate_printer

    @staticmethod
    def _value(event: Any, name: str, default: Any = "") -> Any:
        if isinstance(event, dict):
            return event.get(name, default)
        return getattr(event, name, default)

    def _render(self, label: str, text: str) -> None:
        cleaned = " ".join(str(text).split())
        color = self.theme.get(LABEL_COLORS[label], "")
        reset = self.theme.get("reset", "")
        self.stream.write(f"{color}[{label}]{reset} {cleaned}\n")
        self.stream.flush()
        if self.rate_printer is not None:
            self.rate_printer.tick()

    def on_phase(self, event: Any) -> None:
        phase = str(self._value(event, "phase", "thinking"))
        label = PHASE_LABELS.get(phase, "ERROR")
        self._render(label, self._value(event, "text", ""))

    def on_memory_event(self, event: Any) -> None:
        text = self._value(event, "text", "")
        if not text and isinstance(event, dict):
            text = event.get("content", {}).get("text", event.get("kind", "memory event"))
        self._render("MEMORY", text)

    def on_skill_event(self, event: Any) -> None:
        self._render("SKILL", self._value(event, "text", self._value(event, "name", "skill event")))
