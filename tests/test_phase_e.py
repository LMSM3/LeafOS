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

from core.cli import build_parser
from core.config import Settings
from core.control.recovery import RecoveryManager
from core.control.scheduler import Scheduler
from core.control.store import ControlError, ProjectStore, _pid_alive


SAFE_RESOURCES = {
    "observed_at": "2026-08-20T00:00:00+00:00",
    "cpu_percent": 20.0,
    "ram_used_gb": 8.0,
    "ram_total_gb": 32.0,
    "ram_percent": 25.0,
    "gpu_percent": "unavailable",
    "vram_used_gb": "unavailable",
    "vram_total_gb": "unavailable",
    "vram_percent": "unavailable",
    "thermal_c": "unavailable",
    "queue": {},
    "disk_free_gb": 100.0,
    "disk_total_gb": 200.0,
    "disk_throughput_mb_s": "unavailable",
    "kv_cache_gb": "unavailable",
    "sensor_policy": "observed values only",
}

WORKER_MODEL = {"id": "phase-e-worker", "path": "worker.gguf", "architecture": "unit", "quant": "Q4"}
VERIFIER_MODEL = {"id": "phase-e-verifier", "path": "verifier.gguf", "architecture": "unit", "quant": "Q4"}


def settings(root: Path) -> Settings:
    return Settings(root, (root / "models",), "not-used", 4096, None)


def result(response: str) -> dict[str, object]:
    return {
        "return_code": 0,
        "stdout": response,
        "stderr": "",
        "response": response,
        "started_at": "2026-08-20T00:00:00+00:00",
        "finished_at": "2026-08-20T00:00:01+00:00",
    }


def accepted_task(store: ProjectStore) -> dict[str, object]:
    (store.project_root / "facts.md").write_text("The retained value is source-backed.\n", encoding="utf-8")
    task = store.create_task("retain accepted evidence", "fast", input_paths=["facts.md"])
    sources = store.source_contents(task)
    claimed = store.claim_task(str(task["id"]), token="phase-e-owner")
    completed = store.finalize_execution(
        str(task["id"]),
        result("source-backed result"),
        lane="fast",
        model=WORKER_MODEL,
        input_sources=sources,
        lease_token=str(claimed["lease"]["token"]),
    )
    evidence_id = str(completed["evidence"][0])
    verdict = {
        "verdict": "accept",
        "confidence": "high",
        "claims": [{"text": "result is retained", "evidence_ids": [evidence_id]}],
        "contradictions": [],
    }
    store.record_verification(
        str(task["id"]), result(json.dumps(verdict)), verdict, lane="verifier", model=VERIFIER_MODEL
    )
    return store.accept_task(str(task["id"]), "independent evidence passed")


