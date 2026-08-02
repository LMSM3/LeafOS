#!/usr/bin/env python3
"""Transparent local-token economics shared by reports and operator views."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_POLICY: dict[str, Any] = {
    "currency": "USD",
    "comparison_output_usd_per_million": 10.0,
    "pricing_basis": "operator_assumption",
    "local_costs_included": False,
    "note": (
        "Gross cloud-equivalent output value only; local energy and hardware costs "
        "and cloud input/cache charges are excluded."
    ),
}


def normalize_policy(value: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = dict(DEFAULT_POLICY)
    if isinstance(value, dict):
        policy.update({key: item for key, item in value.items() if key in policy})
    rate = policy.get("comparison_output_usd_per_million")
    if not isinstance(rate, (int, float)) or isinstance(rate, bool) or rate < 0:
        raise ValueError("comparison_output_usd_per_million must be a non-negative number")
    if policy.get("currency") != "USD":
        raise ValueError("only USD comparison output is currently supported")
    if policy.get("pricing_basis") not in {"operator_assumption", "provider_quote"}:
        raise ValueError("pricing_basis must be operator_assumption or provider_quote")
    if policy.get("local_costs_included") is not False:
        raise ValueError("local_costs_included must remain false until costs are measured")
    policy["comparison_output_usd_per_million"] = float(rate)
    return policy


def load_operator_config(root: Path) -> dict[str, Any]:
    path = root / "config" / "operator-experience.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        value = {}
    surface = value.get("surface") if isinstance(value.get("surface"), dict) else {}
    return {
        "schema": value.get("schema", "leafos.operator-experience.v1"),
        "surface": {
            "name": str(surface.get("name", "LeafOS")),
            "engine": str(surface.get("engine", "LeafOS")),
            "stage": str(surface.get("stage", "pre-usage-layer")),
            "default_command": str(surface.get("default_command", "leafctl home")),
        },
        "economics": normalize_policy(value.get("economics")),
    }


def economics_for_tokens(
    generated_tokens: int | float | None,
    policy: dict[str, Any] | None = None,
    *,
    scope: str = "unknown",
) -> dict[str, Any]:
    normalized = normalize_policy(policy)
    tokens = float(generated_tokens) if isinstance(generated_tokens, (int, float)) and not isinstance(generated_tokens, bool) else None
    gross = None if tokens is None else tokens * normalized["comparison_output_usd_per_million"] / 1_000_000
    return {
        **normalized,
        "token_count_scope": scope,
        "generated_tokens": int(tokens) if tokens is not None and tokens.is_integer() else tokens,
        "gross_cloud_equivalent_usd": round(gross, 8) if gross is not None else None,
        "local_energy_cost_usd": None,
        "net_savings_usd": None,
    }


def throughput_projection(
    generation_tokens_per_second: int | float | None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_policy(policy)
    rate = float(generation_tokens_per_second) if isinstance(generation_tokens_per_second, (int, float)) and not isinstance(generation_tokens_per_second, bool) else None
    tokens_per_hour = None if rate is None else rate * 3600
    gross_per_hour = None if tokens_per_hour is None else tokens_per_hour * normalized["comparison_output_usd_per_million"] / 1_000_000
    return {
        "generation_tokens_per_second": round(rate, 3) if rate is not None else None,
        "projected_generated_tokens_per_hour": round(tokens_per_hour, 3) if tokens_per_hour is not None else None,
        "projected_gross_cloud_equivalent_usd_per_hour": round(gross_per_hour, 6) if gross_per_hour is not None else None,
        "projection_status": "decode-only arithmetic; not measured sustained agentic output",
    }


def benchmark_cell_economics(cell: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    definition = cell.get("definition", {}) if isinstance(cell.get("definition"), dict) else {}
    repetitions = definition.get("repetitions")
    generated = definition.get("generated_tokens")
    measured_tokens = generated * repetitions if isinstance(generated, int) and isinstance(repetitions, int) else None
    throughput = cell.get("throughput", {}) if isinstance(cell.get("throughput"), dict) else {}
    generation = throughput.get("generation", {}) if isinstance(throughput.get("generation"), dict) else {}
    return {
        "measured": economics_for_tokens(measured_tokens, policy, scope="benchmark_repetitions"),
        "projection": throughput_projection(generation.get("tokens_per_second"), policy),
    }


def summarize_benchmark(report: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = normalize_policy(policy or report.get("economics"))
    cells = [cell for cell in report.get("cells", []) if isinstance(cell, dict)]
    completed = [cell for cell in cells if cell.get("status") == "completed"]
    total_measured_tokens = 0
    best: dict[str, Any] | None = None
    for cell in completed:
        economics = benchmark_cell_economics(cell, normalized)
        measured = economics["measured"].get("generated_tokens")
        if isinstance(measured, (int, float)):
            total_measured_tokens += int(measured)
        rate = economics["projection"].get("generation_tokens_per_second")
        if isinstance(rate, (int, float)) and (best is None or rate > best["generation_tokens_per_second"]):
            definition = cell.get("definition", {})
            best = {
                "cell_id": cell.get("id"),
                "model": Path(str(definition.get("model", "unknown"))).name,
                "gpu_layers": definition.get("gpu_layers"),
                **economics["projection"],
            }
    measured_value = economics_for_tokens(total_measured_tokens, normalized, scope="completed_benchmark_cells")
    return {
        "benchmark_id": report.get("benchmark_id"),
        "status": report.get("status", "unknown"),
        "completed_cells": len(completed),
        "failed_cells": sum(cell.get("status") == "failed" for cell in cells),
        "planned_cells": report.get("planned_cell_count", len(cells)),
        "comparison": normalized,
        "measured": measured_value,
        "best_generation": best,
    }
