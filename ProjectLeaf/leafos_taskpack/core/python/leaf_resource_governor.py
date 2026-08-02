#!/usr/bin/env python3
"""Deterministic resource policy for the LeafOS resident stack."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = ROOT / "config" / "resident-stack-policy.json"
POLICY_OBJECT = "leafos.resource_policy"
POLICY_VERSION = 1
DECISION_OBJECT = "leafos.resource_decision"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _bounded_number(value: Any, name: str, minimum: float, maximum: float) -> float:
    result = _number(value)
    if result is None or not minimum <= result <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return result


def validate_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("resource policy must be an object")
    if value.get("leafos_object") != POLICY_OBJECT or value.get("version") != POLICY_VERSION:
        raise ValueError(f"resource policy requires {POLICY_OBJECT} version {POLICY_VERSION}")
    profiles = value.get("profiles")
    required_profiles = {"auto-idle", "auto-interactive", "quiet", "full"}
    if not isinstance(profiles, dict) or not required_profiles.issubset(profiles):
        raise ValueError("resource policy is missing a required profile")
    clean_profiles: dict[str, dict[str, float | int]] = {}
    for name in sorted(required_profiles):
        profile = profiles.get(name)
        if not isinstance(profile, dict):
            raise ValueError(f"profiles.{name} must be an object")
        clean_profiles[name] = {
            "cpu_target_percent": _bounded_number(profile.get("cpu_target_percent"), f"profiles.{name}.cpu_target_percent", 1, 100),
            "gpu_target_percent": _bounded_number(profile.get("gpu_target_percent"), f"profiles.{name}.gpu_target_percent", 1, 100),
            "max_cpu_slots": int(_bounded_number(profile.get("max_cpu_slots"), f"profiles.{name}.max_cpu_slots", 1, 64)),
        }
    activity = value.get("activity")
    limits = value.get("limits")
    tuning = value.get("tuning")
    budgets = value.get("budgets")
    if not all(isinstance(item, dict) for item in (activity, limits, tuning, budgets)):
        raise ValueError("activity, limits, tuning, and budgets must be objects")
    clean = {
        "leafos_object": POLICY_OBJECT,
        "version": POLICY_VERSION,
        "profiles": clean_profiles,
        "activity": {
            "interactive_input_seconds": _bounded_number(activity.get("interactive_input_seconds"), "activity.interactive_input_seconds", 0.1, 300),
            "idle_ramp_seconds": _bounded_number(activity.get("idle_ramp_seconds"), "activity.idle_ramp_seconds", 0, 600),
            "responsiveness_soft_ms": _bounded_number(activity.get("responsiveness_soft_ms"), "activity.responsiveness_soft_ms", 10, 5000),
            "responsiveness_hard_ms": _bounded_number(activity.get("responsiveness_hard_ms"), "activity.responsiveness_hard_ms", 10, 10000),
        },
        "limits": {
            "ram_used_percent": _bounded_number(limits.get("ram_used_percent"), "limits.ram_used_percent", 50, 100),
            "vram_used_percent": _bounded_number(limits.get("vram_used_percent"), "limits.vram_used_percent", 50, 100),
            "gpu_temperature_soft_c": _bounded_number(limits.get("gpu_temperature_soft_c"), "limits.gpu_temperature_soft_c", 30, 120),
            "gpu_temperature_hard_c": _bounded_number(limits.get("gpu_temperature_hard_c"), "limits.gpu_temperature_hard_c", 30, 120),
        },
        "tuning": {
            "ewma_alpha": _bounded_number(tuning.get("ewma_alpha"), "tuning.ewma_alpha", 0.01, 1),
            "hysteresis_percent": _bounded_number(tuning.get("hysteresis_percent"), "tuning.hysteresis_percent", 0, 50),
            "cooldown_seconds": _bounded_number(tuning.get("cooldown_seconds"), "tuning.cooldown_seconds", 0, 300),
            "provider_delay_step_seconds": _bounded_number(tuning.get("provider_delay_step_seconds"), "tuning.provider_delay_step_seconds", 0, 30),
            "provider_delay_max_seconds": _bounded_number(tuning.get("provider_delay_max_seconds"), "tuning.provider_delay_max_seconds", 0, 300),
        },
        "budgets": {
            "unattended_minutes": int(_bounded_number(budgets.get("unattended_minutes"), "budgets.unattended_minutes", 1, 10080)),
            "max_iterations": int(_bounded_number(budgets.get("max_iterations"), "budgets.max_iterations", 1, 10000)),
            "max_failures": int(_bounded_number(budgets.get("max_failures"), "budgets.max_failures", 1, 1000)),
            "max_changed_files": int(_bounded_number(budgets.get("max_changed_files"), "budgets.max_changed_files", 1, 100000)),
        },
    }
    if clean["activity"]["responsiveness_hard_ms"] < clean["activity"]["responsiveness_soft_ms"]:
        raise ValueError("responsiveness_hard_ms must be at least responsiveness_soft_ms")
    if clean["limits"]["gpu_temperature_hard_c"] < clean["limits"]["gpu_temperature_soft_c"]:
        raise ValueError("gpu_temperature_hard_c must be at least gpu_temperature_soft_c")
    return clean


def load_policy(path: str | Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(f"unable to load resource policy {source}: {error}") from error
    return validate_policy(value)


def _ratio_percent(used: Any, total: Any) -> float | None:
    used_number = _number(used)
    total_number = _number(total)
    if used_number is None or total_number is None or total_number <= 0:
        return None
    return used_number * 100.0 / total_number


def _sample_metrics(sample: dict[str, Any]) -> dict[str, float | None]:
    hardware = sample.get("hardware", sample) if isinstance(sample, dict) else {}
    cpu = hardware.get("cpu", {}) if isinstance(hardware.get("cpu"), dict) else {}
    gpu = hardware.get("gpu", {}) if isinstance(hardware.get("gpu"), dict) else {}
    memory = hardware.get("memory", {}) if isinstance(hardware.get("memory"), dict) else {}
    return {
        "cpu_percent": _number(cpu.get("utilization_percent", hardware.get("cpu_percent"))),
        "gpu_percent": _number(gpu.get("utilization_percent")),
        "ram_percent": _ratio_percent(memory.get("ram_used_gb", hardware.get("ram_used_gb")), memory.get("ram_total_gb", hardware.get("ram_total_gb"))),
        "vram_percent": _ratio_percent(gpu.get("vram_used_gb"), gpu.get("vram_total_gb")),
        "gpu_temperature_c": _number(gpu.get("temperature_celsius", gpu.get("temperature_c"))),
    }


def _ewma(current: float | None, previous: Any, alpha: float) -> float | None:
    old = _number(previous)
    if current is None:
        return old
    if old is None:
        return current
    return alpha * current + (1.0 - alpha) * old


def decide(
    policy: dict[str, Any],
    sample: dict[str, Any],
    facts: dict[str, Any],
    previous: dict[str, Any] | None = None,
    *,
    now_monotonic: float = 0.0,
) -> dict[str, Any]:
    """Return one side-effect-free scheduling decision from normalized facts."""
    policy = validate_policy(policy)
    previous = previous if isinstance(previous, dict) else {}
    raw = _sample_metrics(sample)
    alpha = float(policy["tuning"]["ewma_alpha"])
    previous_smoothed = previous.get("smoothed", {}) if isinstance(previous.get("smoothed"), dict) else {}
    smoothed = {
        name: _ewma(value, previous_smoothed.get(name), alpha)
        for name, value in raw.items()
    }
    mode = str(facts.get("mode", "auto")).lower()
    if mode not in {"auto", "quiet", "full"}:
        raise ValueError("resource mode must be auto, quiet, or full")
    queue_ready = max(0, int(facts.get("queue_ready", 0)))
    queue_active = max(0, int(facts.get("queue_active", 0)))
    productive = queue_ready + queue_active > 0
    input_idle = _number(facts.get("input_idle_seconds"))
    responsiveness = _number(facts.get("responsiveness_ms"))
    run_state = str(facts.get("run_state", "running"))
    provider_health = str(facts.get("provider_health", "unknown"))
    gpu_needed = bool(facts.get("gpu_needed", queue_ready > 0))

    hard_reason = ""
    if run_state in {"stopped", "stopping", "drained", "draining", "paused"}:
        hard_reason = f"run_{run_state}"
    elif responsiveness is not None and responsiveness >= float(policy["activity"]["responsiveness_hard_ms"]):
        hard_reason = "responsiveness_hard"
    elif smoothed["gpu_temperature_c"] is not None and smoothed["gpu_temperature_c"] >= float(policy["limits"]["gpu_temperature_hard_c"]):
        hard_reason = "gpu_temperature_hard"
    elif smoothed["ram_percent"] is not None and smoothed["ram_percent"] >= float(policy["limits"]["ram_used_percent"]):
        hard_reason = "ram_pressure"
    elif smoothed["vram_percent"] is not None and smoothed["vram_percent"] >= float(policy["limits"]["vram_used_percent"]):
        hard_reason = "vram_pressure"
    elif gpu_needed and provider_health not in {"ready", "running", "off"}:
        hard_reason = "provider_unavailable"

    if hard_reason:
        profile_name = "pressure"
        profile = {"cpu_target_percent": 0.0, "gpu_target_percent": 0.0, "max_cpu_slots": 0}
        reason = hard_reason
        claim_allowed = False
    elif not productive:
        profile_name = "waiting"
        profile = {"cpu_target_percent": 0.0, "gpu_target_percent": 0.0, "max_cpu_slots": 0}
        reason = "no_productive_backlog"
        claim_allowed = False
    else:
        recent_input = input_idle is not None and input_idle <= float(policy["activity"]["interactive_input_seconds"])
        soft_latency = responsiveness is not None and responsiveness >= float(policy["activity"]["responsiveness_soft_ms"])
        soft_temperature = smoothed["gpu_temperature_c"] is not None and smoothed["gpu_temperature_c"] >= float(policy["limits"]["gpu_temperature_soft_c"])
        if mode == "auto":
            activity_limit = float(policy["activity"]["interactive_input_seconds"])
            ramp_seconds = float(policy["activity"]["idle_ramp_seconds"])
            ramping = (
                input_idle is not None and ramp_seconds > 0 and activity_limit < input_idle < activity_limit + ramp_seconds
                and not soft_latency and not soft_temperature
            )
            if recent_input or soft_latency or soft_temperature:
                profile_name = "auto-interactive"
            elif ramping:
                profile_name = "auto-ramp"
            else:
                profile_name = "auto-idle"
        else:
            profile_name = mode
        if profile_name == "auto-ramp":
            ratio = (float(input_idle) - activity_limit) / ramp_seconds
            interactive_profile = policy["profiles"]["auto-interactive"]
            idle_profile = policy["profiles"]["auto-idle"]
            profile = {
                "cpu_target_percent": float(interactive_profile["cpu_target_percent"]) + ratio * (float(idle_profile["cpu_target_percent"]) - float(interactive_profile["cpu_target_percent"])),
                "gpu_target_percent": float(interactive_profile["gpu_target_percent"]) + ratio * (float(idle_profile["gpu_target_percent"]) - float(interactive_profile["gpu_target_percent"])),
                "max_cpu_slots": max(1, round(float(interactive_profile["max_cpu_slots"]) + ratio * (float(idle_profile["max_cpu_slots"]) - float(interactive_profile["max_cpu_slots"])))),
            }
        else:
            profile = policy["profiles"][profile_name]
        if recent_input:
            reason = "recent_operator_input"
        elif soft_latency:
            reason = "responsiveness_soft"
        elif soft_temperature:
            reason = "gpu_temperature_soft"
        elif profile_name == "auto-ramp":
            reason = "idle_ramp"
        else:
            reason = "productive_backlog"
        claim_allowed = queue_ready > 0

    target_overrides = facts.get("target_overrides", {})
    if profile_name not in {"pressure", "waiting"} and isinstance(target_overrides, dict) and target_overrides:
        profile = dict(profile)
        if "cpu_percent" in target_overrides:
            profile["cpu_target_percent"] = _bounded_number(
                target_overrides["cpu_percent"], "target_overrides.cpu_percent", 1, 100,
            )
        if "gpu_percent" in target_overrides:
            profile["gpu_target_percent"] = _bounded_number(
                target_overrides["gpu_percent"], "target_overrides.gpu_percent", 1, 100,
            )

    previous_slots = max(1, int(previous.get("cpu_slots", 1)))
    previous_delay = max(0.0, float(previous.get("provider_delay_seconds", 0.0)))
    previous_changed = _number(previous.get("changed_monotonic"))
    cooldown = float(policy["tuning"]["cooldown_seconds"])
    cooled = previous_changed is None or now_monotonic - previous_changed >= cooldown
    hysteresis = float(policy["tuning"]["hysteresis_percent"])
    cpu_target = float(profile["cpu_target_percent"])
    gpu_target = float(profile["gpu_target_percent"])
    slots = 0 if not claim_allowed else min(previous_slots, int(profile["max_cpu_slots"]))
    delay = previous_delay
    changed = False
    if claim_allowed and cooled and smoothed["cpu_percent"] is not None:
        if smoothed["cpu_percent"] < cpu_target - hysteresis and slots < int(profile["max_cpu_slots"]):
            slots += 1
            changed = True
        elif smoothed["cpu_percent"] > cpu_target + hysteresis and slots > 1:
            slots -= 1
            changed = True
    if claim_allowed and cooled and smoothed["gpu_percent"] is not None:
        step = float(policy["tuning"]["provider_delay_step_seconds"])
        maximum = float(policy["tuning"]["provider_delay_max_seconds"])
        if smoothed["gpu_percent"] > gpu_target + hysteresis:
            new_delay = min(maximum, delay + step)
            changed = changed or new_delay != delay
            delay = new_delay
        elif smoothed["gpu_percent"] < gpu_target - hysteresis:
            new_delay = max(0.0, delay - step)
            changed = changed or new_delay != delay
            delay = new_delay
    if not claim_allowed:
        slots = 0

    return {
        "leafos_object": DECISION_OBJECT,
        "version": 1,
        "profile": profile_name,
        "mode": mode,
        "reason": reason,
        "claim_allowed": claim_allowed,
        "productive_backlog": productive,
        "targets": {"cpu_percent": cpu_target, "gpu_percent": gpu_target},
        "current": raw,
        "smoothed": smoothed,
        "cpu_slots": slots,
        "provider_delay_seconds": round(delay, 3),
        "changed_monotonic": now_monotonic if changed or previous_changed is None else previous_changed,
        "input_idle_seconds": input_idle,
        "responsiveness_ms": responsiveness,
    }
