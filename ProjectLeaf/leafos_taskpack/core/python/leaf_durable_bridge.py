#!/usr/bin/env python3
"""Integration bridge for the durable Monday continual-bloom runtime.

This module exposes a stable, typed API over `leaf_continual_bloom` so that
CLI dispatchers, web projections, and future TUI surfaces can treat Monday's
durable transcript as the authoritative system state without duplicating its
hash-chain, claim/evidence, or checkpoint logic.

For 0.9.4, every interactive action is represented as a typed capability
request.  The bridge records the request in the transcript (if allowed) and
returns a disposition envelope.  Denied requests are still logged as audit
events so the system can prove what was rejected and why.

Wednesday and Friday remain configuration-level personas for now.  Any
attempted mutation of non-Monday data is rejected at this boundary.
"""

from __future__ import annotations

import json
import secrets
import sys
from pathlib import Path
from typing import Any, Dict

_TASKPACK = Path(__file__).resolve().parents[2]
_CORE_PYTHON = _TASKPACK / "core" / "python"
if str(_CORE_PYTHON) not in sys.path:
    sys.path.insert(0, str(_CORE_PYTHON))

import leaf_continual_bloom as _bloom  # noqa: E402


FULL_NAME = _bloom.FULL_NAME
DEFAULT_INSTANCE = _bloom.DEFAULT_INSTANCE
CAPABILITY_REGISTRY_PATH = _TASKPACK / "config" / "capability-registry.json"


