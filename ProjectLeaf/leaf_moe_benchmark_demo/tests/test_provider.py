import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from leaf_moe_bench.provider import probe_llama_bench


HELP = """
--output <csv|json|jsonl>
--offline
--n-gpu-layers <n>
--n-cpu-moe <n>
--device <dev0/dev1/...>
--no-op-offload <0|1>
--fit-target <MiB>
--mmap <0|1>
--direct-io <0|1>
--output-err <format>
--flash-attn <on|off|auto>
load_backend: loaded CPU backend from demo
"""


class ProviderTests(unittest.TestCase):
    def test_cpu_only_probe_does_not_invent_devices(self):
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / "llama-bench.exe"
            executable.write_bytes(b"demo")
            responses = [
                subprocess.CompletedProcess([str(executable), "--help"], 0, HELP, ""),
                subprocess.CompletedProcess(
                    [str(executable), "--list-devices"],
                    0,
                    "Available devices:\n  (none)\n",
                    "load_backend: loaded CPU backend from demo\n",
                ),
            ]
            with patch("leaf_moe_bench.provider._capture", side_effect=responses):
                payload = probe_llama_bench(executable)
            self.assertTrue(payload["usable"])
            self.assertTrue(payload["cpu_available"])
            self.assertFalse(payload["gpu_available"])
            self.assertEqual(payload["devices"], [])
            self.assertTrue(payload["capabilities"]["device"])
            self.assertTrue(payload["capabilities"]["no_op_offload"])


if __name__ == "__main__":
    unittest.main()
