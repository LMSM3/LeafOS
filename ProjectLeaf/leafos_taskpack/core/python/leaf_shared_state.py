#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared read-only state view for CLI, web, and TUI surfaces.

This module is the single source of truth for non-interactive state reads.
It never mutates the durable Monday instance and never downloads model
weights.  Projections that need mutation must route through the durable
bridge (and therefore a recorded capability request).
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[2]
_CONFIG = _ROOT / "config" / "runtime.json"
_CAPABILITY_REGISTRY = _ROOT / "config" / "capability-registry.json"
_ROOT_JSON = _ROOT.parents[1] / "leafos.root.json"

_PYTHON_DIR = _ROOT / "core" / "python"
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

try:
    from leaf_runtime import LeafRuntimeSelector
except Exception:  # pragma: no cover - fallback used only in damaged installs
    LeafRuntimeSelector = None  # type: ignore

try:
    from leaf_durable_bridge import (
        MondayDurableBridge,
        DurableBridgeError,
        CAPABILITY_REGISTRY_PATH,
    )
except Exception:
    MondayDurableBridge = None  # type: ignore
    DurableBridgeError = None  # type: ignore
    CAPABILITY_REGISTRY_PATH = _CAPABILITY_REGISTRY  # type: ignore


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _runtime_config() -> Dict[str, Any]:
    return _read_json(_CONFIG, {"schema_version": 1, "leafos_runtime": {}})


def _root_metadata() -> Dict[str, Any]:
    data = _read_json(
        _ROOT_JSON,
        {
            "leafos_object": "leafos.root.v1",
            "version": "0.0.0",
            "documentation": {},
            "configuration_authorities": {},
        },
    )
    return {
        "leafos_object": "leafos.root.v1",
        "version": data.get("version", "0.0.0"),
        "root_path": str(_ROOT_JSON),
        "configuration_authorities": data.get("configuration_authorities", {}),
        "documentation": data.get("documentation", {}),
        "download_boundary": data.get("download_boundary", "deny"),
        "safe_default": data.get("safe_default", False),
    }


def _capability_registry_summary() -> Dict[str, Any]:
    target = CAPABILITY_REGISTRY_PATH
    data = _read_json(
        target,
        {
            "schema": "leafos.capability_registry.v1",
            "version": 1,
            "capabilities": [],
        },
    )
    caps = data.get("capabilities", [])
    return {
        "leafos_object": "leafos.capability_registry_summary.v1",
        "source": str(target),
        "schema": data.get("schema"),
        "version": data.get("version"),
        "default_policy": data.get("default_policy", "disallow"),
        "rule_order": data.get("rule_order", []),
        "count": len(caps),
        "allowed": [c["key"] for c in caps if c.get("policy") == "allow"],
        "denied": [c["key"] for c in caps if c.get("policy") == "deny"],
        "audited": [c["key"] for c in caps if c.get("policy") == "audit"],
    }


def build_runtime_selection(
    *,
    coding_language: str = "",
    coding_model: str = "",
    coding_tier: str = "",
) -> Dict[str, Any]:
    """Return runtime/model selection without weight download."""
    if LeafRuntimeSelector is not None:
        return LeafRuntimeSelector(_ROOT).select(
            coding_language=coding_language,
            coding_model_choice=coding_model,
            coding_tier=coding_tier,
        )

    cfg = _runtime_config()
    rt = cfg.get("leafos_runtime", {})
    defaults = rt.get("defaults", {})
    return {
        "schema_version": cfg.get("schema_version", 1),
        "selection": {
            "main_model": {},
            "scheduler_model": {},
            "coder_model": {},
            "coding_choice": {
                "language": coding_language or defaults.get("coding_language", "python"),
                "model_key": coding_model or defaults.get("coding_model_choice", "gemma4-coder"),
                "tier": coding_tier or defaults.get("coding_tier", "builder"),
                "backend": "python",
                "source": "runtime-config-fallback",
            },
            "language_hint": coding_language or defaults.get("coding_language", "python"),
            "role_policy": rt.get("role_policy", {}),
        },
    }


