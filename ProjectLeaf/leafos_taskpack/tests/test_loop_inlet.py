import argparse
import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("leaf_loop_inlet", ROOT / "core" / "python" / "leaf_loop_inlet.py")
inlet = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(inlet)


class FakeResponse:
    status = 200

    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        return iter(self.lines)


def start_args(target: pathlib.Path, run_dir: pathlib.Path, **overrides):
    values = {
        "target": str(target),
        "objective": "Validate this repository.",
        "provider": "off",
        "run_id": "inlet-test",
        "run_dir": str(run_dir),
        "max_minutes": 4,
        "timeout_seconds": 20,
        "interval": 0.01,
        "no_start_provider": True,
        "foreground": False,
        "create_only": True,
        "json": False,
        "check": [sys.executable, "-c", "print('inlet-ok')"],
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def monitor_args(run_dir: pathlib.Path, **overrides):
    values = {
        "run": str(run_dir),
        "after": 0,
        "interval": 0.01,
        "heartbeat_timeout": 90.0,
        "timeout": 0.0,
        "cursor_file": "",
        "once": True,
        "json": True,
        "jsonl": False,
        "interactive": False,
        "noninteractive": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def write_monitor_run(base: pathlib.Path, state: str = "complete", events=None, lease=None) -> pathlib.Path:
    run_dir = base / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"run_id": "monitor-fixture", "target": str(base), "provider_mode": "off"}),
        encoding="utf-8",
    )
    (run_dir / "queue.json").write_text(json.dumps({"tasks": []}), encoding="utf-8")
    (run_dir / "state.json").write_text(
        json.dumps({"status": state, "current_task_id": "", "next_action": "loop report"}),
        encoding="utf-8",
    )
    (run_dir / "checkpoint.json").write_text(json.dumps({}), encoding="utf-8")
    event_values = events or [{"seq": 1, "time": "2026-07-24T00:00:00+00:00", "kind": "run.completed"}]
    (run_dir / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in event_values),
        encoding="utf-8",
    )
    if lease is not None:
        (run_dir / "worker.lock").write_text(json.dumps(lease), encoding="utf-8")
    return run_dir


