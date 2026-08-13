#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("leaf_loop_inlet_task_controls", ROOT / "core" / "python" / "leaf_loop_inlet.py")
inlet = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(inlet)


def create_run(base: pathlib.Path) -> pathlib.Path:
    target = base / "repo"
    target.mkdir()
    order = target / "WO-BASE.json"
    order.write_text(json.dumps({
        "work_order_id": "WO-BASE",
        "title": "Task control fixture",
        "target": str(target),
        "objective": "Provide a version two run.",
        "allowed_paths": ["."],
        "acceptance": ["Fixture exists."],
        "commands": {"tests": [[sys.executable, "--version"]]},
        "approval_mode": "automatic",
        "allow_mutation": False,
        "max_attempts": 2,
        "timeout_seconds": 30,
    }), encoding="utf-8")
    run_dir = base / "runs" / "task-controls"
    args = argparse.Namespace(
        target=None, target_option=str(target), work_order=str(order), profile="local-coding",
        provider="off", no_start_provider=True, run_id="task-controls", run_dir=str(run_dir),
        max_minutes=4, yes=True, check=[], objective="", timeout_seconds=30,
        interval=0.01, foreground=False, create_only=True, json=False,
    )
    with mock.patch.object(inlet, "RUNS_ROOT", base / "runs"):
        inlet.create_work_order_run(args)
    return run_dir


def request(command: list[str], **overrides) -> dict:
    task = {
        "objective": "Run a bounded operator validation task.",
        "allowed_paths": ["."],
        "acceptance": ["The declared command passes."],
        "commands": {"tests": [command]},
        "allow_mutation": False,
        "approval_mode": "automatic",
        "priority": 2,
        "max_attempts": 2,
        "timeout_seconds": 30,
        "stack_role": "cpu",
        "dependencies": [],
    }
    task.update(overrides)
    return {"leafos_object": "leafos.task_control_request", "version": 1, "action": "submit", "task": task}


def complete_base_tasks(run_dir: pathlib.Path) -> None:
    queue = inlet.engine.read_json(run_dir / "queue.json", {})
    for task in queue["tasks"]:
        task["status"] = "complete"
    inlet.engine.write_json(run_dir / "queue.json", queue)


