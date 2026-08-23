from __future__ import annotations

import math

from stocklab.linalg import LinearAlgebraError, solve, transpose
from stocklab.statistics import mean, standard_deviation


def fit_factor_model(
    asset_returns: list[float], factors: list[list[float]], factor_names: tuple[str, ...],
    *, ridge: float = 1e-6, periods: int = 252,
) -> dict[str, object]:
    if len(asset_returns) != len(factors) or len(asset_returns) <= len(factor_names) + 1:
        raise ValueError("factor model requires aligned observations exceeding parameter count")
    if any(len(row) != len(factor_names) for row in factors):
        raise ValueError("factor matrix width does not match names")
    design = [[1.0, *row] for row in factors]
    columns = transpose(design)
    gram = [[math.fsum(a * b for a, b in zip(left, right)) for right in columns] for left in columns]
    for index in range(1, len(gram)):
        gram[index][index] += ridge
    target = [math.fsum(value * response for value, response in zip(column, asset_returns)) for column in columns]
    try:
        coefficients = solve(gram, target)
    except LinearAlgebraError as error:
        raise ValueError(f"factor regression is singular; increase ridge: {error}") from error
    fitted = [math.fsum(coefficient * value for coefficient, value in zip(coefficients, row)) for row in design]
    residuals = [actual - predicted for actual, predicted in zip(asset_returns, fitted)]
    center = mean(asset_returns)
    total = math.fsum((value - center) ** 2 for value in asset_returns)
    residual_sum = math.fsum(value * value for value in residuals)
    diagonal = [abs(gram[index][index]) for index in range(len(gram))]
    smallest = min((value for value in diagonal if value > 0.0), default=0.0)
    return {
        "alpha_periodic": coefficients[0],
        "alpha_annualized": coefficients[0] * periods,
        "exposures": {name: value for name, value in zip(factor_names, coefficients[1:])},
        "r_squared": 1.0 - residual_sum / total if total else 0.0,
        "residual_volatility_annualized": standard_deviation(residuals) * math.sqrt(periods),
        "observations": len(asset_returns),
        "ridge": ridge,
        "normal_equation_diagonal_ratio": max(diagonal) / smallest if smallest else float("inf"),
    }
