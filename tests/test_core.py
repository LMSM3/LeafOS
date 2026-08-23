from __future__ import annotations

import json
import os
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.sys.path.insert(0, str(ROOT))

from core.config import ConfigError, load_settings
from core.models.gguf import GGUFError, inspect_gguf
from core.models.inventory import ModelError, local_model_path, resolve_model, scan_model_dirs
from core.routing.packs import PackError, load_pack, validate_pack


class ReducedCoreTests(unittest.TestCase):
    def test_repository_config_is_small_and_valid(self) -> None:
        settings = load_settings(ROOT)
        self.assertEqual(settings.context, 4096)
        self.assertLess((ROOT / "config" / "leaf.conf").stat().st_size, 1024)

    def test_missing_config_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ConfigError):
                load_settings(Path(directory))

    def test_empty_scan_does_not_invent_models(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inventory = scan_model_dirs((Path(directory),), runtime_available=True)
        self.assertEqual(inventory["summary"], {"found": 0, "usable": 0, "invalid": 0})

    def test_bad_gguf_is_reported_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "decorative.gguf"
            model.write_bytes(b"not a model")
            inventory = scan_model_dirs((Path(directory),), runtime_available=True)
        self.assertEqual(inventory["summary"]["usable"], 0)
        self.assertEqual(inventory["models"][0]["load_status"], "invalid")

    def test_parser_fixture_is_metadata_only_not_runtime_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "parser-Q4_K_M.gguf"
            values = [("general.architecture", 8, "llama"), ("general.file_type", 4, 15)]
            payload = bytearray(b"GGUF" + struct.pack("<IQQ", 3, 0, len(values)))
            for key, value_type, value in values:
                encoded = key.encode()
                payload += struct.pack("<Q", len(encoded)) + encoded + struct.pack("<I", value_type)
                if value_type == 8:
                    raw = value.encode()
                    payload += struct.pack("<Q", len(raw)) + raw
                else:
                    payload += struct.pack("<I", value)
            model.write_bytes(payload)
            record = inspect_gguf(model, runtime_available=False)
        self.assertEqual(record["architecture"], "llama")
        self.assertEqual(record["quant"], "Q4_K_M")
        self.assertFalse(record["runtime_compatible"])

    def test_truncated_tensor_data_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "truncated-Q4_K_M.gguf"
            key = b"general.architecture"
            payload = bytearray(b"GGUF" + struct.pack("<IQQ", 3, 1, 1))
            payload += struct.pack("<Q", len(key)) + key + struct.pack("<I", 8)
            payload += struct.pack("<Q", 5) + b"llama"
            name = b"weight"
            payload += struct.pack("<Q", len(name)) + name
            payload += struct.pack("<IQQIQ", 2, 4096, 4096, 12, 0)
            model.write_bytes(payload)
            with self.assertRaises(GGUFError):
                inspect_gguf(model, runtime_available=True)

    def test_missing_model_reference_fails(self) -> None:
        with self.assertRaises(ModelError):
            resolve_model({"models": []}, "imaginary.gguf")

    def test_model_paths_translate_between_windows_and_wsl(self) -> None:
        self.assertEqual(
            local_model_path(r"C:\Users\leaf\.leaf\models\a.gguf", "posix").as_posix(),
            "/mnt/c/Users/leaf/.leaf/models/a.gguf",
        )
        self.assertEqual(
            str(local_model_path("/mnt/c/Users/leaf/.leaf/models/a.gguf", "nt")).replace("\\", "/"),
            "C:/Users/leaf/.leaf/models/a.gguf",
        )

    def test_pack_with_missing_model_is_not_usable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fake.json"
            path.write_text(json.dumps({"schema": "leafos.pack.v1", "id": "fake", "name": "Fake", "lanes": {"brain": "imaginary"}}))
            pack = load_pack(path)
            errors = validate_pack(pack, {"models": []})
        self.assertTrue(errors)

    def test_malformed_pack_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(PackError):
                load_pack(path)


if __name__ == "__main__":
    unittest.main()