class TaskControlTests(unittest.TestCase):
    def test_published_schema_and_sample_match_runtime_contract(self):
        schema = json.loads((ROOT / "schemas" / "leafos.task-control-request.v1.schema.json").read_text(encoding="utf-8"))
        sample = json.loads((ROOT / "config" / "task-control.submit.sample.json").read_text(encoding="utf-8"))
        self.assertEqual("LeafOS Task Control Request", schema["title"])
        self.assertEqual({"submit", "prioritize", "retry", "cancel", "approve"}, set(schema["properties"]["action"]["enum"]))
        normalized = inlet._normalize_task_control(sample)
        self.assertEqual("coder", normalized["task"]["stack_role"])

    def test_submit_creates_bounded_task_work_order_and_native_journal_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = create_run(pathlib.Path(tmp))
            task = inlet.apply_task_control(run_dir, request([sys.executable, "-c", "print('ok')"]))

            self.assertEqual("operator", task["kind"])
            self.assertEqual("off", task["provider"])
            self.assertTrue(pathlib.Path(task["work_order_source"]).is_file())
            self.assertEqual("resumed", inlet.engine.read_json(run_dir / "state.json", {})["status"])
            records = inlet.native_journal.replay(run_dir / "control.lmem")
            self.assertEqual(1, len(records))
            self.assertEqual("submit", records[0]["content"]["data"]["action"])

    def test_submit_preserves_active_task_and_paused_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = create_run(pathlib.Path(tmp))
            state = inlet.engine.read_json(run_dir / "state.json", {})
            state.update(status="running", current_task_id="WO-BASE-001", next_action="active task")
            inlet.engine.write_json(run_dir / "state.json", state)
            inlet.apply_task_control(run_dir, request([sys.executable, "--version"], task_id="TASK-ACTIVE"))
            active = inlet.engine.read_json(run_dir / "state.json", {})
            self.assertEqual("running", active["status"])
            self.assertEqual("WO-BASE-001", active["current_task_id"])
            self.assertEqual("active task", active["next_action"])

            active.update(status="paused", current_task_id="")
            inlet.engine.write_json(run_dir / "state.json", active)
            inlet.apply_task_control(run_dir, request([sys.executable, "--version"], task_id="TASK-PAUSED"))
            paused = inlet.engine.read_json(run_dir / "state.json", {})
            self.assertEqual("paused", paused["status"])

    def test_documented_cli_submits_one_task_noninteractively(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            run_dir = create_run(root)
            request_path = root / "submit.json"
            request_path.write_text(json.dumps(request([sys.executable, "-c", "print('cli')"], task_id="TASK-CLI")), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "core" / "python" / "leaf_loop_inlet.py"), "task", "submit", str(run_dir), str(request_path), "--no-spawn", "--json"],
                cwd=ROOT, capture_output=True, text=True, timeout=15, check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual("TASK-CLI", payload["task"]["task_id"])
            self.assertEqual("queued", payload["task"]["status"])

    def test_priority_orders_runnable_operator_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = create_run(pathlib.Path(tmp))
            complete_base_tasks(run_dir)
            low = inlet.apply_task_control(run_dir, request([sys.executable, "-c", "print('low')"], task_id="TASK-LOW", priority=7))
            high = inlet.apply_task_control(run_dir, request([sys.executable, "-c", "print('high')"], task_id="TASK-HIGH", priority=0))

            self.assertEqual(0, inlet.drive_run(run_dir, interval=0.01))
            starts = [event["task_id"] for event in inlet.engine.read_events(run_dir) if event["kind"] == "task.started" and event["task_id"] in {low["task_id"], high["task_id"]}]
            self.assertEqual(["TASK-HIGH", "TASK-LOW"], starts)

    def test_prioritize_retry_and_task_approval_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = create_run(pathlib.Path(tmp))
            task = inlet.apply_task_control(run_dir, request([sys.executable, "--version"], task_id="TASK-CTRL", approval_mode="required"))
            prioritized = inlet.apply_task_control(run_dir, {
                "leafos_object": "leafos.task_control_request", "version": 1,
                "action": "prioritize", "task_id": task["task_id"], "priority": 0,
            })
            self.assertEqual(0, prioritized["priority"])

            queue = inlet.engine.read_json(run_dir / "queue.json", {})
            current = next(item for item in queue["tasks"] if item["task_id"] == task["task_id"])
            current.update(status="failed", attempts=1, reason="fixture")
            inlet.engine.write_json(run_dir / "queue.json", queue)
            retried = inlet.apply_task_control(run_dir, {
                "leafos_object": "leafos.task_control_request", "version": 1,
                "action": "retry", "task_id": task["task_id"],
            })
            self.assertEqual("repair_queued", retried["status"])

            queue = inlet.engine.read_json(run_dir / "queue.json", {})
            current = next(item for item in queue["tasks"] if item["task_id"] == task["task_id"])
            current.update(status="blocked", reason="approval_required", approval_status="pending")
            inlet.engine.write_json(run_dir / "queue.json", queue)
            approved = inlet.apply_task_control(run_dir, {
                "leafos_object": "leafos.task_control_request", "version": 1,
                "action": "approve", "task_id": task["task_id"],
            })
            self.assertEqual("approved", approved["approval_status"])
            self.assertEqual("queued", approved["status"])

    def test_invalid_submit_fails_before_journal_or_queue_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = create_run(pathlib.Path(tmp))
            before = (run_dir / "queue.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "allowed path"):
                inlet.apply_task_control(run_dir, request([sys.executable, "--version"], allowed_paths=["../escape"]))
            self.assertEqual(before, (run_dir / "queue.json").read_bytes())
            self.assertFalse((run_dir / "control.lmem").exists())

    def test_cancel_interrupts_tracked_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = create_run(pathlib.Path(tmp))
            complete_base_tasks(run_dir)
            task = inlet.apply_task_control(run_dir, request([sys.executable, "-c", "import time; time.sleep(20)"], task_id="TASK-SLEEP"))
            result: list[int] = []
            worker = threading.Thread(target=lambda: result.append(inlet.drive_run(run_dir, interval=0.01)))
            worker.start()
            deadline = time.monotonic() + 8
            while not (run_dir / "active-process.json").is_file() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue((run_dir / "active-process.json").is_file())

            inlet.apply_task_control(run_dir, {
                "leafos_object": "leafos.task_control_request", "version": 1,
                "action": "cancel", "task_id": task["task_id"],
            })
            worker.join(timeout=8)
            self.assertFalse(worker.is_alive())
            queue = inlet.engine.read_json(run_dir / "queue.json", {})
            current = next(item for item in queue["tasks"] if item["task_id"] == task["task_id"])
            self.assertEqual("cancelled", current["status"])
            self.assertFalse((run_dir / "active-process.json").exists())
            self.assertTrue(any(event["kind"] == "task.cancelled" for event in inlet.engine.read_events(run_dir)))

    def test_drain_finishes_active_task_without_claiming_next_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = create_run(pathlib.Path(tmp))
            complete_base_tasks(run_dir)
            first = inlet.apply_task_control(
                run_dir,
                request([sys.executable, "-c", "import time; time.sleep(0.5)"], task_id="TASK-FIRST"),
            )
            second = inlet.apply_task_control(
                run_dir,
                request([sys.executable, "-c", "print('second')"], task_id="TASK-SECOND"),
            )
            result: list[int] = []
            worker = threading.Thread(target=lambda: result.append(inlet.drive_run(run_dir, interval=0.01)))
            worker.start()
            deadline = time.monotonic() + 5
            while not (run_dir / "active-process.json").is_file() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue((run_dir / "active-process.json").is_file())

            inlet.set_control_state(run_dir, "drain")
            worker.join(timeout=5)

            self.assertFalse(worker.is_alive())
            self.assertEqual([0], result)
            queue = inlet.engine.read_json(run_dir / "queue.json", {})
            by_id = {task["task_id"]: task for task in queue["tasks"]}
            self.assertEqual("complete", by_id[first["task_id"]]["status"])
            self.assertEqual("queued", by_id[second["task_id"]]["status"])
            starts = [event.get("task_id") for event in inlet.engine.read_events(run_dir) if event["kind"] == "task.started"]
            self.assertNotIn(second["task_id"], starts)
            self.assertEqual("drained", inlet.engine.read_json(run_dir / "state.json", {})["status"])
            self.assertFalse((run_dir / "worker.lock").exists())


if __name__ == "__main__":
    unittest.main()
