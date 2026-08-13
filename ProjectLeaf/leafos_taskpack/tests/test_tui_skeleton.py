#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
TUI = ROOT / "core" / "ui" / "tui"
if str(TUI) not in sys.path:
    sys.path.insert(0, str(TUI))

import inlet_pipe
import main_screen
from router import RouterState, route_key


def write_json(path: pathlib.Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture_run(base: pathlib.Path) -> pathlib.Path:
    run_dir = base / "run"
    run_dir.mkdir()
    write_json(run_dir / "run.json", {
        "run_id": "tui-fixture", "created_utc": "2026-07-19T12:00:00+00:00",
        "target": str(base), "provider_mode": "required", "stack_entry": "local-stack:test",
        "approval": {"mode": "required", "status": "approved"},
    })
    write_json(run_dir / "state.json", {"status": "running", "next_action": "loop drive", "accepting_tasks": True})
    tasks = []
    previous = None
    for index, kind in enumerate(("inspect", "plan", "approve", "execute", "validate", "report"), 1):
        status = "complete" if index < 4 else "executing" if index == 4 else "queued"
        task_id = f"WO-TUI-{index:03d}"
        tasks.append({
            "task_id": task_id, "kind": kind, "objective": f"Perform {kind}", "status": status,
            "dependencies": [previous] if previous else [], "provider": "llamacpp" if kind == "plan" else "policy",
            "attempts": 1 if index <= 4 else 0, "max_attempts": 2, "evidence": [], "stack_entry": "local-stack:test",
        })
        previous = task_id
    write_json(run_dir / "queue.json", {"work_order_id": "WO-TUI", "tasks": tasks})
    write_json(run_dir / "work-order.json", {
        "work_order_id": "WO-TUI", "title": "Functional TUI fixture", "objective": "Render authoritative run state.",
        "acceptance": ["Screen renders"], "allow_mutation": False,
    })
    write_json(run_dir / "checkpoint.json", {
        "written_at": "2026-07-19T12:00:05+00:00", "changed_file_hashes": {}, "next_action": "loop drive",
    })
    write_json(run_dir / "step-state.json", {"completed_step_ids": [], "steps": {}})
    events = [
        {"seq": 1, "time": "2026-07-19T12:00:01+00:00", "kind": "work_order.accepted"},
        {"seq": 2, "time": "2026-07-19T12:00:02+00:00", "kind": "provider.progress", "task_id": "WO-TUI-002", "private_reasoning_chars": 256},
        {"seq": 3, "time": "2026-07-19T12:00:03+00:00", "kind": "provider.proposal.attached", "task_id": "WO-TUI-002", "plan": "plan.v2.json"},
        {"seq": 4, "time": "2026-07-19T12:00:04+00:00", "kind": "step.started", "task_id": "WO-TUI-004", "step_id": "edit", "step_kind": "apply_patch"},
        {"seq": 5, "time": "2026-07-19T12:00:05+00:00", "kind": "validation.passed", "task_id": "WO-TUI-004", "exit_code": 0},
    ]
    (run_dir / "events.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    telemetry = {
        "sequence": 1, "event_type": "sample", "stack": {"local_stack_id": "local-stack:test"},
        "hardware": {
            "gpu": {"name": "Fixture GPU", "utilization_percent": 75.0, "vram_used_gb": 8.0, "vram_total_gb": 12.0, "temperature_celsius": 60.0, "power_watts": 150.0},
            "cpu": {"utilization_percent": 20.0}, "memory": {"ram_used_gb": 16.0, "ram_total_gb": 48.0},
        },
        "throughput": {"brain_generation_tk_s": 32.5, "brain_prompt_tk_s": 120.0, "generated_tokens": 40, "prompt_tokens": 100},
        "economics": {"comparison_output_usd_per_million": 10.0, "gross_cloud_equivalent_usd": 0.0004, "token_count_scope": "interval"},
    }
    (run_dir / "universal-run-log.jsonl").write_text(json.dumps(telemetry) + "\n", encoding="utf-8")
    return run_dir


HOME = {
    "operator": {"name": "FlowerOS", "engine": "LeafOS", "stage": "pre-usage-layer"},
    "benchmark": {
        "status": "completed", "completed_cells": 20, "planned_cells": 20,
        "comparison": {"comparison_output_usd_per_million": 10.0},
        "best_generation": {"projected_gross_cloud_equivalent_usd_per_hour": 3.87},
    },
    "accelerator": {
        "backend": "vulkan", "model": "C:/models/fixture.gguf",
        "provider": {"health": "ok", "pid": 1234},
    }
}


class TuiFunctionalTests(unittest.TestCase):
    def test_snapshot_normalizes_run_and_preserves_event_cursor(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = fixture_run(pathlib.Path(tmp))
            with mock.patch.object(inlet_pipe.home_state, "build_state", return_value=HOME):
                snapshot = inlet_pipe.build_snapshot(str(run_dir), after=3)
            self.assertEqual("leafos.tui.snapshot", snapshot["leafos_object"])
            schema = json.loads((ROOT / "schemas" / "leafos.tui-snapshot.v1.schema.json").read_text(encoding="utf-8"))
            self.assertTrue(set(schema["required"]).issubset(snapshot))
            self.assertEqual(5, snapshot["event_cursor"])
            self.assertEqual([4, 5], [event["seq"] for event in snapshot["events"]])
            self.assertEqual("EXECUTE", next(item["name"] for item in snapshot["milestones"] if item["state"] == "active"))
            self.assertEqual(75.0, snapshot["hardware"]["gpu"]["utilization_percent"])
            self.assertEqual("SAFE", snapshot["run"]["safety"])
            self.assertEqual("FlowerOS", snapshot["operator"]["name"])
            self.assertEqual("completed", snapshot["benchmark"]["status"])
            self.assertEqual({"pid": None, "task_id": None, "started_utc": None}, snapshot["control"]["active_process"])

    def test_snapshot_exposes_resident_targets_budgets_and_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = fixture_run(pathlib.Path(tmp))
            write_json(run_dir / "resident-state.json", {
                "leafos_object": "leafos.resident_state", "version": 1, "enabled": True,
                "status": "auto-idle", "mode": "auto", "supervisor_pid": 4567,
                "budgets": {"unattended_minutes": 64, "max_iterations": 8},
                "usage": {"elapsed_minutes": 4.0, "iterations_generated": 2},
                "last_decision": {
                    "profile": "auto-idle", "reason": "productive_backlog", "claim_allowed": True,
                    "targets": {"cpu_percent": 80.0, "gpu_percent": 90.0},
                    "current": {"cpu_percent": 72.0, "gpu_percent": 88.0},
                    "cpu_slots": 3, "provider_delay_seconds": 0.0,
                    "input_idle_seconds": 30.0, "responsiveness_ms": 12.0,
                },
            })
            write_json(run_dir / "resident.lock", {"pid": 4567})
            with mock.patch.object(inlet_pipe.home_state, "build_state", return_value=HOME), mock.patch.object(
                inlet_pipe.inlet, "_pid_alive", return_value=True,
            ):
                snapshot = inlet_pipe.build_snapshot(str(run_dir))
            self.assertEqual("RESIDENT", snapshot["run"]["mode"])
            self.assertTrue(snapshot["resident"]["supervisor_alive"])
            self.assertEqual({"cpu_percent": 80.0, "gpu_percent": 90.0}, snapshot["resident"]["targets"])
            self.assertEqual("productive_backlog", snapshot["resident"]["reason"])
            self.assertEqual({"cpu_percent": 28.0, "gpu_percent": 12.0}, snapshot["resident"]["headroom"])

    def test_bare_run_id_resolves_inside_inlet_run_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_root = pathlib.Path(tmp) / "runs"
            runs_root.mkdir()
            run_dir = fixture_run(runs_root)
            named = runs_root / "named-run"
            run_dir.rename(named)
            with mock.patch.object(inlet_pipe.inlet, "RUNS_ROOT", runs_root):
                self.assertEqual(named.resolve(), inlet_pipe.resolve_run("named-run"))

    def test_snapshot_and_all_renderers_are_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = fixture_run(pathlib.Path(tmp))
            state_path = run_dir / "state.json"
            before = hashlib.sha256(state_path.read_bytes()).hexdigest()
            with mock.patch.object(inlet_pipe.home_state, "build_state", return_value=HOME):
                snapshot = inlet_pipe.build_snapshot(str(run_dir))
            for page in range(7):
                screen = main_screen.render(snapshot, page, 110, 32)
                self.assertIn(f"<{page + 1} {main_screen.header.PAGES[page]}>", screen)
                self.assertIn("tui-fixture", screen)
            hardware = main_screen.render(snapshot, 2, 110, 32)
            self.assertIn("Local value", hardware)
            self.assertIn("FlowerOS", hardware)
            self.assertEqual(before, hashlib.sha256(state_path.read_bytes()).hexdigest())

    def test_compact_layout_fits_small_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = fixture_run(pathlib.Path(tmp))
            with mock.patch.object(inlet_pipe.home_state, "build_state", return_value=HOME):
                snapshot = inlet_pipe.build_snapshot(str(run_dir))
            lines = main_screen.render(snapshot, 2, 72, 20).splitlines()
            self.assertLessEqual(len(lines), 20)
            self.assertTrue(all(len(line) <= 72 for line in lines))
            self.assertIn("q quit", lines[-1])

    def test_router_navigation_and_stop_confirmation_are_explicit(self):
        state = RouterState()
        self.assertIsNone(route_key(state, "TAB"))
        self.assertEqual(1, state.page_index)
        self.assertIsNone(route_key(state, "7"))
        self.assertEqual(6, state.page_index)
        self.assertEqual("quit", route_key(state, "q"))
        self.assertEqual("project_wizard", route_key(RouterState(), "n"))
        state = RouterState()
        route_key(state, ":")
        for key in "stop":
            route_key(state, key)
        self.assertIsNone(route_key(state, "ENTER"))
        self.assertEqual("STOP", state.confirmation)
        for key in "STOP":
            route_key(state, key)
        self.assertEqual("stop", route_key(state, "ENTER"))

        live_state = RouterState()
        route_key(live_state, ":")
        for key in "improve":
            route_key(live_state, key)
        self.assertEqual("live_command", route_key(live_state, "ENTER"))
        self.assertEqual(":improve", live_state.pending_command)

    def test_router_exposes_selected_task_controls_with_confirmed_cancel(self):
        state = RouterState()
        self.assertEqual("task_retry", route_key(state, "r"))
        self.assertEqual("task_priority_up", route_key(state, "["))
        self.assertEqual("task_priority_down", route_key(state, "]"))
        self.assertEqual("task_approve", route_key(state, "A"))
        self.assertIsNone(route_key(state, "x"))
        self.assertEqual("CANCEL", state.confirmation)
        state.confirmation_task_id = "TASK-PINNED"
        for key in "CANCEL":
            route_key(state, key)
        self.assertEqual("task_cancel", route_key(state, "ENTER"))
        self.assertEqual("TASK-PINNED", state.confirmation_task_id)

    @unittest.skipUnless(subprocess.call(["bash", "-c", "exit 0"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0, "bash is required")
    def test_leafctl_tui_renders_noninteractive_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = fixture_run(pathlib.Path(tmp))
            result = subprocess.run(
                ["bash", "./bin/leafctl", "tui", "--run", str(run_dir).replace("\\", "/"), "--once", "--width", "90", "--height", "28"],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("FlowerOS | LeafOS engine | run tui-fixture", result.stdout)
            self.assertIn("ACTIVE WORK", result.stdout)


if __name__ == "__main__":
    unittest.main()
