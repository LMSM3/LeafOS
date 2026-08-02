#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TASKPACK = Path(__file__).resolve().parents[1]
LEAFOS_ROOT = TASKPACK.parents[1]
MSYS_BASH = Path("C:/msys64/usr/bin/bash.exe")
BASH = str(MSYS_BASH) if MSYS_BASH.is_file() else shutil.which("bash")
PWSH = shutil.which("pwsh")
sys.path.insert(0, str(TASKPACK / "core" / "ui"))

from quick_syntax import load_contract, render  # noqa: E402
from reference import build_state as build_reference_state  # noqa: E402


EXPECTED = {
    "q": ["quick"],
    "h": ["home"],
    "s": ["status"],
    "d": ["doctor"],
    "r": ["runtime", "select"],
    "p": ["provider-stack", "check"],
    "t": ["trace", "latest"],
    "ref": ["reference"],
    "b": ["bloom", "status"],
    "m": ["flower-monitor"],
    "c": ["chat"],
    "go": ["live"],
}


def bash_environment() -> dict[str, str]:
    environment = os.environ.copy()
    if MSYS_BASH.is_file():
        environment["PATH"] = ";".join((
            "C:\\msys64\\ucrt64\\bin",
            "C:\\msys64\\usr\\bin",
            environment.get("PATH", ""),
        ))
    return environment


class QuickSyntaxContractTests(unittest.TestCase):
    def test_contract_is_unique_fixed_token_and_plain_text_accessible(self) -> None:
        contract = load_contract()
        aliases = {entry["alias"]: entry["expansion"] for entry in contract["entries"]}
        self.assertEqual(EXPECTED, aliases)
        self.assertEqual(len(aliases), len(contract["entries"]))
        card = render(contract)
        card.encode("ascii")
        self.assertIn("FlowerOS quick syntax (LeafOS engine)", card)
        self.assertIn("Shortcuts expand fixed command tokens", card)
        self.assertIn("leafos q --json", card)

    def test_reference_route_finds_both_primary_outputs(self) -> None:
        state = build_reference_state()
        self.assertEqual("available", state["status"])
        self.assertTrue(Path(str(state["markdown"])).is_file())
        self.assertTrue(Path(str(state["tex"])).is_file())

    def test_aliases_are_declared_in_both_native_routers(self) -> None:
        bash = (TASKPACK / "bin" / "leafctl").read_text(encoding="utf-8")
        powershell = (TASKPACK / "bin" / "leafctl.ps1").read_text(encoding="utf-8")
        for alias in EXPECTED:
            self.assertIn(f"{alias})" if len(alias) > 1 else f"{alias})", bash)
            self.assertIn(f"'{alias}'", powershell)
        self.assertIn("try: leafos q", bash)
        self.assertIn("leafos.ps1 q", powershell)

    def test_post_install_surfaces_advertise_quick_syntax(self) -> None:
        files = (
            LEAFOS_ROOT / "PowerShell-Version" / "install.ps1",
            LEAFOS_ROOT / "Bash-Version" / "install.sh",
            TASKPACK / "bin" / "post_install.sh",
            TASKPACK / "bin" / "install_demo.sh",
            TASKPACK / "bin" / "install_mac.sh",
        )
        for path in files:
            self.assertIn("leafos", path.read_text(encoding="utf-8").lower(), path)
            self.assertIn(" q", path.read_text(encoding="utf-8"), path)


