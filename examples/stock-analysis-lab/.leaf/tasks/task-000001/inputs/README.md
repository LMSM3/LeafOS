# Verdant Quant Lab

Verdant Quant Lab is a deterministic, dependency-free Python stock-analysis system built as a real LeafOS long-loop workload. It is an educational research engine, not trading advice and not a live-market data client.

The implementation must begin from this README and the files under `seed/`. No feature may depend on network access, a proprietary numerical library, or an imaginary data source.

## Required capabilities

The package must remain modular and expose auditable mathematical layers:

1. CSV/config ingestion with strict date, numeric, alignment, and missing-data checks.
2. Simple and log returns; cumulative wealth; drawdown duration and depth.
3. Means, sample covariance, shrinkage covariance, volatility, skewness, excess kurtosis, quantiles, Sharpe, Sortino, and Omega.
4. Historical, Gaussian, and Cornish-Fisher value-at-risk plus historical expected shortfall.
5. CAPM alpha/beta and regularized multi-factor regression with intercept, residual risk, R-squared, and normal-equation diagnostics.
6. Long-only portfolio construction: minimum variance, mean-variance utility, risk parity, and maximum diversification.
7. Correlated geometric-Brownian scenarios using deterministic Cholesky sampling.
8. A walk-forward backtest with lookback/rebalance policy, transaction costs, turnover, weights, and performance metrics.
9. One orchestration API and one CLI producing a stable JSON research report.

## Mathematical conventions

- Prices are positive adjusted-close observations ordered by ISO date.
- Returns are decimal fractions, not percentages.
- Covariance uses `n - 1`; annualized volatility uses `sqrt(periods_per_year)`.
- VaR and expected shortfall are reported as positive loss magnitudes at the configured confidence.
- Portfolio weights are finite, long-only, and sum to one within numerical tolerance.
- Regressions include an intercept. Ridge regularization never penalizes that intercept.
- Random paths must be repeatable for the same integer seed.
- Singular systems fail with a useful error or use the configured regularization; they never invent a solution.

## Seed workload

`seed/prices.csv` contains four synthetic adjusted-close series. `seed/factors.csv` contains aligned synthetic market, size, and momentum factor returns. `seed/config.json` is the canonical policy.

The seed is deliberately synthetic: it makes tests reproducible and prevents an example from masquerading as current market analysis.

## Acceptance commands

From this directory:

```text
python -m unittest discover -s tests -v
python -m stocklab.cli analyze --prices seed/prices.csv --factors seed/factors.csv --config seed/config.json --output reports/seed-analysis.json
```

The report must include `metadata`, `assets`, `portfolio_risk`, `factor_models`, `portfolios`, `simulation`, and `backtest`. Re-running the command with unchanged inputs must produce equivalent analytical values.

## Project shape

```text
stock-analysis-lab/
├── README.md
├── SEED.md
├── pyproject.toml
├── seed/
├── stocklab/
├── tests/
└── reports/
```

LeafOS evidence is stored in `.leaf/`; it is runtime provenance rather than source code.
