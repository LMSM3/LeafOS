#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LeafOS web state -- slow-growing web/runtime bridge.

This module builds a safe, read-only state document for dashboards and LAN
serve endpoints.  It never downloads model weights.  The optional metadata
refresh only asks repository APIs for lightweight model metadata and falls back
to local steady-state config/cache if the network is unavailable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[2]
_CONFIG = _ROOT / "config" / "runtime.json"
_FALLBACK = _ROOT / "config" / "web_state.fallback.json"
_CAPABILITY_REGISTRY = _ROOT / "config" / "capability-registry.json"
_REPORT_DIR = _ROOT / "reports" / "web_state"
_METADATA_CACHE = _REPORT_DIR / "model_metadata.latest.json"
_STATE_CACHE = _REPORT_DIR / "latest.json"

_PYTHON_DIR = _ROOT / "core" / "python"
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

try:
    from leaf_runtime import LeafRuntimeSelector
except Exception:  # pragma: no cover - fallback used only in damaged installs
    LeafRuntimeSelector = None  # type: ignore

try:
    from leaf_durable_bridge import MondayDurableBridge, DurableBridgeError
except Exception:  # pragma: no cover - fallback used only in damaged installs
    MondayDurableBridge = None  # type: ignore
    DurableBridgeError = None  # type: ignore


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return default


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _runtime_config() -> Dict[str, Any]:
    return _read_json(_CONFIG, {"schema_version": 1, "leafos_runtime": {}})


def _fallback_state() -> Dict[str, Any]:
    return _read_json(
        _FALLBACK,
        {
            "schema_version": 1,
            "leafos_object": "web_state_fallback",
            "source": "built-in",
            "safe_operation": {
                "default_coding_language": "python",
                "coding_backend": "python",
                "coding_model_choice": "gemma4-coder",
                "coding_tier": "builder",
            },
            "metadata_policy": {
                "remote_metadata_only": True,
                "fallback": "runtime config",
            },
        },
    )


def _capability_registry_summary() -> Dict[str, Any]:
    data = _read_json(
        _CAPABILITY_REGISTRY,
        {
            "schema": "leafos.capability_registry.v1",
            "version": 1,
            "capabilities": [],
        },
    )
    caps = data.get("capabilities", [])
    return {
        "leafos_object": "leafos.capability_registry_summary.v1",
        "schema": data.get("schema"),
        "version": data.get("version"),
        "default_policy": data.get("default_policy", "disallow"),
        "rule_order": data.get("rule_order", []),
        "count": len(caps),
        "allowed": [c["key"] for c in caps if c.get("policy") == "allow"],
        "denied": [c["key"] for c in caps if c.get("policy") == "deny"],
        "audited": [c["key"] for c in caps if c.get("policy") == "audit"],
    }


def _durable_monday_state(instance_name: str = "monday-primary") -> Dict[str, Any]:
    """Read Monday durable state via the bridge without mutation authority."""
    if MondayDurableBridge is None:
        return {
            "leafos_object": "leafos.durable_monday_state.v1",
            "instance": instance_name,
            "available": False,
            "reason": "durable bridge module is not importable",
        }
    try:
        bridge = MondayDurableBridge(source="web-state")
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


def _select_runtime(
    *,
    coding_language: str = "",
    coding_model: str = "",
    coding_tier: str = "",
) -> Dict[str, Any]:
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


def _hf_model_metadata(repo_id: str, timeout: float) -> Dict[str, Any]:
    url = f"https://huggingface.co/api/models/{repo_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "LeafOS-web-state/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    siblings = payload.get("siblings") or []
    return {
        "repo": repo_id,
        "url": url,
        "ok": True,
        "sha": payload.get("sha"),
        "last_modified": payload.get("lastModified"),
        "private": payload.get("private"),
        "gated": payload.get("gated"),
        "downloads": payload.get("downloads"),
        "likes": payload.get("likes"),
        "tags": payload.get("tags", [])[:12],
        "sibling_count": len(siblings),
    }


def refresh_remote_metadata(repos: Iterable[Dict[str, str]], timeout: float = 4.0) -> Dict[str, Any]:
    started = time.perf_counter()
    models: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    for item in repos:
        repo = item["repo"]
        try:
            meta = _hf_model_metadata(repo, timeout=timeout)
            meta["key"] = item["key"]
            meta["role"] = item["role"]
            models.append(meta)
        except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            errors.append({"repo": repo, "key": item["key"], "role": item["role"], "error": str(exc)})

    return {
        "schema_version": 1,
        "source": "huggingface-api",
        "refreshed_at": _utc_now(),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "remote_metadata_only": True,
        "downloaded_weights": False,
        "success": bool(models) and not errors,
        "partial_success": bool(models) and bool(errors),
        "models": models,
        "errors": errors,
    }


def _fallback_metadata(repos: Iterable[Dict[str, str]], reason: str) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "source": "steady-state-fallback",
        "refreshed_at": None,
        "remote_metadata_only": True,
        "downloaded_weights": False,
        "success": False,
        "reason": reason,
        "models": [
            {
                "repo": item["repo"],
                "key": item["key"],
                "role": item["role"],
                "ok": None,
                "sha": None,
                "last_modified": None,
            }
            for item in repos
        ],
        "errors": [],
    }


