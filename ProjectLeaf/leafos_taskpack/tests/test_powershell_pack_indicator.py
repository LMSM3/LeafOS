#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core" / "powershell" / "LeafOS.psm1"
CLI = ROOT / "bin" / "leaf-indicator.ps1"
FICUS = ROOT / "config" / "packs" / "ficus.json"
PWSH = shutil.which("pwsh")
WINDOWS_POWERSHELL = shutil.which("powershell.exe")
WORKSPACE = ROOT.parents[1]
ACTIVATOR = WORKSPACE / "PowerShell-Version" / "Enable-LeafPackIndicator.ps1"
ROOT_CLI = WORKSPACE / "leafos.ps1"
RESOLVER = WORKSPACE / "PowerShell-Version" / "Resolve-LeafPowerShellHost.ps1"
EVIDENCE_SCHEMA = ROOT / "schemas" / "leafos.subsystem-indicator-evidence.v1.schema.json"


class IndicatorSourceCompatibilityTests(unittest.TestCase):
    def test_indicator_module_remains_windows_powershell_safe_text(self) -> None:
        source = MODULE.read_bytes()
        source.decode("ascii")
        self.assertNotIn(b"??", source)


@unittest.skipUnless(WINDOWS_POWERSHELL, "Windows PowerShell 5.1 is required")
class WindowsPowerShellIndicatorCompatibilityTests(unittest.TestCase):
    def run_windows_powershell(
        self, arguments: list[str], *, state_path: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["NO_COLOR"] = "1"
        if state_path is not None:
            environment["LEAF_ACTIVE_PACK_STATE"] = str(state_path)
            environment["LEAF_ACTIVE_RUN_STATE"] = str(state_path.with_name("active-run.json"))
        return subprocess.run(
            [
                WINDOWS_POWERSHELL,
                "-NoLogo",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                *arguments,
            ],
            cwd=WORKSPACE,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )

    def test_windows_powershell_root_route_renders_ficus(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_windows_powershell(
                ["-File", str(ROOT_CLI), "indicator", "preview", "ficus", "--json"],
                state_path=Path(temporary) / "active-pack.json",
            )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("ficus", payload["pack_id"])
        self.assertEqual("✿", payload["glyph"])

    def test_windows_powershell_doctor_reports_ready(self) -> None:
        result = self.run_windows_powershell(
            ["-File", str(ROOT_CLI), "indicator", "doctor", "--json"]
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("leafos.indicator_host_report", payload["leafos_object"])
        self.assertTrue(payload["ready"])
        self.assertEqual("Desktop", payload["host"]["edition"])
        self.assertGreaterEqual(int(payload["host"]["powershell"].split(".")[0]), 5)

    def test_windows_powershell_activator_changes_the_current_prompt(self) -> None:
        command = (
            "$env:LEAF_SUBSYSTEM_PID=[string]$PID; "
            f". '{ACTIVATOR}' -Pack ficus; "
            "$rendered=prompt; Disable-LeafPackIndicator; "
            "[pscustomobject]@{contains_pack_glyph=$rendered.Contains([string][char]0x273f)} "
            "| ConvertTo-Json -Compress"
        )
        result = self.run_windows_powershell(["-Command", command])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)["contains_pack_glyph"])

    def test_windows_powershell_active_without_pack_uses_leaf_fallback(self) -> None:
        command = (
            f"Import-Module '{MODULE}' -Force; "
            "$env:LEAF_SUBSYSTEM_PID=[string]$PID; "
            f"$result=Get-LeafPackIndicator -Root '{ROOT}' -Refresh; "
            "$leaf=[char]::ConvertFromUtf32(0x1f343); "
            "[pscustomobject]@{active=$result.active;is_leaf=($result.glyph -eq $leaf);"
            "customized=$result.customized} | ConvertTo-Json -Compress"
        )
        result = self.run_windows_powershell(["-Command", command])
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["active"])
        self.assertTrue(payload["is_leaf"])
        self.assertFalse(payload["customized"])

    @unittest.skipUnless(PWSH, "PowerShell 7 is required for resolver preference")
    def test_windows_powershell_resolver_prefers_a_working_v7_host(self) -> None:
        result = self.run_windows_powershell(
            ["-File", str(RESOLVER), "-MinimumMajor", "7"]
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["usable"])
        self.assertGreaterEqual(int(payload["version"].split(".")[0]), 7)

    def test_doctor_distinguishes_a_corrupted_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fake_root = Path(temporary)
            module = fake_root / "core" / "powershell" / "LeafOS.psm1"
            module.parent.mkdir(parents=True)
            module.write_text("function Broken {\n", encoding="ascii")
            (fake_root / "config" / "packs").mkdir(parents=True)
            result = self.run_windows_powershell(
                ["-File", str(CLI), "doctor", "--root", str(fake_root), "--json"]
            )
        self.assertNotEqual(0, result.returncode)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ready"])
        failed = {check["id"]: check for check in payload["checks"] if not check["ok"]}
        self.assertIn("install.indicator_module", failed)
        self.assertIn("parse failed", failed["install.indicator_module"]["detail"])


