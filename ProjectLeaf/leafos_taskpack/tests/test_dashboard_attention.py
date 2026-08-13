import importlib.util
import json
import os
import pathlib
import tempfile
import unittest


DASHBOARD = pathlib.Path(__file__).resolve().parents[1] / "core" / "ui" / "dashboard.py"
SPEC = importlib.util.spec_from_file_location("leaf_dashboard", DASHBOARD)
dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)


class DashboardAttentionTests(unittest.TestCase):
    def test_failed_tasks_have_priority(self):
        summary = dashboard.build_attention_summary({"failed": 2, "running": 1})
        self.assertEqual(summary["level"], "warning")
        self.assertEqual(summary["next_action"], "leafctl task list")

    def test_running_tasks_are_active(self):
        summary = dashboard.build_attention_summary({"running": 1})
        self.assertEqual(summary["level"], "active")
        self.assertEqual(summary["next_action"], "leafctl task logs")

    def test_empty_queue_suggests_task_creation(self):
        summary = dashboard.build_attention_summary({})
        self.assertEqual(summary["level"], "ready")
        self.assertIn("leafctl agent-task", summary["next_action"])


class DashboardStateDirHelper:
    """Populates a temp ~/.leaf-style home with N json files per state dir."""

    def __init__(self, home, counts):
        for state, count in counts.items():
            d = pathlib.Path(home) / state
            d.mkdir(parents=True, exist_ok=True)
            for i in range(count):
                (d / f"task-{i}.json").write_text("{}", encoding="utf-8")


class DashboardRenderPathTests(unittest.TestCase):
    """Exercises the full render_dashboard/render_json path (not just the
    build_attention_summary helper) for empty, active, and failed queue
    states, and verifies the dashboard never mutates on-disk state."""

    def _snapshot(self, home):
        home = pathlib.Path(home)
        snap = {}
        for p in sorted(home.rglob("*")):
            if p.is_file():
                snap[str(p.relative_to(home))] = p.read_bytes()
        return snap

    def _render(self, counts):
        with tempfile.TemporaryDirectory() as home:
            DashboardStateDirHelper(home, counts)
            before = self._snapshot(home)
            lines = dashboard.render_dashboard(home, no_color=True)
            after = self._snapshot(home)
            self.assertEqual(before, after, "render_dashboard must not mutate on-disk state")
            return "\n".join(lines)

    def test_empty_queue_state_renders(self):
        text = self._render({})
        self.assertIsInstance(text, str)

    def test_active_queue_state_renders(self):
        text = self._render({"running": 2, "queued": 1})
        self.assertIsInstance(text, str)

    def test_failed_queue_state_renders(self):
        text = self._render({"failed": 3, "running": 1})
        self.assertIsInstance(text, str)

    def test_render_json_is_also_read_only(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as home:
            DashboardStateDirHelper(home, {"failed": 1})
            before = self._snapshot(home)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                dashboard.render_json(home)
            after = self._snapshot(home)
            self.assertEqual(before, after, "render_json must not mutate on-disk state")
            self.assertIn('"leafos_object": "dashboard"', buf.getvalue())

    def test_width_80_clips_long_header_and_registry_values(self):
        with tempfile.TemporaryDirectory() as home:
            hp = pathlib.Path(home)
            DashboardStateDirHelper(home, {"failed": 1})
            (hp / "node.json").write_text(json.dumps({
                "node_id": "node-with-a-very-long-name-that-should-not-break-the-header",
                "role": "worker-with-extra-label",
            }), encoding="utf-8")
            (hp / "nodes.json").write_text(json.dumps({
                "remote-node-name-that-is-too-long": {
                    "target": "user@192.168.4.200:/very/long/path",
                    "transport": "ssh-with-long-label",
                },
            }), encoding="utf-8")

            old_width = os.environ.get("LEAF_DASH_WIDTH")
            os.environ["LEAF_DASH_WIDTH"] = "80"
            try:
                lines = dashboard.render_dashboard(home, no_color=True)
            finally:
                if old_width is None:
                    os.environ.pop("LEAF_DASH_WIDTH", None)
                else:
                    os.environ["LEAF_DASH_WIDTH"] = old_width

            visible_lengths = [len(dashboard._strip_ansi(line)) for line in lines]
            self.assertLessEqual(max(visible_lengths), 80)


if __name__ == "__main__":
    unittest.main()
