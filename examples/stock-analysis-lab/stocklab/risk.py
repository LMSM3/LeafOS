from __future__ import annotations

import math

from stocklab.linalg import dot, matvec, quadratic
from stocklab.statistics import excess_kurtosis, mean, normal_ppf, quantile, skewness, standard_deviation


def value_at_risk(returns: list[float], confidence: float) -> dict[str, float]:
    tail_probability = 1.0 - confidence
    historical_cutoff = quantile(returns, tail_probability)
    historical = max(0.0, -historical_cutoff)
    tail = [-value for value in returns if value <= historical_cutoff]
    expected_shortfall = mean(tail) if tail else historical
    average = mean(returns)
    deviation = standard_deviation(returns)
    z = normal_ppf(tail_probability)
    gaussian = max(0.0, -(average + z * deviation))
    skew = skewness(returns)
    kurtosis = excess_kurtosis(returns)
    adjusted = (
        z + (z * z - 1.0) * skew / 6.0
        + (z ** 3 - 3.0 * z) * kurtosis / 24.0
        - (2.0 * z ** 3 - 5.0 * z) * skew * skew / 36.0
    )
    cornish_fisher = max(0.0, -(average + adjusted * deviation))
    return {
        "confidence": confidence,
        "historical_var": historical,
        "historical_expected_shortfall": expected_shortfall,
        "gaussian_var": gaussian,
        "cornish_fisher_var": cornish_fisher,
    }


def portfolio_risk(weights: list[float], covariance: list[list[float]], periods: int) -> dict[str, object]:
    marginal = matvec(covariance, weights)
    periodic_variance = max(0.0, dot(weights, marginal))
    periodic_volatility = math.sqrt(periodic_variance)
    contributions = [
        weight * value / periodic_volatility if periodic_volatility else 0.0
        for weight, value in zip(weights, marginal)
    ]
    return {
        "periodic_variance": periodic_variance,
        "annual_volatility": periodic_volatility * math.sqrt(periods),
        "volatility_contributions": contributions,
        "contribution_sum": math.fsum(contributions),
    }


def capm(asset_returns: list[float], market_returns: list[float], periods: int, risk_free_rate: float) -> dict[str, float]:
    if len(asset_returns) != len(market_returns) or len(asset_returns) < 2:
        raise ValueError("CAPM requires aligned asset and market observations")
    market_mean = mean(market_returns)
    asset_mean = mean(asset_returns)
    covariance = math.fsum(
        (asset - asset_mean) * (market - market_mean)
        for asset, market in zip(asset_returns, market_returns)
    ) / (len(asset_returns) - 1)
    market_variance = standard_deviation(market_returns) ** 2
    beta = covariance / market_variance if market_variance else 0.0
    periodic_rf = (1.0 + risk_free_rate) ** (1.0 / periods) - 1.0
    alpha_periodic = asset_mean - periodic_rf - beta * (market_mean - periodic_rf)
    residuals = [
        asset - (alpha_periodic + periodic_rf + beta * (market - periodic_rf))
        for asset, market in zip(asset_returns, market_returns)
    ]
    return {
        "alpha_annualized": alpha_periodic * periods,
        "beta": beta,
        "residual_volatility_annualized": standard_deviation(residuals) * math.sqrt(periods),
        "r_squared": 1.0 - quadratic(residuals, [[1.0 if i == j else 0.0 for j in range(len(residuals))] for i in range(len(residuals))]) / math.fsum((value - asset_mean) ** 2 for value in asset_returns) if any(value != asset_mean for value in asset_returns) else 0.0,
    }
