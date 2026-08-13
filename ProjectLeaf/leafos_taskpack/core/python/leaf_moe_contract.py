#!/usr/bin/env python3
"""Validate LeafOS medium-MoE selection policy and candidate records."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "config" / "medium_moe_policy.json"
DEFAULT_CANDIDATE = ROOT / "config" / "medium_moe_candidate.template.json"
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in {path}: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _mapping(value: Any, field: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{field} must be an object")
        return {}
    return value


def _require_keys(value: dict[str, Any], field: str, required: set[str], errors: list[str]) -> None:
    missing = sorted(required - set(value))
    if missing:
        errors.append(f"{field} is missing required fields: {', '.join(missing)}")


def _positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema") != "leafos.medium-moe-policy.v1":
        errors.append("schema must be leafos.medium-moe-policy.v1")
    if not isinstance(policy.get("policy_id"), str) or not policy["policy_id"].strip():
        errors.append("policy_id must be a non-empty string")
    if policy.get("status") != "active":
        errors.append("status must be active")

    decision = _mapping(policy.get("decision"), "decision", errors)
    _require_keys(
        decision,
        "decision",
        {
            "preferred_architecture",
            "total_parameter_band_billion",
            "selection_basis",
            "automatic_promotion",
            "deprecated_model_ids",
            "deprecated_profile_ids",
            "incumbent_route",
        },
        errors,
    )
    band = _mapping(decision.get("total_parameter_band_billion"), "decision.total_parameter_band_billion", errors)
    if decision.get("preferred_architecture") != "moe":
        errors.append("decision.preferred_architecture must be moe")
    if band.get("minimum") != 47 or band.get("maximum") != 156:
        errors.append("candidate total-parameter band must be 47 through 156 billion")
    if decision.get("selection_basis") != "operator_experiment_and_theory":
        errors.append("decision.selection_basis must preserve operator provenance")
    if decision.get("automatic_promotion") is not False:
        errors.append("decision.automatic_promotion must be false")
    if "GLM-5.2" not in decision.get("deprecated_model_ids", []):
        errors.append("decision.deprecated_model_ids must include GLM-5.2")
    if "glm52-q4-overnight" not in decision.get("deprecated_profile_ids", []):
        errors.append("decision.deprecated_profile_ids must include glm52-q4-overnight")
    if not isinstance(decision.get("incumbent_route"), str) or not decision["incumbent_route"].strip():
        errors.append("decision.incumbent_route must preserve the current active route")

    host = _mapping(policy.get("reference_host"), "reference_host", errors)
    _require_keys(
        host,
        "reference_host",
        {"gpu_name", "gpu_vram_gb", "system_ram_gb", "compute_backend", "resource_policy"},
        errors,
    )
    if not isinstance(host.get("gpu_name"), str) or not host["gpu_name"].strip():
        errors.append("reference_host.gpu_name must be a non-empty string")
    if host.get("compute_backend") != "vulkan":
        errors.append("reference_host.compute_backend must be vulkan")
    if not _positive_number(host.get("gpu_vram_gb")) or not _positive_number(host.get("system_ram_gb")):
        errors.append("reference host RAM and VRAM must be positive numbers")
    if not isinstance(host.get("resource_policy"), str) or not host["resource_policy"].strip():
        errors.append("reference_host.resource_policy must name the governing resource policy")

    placement = _mapping(policy.get("placement"), "placement", errors)
    expected = {
        "runtime": "llama.cpp",
        "model_format": "GGUF",
        "weights_source": "local_stack_only",
        "mmap_required": True,
        "ssd_semantics": "os_page_cache_backing_store",
        "leafos_managed_ssd_tiering": False,
        "gpu_offload_selection": "measured_per_candidate",
        "expert_pinning_assumed": False,
    }
    for field, expected_value in expected.items():
        if placement.get(field) != expected_value:
            errors.append(f"placement.{field} must be {expected_value!r}")
    variants = placement.get("kv_cache_variants", [])
    if not isinstance(variants, list) or not {"f16", "q8_0"}.issubset(set(variants)):
        errors.append("placement.kv_cache_variants must include f16 and q8_0")

    qualification = _mapping(policy.get("qualification"), "qualification", errors)
    _require_keys(
        qualification,
        "qualification",
        {
            "durations_minutes",
            "promotion_after_minutes",
            "required_scenarios",
            "required_runs",
            "required_metrics",
            "hard_gates",
            "ranking_metrics",
            "throughput_threshold_policy",
            "operator_approval_required",
        },
        errors,
    )
    if qualification.get("durations_minutes") != [4, 8, 64]:
        errors.append("qualification.durations_minutes must be [4, 8, 64]")
    if qualification.get("promotion_after_minutes") != 64:
        errors.append("qualification.promotion_after_minutes must be 64")
    if qualification.get("throughput_threshold_policy") != "candidate_specific_before_run":
        errors.append("throughput thresholds must be candidate-specific and set before a run")
    if qualification.get("operator_approval_required") is not True:
        errors.append("qualification.operator_approval_required must be true")
    if set(qualification.get("required_scenarios", [])) != {
        "cold_cache",
        "warm_cache",
        "resident_foreground",
    }:
        errors.append("qualification.required_scenarios must define cold, warm, and resident-foreground runs")
    required_runs = qualification.get("required_runs", [])
    expected_runs = {
        (4, "leafos", "cold_cache"),
        (8, "leafos", "warm_cache"),
        (64, "leafos", "resident_foreground"),
    }
    actual_runs = {
        (item.get("duration_minutes"), item.get("mode"), item.get("scenario"))
        for item in required_runs
        if isinstance(item, dict)
    } if isinstance(required_runs, list) else set()
    if actual_runs != expected_runs or len(required_runs) != len(expected_runs):
        errors.append("qualification.required_runs must map 4m cold, 8m warm, and 64m resident evidence")
    for item in required_runs if isinstance(required_runs, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("purpose"), str) or not item["purpose"].strip():
            errors.append("every qualification.required_runs entry must state its purpose")
    hard_gates = _mapping(qualification.get("hard_gates"), "qualification.hard_gates", errors)
    for field in (
        "provider_must_survive_run",
        "no_out_of_memory",
        "baseline_validation_must_pass",
        "unknown_metrics_require_reason",
    ):
        if hard_gates.get(field) is not True:
            errors.append(f"qualification.hard_gates.{field} must be true")
    if not isinstance(hard_gates.get("resource_limits_source"), str) or not hard_gates["resource_limits_source"].strip():
        errors.append("qualification.hard_gates.resource_limits_source must be set")
    required_metrics = qualification.get("required_metrics", [])
    core_metrics = {
        "generation_tokens_per_second",
        "gpu_process_alive_for_run",
        "gpu_vram_used_peak_percent",
        "ram_used_peak_percent",
        "foreground_responsiveness_p95_ms",
        "validated_patches",
        "baseline_validation_passed",
        "oom_events",
        "availability",
    }
    if not isinstance(required_metrics, list) or not core_metrics.issubset(set(required_metrics)):
        errors.append("qualification.required_metrics is missing a core stability or productivity metric")
    provenance = policy.get("provenance", [])
    kinds = {item.get("kind") for item in provenance if isinstance(item, dict)} if isinstance(provenance, list) else set()
    if not {"operator_decision", "measured_repository_evidence", "historical_proposal"}.issubset(kinds):
        errors.append("provenance must distinguish operator, measured, and historical sources")
    return errors


def validate_candidate(
    candidate: dict[str, Any], policy: dict[str, Any], *, require_resolved: bool = False
) -> list[str]:
    errors = validate_policy(policy)
    if errors:
        return errors
    if candidate.get("schema") != "leafos.medium-moe-candidate.v1":
        errors.append("schema must be leafos.medium-moe-candidate.v1")
    if candidate.get("policy_id") != policy.get("policy_id"):
        errors.append("policy_id must match the selected policy")
    status = candidate.get("status")
    if status not in {"template", "resolved"}:
        errors.append("status must be template or resolved")

    identity = _mapping(candidate.get("identity"), "identity", errors)
    topology = _mapping(candidate.get("topology"), "topology", errors)
    runtime = _mapping(candidate.get("runtime"), "runtime", errors)
    acceptance = _mapping(candidate.get("acceptance"), "acceptance", errors)
    _require_keys(identity, "identity", {"model_id", "source_repo", "revision", "artifact", "sha256", "license"}, errors)
    _require_keys(
        topology,
        "topology",
        {"total_parameters_billion", "active_parameters_billion", "expert_count", "active_experts_per_token"},
        errors,
    )
    _require_keys(
        runtime,
        "runtime",
        {
            "provider",
            "compute_backend",
            "model_format",
            "model_path",
            "executable",
            "benchmark_command",
            "context_tokens",
            "gpu_layers",
            "mmap",
            "kv_cache_type_k",
            "kv_cache_type_v",
            "no_download",
        },
        errors,
    )
    _require_keys(
        acceptance,
        "acceptance",
        {
            "minimum_generation_tokens_per_second",
            "maximum_time_to_first_token_seconds",
            "minimum_validated_useful_changes_per_hour",
            "threshold_provenance",
        },
        errors,
    )

    fixed_runtime = {
        "provider": "llamacpp",
        "compute_backend": "vulkan",
        "model_format": "GGUF",
        "mmap": True,
        "no_download": True,
    }
    for field, expected in fixed_runtime.items():
        if runtime.get(field) != expected:
            errors.append(f"runtime.{field} must be {expected!r}")
    command = runtime.get("benchmark_command")
    if not isinstance(command, list) or not all(isinstance(arg, str) for arg in command):
        errors.append("runtime.benchmark_command must be an array of strings")
    if not isinstance(runtime.get("executable"), str) or not runtime["executable"].strip():
        errors.append("runtime.executable must be a non-empty string")
    if not isinstance(runtime.get("kv_cache_type_k"), str) or not isinstance(runtime.get("kv_cache_type_v"), str):
        errors.append("runtime KV-cache types must be strings")

    if status != "resolved":
        if require_resolved:
            errors.append("candidate status must be resolved before manifest, evaluation, or execution")
        return errors

    for field in ("model_id", "source_repo", "revision", "artifact", "license"):
        if not isinstance(identity.get(field), str) or not identity[field].strip():
            errors.append(f"identity.{field} must be set for a resolved candidate")
    if not isinstance(identity.get("sha256"), str) or not _SHA256.fullmatch(identity["sha256"]):
        errors.append("identity.sha256 must be a 64-character hexadecimal digest")
    deprecated = {str(item).casefold() for item in policy["decision"]["deprecated_model_ids"]}
    if str(identity.get("model_id", "")).casefold() in deprecated:
        errors.append("identity.model_id is deprecated by the selected policy")

    total = topology.get("total_parameters_billion")
    active = topology.get("active_parameters_billion")
    minimum = policy["decision"]["total_parameter_band_billion"]["minimum"]
    maximum = policy["decision"]["total_parameter_band_billion"]["maximum"]
    if not _positive_number(total) or not minimum <= total <= maximum:
        errors.append(f"topology.total_parameters_billion must be within {minimum}-{maximum}")
    if not _positive_number(active) or (_positive_number(total) and active > total):
        errors.append("topology.active_parameters_billion must be positive and no greater than total parameters")
    experts = topology.get("expert_count")
    active_experts = topology.get("active_experts_per_token")
    if not isinstance(experts, int) or isinstance(experts, bool) or experts < 2:
        errors.append("topology.expert_count must be an integer of at least 2")
    if (
        not isinstance(active_experts, int)
        or isinstance(active_experts, bool)
        or active_experts < 1
        or (isinstance(experts, int) and active_experts > experts)
    ):
        errors.append("topology.active_experts_per_token must be between 1 and expert_count")

    if not isinstance(runtime.get("model_path"), str) or not runtime["model_path"].strip():
        errors.append("runtime.model_path must name a local GGUF artifact")
    if not isinstance(command, list) or not command:
        errors.append("runtime.benchmark_command must be explicitly configured")
    if not isinstance(runtime.get("context_tokens"), int) or runtime["context_tokens"] <= 0:
        errors.append("runtime.context_tokens must be a positive integer")
    if not isinstance(runtime.get("gpu_layers"), int) or runtime["gpu_layers"] < 0:
        errors.append("runtime.gpu_layers must be a non-negative integer")
    allowed_kv = set(policy["placement"]["kv_cache_variants"])
    if runtime.get("kv_cache_type_k") not in allowed_kv or runtime.get("kv_cache_type_v") not in allowed_kv:
        errors.append("runtime KV-cache types must be declared by the policy")

    if not _positive_number(acceptance.get("minimum_generation_tokens_per_second")):
        errors.append("acceptance.minimum_generation_tokens_per_second must be set before the run")
    if not _positive_number(acceptance.get("maximum_time_to_first_token_seconds")):
        errors.append("acceptance.maximum_time_to_first_token_seconds must be set before the run")
    useful = acceptance.get("minimum_validated_useful_changes_per_hour")
    if not isinstance(useful, (int, float)) or isinstance(useful, bool) or useful < 0:
        errors.append("acceptance.minimum_validated_useful_changes_per_hour must be non-negative")
    if not isinstance(acceptance.get("threshold_provenance"), str) or not acceptance["threshold_provenance"].strip():
        errors.append("acceptance.threshold_provenance must explain thresholds set before the run")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--require-resolved", action="store_true")
    args = parser.parse_args()
    try:
        policy = load_json(args.policy)
        candidate = load_json(args.candidate)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    errors = validate_candidate(candidate, policy, require_resolved=args.require_resolved)
    result = {
        "valid": not errors,
        "policy_id": policy.get("policy_id"),
        "candidate_status": candidate.get("status"),
        "ready": candidate.get("status") == "resolved" and not errors,
        "errors": errors,
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
