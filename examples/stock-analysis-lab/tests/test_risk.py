from __future__ import annotations

import unittest

from stocklab.risk import capm, portfolio_risk, value_at_risk
from stocklab.statistics import normal_ppf, quantile


class RiskTests(unittest.TestCase):
    def test_quantile_and_normal_inverse(self) -> None:
        self.assertEqual(quantile([0.0, 10.0], 0.25), 2.5)
        self.assertAlmostEqual(normal_ppf(0.975), 1.959963, places=5)

    def test_var_is_positive_loss_and_expected_shortfall_is_at_least_var(self) -> None:
        report = value_at_risk([-0.10, -0.05, -0.02, 0.01, 0.03, 0.04], 0.80)
        self.assertGreater(report["historical_var"], 0.0)
        self.assertGreaterEqual(report["historical_expected_shortfall"], report["historical_var"])

    def test_portfolio_contributions_and_capm(self) -> None:
        risk = portfolio_risk([0.5, 0.5], [[0.04, 0.01], [0.01, 0.09]], 1)
        self.assertAlmostEqual(sum(risk["volatility_contributions"]), risk["annual_volatility"])
        market = [-0.02, -0.01, 0.01, 0.02, 0.03]
        asset = [2.0 * value for value in market]
        model = capm(asset, market, 252, 0.0)
        self.assertAlmostEqual(model["beta"], 2.0)


if __name__ == "__main__":
    unittest.main()
