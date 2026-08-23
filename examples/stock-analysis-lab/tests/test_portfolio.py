from __future__ import annotations

import math
import unittest

from stocklab.monte_carlo import simulate_correlated_gbm
from stocklab.portfolio import maximum_diversification, mean_variance, minimum_variance, risk_parity


class PortfolioTests(unittest.TestCase):
    covariance = [[0.040, 0.006, 0.004], [0.006, 0.090, 0.008], [0.004, 0.008, 0.025]]

    def assert_weights(self, values: tuple[float, ...]) -> None:
        self.assertAlmostEqual(math.fsum(values), 1.0, places=10)
        self.assertTrue(all(math.isfinite(value) and value >= 0.0 for value in values))

    def test_all_optimizers_return_long_only_fully_invested_weights(self) -> None:
        solutions = [
            minimum_variance(self.covariance),
            mean_variance([0.06, 0.11, 0.045], self.covariance, 5.0),
            risk_parity(self.covariance),
            maximum_diversification(self.covariance),
        ]
        for solution in solutions:
            self.assert_weights(solution.weights)
            self.assertTrue(math.isfinite(solution.objective))

    def test_lower_variance_asset_receives_more_minimum_variance_weight(self) -> None:
        solution = minimum_variance([[0.01, 0.0], [0.0, 0.09]])
        self.assertGreater(solution.weights[0], solution.weights[1])

    def test_correlated_gbm_is_deterministic(self) -> None:
        arguments = ([0.001, 0.002], [[0.0004, 0.0001], [0.0001, 0.0009]], [0.6, 0.4])
        first = simulate_correlated_gbm(*arguments, paths=100, steps=10, seed=17)
        second = simulate_correlated_gbm(*arguments, paths=100, steps=10, seed=17)
        self.assertEqual(first, second)
        self.assertEqual(first["paths"], 100)


if __name__ == "__main__":
    unittest.main()
