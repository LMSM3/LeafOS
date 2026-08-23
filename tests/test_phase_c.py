from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
os.sys.path.insert(0, str(ROOT))

from core.config import Settings
from core.control.scheduler import Scheduler, observe_resources
from core.control.store import ControlError, ProjectStore


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


def settings(root: Path) -> Settings:
    return Settings(root, (root / "models",), "not-used", 4096, None)


def planned_scheduler(root: Path, workers: int = 2) -> tuple[ProjectStore, Scheduler]:
    store = ProjectStore(root)
    store.initialize("Phase C bounded scheduler")
    scheduler = Scheduler(settings(root), root)
    scheduler.initialize(workers, 30)
    return store, scheduler


class PhaseCSchedulerTests(unittest.TestCase):
    def test_two_independent_tasks_claim_concurrently_while_dependency_waits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, scheduler = planned_scheduler(root)
            first = store.create_task("first", "fast")
            second = store.create_task("second", "fast")
            dependent = store.create_task("dependent", "fast", dependencies=[first["id"]])
            started = []

            def claim(task, slot, kind, lease_seconds):
                token = f"token-{slot}"
                store.claim_task(
                    task["id"], worker_id=slot, slot=slot, pid=os.getpid(),
                    lease_seconds=lease_seconds, token=token,
                )
                started.append((slot, task["id"]))

            with (
                patch("core.control.scheduler.observe_resources", return_value=SAFE_RESOURCES),
                patch.object(scheduler, "_role_status", return_value=({}, ["optional verifier role unavailable"])),
                patch.object(scheduler, "_spawn", side_effect=claim),
            ):
                result = scheduler.tick()
            self.assertEqual({first["id"], second["id"]}, {task_id for _, task_id in started})
            self.assertEqual(2, len(result["started"]))
            self.assertEqual("planned", store.get_task(dependent["id"])["status"])
            self.assertEqual({"worker-1", "worker-2"}, {slot for slot, _ in started})

    def test_priority_order_is_contractual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, scheduler = planned_scheduler(root)
            ids = {}
            for schedule_class in ("compression", "speculative", "verifier", "critical", "interactive"):
                ids[schedule_class] = store.create_task(
                    schedule_class, "fast", schedule_class=schedule_class, priority=50
                )["id"]
            ordered = scheduler._ready_tasks(store.load_taskgraph(), False)
            self.assertEqual(
                [ids[value] for value in ("interactive", "critical", "verifier", "speculative", "compression")],
                [task["id"] for task in ordered],
            )

    def test_foreground_preempts_background_and_blocks_new_background_claims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, scheduler = planned_scheduler(root)
            background = store.create_task("background", "fast", schedule_class="speculative")
            token = "background-token"
            store.claim_task(
                background["id"], worker_id="worker:worker-1", slot="worker-1",
                pid=os.getpid(), lease_seconds=30, token=token,
            )
            process = Mock()
            process.poll.return_value = None
            scheduler.children["worker-1"] = {
                "process": process,
                "task_id": background["id"],
                "token": token,
                "kind": "worker",
                "schedule_class": "speculative",
            }
            scheduler.set_foreground(True)
            with (
                patch("core.control.scheduler.observe_resources", return_value=SAFE_RESOURCES),
                patch.object(scheduler, "_role_status", return_value=({}, [])),
            ):
                result = scheduler.tick()
            process.terminate.assert_called_once()
            self.assertEqual([background["id"]], result["preempted"])
            self.assertEqual("ready", store.get_task(background["id"])["status"])
            self.assertEqual([], result["started"])

    def test_real_worker_process_death_requeues_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, _ = planned_scheduler(root)
            task = store.create_task("survive worker death", "fast", attempts=2)
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                store.claim_task(
                    task["id"], worker_id="worker:worker-1", slot="worker-1",
                    pid=child.pid, lease_seconds=30, token="death-token",
                )
                child.terminate()
                child.wait(timeout=10)
                self.assertEqual([task["id"]], store.recover())
                self.assertEqual([], store.recover())
                recovered = store.get_task(task["id"])
                self.assertEqual("ready", recovered["status"])
                self.assertEqual(1, recovered["attempt"])
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()

    def test_ownership_token_prevents_second_writer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, _ = planned_scheduler(root)
            task = store.create_task("owned artifact", "fast")
            claimed = store.claim_task(task["id"], worker_id="one", slot="worker-1", token="owner-one")
            self.assertEqual("owner-one", claimed["lease"]["token"])
            result = {
                "return_code": 0,
                "stdout": "result",
                "stderr": "",
                "response": "result",
                "started_at": "2026-08-20T00:00:00+00:00",
                "finished_at": "2026-08-20T00:00:01+00:00",
            }
            with self.assertRaisesRegex(ControlError, "lease token"):
                store.finalize_execution(
                    task["id"], result, lane="fast",
                    model={"id": "unit-model", "path": "unused", "architecture": "unit", "quant": "unit"},
                    lease_token="owner-two",
                )
            self.assertFalse((root / ".leaf" / "tasks" / task["id"] / "worker-output.txt").exists())

    def test_atomic_claim_allows_only_one_contending_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, _ = planned_scheduler(root)
            task = store.create_task("contended", "fast")
            barrier = threading.Barrier(2)
            outcomes = []

            def contend(name: str) -> None:
                barrier.wait()
                try:
                    store.claim_task(task["id"], worker_id=name, slot=name, token=name)
                    outcomes.append("claimed")
                except ControlError:
                    outcomes.append("rejected")

            threads = [threading.Thread(target=contend, args=(name,)) for name in ("worker-1", "worker-2")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertCountEqual(outcomes, ["claimed", "rejected"])

    def test_cancellation_terminates_process_and_does_not_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, scheduler = planned_scheduler(root)
            task = store.create_task("cancel me", "fast", attempts=3)
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                store.claim_task(
                    task["id"], worker_id="worker:worker-1", slot="worker-1",
                    pid=child.pid, token="cancel-token",
                )
                cancelled = scheduler.cancel(task["id"], "operator cancelled")
                child.wait(timeout=10)
                self.assertEqual("cancelled", cancelled["status"])
                self.assertTrue(cancelled["cancellation_requested"])
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()

    def test_unavailable_gpu_and_thermal_sensors_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("core.control.scheduler.shutil.which", return_value=None):
            resources = observe_resources(Path(directory), {"ready": 2})
            for key in ("gpu_percent", "vram_used_gb", "vram_total_gb", "vram_percent", "thermal_c"):
                self.assertEqual("unavailable", resources[key])
            self.assertEqual("unavailable", resources["disk_throughput_mb_s"])
            self.assertEqual({"ready": 2}, resources["queue"])

    def test_scheduler_state_integrity_and_slot_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, scheduler = planned_scheduler(root, workers=4)
            self.assertEqual(4, scheduler.status()["policy"]["worker_slots"])
            with self.assertRaisesRegex(ControlError, "between 2 and 4"):
                scheduler.initialize(5, 30)
            state_path = root / ".leaf" / "state" / "scheduler.json"
            text = state_path.read_text(encoding="utf-8").replace('"worker_slots": 4', '"worker_slots": 3')
            state_path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ControlError, "integrity"):
                scheduler.status()


if __name__ == "__main__":
    unittest.main()

