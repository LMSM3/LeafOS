#!/usr/bin/env python3
from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "runtime"))

from gguf_metadata import GGUFError, read_metadata  # noqa: E402
from profile_resolver import resolve_manifest  # noqa: E402


def write_string(handle, value: str) -> None:
    encoded = value.encode("utf-8")
    handle.write(struct.pack("<Q", len(encoded)))
    handle.write(encoded)


def write_fixture(path: Path, context: int) -> None:
    entries = [
        ("general.name", 8, "Leaf Fixture"),
        ("general.architecture", 8, "llama"),
        ("llama.context_length", 4, context),
    ]
    with path.open("wb") as handle:
        handle.write(b"GGUF")
        handle.write(struct.pack("<IQQ", 3, 0, len(entries)))
        for key, value_type, value in entries:
            write_string(handle, key)
            handle.write(struct.pack("<I", value_type))
            if value_type == 8:
                write_string(handle, value)
            else:
                handle.write(struct.pack("<I", value))


class RuntimeCapabilityTests(unittest.TestCase):
    def test_reads_bounded_gguf_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "fixture.gguf"
            write_fixture(model, 65536)
            metadata = read_metadata(model)
            self.assertEqual("llama", metadata["architecture"])
            self.assertEqual(65536, metadata["context_length"])

    def test_supported_profile_uses_verified_model_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "fixture.gguf"
            write_fixture(model, 65536)
            manifest = resolve_manifest(ROOT / "config" / "runtime-profiles.json", "continual", "llama.cpp", str(model))
            self.assertEqual("continual", manifest["profile"])
            self.assertEqual("supported", manifest["capability_status"])
            self.assertEqual(65536, manifest["model_capabilities"]["context_limit"])
            self.assertGreaterEqual(
                manifest["reasoning_budget_requested"] + manifest["max_output_tokens"], 16384
            )

    def test_oversized_profile_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "fixture.gguf"
            write_fixture(model, 32768)
            manifest = resolve_manifest(ROOT / "config" / "runtime-profiles.json", "overnight", "llama.cpp", str(model))
            self.assertEqual("compat-4k", manifest["profile"])
            self.assertEqual("fallback", manifest["capability_status"])

    def test_rejects_non_gguf_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "broken.gguf"
            model.write_bytes(b"not gguf")
            with self.assertRaises(GGUFError):
                read_metadata(model)


if __name__ == "__main__":
    unittest.main()
