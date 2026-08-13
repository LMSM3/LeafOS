#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "bench"))

from inference_matrix import (  # noqa: E402
    SCHEMA,
    _parse_benchmark_rows,
    _rate_summary,
    build_cell_command,
    run_matrix,
    validate_manifest,
)


def _cell(model: str, cell_id: str = "cpu-reference") -> dict[str, object]:
    return {
        "id": cell_id,
        "model": model,
        "prompt_tokens": 512,
        "generated_tokens": 128,
        "repetitions": 3,
        "threads": 24,
        "gpu_layers": 0,
        "kv_key_type": "f16",
        "kv_value_type": "f16",
    }


class InferenceMatrixTests(unittest.TestCase):
    def test_manifest_contract_accepts_explicit_cell(self) -> None:
        manifest = {
            "schema": SCHEMA,
            "benchmark_id": "test",
            "runtime": {"command": [sys.executable]},
            "cells": [_cell("model.gguf")],
        }
        self.assertEqual([], validate_manifest(manifest))

    def test_manifest_contract_rejects_duplicate_and_implicit_parameters(self) -> None:
        incomplete = {"id": "same", "model": "model.gguf"}
        manifest = {
            "schema": SCHEMA,
            "benchmark_id": "test",
            "runtime": {"command": [sys.executable]},
            "cells": [incomplete, incomplete],
        }
        errors = validate_manifest(manifest)
        self.assertTrue(any("duplicate cell id" in error for error in errors))
        self.assertTrue(any("prompt_tokens" in error for error in errors))
        self.assertTrue(any("gpu_layers" in error for error in errors))

    def test_cell_command_exposes_placement_threads_and_kv_cache(self) -> None:
        command = build_cell_command(["llama-bench"], _cell("model.gguf"))
        self.assertIn("--offline", command)
        self.assertEqual("24", command[command.index("-t") + 1])
        self.assertEqual("0", command[command.index("-ngl") + 1])
        self.assertEqual("f16", command[command.index("-ctk") + 1])

    def test_rate_parser_keeps_prefill_and_generation_separate(self) -> None:
        payload = json.dumps([
            {"n_prompt": 512, "n_gen": 0, "avg_ts": 99.25},
            {"n_prompt": 0, "n_gen": 128, "avg_ts": 12.5},
        ])
        summary = _rate_summary(_parse_benchmark_rows(payload, ""))
        self.assertEqual(99.25, summary["prefill"]["tokens_per_second"])
        self.assertEqual(12.5, summary["generation"]["tokens_per_second"])

    def test_runner_writes_resumable_report_and_raw_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "fixture.gguf"
            model.write_bytes(b"GGUF fixture")
            fake_bench = root / "fake_bench.py"
            fake_bench.write_text(
                "import json\n"
                "print(json.dumps(["
                "{'n_prompt': 512, 'n_gen': 0, 'avg_ts': 99.25},"
                "{'n_prompt': 0, 'n_gen': 128, 'avg_ts': 12.5}]))\n",
                encoding="utf-8",
            )
            manifest = {
                "schema": SCHEMA,
                "benchmark_id": "fixture-run",
                "runtime": {"command": [sys.executable, str(fake_bench)]},
                "idle_policy": {"required": False, "settle_sample_seconds": 0.01},
                "protocol": {"telemetry_interval_seconds": 0.01},
                "cells": [_cell(str(model))],
            }
            manifest_path = root / "matrix.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            output = root / "output"
            args = SimpleNamespace(
                manifest=str(manifest_path), output_dir=str(output), bench="",
                resume=False, dry_run=False, allow_busy=False,
            )
            exit_code, report = run_matrix(args)
            self.assertEqual(0, exit_code)
            self.assertEqual("completed", report["status"])
            self.assertEqual(12.5, report["cells"][0]["throughput"]["generation"]["tokens_per_second"])
            self.assertEqual(384, report["cells"][0]["economics"]["measured"]["generated_tokens"])
            self.assertEqual(1, report["summary"]["completed_cells"])
            self.assertEqual(1, report["summary"]["planned_cells"])
            self.assertTrue((output / "report.json").is_file())
            self.assertTrue((output / "raw" / "cpu-reference.stdout.json").is_file())


if __name__ == "__main__":
    unittest.main()
