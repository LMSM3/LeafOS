#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FlowerSurfaceTests(unittest.TestCase):
    def test_operator_contract_names_surface_and_engine_without_renaming_engine_objects(self) -> None:
        config = json.loads((ROOT / "config" / "operator-experience.json").read_text(encoding="utf-8"))
        schema = json.loads((ROOT / "config" / "operator-experience.schema.json").read_text(encoding="utf-8"))
        self.assertEqual("leafos.operator-experience.v1", config["schema"])
        self.assertEqual("FlowerOS", config["surface"]["name"])
        self.assertEqual("LeafOS", config["surface"]["engine"])
        self.assertEqual("usage-layer", config["surface"]["stage"])
        self.assertEqual(".\\leafos.ps1 home", config["surface"]["default_command"])
        self.assertEqual("FlowerOS", schema["properties"]["surface"]["properties"]["name"]["const"])

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_powershell_flower_entrypoint_reaches_read_only_home(self) -> None:
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(ROOT / "bin" / "flower.ps1"), "home", "--json"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        state = json.loads(result.stdout)
        self.assertEqual("FlowerOS", state["operator"]["name"])
        self.assertEqual("LeafOS", state["operator"]["engine"])
        self.assertEqual("home_state", state["leafos_object"])
        benchmark_action = next(
            item["command"] for item in state["next_actions"] if item["label"] == "Check clean inference benchmark"
        )
        self.assertIn(str(ROOT / "config" / "inference-benchmark-matrix.json"), benchmark_action)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required")
    def test_powershell_flower_entrypoint_defaults_to_home(self) -> None:
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(ROOT / "bin" / "flower.ps1")],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("FlowerOS Home", result.stdout)

    def test_shell_flower_entrypoint_is_a_thin_engine_forwarder(self) -> None:
        text = (ROOT / "bin" / "flowerctl").read_text(encoding="utf-8")
        leafctl = (ROOT / "bin" / "leafctl").read_text(encoding="utf-8")
        self.assertIn("LEAF_UI_SURFACE=FlowerOS", text)
        self.assertIn('exec "$DIR/leafctl" "$@"', text)
        self.assertIn('LEAF_CALLER_SHELL="$caller_shell"', leafctl)


if __name__ == "__main__":
    unittest.main()