class PhaseEProcessRecoveryTests(unittest.TestCase):
    def test_boot_session_mismatch_requeues_without_trusting_reused_pid(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "core.control.store._host_session_id", return_value="session-current"
        ):
            root = Path(directory)
            store = ProjectStore(root)
            store.initialize("boot-scoped recovery")
            task = store.create_task("resume after WSL restart", "fast", attempts=2)
            store.claim_task(str(task["id"]), pid=os.getpid(), token="boot-token")
            graph = store.load_taskgraph()
            graph["tasks"][task["id"]]["lease"]["host_session_id"] = "session-previous"
            store._write_document(store.taskgraph_path, graph)
            self.assertEqual([task["id"]], store.recover())
            self.assertEqual("ready", store.get_task(str(task["id"]))["status"])

    def test_orphan_runtime_is_terminated_when_worker_is_dead(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ProjectStore(root)
            store.initialize("orphan model recovery")
            task = store.create_task("kill orphaned model", "fast", attempts=2)
            runtime = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                store.claim_task(str(task["id"]), pid=999_999_999, token="orphan-token")
                store.bind_runtime_process(str(task["id"]), "orphan-token", runtime.pid)
                self.assertEqual([task["id"]], store.recover())
                runtime.wait(timeout=10)
                self.assertFalse(_pid_alive(runtime.pid))
                self.assertEqual("ready", store.get_task(str(task["id"]))["status"])
            finally:
                if runtime.poll() is None:
                    runtime.kill()
                    runtime.wait()

    def test_clean_stop_terminates_worker_and_model_processes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ProjectStore(root)
            store.initialize("clean tree shutdown")
            scheduler = Scheduler(settings(root), root)
            scheduler.initialize()
            task = store.create_task("stop every owned process", "fast", attempts=2)
            worker = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            runtime = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                store.claim_task(str(task["id"]), pid=worker.pid, token="stop-token")
                store.bind_runtime_process(str(task["id"]), "stop-token", runtime.pid)
                stopped = scheduler.stop()
                worker.wait(timeout=10)
                runtime.wait(timeout=10)
                self.assertEqual([task["id"]], stopped["tasks"])
                self.assertFalse(_pid_alive(worker.pid))
                self.assertFalse(_pid_alive(runtime.pid))
                self.assertEqual("ready", store.get_task(str(task["id"]))["status"])
            finally:
                for process in (worker, runtime):
                    if process.poll() is None:
                        process.kill()
                        process.wait()


class PhaseECheckpointTests(unittest.TestCase):
    def test_checkpoint_keeps_append_only_prefix_and_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ProjectStore(root)
            store.initialize("immutable recovery checkpoint")
            manager = RecoveryManager(settings(root), root)
            manager.initialize(hours=1 / 3600, sample_seconds=0.05)
            manifest = manager.checkpoint("initial durable state")
            store._journal("test.after_checkpoint")
            verified = manager.verify_checkpoint(str(manifest["id"]))
            self.assertEqual(manifest["id"], verified["manifest"]["id"])
            snapshot = root / ".leaf" / "checkpoints" / str(manifest["id"]) / "snapshot.json"
            snapshot.write_text(snapshot.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(ControlError, "integrity"):
                manager.verify_checkpoint(str(manifest["id"]))

    def test_recovery_preserves_one_evidence_linked_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ProjectStore(root)
            store.initialize("accepted state survives")
            accepted = accepted_task(store)
            manager = RecoveryManager(settings(root), root)
            manager.initialize(hours=1 / 3600, sample_seconds=0.05)
            manager.checkpoint("accepted baseline")
            recovered = manager.recover()
            self.assertEqual(1, recovered["accepted"])
            self.assertEqual("accepted", store.get_task(str(accepted["id"]))["status"])
            decisions = [
                value for value in store._read_records(store.decisions_path)
                if value.get("kind") == "acceptance" and value.get("task_id") == accepted["id"]
            ]
            self.assertEqual(1, len(decisions))
            self.assertTrue(decisions[0]["verifier_evidence"])
            self.assertTrue(decisions[0]["claims"][0]["evidence_ids"])


class PhaseESoakTests(unittest.TestCase):
    def test_release_fault_cannot_be_self_reported_without_audit_proof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ProjectStore(root)
            store.initialize("proof-bound fault ledger")
            manager = RecoveryManager(settings(root), root)
            manager.initialize(hours=1 / 3600, sample_seconds=0.05)
            with self.assertRaisesRegex(ControlError, "without post-soak"):
                manager.record_fault("tool-failure", "passed", "unproven claim")
            observed = manager.record_fault("tool-failure", "observed", "pending a controller evidence record")
            self.assertFalse(observed["verified"])

    def test_soak_pauses_resumes_and_records_resource_latency_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ProjectStore(root)
            store.initialize("short deterministic soak")
            manager = RecoveryManager(settings(root), root)
            with (
                patch("core.control.scheduler.observe_resources", return_value=SAFE_RESOURCES),
                patch.object(manager.scheduler, "_role_status", return_value=({}, ["active pack unavailable"])),
            ):
                first = manager.run(hours=1 / 3600, sample_seconds=0.05, max_samples=2)
                self.assertEqual("paused", first["status"])
                self.assertEqual(2, first["telemetry"]["records"])
                state = manager._load()
                state["status"] = "running"
                state["owner"] = {"pid": 999_999_999, "host_session_id": "previous-session"}
                manager._save(state)
                second = manager.run(hours=1 / 3600, sample_seconds=0.05, max_samples=1)
            self.assertEqual("paused", second["status"])
            self.assertEqual(1, second["resume_count"])
            self.assertEqual(3, second["telemetry"]["records"])
            self.assertIsNotNone(second["telemetry"]["tick_ms_median"])
            self.assertIsNotNone(second["latest_checkpoint"])

    def test_cli_exposes_recovery_as_bounded_swarm_actions(self) -> None:
        parser = build_parser()
        soak = parser.parse_args(["swarm", "soak", "--hours", "6", "--sample-seconds", "30"])
        recover = parser.parse_args(["swarm", "recover"])
        checkpoint = parser.parse_args(["swarm", "checkpoint", "--reason", "epoch boundary"])
        fault = parser.parse_args(
            ["swarm", "fault", "--kind", "worker-kill", "--outcome", "passed", "--detail", "lease recovered"]
        )
        self.assertEqual(6.0, soak.hours)
        self.assertEqual("recover", recover.swarm_command)
        self.assertEqual("epoch boundary", checkpoint.reason)
        self.assertEqual("worker-kill", fault.kind)


if __name__ == "__main__":
    unittest.main()
