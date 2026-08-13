#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TASKPACK_ROOT = Path(__file__).resolve().parents[1]
CORE = TASKPACK_ROOT / "core"
INSTALLER_ROOT = TASKPACK_ROOT.parent / "leaf_model_installer"
for directory in (CORE, INSTALLER_ROOT):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from leaf_models.orchestrator import create_pack_plan  # noqa: E402
import pack_constructor_cli  # noqa: E402
from pack_constructor import (  # noqa: E402
    PackConstructorError,
    build_pack,
    load_catalog,
    validate_pack,
    write_pack,
)


class PackConstructorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog()

    def test_runtime_default_is_small_valid_and_installer_compatible(self) -> None:
        pack = build_pack(self.catalog, name="Pocket Meadow", profile="runtime-default")
        report = validate_pack(pack, self.catalog)

        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual("pocket-meadow", pack["id"])
        self.assertEqual(2, report["summary"]["unique_artifacts"])
        self.assertEqual(1, pack["policy"]["max_concurrent_local_models"])
        self.assertFalse(pack["presentation"]["capability_bearing"])
        self.assertEqual(
            "leafos.subsystem_indicator_evidence.v1",
            pack["presentation"]["indicator_evidence_contract"],
        )
        self.assertNotIn("groups", pack)
        self.assertNotIn("role_policy", pack)

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pocket-meadow.json"
            write_pack(path, pack)
            plan = create_pack_plan(pack_path=path)
        self.assertEqual(2, len(plan.items))
        self.assertEqual("pocket-meadow", plan.profile)

    def test_explicit_models_support_quants_and_exact_deduplication(self) -> None:
        pack = build_pack(
            self.catalog,
            name="Coder Sprig",
            model_specs=["1:Q2_K", "gemma4-coder:Q2_K", "gemma4-coder:Q6_K"],
        )
        self.assertEqual(
            [
                {"catalog_key": "gemma4-coder", "quant": "Q2_K"},
                {"catalog_key": "gemma4-coder", "quant": "Q6_K"},
            ],
            pack["install"]["items"],
        )
        report = validate_pack(pack, self.catalog)
        self.assertTrue(report["ok"], report["errors"])
        self.assertTrue(any("quantizations" in warning for warning in report["warnings"]))

    def test_experimental_models_require_explicit_opt_in(self) -> None:
        with self.assertRaisesRegex(PackConstructorError, "experimental"):
            build_pack(self.catalog, name="Sleeping Giant", model_specs=["gpt-oss-120b"])

        pack = build_pack(
            self.catalog,
            name="Sleeping Giant",
            model_specs=["gpt-oss-120b"],
            include_experimental=True,
        )
        self.assertEqual(
            ["gpt-oss-120b"],
            pack["requirements"]["experimental_confirmation_keys"],
        )

    def test_invalid_quant_is_rejected(self) -> None:
        with self.assertRaisesRegex(PackConstructorError, "valid quantizations"):
            build_pack(self.catalog, name="Bad Quant", model_specs=["gemma4-coder:NOPE"])

    def test_existing_viola_pack_remains_valid_with_legacy_identity_warnings(self) -> None:
        path = TASKPACK_ROOT / "config" / "packs" / "viola-nocturne.json"
        report = validate_pack(json.loads(path.read_text(encoding="utf-8")), self.catalog)
        self.assertTrue(report["ok"], report["errors"])
        self.assertTrue(any("canonical flower" in warning for warning in report["warnings"]))

    def test_write_refuses_silent_overwrite(self) -> None:
        pack = build_pack(self.catalog, name="Safe Seed", model_specs=["gemma4-coder"])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "safe-seed.json"
            write_pack(path, pack)
            with self.assertRaisesRegex(PackConstructorError, "refusing to overwrite"):
                write_pack(path, pack)

    def test_json_cli_writes_machine_readable_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "cli-bloom.json"
            environment = os.environ.copy()
            environment.update({"NO_COLOR": "1", "NO_ANIMATION": "1", "LEAF_GLYPHS": "ascii"})
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(CORE / "pack_constructor_cli.py"),
                    "create",
                    "--name",
                    "CLI Bloom",
                    "--model",
                    "gemma4-coder:Q2_K",
                    "--flower",
                    "clover",
                    "--colour",
                    "green",
                    "--output",
                    str(output),
                    "--yes",
                    "--json",
                    "--no-animation",
                ],
                cwd=TASKPACK_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual("written", payload["state"])
            self.assertEqual("clover", payload["pack"]["identity"]["flower"])
            self.assertTrue(output.is_file())

    def test_motion_is_accessible_and_never_animates_redirected_output(self) -> None:
        motion_environment = {
            key: value
            for key, value in os.environ.items()
            if key not in {
                "CI", "NO_ANIMATION", "LEAF_NO_ANIMATION", "REDUCE_MOTION", "LEAF_MOTION", "TERM"
            }
        }
        with mock.patch.dict(os.environ, motion_environment, clear=True):
            with mock.patch.object(pack_constructor_cli.sys, "stdout", mock.Mock(isatty=lambda: True)):
                self.assertTrue(pack_constructor_cli._motion_enabled())
                os.environ["LEAF_NO_ANIMATION"] = "1"
                self.assertFalse(pack_constructor_cli._motion_enabled())
                os.environ.pop("LEAF_NO_ANIMATION")
                os.environ["LEAF_MOTION"] = "reduced"
                self.assertFalse(pack_constructor_cli._motion_enabled())
            os.environ["LEAF_MOTION"] = "always"
            with mock.patch.object(pack_constructor_cli.sys, "stdout", mock.Mock(isatty=lambda: False)):
                self.assertFalse(pack_constructor_cli._motion_enabled())


if __name__ == "__main__":
    unittest.main()
