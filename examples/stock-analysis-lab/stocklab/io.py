from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

from stocklab.models import MatrixSeries


class DataError(ValueError):
    pass


DEFAULT_CONFIG: dict[str, int | float] = {
    "periods_per_year": 252,
    "confidence": 0.95,
    "risk_free_rate": 0.02,
    "lookback": 20,
    "rebalance_every": 5,
    "transaction_cost_bps": 10,
    "covariance_shrinkage": 0.20,
    "ridge": 1e-6,
    "risk_aversion": 6.0,
    "monte_carlo_paths": 500,
    "monte_carlo_steps": 20,
    "random_seed": 1701,
}


def _read_matrix(path: Path, *, positive: bool) -> MatrixSeries:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream))
    except OSError as error:
        raise DataError(f"cannot read data file {path}: {error}") from error
    if len(rows) < 3 or len(rows[0]) < 2 or rows[0][0].strip().casefold() != "date":
        raise DataError(f"{path} must contain date plus at least one series and two observations")
    names = tuple(value.strip() for value in rows[0][1:])
    if any(not value for value in names) or len(set(names)) != len(names):
        raise DataError(f"{path} contains empty or duplicate series names")
    dates: list[str] = []
    values: list[tuple[float, ...]] = []
    previous: date | None = None
    for number, row in enumerate(rows[1:], start=2):
        if len(row) != len(names) + 1:
            raise DataError(f"{path}:{number} has {len(row)} fields; expected {len(names) + 1}")
        try:
            current = date.fromisoformat(row[0].strip())
        except ValueError as error:
            raise DataError(f"{path}:{number} has an invalid ISO date") from error
        if previous is not None and current <= previous:
            raise DataError(f"{path}:{number} dates must be strictly increasing")
        try:
            parsed = tuple(float(value) for value in row[1:])
        except ValueError as error:
            raise DataError(f"{path}:{number} contains a non-numeric value") from error
        if any(not math.isfinite(value) for value in parsed):
            raise DataError(f"{path}:{number} contains a non-finite value")
        if positive and any(value <= 0.0 for value in parsed):
            raise DataError(f"{path}:{number} prices must be positive")
        dates.append(current.isoformat())
        values.append(parsed)
        previous = current
    return MatrixSeries(tuple(dates), names, tuple(values))


def read_prices(path: str | Path) -> MatrixSeries:
    return _read_matrix(Path(path), positive=True)


def read_factors(path: str | Path) -> MatrixSeries:
    return _read_matrix(Path(path), positive=False)


def load_config(path: str | Path) -> dict[str, int | float]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataError(f"cannot read config {path}: {error}") from error
    if not isinstance(raw, dict):
        raise DataError("configuration must be a JSON object")
    unknown = sorted(set(raw) - set(DEFAULT_CONFIG))
    if unknown:
        raise DataError("unknown configuration keys: " + ", ".join(unknown))
    config = {**DEFAULT_CONFIG, **raw}
    integer_keys = {"periods_per_year", "lookback", "rebalance_every", "monte_carlo_paths", "monte_carlo_steps", "random_seed"}
    for key, value in config.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
            raise DataError(f"configuration value {key} must be finite and numeric")
        if key in integer_keys and int(value) != value:
            raise DataError(f"configuration value {key} must be an integer")
    if int(config["periods_per_year"]) <= 0 or int(config["lookback"]) < 3:
        raise DataError("periods_per_year must be positive and lookback must be at least 3")
    if not 0.5 < float(config["confidence"]) < 1.0:
        raise DataError("confidence must be between 0.5 and 1.0")
    if not 0.0 <= float(config["covariance_shrinkage"]) <= 1.0:
        raise DataError("covariance_shrinkage must be between 0 and 1")
    if float(config["ridge"]) < 0.0 or float(config["transaction_cost_bps"]) < 0.0:
        raise DataError("ridge and transaction costs cannot be negative")
    for key in ("rebalance_every", "monte_carlo_paths", "monte_carlo_steps"):
        if int(config[key]) <= 0:
            raise DataError(f"{key} must be positive")
    return {key: int(value) if key in integer_keys else float(value) for key, value in config.items()}