def load_metadata(
    repos: Iterable[Dict[str, str]],
    *,
    refresh: bool = False,
    write_cache: bool = False,
    timeout: float = 4.0,
) -> Dict[str, Any]:
    repos = list(repos)
    if refresh:
        live = refresh_remote_metadata(repos, timeout=timeout)
        if live.get("models"):
            if write_cache:
                _atomic_write_json(_METADATA_CACHE, live)
            return live
        cached = _read_json(_METADATA_CACHE, None)
        if cached:
            cached["source"] = "cached-after-refresh-failure"
            cached["refresh_error"] = live.get("errors", [])
            return cached
        return _fallback_metadata(repos, "live metadata refresh failed and no cache exists")

    cached = _read_json(_METADATA_CACHE, None)
    if cached:
        cached["source"] = "cached"
        return cached
    return _fallback_metadata(repos, "no metadata refresh requested and no cache exists")


def _local_model_hint(runtime: Dict[str, Any]) -> Dict[str, Any]:
    root_candidates = [
        Path(os.environ.get("LEAF_MODEL_DIR", "")) if os.environ.get("LEAF_MODEL_DIR") else None,
        _ROOT.parent / "leaf_model_installer" / "models",
        Path.home() / ".leaf" / "models",
    ]
    model_root = next((path for path in root_candidates if path and path.is_dir()), root_candidates[-1])
    found = []
    for model in runtime.get("main_models", []) + runtime.get("coder_models", []):
        catalog_key = model.get("catalog_key") or model.get("key")
        found.append(
            {
                "key": model.get("key"),
                "catalog_key": catalog_key,
                "repo": model.get("repo"),
                "configured_quant": model.get("quant") or model.get("default_quant"),
            }
        )
    return {
        "model_root": str(model_root) if model_root else "",
        "models": found,
        "note": "lightweight runtime hint only; use leaf download doctor for full file integrity and hashes",
    }


def build_state(
    *,
    refresh_metadata: bool = False,
    write_cache: bool = False,
    timeout: float = 4.0,
    coding_language: str = "",
    coding_model: str = "",
    coding_tier: str = "",
) -> Dict[str, Any]:
    cfg = _runtime_config()
    runtime = cfg.get("leafos_runtime", {})
    selection = _select_runtime(
        coding_language=coding_language,
        coding_model=coding_model,
        coding_tier=coding_tier,
    )
    repos = _unique_repos(selection, runtime)
    metadata = load_metadata(
        repos,
        refresh=refresh_metadata,
        write_cache=write_cache,
        timeout=timeout,
    )
    fallback = _fallback_state()
    state = {
        "schema_version": 1,
        "leafos_object": "web_state",
        "generated_at": _utc_now(),
        "root": str(_ROOT),
        "web": {
            "default_surface": "python",
            "state_endpoint": "/web-state.json",
            "api_endpoint": "/api/state",
            "status": "developing",
        },
        "selection": selection.get("selection", {}),
        "coding_backend_choice": selection.get("selection", {}).get("coding_choice", {}),
        "model_choices": {
            "main": selection.get("selection", {}).get("main_model", {}),
            "scheduler": selection.get("selection", {}).get("scheduler_model", {}),
            "coder": selection.get("selection", {}).get("coder_model", {}),
            "role_policy": selection.get("selection", {}).get("role_policy", {}),
        },
        "local_model_hint": _local_model_hint(runtime),
        "remote_metadata": metadata,
        "steady_state_fallback": fallback,
        "durable_monday": _durable_monday_state(),
        "capability_registry": _capability_registry_summary(),
        "capability_authority": {
            "registry_source": str(_CAPABILITY_REGISTRY),
            "enforced_by": "core/python/leaf_durable_bridge.py",
            "supported_actions": [
                "request_capability",
                "append_input",
                "record_claim",
                "validate_claim",
                "commit_checkpoint",
                "recover",
                "verify",
            ],
            "denied_actions": [
                "direct_project_mutation",
                "checkpoint_self_declare",
            ],
        },
        "safety": {
            "downloads_model_weights": False,
            "metadata_refresh_requires_flag": True,
            "fallback_available": True,
        },
    }
    if write_cache:
        _atomic_write_json(_STATE_CACHE, state)
    return state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="web-state.py",
        description="Build the LeafOS web/runtime state document",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--refresh-metadata", action="store_true", help="attempt live Hugging Face metadata refresh")
    parser.add_argument("--write", action="store_true", help="write reports/web_state/latest.json")
    parser.add_argument("--out", default="", help="optional output JSON path")
    parser.add_argument("--timeout", type=float, default=4.0, help="metadata request timeout seconds")
    parser.add_argument("--language", default="", help="override coding language")
    parser.add_argument("--coding-model", default="", help="override coding model choice")
    parser.add_argument("--coding-tier", default="", help="override coding worker tier")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    state = build_state(
        refresh_metadata=args.refresh_metadata,
        write_cache=args.write,
        timeout=args.timeout,
        coding_language=args.language,
        coding_model=args.coding_model,
        coding_tier=args.coding_tier,
    )
    if args.out:
        _atomic_write_json(Path(args.out).expanduser().resolve(), state)
    if args.json:
        print(json.dumps(state, indent=2, ensure_ascii=False))
    else:
        choice = state["coding_backend_choice"]
        meta = state["remote_metadata"]
        print("LeafOS web state")
        print(f"  language       : {choice.get('language')}")
        print(f"  coding model   : {choice.get('model_key')} / {choice.get('tier')}")
        print(f"  backend        : {choice.get('backend')}")
        print(f"  metadata source: {meta.get('source')}")
        print(f"  metadata models: {len(meta.get('models', []))}")
        print(f"  fallback       : available")
        if args.write:
            print(f"  wrote          : {_STATE_CACHE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
