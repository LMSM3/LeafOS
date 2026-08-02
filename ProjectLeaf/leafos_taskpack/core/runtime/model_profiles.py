#!/usr/bin/env python3
"""Validated model assignment registry for WO-005-G."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = ROOT / "config" / "model-profiles"
SCHEMA = "leafos.model-profile.v1"
ROLES_LEGACY = {"brain", "coder", "helper", "reviewer", "reporter"}
ROLES_EXTENDED = {
    "brain", "coder", "helper", "reviewer", "reporter",
    "router", "drafter", "summarizer", "critic", "reasoner",
    "judge", "memory", "writer", "classifier", "heavy_reasoner",
    "creative", "security", "synthesizer", "retriever", "repair",
    "reinforcer", "experimental", "chat", "dormant_expert",
}
REQUIRED_LISTS = ("lanes", "contracts", "runtime", "notes")
NEW_ROLE_FIELDS = (
    "base_catalog_key", "recommended_quant", "quality_quant",
    "low_memory_quant", "emergency_quant", "activation",
    "escalation_from", "escalation_to",
)


class ModelProfileError(RuntimeError):
    """Raised when a model profile violates the assignment contract."""


def _require_string(profile: dict, key: str, label: str) -> None:
    if not isinstance(profile.get(key), str) or not profile[key].strip():
        raise ModelProfileError(f"{label}: {key} must be a non-empty string")


def _require_string_list(profile: dict, key: str, label: str, allow_empty: bool = False) -> None:
    values = profile.get(key)
    if not isinstance(values, list):
        raise ModelProfileError(f"{label}: {key} must be a string array")
    if not allow_empty and not values:
        raise ModelProfileError(f"{label}: {key} must be a non-empty string array")
    if not all(isinstance(value, str) and value for value in values):
        raise ModelProfileError(f"{label}: {key} items must be non-empty strings")


def validate_profile(profile: Any, source: Path | None = None) -> dict[str, Any]:
    label = str(source) if source else "model profile"
    if not isinstance(profile, dict):
        raise ModelProfileError(f"{label}: expected a JSON object")

    _require_string(profile, "schema", label)
    _require_string(profile, "profile_id", label)
    if profile["schema"] != SCHEMA:
        raise ModelProfileError(f"{label}: unsupported schema {profile['schema']!r}")
    if source and profile["profile_id"] != source.stem:
        raise ModelProfileError(f"{label}: profile_id must match the filename")

    for key in REQUIRED_LISTS:
        _require_string_list(profile, key, label)
    if len(set(profile["lanes"])) != len(profile["lanes"]):
        raise ModelProfileError(f"{label}: lanes must be unique")
    if not all(lane.startswith("slot.") for lane in profile["lanes"]):
        raise ModelProfileError(f"{label}: every lane must begin with 'slot.'")

    is_extended = isinstance(profile.get("base_catalog_key"), str) and bool(profile["base_catalog_key"].strip())
    if is_extended:
        _require_string(profile, "base_catalog_key", label)
        _require_string(profile, "title", label)
        _require_string(profile, "role", label)
        if profile["role"] not in ROLES_EXTENDED:
            raise ModelProfileError(f"{label}: unsupported role {profile['role']!r}")
        for key in ("recommended_quant", "quality_quant", "low_memory_quant", "emergency_quant", "activation"):
            _require_string(profile, key, label)
        for key in ("escalation_from", "escalation_to"):
            _require_string_list(profile, key, label, allow_empty=True)
    else:
        for key in ("model_repo", "role", "status"):
            _require_string(profile, key, label)
        if profile["role"] not in ROLES_LEGACY:
            raise ModelProfileError(f"{label}: unsupported legacy role {profile['role']!r}")

    return profile


def load_profile(path: Path) -> dict[str, Any]:
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ModelProfileError(f"model profile not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ModelProfileError(f"invalid JSON in {path}: {exc}") from exc
    return validate_profile(profile, path)


def load_profiles(profile_dir: Path = PROFILE_DIR) -> list[dict[str, Any]]:
    if not profile_dir.is_dir():
        raise ModelProfileError(f"model profile directory not found: {profile_dir}")
    paths = sorted(profile_dir.glob("*.json"))
    if not paths:
        raise ModelProfileError(f"no model profiles found in {profile_dir}")
    profiles = [load_profile(path) for path in paths]
    ids = [profile["profile_id"] for profile in profiles]
    if len(set(ids)) != len(ids):
        raise ModelProfileError("model profile ids must be unique")
    return profiles


def route_lane(lane: str, profiles: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = [profile for profile in profiles if lane in profile["lanes"]]
    if not matches:
        raise ModelProfileError(f"no model profile accepts lane: {lane}")
    rank = {
        "always": 0,
        "fast": 0,
        "on_demand": 1,
        "background": 2,
        "dormant": 3,
        "manual": 3,
        "stable_primary_candidate": 0,
        "stable_primary_coder_candidate": 0,
        "helper_candidate": 1,
        "experimental_primary": 2,
    }
    return sorted(matches, key=lambda item: (rank.get(item.get("status") or item.get("activation", ""), 9), item["profile_id"]))


def _summary(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_id": profile["profile_id"],
        "model_repo": profile.get("model_repo", profile.get("base_catalog_key", "")),
        "role": profile["role"],
        "lanes": profile["lanes"],
        "status": profile.get("status", profile.get("activation", "")),
    }


def _emit(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return
    if isinstance(payload, list):
        for item in payload:
            print(f"{item['profile_id']:<34} {item['role']:<8} {item['status']}")
        return
    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="leafctl model-profile")
    parser.add_argument("action", nargs="?", default="list", choices=["list", "show", "validate", "route"])
    parser.add_argument("value", nargs="?")
    parser.add_argument("--profile-dir", type=Path, default=PROFILE_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        profiles = load_profiles(args.profile_dir)
        if args.action == "list":
            payload: Any = [_summary(profile) for profile in profiles]
        elif args.action == "validate":
            payload = {"schema": SCHEMA, "status": "ok", "profile_count": len(profiles)}
        elif args.action == "show":
            if not args.value:
                raise ModelProfileError("show requires PROFILE_ID")
            payload = next((profile for profile in profiles if profile["profile_id"] == args.value), None)
            if payload is None:
                raise ModelProfileError(f"unknown model profile: {args.value}")
        else:
            if not args.value:
                raise ModelProfileError("route requires LANE")
            payload = [_summary(profile) for profile in route_lane(args.value, profiles)]
    except ModelProfileError as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 1
    _emit(payload, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
