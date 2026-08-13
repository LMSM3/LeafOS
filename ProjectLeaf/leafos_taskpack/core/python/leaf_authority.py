#!/usr/bin/env python3
"""Shared authority enforcement helper for CLI, loop, and web surfaces.

This module wraps the durable bridge so callers can require capabilities,
attach tickets to mutation operations, and fail fast with audit-friendly
errors.  It is intentionally thin: the durable Monday instance remains the
source of truth; this helper only provides ergonomic enforcement.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

_CORE_PYTHON = Path(__file__).resolve().parent
if str(_CORE_PYTHON) not in sys.path:
    sys.path.insert(0, str(_CORE_PYTHON))

from leaf_durable_bridge import (
    CAPABILITY_REGISTRY_PATH,
    DEFAULT_INSTANCE,
    DurableBridgeError,
    MondayDurableBridge,
    _load_capability_registry,
)


class AuthorityError(DurableBridgeError):
    """Raised when a capability is required but denied or missing."""


def require_capability(
    capability: str,
    *,
    actor: str,
    reason: str = "",
    context: Dict[str, Any] | None = None,
    source: str = "authority",
    instance: Path | None = None,
) -> Dict[str, Any]:
    """Request a capability and raise AuthorityError if denied.

    Returns the durable-bridge response envelope, including the ticket.
    """
    bridge = MondayDurableBridge(instance=instance, source=source)
    response = bridge.request_capability(
        capability, actor=actor, reason=reason, context=context or {}
    )
    payload = response.get("payload", response)
    if not payload.get("allowed"):
        raise AuthorityError(
            f"capability denied: {capability} for actor={actor} "
            f"(policy={payload.get('policy')}, request_id={payload.get('request_id')})"
        )
    return response


def must_have_capability(
    ticket: Dict[str, Any] | None,
    capability: str,
) -> Dict[str, Any]:
    """Validate an existing ticket shape without re-requesting.

    This is intentionally lightweight; cryptographic verification is deferred
    to a future release.  For now the presence of an allowed ticket from the
    bridge is sufficient within the same process/trust boundary.
    """
    if not ticket or ticket.get("leafos_object") != "leafos.capability_ticket.v1":
        raise AuthorityError("invalid or missing capability ticket")
    if ticket.get("capability") != capability:
        raise AuthorityError(
            f"ticket capability mismatch: expected {capability}, "
            f"got {ticket.get('capability')}"
        )
    if not ticket.get("allowed"):
        raise AuthorityError(f"ticket not allowed for capability: {capability}")
    return ticket


def cap_check_naive(capability: str) -> bool:
    """Read-only registry check without recording anything in the transcript.

    Use for UI grey-out / early filtering only.  Real enforcement still
    requires a recorded ticket via require_capability.
    """
    registry = _load_capability_registry()
    for item in registry.get("capabilities", []):
        if item.get("key") == capability:
            return item.get("policy") == "allow"
    return registry.get("default_policy", "disallow") == "allow"


def default_actor() -> str:
    """Return a sensible default actor identifier for the local surface."""
    import getpass

    return f"leafos.{getpass.getuser()}"


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(prog="leaf-authority")
    parser.add_argument("--actor", default=default_actor())
    parser.add_argument("--source", default="authority")
    parser.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    subparsers = parser.add_subparsers(dest="command", required=True)

    req = subparsers.add_parser("require", help="require a capability (fails if denied)")
    req.add_argument("capability")
    req.add_argument("--reason", default=" CLI mutation pre-flight")
    req.add_argument("--context", default="{}")

    chk = subparsers.add_parser("check", help="read-only registry check")
    chk.add_argument("capability")

    subparsers.add_parser("capabilities", help="list registry entries")

    args = parser.parse_args(argv)

    if args.command == "require":
        try:
            result = require_capability(
                args.capability,
                actor=args.actor,
                reason=args.reason,
                context=json.loads(args.context),
                source=args.source,
                instance=args.instance,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except AuthorityError as error:
            print(json.dumps({"leafos_object": "leafos.authority_error.v1", "error": str(error)}))
            return 1
    elif args.command == "check":
        allowed = cap_check_naive(args.capability)
        print(
            json.dumps(
                {
                    "leafos_object": "leafos.authority_check.v1",
                    "capability": args.capability,
                    "allowed": allowed,
                },
                ensure_ascii=False,
            )
        )
    elif args.command == "capabilities":
        registry = _load_capability_registry()
        print(
            json.dumps(
                {
                    "leafos_object": "leafos.capability_registry_summary.v1",
                    "schema": registry.get("schema"),
                    "version": registry.get("version"),
                    "default_policy": registry.get("default_policy", "disallow"),
                    "capabilities": registry.get("capabilities", []),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
