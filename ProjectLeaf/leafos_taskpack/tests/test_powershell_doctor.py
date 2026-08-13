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
WORKSPACE = ROOT.parents[1]
MODULE = ROOT / "core" / "powershell" / "LeafOS.psm1"
DOCTOR = ROOT / "core" / "python" / "leaf_doctor.py"
ROOT_CLI = WORKSPACE / "leafos.ps1"
PWSH = shutil.which("pwsh")


@unittest.skipUnless(PWSH, "PowerShell 7 is required")
class PowerShellDoctorTests(unittest.TestCase):
    def run_pwsh(self, command: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["NO_COLOR"] = "1"
        environment.pop("LEAF_MEMORY_BIN", None)
        environment.pop("LEAF_MONDAY_INSTANCE", None)
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

    @staticmethod
    def make_layout(root: Path) -> None:
        for directory in ("bin", "core", "config", "share", "logs", "tests", "docs"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        for relative in (
            "config/brand.conf",
            "config/loaders.conf",
            "config/glyphs.conf",
            "config/runtime.json",
            "core/brand/brand.sh",
            "core/log/log.sh",
            "core/loaders/loaders.sh",
            "core/glyphs/glyphs.sh",
            "core/runtime/runtime.sh",
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n" if path.suffix == ".json" else "# fixture\n", encoding="utf-8")

    def report_for(self, root: Path) -> dict:
        escaped_root = str(root).replace("'", "''")
        command = (
            f"Import-Module '{MODULE}' -Force; "
            f"Get-LeafDoctorReport -Root '{escaped_root}' | ConvertTo-Json -Depth 10 -Compress"
        )
        result = self.run_pwsh(command)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def test_missing_native_memory_and_monday_are_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_layout(root)
            report = self.report_for(root)

        checks = {item["id"]: item for item in report["checks"]}
        self.assertEqual("not_ready", report["status"])
        self.assertFalse(report["ready"])
        self.assertFalse(report["capabilities"]["live_project"])
        self.assertFalse(checks["memory.native"]["ok"])
        self.assertFalse(checks["persona.monday"]["ok"])
        self.assertIn("make -C", checks["memory.native"]["repair"])
        self.assertEqual("run: leafos bloom init --json", checks["persona.monday"]["repair"])

    def test_monday_files_with_the_wrong_identity_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_layout(root)
            monday = root / "instances" / "monday-primary"
            monday.mkdir(parents=True)
            (monday / "persona.json").write_text(json.dumps({
                "schema": "leafos.continual-bloom-persona.v1",
                "instance_id": "monday-primary",
                "identity": {"key": "not-monday"},
            }), encoding="utf-8")
            (monday / "state.json").write_text(
                json.dumps({"instance_id": "monday-primary"}), encoding="utf-8"
            )
            (monday / "events.ndjson").write_text("", encoding="utf-8")
            (monday / "facts.ndjson").write_text("", encoding="utf-8")
            report = self.report_for(root)

        monday_check = next(item for item in report["checks"] if item["id"] == "persona.monday")
        self.assertFalse(monday_check["ok"])
        self.assertIn("identity contract", monday_check["detail"])

    def test_root_cli_json_is_a_machine_readable_exit_contract(self) -> None:
        environment = os.environ.copy()
        environment["NO_COLOR"] = "1"
        result = subprocess.run(
            [PWSH, "-NoProfile", "-File", ROOT_CLI, "doctor", "--json"],
            cwd=WORKSPACE,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        payload = json.loads(result.stdout)
        self.assertEqual("leafos.doctor_report", payload["leafos_object"])
        self.assertEqual(result.returncode == 0, payload["ready"])
        self.assertEqual(payload["ready"], payload["capabilities"]["live_project"])

    def test_unknown_doctor_option_is_rejected(self) -> None:
        result = subprocess.run(
            [PWSH, "-NoProfile", "-File", ROOT_CLI, "doctor", "--bogus"],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("unknown doctor option", result.stderr)

    def test_shared_doctor_rejects_the_same_missing_prerequisites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_layout(root)
            environment = os.environ.copy()
            environment.pop("LEAF_MEMORY_BIN", None)
            environment.pop("LEAF_MONDAY_INSTANCE", None)
            result = subprocess.run(
                [os.sys.executable, DOCTOR, "--root", root, "--json"],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )

        self.assertEqual(1, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        checks = {item["id"]: item for item in payload["checks"]}
        self.assertFalse(checks["memory.native"]["ok"])
        self.assertFalse(checks["persona.monday"]["ok"])


if __name__ == "__main__":
    unittest.main()
