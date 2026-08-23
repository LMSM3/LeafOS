# Seed Contract

Implement the README against the checked-in synthetic dataset.

The four assets are intentionally different: ALPHA trends with the market, BETA is more volatile, GAMMA is defensive, and DELTA carries stronger momentum. The factors are synthetic decimal returns aligned to every price interval after the first observation.

The canonical run uses:

- 252 periods per year
- 95% loss confidence
- 0.02 annual risk-free rate
- 10-day walk-forward lookback
- rebalance every 5 observations
- 12 basis points one-way transaction cost
- covariance shrinkage 0.20
- regression ridge 0.000001
- mean-variance risk aversion 6.0
- 600 Monte Carlo paths over 20 future steps
- deterministic random seed 1701

The sample is intentionally short enough to inspect and long enough to exercise every layer. Tests should use analytical micro-cases in addition to the integrated seed.