@unittest.skipUnless(PWSH, "PowerShell 7 is required")
class PowerShellQuickSyntaxTests(unittest.TestCase):
    def run_leafos(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PWSH, "-NoProfile", "-File", str(LEAFOS_ROOT / "leafos.ps1"), *args],
            cwd=LEAFOS_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )

    def test_quick_home_and_reference_shortcuts_execute(self) -> None:
        quick = self.run_leafos("q", "--json")
        self.assertEqual(0, quick.returncode, quick.stderr)
        self.assertEqual("leafos.quick-syntax.v1", json.loads(quick.stdout)["schema"])

        home = self.run_leafos("h", "--json")
        self.assertEqual(0, home.returncode, home.stderr)
        self.assertEqual("home_state", json.loads(home.stdout)["leafos_object"])

        reference = self.run_leafos("ref", "--json")
        self.assertEqual(0, reference.returncode, reference.stderr)
        self.assertEqual("available", json.loads(reference.stdout)["status"])

    def test_application_installer_creates_verified_alias_launchers_without_path_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            installer = str(LEAFOS_ROOT / "PowerShell-Version" / "install-leafos.ps1")
            plan_result = subprocess.run(
                [
                    PWSH,
                    "-NoProfile",
                    "-File",
                    installer,
                    "-Action",
                    "plan",
                    "-Prefix",
                    directory,
                ],
                cwd=LEAFOS_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
            self.assertEqual(0, plan_result.returncode, plan_result.stderr)
            plan = json.loads(plan_result.stdout)
            self.assertEqual(6, len(plan["entrypoints"]))
            self.assertEqual("print opt-in instructions only", plan["path_integration"])
            self.assertIn("no PATH mutation", plan["safety"])

            apply_result = subprocess.run(
                [PWSH, "-NoProfile", "-File", installer, "-Action", "apply", "-Prefix", directory],
                cwd=LEAFOS_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
            )
            self.assertEqual(0, apply_result.returncode, apply_result.stderr)

            verify_result = subprocess.run(
                [PWSH, "-NoProfile", "-File", installer, "-Action", "verify", "-Prefix", directory],
                cwd=LEAFOS_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
            )
            self.assertEqual(0, verify_result.returncode, verify_result.stderr)
            verified = json.loads(verify_result.stdout)
            self.assertTrue(verified["verified"])
            self.assertEqual(6, len(verified["entrypoints"]))
            self.assertFalse(verified["on_user_path"])

            quick_result = subprocess.run(
                [
                    PWSH,
                    "-NoProfile",
                    "-File",
                    str(Path(directory) / "bin" / "leafos.ps1"),
                    "q",
                    "--json",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            self.assertEqual(0, quick_result.returncode, quick_result.stderr)
            self.assertEqual("leafos.quick-syntax.v1", json.loads(quick_result.stdout)["schema"])

            home_result = subprocess.run(
                [PWSH, "-NoProfile", "-File", str(Path(directory) / "bin" / "leafos.ps1")],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            self.assertEqual(0, home_result.returncode, home_result.stderr)
            self.assertIn("FlowerOS Home", home_result.stdout)

            reference_result = subprocess.run(
                [
                    PWSH,
                    "-NoProfile",
                    "-File",
                    str(Path(directory) / "bin" / "flower.ps1"),
                    "ref",
                    "--json",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            self.assertEqual(0, reference_result.returncode, reference_result.stderr)
            self.assertEqual("available", json.loads(reference_result.stdout)["status"])

            if os.name == "nt":
                cmd_result = subprocess.run(
                    [str(Path(directory) / "bin" / "leaf.cmd"), "q", "--json"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=False,
                )
                self.assertEqual(0, cmd_result.returncode, cmd_result.stderr)
                self.assertEqual("leafos.quick-syntax.v1", json.loads(cmd_result.stdout)["schema"])


@unittest.skipUnless(BASH, "Bash is required")
class BashQuickSyntaxTests(unittest.TestCase):
    def run_leafos(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [BASH, "./bin/flowerctl", *args],
            cwd=TASKPACK,
            env=bash_environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )

    def test_quick_home_and_reference_shortcuts_execute(self) -> None:
        quick = self.run_leafos("q", "--json")
        self.assertEqual(0, quick.returncode, quick.stderr)
        self.assertEqual("leafos.quick-syntax.v1", json.loads(quick.stdout)["schema"])

        home = self.run_leafos("h", "--json")
        self.assertEqual(0, home.returncode, home.stderr)
        self.assertEqual("home_state", json.loads(home.stdout)["leafos_object"])

        reference = self.run_leafos("ref", "--json")
        self.assertEqual(0, reference.returncode, reference.stderr)
        self.assertEqual("available", json.loads(reference.stdout)["status"])

    def test_changed_bash_installers_parse(self) -> None:
        for path in (
            LEAFOS_ROOT / "Bash-Version" / "install.sh",
            TASKPACK / "bin" / "post_install.sh",
            TASKPACK / "bin" / "install_demo.sh",
            TASKPACK / "bin" / "install_mac.sh",
        ):
            result = subprocess.run(
                [BASH, "-n", str(path)],
                env=bash_environment(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
            self.assertEqual(0, result.returncode, f"{path}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
