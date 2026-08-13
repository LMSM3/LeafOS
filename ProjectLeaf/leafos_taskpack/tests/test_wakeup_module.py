#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "examples" / "WO-004-C"


class WakeupModuleTests(unittest.TestCase):
    def test_latest_result_matches_runtime_contract(self) -> None:
        result = json.loads((MODULE / "runs" / "latest" / "wakeup_result.json").read_text(encoding="utf-8"))
        self.assertEqual("leafos_wakeup_result", result["leafos_object"])
        self.assertIn(result["branch"], {"heads", "tails"})
        self.assertEqual("WO-004-C", result["context"]["work_order"])

    def test_verified_export_is_selective(self) -> None:
        archives = sorted((MODULE / "exports").glob("WO-004-C_wakeup_*_verified.zip"))
        self.assertTrue(archives, "verified wakeup export is missing")
        with zipfile.ZipFile(archives[-1]) as archive:
            names = set(archive.namelist())
        self.assertIn("wakeup.py", names)
        self.assertIn("tests/test_wakeup_shell.sh", names)
        self.assertIn("docs/wakeup_node.md", names)
        self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))


if __name__ == "__main__":
    unittest.main()
