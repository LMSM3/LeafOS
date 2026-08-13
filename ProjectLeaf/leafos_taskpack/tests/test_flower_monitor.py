#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


TASKPACK = Path(__file__).resolve().parents[1]
LEAFOS_ROOT = TASKPACK.parents[1]
SOURCE = TASKPACK / "core" / "monitor" / "flower.c"


class FlowerMonitorIntegrationTests(unittest.TestCase):
    def test_c_source_is_present_and_linux_metric_driven(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn('#define TARGET_HZ 60.0', text)
        self.assertIn('fopen("/proc/stat", "r")', text)
        self.assertIn('fopen("/proc/meminfo", "r")', text)
        self.assertIn("statvfs(root, &stats)", text)
        self.assertIn('getenv("LEAFOS_ROOT")', text)
        self.assertIn("leafos.flower_monitor_snapshot", text)
        self.assertIn('strcmp(argv[index], "--once")', text)
        self.assertIn("render_diff", text)

    def test_launcher_binds_monitor_to_canonical_leafos_root(self) -> None:
        text = (TASKPACK / "bin" / "flower-monitor").read_text(encoding="utf-8")
        self.assertIn('CANONICAL_LEAFOS_ROOT="$(cd "$TASKPACK_ROOT/../.." && pwd)"', text)
        self.assertIn('export LEAFOS_ROOT="${LEAFOS_ROOT:-$CANONICAL_LEAFOS_ROOT}"', text)
        bridge = (TASKPACK / "bin" / "flower-monitor.ps1").read_text(encoding="utf-8")
        self.assertIn("--exec wslpath -a -u", bridge)
        self.assertIn("& $Wsl.Source --exec bash", bridge)

    def test_makefile_builds_monitor_with_math_library(self) -> None:
        text = (TASKPACK / "Makefile").read_text(encoding="utf-8")
        self.assertIn("FLOWER_MONITOR_SRC := $(ROOT)core/monitor/flower.c", text)
        self.assertRegex(text, r"\$\(CC\).*\$<.*-lm")

    def test_monitor_has_at_least_eight_command_routes(self) -> None:
        readme = (TASKPACK / "README.md").read_text(encoding="utf-8")
        section = readme.split("The same monitor is available through every supported command layer:", 1)[1]
        command_block = section.split("```text", 1)[1].split("```", 1)[0]
        routes = [line.strip() for line in command_block.splitlines() if line.strip()]
        self.assertGreaterEqual(len(routes), 8)
        self.assertEqual(len(routes), len(set(routes)))

        shell_router = (TASKPACK / "bin" / "leafctl").read_text(encoding="utf-8")
        ps_router = (TASKPACK / "bin" / "leafctl.ps1").read_text(encoding="utf-8")
        self.assertIn("flower-monitor|monitor)", shell_router)
        self.assertIn("@('flower-monitor', 'monitor')", ps_router)

    def test_all_documented_route_files_exist(self) -> None:
        expected = (
            TASKPACK / "bin" / "flower-monitor",
            TASKPACK / "bin" / "flowerctl",
            TASKPACK / "bin" / "leafctl",
            TASKPACK / "bin" / "flower.ps1",
            TASKPACK / "bin" / "leafctl.ps1",
            LEAFOS_ROOT / "Bash-Version" / "leaf.sh",
            LEAFOS_ROOT / "PowerShell-Version" / "leaf.ps1",
            LEAFOS_ROOT / "leafos.sh",
            LEAFOS_ROOT / "leafos.ps1",
        )
        self.assertGreaterEqual(len(expected), 8)
        self.assertTrue(all(path.is_file() for path in expected))

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_powershell_router_resolves_canonical_source(self) -> None:
        result = subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-File",
                str(TASKPACK / "bin" / "leafctl.ps1"),
                "flower-monitor",
                "--source",
            ],
            cwd=TASKPACK,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        resolved = Path(result.stdout.strip()).resolve()
        self.assertEqual(SOURCE.resolve(), resolved)

    @unittest.skipUnless(
        shutil.which("pwsh") and shutil.which("wsl"),
        "PowerShell 7 and WSL are required",
    )
    def test_root_entrypoint_binds_canonical_directory_inside_wsl(self) -> None:
        result = subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-File",
                str(LEAFOS_ROOT / "leafos.ps1"),
                "flower-monitor",
                "--root-path",
            ],
            cwd=LEAFOS_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        expected = subprocess.run(
            ["wsl", "--exec", "wslpath", "-a", "-u", str(LEAFOS_ROOT)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        self.assertEqual(0, expected.returncode, expected.stderr)
        self.assertEqual(expected.stdout.strip(), result.stdout.strip())

    def test_authoritative_version_meets_normalized_baseline(self) -> None:
        version = (TASKPACK / "VERSION").read_text(encoding="utf-8").strip()
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(tuple(map(int, match.groups())), (0, 2, 2))
        self.assertEqual(version, (LEAFOS_ROOT / "VERSION").read_text(encoding="utf-8").strip())

    def test_both_root_validators_require_primary_reference_outputs(self) -> None:
        powershell = (LEAFOS_ROOT / "Validate-RootContract.ps1").read_text(encoding="utf-8")
        bash = (LEAFOS_ROOT / "leafos.sh").read_text(encoding="utf-8")
        for key in ("primary_reference", "primary_reference_tex"):
            self.assertIn(key, powershell)
            self.assertIn(key, bash)
        for contract_check in ("VERSION", "sha256", "immutable", "brand-asset:start"):
            self.assertIn(contract_check, powershell)
            self.assertIn(contract_check, bash)

    def test_root_contract_integrates_change_loop_without_implementing_future_tasks(self) -> None:
        metadata = json.loads((LEAFOS_ROOT / "leafos.root.json").read_text(encoding="utf-8"))
        change_loop = metadata["change_loop"]
        for key in ("ccis_cli", "scientific_loop", "typed_task_registry", "series_index", "next_work_order"):
            self.assertTrue((LEAFOS_ROOT / change_loop[key]).is_file(), key)

        registry = json.loads(
            (LEAFOS_ROOT / change_loop["typed_task_registry"]).read_text(encoding="utf-8")
        )
        entries = {item["task_type"]: item for item in registry["entries"]}
        self.assertEqual("implemented", entries["probe.llamacpp.capability"]["status"])
        self.assertEqual(
            "ccis.probe.llamacpp.capability",
            entries["probe.llamacpp.capability"]["native_handler"],
        )
        for task_type in ("eval.llamacpp.grammar", "eval.llamacpp.stream"):
            self.assertEqual("reserved", entries[task_type]["status"])
            self.assertIsNone(entries[task_type]["native_handler"])


if __name__ == "__main__":
    unittest.main()
