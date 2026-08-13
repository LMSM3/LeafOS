#!/usr/bin/env python3
"""Canonical runtime-profile / capability manifest resolver.

WO-019 (Persistent Reasoning Memory), tranche 019-A.

This module is the SINGLE authority for resolving a named runtime profile
(from ``config/runtime-profiles.json``) plus command-line overrides into the
capability manifest defined by the work order:

    {
      "profile": "continual",
      "provider": "llama.cpp",
      "model": "resolved-model-id",
      "context_limit": 65536,
      "max_output_tokens": 8192,
      "reasoning_budget_requested": 16384,
      "memory_pack_tokens": 12288,
      "capability_status": "supported"
    }

Gate G2 requires that Bash and PowerShell produce byte-equivalent canonical
JSON for the same configuration. That guarantee is provided here: both shell
wrappers MUST invoke this module (via ``python3``/``python``) rather than
re-implementing resolution logic, so there is exactly one code path that
computes and serializes the manifest.

Canonical JSON serialization rules used here (and required for equivalence):
  - keys sorted
  - compact separators: ``(",", ":")``
  - UTF-8, no trailing whitespace beyond a single trailing newline
  - numbers emitted as JSON integers/strings only (no floats, no NaN)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from gguf_metadata import GGUFError, read_metadata

RESOLUTION_PRECEDENCE = (
    "command_line_override",
    "selected_runtime_profile",
    "provider_supported_limit",
    "model_metadata",
    "safe_compatibility_default",
)

FALLBACK_PROFILE = "compat-4k"


class ProfileResolutionError(RuntimeError):
    """Raised when a profile cannot be resolved and no safe fallback applies."""


def _load_profiles_doc(profiles_file: Path) -> Dict[str, Any]:
    try:
        with profiles_file.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise ProfileResolutionError(
            f"runtime profiles file not found: {profiles_file}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ProfileResolutionError(
            f"runtime profiles file is not valid JSON: {profiles_file}: {exc}"
        ) from exc


def _model_capabilities(model_path: Optional[str]) -> Dict[str, Any]:
    if not model_path or model_path == "unresolved":
        return {"status": "unresolved", "context_limit": None, "architecture": None}
    path = Path(model_path)
    if not path.is_file():
        looks_like_path = path.suffix.lower() == ".gguf" or any(separator in model_path for separator in ("/", "\\"))
        return {
            "status": "missing" if looks_like_path else "unresolved_identifier",
            "context_limit": None, "architecture": None,
        }
    if path.suffix.lower() != ".gguf":
        return {"status": "unknown_format", "context_limit": None, "architecture": None}
    try:
        metadata = read_metadata(path)
    except (OSError, GGUFError) as exc:
        return {"status": "invalid", "context_limit": None, "architecture": None, "error": str(exc)}
    return {
        "status": "verified" if metadata["context_length"] else "metadata_incomplete",
        "context_limit": metadata["context_length"], "architecture": metadata["architecture"],
        "name": metadata["name"], "gguf_version": metadata["version"],
    }


def resolve_manifest(
    profiles_file: Path,
    profile_name: str,
    provider: str,
    model: Optional[str] = None,
    ctx_override: Optional[int] = None,
    tokens_override: Optional[int] = None,
    reasoning_budget_override: Optional[int] = None,
) -> Dict[str, Any]:
    """Resolve the canonical capability manifest for one profile/provider/model.

    Precedence (highest first): command_line_override > selected_runtime_profile
    > safe_compatibility_default (compat-4k fallback on unknown profile).
    """
    doc = _load_profiles_doc(profiles_file)
    profiles = doc.get("profiles", {})

    used_profile_name = profile_name
    profile = profiles.get(profile_name)
    if profile is None:
        # Unknown profile: fall back per fallback_policy.on_unsupported_model.
        fallback_name = doc.get("fallback_policy", {}).get(
            "on_unsupported_model", FALLBACK_PROFILE
        )
        profile = profiles.get(fallback_name)
        if profile is None:
            raise ProfileResolutionError(
                f"unknown profile '{profile_name}' and no fallback profile "
                f"'{fallback_name}' available"
            )
        used_profile_name = fallback_name

    capabilities = _model_capabilities(model)
    requested_context = int(profile["context_size"])
    supported_context = capabilities.get("context_limit")
    if supported_context and requested_context > int(supported_context):
        fallback_name = doc.get("fallback_policy", {}).get("on_unsupported_model", FALLBACK_PROFILE)
        profile = profiles.get(fallback_name)
        if profile is None:
            raise ProfileResolutionError(
                f"model context limit {supported_context} is below requested {requested_context} and fallback is unavailable"
            )
        used_profile_name = fallback_name

    context_limit = profile["context_size"]
    max_output_tokens = profile["max_output_tokens"]
    reasoning_budget = profile["reasoning_budget_requested"]
    memory_pack_tokens = profile["memory_pack_tokens"]

    if reasoning_budget in ("auto", None):
        reasoning_budget = 0

    # command_line_override takes precedence over selected_runtime_profile.
    if ctx_override is not None:
        context_limit = ctx_override
    if tokens_override is not None:
        max_output_tokens = tokens_override
    if reasoning_budget_override is not None:
        reasoning_budget = reasoning_budget_override

    model_id = model if model else "unresolved"
    required_capacity = int(reasoning_budget) + int(max_output_tokens) + int(memory_pack_tokens) + int(doc.get("safety_reserve_tokens", 0))
    if required_capacity > int(context_limit):
        raise ProfileResolutionError(
            f"impossible allocation: context {context_limit} < reasoning+output+memory+reserve {required_capacity}"
        )
    if capabilities["status"] == "missing":
        capability_status = "unsupported"
    elif used_profile_name == FALLBACK_PROFILE:
        capability_status = "fallback"
    elif capabilities["status"] == "verified":
        capability_status = "supported"
    else:
        capability_status = "unverified"

    manifest = {
        "profile": used_profile_name,
        "provider": provider,
        "model": model_id,
        "context_limit": int(context_limit),
        "max_output_tokens": int(max_output_tokens),
        "reasoning_budget_requested": int(reasoning_budget),
        "memory_pack_tokens": int(memory_pack_tokens),
        "capability_status": capability_status,
        "model_capabilities": capabilities,
        "capacity_required_tokens": required_capacity,
    }
    return manifest


def to_canonical_json(manifest: Dict[str, Any]) -> str:
    """Serialize a manifest as canonical JSON: sorted keys, compact separators."""
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"))


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve the WO-019 runtime capability manifest (canonical JSON)."
    )
    parser.add_argument(
        "--profiles-file",
        required=True,
        help="Path to config/runtime-profiles.json",
    )
    parser.add_argument("--profile", required=True, help="Named runtime profile")
    parser.add_argument("--provider", required=True, help="Provider identifier, e.g. llama.cpp")
    parser.add_argument("--model", default=None, help="Resolved model id or file path")
    parser.add_argument("--ctx", type=int, default=None, help="Command-line context override")
    parser.add_argument("--tokens", type=int, default=None, help="Command-line max-output-tokens override")
    parser.add_argument(
        "--reasoning-budget", type=int, default=None, help="Command-line reasoning-budget override"
    )
    args = parser.parse_args(argv)

    try:
        manifest = resolve_manifest(
            profiles_file=Path(args.profiles_file),
            profile_name=args.profile,
            provider=args.provider,
            model=args.model,
            ctx_override=args.ctx,
            tokens_override=args.tokens,
            reasoning_budget_override=args.reasoning_budget,
        )
    except ProfileResolutionError as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True, separators=(",", ":")))
        return 1

    sys.stdout.write(to_canonical_json(manifest))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
