#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
import shlex
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MSYS_BASH = Path("C:/msys64/usr/bin/bash.exe")
BASH = str(MSYS_BASH) if MSYS_BASH.is_file() else shutil.which("bash")
WSL = shutil.which("wsl.exe")


def windows_path_to_wsl(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = resolved.as_posix().split(":", 1)[-1].lstrip("/")
    return f"/mnt/{drive}/{rest}"


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
        self.assertIn("pack create", result.stdout)
        self.assertIn("indicator status|preview|set|clear|doctor", result.stdout)

    def test_pack_route_reaches_constructor_catalog(self) -> None:
        result = self.run_leafctl("pack", "catalog", "--json")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("runtime-default", payload["profiles"])
        self.assertGreaterEqual(len(payload["models"]), 10)

    def test_indicator_route_resolves_pack_glyph(self) -> None:
        result = self.run_leafctl("indicator", "preview", "ficus", "--json")
        if "PowerShell 5+ not found" in result.stderr:
            self.skipTest("PowerShell 5+ is not available to bash")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("ficus", payload["pack_id"])
        self.assertEqual("✿", payload["glyph"])

    def test_indicator_doctor_reports_the_discovered_host(self) -> None:
        result = self.run_leafctl("indicator", "doctor", "--json")
        if "PowerShell 5+ not found" in result.stderr:
            self.skipTest("PowerShell 5+ is not available to bash")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("leafos.indicator_host_report", payload["leafos_object"])
        self.assertTrue(payload["ready"])
        self.assertGreaterEqual(int(payload["host"]["powershell"].split(".")[0]), 5)
        self.assertIn(
            payload["host"]["route"],
            {"msys-windows-interop", "wsl-windows-interop", "wsl-native", "unix-native"},
        )

    def test_detected_powershell_is_checked_against_each_capability_floor(self) -> None:
        result = subprocess.run(
            [
                BASH,
                "-c",
                "source ./core/system/versions.sh; "
                "LEAF_PWSH_CMD=/detected/powershell; LEAF_VER_PWSH=5.1; "
                "if leaf_pwsh_meets 7.0; then exit 9; fi; leaf_pwsh_meets 5.0",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    @unittest.skipUnless(WSL, "WSL is required")
    def test_wsl_general_forward_never_sends_a_v7_script_to_v5(self) -> None:
        root = shlex.quote(windows_path_to_wsl(ROOT))
        command = (
            f"cd {root} && "
            "env USER=leafos-no-user USERNAME=leafos-no-user "
            "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "
            "./bin/leafctl home --json"
        )
        result = subprocess.run(
            [WSL, "bash", "-lc", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            check=False,
        )
        combined = result.stdout + result.stderr
        if result.returncode == 0:
            self.skipTest("A discoverable PowerShell 7 host prevented the forced 5.1 fallback")
        self.assertIn("PowerShell 7+ is required for 'home'", combined)
        self.assertIn("PowerShell 5/5.1 fallback is limited", combined)
        self.assertNotIn("Unexpected token '??'", combined)

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
        self.assertGreaterEqual(payload["profile_count"], 4)

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

    def test_live_route_inspects_current_directory_without_starting_a_run(self) -> None:
        result = self.run_leafctl("live", ".", "--inspect", "--json")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("leafos.live_project_inventory", payload["leafos_object"])
        self.assertEqual("codebase", payload["state"])

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
