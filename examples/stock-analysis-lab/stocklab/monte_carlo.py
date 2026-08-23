from __future__ import annotations

import math
import random

from stocklab.linalg import cholesky, matvec
from stocklab.statistics import mean, quantile, standard_deviation


def simulate_correlated_gbm(
    means: list[float], covariance: list[list[float]], weights: list[float],
    *, paths: int, steps: int, seed: int,
) -> dict[str, float | int]:
    if paths <= 0 or steps <= 0 or len(means) != len(weights):
        raise ValueError("simulation dimensions and counts must be positive and aligned")
    lower = cholesky(covariance)
    generator = random.Random(seed)
    terminal_returns: list[float] = []
    for _ in range(paths):
        relatives = [1.0] * len(means)
        for _ in range(steps):
            independent = [generator.gauss(0.0, 1.0) for _ in means]
            shocks = matvec(lower, independent)
            for index, (drift, shock) in enumerate(zip(means, shocks)):
                relatives[index] *= math.exp(drift - 0.5 * covariance[index][index] + shock)
        terminal_returns.append(math.fsum(weight * relative for weight, relative in zip(weights, relatives)) - 1.0)
    return {
        "paths": paths,
        "steps": steps,
        "seed": seed,
        "mean_terminal_return": mean(terminal_returns),
        "terminal_volatility": standard_deviation(terminal_returns),
        "p05": quantile(terminal_returns, 0.05),
        "median": quantile(terminal_returns, 0.50),
        "p95": quantile(terminal_returns, 0.95),
        "probability_of_loss": math.fsum(1.0 for value in terminal_returns if value < 0.0) / paths,
    }
