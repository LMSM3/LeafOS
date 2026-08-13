#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "python"))

from leaf_economics import (  # noqa: E402
    benchmark_cell_economics,
    economics_for_tokens,
    normalize_policy,
    summarize_benchmark,
    throughput_projection,
)


class InferenceEconomicsTests(unittest.TestCase):
    def test_token_value_uses_explicit_per_million_assumption(self) -> None:
        value = economics_for_tokens(336_960, scope="interval")
        self.assertEqual(3.3696, value["gross_cloud_equivalent_usd"])
        self.assertEqual("operator_assumption", value["pricing_basis"])
        self.assertIsNone(value["net_savings_usd"])

    def test_throughput_projection_is_labeled_decode_only(self) -> None:
        value = throughput_projection(66.0)
        self.assertEqual(237_600.0, value["projected_generated_tokens_per_hour"])
        self.assertEqual(2.376, value["projected_gross_cloud_equivalent_usd_per_hour"])
        self.assertIn("not measured sustained", value["projection_status"])

    def test_invalid_or_incomplete_local_cost_claim_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            normalize_policy({"local_costs_included": True})
        with self.assertRaises(ValueError):
            normalize_policy({"comparison_output_usd_per_million": -1})

    def test_benchmark_summary_separates_measured_tokens_from_hourly_projection(self) -> None:
        cell = {
            "id": "gpu-full",
            "status": "completed",
            "definition": {"model": "model.gguf", "generated_tokens": 128, "repetitions": 3, "gpu_layers": 999},
            "throughput": {"generation": {"tokens_per_second": 100.0}},
        }
        cell_value = benchmark_cell_economics(cell, normalize_policy())
        self.assertEqual(384, cell_value["measured"]["generated_tokens"])
        report = {"benchmark_id": "fixture", "status": "completed", "planned_cell_count": 1, "cells": [cell]}
        summary = summarize_benchmark(report)
        self.assertEqual(384, summary["measured"]["generated_tokens"])
        self.assertEqual("gpu-full", summary["best_generation"]["cell_id"])


if __name__ == "__main__":
    unittest.main()
