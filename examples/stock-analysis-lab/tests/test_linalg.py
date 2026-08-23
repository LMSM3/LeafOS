from __future__ import annotations

import math
import unittest

from stocklab.linalg import cholesky, covariance_matrix, matmul, project_simplex, solve


class LinearAlgebraTests(unittest.TestCase):
    def test_partial_pivot_solve(self) -> None:
        solved = solve([[0.0, 2.0], [1.0, 3.0]], [4.0, 5.0])
        self.assertAlmostEqual(solved[0], -1.0)
        self.assertAlmostEqual(solved[1], 2.0)

    def test_cholesky_reconstructs_covariance(self) -> None:
        covariance = [[4.0, 2.0], [2.0, 3.0]]
        lower = cholesky(covariance)
        reconstructed = matmul(lower, [list(column) for column in zip(*lower)])
        for row in range(2):
            for column in range(2):
                self.assertAlmostEqual(reconstructed[row][column], covariance[row][column])

    def test_covariance_and_simplex_projection(self) -> None:
        covariance = covariance_matrix([[1.0, 2.0], [2.0, 4.0], [3.0, 6.0]])
        self.assertAlmostEqual(covariance[0][0], 1.0)
        self.assertAlmostEqual(covariance[0][1], 2.0)
        weights = project_simplex([-2.0, 0.4, 3.0])
        self.assertAlmostEqual(math.fsum(weights), 1.0)
        self.assertTrue(all(weight >= 0.0 for weight in weights))


if __name__ == "__main__":
    unittest.main()
