from __future__ import annotations

import math


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("mean requires observations")
    return math.fsum(values) / len(values)


def variance(values: list[float], *, sample: bool = True) -> float:
    divisor = len(values) - 1 if sample else len(values)
    if divisor <= 0:
        raise ValueError("variance requires at least two observations for a sample")
    center = mean(values)
    return math.fsum((value - center) ** 2 for value in values) / divisor


def standard_deviation(values: list[float], *, sample: bool = True) -> float:
    return math.sqrt(max(0.0, variance(values, sample=sample)))


def quantile(values: list[float], probability: float) -> float:
    if not values or not 0.0 <= probability <= 1.0:
        raise ValueError("quantile requires observations and probability in [0, 1]")
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def skewness(values: list[float]) -> float:
    count = len(values)
    if count < 3:
        return 0.0
    center = mean(values)
    deviation = standard_deviation(values)
    if deviation == 0.0:
        return 0.0
    raw = math.fsum(((value - center) / deviation) ** 3 for value in values)
    return count * raw / ((count - 1) * (count - 2))


def excess_kurtosis(values: list[float]) -> float:
    count = len(values)
    if count < 4:
        return 0.0
    center = mean(values)
    deviation = standard_deviation(values)
    if deviation == 0.0:
        return 0.0
    fourth = math.fsum(((value - center) / deviation) ** 4 for value in values)
    return (
        count * (count + 1) * fourth / ((count - 1) * (count - 2) * (count - 3))
        - 3.0 * (count - 1) ** 2 / ((count - 2) * (count - 3))
    )


def normal_ppf(probability: float) -> float:
    """Acklam's rational approximation for the standard-normal quantile."""
    if not 0.0 < probability < 1.0:
        raise ValueError("normal probability must be strictly between zero and one")
    a = (-39.6968302866538, 220.946098424521, -275.928510446969, 138.357751867269, -30.6647980661472, 2.50662827745924)
    b = (-54.4760987982241, 161.585836858041, -155.698979859887, 66.8013118877197, -13.2806815528857)
    c = (-0.00778489400243029, -0.322396458041136, -2.40075827716184, -2.54973253934373, 4.37466414146497, 2.93816398269878)
    d = (0.00778469570904146, 0.32246712907004, 2.445134137143, 3.75440866190742)
    low = 0.02425
    if probability < low:
        q = math.sqrt(-2.0 * math.log(probability))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    if probability > 1.0 - low:
        q = math.sqrt(-2.0 * math.log(1.0 - probability))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    q = probability - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)


def performance_summary(returns: list[float], periods: int, risk_free_rate: float = 0.0) -> dict[str, float]:
    average = mean(returns)
    volatility = standard_deviation(returns)
    downside = [min(value, 0.0) for value in returns]
    downside_deviation = math.sqrt(math.fsum(value * value for value in downside) / len(downside))
    periodic_risk_free = (1.0 + risk_free_rate) ** (1.0 / periods) - 1.0
    annual_return = (math.prod(1.0 + value for value in returns) ** (periods / len(returns)) - 1.0)
    annual_volatility = volatility * math.sqrt(periods)
    gains = math.fsum(max(value, 0.0) for value in returns)
    losses = math.fsum(max(-value, 0.0) for value in returns)
    return {
        "mean_periodic": average,
        "annual_return": annual_return,
        "annual_volatility": annual_volatility,
        "sharpe": (average - periodic_risk_free) / volatility * math.sqrt(periods) if volatility else 0.0,
        "sortino": (average - periodic_risk_free) / downside_deviation * math.sqrt(periods) if downside_deviation else 0.0,
        "omega_zero": gains / losses if losses else float("inf"),
        "skewness": skewness(returns),
        "excess_kurtosis": excess_kurtosis(returns),
    }
