import argparse
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


work_orders = load_module("leaf_work_order_test", ROOT / "core" / "python" / "leaf_work_order.py")
inlet = load_module("leaf_loop_inlet_work_order_test", ROOT / "core" / "python" / "leaf_loop_inlet.py")


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


def write_work_order(base: pathlib.Path, target: pathlib.Path) -> pathlib.Path:
    path = base / "WO-TEST.json"
    path.write_text(
        json.dumps(
            {
                "work_order_id": "WO-TEST",
                "title": "Exercise work-order loop",
                "target": str(target),
                "objective": "Inspect and validate the fixture repository.",
                "allowed_paths": ["."],
                "denied_paths": ["private"],
                "commands": {"tests": [[sys.executable, "--version"]]},
                "acceptance": ["The declared validation command passes."],
                "max_attempts": 2,
                "timeout_seconds": 30,
                "approval_mode": "required",
                "allow_mutation": True,
            }
        ),
        encoding="utf-8",
    )
    return path


class WorkOrderLoopTests(unittest.TestCase):
    def test_intake_decomposes_six_dependency_ordered_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "repo"
            target.mkdir()
            order = work_orders.validate_work_order(work_orders.load_work_order(write_work_order(base, target)), target)
            tasks = work_orders.queue_from_work_order(order, "llamacpp")
            self.assertEqual(["inspect", "plan", "approve", "execute", "validate", "report"], [task["kind"] for task in tasks])
            self.assertEqual([], tasks[0]["dependencies"])
            self.assertEqual([tasks[0]["task_id"]], tasks[1]["dependencies"])
            self.assertEqual("llamacpp", tasks[1]["provider"])

    def test_path_and_command_policy_reject_escape_and_undeclared_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "repo"
            target.mkdir()
            (target / "safe").mkdir()
            data = json.loads(write_work_order(base, target).read_text(encoding="utf-8"))
            data["allowed_paths"] = ["safe"]
            order = work_orders.validate_work_order(data, target)
            with self.assertRaisesRegex(ValueError, "escapes target"):
                order["_policy"].resolve("../outside.txt")
            with self.assertRaisesRegex(ValueError, "outside allowed_paths"):
                order["_policy"].resolve("other.txt")
            task = work_orders.queue_from_work_order(order, "llamacpp")[1]
            plan = {
                "leafos_object": "agent_loop_plan",
                "version": 2,
                "task_id": task["task_id"],
                "steps": [
                    {"id": "bad", "kind": "run_command", "command": ["cmd", "/c", "del", "*"], "cwd": ".", "timeout_seconds": 10}
                ],
            }
            errors = work_orders.validate_plan_v2(plan, task, order, base / "run")
            self.assertTrue(any("not declared" in error for error in errors))

    def test_plan_normalization_uses_only_unambiguous_declared_test_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "repo"
            target.mkdir()
            order = work_orders.validate_work_order(work_orders.load_work_order(write_work_order(base, target)), target)
            plan = {"steps": [{"id": "verify", "kind": "run_tests"}]}
            normalized = work_orders.normalize_plan_v2(plan, order)
            self.assertEqual([sys.executable, "--version"], normalized["steps"][0]["command"])

    def test_plan_schema_requires_kind_specific_fields(self):
        variants = work_orders.plan_v2_schema()["schema"]["properties"]["steps"]["items"]["oneOf"]
        write_variant = next(item for item in variants if item["properties"]["kind"].get("const") == "write_file")
        test_variant = next(item for item in variants if item["properties"]["kind"].get("const") == "run_tests")
        self.assertEqual({"id", "kind", "path", "content"}, set(write_variant["required"]))
        self.assertIn("command", test_variant["required"])
        self.assertFalse(write_variant["additionalProperties"])

    def test_inspection_excerpts_are_bounded_for_local_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "repo"
            target.mkdir()
            for index in range(6):
                (target / f"source-{index}.py").write_text("x" * 5000, encoding="utf-8")
            order = work_orders.validate_work_order(work_orders.load_work_order(write_work_order(base, target)), target)
            run_dir = base / "run"
            (run_dir / "artifacts").mkdir(parents=True)
            artifact = work_orders.inspect_work_order(run_dir, order)
            inspection = json.loads(artifact.read_text(encoding="utf-8"))
            excerpt_bytes = sum(len(item.get("excerpt", "").encode("utf-8")) for item in inspection["files"])
            self.assertLessEqual(excerpt_bytes, work_orders.DEFAULT_INSPECTION_CONTENT_BYTES)

    def test_mutation_requires_approval_and_completed_steps_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "repo"
            target.mkdir()
            order = work_orders.validate_work_order(work_orders.load_work_order(write_work_order(base, target)), target)
            run_dir = base / "run"
            (run_dir / "artifacts").mkdir(parents=True)
            inlet.engine.write_json(run_dir / "queue.json", {"tasks": []})
            task = {"task_id": "WO-TEST-004"}
            plan = {
                "steps": [
                    {"id": "write", "kind": "write_file", "path": "result.txt", "content": "approved\n"},
                    {"id": "hash", "kind": "record_hashes", "paths": ["result.txt"]},
                ]
            }
            emit = lambda kind, **data: inlet.engine.append_event(run_dir, kind, **data)
            with self.assertRaisesRegex(RuntimeError, "approval required"):
                work_orders.execute_plan_v2(run_dir, {"approval": {"status": "pending"}}, task, order, plan, emit)
            self.assertFalse((target / "result.txt").exists())
            run = {"approval": {"status": "approved"}, "provider_mode": "off", "stack_entry": "local-stack:test"}
            work_orders.execute_plan_v2(run_dir, run, task, order, plan, emit)
            first_event_count = len(inlet.engine.read_events(run_dir))
            work_orders.execute_plan_v2(run_dir, run, task, order, plan, emit)
            self.assertEqual("approved\n", (target / "result.txt").read_text(encoding="utf-8"))
            replay = inlet.engine.read_events(run_dir)[first_event_count:]
            self.assertEqual(["step.skipped", "step.skipped"], [event["kind"] for event in replay])

    def test_operator_repair_archives_failed_plan_and_step_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "run"
            (run_dir / "artifacts").mkdir(parents=True)
            task = {
                "task_id": "TASK-REPAIR", "kind": "operator", "attempts": 1,
                "evidence": [{"kind": "plan_v2", "path": str(run_dir / "artifacts" / "TASK-REPAIR.plan.v2.json")}],
            }
            plan_path = work_orders._plan_path(run_dir, task)
            step_path = work_orders._step_state_path(run_dir, task)
            inlet.engine.write_json(plan_path, {"steps": []})
            inlet.engine.write_json(step_path, {"completed_step_ids": ["broken"]})

            archived = work_orders._archive_attempt_artifacts(run_dir, task)

            self.assertEqual(2, len(archived))
            self.assertFalse(plan_path.exists())
            self.assertFalse(step_path.exists())
            self.assertTrue(all(pathlib.Path(path).is_file() for path in archived))
            self.assertIn("attempt-1", task["evidence"][0]["path"])

    def test_pipeline_failure_rewinds_to_plan_instead_of_repeating_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "run"
            (run_dir / "artifacts").mkdir(parents=True)
            tasks = [
                {"task_id": "WO-TEST-002", "kind": "plan", "work_order": "WO.json", "status": "complete", "attempts": 1, "max_attempts": 2, "evidence": []},
                {"task_id": "WO-TEST-003", "kind": "approve", "work_order": "WO.json", "status": "complete"},
                {"task_id": "WO-TEST-004", "kind": "execute", "work_order": "WO.json", "status": "queued", "attempts": 1, "evidence": []},
                {"task_id": "WO-TEST-005", "kind": "validate", "work_order": "WO.json", "status": "queued"},
                {"task_id": "WO-TEST-006", "kind": "report", "work_order": "WO.json", "status": "queued"},
            ]
            queue = {"tasks": tasks}
            inlet.engine.write_json(run_dir / "queue.json", queue)
            inlet.engine.write_json(run_dir / "plan.v2.json", {"steps": [{"id": "broken"}]})
            inlet.engine.write_json(run_dir / "step-state.json", {"completed_step_ids": ["broken"]})

            work_orders._rewind_pipeline_for_repair(run_dir, queue, tasks[2], tasks[0]["task_id"], "tests failed")

            latest = inlet.engine.read_json(run_dir / "queue.json", {})
            by_kind = {task["kind"]: task for task in latest["tasks"]}
            self.assertEqual("repair_queued", by_kind["plan"]["status"])
            self.assertTrue(all(by_kind[kind]["status"] == "queued" for kind in ("approve", "execute", "validate", "report")))
            self.assertEqual("tests failed", by_kind["plan"]["evidence"][-1]["error"])
            self.assertFalse((run_dir / "plan.v2.json").exists())
            self.assertFalse((run_dir / "step-state.json").exists())

    def test_full_work_order_lifecycle_with_provider_plan_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "repo"
            target.mkdir()
            (target / "sample.txt").write_text("fixture\n", encoding="utf-8")
            order_path = write_work_order(target, target)
            run_dir = base / "runs" / "work-order"
            args = argparse.Namespace(
                target=None,
                target_option=str(target),
                work_order=str(order_path),
                profile="local-coding",
                provider="required",
                no_start_provider=True,
                run_id="work-order-full",
                run_dir=str(run_dir),
                max_minutes=4,
                yes=True,
                check=[],
                objective="",
                timeout_seconds=30,
                interval=0.01,
                foreground=False,
                create_only=True,
                json=False,
            )
            with mock.patch.object(inlet, "RUNS_ROOT", base / "runs"), mock.patch.object(
                inlet, "ensure_provider", return_value=("ready", "fixture")
            ):
                inlet.create_work_order_run(args)
            plan = {
                "leafos_object": "agent_loop_plan",
                "version": 2,
                "task_id": "WO-TEST-002",
                "steps": [
                    {"id": "read", "kind": "read_files", "paths": ["sample.txt"]},
                    {"id": "test", "kind": "run_tests", "command": [sys.executable, "--version"], "cwd": ".", "timeout_seconds": 30},
                    {"id": "hash", "kind": "record_hashes", "paths": ["sample.txt"]},
                ],
            }
            response = FakeResponse(
                [
                    (
                        "data: "
                        + json.dumps(
                            {
                                "timings": {"predicted_per_second": 42.0, "prompt_per_second": 100.0},
                                "usage": {"prompt_tokens": 20, "completion_tokens": 7},
                                "choices": [{"delta": {"content": json.dumps(plan)}}],
                            }
                        )
                        + "\n"
                    ).encode(),
                    b"data: [DONE]\n",
                ]
            )
            with mock.patch.object(inlet.urllib.request, "urlopen", return_value=response), mock.patch.object(
                work_orders.urllib.request, "urlopen", return_value=response
            ):
                self.assertEqual(0, inlet.drive_run(run_dir, interval=0.01))
            state = inlet.engine.read_json(run_dir / "state.json", {})
            queue = inlet.engine.read_json(run_dir / "queue.json", {})
            checkpoint = inlet.engine.read_json(run_dir / "checkpoint.json", {})
            self.assertEqual("complete", state["status"])
            self.assertTrue(all(task["status"] == "complete" for task in queue["tasks"]))
            self.assertEqual(2, checkpoint["version"])
            self.assertEqual("WO-TEST", checkpoint["work_order_id"])
            self.assertIn("test", checkpoint["completed_step_ids"])
            telemetry_path = run_dir / inlet.engine.UNIVERSAL_LOG_NAME
            telemetry = [json.loads(line) for line in telemetry_path.read_text(encoding="utf-8").splitlines()]
            provider_sample = next(event for event in telemetry if event["event_type"] == "sample")
            self.assertEqual(42.0, provider_sample["throughput"]["brain_generation_tk_s"])
            self.assertTrue(any(event["event_type"] == "task_end" for event in telemetry))

    def test_empty_provider_plan_exhausts_bounded_repair_without_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "repo"
            target.mkdir()
            order_path = write_work_order(target, target)
            run_dir = base / "runs" / "repair"
            args = argparse.Namespace(
                target=None,
                target_option=str(target),
                work_order=str(order_path),
                profile="local-coding",
                provider="required",
                no_start_provider=True,
                run_id="work-order-repair",
                run_dir=str(run_dir),
                max_minutes=4,
                yes=True,
                check=[],
                objective="",
                timeout_seconds=30,
                interval=0.01,
                foreground=False,
                create_only=True,
                json=False,
            )
            with mock.patch.object(inlet, "RUNS_ROOT", base / "runs"), mock.patch.object(
                inlet, "ensure_provider", return_value=("ready", "fixture")
            ):
                inlet.create_work_order_run(args)
            empty_response = FakeResponse([b"data: [DONE]\n"])
            with mock.patch.object(work_orders.urllib.request, "urlopen", return_value=empty_response):
                self.assertEqual(2, inlet.drive_run(run_dir, interval=0.01))
            state = inlet.engine.read_json(run_dir / "state.json", {})
            queue = inlet.engine.read_json(run_dir / "queue.json", {})
            plan_task = queue["tasks"][1]
            event_kinds = [event["kind"] for event in inlet.engine.read_events(run_dir)]
            self.assertEqual("blocked", state["status"])
            self.assertEqual("failed", plan_task["status"])
            self.assertEqual(2, plan_task["attempts"])
            self.assertEqual(1, event_kinds.count("repair.queued"))
            self.assertFalse((run_dir / "plan.v2.json").exists())


if __name__ == "__main__":
    unittest.main()
