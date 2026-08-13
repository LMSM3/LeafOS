from __future__ import annotations

import io
import json
import tempfile
import time
import unittest
from pathlib import Path

from core.testing import visual_test_runner as visual


class VisualTestRunnerTests(unittest.TestCase):
    def test_discovery_covers_original_suite_and_runner_contracts(self) -> None:
        discovered = visual.discover_test_ids()
        self.assertGreaterEqual(sum(map(len, discovered.values())), 124)
        self.assertIn("tests.test_visual_test_runner", discovered)
        self.assertEqual(10, len(discovered["tests.test_agent_loop"]))

    def test_domains_distinguish_stack_from_animation_surfaces(self) -> None:
        self.assertEqual("stack", visual.classify_test("tests.test_chat_provider.test_llamacpp"))
        self.assertEqual("memory", visual.classify_test("tests.test_memory_pipeline.test_replay"))
        self.assertEqual("interface", visual.classify_test("tests.test_tui_native.test_render"))
        self.assertEqual("game", visual.classify_test("tests.test_monday_report.test_tiles"))

    def test_private_reasoning_is_counted_but_not_rendered(self) -> None:
        visible, hidden = visual.strip_private_reasoning(
            "<think>private recursive work</think>STACK DEMO: READY\nAUTHORITY: CPU VALIDATES"
        )
        self.assertNotIn("recursive work", visible)
        self.assertGreater(hidden, 0)
        self.assertIn("STACK DEMO: READY", visible)

    def test_evidence_journal_sequences_machine_readable_events(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            journal = visual.EvidenceJournal(Path(temporary))
            journal.append("test.started", test_id="fixture.one")
            journal.append("test.finished", test_id="fixture.one", outcome="passed")
            events = [json.loads(line) for line in journal.events_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([1, 2], [event["sequence"] for event in events])
        self.assertTrue(all(event["schema"] == visual.SCHEMA for event in events))

    def test_plain_renderer_emits_start_progress_and_result(self) -> None:
        stream = io.StringIO()
        renderer = visual.VisualRenderer(1, animation=True, plain=True, stream=stream)
        test_id = "tests.test_monday_report.MondayReportTests.test_heatmap_has_16_channels_and_slices"
        renderer.start_test(test_id)
        renderer.finish_test({"test_id": test_id, "outcome": "passed", "duration_seconds": 0.01})
        output = stream.getvalue()
        self.assertIn("GAME", output)
        self.assertIn("PASS", output)
        self.assertIn("[########################]", output)

    def test_summary_fails_when_live_stack_gate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = visual.summarize_results(
                "fixture", Path(temporary),
                [{"test_id": "fixture.test", "outcome": "passed"}],
                time.monotonic(), {"sample_count": 0}, {"status": "failed"},
            )
        self.assertEqual("failed", summary["status"])
        self.assertEqual(1, summary["counts"]["passed"])


if __name__ == "__main__":
    unittest.main()
