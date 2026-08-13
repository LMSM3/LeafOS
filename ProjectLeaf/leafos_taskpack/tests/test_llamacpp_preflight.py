#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import stat
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TASKPACK = Path(__file__).resolve().parents[1]
LEAFOS_ROOT = TASKPACK.parents[1]
sys.path.insert(0, str(LEAFOS_ROOT))
sys.path.insert(0, str(TASKPACK / "core" / "runtime"))

from ccis.kernel import storage, task_registry  # noqa: E402
from llamacpp_preflight import OPT_IN_ENV, probe  # noqa: E402


def write_model(path: Path, *, magic: bytes = b"GGUF", version: int = 3) -> None:
    path.write_bytes(magic + struct.pack("<I", version) + b"fixture-payload")


def write_fake_llama(path: Path, calls: Path, *, devices: str = "Vulkan0 NVIDIA RTX fixture") -> Path:
    if os.name == "nt":
        path = path.with_suffix(".cmd")
        path.write_text(
            "@echo off\n"
            f">>\"{calls}\" echo %1\n"
            "if \"%1\"==\"--version\" (echo llama.cpp version b4242 commit abcdef123& exit /b 0)\n"
            f"if \"%1\"==\"--list-devices\" (echo {devices}& exit /b 0)\n"
            "exit /b 9\n",
            encoding="utf-8",
        )
    else:
        path.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$1\" >> '{calls}'\n"
            "case \"$1\" in\n"
            "  --version) echo 'llama.cpp version b4242 commit abcdef123'; exit 0 ;;\n"
            f"  --list-devices) echo '{devices}'; exit 0 ;;\n"
            "  *) exit 9 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class LlamaCppPreflightTests(unittest.TestCase):
    def fixture(self, root: Path, *, devices: str = "Vulkan0 NVIDIA RTX fixture") -> tuple[Path, Path, Path]:
        calls = root / "calls.txt"
        executable = write_fake_llama(root / "llama-cli", calls, devices=devices)
        model = root / "model.gguf"
        write_model(model)
        return executable, model, calls

    def test_opt_in_gate_blocks_without_touching_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable, model, calls = self.fixture(Path(temporary))
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(OPT_IN_ENV, None)
                result = probe(executable=executable, model=model, backend="vulkan")
            self.assertFalse(result["capable"])
            self.assertEqual("preflight_only", result["mode"])
            self.assertEqual(["OPT_IN_REQUIRED"], [item["code"] for item in result["failures"]])
            self.assertFalse(calls.exists())
            self.assertFalse(result["inference_started"])
            self.assertFalse(result["server_started"])
            self.assertFalse(result["network_used"])

    def test_native_typed_task_returns_digest_bound_preflight_only_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable, model, calls = self.fixture(Path(temporary))
            task = task_registry.adapt_llamacpp_capability(
                executable, model, "vulkan", expected_version="b4242", task_id="llamacpp-preflight-pass"
            )
            self.assertEqual("ccis.probe.llamacpp.capability", task["native_handler"])
            self.assertEqual(
                {"cpu", f"model:{model.resolve()}", "gpu:vulkan"},
                {claim["resource"] for claim in task["resource_claims"]},
            )
            with mock.patch.dict(os.environ, {OPT_IN_ENV: "1"}):
                result = task_registry.execute_typed_task(task, {})
            capability = result["output"]["capability"]
            self.assertEqual("SUCCEEDED", result["status"])
            self.assertTrue(capability["capable"])
            self.assertEqual(task["task_digest"], capability["task_digest"])
            self.assertEqual("GGUF", capability["model"]["magic"])
            self.assertEqual(3, capability["model"]["gguf_version"])
            self.assertRegex(capability["model"]["sha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(capability["binary"]["sha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(["--version", "--list-devices"], calls.read_text(encoding="utf-8").splitlines())
            self.assertNotIn(str(model), calls.read_text(encoding="utf-8"))

    def test_missing_and_invalid_prerequisites_fail_explicitly_after_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable, _, _ = self.fixture(root, devices="CPU only")
            invalid_model = root / "invalid.gguf"
            write_model(invalid_model, magic=b"NOPE")
            with mock.patch.dict(os.environ, {OPT_IN_ENV: "1"}):
                result = probe(
                    executable=executable, model=invalid_model, backend="vulkan",
                    expected_version="not-this-build",
                )
            codes = {item["code"] for item in result["failures"]}
            self.assertEqual(
                {"MODEL_NOT_GGUF", "BACKEND_UNAVAILABLE", "VERSION_MISMATCH"},
                codes,
            )
            self.assertFalse(result["capable"])

            missing = task_registry.adapt_llamacpp_capability(
                root / "missing-llama", root / "missing.gguf", "cpu", task_id="llamacpp-preflight-missing"
            )
            with mock.patch.dict(os.environ, {OPT_IN_ENV: "1"}):
                typed = task_registry.execute_typed_task(missing, {})
            self.assertEqual("FAILED", typed["status"])
            self.assertEqual(
                {"EXECUTABLE_MISSING", "MODEL_MISSING"},
                {item["code"] for item in typed["output"]["capability"]["failures"]},
            )

            zero = root / "zero.gguf"
            zero.write_bytes(b"")
            with mock.patch.dict(os.environ, {OPT_IN_ENV: "1"}):
                empty = probe(executable=executable, model=zero, backend="cpu")
            self.assertIn("MODEL_ZERO_BYTES", {item["code"] for item in empty["failures"]})

    def test_contract_and_claim_shape_fail_closed(self) -> None:
        schema = json.loads(
            (TASKPACK / "config" / "llamacpp-capability-preflight.schema.json").read_text(encoding="utf-8")
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual("preflight_only", schema["properties"]["mode"]["const"])
        self.assertFalse(schema["properties"]["inference_started"]["const"])

        with tempfile.TemporaryDirectory() as temporary:
            executable, model, _ = self.fixture(Path(temporary))
            task = task_registry.adapt_llamacpp_capability(executable, model, "cpu")
            task["resource_claims"] = task["resource_claims"][:-1]
            task["task_digest"] = task_registry.task_digest(task)
            with self.assertRaisesRegex(storage.CCISError, "requested accelerator"):
                task_registry.verify_task(task)


if __name__ == "__main__":
    unittest.main()
