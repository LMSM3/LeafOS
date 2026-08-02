from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("leaf_loop_inlet", ROOT / "core" / "python" / "leaf_loop_inlet.py")
inlet = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inlet)


class InstallBenchmarkTests(unittest.TestCase):
    def test_duration_parser_accepts_seconds_minutes_hours(self) -> None:
        self.assertEqual(30.0, inlet._parse_benchmark_duration("30s"))
        self.assertEqual(90.0, inlet._parse_benchmark_duration("1.5m"))
        self.assertEqual(3600.0, inlet._parse_benchmark_duration("1h"))

    def test_duration_parser_rejects_missing_unit_and_empty(self) -> None:
        with self.assertRaises(ValueError):
            inlet._parse_benchmark_duration("60")
        with self.assertRaises(ValueError):
            inlet._parse_benchmark_duration("")

    def test_benchmark_command_runs_within_requested_duration(self) -> None:
        bench_dir = ROOT / "runs" / "bench"
        before = {path.name for path in bench_dir.glob("*-install") if path.is_dir()} if bench_dir.is_dir() else set()
        result = subprocess.run(
            [sys.executable, str(ROOT / "core" / "python" / "leaf_loop_inlet.py"), "benchmark", "5s", "--provider", "off", "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("leafos.install_benchmark", payload["leafos_object"])
        self.assertEqual(5.0, payload["duration_requested_sec"])
        self.assertLessEqual(payload["duration_actual_sec"], 8.0)
        self.assertGreaterEqual(payload["samples"]["count"], 3)
        self.assertEqual(payload["provider_mode"], "off")
        report_path = Path(payload["run_dir"]) / "benchmark.json"
        self.assertTrue(report_path.is_file())

    def test_benchmark_help_mentions_units(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "core" / "python" / "leaf_loop_inlet.py"), "benchmark", "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertIn("duration", result.stdout)
        self.assertIn("s, 60s, 5m", result.stdout)

    def test_skeleton_mode_exercises_project_creation(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "core" / "python" / "leaf_loop_inlet.py"), "benchmark", "8s", "--provider", "off", "--mode", "skeleton", "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("skeleton", payload["mode"])
        self.assertGreaterEqual(payload["work"]["iterations"], 1)
        self.assertGreater(payload["work"]["successful"], 0)

    def test_brain_coder_mode_produces_conversation_and_thinking_artifacts(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "core" / "python" / "leaf_loop_inlet.py"), "benchmark", "15s", "--provider", "off", "--mode", "brain-coder", "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=45,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("brain-coder", payload["mode"])
        self.assertIn("thinking_process", payload)
        run_dir = Path(payload["run_dir"])
        conversation = run_dir / "conversation.jsonl"
        thinking = run_dir / "thinking.json"
        self.assertTrue(conversation.is_file())
        self.assertTrue(thinking.is_file())
        lines = conversation.read_text(encoding="utf-8").strip().splitlines()
        self.assertGreaterEqual(len(lines), 3)
        roles = set()
        for line in lines:
            item = json.loads(line)
            self.assertIn(item["role"], {"user", "brain", "coder", "system"})
            self.assertIsInstance(item["time"], str)
            self.assertIsInstance(item["message"], str)
            roles.add(item["role"])
        self.assertTrue(roles.issuperset({"user", "brain", "coder", "system"}))
        summary = json.loads(thinking.read_text(encoding="utf-8"))
        self.assertIn("iterations", summary)
        self.assertIn("successful_thinking", summary)
        self.assertIn("last_thinking", summary)

    def test_llm_provider_off_records_truthful_conversation_and_telemetry(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "core" / "python" / "leaf_loop_inlet.py"), "benchmark", "10s", "--provider", "off", "--mode", "llm", "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("llm", payload["mode"])
        self.assertIn("llm_conversation", payload)
        run_dir = Path(payload["run_dir"])
        conversation = run_dir / "conversation.jsonl"
        telemetry = run_dir / "universal-run-log.jsonl"
        self.assertTrue(conversation.is_file())
        self.assertTrue(telemetry.is_file())
        lines = conversation.read_text(encoding="utf-8").strip().splitlines()
        self.assertGreaterEqual(len(lines), 2)
        roles = set()
        for line in lines:
            item = json.loads(line)
            self.assertIn(item["role"], {"user", "assistant"})
            self.assertIsInstance(item["time"], str)
            self.assertIsInstance(item["message"], str)
            roles.add(item["role"])
        self.assertEqual({"user"}, roles)
        log_lines = telemetry.read_text(encoding="utf-8").strip().splitlines()
        self.assertGreaterEqual(len(log_lines), 1)
        event = json.loads(log_lines[0])
        self.assertEqual(event.get("leafos_object"), "leafos.universal_run_log.event")
        self.assertEqual(event.get("run_kind"), "fullstackbench")
        self.assertEqual(event.get("event_type"), "sample")
        self.assertEqual("off", event["provider"]["mode"])
        self.assertEqual("off", event["provider"]["status"])
        self.assertIsNone(event["provider"]["backend"])
        self.assertEqual(0, event["instances"]["brain_initiated"])
        self.assertEqual(0, event["instances"]["brain_alive"])
        self.assertEqual(0, event["instances"]["provider_initiated"])
        self.assertEqual(0, event["instances"]["provider_alive"])
        self.assertIsNone(event["throughput"]["brain_generation_tk_s"])
        self.assertIsNone(event["throughput"]["generated_tokens"])
        self.assertEqual("failed", event["quality"]["validation_status"])
        self.assertIn("outcome=provider_unhealthy", event["notes"])
        summary = payload["llm_conversation"]
        self.assertIn("iterations", summary)
        self.assertIn("successful_turns", summary)
        self.assertIn("total_prompt_tokens", summary)
        self.assertIn("total_completion_tokens", summary)
        self.assertEqual(0, summary["successful_turns"])
        self.assertEqual(0, summary["total_prompt_tokens"])
        self.assertEqual(0, summary["total_completion_tokens"])


if __name__ == "__main__":
    unittest.main()
