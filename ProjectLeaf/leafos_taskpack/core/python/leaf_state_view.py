#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared read-only state view for CLI, web, and future TUI surfaces.

This module is a thin, stable facade over `leaf_shared_state.py`.  It exists so
that CLI/TUI code can import a single module without caring whether the state
came from the runtime selector, the durable bridge, or the web fallback.

All operations are read-only and safe to call anywhere.  Mutations must still
route through `leaf_durable_bridge.py` (and therefore a capability request).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

_HERE = Path(__file__).resolve()
_PYTHON_DIR = _HERE.parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from leaf_shared_state import build_shared_state


def build_state_view(
    *,
    fetch_remote_metadata: bool = False,
    coding_language: str = "",
    coding_model: str = "",
    coding_tier: str = "",
) -> Dict[str, Any]:
    """Build the stable shared-state view for CLI/web/TUI consumers.

    The returned document is always read-only.  It includes the durable Monday
    status, capability registry summary, runtime selection, and an explicit
    mutation policy so callers know where to send write requests.
    """
    state = build_shared_state(
        fetch_remote_metadata=fetch_remote_metadata,
        coding_language=coding_language,
        coding_model=coding_model,
        coding_tier=coding_tier,
    )
    state["leafos_object"] = "leafos.state_view.v1"
    state["view_policy"] = {
        "shared_view_is_read_only": True,
        "mutation_path": "leafctl bloom capability <key> -> leaf_durable_bridge.request_capability -> transcript_event -> native_validator -> checkpoint",
        "direct_mutation_allowed": False,
        "authority_source": "monday-primary",
        "ticket_lease_scope": "single_command",
    }
    registry = state.get("capability_registry", {})
    state["capability_authority"] = {
        "enforced_by": "core/python/leaf_durable_bridge.py",
        "registry_source": registry.get("source"),
        "default_policy": registry.get("default_policy", "disallow"),
        "rule_order": registry.get("rule_order", []),
        "allowed_count": len(registry.get("allowed", [])),
        "denied_count": len(registry.get("denied", [])),
        "audited_count": len(registry.get("audited", [])),
    }
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="leaf-state-view",
        description="Emit the shared read-only state view as JSON",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--remote-metadata",
        action="store_true",
        help="fetch remote metadata (still no weight downloads)",
    )
    parser.add_argument("--language", default="", help="override coding language")
    parser.add_argument("--model", default="", help="override coding model choice")
    parser.add_argument("--tier", default="", help="override coding worker tier")
    args = parser.parse_args(argv)

    view = build_state_view(
        fetch_remote_metadata=args.remote_metadata,
        coding_language=args.language,
        coding_model=args.model,
        coding_tier=args.tier,
    )
    print(json.dumps(view, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
