import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from leaf_moe_bench.runner import ExecutionRefused, _validate_command, run_plan
from leaf_moe_bench.util import sha256_file


class RunnerTests(unittest.TestCase):
    def test_execute_flag_is_required_before_output_is_created(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "runs"
            with self.assertRaises(ExecutionRefused):
                run_plan(
                    {"schema": "leafos.moe.benchmark-plan/0.1"},
                    output,
                    execute=False,
                )
            self.assertFalse(output.exists())

    def test_rejects_remote_provider_arguments(self):
        provider = {"executable": "C:/bin/llama-bench.exe"}
        entry = {
            "entry_id": "test",
            "absolute_path": "C:/models/model.gguf",
            "command": [
                "C:/bin/llama-bench.exe",
                "--offline",
                "--model",
                "C:/models/model.gguf",
                "--hf-repo",
                "owner/repo",
            ],
        }
        with self.assertRaises(ExecutionRefused):
            _validate_command(entry, provider)

    def test_strict_cpu_placement_requires_device_and_operation_isolation(self):
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp) / "model.gguf"
            model.write_bytes(b"GGUF-demo")
            provider = {"executable": sys.executable}
            entry = {
                "entry_id": "strict",
                "placement_id": "cpu-strict-16t",
                "absolute_path": str(model),
                "command": [
                    sys.executable,
                    "--offline",
                    "--model",
                    str(model),
                    "--n-gpu-layers",
                    "0",
                    "--device",
                    "none",
                    "--no-op-offload",
                    "0",
                ],
            }
            with self.assertRaisesRegex(ExecutionRefused, "no-op-offload 1"):
                _validate_command(entry, provider)

    def test_executes_a_guarded_local_jsonl_provider_and_records_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = root / "model.gguf"
            model.write_bytes(b"GGUF-demo")
            fake = root / "fake_llama_bench.py"
            fake.write_text(
                "import json\nprint(json.dumps({'test': 'tg8', 'avg_ts': 12.5}))\n",
                encoding="utf-8",
            )
            stat = model.stat()
            provider = {
                "executable": sys.executable,
                "executable_sha256": sha256_file(Path(sys.executable)),
            }
            entry = {
                "entry_id": "bench:test",
                "absolute_path": str(model),
                "bytes": stat.st_size,
                "modified_at_ns": stat.st_mtime_ns,
                "content_sha256": None,
                "command": [
                    sys.executable,
                    str(fake),
                    "--offline",
                    "--model",
                    str(model),
                ],
                "ready": True,
                "execution_blockers": [],
                "benchmark_admission_blockers": ["content_sha256_missing"],
                "promotion_blockers": [
                    "content_sha256_missing",
                    "statistical_promotion_analysis_missing",
                ],
                "requires_experimental_identity_override": False,
            }
            plan = {
                "schema": "leafos.moe.benchmark-plan/0.1",
                "plan_id": "plan:" + "a" * 64,
                "provider": provider,
                "entries": [entry],
            }
            with patch("leaf_moe_bench.runner._nvidia_sample", return_value=None):
                manifest = run_plan(
                    plan,
                    root / "runs",
                    execute=True,
                    telemetry_interval_seconds=0.01,
                    timeout_seconds=10,
                )
            self.assertTrue(manifest["success"])
            result = manifest["results"][0]
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["benchmark_rows"][0]["avg_ts"], 12.5)
            self.assertEqual(result["telemetry"]["background_gpu_envelope"]["sample_count"], 0)
            self.assertTrue(Path(manifest["manifest_path"]).is_file())
            self.assertFalse(result["promotion"]["eligible"])


if __name__ == "__main__":
    unittest.main()
