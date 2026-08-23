from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from stocklab.analysis import analyze


ROOT = Path(__file__).resolve().parents[1]


class IntegratedSeedTests(unittest.TestCase):
    def test_seed_report_has_every_required_layer_and_is_deterministic(self) -> None:
        arguments = (ROOT / "seed" / "prices.csv", ROOT / "seed" / "factors.csv", ROOT / "seed" / "config.json")
        first = analyze(*arguments)
        second = analyze(*arguments)
        self.assertEqual(first, second)
        self.assertEqual(
            set(first),
            {"metadata", "assets", "portfolio_risk", "factor_models", "portfolios", "simulation", "backtest"},
        )
        self.assertEqual(first["metadata"]["return_observations"], 40)
        self.assertEqual(first["simulation"]["paths"], 600)
        self.assertGreater(first["backtest"]["rebalance_count"], 1)
        for portfolio in first["portfolios"].values():
            self.assertAlmostEqual(sum(portfolio["weights"].values()), 1.0, places=9)

    def test_cli_writes_strict_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            completed = subprocess.run(
                [
                    sys.executable, "-m", "stocklab.cli", "analyze",
                    "--prices", "seed/prices.csv", "--factors", "seed/factors.csv",
                    "--config", "seed/config.json", "--output", str(output),
                ],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            parsed = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(parsed["metadata"]["engine"], "verdant-quant-lab")
            self.assertNotIn("NaN", output.read_text(encoding="utf-8"))
            self.assertNotIn("Infinity", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
