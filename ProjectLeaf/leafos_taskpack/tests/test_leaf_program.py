from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "core" / "python" / "leaf_program.py"
SPEC = importlib.util.spec_from_file_location("leaf_program", MODULE_PATH)
assert SPEC and SPEC.loader
leaf_program = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(leaf_program)


class LeafProgramTests(unittest.TestCase):
    def test_permanent_asset_matches_manifest(self) -> None:
        asset, manifest = leaf_program.verify_asset()
        self.assertEqual(manifest["sha256"], leaf_program.sha256(asset))
        self.assertTrue(asset.name.endswith(str(manifest["sha256"])[:16] + ".png"))

    def test_branding_follows_badge_block_and_is_idempotent(self) -> None:
        asset, _ = leaf_program.verify_asset()
        with tempfile.TemporaryDirectory(dir=leaf_program.ROOT) as temporary:
            readme = Path(temporary) / "README.md"
            original = "# LeafOS\n\n### Durable work\n\n![Snapshot](https://img.shields.io/badge/snapshot-0.9.4-green)\n![Status](https://img.shields.io/badge/status-new-blue)\n\nBody.\n"
            once = leaf_program.branded_readme(original, readme, asset)
            twice = leaf_program.branded_readme(once, readme, asset)
            self.assertEqual(once, twice)
            self.assertLess(once.index("![Status]"), once.index(leaf_program.START))
            self.assertLess(once.index(leaf_program.END), once.index("Body."))
            self.assertIn("../assets/brand/immutable/", once)

    def test_root_readme_is_linked(self) -> None:
        asset, _ = leaf_program.verify_asset()
        self.assertTrue(leaf_program.readme_has_asset(leaf_program.ROOT / "README.md", asset))

    def test_default_listing_skips_archives(self) -> None:
        self.assertFalse(any(path.casefold().startswith("archive/") for path in leaf_program.list_readmes()))

    def test_version_requires_numeric_semver(self) -> None:
        with self.assertRaises(leaf_program.ProgramError):
            leaf_program.change_version("new", ["README.md"], True)

    def test_readme_target_cannot_escape_root(self) -> None:
        with self.assertRaises(leaf_program.ProgramError):
            leaf_program.target_path(leaf_program.ROOT.parent / "README.md")

    def test_version_updates_badge_and_bold_snapshot_copy(self) -> None:
        source = "![Snapshot](https://img.shields.io/badge/snapshot-0.9.4-green)\n**partially working **0.9.4 snapshot****"
        result = leaf_program._versioned_readme(source, "0.9.4", "0.9.5")
        self.assertNotIn("0.9.4", result)
        self.assertEqual(2, result.count("0.9.5"))

    def test_markdown_split_detects_spaced_chains_but_ignores_fences(self) -> None:
        source = "# One\nA\n____________\n# Two\nB\n```text\n------------\n```\n- - - - - - - - - - - -\n# Three\nC\n"
        parts, separators = leaf_program.split_sections(source)
        self.assertEqual(2, separators)
        self.assertEqual(3, len(parts))
        self.assertIn("------------", parts[1])

    def test_markdown_split_writes_managed_parts_without_touching_source(self) -> None:
        with tempfile.TemporaryDirectory(dir=leaf_program.ROOT) as temporary:
            source = Path(temporary) / "notes.md"
            content = "# First\nA\n------------\n## Second section\nB\n"
            source.write_text(content, encoding="utf-8")
            preview = leaf_program.split_markdown(str(source), None, True)
            self.assertEqual(2, preview["parts"])
            self.assertFalse(preview["written"])
            result = leaf_program.split_markdown(str(source), None, False)
            self.assertTrue(result["written"])
            self.assertEqual(content, source.read_text(encoding="utf-8"))
            output = Path(str(result["output"]))
            self.assertTrue((output / ".leafos-program-split.json").is_file())
            self.assertEqual(2, len(list(output.glob("*.md"))))


if __name__ == "__main__":
    unittest.main()
