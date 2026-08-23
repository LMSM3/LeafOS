from __future__ import annotations

import unittest

from stocklab.factors import fit_factor_model


class FactorTests(unittest.TestCase):
    def test_regularized_factor_model_recovers_known_exposures(self) -> None:
        factors = [[index / 100.0, ((index % 3) - 1) / 100.0] for index in range(-8, 9)]
        asset = [0.001 + 1.5 * market - 0.4 * style for market, style in factors]
        report = fit_factor_model(asset, factors, ("MKT", "STYLE"), ridge=1e-12)
        self.assertAlmostEqual(report["alpha_periodic"], 0.001, places=8)
        self.assertAlmostEqual(report["exposures"]["MKT"], 1.5, places=7)
        self.assertAlmostEqual(report["exposures"]["STYLE"], -0.4, places=7)
        self.assertAlmostEqual(report["r_squared"], 1.0, places=9)


if __name__ == "__main__":
    unittest.main()
