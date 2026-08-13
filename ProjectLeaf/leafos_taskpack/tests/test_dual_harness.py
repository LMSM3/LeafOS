import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


HARNESS = pathlib.Path(__file__).resolve().parents[1] / "core" / "python" / "leaf_dual_harness.py"
SPEC = importlib.util.spec_from_file_location("leaf_dual_harness", HARNESS)
leaf_dual_harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(leaf_dual_harness)


def harness_config():
    return {
        "schema_version": 1,
        "run_id": "dual-harness-test",
        "workspace_allowlist": ["sandbox/overnight-01/work"],
        "lanes": {
            "experimental_brain": {
                "model": "fixture-medium-moe",
                "role": "medium_moe_qualification_lane",
                "max_concurrent": 1,
                "provider": "local",
                "context_tokens": 16384,
                "compaction_threshold_tokens": 1000,
            },
            "daily_candidate": {
                "model": "fixture-incumbent",
                "role": "incumbent_fallback",
                "max_concurrent": 1,
            },
        },
        "brain_runtime": {
            "methods": [
                {"name": "f16", "cache_type_k": "f16", "cache_type_v": "f16", "decode_tokens_per_second": 107.762078, "gpu_allocation_fraction": 0.5},
                {"name": "q8_0", "cache_type_k": "q8_0", "cache_type_v": "q8_0", "decode_tokens_per_second": 102.830487, "gpu_allocation_fraction": 0.5},
            ],
        },
        "limits": {
            "task_timeout_seconds": 10,
            "max_attempts": 2,
            "retry_backoff_seconds": 1,
            "heartbeat_seconds": 1,
            "report_interval_seconds": 60,
        },
        "safety": {
            "allow_network": False,
            "allow_install": False,
            "allow_delete": False,
            "allow_unattended_apply": False,
        },
        "chat_bridge": {
            "inbox": "chat-inbox.jsonl",
            "outbox": "chat-outbox.jsonl",
            "compaction_directory": "context-checkpoints",
        },
    }


class DualHarnessTests(unittest.TestCase):
    def make_harness_tree(self, config=None):
        tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(tmp.name)
        run_root = base / "sandbox" / "overnight-01" / "harness"
        workdir = base / "sandbox" / "overnight-01" / "work" / "task"
        workdir.mkdir(parents=True)
        harness = leaf_dual_harness.Harness(run_root, config or harness_config())
        return tmp, base, run_root, workdir, harness

    def test_pause_resume_commands_are_persistent(self):
        tmp, _base, _run_root, _workdir, harness = self.make_harness_tree()
        with tmp:
            harness.post("pause")
            harness.tick()
            self.assertTrue(harness.state["paused"])

            harness.post("resume")
            harness.tick()
            self.assertFalse(harness.state["paused"])

            reloaded = leaf_dual_harness.Harness(harness.root, harness.config)
            self.assertFalse(reloaded.state["paused"])

    def test_allowlisted_task_runs_inside_staged_work_tree(self):
        tmp, _base, _run_root, workdir, harness = self.make_harness_tree()
        with tmp:
            harness.state["tasks"].append({
                "id": "ok-task",
                "state": "queued",
                "workdir": str(workdir),
                "command": [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('done.json').write_text('{\"ok\": true}', encoding='utf-8')",
                ],
            })
            harness.tick()
            self.assertEqual(harness.state["tasks"][0]["state"], "completed")
            self.assertTrue((workdir / "done.json").is_file())

    def test_task_outside_allowlist_is_blocked(self):
        tmp, base, _run_root, _workdir, harness = self.make_harness_tree()
        with tmp:
            outside = base / "outside"
            outside.mkdir()
            harness.state["tasks"].append({
                "id": "bad-task",
                "state": "queued",
                "workdir": str(outside),
                "command": [sys.executable, "-c", "print('should not run')"],
            })
            harness.tick()
            self.assertEqual(harness.state["tasks"][0]["state"], "blocked")
            self.assertEqual(harness.state["tasks"][0]["reason"], "workspace_not_allowlisted")

    def test_context_compaction_writes_checkpoint(self):
        config = harness_config()
        config["lanes"]["experimental_brain"]["compaction_threshold_tokens"] = 2
        tmp, _base, _run_root, _workdir, harness = self.make_harness_tree(config)
        with tmp:
            harness.post("a long enough message to compact")
            harness.tick()
            checkpoint = pathlib.Path(harness.state["latest_context_checkpoint"])
            self.assertTrue(checkpoint.is_file())
            self.assertIn("fixture-medium-moe Context Compaction", checkpoint.read_text(encoding="utf-8"))
            self.assertEqual(harness.state["brain_method"], "q8_0")

    def test_failure_switches_runtime_method_and_exports_it(self):
        tmp, _base, _run_root, workdir, harness = self.make_harness_tree()
        with tmp:
            harness.state["tasks"].append({"id": "fail-task", "state": "queued", "workdir": str(workdir), "command": [sys.executable, "-c", "import os, sys; assert os.environ['LEAF_BRAIN_METHOD'] == 'f16'; sys.exit(1)"]})
            harness.tick()
            self.assertEqual(harness.state["brain_method"], "q8_0")
            self.assertEqual(harness.state["brain_switches"], 1)

    def test_clear_command_switches_runtime_method(self):
        tmp, _base, _run_root, _workdir, harness = self.make_harness_tree()
        with tmp:
            harness.post("clear conversation")
            harness.tick()
            self.assertEqual(harness.state["brain_method"], "q8_0")
            self.assertEqual(harness.state["conversation_clears"], 1)

    def test_agent_loop_queue_is_shared_instead_of_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            target = base / "Games"
            workdir = target / "generic-python-sim"
            run_dir = base / "agent-loop-run"
            workdir.mkdir(parents=True)
            run_dir.mkdir()
            (run_dir / "run.json").write_text(
                json.dumps({"run_id": "loop-01", "target": str(target)}), encoding="utf-8"
            )
            (run_dir / "queue.json").write_text(
                json.dumps({
                    "leafos_object": "agent_loop_queue",
                    "version": 1,
                    "run_id": "loop-01",
                    "tasks": [{
                        "task_id": "001-shared",
                        "status": "queued",
                        "workdir": str(workdir),
                        "validation_command": [
                            sys.executable,
                            "-c",
                            "from pathlib import Path; Path('shared-done.txt').write_text('ok', encoding='utf-8')",
                        ],
                        "timeout_seconds": 10,
                        "attempts": 0,
                    }],
                }),
                encoding="utf-8",
            )
            (run_dir / "events.jsonl").write_text("", encoding="utf-8")
            config = harness_config()
            config["agent_loop_run_dir"] = str(run_dir)
            harness = leaf_dual_harness.Harness(base / "harness", config)
            harness.tick()

            queue = json.loads((run_dir / "queue.json").read_text(encoding="utf-8"))
            persisted = json.loads((harness.state_path).read_text(encoding="utf-8"))
            self.assertEqual("complete", queue["tasks"][0]["status"])
            self.assertTrue((workdir / "shared-done.txt").is_file())
            self.assertNotIn("tasks", persisted)
            self.assertEqual("agent_loop_queue", persisted["task_source"])
            self.assertIn("dual_harness.task.completed", (run_dir / "events.jsonl").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
