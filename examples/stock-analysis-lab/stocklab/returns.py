from __future__ import annotations

import math

from stocklab.linalg import dot
from stocklab.models import MatrixSeries


def simple_returns(prices: MatrixSeries) -> MatrixSeries:
    values = []
    for previous, current in zip(prices.values, prices.values[1:]):
        values.append(tuple(current[index] / previous[index] - 1.0 for index in range(prices.columns)))
    return MatrixSeries(prices.dates[1:], prices.names, tuple(values))


def log_returns(prices: MatrixSeries) -> MatrixSeries:
    values = []
    for previous, current in zip(prices.values, prices.values[1:]):
        values.append(tuple(math.log(current[index] / previous[index]) for index in range(prices.columns)))
    return MatrixSeries(prices.dates[1:], prices.names, tuple(values))


def portfolio_returns(returns: MatrixSeries | list[list[float]], weights: list[float]) -> list[float]:
    rows = returns.values if isinstance(returns, MatrixSeries) else returns
    return [dot(row, weights) for row in rows]


def wealth_curve(returns: list[float], initial: float = 1.0) -> list[float]:
    wealth = initial
    values = [wealth]
    for value in returns:
        wealth *= 1.0 + value
        values.append(wealth)
    return values


def drawdown_report(returns: list[float]) -> dict[str, float | int]:
    curve = wealth_curve(returns)
    peak = curve[0]
    peak_index = 0
    current_duration = 0
    longest_duration = 0
    maximum_drawdown = 0.0
    trough_index = 0
    drawdown_start = 0
    for index, wealth in enumerate(curve):
        if wealth >= peak:
            peak = wealth
            peak_index = index
            current_duration = 0
        else:
            current_duration += 1
            longest_duration = max(longest_duration, current_duration)
            drawdown = wealth / peak - 1.0
            if drawdown < maximum_drawdown:
                maximum_drawdown = drawdown
                trough_index = index
                drawdown_start = peak_index
    return {
        "maximum_drawdown": maximum_drawdown,
        "longest_duration": longest_duration,
        "peak_index": drawdown_start,
        "trough_index": trough_index,
        "terminal_wealth": curve[-1],
    }
