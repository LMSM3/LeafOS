from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


class RealRuntimeGate(unittest.TestCase):
    def test_real_gguf_reaches_real_llama_cpp(self) -> None:
        model = os.environ.get("LEAF_TEST_MODEL")
        executable = shutil.which("llama-cli") or shutil.which("llama-cli.exe")
        if not model or not executable:
            self.skipTest("set LEAF_TEST_MODEL to a real GGUF and install llama-cli")
        path = Path(model).expanduser().resolve()
        self.assertTrue(path.is_file(), f"real model is missing: {path}")
        with path.open("rb") as stream:
            self.assertEqual(stream.read(4), b"GGUF")
        root = Path(__file__).resolve().parents[1]
        command = [
            sys.executable, str(root / "core" / "cli.py"), "run", str(path),
            "--prompt", "Reply with OK", "--tokens", "16", "--context", "512",
        ]
        if os.environ.get("LEAF_TEST_CPU") == "1":
            command.append("--cpu")
        completed = subprocess.run(
            command,
            capture_output=True, text=True, timeout=180, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        self.assertTrue(completed.stdout.strip(), "llama.cpp returned no inference output")


if __name__ == "__main__":
    unittest.main()