def build_durable_monday_state(instance_name: str = "monday-primary") -> Dict[str, Any]:
    """Read Monday durable state via the bridge without mutation authority."""
    if MondayDurableBridge is None:
        return {
            "leafos_object": "leafos.durable_monday_state.v1",
            "instance": instance_name,
            "available": False,
            "reason": "durable bridge module is not importable",
        }
    try:
        bridge = MondayDurableBridge(source="shared-state-view")
        report = bridge.status()
    except DurableBridgeError as error:
        return {
            "leafos_object": "leafos.durable_monday_state.v1",
            "instance": instance_name,
            "available": False,
            "reason": str(error),
        }
    payload = report.get("payload", report)
    return {
        "leafos_object": "leafos.durable_monday_state.v1",
        "instance": instance_name,
        "available": payload.get("status") != "not_initialized",
        "status": payload.get("status"),
        "transcript_head": payload.get("transcript_head"),
        "transcript_cursor": payload.get("transcript_cursor"),
        "event_count": payload.get("event_count"),
        "fact_count": payload.get("fact_count"),
        "checkpoint_count": payload.get("checkpoint_count"),
        "claim_metrics": payload.get("claim_metrics"),
        "next_action": payload.get("next_action"),
        "kv_cache_authoritative": payload.get("kv_cache_authoritative"),
        "raw": payload,
    }


def _unique_repos(selection: Dict[str, Any], runtime: Dict[str, Any]) -> List[Dict[str, str]]:
    repos: List[Dict[str, str]] = []

    def add(role: str, obj: Dict[str, Any]) -> None:
        repo = obj.get("repo")
        key = obj.get("key")
        if repo and key:
            repos.append({"role": role, "key": str(key), "repo": str(repo)})

    sel = selection.get("selection", {})
    add("main", sel.get("main_model", {}))
    add("scheduler", sel.get("scheduler_model", {}))
    add("coder", sel.get("coder_model", {}))
    for item in runtime.get("main_models", []):
        add("main_pool", item)
    for item in runtime.get("coder_models", []):
        add("coder_pool", item)

    seen: set[str] = set()
    result: List[Dict[str, str]] = []
    for item in repos:
        if item["repo"] in seen:
            continue
        seen.add(item["repo"])
        result.append(item)
    return result


def _local_metadata(repos: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Return repo metadata without any network access."""
    return [
        {
            "repo": item["repo"],
            "key": item["key"],
            "role": item["role"],
            "ok": None,
            "sha": None,
            "last_modified": None,
            "local_only": True,
        }
        for item in repos
    ]


def build_shared_state(
    *,
    fetch_remote_metadata: bool = False,
    coding_language: str = "",
    coding_model: str = "",
    coding_tier: str = "",
) -> Dict[str, Any]:
    """Build the authoritative, read-only shared state document."""
    started = time.perf_counter()
    runtime_cfg = _runtime_config()
    rt = runtime_cfg.get("leafos_runtime", {})
    selection = build_runtime_selection(
        coding_language=coding_language,
        coding_model=coding_model,
        coding_tier=coding_tier,
    )
    repos = _unique_repos(selection, rt)

    metadata_block: Dict[str, Any] = {
        "schema_version": 1,
        "source": "steady-state-fallback",
        "remote_metadata_only": True,
        "downloaded_weights": False,
        "models": _local_metadata(repos),
    }
    metadata_block["success"] = bool(metadata_block["models"])

    return {
        "leafos_object": "leafos.shared_state.v1",
        "built_at": _utc_now(),
        "duration_seconds": round(time.perf_counter() - started, 4),
        "root": _root_metadata(),
        "capability_registry": _capability_registry_summary(),
        "runtime": runtime_cfg,
        "selection": selection.get("selection", {}),
        "durable_monday": build_durable_monday_state(),
        "metadata": metadata_block,
        "mutation_policy": {
            "shared_view_is_read_only": True,
            "mutation_path": "durable_bridge.request_capability -> transcript_event -> native_validator -> checkpoint",
            "direct_mutation_allowed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="leaf-shared-state")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--remote-metadata",
        action="store_true",
        help="fetch remote metadata (still no weight downloads)",
    )
    parser.add_argument("--language", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--tier", default="")
    args = parser.parse_args(argv)

    state = build_shared_state(
        fetch_remote_metadata=args.remote_metadata,
        coding_language=args.language,
        coding_model=args.model,
        coding_tier=args.tier,
    )
    print(json.dumps(state, indent=2 if not args.json else None, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
