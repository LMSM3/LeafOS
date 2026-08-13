from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


BRAND_DIR = Path(__file__).resolve().parents[1] / "core" / "brand"
UI_DIR = Path(__file__).resolve().parents[1] / "core" / "ui"
sys.path.insert(0, str(BRAND_DIR))
sys.path.insert(0, str(UI_DIR))

import flower_palette  # noqa: E402
import menu  # noqa: E402


COLOR_ENV = {"NO_COLOR", "FORCE_COLOR", "LEAF_COLOR", "NO_EMOJI", "LEAF_NO_EMOJI"}


class FlowerPaletteTests(unittest.TestCase):
    def environment(self, **values: str):
        clean = {key: value for key, value in os.environ.items() if key not in COLOR_ENV}
        clean.update(values)
        return mock.patch.dict(os.environ, clean, clear=True)

    def test_palette_sequences_have_no_invalid_parameter_spacing(self) -> None:
        for name, value in flower_palette.PALETTE.items():
            with self.subTest(name=name):
                self.assertNotIn("; ", value)
                self.assertNotIn(" ;", value)

    def test_no_color_wins_over_force_color(self) -> None:
        with self.environment(NO_COLOR="1", FORCE_COLOR="1"):
            self.assertTrue(flower_palette.no_color())
            self.assertEqual("ready", flower_palette.paint("ready", "leaf"))

    def test_either_force_color_variable_enables_color(self) -> None:
        with self.environment(FORCE_COLOR="0", LEAF_COLOR="true"):
            self.assertTrue(flower_palette.color_enabled())
            self.assertIn("\x1b[", flower_palette.paint("ready", "leaf"))

    def test_glyph_fallback_is_independent_from_color(self) -> None:
        with self.environment(NO_COLOR="1"):
            self.assertEqual("🌱", flower_palette.glyph("🌱", "LeafOS"))
        with self.environment(FORCE_COLOR="1", NO_EMOJI="1"):
            self.assertEqual("LeafOS", flower_palette.glyph("🌱", "LeafOS"))

    def test_menu_uses_ascii_fallback_only_when_requested(self) -> None:
        with self.environment(NO_COLOR="1", NO_EMOJI="1"):
            rendered = menu.render_menu("test", [{"label": "Ready", "glyph": "ok"}])
            self.assertIn("[ok] Ready", rendered)
            self.assertNotIn("\x1b[", rendered)
        with self.environment(FORCE_COLOR="1"):
            rendered = menu.render_menu("test", [{"label": "Ready", "glyph": "ok"}])
            self.assertIn("✓", rendered)
            self.assertIn("\x1b[", rendered)

    def test_menu_actions_resolve_the_repository_from_the_module_path(self) -> None:
        expected_root = Path(menu.__file__).resolve().parents[4]
        with self.environment():
            actions = menu._default_actions()
        self.assertTrue(actions)
        leaf_actions = [action for action in actions if action.get("category") != "FlowerOS layer"]
        self.assertTrue(
            all(str(expected_root) in action["command"] for action in leaf_actions if not action.get("disabled", False))
        )
        flower_root = expected_root.parent / "FlowerOS"
        flower_actions = [action for action in actions if action.get("category") == "FlowerOS layer"]
        self.assertTrue(all(str(flower_root) in action["command"] for action in flower_actions))
        self.assertTrue(all(r"C:\R\LeafOS0.2.2" not in action["command"] for action in actions))


if __name__ == "__main__":
    unittest.main()