def _load_capability_registry() -> Dict[str, Any]:
    try:
        data = json.loads(CAPABILITY_REGISTRY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema": "leafos.capability_registry.v1", "capabilities": []}
    except json.JSONDecodeError as error:
        raise DurableBridgeError(f"invalid capability registry: {error}") from error
    return data


def _rule_for(registry: Dict[str, Any], key: str) -> Dict[str, Any]:
    """Return the capability rule for key or a synthetic disallow rule.

    This helper enforces the registry's declared rule order (deny, allow,
    audit).  When multiple entries share the same key the first matching
    policy wins; otherwise the default policy is applied.
    """
    order = registry.get("rule_order", ["deny", "allow", "audit"])
    capabilities = registry.get("capabilities", [])
    rules = [item for item in capabilities if item.get("key") == key]
    if not rules:
        return {
            "key": key,
            "policy": registry.get("default_policy", "disallow"),
            "synthetic": True,
        }
    for policy in order:
        for rule in rules:
            if rule.get("policy") == policy:
                return rule
    return rules[0]


def _find_rule(registry: Dict[str, Any], key: str) -> Dict[str, Any] | None:
    for item in registry.get("capabilities", []):
        if item.get("key") == key:
            return item
    return None


def _ticket_digest(ticket: Dict[str, Any]) -> str:
    payload = json.dumps(ticket, sort_keys=True, ensure_ascii=False)
    import hashlib

    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _make_ticket(
    capability: str,
    actor: str,
    source: str,
    request_id: str,
    policy: str,
    allowed: bool,
    reason: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    ticket = {
        "leafos_object": "leafos.capability_ticket.v1",
        "capability": capability,
        "actor": actor,
        "source": source,
        "request_id": request_id,
        "policy": policy,
        "allowed": allowed,
        "reason": reason,
        "context": context,
        "timestamp": _bloom.utc_now(),
        "lease": {"scope": "single_command", "revokable": True},
    }
    ticket["ticket_digest"] = _ticket_digest(ticket)
    return ticket


class DurableBridgeError(RuntimeError):
    """A durable-bridge contract or runtime failure."""


class MondayDurableBridge:
    """Read-mostly authority surface for the Monday durable instance.

    The bridge does not grant mutation authority beyond the verbs the
    underlying runtime already exposes.  It adds cross-cutting integration
    metadata (request_id, source surface) to every returned envelope and
    converts runtime exceptions into typed error payloads.
    """

    def __init__(self, instance: Path | None = None, *, source: str = "bridge") -> None:
        self.instance = instance or DEFAULT_INSTANCE
        self.source = source

    def _envelope(self, operation: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "leafos_object": "leafos.durable_bridge_response.v1",
            "source": self.source,
            "operation": operation,
            "instance": str(self.instance),
            "persona": FULL_NAME,
            "payload": payload,
        }

    def status(self) -> Dict[str, Any]:
        try:
            return self._envelope("status", _bloom.status(self.instance))
        except _bloom.BloomError as error:
            raise DurableBridgeError(str(error)) from error

    def initialize(self) -> Dict[str, Any]:
        try:
            return self._envelope("initialize", _bloom.initialize(self.instance))
        except _bloom.BloomError as error:
            raise DurableBridgeError(str(error)) from error

    def append_input(self, text: str) -> Dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise DurableBridgeError("input text must be a non-empty string")
        try:
            return self._envelope("append_input", _bloom.append_input(self.instance, text))
        except _bloom.BloomError as error:
            raise DurableBridgeError(str(error)) from error

    def record_claim(self, claim_id: str, text: str, read_head: int) -> Dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise DurableBridgeError("claim text must be a non-empty string")
        try:
            return self._envelope(
                "record_claim",
                _bloom.record_claim(self.instance, claim_id, text, read_head),
            )
        except _bloom.BloomError as error:
            raise DurableBridgeError(str(error)) from error

    def validate_claim(
        self,
        claim_id: str,
        status: str,
        evidence_path: Path | str,
    ) -> Dict[str, Any]:
        resolved = Path(evidence_path)
        try:
            return self._envelope(
                "validate_claim",
                _bloom.validate_claim(self.instance, claim_id, status, resolved),
            )
        except _bloom.BloomError as error:
            raise DurableBridgeError(str(error)) from error

    def commit_checkpoint(
        self,
        next_capability: str = "input.append",
        reason: str = "await the next operator or tool event",
    ) -> Dict[str, Any]:
        try:
            return self._envelope(
                "commit_checkpoint",
                _bloom.commit_checkpoint(self.instance, next_capability, reason),
            )
        except _bloom.BloomError as error:
            raise DurableBridgeError(str(error)) from error

    def recover(self) -> Dict[str, Any]:
        try:
            return self._envelope("recover", _bloom.recover(self.instance))
        except _bloom.BloomError as error:
            raise DurableBridgeError(str(error)) from error

    def verify(self) -> Dict[str, Any]:
        try:
            return self._envelope("verify", _bloom.verify(self.instance))
        except _bloom.BloomError as error:
            raise DurableBridgeError(str(error)) from error

    def _record_capability_event(
        self,
        event_kind: str,
        capability: str,
        actor: str,
        request_id: str,
        policy: str,
        allowed: bool,
        reason: str,
        context: Dict[str, Any],
    ) -> None:
        """Append the capability request/denial to the transcript.

        Both the input marker and the capability event are committed atomically
        under a single instance lock so events.ndjson and state.json can never
        diverge.
        """
        try:
            with _bloom.instance_lock(self.instance):
                persona = _bloom.read_json(self.instance / "persona.json")
                events = _bloom.read_events(self.instance)
                input_event, _ = _bloom.commit_event(
                    self.instance,
                    events,
                    persona,
                    "input.received",
                    actor,
                    len(events),
                    {"text": f"[{event_kind}] {capability} by {actor}: {reason}".strip()},
                )
                _bloom.commit_event(
                    self.instance,
                    events,
                    persona,
                    event_kind,
                    actor,
                    input_event["seq"],
                    {
                        "capability": capability,
                        "actor": actor,
                        "source": self.source,
                        "request_id": request_id,
                        "policy": policy,
                        "allowed": allowed,
                        "reason": reason,
                        "context": context,
                    },
                )
        except _bloom.BloomError as error:
            raise DurableBridgeError(str(error)) from error

    def request_capability(
        self,
        capability: str,
        *,
        actor: str,
        reason: str = "",
        context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Evaluate and record a typed capability request.

        Allowed requests are appended to the transcript as
        ``capability.requested`` events.  Denied requests are appended as
        ``capability.denied`` events.  The return value always contains the
        disposition so callers cannot silently ignore a denial.
        """
        if not capability or not actor:
            raise DurableBridgeError("capability and actor are required")
        registry = _load_capability_registry()
        rule = _rule_for(registry, capability)
        policy = rule.get("policy", registry.get("default_policy", "disallow"))
        allowed = policy == "allow"
        request_id = secrets.token_hex(8)
        context = context or {}

        event_kind = "capability.requested" if allowed else "capability.denied"
        self._record_capability_event(
            event_kind, capability, actor, request_id, policy, allowed, reason, context
        )

        ticket = _make_ticket(
            capability, actor, self.source, request_id, policy, allowed, reason, context
        )

        return self._envelope(
            "request_capability",
            {
                "capability": capability,
                "actor": actor,
                "request_id": request_id,
                "allowed": allowed,
                "policy": policy,
                "reason": reason,
                "requires_evidence": rule.get("requires_evidence") if rule else None,
                "recorded_event_kind": event_kind,
                "ticket": ticket,
            },
        )

    def require_capability(
        self,
        capability: str,
        *,
        actor: str,
        reason: str = "",
        context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Request a capability and raise if it is not allowed.

        Use this for enforcement surfaces such as the CLI or loop kernel that
        must fail fast when a mutation-capability is denied.
        """
        response = self.request_capability(capability, actor=actor, reason=reason, context=context)
        payload = response.get("payload", response)
        if not payload.get("allowed"):
            raise DurableBridgeError(
                f"capability denied: {capability} for {actor} ({payload.get('policy')})"
            )
        return response

    def list_capabilities(self, actor: str = "") -> Dict[str, Any]:
        """Return the registry view for the given actor."""
        registry = _load_capability_registry()
        caps = registry.get("capabilities", [])
        if actor:
            caps = [
                c for c in caps
                if actor in c.get("actor", []) or not c.get("actor")
            ]
        return self._envelope(
            "list_capabilities",
            {
                "schema": registry.get("schema"),
                "version": registry.get("version"),
                "default_policy": registry.get("default_policy", "disallow"),
                "rule_order": registry.get("rule_order", []),
                "capabilities": caps,
            },
        )


def bridge_for(
    persona_key: str = "monday",
    *,
    instance: Path | None = None,
    source: str = "bridge",
) -> MondayDurableBridge:
    """Return a durable bridge for the requested persona key.

    Currently only ``monday`` is supported.  Wednesday and Friday are still
    config-only personas.
    """
    if persona_key != "monday":
        raise DurableBridgeError(
            f"durable instances are not yet available for persona: {persona_key}"
        )
    return MondayDurableBridge(instance=instance, source=source)


def build_parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(prog="leaf-durable-bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def command(name: str, help_text: str) -> Any:
        item = subparsers.add_parser(name, help=help_text)
        item.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
        item.add_argument("--source", default="bridge")
        item.add_argument("--json", action="store_true")
        return item

    command("init", "create the durable Monday instance")
    command("status", "show durable Monday status")

    input_parser = command("input", "append operator input")
    input_parser.add_argument("text")

    claim_parser = command("claim", "record a claim")
    claim_parser.add_argument("claim_id")
    claim_parser.add_argument("text")
    claim_parser.add_argument("--read-head", type=int, required=True)

    validate_parser = command("validate", "validate a claim with native evidence")
    validate_parser.add_argument("claim_id")
    validate_parser.add_argument("status", choices=["supported", "refuted"])
    validate_parser.add_argument("evidence", type=Path)

    checkpoint_parser = command("checkpoint", "commit a checkpoint")
    checkpoint_parser.add_argument("--next-capability", default="input.append")
    checkpoint_parser.add_argument("--reason", default="await the next operator or tool event")

    command("recover", "recover and verify the durable instance")
    command("verify", "verify durable instance integrity")

    cap_parser = command("capability", "request a capability and record the disposition")
    cap_parser.add_argument("capability")
    cap_parser.add_argument("--actor", required=True)
    cap_parser.add_argument("--reason", default="")
    cap_parser.add_argument(
        "--context",
        default="{}",
        help="JSON object describing the request context",
    )

    command("capabilities", "list capability registry entries")
    return parser


def main(argv: list[str] | None = None) -> int:
    import json as _json

    parser = build_parser()
    args = parser.parse_args(argv)
    bridge = MondayDurableBridge(instance=args.instance, source=args.source)

    try:
        if args.command == "init":
            result = bridge.initialize()
        elif args.command == "status":
            result = bridge.status()
        elif args.command == "input":
            result = bridge.append_input(args.text)
        elif args.command == "claim":
            result = bridge.record_claim(args.claim_id, args.text, args.read_head)
        elif args.command == "validate":
            result = bridge.validate_claim(args.claim_id, args.status, args.evidence)
        elif args.command == "checkpoint":
            result = bridge.commit_checkpoint(args.next_capability, args.reason)
        elif args.command == "recover":
            result = bridge.recover()
        elif args.command == "verify":
            result = bridge.verify()
        elif args.command == "capability":
            context = _json.loads(args.context)
            result = bridge.request_capability(
                args.capability, actor=args.actor, reason=args.reason, context=context
            )
        elif args.command == "capabilities":
            result = bridge.list_capabilities(actor=args.actor)
        else:
            raise DurableBridgeError(f"unknown command: {args.command}")
    except DurableBridgeError as error:
        print(
            _json.dumps(
                {
                    "leafos_object": "leafos.durable_bridge_response.v1",
                    "source": getattr(args, "source", "bridge"),
                    "operation": getattr(args, "command", "unknown"),
                    "instance": str(getattr(args, "instance", DEFAULT_INSTANCE)),
                    "error": str(error),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1

    if args.json:
        print(
            _json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    else:
        inner = result.get("payload", result)
        _bloom.print_value(inner, as_json=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