@unittest.skipUnless(PWSH, "PowerShell 7 is required")
class PowerShellPackIndicatorTests(unittest.TestCase):
    def run_pwsh(
        self,
        command: str,
        *,
        state_path: Path,
        active_pack: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["LEAF_ACTIVE_PACK_STATE"] = str(state_path)
        environment["LEAF_ACTIVE_RUN_STATE"] = str(state_path.with_name("active-run.json"))
        environment["NO_COLOR"] = "1"
        environment.pop("LEAF_ACTIVE_PACK", None)
        environment.pop("LEAF_SUBSYSTEM_PID", None)
        environment.pop("LEAF_SUBSYSTEM_NAME", None)
        environment.pop("LEAF_SUBSYSTEM_ACTIVE", None)
        if active_pack is not None:
            environment["LEAF_ACTIVE_PACK"] = active_pack
        return subprocess.run(
            [PWSH, "-NoProfile", "-Command", command],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )

    def indicator_command(self) -> str:
        return (
            f"Import-Module '{MODULE}' -Force; "
            f"Get-LeafPackIndicator -Root '{ROOT}' -Refresh | ConvertTo-Json -Compress"
        )

    def test_falls_back_to_leaf_when_no_pack_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_pwsh(
                self.indicator_command(),
                state_path=Path(temporary) / "active-pack.json",
            )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("🍃", payload["glyph"])
        self.assertEqual("fallback", payload["source"])
        self.assertFalse(payload["customized"])
        self.assertFalse(payload["active"])
        self.assertEqual("leafos.subsystem_indicator_evidence", payload["evidence"]["leafos_object"])
        self.assertEqual([], payload["evidence"]["claims"])
        self.assertEqual("none", payload["evidence"]["evidence_grade"])

    def test_live_subsystem_uses_environment_pack_glyph_as_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            command = (
                f"Import-Module '{MODULE}' -Force; "
                "$env:LEAF_SUBSYSTEM_PID=[string]$PID; "
                "$env:LEAF_SUBSYSTEM_NAME='test-owned'; "
                f"Get-LeafPackIndicator -Root '{ROOT}' -Refresh | ConvertTo-Json -Depth 8 -Compress"
            )
            result = self.run_pwsh(
                command,
                state_path=Path(temporary) / "active-pack.json",
                active_pack=str(FICUS),
            )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("ficus", payload["pack_id"])
        self.assertEqual("✿", payload["glyph"])
        self.assertEqual("environment", payload["source"])
        self.assertTrue(payload["customized"])
        self.assertTrue(payload["active"])
        self.assertEqual("test-owned", payload["evidence"]["subsystem"])
        self.assertEqual("process", payload["evidence"]["evidence_grade"])
        self.assertEqual(
            ["subsystem.process.active", "pack.identity.bound"],
            payload["evidence"]["claims"],
        )

    def test_live_subsystem_without_pack_uses_leaf_glyph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            command = (
                f"Import-Module '{MODULE}' -Force; "
                "$env:LEAF_SUBSYSTEM_PID=[string]$PID; "
                f"Get-LeafPackIndicator -Root '{ROOT}' -Refresh | ConvertTo-Json -Depth 8 -Compress"
            )
            result = self.run_pwsh(
                command,
                state_path=Path(temporary) / "active-pack.json",
            )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["active"])
        self.assertEqual("🍃", payload["glyph"])
        self.assertEqual(["subsystem.process.active"], payload["evidence"]["claims"])

    def test_active_run_pointer_detects_resident_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "active-pack.json"
            active_run = state_path.with_name("active-run.json")
            run_dir = Path(temporary) / "run"
            command = (
                f"Import-Module '{MODULE}' -Force; "
                f"$run='{run_dir}'; New-Item -ItemType Directory -Path $run | Out-Null; "
                "@{pid=$PID} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $run 'resident.lock') -Encoding utf8; "
                f"@{{run_dir=$run}} | ConvertTo-Json | Set-Content -LiteralPath '{active_run}' -Encoding utf8; "
                f"Get-LeafPackIndicator -Root '{ROOT}' -Refresh | ConvertTo-Json -Depth 8 -Compress"
            )
            result = self.run_pwsh(command, state_path=state_path)
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["active"])
        self.assertEqual("leafos.resident-supervisor", payload["evidence"]["subsystem"])
        self.assertEqual("active-run:resident.lock", payload["evidence"]["source"])

    def test_ascii_pack_indicator_is_independent_from_colour(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            command = (
                f"Import-Module '{MODULE}' -Force; $env:LEAF_GLYPHS='ascii'; "
                f"$indicator=Get-LeafPackIndicator -Pack '{FICUS}' -Root '{ROOT}' -Refresh; "
                "[pscustomobject]@{pack=(Format-LeafPackIndicator $indicator);"
                "fallback=(Get-LeafGlyph -Alias 'leaf.active')} | ConvertTo-Json -Compress"
            )
            result = self.run_pwsh(
                command,
                state_path=Path(temporary) / "active-pack.json",
            )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("[pack:ficus]", payload["pack"])
        self.assertEqual("(live)", payload["fallback"])

    def test_cli_persists_then_clears_pack_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "active-pack.json"
            set_result = self.run_pwsh(
                f"& '{CLI}' set ficus --json",
                state_path=state_path,
            )
            self.assertEqual(0, set_result.returncode, set_result.stderr)
            self.assertTrue(state_path.is_file())

            status_result = self.run_pwsh(
                f"& '{CLI}' status --json",
                state_path=state_path,
            )
            self.assertEqual(0, status_result.returncode, status_result.stderr)
            status = json.loads(status_result.stdout)
            self.assertEqual("ficus", status["pack_id"])
            self.assertEqual("persisted", status["source"])

            clear_result = self.run_pwsh(
                f"& '{CLI}' clear --json",
                state_path=state_path,
            )
            self.assertEqual(0, clear_result.returncode, clear_result.stderr)
            self.assertFalse(state_path.exists())

    def test_persistence_refuses_to_replace_an_unrelated_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "active-pack.json"
            state_path.write_text("do not replace\n", encoding="utf-8")
            result = self.run_pwsh(
                f"& '{CLI}' set ficus --json",
                state_path=state_path,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("Refusing to replace non-LeafOS state file", result.stderr)
            self.assertEqual("do not replace\n", state_path.read_text(encoding="utf-8"))

    def test_prompt_hook_restores_the_previous_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            command = (
                f"Import-Module '{MODULE}' -Force; "
                "$env:LEAF_SUBSYSTEM_PID=[string]$PID; "
                "$before=(Get-Item Function:\\prompt).ScriptBlock.ToString(); "
                f"$null=Enable-LeafPackIndicator -Pack '{FICUS}' -Root '{ROOT}'; "
                "$state=Get-LeafPackIndicator -Refresh; $rendered=prompt; Disable-LeafPackIndicator; "
                "$after=(Get-Item Function:\\prompt).ScriptBlock.ToString(); "
                "[pscustomobject]@{active=$state.active;rendered=$rendered;restored=($before -eq $after)} | ConvertTo-Json -Compress"
            )
            result = self.run_pwsh(
                command,
                state_path=Path(temporary) / "active-pack.json",
            )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["active"])
        self.assertIn("✿", payload["rendered"])
        self.assertTrue(payload["restored"])

    def test_dot_sourced_activator_installs_pack_prompt_without_output_spam(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            command = (
                "$env:LEAF_SUBSYSTEM_PID=[string]$PID; "
                f". '{ACTIVATOR}' -Pack ficus; "
                "$rendered=prompt; Disable-LeafPackIndicator; "
                "[pscustomobject]@{rendered=$rendered} | ConvertTo-Json -Compress"
            )
            result = self.run_pwsh(
                command,
                state_path=Path(temporary) / "active-pack.json",
            )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("✿", payload["rendered"])

    def test_inactive_subsystem_does_not_decorate_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            command = (
                f"Import-Module '{MODULE}' -Force; "
                "$before=(prompt); $null=Enable-LeafPackIndicator; $after=(prompt); "
                "Disable-LeafPackIndicator; "
                "[pscustomobject]@{same=($before -eq $after);rendered=$after} | ConvertTo-Json -Compress"
            )
            result = self.run_pwsh(
                command,
                state_path=Path(temporary) / "active-pack.json",
            )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["same"])
        self.assertNotIn("🍃", payload["rendered"])

    def test_demo_override_is_explicitly_graded_demo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            command = (
                f"Import-Module '{MODULE}' -Force; "
                "$env:LEAF_SUBSYSTEM_ACTIVE='1'; $env:LEAF_SUBSYSTEM_NAME='showcase'; "
                f"Get-LeafPackIndicator -Root '{ROOT}' -Refresh | ConvertTo-Json -Depth 8 -Compress"
            )
            result = self.run_pwsh(
                command,
                state_path=Path(temporary) / "active-pack.json",
            )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["active"])
        self.assertEqual("demo", payload["evidence"]["evidence_grade"])
        self.assertEqual(0, payload["evidence"]["process_id"])

    def test_evidence_schema_declares_the_runtime_claim_contract(self) -> None:
        schema = json.loads(EVIDENCE_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(
            "leafos.subsystem_indicator_evidence",
            schema["properties"]["leafos_object"]["const"],
        )
        self.assertIn("claims", schema["required"])
        self.assertIn("does_not_prove", schema["required"])

    def test_quiet_process_captures_evidence_without_a_shell_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            command = (
                f"Import-Module '{MODULE}' -Force; "
                "$child=Invoke-LeafQuietProcess -FilePath (Get-Command pwsh).Source "
                "-ArgumentList @('-NoProfile','-Command','Write-Output quiet-ok') -TimeoutSeconds 10; "
                "$child | ConvertTo-Json -Compress"
            )
            result = self.run_pwsh(
                command,
                state_path=Path(temporary) / "active-pack.json",
            )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(0, payload["ExitCode"])
        self.assertEqual("quiet-ok", payload["StdOut"].strip())
        self.assertEqual("", payload["StdErr"])
        self.assertTrue(payload["CreateNoWindow"])
        self.assertFalse(payload["UseShellExecute"])

    def test_quiet_background_process_writes_logs_and_returns_pid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "active-pack.json"
            stdout = Path(temporary) / "child.out.log"
            stderr = Path(temporary) / "child.err.log"
            command = (
                f"Import-Module '{MODULE}' -Force; "
                "$child=Start-LeafQuietProcess -FilePath (Get-Command pwsh).Source "
                "-ArgumentList @('-NoProfile','-Command','Write-Output background-ok') "
                f"-StdOutPath '{stdout}' -StdErrPath '{stderr}'; "
                "$child.Process.WaitForExit(); "
                "[pscustomobject]@{pid=$child.ProcessId;hidden=$child.Hidden;exit=$child.Process.ExitCode} "
                "| ConvertTo-Json -Compress"
            )
            result = self.run_pwsh(command, state_path=state_path)
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertGreater(payload["pid"], 0)
            self.assertEqual(0, payload["exit"])
            self.assertTrue(payload["hidden"])
            self.assertEqual("background-ok", stdout.read_text(encoding="utf-8-sig").strip())
            self.assertEqual("", stderr.read_text(encoding="utf-8-sig").strip())

    def test_root_powershell_route_preserves_gnu_style_json_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment = os.environ.copy()
            environment["LEAF_ACTIVE_PACK_STATE"] = str(Path(temporary) / "active-pack.json")
            environment["NO_COLOR"] = "1"
            environment.pop("LEAF_ACTIVE_PACK", None)
            result = subprocess.run(
                [
                    PWSH,
                    "-NoProfile",
                    "-File",
                    str(WORKSPACE / "leafos.ps1"),
                    "indicator",
                    "preview",
                    "viola-nocturne",
                    "--json",
                ],
                cwd=WORKSPACE,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("viola-nocturne", payload["pack_id"])
        self.assertEqual("❀", payload["glyph"])

    def test_resident_supervisor_uses_full_windows_hide_contract(self) -> None:
        source = (ROOT / "core" / "python" / "leaf_resident_supervisor.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('getattr(subprocess, "CREATE_NO_WINDOW", 0)', source)
        self.assertIn("subprocess.STARTF_USESHOWWINDOW", source)
        self.assertIn("startupinfo=startupinfo", source)


if __name__ == "__main__":
    unittest.main()
