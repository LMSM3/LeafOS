#!/usr/bin/env python3
"""Evidence-gated benchmark runner for a resolved local medium-MoE candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PYTHON_DIR = Path(__file__).resolve().parent
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from leaf_moe_contract import (  # noqa: E402
    DEFAULT_CANDIDATE,
    DEFAULT_POLICY,
    load_json,
    validate_candidate,
)

MODES = ("raw", "llamacpp_tuned", "leafos")
SCENARIOS = ("cold_cache", "warm_cache", "resident_foreground")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _resolved_errors(candidate: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    return validate_candidate(candidate, policy, require_resolved=True)


def _resource_limits(policy: dict[str, Any]) -> dict[str, Any]:
    configured = Path(policy["qualification"]["hard_gates"]["resource_limits_source"])
    path = configured if configured.is_absolute() else ROOT / configured
    resource_policy = load_json(path)
    limits = resource_policy.get("limits")
    activity = resource_policy.get("activity")
    if not isinstance(limits, dict) or not isinstance(activity, dict):
        raise ValueError(f"resource policy lacks limits or activity: {path}")
    return {
        "ram_used_percent": limits.get("ram_used_percent"),
        "vram_used_percent": limits.get("vram_used_percent"),
        "responsiveness_hard_ms": activity.get("responsiveness_hard_ms"),
        "source": str(configured).replace("\\", "/"),
    }


def build_manifest(
    candidate: dict[str, Any], policy: dict[str, Any], mode: str, scenario: str, duration_minutes: int
) -> dict[str, Any]:
    return {
        "leafos_object": "medium_moe_benchmark_manifest",
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy_id": policy["policy_id"],
        "mode": mode,
        "scenario": scenario,
        "duration_minutes": duration_minutes,
        "candidate": candidate,
        "required_metrics": policy["qualification"]["required_metrics"],
        "resource_limits": _resource_limits(policy),
        "placement_truth": {
            "weight_access": "llama.cpp mmap",
            "ssd_role": policy["placement"]["ssd_semantics"],
            "leafos_managed_ssd_tiering": policy["placement"]["leafos_managed_ssd_tiering"],
            "expert_pinning_assumed": policy["placement"]["expert_pinning_assumed"],
        },
        "safety": {
            "downloads_model_weights": False,
            "local_stack_only": True,
            "automatic_promotion": False,
            "operator_approval_required": True,
            "live_inference_requires_resolved_candidate": True,
            "live_inference_requires_explicit_benchmark_command": True,
        },
    }


def _number(metrics: dict[str, Any], field: str, errors: list[str], *, minimum: float = 0.0) -> float:
    value = metrics.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < minimum:
        errors.append(f"{field} must be a number greater than or equal to {minimum}")
        return 0.0
    return float(value)


def evaluate_metrics(
    candidate: dict[str, Any],
    policy: dict[str, Any],
    metrics: dict[str, Any],
    mode: str,
    scenario: str,
    duration_minutes: int,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors = _resolved_errors(candidate, policy)
    if errors:
        return None, errors
    required = policy["qualification"]["required_metrics"]
    missing = [name for name in required if name not in metrics]
    if missing:
        errors.append("missing required metrics: " + ", ".join(missing))
    availability = metrics.get("availability")
    if not isinstance(availability, dict):
        errors.append("availability must be an object")
        availability = {}
    unknown_without_reason = [
        name
        for name in required
        if name != "availability" and metrics.get(name) is None and not str(availability.get(name, "")).strip()
    ]
    if unknown_without_reason:
        errors.append("null metrics require field-specific availability reasons: " + ", ".join(unknown_without_reason))

    if metrics.get("candidate_model_id") != candidate["identity"]["model_id"]:
        errors.append("candidate_model_id must match the resolved candidate")
    if metrics.get("duration_minutes") != duration_minutes:
        errors.append("metrics duration_minutes must match the selected benchmark duration")
    if metrics.get("scenario") != scenario:
        errors.append("metrics scenario must match the selected benchmark scenario")
    if metrics.get("evidence_kind") not in {"measured_local", "measured_external"}:
        errors.append("evidence_kind must identify measured evidence")

    rate = _number(metrics, "generation_tokens_per_second", errors)
    ttft = _number(metrics, "time_to_first_token_seconds", errors)
    validated = _number(metrics, "validated_patches", errors)
    restarts = _number(metrics, "provider_restarts", errors)
    oom_events = _number(metrics, "oom_events", errors)
    ram_peak = _number(metrics, "ram_used_peak_percent", errors)
    vram_peak = _number(metrics, "gpu_vram_used_peak_percent", errors)
    responsiveness = _number(metrics, "foreground_responsiveness_p95_ms", errors)
    if not isinstance(metrics.get("gpu_process_alive_for_run"), bool):
        errors.append("gpu_process_alive_for_run must be a boolean")
    if not isinstance(metrics.get("baseline_validation_passed"), bool):
        errors.append("baseline_validation_passed must be a boolean")
    if errors:
        return None, errors

    limits = _resource_limits(policy)
    acceptance = candidate["acceptance"]
    useful_per_hour = validated * 60.0 / duration_minutes
    gates = {
        "generation_rate": rate >= acceptance["minimum_generation_tokens_per_second"],
        "time_to_first_token": ttft <= acceptance["maximum_time_to_first_token_seconds"],
        "productive_throughput": useful_per_hour >= acceptance["minimum_validated_useful_changes_per_hour"],
        "provider_survived": metrics["gpu_process_alive_for_run"] and restarts == 0,
        "no_out_of_memory": oom_events == 0,
        "baseline_validation": metrics["baseline_validation_passed"],
        "ram_pressure": ram_peak <= limits["ram_used_percent"],
        "vram_pressure": vram_peak <= limits["vram_used_percent"],
        "foreground_responsiveness": responsiveness <= limits["responsiveness_hard_ms"],
    }
    passed = all(gates.values())
    report = {
        "leafos_object": "medium_moe_benchmark_report",
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy_id": policy["policy_id"],
        "candidate_model_id": candidate["identity"]["model_id"],
        "mode": mode,
        "scenario": scenario,
        "duration_minutes": duration_minutes,
        "benchmark_passed": passed,
        "run_qualifies_for_portfolio": passed,
        "promotion_eligible": False,
        "promotion_eligibility_requires": "all policy.required_runs through the qualify command",
        "automatic_promotion": False,
        "operator_approval_required": True,
        "gate_results": gates,
        "productive_throughput": {
            "unit": "validated_useful_changes_per_hour",
            "value": useful_per_hour,
        },
        "acceptance": acceptance,
        "resource_limits": limits,
        "metrics": metrics,
    }
    return report, []


def qualify_reports(
    candidate: dict[str, Any], policy: dict[str, Any], reports: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, list[str]]:
    errors = _resolved_errors(candidate, policy)
    if errors:
        return None, errors
    required_runs = policy["qualification"]["required_runs"]
    required_by_slot = {
        (item["duration_minutes"], item["mode"], item["scenario"]): item for item in required_runs
    }
    found: dict[tuple[int, str, str], dict[str, Any]] = {}
    for index, report in enumerate(reports):
        label = f"report[{index}]"
        if report.get("leafos_object") != "medium_moe_benchmark_report":
            errors.append(f"{label} is not a medium-MoE benchmark report")
            continue
        if report.get("policy_id") != policy["policy_id"]:
            errors.append(f"{label} policy_id does not match")
        if report.get("candidate_model_id") != candidate["identity"]["model_id"]:
            errors.append(f"{label} candidate_model_id does not match")
        slot = (report.get("duration_minutes"), report.get("mode"), report.get("scenario"))
        if slot not in required_by_slot:
            errors.append(f"{label} does not match a policy.required_runs slot")
            continue
        if slot in found:
            errors.append(f"duplicate qualification report for {slot[0]}m {slot[2]}")
            continue
        gate_results = report.get("gate_results")
        if not isinstance(gate_results, dict) or not gate_results:
            errors.append(f"{label} has no gate_results")
        elif report.get("benchmark_passed") is not all(value is True for value in gate_results.values()):
            errors.append(f"{label} benchmark_passed disagrees with gate_results")
        if report.get("run_qualifies_for_portfolio") is not report.get("benchmark_passed"):
            errors.append(f"{label} portfolio status disagrees with benchmark_passed")
        if report.get("promotion_eligible") is not False:
            errors.append(f"{label} must not claim promotion eligibility by itself")
        if report.get("automatic_promotion") is not False:
            errors.append(f"{label} must not claim automatic promotion")
        found[slot] = report
    if errors:
        return None, errors

    run_results = []
    for slot, requirement in required_by_slot.items():
        report = found.get(slot)
        run_results.append(
            {
                "duration_minutes": slot[0],
                "mode": slot[1],
                "scenario": slot[2],
                "purpose": requirement["purpose"],
                "present": report is not None,
                "passed": bool(report and report.get("benchmark_passed") is True),
            }
        )
    all_passed = all(item["present"] and item["passed"] for item in run_results)
    qualification = {
        "leafos_object": "medium_moe_qualification_report",
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy_id": policy["policy_id"],
        "candidate_model_id": candidate["identity"]["model_id"],
        "required_runs": run_results,
        "all_required_runs_passed": all_passed,
        "promotion_eligible": all_passed,
        "automatic_promotion": False,
        "operator_approval_required": True,
        "status": "eligible_for_operator_approval" if all_passed else "evidence_incomplete_or_failed",
    }
    return qualification, []


def _print_errors(errors: list[str]) -> int:
    for error in errors:
        print(f"invalid contract: {error}", file=sys.stderr)
    return 1


def cmd_validate(candidate: dict[str, Any], policy: dict[str, Any], args: argparse.Namespace) -> int:
    errors = validate_candidate(candidate, policy, require_resolved=args.require_resolved)
    if errors:
        return _print_errors(errors)
    if candidate["status"] == "template":
        print("medium-MoE candidate template is valid but unresolved and cannot run")
    else:
        print(f"medium-MoE candidate is resolved: {candidate['identity']['model_id']}")
    return 0


def cmd_manifest(candidate: dict[str, Any], policy: dict[str, Any], args: argparse.Namespace) -> int:
    errors = _resolved_errors(candidate, policy)
    if errors:
        return _print_errors(errors)
    try:
        manifest = build_manifest(candidate, policy, args.mode, args.scenario, args.duration_minutes)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    write_json(Path(args.output), manifest)
    print(args.output)
    return 0


def cmd_evaluate(candidate: dict[str, Any], policy: dict[str, Any], args: argparse.Namespace) -> int:
    try:
        metrics = load_json(Path(args.metrics))
        report, errors = evaluate_metrics(
            candidate, policy, metrics, args.mode, args.scenario, args.duration_minutes
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    if errors:
        return _print_errors(errors)
    assert report is not None
    write_json(Path(args.output), report)
    print(args.output)
    return 0


def cmd_qualify(candidate: dict[str, Any], policy: dict[str, Any], args: argparse.Namespace) -> int:
    reports: list[dict[str, Any]] = []
    evidence_files = []
    try:
        for value in args.reports:
            path = Path(value)
            reports.append(load_json(path))
            evidence_files.append(
                {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            )
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    qualification, errors = qualify_reports(candidate, policy, reports)
    if errors:
        return _print_errors(errors)
    assert qualification is not None
    qualification["evidence_files"] = evidence_files
    write_json(Path(args.output), qualification)
    print(args.output)
    return 0


def cmd_run(candidate: dict[str, Any], policy: dict[str, Any], args: argparse.Namespace) -> int:
    errors = _resolved_errors(candidate, policy)
    if errors:
        return _print_errors(errors)
    model_path = Path(candidate["runtime"]["model_path"])
    if not model_path.is_file():
        print(f"local model artifact not found: {model_path}", file=sys.stderr)
        return 2
    command = candidate["runtime"]["benchmark_command"]
    if str(model_path) not in command:
        print("benchmark_command must include the resolved model_path explicitly", file=sys.stderr)
        return 2
    try:
        manifest = build_manifest(candidate, policy, args.mode, args.scenario, args.duration_minutes)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    write_json(Path(args.manifest), manifest)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--policy", default=str(DEFAULT_POLICY), help="path to medium-MoE policy JSON")
    result.add_argument("--profile", default=str(DEFAULT_CANDIDATE), help="path to candidate JSON")
    commands = result.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("--require-resolved", action="store_true")

    qualify = commands.add_parser("qualify")
    qualify.add_argument("--reports", nargs="+", required=True)
    qualify.add_argument("--output", required=True)

    for name in ("manifest", "evaluate", "run"):
        command = commands.add_parser(name)
        command.add_argument("--mode", choices=MODES, required=True)
        command.add_argument("--scenario", choices=SCENARIOS, required=True)
        command.add_argument("--duration-minutes", type=int, choices=(4, 8, 64), required=True)
        if name == "manifest":
            command.add_argument("--output", required=True)
        elif name == "evaluate":
            command.add_argument("--metrics", required=True)
            command.add_argument("--output", required=True)
        else:
            command.add_argument("--manifest", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        candidate = load_json(Path(args.profile))
        policy = load_json(Path(args.policy))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    handlers = {
        "validate": cmd_validate,
        "manifest": cmd_manifest,
        "evaluate": cmd_evaluate,
        "qualify": cmd_qualify,
        "run": cmd_run,
    }
    return handlers[args.command](candidate, policy, args)


if __name__ == "__main__":
    raise SystemExit(main())
