import argparse
import concurrent.futures
import contextlib
import io
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = ROOT / "core" / "python" / "leaf_agent_loop.py"
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("leaf_agent_loop", MODULE)
leaf_agent_loop = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(leaf_agent_loop)


def args(**overrides):
    values = {
        "target": "",
        "projects": "generic-python-sim",
        "profile": "cpu-only",
        "provider_mode": "",
        "run_id": "test-run",
        "run_dir": "",
        "max_minutes": 0,
        "dry_run": False,
        "yes": True,
        "force": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def quiet_call(func, *call_args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return func(*call_args)


class AgentLoopTests(unittest.TestCase):
    def setUp(self):
        # Agent-loop unit tests exercise queue and event behavior, not the live
        # operator journal.  Keep them deterministic and leave Monday state to
        # the dedicated durable-bridge integration tests.
        self.authority = mock.patch.object(
            leaf_agent_loop,
            "_agent_ticket",
            side_effect=lambda capability, context=None: {
                "leafos_object": "leafos.capability_ticket.v1",
                "capability": capability,
                "allowed": True,
                "source": "agent-loop-test",
                "context": context or {},
            },
        )
        self.authority.start()

    def tearDown(self):
        self.authority.stop()

    def test_concurrent_event_appends_preserve_reconnect_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(leaf_agent_loop.append_event, run_dir, "fixture.concurrent", value=i) for i in range(40)]
                for future in futures:
                    future.result()
            events = leaf_agent_loop.read_events(run_dir)
            self.assertEqual(list(range(1, 41)), [event["seq"] for event in events])
            self.assertEqual(set(range(40)), {event["value"] for event in events})

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "Games"
            run_dir = base / "runs" / "dry"
            code = quiet_call(
                leaf_agent_loop.create_run,
                args(target=str(target), run_dir=str(run_dir), dry_run=True, yes=False)
            )
            self.assertEqual(0, code)
            self.assertFalse(target.exists())
            self.assertFalse(run_dir.exists())

    def test_create_status_and_tick_complete_skeleton_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "Games"
            run_dir = base / "runs" / "loop"
            self.assertEqual(0, quiet_call(leaf_agent_loop.create_run, args(target=str(target), run_dir=str(run_dir))))

            self.assertTrue((target / "generic-python-sim" / "README.md").is_file())
            self.assertTrue((target / "generic-python-sim" / "run_tests.ps1").is_file())
            self.assertTrue((run_dir / "run.json").is_file())
            self.assertTrue((run_dir / "queue.json").is_file())
            self.assertTrue((run_dir / "events.jsonl").is_file())
            self.assertTrue((run_dir / "universal-run-log.jsonl").is_file())

            status = leaf_agent_loop.status_data(run_dir)
            self.assertEqual("test-run", status["run_id"])
            self.assertEqual({"queued": 1}, status["task_counts"])

            self.assertEqual(0, quiet_call(leaf_agent_loop.tick_run, argparse.Namespace(run=str(run_dir))))
            queue = json.loads((run_dir / "queue.json").read_text(encoding="utf-8"))
            self.assertEqual("complete", queue["tasks"][0]["status"])
            self.assertTrue((run_dir / "checkpoint.json").is_file())
            self.assertIn("validation.passed", (run_dir / "events.jsonl").read_text(encoding="utf-8"))
            universal = [json.loads(line) for line in (run_dir / "universal-run-log.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertIn("run_start", {event["event_type"] for event in universal})
            self.assertIn("validation", {event["event_type"] for event in universal})
            self.assertIn("checkpoint", {event["event_type"] for event in universal})

    def test_stop_and_resume_are_recorded_in_state_and_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "Games"
            run_dir = base / "runs" / "loop"
            self.assertEqual(0, quiet_call(leaf_agent_loop.create_run, args(target=str(target), run_dir=str(run_dir))))
            self.assertEqual(
                0,
                quiet_call(
                    leaf_agent_loop.stop_run,
                    argparse.Namespace(run=str(run_dir), after_current_step=True)
                ),
            )
            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual("paused", state["status"])
            self.assertEqual("after-current-step", state["stop_policy"])
            self.assertEqual(0, quiet_call(leaf_agent_loop.resume_run, argparse.Namespace(run=str(run_dir), yes=True)))
            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual("resumed", state["status"])
            events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("run.paused", events)
            self.assertIn("run.resumed", events)

    def test_validation_failure_queues_repair_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "Games"
            run_dir = base / "runs" / "loop"
            self.assertEqual(0, quiet_call(leaf_agent_loop.create_run, args(target=str(target), run_dir=str(run_dir))))
            queue = json.loads((run_dir / "queue.json").read_text(encoding="utf-8"))
            queue["tasks"][0]["validation_command"] = [
                sys.executable,
                "-c",
                "import sys; sys.exit(7)",
            ]
            (run_dir / "queue.json").write_text(json.dumps(queue), encoding="utf-8")

            self.assertEqual(0, quiet_call(leaf_agent_loop.tick_run, argparse.Namespace(run=str(run_dir), max_minutes=0, yes=True)))
            queue = json.loads((run_dir / "queue.json").read_text(encoding="utf-8"))
            self.assertEqual("failed", queue["tasks"][0]["status"])
            self.assertEqual("repair_queued", queue["tasks"][1]["status"])
            events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("validation.failed", events)
            self.assertIn("repair.queued", events)

            queue["tasks"][1]["validation_command"] = [sys.executable, "-c", "print('repaired')"]
            (run_dir / "queue.json").write_text(json.dumps(queue), encoding="utf-8")
            self.assertEqual(0, quiet_call(leaf_agent_loop.tick_run, argparse.Namespace(run=str(run_dir), max_minutes=0, yes=True)))
            queue = json.loads((run_dir / "queue.json").read_text(encoding="utf-8"))
            self.assertEqual("complete", queue["tasks"][0]["status"])
            self.assertEqual("complete", queue["tasks"][1]["status"])
            self.assertEqual(queue["tasks"][1]["task_id"], queue["tasks"][0]["repaired_by"])

    def test_timeout_writes_event_and_queues_repair_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "Games"
            run_dir = base / "runs" / "loop"
            self.assertEqual(0, quiet_call(leaf_agent_loop.create_run, args(target=str(target), run_dir=str(run_dir))))
            queue = json.loads((run_dir / "queue.json").read_text(encoding="utf-8"))
            queue["tasks"][0]["timeout_seconds"] = 1
            queue["tasks"][0]["validation_command"] = [
                sys.executable,
                "-c",
                "import time; time.sleep(2)",
            ]
            (run_dir / "queue.json").write_text(json.dumps(queue), encoding="utf-8")

            self.assertEqual(0, quiet_call(leaf_agent_loop.tick_run, argparse.Namespace(run=str(run_dir), max_minutes=0, yes=True)))
            queue = json.loads((run_dir / "queue.json").read_text(encoding="utf-8"))
            self.assertEqual("failed", queue["tasks"][0]["status"])
            self.assertEqual("timeout", queue["tasks"][0]["reason"])
            self.assertEqual("repair_queued", queue["tasks"][1]["status"])
            self.assertIn("step.timeout", (run_dir / "events.jsonl").read_text(encoding="utf-8"))

    def test_provider_required_detects_incomplete_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            config_dir = base / "config"
            config_dir.mkdir()
            (config_dir / "vulkan-provider-stack.json").write_text(
                json.dumps({"server": {"executable": "", "model": ""}}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                leaf_agent_loop.require_provider_configured(base)

    def test_provider_auto_records_fallback_and_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "Games"
            run_dir = base / "runs" / "loop"
            with mock.patch.object(
                leaf_agent_loop,
                "provider_configuration_error",
                return_value="fixture provider unavailable",
            ):
                self.assertEqual(
                    0,
                    quiet_call(
                        leaf_agent_loop.create_run,
                        args(
                            target=str(target),
                            run_dir=str(run_dir),
                            profile="provider-auto",
                            provider_mode="auto",
                        ),
                    ),
                )
            run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual("degraded", run["provider_status"])
            self.assertIn("provider.startup_failed", (run_dir / "events.jsonl").read_text(encoding="utf-8"))

    def test_policy_plan_is_valid_and_malformed_proposal_fails_closed(self):
        task = {
            "task_id": "policy-001",
            "provider": "policy",
            "stack_entry": "local-stack:test",
            "workdir": str(ROOT),
            "validation_command": [sys.executable, "-c", "print('ok')"],
            "timeout_seconds": 10,
        }
        plan = leaf_agent_loop.policy_plan(task)
        self.assertEqual([], leaf_agent_loop.validate_plan(plan, task))
        malformed = {**plan, "steps": [{**plan["steps"][0], "command": [sys.executable, "-c", "print('changed')"]}]}
        self.assertIn("provider plan may not replace the queued validation command", leaf_agent_loop.validate_plan(malformed, task))

        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "Games"
            run_dir = base / "runs" / "loop"
            self.assertEqual(0, quiet_call(leaf_agent_loop.create_run, args(target=str(target), run_dir=str(run_dir))))
            queue = json.loads((run_dir / "queue.json").read_text(encoding="utf-8"))
            queue["tasks"][0]["provider_proposal"] = {"untrusted": "shell text"}
            (run_dir / "queue.json").write_text(json.dumps(queue), encoding="utf-8")
            self.assertEqual(0, quiet_call(leaf_agent_loop.tick_run, argparse.Namespace(run=str(run_dir))))
            queue = json.loads((run_dir / "queue.json").read_text(encoding="utf-8"))
            self.assertEqual("failed", queue["tasks"][0]["status"])
            self.assertEqual("invalid_provider_plan", queue["tasks"][0]["reason"])
            self.assertEqual("repair_queued", queue["tasks"][1]["status"])
            self.assertIn("plan.rejected", (run_dir / "events.jsonl").read_text(encoding="utf-8"))

    def test_live_provider_task_without_proposal_blocks_without_synthetic_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "Games"
            run_dir = base / "runs" / "loop"
            with mock.patch.object(leaf_agent_loop, "provider_configuration_error", return_value=""):
                self.assertEqual(
                    0,
                    quiet_call(
                        leaf_agent_loop.create_run,
                        args(target=str(target), run_dir=str(run_dir), profile="provider-auto", provider_mode="auto"),
                    ),
                )
            self.assertEqual(0, quiet_call(leaf_agent_loop.tick_run, argparse.Namespace(run=str(run_dir))))
            queue = json.loads((run_dir / "queue.json").read_text(encoding="utf-8"))
            self.assertEqual("blocked", queue["tasks"][0]["status"])
            self.assertEqual("provider_proposal_missing", queue["tasks"][0]["reason"])
            self.assertFalse(list((run_dir / "artifacts").glob("*.plan.json")))
            self.assertIn("provider.proposal_missing", (run_dir / "events.jsonl").read_text(encoding="utf-8"))


    if __name__ == "__main__":
        unittest.main()