class LoopInletTests(unittest.TestCase):
    def test_provider_launcher_uses_file_backed_capture(self):
        config = {
            "server": {"host": "127.0.0.1", "port": 8080},
            "lifecycle": {"startup_timeout_seconds": 5},
        }
        observed = {}

        def fake_run(command, **kwargs):
            observed.update(kwargs)
            kwargs["stdout"].write(b'{"status":"started"}')
            kwargs["stdout"].flush()
            return types.SimpleNamespace(returncode=0)

        with mock.patch.object(inlet.subprocess, "run", side_effect=fake_run), mock.patch.object(
            inlet, "provider_healthy", side_effect=(False, True)
        ):
            ok, reason = inlet.start_provider_stack(config)

        self.assertTrue(ok)
        self.assertEqual('{"status":"started"}', reason)
        self.assertNotIn("capture_output", observed)
        self.assertNotEqual(inlet.subprocess.PIPE, observed["stdout"])
        self.assertEqual(inlet.subprocess.STDOUT, observed["stderr"])

    def test_repository_run_uses_policy_without_mutating_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "repo"
            target.mkdir()
            marker = target / "owned.txt"
            marker.write_text("unchanged", encoding="utf-8")
            run_dir = base / "runs" / "one"
            with mock.patch.object(inlet, "RUNS_ROOT", base / "runs"):
                created = inlet.create_repository_run(start_args(target, run_dir))

            queue = inlet.engine.read_json(created / "queue.json", {})
            self.assertEqual("policy", queue["tasks"][0]["provider"])
            self.assertEqual(start_args(target, run_dir).check, queue["tasks"][0]["validation_command"])
            self.assertEqual("unchanged", marker.read_text(encoding="utf-8"))
            self.assertFalse((target / "run.json").exists())

    def test_repository_run_persists_bounded_work_order_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "repo"
            target.mkdir()
            work_order = target / "WO-001.md"
            work_order.write_text("# Inspect repository\n\nReview the current state.\n", encoding="utf-8")
            run_dir = base / "runs" / "one"
            with mock.patch.object(inlet, "RUNS_ROOT", base / "runs"):
                created = inlet.create_repository_run(start_args(target, run_dir, work_order=str(work_order)))

            run = inlet.engine.read_json(created / "run.json", {})
            queue = inlet.engine.read_json(created / "queue.json", {})
            self.assertEqual(str(work_order.resolve()), run["work_order"]["path"])
            self.assertEqual("Inspect repository", run["work_order"]["title"])
            self.assertEqual(str(work_order.resolve()), queue["tasks"][0]["work_order"])
            self.assertTrue(run["work_order"]["sha256"])
            self.assertTrue(any(event.get("work_order") == str(work_order.resolve()) for event in inlet.engine.read_events(created)))

    def test_repository_run_rejects_work_order_outside_safety_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "repo"
            target.mkdir()
            work_order = base / "outside.md"
            work_order.write_text("# Outside\n", encoding="utf-8")
            run_dir = base / "runs" / "one"
            with mock.patch.object(inlet, "RUNS_ROOT", base / "runs"):
                with self.assertRaisesRegex(ValueError, "outside the repository safety boundary"):
                    inlet.create_repository_run(start_args(target, run_dir, work_order=str(work_order)))

    def test_cpu_policy_drive_completes_through_existing_executor(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "repo"
            target.mkdir()
            run_dir = base / "runs" / "one"
            with mock.patch.object(inlet, "RUNS_ROOT", base / "runs"):
                inlet.create_repository_run(start_args(target, run_dir))
                self.assertEqual(0, inlet.drive_run(run_dir, interval=0.01))

            state = inlet.engine.read_json(run_dir / "state.json", {})
            queue = inlet.engine.read_json(run_dir / "queue.json", {})
            self.assertEqual("complete", state["status"])
            self.assertEqual("complete", queue["tasks"][0]["status"])
            self.assertFalse((run_dir / "worker.lock").exists())

    def test_streamed_provider_plan_is_validated_and_attached(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "repo"
            target.mkdir()
            run_dir = base / "runs" / "one"
            with mock.patch.object(inlet, "RUNS_ROOT", base / "runs"):
                inlet.create_repository_run(start_args(target, run_dir))
            queue = inlet.engine.read_json(run_dir / "queue.json", {})
            task = queue["tasks"][0]
            task["provider"] = "llamacpp"
            plan = inlet.engine.policy_plan({**task, "provider": "policy"})
            plan["provider"] = "llamacpp"
            inlet.engine.write_json(run_dir / "queue.json", queue)
            run = inlet.engine.read_json(run_dir / "run.json", {})
            run["provider_endpoint"] = "http://provider.test/v1/chat/completions"
            inlet.engine.write_json(run_dir / "run.json", run)
            encoded = json.dumps(plan, separators=(",", ":"))
            response = FakeResponse(
                [
                    b'data: {"choices":[{"delta":{"reasoning_content":"reviewing"}}]}\n',
                    ("data: " + json.dumps({"choices": [{"delta": {"content": encoded}}]}) + "\n").encode(),
                    b'data: [DONE]\n',
                ]
            )
            config = {
                "server": {"model": "fixture"},
                "thinking_loop": {"max_output_tokens": 512, "temperature": 0},
                "api": {"path": "/v1/chat/completions"},
            }
            with mock.patch.object(inlet, "load_provider_config", return_value=config), mock.patch.object(
                inlet.urllib.request, "urlopen", return_value=response
            ):
                attached = inlet.attach_provider_proposal(run_dir, task["task_id"])

            self.assertEqual(plan, attached)
            queue = inlet.engine.read_json(run_dir / "queue.json", {})
            self.assertEqual(plan, queue["tasks"][0]["provider_proposal"])
            events = inlet.engine.read_events(run_dir)
            self.assertTrue(any(event["kind"] == "provider.proposal.attached" for event in events))
            self.assertTrue(any(event["kind"] == "provider.request.completed" for event in events))
            self.assertFalse(any("reasoning_content" in event for event in events))

    def test_controls_and_cursor_replay_are_persistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "repo"
            target.mkdir()
            run_dir = base / "runs" / "one"
            with mock.patch.object(inlet, "RUNS_ROOT", base / "runs"):
                inlet.create_repository_run(start_args(target, run_dir))
            first_cursor = inlet.engine.read_events(run_dir)[-1]["seq"]
            inlet.set_control_state(run_dir, "pause")
            inlet.set_control_state(run_dir, "resume")
            inlet.set_control_state(run_dir, "drain")
            replay = inlet.events_after(run_dir, first_cursor)

            self.assertEqual(["run.paused", "run.resumed", "run.drain_requested"], [event["kind"] for event in replay])
            state = inlet.engine.read_json(run_dir / "state.json", {})
            self.assertEqual("draining", state["status"])
            self.assertFalse(state["accepting_tasks"])
            control_records = inlet.native_journal.replay(run_dir / "control.lmem")
            self.assertEqual(["run.pause", "run.resume", "run.drain"], [record["content"]["data"]["action"] for record in control_records])

    def test_monitor_json_once_replays_events_and_persists_cursor(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            run_dir = write_monitor_run(
                base,
                events=[
                    {"seq": 1, "time": "2026-07-24T00:00:00+00:00", "kind": "run.started"},
                    {"seq": 2, "time": "2026-07-24T00:00:01+00:00", "kind": "run.completed"},
                ],
            )
            cursor = base / "monitor.cursor"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = inlet.command_monitor(monitor_args(run_dir, cursor_file=str(cursor)))

            payload = json.loads(output.getvalue())
            self.assertEqual(0, code)
            self.assertEqual("leafos.loop_monitor.snapshot", payload["leafos_object"])
            self.assertEqual(2, payload["event_cursor"])
            self.assertEqual(2, len(payload["new_events"]))
            self.assertEqual("2", cursor.read_text(encoding="utf-8").strip())

    def test_monitor_auto_selects_jsonl_when_output_is_redirected(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_monitor_run(pathlib.Path(tmp))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = inlet.command_monitor(monitor_args(run_dir, json=False, jsonl=False))

            payload = json.loads(output.getvalue())
            self.assertEqual(0, code)
            self.assertEqual("leafos.loop_monitor.snapshot", payload["leafos_object"])

    def test_monitor_interactive_renderer_is_plain_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_monitor_run(pathlib.Path(tmp))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = inlet.command_monitor(
                    monitor_args(run_dir, json=False, interactive=True)
                )

            self.assertEqual(0, code)
            self.assertIn("LeafOS loop monitor", output.getvalue())
            self.assertIn("state       : complete", output.getvalue())
            self.assertNotIn("\\033[2J", output.getvalue())

    def test_monitor_stale_heartbeat_has_distinct_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_monitor_run(
                pathlib.Path(tmp),
                state="running",
                lease={"pid": 2468, "heartbeat_utc": "2020-01-01T00:00:00+00:00", "state": "running"},
            )
            output = io.StringIO()
            with mock.patch.object(inlet, "_pid_alive", return_value=False), contextlib.redirect_stdout(output):
                code = inlet.command_monitor(monitor_args(run_dir, jsonl=True))

            payload = json.loads(output.getvalue())
            self.assertEqual(3, code)
            self.assertTrue(payload["heartbeat"]["stale"])
            self.assertEqual("worker_not_alive", payload["heartbeat"]["reason"])

    def test_monitor_running_without_worker_lease_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_monitor_run(pathlib.Path(tmp), state="running")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = inlet.command_monitor(monitor_args(run_dir, jsonl=True))

            payload = json.loads(output.getvalue())
            self.assertEqual(3, code)
            self.assertTrue(payload["heartbeat"]["stale"])
            self.assertEqual("no_worker_lease", payload["heartbeat"]["reason"])

    def test_monitor_timeout_returns_distinct_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_monitor_run(pathlib.Path(tmp), state="created")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = inlet.command_monitor(
                    monitor_args(run_dir, json=False, jsonl=True, once=False, timeout=0.01)
                )

            self.assertEqual(4, code)
            self.assertGreaterEqual(len(output.getvalue().splitlines()), 1)

    def test_monitor_rejects_cursor_inside_run_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_monitor_run(pathlib.Path(tmp))
            with self.assertRaisesRegex(ValueError, "outside the run directory"):
                inlet.command_monitor(monitor_args(run_dir, cursor_file=str(run_dir / "cursor")))

    def test_monitor_blocked_run_returns_failure_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_monitor_run(pathlib.Path(tmp), state="blocked")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = inlet.command_monitor(monitor_args(run_dir))

            self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main()
