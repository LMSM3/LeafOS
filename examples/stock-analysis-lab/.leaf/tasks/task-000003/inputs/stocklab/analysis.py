from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

from stocklab.backtest import walk_forward
from stocklab.factors import fit_factor_model
from stocklab.io import load_config, read_factors, read_prices
from stocklab.linalg import column_means, covariance_matrix, dot, quadratic, shrink_covariance
from stocklab.monte_carlo import simulate_correlated_gbm
from stocklab.portfolio import equal_weight, maximum_diversification, mean_variance, minimum_variance, risk_parity
from stocklab.returns import drawdown_report, log_returns, portfolio_returns, simple_returns
from stocklab.risk import capm, portfolio_risk, value_at_risk
from stocklab.statistics import performance_summary


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _portfolio_record(solution: Any, assets: tuple[str, ...], means: list[float], covariance: list[list[float]], periods: int) -> dict[str, Any]:
    record = solution.as_dict(assets)
    record.update({
        "expected_return_annualized": dot(list(solution.weights), means) * periods,
        "volatility_annualized": math.sqrt(max(quadratic(list(solution.weights), covariance), 0.0)) * math.sqrt(periods),
    })
    return record


def analyze(prices_path: str | Path, factors_path: str | Path, config_path: str | Path) -> dict[str, Any]:
    prices_file = Path(prices_path).resolve()
    factors_file = Path(factors_path).resolve()
    config_file = Path(config_path).resolve()
    prices = read_prices(prices_file)
    factors = read_factors(factors_file)
    config = load_config(config_file)
    returns = simple_returns(prices)
    logarithmic = log_returns(prices)
    if factors.dates != returns.dates:
        missing = sorted(set(returns.dates) - set(factors.dates))
        extra = sorted(set(factors.dates) - set(returns.dates))
        raise ValueError(f"factor dates must exactly align to return dates; missing={missing}, extra={extra}")

    observations = [list(row) for row in returns.values]
    log_observations = [list(row) for row in logarithmic.values]
    means = column_means(observations)
    covariance = covariance_matrix(observations)
    regularized = shrink_covariance(covariance, float(config["covariance_shrinkage"]))
    periods = int(config["periods_per_year"])
    confidence = float(config["confidence"])
    risk_free_rate = float(config["risk_free_rate"])

    market_index = factors.names.index("MKT") if "MKT" in factors.names else 0
    market_returns = factors.column(market_index)
    asset_records: dict[str, Any] = {}
    factor_models: dict[str, Any] = {}
    factor_rows = [list(row) for row in factors.values]
    for index, asset in enumerate(prices.names):
        series = returns.column(index)
        asset_records[asset] = {
            "first_price": prices.values[0][index],
            "last_price": prices.values[-1][index],
            "simple_performance": performance_summary(series, periods, risk_free_rate),
            "log_return_mean": column_means(log_observations)[index],
            "loss_risk": value_at_risk(series, confidence),
            "drawdown": drawdown_report(series),
            "capm": capm(series, market_returns, periods, risk_free_rate),
        }
        factor_models[asset] = fit_factor_model(
            series, factor_rows, factors.names,
            ridge=float(config["ridge"]), periods=periods,
        )

    solutions = [
        equal_weight(prices.columns),
        minimum_variance(regularized),
        mean_variance(means, regularized, float(config["risk_aversion"])),
        risk_parity(regularized),
        maximum_diversification(regularized),
    ]
    solution_records = {
        solution.name: _portfolio_record(solution, prices.names, means, regularized, periods)
        for solution in solutions
    }
    equal_returns = portfolio_returns(returns, list(solutions[0].weights))
    selected = next(solution for solution in solutions if solution.name == "mean_variance")
    simulation = simulate_correlated_gbm(
        column_means(log_observations), covariance_matrix(log_observations), list(selected.weights),
        paths=int(config["monte_carlo_paths"]),
        steps=int(config["monte_carlo_steps"]),
        seed=int(config["random_seed"]),
    )
    backtest = walk_forward(
        returns,
        lookback=int(config["lookback"]),
        rebalance_every=int(config["rebalance_every"]),
        transaction_cost_bps=float(config["transaction_cost_bps"]),
        shrinkage=float(config["covariance_shrinkage"]),
        risk_aversion=float(config["risk_aversion"]),
        periods=periods,
        risk_free_rate=risk_free_rate,
    )
    return {
        "metadata": {
            "engine": "verdant-quant-lab",
            "version": "0.1.0",
            "purpose": "deterministic educational research; not financial advice",
            "as_of_date": prices.dates[-1],
            "observations": prices.rows,
            "return_observations": returns.rows,
            "assets": list(prices.names),
            "factors": list(factors.names),
            "input_sha256": {
                "prices": _digest(prices_file),
                "factors": _digest(factors_file),
                "config": _digest(config_file),
            },
            "config": config,
        },
        "assets": asset_records,
        "portfolio_risk": {
            "equal_weight": portfolio_risk(list(solutions[0].weights), regularized, periods),
            "equal_weight_loss_risk": value_at_risk(equal_returns, confidence),
            "equal_weight_performance": performance_summary(equal_returns, periods, risk_free_rate),
            "covariance": covariance,
            "shrinkage_covariance": regularized,
        },
        "factor_models": factor_models,
        "portfolios": solution_records,
        "simulation": simulation,
        "backtest": backtest,
    }
