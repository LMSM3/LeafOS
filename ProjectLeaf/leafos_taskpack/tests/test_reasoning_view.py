#!/usr/bin/env python3
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "ui"))
sys.path.insert(0, str(ROOT / "core" / "runtime"))

from reasoning_view import ReasoningView  # noqa: E402
from thinking_loop import ThinkingLoopEngine  # noqa: E402


class RatePrinterProbe:
    def __init__(self) -> None:
        self.ticks = 0

    def tick(self) -> None:
        self.ticks += 1


class ReasoningViewTests(unittest.TestCase):
    def test_all_six_channels_render_and_share_rate_refresh(self) -> None:
        output = io.StringIO()
        probe = RatePrinterProbe()
        view = ReasoningView(stream=output, rate_printer=probe)
        engine = ThinkingLoopEngine("view-smoke", on_event=view.on_phase)
        engine.feed("[THOUGHT] inspect state")
        engine.feed("[ACTION] run command")
        engine.feed("[CODE] printf('ok')")
        engine.feed("[ERROR] failed command")
        view.on_memory_event({"kind": "reflection", "content": {"text": "reflection committed"}})
        view.on_skill_event({"name": "fixture-skill"})
        rendered = output.getvalue()
        for label in ("THOUGHT", "ACTION", "CODE", "MEMORY", "SKILL", "ERROR"):
            self.assertIn("[" + label + "]", rendered)
        self.assertEqual(probe.ticks, 6)


if __name__ == "__main__":
    unittest.main()
