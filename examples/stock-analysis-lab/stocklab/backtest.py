from __future__ import annotations

import math

from stocklab.linalg import column_means, covariance_matrix, dot, shrink_covariance
from stocklab.models import MatrixSeries
from stocklab.portfolio import mean_variance
from stocklab.returns import drawdown_report
from stocklab.statistics import performance_summary


def walk_forward(
    returns: MatrixSeries, *, lookback: int, rebalance_every: int, transaction_cost_bps: float,
    shrinkage: float, risk_aversion: float, periods: int, risk_free_rate: float,
) -> dict[str, object]:
    if returns.rows <= lookback:
        raise ValueError("walk-forward backtest requires more observations than lookback")
    count = returns.columns
    weights = [1.0 / count] * count
    cost_rate = transaction_cost_bps / 10_000.0
    realized: list[float] = []
    rebalances: list[dict[str, object]] = []
    total_turnover = 0.0
    total_cost = 0.0
    for index in range(lookback, returns.rows):
        cost = 0.0
        if (index - lookback) % rebalance_every == 0:
            window = [list(row) for row in returns.values[index - lookback:index]]
            covariance = shrink_covariance(covariance_matrix(window), shrinkage)
            means = column_means(window)
            solution = mean_variance(means, covariance, risk_aversion)
            updated = list(solution.weights)
            turnover = math.fsum(abs(left - right) for left, right in zip(updated, weights))
            cost = turnover * cost_rate
            total_turnover += turnover
            total_cost += cost
            weights = updated
            rebalances.append({
                "date": returns.dates[index],
                "turnover": turnover,
                "cost": cost,
                "weights": {asset: weight for asset, weight in zip(returns.names, weights)},
            })
        realized.append(dot(returns.values[index], weights) - cost)
    return {
        "start_date": returns.dates[lookback],
        "end_date": returns.dates[-1],
        "observations": len(realized),
        "rebalance_count": len(rebalances),
        "total_turnover": total_turnover,
        "total_transaction_cost": total_cost,
        "rebalances": rebalances,
        "performance": performance_summary(realized, periods, risk_free_rate),
        "drawdown": drawdown_report(realized),
    }
