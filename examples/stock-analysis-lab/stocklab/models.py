from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MatrixSeries:
    dates: tuple[str, ...]
    names: tuple[str, ...]
    values: tuple[tuple[float, ...], ...]

    @property
    def rows(self) -> int:
        return len(self.values)

    @property
    def columns(self) -> int:
        return len(self.names)

    def column(self, index: int) -> list[float]:
        return [row[index] for row in self.values]


@dataclass(frozen=True)
class PortfolioSolution:
    name: str
    weights: tuple[float, ...]
    converged: bool
    iterations: int
    objective: float

    def as_dict(self, assets: tuple[str, ...]) -> dict[str, Any]:
        return {
            "name": self.name,
            "weights": {asset: weight for asset, weight in zip(assets, self.weights)},
            "converged": self.converged,
            "iterations": self.iterations,
            "objective": self.objective,
        }
