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
PWSH = shutil.which("pwsh")


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    if MSYS_BASH.is_file():
        environment["PATH"] = ";".join((
            "C:\\msys64\\ucrt64\\bin",
            "C:\\msys64\\usr\\bin",
            environment.get("PATH", ""),
        ))
    return environment


@unittest.skipUnless(BASH and PWSH, "Bash and PowerShell 7 are required")
class GlyphObjectTests(unittest.TestCase):
    def run_bash(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [BASH, "./bin/leafctl", *args],
            cwd=ROOT,
            env=_environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )

    def run_powershell(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PWSH, "-NoProfile", "-File", str(ROOT / "bin" / "leafctl.ps1"), *args],
            cwd=ROOT,
            env=_environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )

    def test_schema_defines_complete_glyph_object(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "leafos.glyph.v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual("LeafOS Glyph Object", schema["title"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            {
                "leafos_object",
                "version",
                "alias",
                "glyph",
                "codepoints",
                "category",
                "severity",
                "ascii",
                "meaning",
                "render_mode",
            },
            set(schema["required"]),
        )

    def test_single_glyph_object_matches_across_shells(self) -> None:
        bash_result = self.run_bash("glyph", "leaf.verify", "--ascii", "--json")
        ps_result = self.run_powershell("glyph", "leaf.verify", "--ascii", "--json")
        self.assertEqual(0, bash_result.returncode, bash_result.stderr)
        self.assertEqual(0, ps_result.returncode, ps_result.stderr)
        bash_object = json.loads(bash_result.stdout)
        ps_object = json.loads(ps_result.stdout)
        self.assertEqual(bash_object, ps_object)
        self.assertEqual("[ok]", bash_object["glyph"])

    def test_filtered_registry_matches_across_shells(self) -> None:
        bash_result = self.run_bash("glyphs", "status", "--ascii", "--json")
        ps_result = self.run_powershell("glyphs", "status", "--ascii", "--json")
        self.assertEqual(0, bash_result.returncode, bash_result.stderr)
        self.assertEqual(0, ps_result.returncode, ps_result.stderr)
        bash_object = json.loads(bash_result.stdout)
        ps_object = json.loads(ps_result.stdout)
        self.assertEqual(bash_object, ps_object)
        self.assertEqual(bash_object["count"], len(bash_object["glyphs"]))
        self.assertIn("leaf.status.blocked", {item["alias"] for item in bash_object["glyphs"]})

    def test_unknown_alias_fails_in_both_shells(self) -> None:
        bash_result = self.run_bash("glyph", "leaf.does.not.exist", "--json")
        ps_result = self.run_powershell("glyph", "leaf.does.not.exist", "--json")
        self.assertNotEqual(0, bash_result.returncode)
        self.assertNotEqual(0, ps_result.returncode)
        self.assertIn("unknown glyph alias", bash_result.stderr)
        self.assertIn("unknown glyph alias", ps_result.stderr)


if __name__ == "__main__":
    unittest.main()
