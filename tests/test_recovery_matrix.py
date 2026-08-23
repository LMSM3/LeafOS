from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
os.sys.path.insert(0, str(ROOT))

from core.control.store import ControlError, ProjectStore, _FileLock


def successful_result(response: str = "RECOVERY_OK") -> dict[str, object]:
    return {
        "return_code": 0,
        "stdout": f"raw process output\n> prompt\n{response}\nExiting...\n",
        "stderr": "",
        "response": response,
        "started_at": "2026-08-19T00:00:00+00:00",
        "finished_at": "2026-08-19T00:00:01+00:00",
    }


MODEL = {
    "id": "stubbed-recovery-model",
    "path": "not-executed-by-recovery-tests",
    "architecture": "test-only",
    "quant": "test-only",
}


class PhaseARecoveryMatrix(unittest.TestCase):
    def test_R01_restart_after_objective_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            ProjectStore(project).initialize("Recovery matrix")
            restarted = ProjectStore(project)
            self.assertEqual(restarted.load_objective()["text"], "Recovery matrix")
            self.assertEqual(restarted.load_taskgraph()["tasks"], {})

    def test_R02_restart_after_ready_task_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            store = ProjectStore(project)
            store.initialize("Recovery matrix")
            task = store.create_task("Ready boundary", "fast")
            self.assertEqual(ProjectStore(project).get_task(task["id"])["status"], "ready")

    def test_R03_restart_while_current_live_lease_is_running(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            store = ProjectStore(project)
            store.initialize("Recovery matrix")
            task = store.create_task("Running boundary", "fast")
            store.claim_task(task["id"])
            self.assertEqual(ProjectStore(project).get_task(task["id"])["status"], "running")

    def test_R04_real_worker_process_death_requeues_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            script = (
                "from pathlib import Path\n"
                "import sys\n"
                "from core.control.store import ProjectStore\n"
                "store=ProjectStore(Path(sys.argv[1]))\n"
                "store.initialize('Child death')\n"
                "task=store.create_task('Abandoned by child','fast',attempts=2)\n"
                "store.claim_task(task['id'])\n"
            )
            environment = dict(os.environ)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            completed = subprocess.run(
                [sys.executable, "-c", script, str(project)],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            restarted = ProjectStore(project)
            self.assertEqual(restarted.recover(), ["task-000001"])
            task = restarted.get_task("task-000001")
            self.assertEqual(task["status"], "ready")
            self.assertEqual(task["attempt"], 1)

    def test_R05_dead_worker_at_attempt_limit_fails_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory))
            store.initialize("Recovery matrix")
            task = store.create_task("One attempt only", "fast", attempts=1)
            store.claim_task(task["id"])
            with patch("core.control.store._pid_alive", return_value=False):
                self.assertEqual(store.recover(), [task["id"]])
            failed = store.get_task(task["id"])
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["attempt"], 1)
            self.assertEqual(store.recover(), [])

    def test_R06_crash_before_first_artifact_write_recovers_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            store = ProjectStore(project)
            store.initialize("Recovery matrix")
            task = store.create_task("Crash before artifact", "fast", attempts=2)
            store.claim_task(task["id"])
            with patch.object(store, "_atomic_text", side_effect=OSError("injected artifact failure")):
                with self.assertRaisesRegex(OSError, "injected artifact"):
                    store.finalize_execution(task["id"], successful_result(), lane="fast", model=MODEL)
            with patch("core.control.store._pid_alive", return_value=False):
                ProjectStore(project).recover()
            recovered = ProjectStore(project).get_task(task["id"])
            self.assertEqual(recovered["status"], "ready")
            self.assertEqual(recovered["evidence"], [])

    def test_R07_crash_after_evidence_before_graph_commit_retries_without_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            store = ProjectStore(project)
            store.initialize("Recovery matrix")
            task = store.create_task("Crash before graph", "fast", attempts=2)
            store.claim_task(task["id"])
            original_write = store._write_document

            def fail_result_graph(path: Path, value: dict[str, object]) -> dict[str, object]:
                if path == store.taskgraph_path and value.get("tasks", {}).get(task["id"], {}).get("status") == "verifying":
                    raise OSError("injected graph failure")
                return original_write(path, value)

            with patch.object(store, "_write_document", side_effect=fail_result_graph):
                with self.assertRaisesRegex(OSError, "injected graph"):
                    store.finalize_execution(task["id"], successful_result("FIRST"), lane="fast", model=MODEL)
            self.assertTrue((store.evidence_dir / "evidence-000001.json").is_file())
            with patch("core.control.store._pid_alive", return_value=False):
                ProjectStore(project).recover()
            retry = ProjectStore(project)
            retry.claim_task(task["id"])
            completed = retry.finalize_execution(task["id"], successful_result("SECOND"), lane="fast", model=MODEL)
            self.assertEqual(completed["status"], "verifying")
            self.assertEqual(completed["evidence"], ["evidence-000001"])
            self.assertEqual(retry.audit()["evidence"], 1)
            self.assertEqual((project / completed["output"]["path"]).read_text(encoding="utf-8"), "SECOND")

    def test_R08_crash_after_graph_before_journal_keeps_committed_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            store = ProjectStore(project)
            store.initialize("Recovery matrix")
            task = store.create_task("Crash after graph", "fast")
            store.claim_task(task["id"])
            with patch.object(store, "_journal", side_effect=OSError("injected journal failure")):
                with self.assertRaisesRegex(OSError, "injected journal"):
                    store.finalize_execution(task["id"], successful_result(), lane="fast", model=MODEL)
            restarted = ProjectStore(project)
            committed = restarted.get_task(task["id"])
            self.assertEqual(committed["status"], "verifying")
            self.assertEqual(committed["evidence"], ["evidence-000001"])
            self.assertEqual(restarted.audit()["evidence"], 1)

    def test_R09_atomic_replace_failure_preserves_previous_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory))
            store.initialize("Recovery matrix")
            before = store.objective_path.read_bytes()
            changed = dict(store.load_objective())
            changed["text"] = "must not commit"
            with patch("core.control.store.os.replace", side_effect=OSError("injected replace failure")):
                with self.assertRaisesRegex(OSError, "injected replace"):
                    store._write_document(store.objective_path, changed)
            self.assertEqual(store.objective_path.read_bytes(), before)
            self.assertEqual(store.load_objective()["text"], "Recovery matrix")

    def test_R10_partial_state_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory))
            store.initialize("Recovery matrix")
            store.taskgraph_path.unlink()
            with self.assertRaisesRegex(ControlError, "not initialized|partial"):
                store.initialize("Recovery matrix")

    def test_R11_corrupt_graph_fails_integrity_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory))
            store.initialize("Recovery matrix")
            graph = json.loads(store.taskgraph_path.read_text(encoding="utf-8"))
            graph["next_task"] = 999
            store.taskgraph_path.write_text(json.dumps(graph), encoding="utf-8")
            with self.assertRaisesRegex(ControlError, "integrity"):
                store.load_taskgraph()

    def test_R12_live_lock_cannot_be_stolen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "control.lock"
            with _FileLock(lock_path, timeout_seconds=0.05):
                with self.assertRaisesRegex(ControlError, "locked"):
                    with _FileLock(lock_path, timeout_seconds=0.05):
                        self.fail("a live lock was stolen")

    def test_R13_dead_lock_is_reclaimed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "control.lock"
            lock_path.write_text(json.dumps({"pid": 2_147_483_647}), encoding="utf-8")
            with patch("core.control.store._pid_alive", return_value=False):
                with _FileLock(lock_path, timeout_seconds=0.1):
                    self.assertTrue(lock_path.is_file())
            self.assertFalse(lock_path.exists())

    def test_R14_corrupt_journal_blocks_integrity_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory))
            store.initialize("Recovery matrix")
            with store.journal_path.open("a", encoding="utf-8") as stream:
                stream.write("{not-json}\n")
            with self.assertRaisesRegex(ControlError, "append-only"):
                store.audit()


if __name__ == "__main__":
    unittest.main()

