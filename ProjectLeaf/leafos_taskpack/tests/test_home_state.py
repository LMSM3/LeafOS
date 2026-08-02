#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "ui"))

from accelerator_state import _process_alive, build_state as build_accelerator_state  # noqa: E402
from home import render  # noqa: E402
from home_state import _operator_cli, build_state  # noqa: E402
from trace import build_trace  # noqa: E402


def inventory(root: Path) -> list[tuple[str, int]]:
    return sorted((str(path.relative_to(root)), path.stat().st_size) for path in root.rglob("*") if path.is_file())


class HomeStateTests(unittest.TestCase):
    def make_root(self, directory: str) -> Path:
        root = Path(directory) / "taskpack"
        for name in ("bin", "core", "config", "docs", "tests", "runs"):
            (root / name).mkdir(parents=True)
        (root / "config" / "runtime.json").write_text(
            json.dumps({"leafos_runtime": {"defaults": {"main_model": "brain", "coder_model": "coder", "mode": "loop"}}}),
            encoding="utf-8",
        )
        (root / "config" / "vulkan-provider-stack.json").write_text(
            json.dumps({"provider": "llamacpp", "backend": "vulkan", "server": {"host": "127.0.0.1", "port": 1}}),
            encoding="utf-8",
        )
        work_orders = root / "docs" / "work-orders"
        work_orders.mkdir()
        (work_orders / "WO-018-capabilities.md").write_text("[I] ACTIVE\n", encoding="utf-8")
        run = root / "runs" / "run-1"
        run.mkdir()
        (run / "events.jsonl").write_text('{"kind":"run.started"}\n', encoding="utf-8")
        return root

    def test_home_contract_is_complete_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            before = inventory(root)
            state = build_state(root, health_timeout=0.01)
            self.assertEqual(before, inventory(root))
            required = {
                "leafos_object", "version", "generated_at", "root", "readiness", "provider",
                "accelerator", "stack", "runtime", "gpu", "work_order", "task_loop",
                "recent_runs", "next_actions", "operator", "benchmark", "reference",
            }
            self.assertEqual(required, set(state))
            self.assertEqual("WO-018", state["work_order"]["id"])
            self.assertIn("LeafOS Home", render(state))

    def test_floweros_surface_projects_latest_benchmark_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            (root / "config" / "operator-experience.json").write_text(json.dumps({
                "schema": "leafos.operator-experience.v1",
                "surface": {"name": "FlowerOS", "engine": "LeafOS", "stage": "usage-layer", "default_command": "flower.ps1 home"},
                "economics": {
                    "currency": "USD", "comparison_output_usd_per_million": 10.0,
                    "pricing_basis": "operator_assumption", "local_costs_included": False,
                },
            }), encoding="utf-8")
            report_dir = root / "reports" / "inference-benchmark" / "latest"
            report_dir.mkdir(parents=True)
            (report_dir / "report.json").write_text(json.dumps({
                "benchmark_id": "latest", "status": "completed", "planned_cell_count": 1,
                "cells": [{
                    "id": "full", "status": "completed",
                    "definition": {"model": "brain.gguf", "generated_tokens": 100, "repetitions": 2, "gpu_layers": 999},
                    "throughput": {"generation": {"tokens_per_second": 50.0}},
                }],
            }), encoding="utf-8")
            before = inventory(root)
            state = build_state(root, health_timeout=0.01)
            self.assertEqual(before, inventory(root))
            self.assertEqual("FlowerOS", state["operator"]["name"])
            self.assertEqual("LeafOS", state["operator"]["engine"])
            self.assertEqual(1.8, state["benchmark"]["best_generation"]["projected_gross_cloud_equivalent_usd_per_hour"])
            self.assertIn("FlowerOS Home", render(state))
            self.assertTrue(all("flower" in item["command"] for item in state["next_actions"]))

    def test_canonical_layout_uses_root_launcher_for_next_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            leafos_root = Path(directory) / "LeafOS0.2.1"
            taskpack = leafos_root / "ProjectLeaf" / "leafos_taskpack"
            taskpack.mkdir(parents=True)
            (leafos_root / "leafos.ps1").write_text("# root launcher\n", encoding="utf-8")
            (leafos_root / "leafos.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            command = _operator_cli(taskpack, "FlowerOS")
            self.assertIn("leafos.ps1" if os.name == "nt" else "leafos.sh", command)
            self.assertNotIn("bin\\flower.ps1", command)
            self.assertNotIn("bin/flowerctl", command)

            if os.name == "nt":
                with mock.patch.dict(os.environ, {"LEAF_CALLER_SHELL": "wsl"}):
                    wsl_command = _operator_cli(taskpack, "FlowerOS")
                self.assertIn("/mnt/", wsl_command)
                self.assertIn("leafos.sh", wsl_command)

    def test_missing_gpu_config_has_cpu_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = build_accelerator_state(root, timeout=0.01)
            self.assertEqual("cpu_fallback", state["state"])
            self.assertTrue(state["cpu_fallback"])
            self.assertEqual("leafctl provider-stack check", state["safe_start_command"])

    def test_trace_reads_real_artifact_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            trace = build_trace("latest", root)
            self.assertEqual("ok", trace["status"])
            self.assertEqual("run.started", trace["events"][0]["kind"])
            self.assertFalse(trace["private_chain_of_thought_exposed"])

    def test_current_process_pid_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pid_path = Path(directory) / "provider.pid"
            pid_path.write_text(str(os.getpid()), encoding="utf-8")
            alive, pid = _process_alive(pid_path)
            self.assertTrue(alive)
            self.assertEqual(os.getpid(), pid)


if __name__ == "__main__":
    unittest.main()
