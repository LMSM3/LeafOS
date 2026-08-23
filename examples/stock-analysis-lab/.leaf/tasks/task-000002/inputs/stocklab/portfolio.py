from __future__ import annotations

import math

from stocklab.linalg import LinearAlgebraError, dot, matvec, project_simplex, quadratic, solve
from stocklab.models import PortfolioSolution


def _validate(means: list[float], covariance: list[list[float]]) -> None:
    if not means or len(covariance) != len(means) or any(len(row) != len(means) for row in covariance):
        raise ValueError("portfolio inputs have incompatible dimensions")


def equal_weight(count: int) -> PortfolioSolution:
    if count <= 0:
        raise ValueError("portfolio requires at least one asset")
    weights = tuple([1.0 / count] * count)
    return PortfolioSolution("equal_weight", weights, True, 0, 0.0)


def minimum_variance(covariance: list[list[float]]) -> PortfolioSolution:
    count = len(covariance)
    _validate([0.0] * count, covariance)
    try:
        direction = solve(covariance, [1.0] * count)
    except LinearAlgebraError:
        regularized = [row[:] for row in covariance]
        scale = math.fsum(regularized[i][i] for i in range(count)) / count
        for index in range(count):
            regularized[index][index] += max(1e-10, scale * 1e-6)
        direction = solve(regularized, [1.0] * count)
    total = math.fsum(direction)
    raw = [value / total for value in direction] if abs(total) > 1e-14 else [1.0 / count] * count
    weights = project_simplex(raw)
    return PortfolioSolution("minimum_variance", tuple(weights), True, 1, quadratic(weights, covariance))


def mean_variance(
    means: list[float], covariance: list[list[float]], risk_aversion: float,
    *, iterations: int = 1200, tolerance: float = 1e-11,
) -> PortfolioSolution:
    _validate(means, covariance)
    if risk_aversion <= 0.0:
        raise ValueError("risk aversion must be positive")
    weights = [1.0 / len(means)] * len(means)
    spectral_bound = max(math.fsum(abs(value) for value in row) for row in covariance)
    step = 0.35 / max(risk_aversion * spectral_bound, 1e-8)
    converged = False
    completed = 0
    for completed in range(1, iterations + 1):
        gradient = [expected - risk_aversion * risk for expected, risk in zip(means, matvec(covariance, weights))]
        updated = project_simplex([weight + step * value for weight, value in zip(weights, gradient)])
        if max(abs(left - right) for left, right in zip(weights, updated)) < tolerance:
            weights = updated
            converged = True
            break
        weights = updated
        step *= 0.998
    objective = dot(means, weights) - 0.5 * risk_aversion * quadratic(weights, covariance)
    return PortfolioSolution("mean_variance", tuple(weights), converged, completed, objective)


def risk_parity(
    covariance: list[list[float]], *, iterations: int = 2000, tolerance: float = 1e-9,
) -> PortfolioSolution:
    count = len(covariance)
    _validate([0.0] * count, covariance)
    weights = [1.0 / count] * count
    converged = False
    completed = 0
    for completed in range(1, iterations + 1):
        marginal = matvec(covariance, weights)
        contributions = [max(weight * value, 1e-16) for weight, value in zip(weights, marginal)]
        target = math.fsum(contributions) / count
        spread = max(abs(value - target) for value in contributions)
        if spread <= tolerance * max(target, 1e-12):
            converged = True
            break
        updated = [weight * math.sqrt(target / contribution) for weight, contribution in zip(weights, contributions)]
        weights = project_simplex(updated)
    objective = max(contributions) - min(contributions)
    return PortfolioSolution("risk_parity", tuple(weights), converged, completed, objective)


def maximum_diversification(
    covariance: list[list[float]], *, iterations: int = 1600, tolerance: float = 1e-10,
) -> PortfolioSolution:
    count = len(covariance)
    _validate([0.0] * count, covariance)
    volatilities = [math.sqrt(max(covariance[index][index], 0.0)) for index in range(count)]
    weights = [1.0 / count] * count
    converged = False
    completed = 0
    for completed in range(1, iterations + 1):
        numerator = max(dot(weights, volatilities), 1e-16)
        variance = max(quadratic(weights, covariance), 1e-16)
        risk_gradient = matvec(covariance, weights)
        gradient = [volatility / numerator - value / variance for volatility, value in zip(volatilities, risk_gradient)]
        step = 0.08 / math.sqrt(completed)
        updated = project_simplex([weight + step * value for weight, value in zip(weights, gradient)])
        if max(abs(left - right) for left, right in zip(weights, updated)) < tolerance:
            weights = updated
            converged = True
            break
        weights = updated
    ratio = dot(weights, volatilities) / math.sqrt(max(quadratic(weights, covariance), 1e-16))
    return PortfolioSolution("maximum_diversification", tuple(weights), converged, completed, ratio)
