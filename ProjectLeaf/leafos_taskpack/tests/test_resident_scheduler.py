from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from core.python import leaf_foreground_activity as activity
from core.python import leaf_live_project as live
from core.python import leaf_resident_supervisor as resident
from core.python import leaf_work_order as work_orders


def hardware(cpu=25.0, gpu=40.0):
    return {
        "hardware": {
            "cpu": {"utilization_percent": cpu, "process_percent": 5.0},
            "gpu": {
                "utilization_percent": gpu, "vram_used_gb": 5.0, "vram_total_gb": 12.0,
                "temperature_celsius": 60.0, "power_watts": 100.0,
            },
            "memory": {"ram_used_gb": 10.0, "ram_total_gb": 32.0},
            "io": {"nvme_read_mb_s": None, "nvme_write_mb_s": None, "read_latency_ms": None, "write_latency_ms": None},
            "power": {"total_watts": 100.0, "energy_watt_hours": None, "tokens_per_watt_hour": None},
            "backend": "vulkan",
        },
        "availability": {},
    }


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class ResidentSchedulerTests(unittest.TestCase):
    def make_run(self, root: Path) -> Path:
        target = root / "project"
        runs = root / "runs"
        with mock.patch.object(live.inlet, "RUNS_ROOT", runs), mock.patch.object(
            live.inlet, "LIVE_INTAKE_ROOT", runs / "live-intake"
        ):
            result = live.start_project(
                target, create_seed=True, template="generic", provider="off", fresh_run=True,
                spawn=False, run_dir=str(root / "run"),
            )
        return Path(result["run_dir"])

    def test_resident_refills_completed_live_queue_and_starts_worker_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self.make_run(root)
            queue = live.engine.read_json(run_dir / "queue.json", {})
            for task in queue["tasks"]:
                task["status"] = "complete"
            live.engine.write_json(run_dir / "queue.json", queue)
            state = live.engine.read_json(run_dir / "state.json", {})
            state["status"] = "complete"
            live.engine.write_json(run_dir / "state.json", state)
            policy = ROOT_POLICY = Path(resident.ROOT / "config" / "resident-stack-policy.json")
            resident.initialize_resident(run_dir, policy_path=policy)
            spawned = []
            clock = FakeClock()
            supervisor = resident.ResidentSupervisor(
                run_dir, collector=lambda **_kwargs: hardware(), input_probe=lambda: 60.0, clock=clock,
                worker_spawner=lambda _run, _interval: spawned.append(4321) or 4321,
            )
            with mock.patch.object(resident, "_pid_alive", return_value=False):
                result = supervisor.tick_once()
            queue = live.engine.read_json(run_dir / "queue.json", {})
            generated = [task for task in queue["tasks"] if task.get("admission_source") == "resident"]
            self.assertEqual(1, len(generated))
            self.assertEqual([4321], spawned)
            self.assertEqual(1, result["usage"]["iterations_generated"])

    def test_existing_worker_prevents_duplicate_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.make_run(Path(temporary))
            resident.initialize_resident(run_dir)
            live.engine.write_json(run_dir / "worker.lock", {"pid": 999, "started_utc": resident.utc_now()})
            spawned = []
            supervisor = resident.ResidentSupervisor(
                run_dir, collector=lambda **_kwargs: hardware(), input_probe=lambda: 60.0,
                worker_spawner=lambda _run, _interval: spawned.append(1) or 1,
            )
            with mock.patch.object(resident, "_pid_alive", return_value=True):
                supervisor.tick_once()
            self.assertEqual([], spawned)

    def test_worker_obeys_resident_claim_gate_at_task_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.make_run(Path(temporary))
            state = resident.initialize_resident(run_dir)
            state["last_decision"] = {
                "profile": "pressure", "reason": "ram_pressure", "claim_allowed": False,
            }
            live.engine.write_json(run_dir / resident.STATE_NAME, state)

            self.assertEqual(2, live.inlet.drive_run(run_dir, interval=0.01))

            events = live.engine.read_events(run_dir)
            self.assertTrue(any(event["kind"] == "worker.claim_deferred" for event in events))
            self.assertFalse(any(event["kind"] == "task.started" for event in events))

    def test_worker_spawn_reuses_live_owned_lease(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.make_run(Path(temporary))
            live.engine.write_json(run_dir / "worker.lock", {"pid": 2468, "started_utc": resident.utc_now()})
            with mock.patch.object(live.inlet, "_pid_alive", return_value=True), mock.patch.object(
                live.inlet.subprocess, "Popen",
            ) as popen:
                pid = live.inlet.spawn_worker(run_dir, 1.0)
            self.assertEqual(2468, pid)
            popen.assert_not_called()

    def test_recent_dead_worker_heartbeat_holds_lease_during_handoff(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.make_run(Path(temporary))
            live.engine.write_json(run_dir / "worker.lock", {
                "pid": 2468, "started_utc": resident.utc_now(), "heartbeat_utc": resident.utc_now(),
            })
            with mock.patch.object(live.inlet, "_pid_alive", return_value=False), mock.patch.object(
                live.inlet.subprocess, "Popen",
            ) as popen:
                pid = live.inlet.spawn_worker(run_dir, 1.0)
            self.assertEqual(2468, pid)
            popen.assert_not_called()

    def test_stale_dead_worker_heartbeat_releases_lease(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.make_run(Path(temporary))
            old = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
            live.engine.write_json(run_dir / "worker.lock", {
                "pid": 2468, "started_utc": old, "heartbeat_utc": old,
            })
            process = mock.Mock(pid=9753)
            with mock.patch.object(live.inlet, "_pid_alive", return_value=False), mock.patch.object(
                live.inlet.subprocess, "Popen", return_value=process,
            ):
                pid = live.inlet.spawn_worker(run_dir, 1.0)
            self.assertEqual(9753, pid)
            self.assertEqual(9753, live.engine.read_json(run_dir / "worker.lock", {})["pid"])

    def test_worker_persistence_preserves_task_admitted_from_stale_queue(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.make_run(Path(temporary))
            stale = live.engine.read_json(run_dir / "queue.json", {})
            active = stale["tasks"][0]
            active["status"] = "executing"
            admitted = live.queue_improvement(run_dir, "add a bounded trading rule", spawn=False)
            active["status"] = "complete"
            work_orders._persist_task(run_dir, stale, active)
            latest = live.engine.read_json(run_dir / "queue.json", {})
            self.assertIn(admitted["task"]["task_id"], {task["task_id"] for task in latest["tasks"]})
            self.assertEqual("complete", next(task for task in latest["tasks"] if task["task_id"] == active["task_id"])["status"])

    def test_budget_exhaustion_fails_to_awaiting_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.make_run(Path(temporary))
            state = resident.initialize_resident(run_dir)
            state["budgets"]["max_iterations"] = 1
            state["usage"]["iterations_generated"] = 1
            live.engine.write_json(run_dir / resident.STATE_NAME, state)
            supervisor = resident.ResidentSupervisor(run_dir, collector=lambda **_kwargs: hardware(), input_probe=lambda: 60.0)
            with mock.patch.object(resident, "_pid_alive", return_value=False):
                result = supervisor.tick_once()
            self.assertEqual("awaiting_budget", result["status"])
            self.assertEqual("iteration_budget_exhausted", result["last_decision"]["reason"])

    def test_typed_mode_target_and_budget_controls_are_durable(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.make_run(Path(temporary))
            resident.initialize_resident(run_dir)
            resident.set_resident_control(run_dir, "mode", mode="quiet")
            resident.set_resident_control(run_dir, "targets", cpu=70, gpu=85)
            result = resident.set_resident_control(run_dir, "budget", minutes=120)
            self.assertEqual("quiet", result["mode"])
            self.assertEqual({"cpu_percent": 70.0, "gpu_percent": 85.0}, result["targets_override"])
            self.assertEqual(120, result["budgets"]["unattended_minutes"])
            self.assertTrue((run_dir / "control.lmem").is_file())

    def test_live_window_commands_reach_resident_control_without_shell(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.make_run(Path(temporary))
            resident.initialize_resident(run_dir)
            mode = live.execute_active_command(":mode quiet", run_dir, spawn=False)
            targets = live.execute_active_command(":targets cpu 72 gpu 88", run_dir, spawn=False)
            budget = live.execute_active_command(":budget 8m", run_dir, spawn=False)
            self.assertEqual("quiet", mode["resident"]["mode"])
            self.assertEqual(72.0, targets["resident"]["targets_override"]["cpu_percent"])
            self.assertEqual(8, budget["resident"]["budgets"]["unattended_minutes"])

    def test_provider_recovery_uses_bounded_backoff(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.make_run(Path(temporary))
            run = live.engine.read_json(run_dir / "run.json", {})
            run.update(provider_mode="required", provider_endpoint="http://127.0.0.1:1", provider_status="degraded")
            live.engine.write_json(run_dir / "run.json", run)
            resident.initialize_resident(run_dir)
            attempts = []
            clock = FakeClock()
            supervisor = resident.ResidentSupervisor(
                run_dir, collector=lambda **_kwargs: hardware(), input_probe=lambda: 60.0, clock=clock,
                provider_refresher=lambda _mode: attempts.append(clock.value) or ("degraded", "fixture unavailable"),
                worker_spawner=lambda _run, _interval: 0,
            )
            with mock.patch.object(resident.inlet, "provider_healthy", return_value=False), mock.patch.object(resident, "_pid_alive", return_value=False):
                supervisor.tick_once()
                clock.value = 1
                supervisor.tick_once()
                clock.value = 6
                supervisor.tick_once()
            self.assertEqual([0.0, 6], attempts)
            state = live.engine.read_json(run_dir / resident.STATE_NAME, {})
            self.assertEqual(2, state["provider_recovery"]["attempts"])

    def test_responsiveness_probe_reports_only_excess_wakeup_delay(self):
        clock = FakeClock()
        probe = activity.ResponsivenessProbe(1.0, clock)
        clock.value = 1.05
        self.assertAlmostEqual(50.0, probe.sample(), places=2)
        clock.value = 2.0
        self.assertEqual(0.0, probe.sample())

    def test_resident_state_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.make_run(Path(temporary))
            resident.initialize_resident(run_dir, mode="auto", budget_minutes=8)
            payload = json.loads((run_dir / resident.STATE_NAME).read_text(encoding="utf-8"))
            self.assertEqual("leafos.resident_state", payload["leafos_object"])
            self.assertEqual(8, payload["budgets"]["unattended_minutes"])


if __name__ == "__main__":
    unittest.main()
