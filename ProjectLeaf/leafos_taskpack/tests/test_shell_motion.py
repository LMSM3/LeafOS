from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PALETTE = ROOT / "core" / "brand" / "palette.sh"


@unittest.skipUnless(shutil.which("bash"), "bash is required for shell motion tests")
class ShellMotionContractTests(unittest.TestCase):
    def run_bash(self, script: str, **environment: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        for name in (
            "NO_ANIMATION",
            "LEAF_NO_ANIMATION",
            "REDUCE_MOTION",
            "LEAF_MOTION",
            "LEAF_ANIMATION_DELAY",
            "NO_EMOJI",
            "LEAF_NO_EMOJI",
            "LEAF_GLYPHS",
            "NO_COLOR",
            "FORCE_COLOR",
            "LEAF_COLOR",
        ):
            env.pop(name, None)
        env.update(environment)
        names = (
            "NO_ANIMATION LEAF_NO_ANIMATION REDUCE_MOTION LEAF_MOTION "
            "LEAF_ANIMATION_DELAY NO_EMOJI LEAF_NO_EMOJI LEAF_GLYPHS "
            "NO_COLOR FORCE_COLOR LEAF_COLOR"
        )
        exports = "; ".join(f"export {name}={shlex.quote(value)}" for name, value in environment.items())
        command = f"unset {names}; {exports + '; ' if exports else ''}source core/brand/palette.sh; {script}"
        return subprocess.run(
            ["bash", "-lc", command],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def test_auto_mode_is_static_when_stdout_is_redirected(self) -> None:
        result = self.run_bash('if leaf_motion_enabled; then exit 9; fi; leaf_transition "inspect" bloom 2 0')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("  [READY] inspect\n", result.stdout)
        self.assertNotIn("\r", result.stdout)
        self.assertNotIn("\x1b", result.stdout)

    def test_explicit_accessibility_flags_win_over_force(self) -> None:
        for variable in ("NO_ANIMATION", "LEAF_NO_ANIMATION", "REDUCE_MOTION"):
            with self.subTest(variable=variable):
                result = self.run_bash(
                    'if leaf_motion_enabled; then exit 9; fi; leaf_transition "safe" orbit 2 0',
                    LEAF_MOTION="always",
                    **{variable: "1"},
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("  [READY] safe\n", result.stdout)

    def test_forced_motion_uses_ascii_independently_from_color(self) -> None:
        result = self.run_bash(
            'leaf_transition "build" bloom 3 0',
            LEAF_MOTION="always",
            LEAF_NO_EMOJI="1",
            NO_COLOR="1",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("\x1b[2K", result.stdout)
        self.assertIn("[READY] build", result.stdout)
        self.assertNotIn("✿", result.stdout)
        self.assertNotIn("\x1b[38;", result.stdout)

    def test_no_color_does_not_disable_unicode_or_motion(self) -> None:
        result = self.run_bash(
            '_leaf_transition_frames bloom',
            LEAF_MOTION="always",
            NO_COLOR="1",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("✿", result.stdout)

    def test_invalid_delay_uses_supplied_fallback(self) -> None:
        result = self.run_bash('leaf_motion_delay 0.125', LEAF_ANIMATION_DELAY="quickly")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("0.125", result.stdout)


if __name__ == "__main__":
    unittest.main()
