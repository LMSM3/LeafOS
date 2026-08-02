#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MSYS_BASH = Path("C:/msys64/usr/bin/bash.exe")
BASH = str(MSYS_BASH) if MSYS_BASH.is_file() else shutil.which("bash")


@unittest.skipUnless(BASH, "bash is required")
class LeafctlDispatchTests(unittest.TestCase):
    def run_leafctl(self, *args: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        if MSYS_BASH.is_file():
            environment["PATH"] = ";".join((
                "C:\\msys64\\ucrt64\\bin",
                "C:\\msys64\\usr\\bin",
                environment.get("PATH", ""),
            ))
        return subprocess.run(
            [BASH, "./bin/leafctl", *args],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )

    def test_help_advertises_cross_shell_routes(self) -> None:
        result = self.run_leafctl("help")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("provider-stack check|start|status|stop", result.stdout)
        self.assertIn("oneshot --oneshot SOURCE TARGET", result.stdout)
        self.assertIn("model-profile list|validate", result.stdout)
        self.assertIn("wakeup [--force heads|tails]", result.stdout)
        self.assertIn("test visual", result.stdout)
        self.assertIn("live [DIR]", result.stdout)
        self.assertIn("resident start|status", result.stdout)
        self.assertIn("passive-report [-RunRoot RUN]", result.stdout)
        self.assertIn("bloom init|status|input|claim|validate|checkpoint|verify|recover", result.stdout)

    def test_no_argument_route_defaults_to_home(self) -> None:
        result = self.run_leafctl()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("FlowerOS Home", result.stdout)

    def test_provider_stack_route_reaches_native_checker(self) -> None:
        result = self.run_leafctl("provider-stack", "check", "--json")
        if "PowerShell 7+ not found" in result.stderr:
            self.skipTest("PowerShell 7+ is not available to bash")
        self.assertNotIn("unknown command", result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {"ready", "not_ready"})

    def test_oneshot_route_reaches_native_help(self) -> None:
        result = self.run_leafctl("oneshot", "--help")
        if "PowerShell 7+ not found" in result.stderr:
            self.skipTest("PowerShell 7+ is not available to bash")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("LeafOS OneShot Bundle", result.stdout)

    def test_model_profile_route_validates_registry(self) -> None:
        result = self.run_leafctl("model-profile", "validate", "--json")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("ok", payload["status"])
        self.assertEqual(4, payload["profile_count"])

    def test_wakeup_route_runs_without_writing_logs(self) -> None:
        result = self.run_leafctl("wakeup", "--force", "tails", "--no-log")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("time is", result.stdout)

    def test_loop_task_help_reaches_typed_inlet(self) -> None:
        result = self.run_leafctl("loop", "task", "--help")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("submit", result.stdout)
        self.assertIn("prioritize", result.stdout)
        self.assertIn("cancel", result.stdout)

    def test_live_route_inspects_catan2_without_starting_a_run(self) -> None:
        result = self.run_leafctl("live", ".", "--inspect", "--json")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("leafos.live_project_inventory", payload["leafos_object"])
        self.assertTrue(payload["catan2"])

    def test_resident_route_reports_machine_readable_state(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            (run_dir / "run.json").write_text(json.dumps({"run_id": "resident-cli"}), encoding="utf-8")
            (run_dir / "queue.json").write_text(json.dumps({"tasks": []}), encoding="utf-8")
            (run_dir / "resident-state.json").write_text(json.dumps({
                "leafos_object": "leafos.resident_state", "version": 1, "enabled": True,
                "status": "waiting", "mode": "auto",
            }), encoding="utf-8")
            result = self.run_leafctl("resident", "status", str(run_dir), "--json")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("resident-cli", payload.get("run_id"))
        self.assertFalse(payload["supervisor_alive"])

    def test_passive_report_route_preserves_windows_run_path(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            (run_dir / "run.json").write_text(json.dumps({"run_id": "passive-cli"}), encoding="utf-8")
            (run_dir / "journal.lje").write_text(
                '{"event":"checkpoint.valid","data":{"status":"ok"}}\n',
                encoding="utf-8",
            )
            result = self.run_leafctl(
                "passive-report", "-RunRoot", str(run_dir), "-SkipHealthCheck", "-Json"
            )
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual("passive-cli", json.loads((run_dir / "run.json").read_text())["run_id"])
            self.assertEqual("leafos.passive_report_launch", payload["leafos_object"])
            self.assertTrue(Path(payload["html"]).is_file())


if __name__ == "__main__":
    unittest.main()
