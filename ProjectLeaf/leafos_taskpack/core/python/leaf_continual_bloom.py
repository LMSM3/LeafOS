#!/usr/bin/env python3
"""Durable single-personality continual-bloom runtime for Monday.

This module deliberately does not start a model or grant mutation authority.
It proves the transcript, cursor, claim/evidence, checkpoint, and recovery
contract required before Wednesday or Friday may become durable instances.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INSTANCE = ROOT / "instances" / "monday-primary"
CONTRACT_PATH = ROOT / "config" / "continual-bloom-monday.json"
FULL_NAME = "Monday — Rescue and Analysis"
GENESIS = "GENESIS"
CLAIM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# Windows file locks are process-scoped enough that two Python threads can
# receive EDEADLK instead of waiting for each other.  Serialize contenders in
# this process first; the file lock below remains the cross-process authority.
_INSTANCE_THREAD_LOCKS: dict[str, threading.Lock] = {}
_INSTANCE_THREAD_LOCKS_GUARD = threading.Lock()


class BloomError(RuntimeError):
    """A closed-boundary continual-bloom contract failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: Any) -> Any:
    """Recursively normalize Unicode text so equivalent glyphs hash the same.

    Uses NFKC normalization.  This prevents encoding drift (e.g. em-dash vs
    en-dash, composed vs decomposed characters) from breaking event hashes or
    state identity across platforms.
    """
    if isinstance(value, str):
        return unicodedata.normalize("NFKC", value)
    if isinstance(value, list):
        return [normalize_text(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_text(val) for key, val in value.items()}
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    normalized = normalize_text(value)
    return "sha256:" + hashlib.sha256(canonical_json(normalized).encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            value.update(chunk)
    return "sha256:" + value.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise BloomError(f"required file is missing: {path}") from error
    except json.JSONDecodeError as error:
        raise BloomError(f"invalid JSON in {path}: {error.msg}") from error
    if not isinstance(value, dict):
        raise BloomError(f"JSON object required: {path}")
    return value


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.005)


def write_ndjson(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for item in items:
            handle.write(canonical_json(item) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


@contextlib.contextmanager
def instance_lock(instance: Path) -> Iterator[None]:
    lock_path = instance / ".instance.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_key = os.path.normcase(str(lock_path.resolve()))
    with _INSTANCE_THREAD_LOCKS_GUARD:
        thread_lock = _INSTANCE_THREAD_LOCKS.setdefault(lock_key, threading.Lock())

    with thread_lock:
        with lock_path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = read_json(path)
    if contract.get("schema") != "leafos.continual-bloom-persona.v1":
        raise BloomError("continual bloom contract schema is invalid")
    identity = contract.get("identity")
    if not isinstance(identity, dict) or identity.get("key") != "monday" or identity.get("full_name") != FULL_NAME:
        raise BloomError("the first durable continual bloom instance must be Monday — Rescue and Analysis")
    if contract.get("instance_id") != "monday-primary":
        raise BloomError("the first durable instance id must be monday-primary")
    if contract.get("routing_preferences", {}).get("coder_persona_neutral") is not True:
        raise BloomError("coder workers must remain persona-neutral")
    if contract.get("durability", {}).get("kv_cache_authoritative") is not False:
        raise BloomError("KV cache must be non-authoritative")
    return contract


def persona_from_contract(contract: dict[str, Any]) -> dict[str, Any]:
    contract_material = {
        key: contract[key]
        for key in (
            "schema",
            "version",
            "instance_id",
            "identity",
            "duties",
            "forbidden_actions",
            "routing_preferences",
            "durability",
            "planner_fields",
        )
    }
    return {
        "schema": "leafos.continual-bloom-persona.v1",
        "version": 1,
        "instance_id": "monday-primary",
        "identity": contract["identity"],
        "duties": contract["duties"],
        "forbidden_actions": contract["forbidden_actions"],
        "routing_preferences": contract["routing_preferences"],
        "durability": contract["durability"],
        "planner_fields": contract["planner_fields"],
        "system_contract_hash": digest(contract_material),
    }


def event_without_hash(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if key != "event_hash"}


def make_event(
    events: list[dict[str, Any]],
    kind: str,
    actor: str,
    read_head: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    head = len(events)
    if read_head < 0 or read_head > head:
        raise BloomError(f"read_head must be between 0 and current head {head}")
    event = {
        "schema": "leafos.continual-bloom-event.v1",
        "seq": head + 1,
        "timestamp": utc_now(),
        "kind": kind,
        "actor": actor,
        "read_head": read_head,
        "parent_hash": events[-1]["event_hash"] if events else GENESIS,
        "payload": payload,
    }
    event["event_hash"] = digest(event)
    return event


def append_event_locked(path: Path, event: dict[str, Any]) -> None:
    """Append an event to the NDJSON log atomically.

    The existing log is read, the new event is appended, and the result is
    written to a temporary file that replaces the original via os.replace().
    This prevents partial/corrupted events if the process is interrupted.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    if path.exists():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line:
                    items.append(json.loads(line))
        except (OSError, json.JSONDecodeError) as error:
            raise BloomError(f"cannot read event log {path}: {error}") from error
    items.append(event)
    write_ndjson(path, items)


def read_events(instance: Path) -> list[dict[str, Any]]:
    path = instance / "events.ndjson"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise BloomError(f"event log is missing: {path}") from error
    events: list[dict[str, Any]] = []
    previous = GENESIS
    for line_number, line in enumerate(lines, start=1):
        if not line:
            raise BloomError(f"blank event at line {line_number}")
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise BloomError(f"invalid event JSON at line {line_number}: {error.msg}") from error
        if not isinstance(event, dict):
            raise BloomError(f"event line {line_number} is not an object")
        if event.get("schema") != "leafos.continual-bloom-event.v1":
            raise BloomError(f"event schema mismatch at line {line_number}")
        if event.get("seq") != line_number:
            raise BloomError(f"event sequence mismatch at line {line_number}")
        if event.get("parent_hash") != previous:
            raise BloomError(f"event parent hash mismatch at line {line_number}")
        if not isinstance(event.get("read_head"), int) or not 0 <= event["read_head"] <= line_number - 1:
            raise BloomError(f"event read_head is invalid at line {line_number}")
        expected = digest(event_without_hash(event))
        if event.get("event_hash") != expected:
            raise BloomError(f"event hash mismatch at line {line_number}")
        if not isinstance(event.get("payload"), dict) or not isinstance(event.get("actor"), str):
            raise BloomError(f"event payload or actor is invalid at line {line_number}")
        events.append(event)
        previous = event["event_hash"]
    return events


def initial_state(persona: dict[str, Any]) -> dict[str, Any]:
    return {
        "leafos_object": "leafos.continual_bloom_state",
        "version": 1,
        "instance_id": "monday-primary",
        "persona_key": "monday",
        "persona_full_name": FULL_NAME,
        "system_contract_hash": persona["system_contract_hash"],
        "status": "starting",
        "transcript_head": 0,
        "transcript_cursor": 0,
        "last_event_hash": GENESIS,
        "stale_rejections": 0,
        "pending_claims": [],
        "last_validation": None,
        "last_checkpoint": None,
        "lease": {"owner": None, "expires_at": None},
        "blocked_reason": None,
        "next_action": {"capability": "instance.initialize", "reason": "create the durable instance"},
    }


def apply_event(state: dict[str, Any], event: dict[str, Any]) -> None:
    kind = event["kind"]
    payload = event["payload"]
    state["transcript_head"] = event["seq"]
    state["last_event_hash"] = event["event_hash"]
    if kind == "instance.initialized":
        state["status"] = "idle"
        state["transcript_cursor"] = event["seq"]
        state["next_action"] = {"capability": "input.append", "reason": "await an operator or tool event"}
    elif kind == "input.received":
        state["status"] = "active"
        state["next_action"] = {
            "capability": "persona.claim",
            "reason": f"Monday must analyze transcript head {event['seq']}",
        }
    elif kind == "claim.recorded":
        claim_id = str(payload["claim_id"])
        if claim_id not in state["pending_claims"]:
            state["pending_claims"].append(claim_id)
        state["transcript_cursor"] = event["read_head"]
        state["status"] = "waiting"
        state["next_action"] = {
            "capability": "claim.validate",
            "reason": f"claim {claim_id} remains unverified",
        }
    elif kind == "proposal.rejected_stale":
        state["stale_rejections"] += 1
        state["status"] = "active"
        state["next_action"] = {
            "capability": "persona.rebase",
            "reason": f"advance Monday to transcript head {event['seq']}",
        }
    elif kind == "claim.validated":
        claim_id = str(payload["claim_id"])
        state["pending_claims"] = [item for item in state["pending_claims"] if item != claim_id]
        state["last_validation"] = {
            "event_seq": event["seq"],
            "event_hash": event["event_hash"],
            "claim_id": claim_id,
            "status": payload["status"],
            "evidence_refs": payload["evidence_refs"],
        }
        state["status"] = "waiting"
        state["next_action"] = {
            "capability": "checkpoint.commit",
            "reason": f"native validation completed for {claim_id}",
        }
    elif kind == "checkpoint.committed":
        state["last_checkpoint"] = {
            "event_seq": event["seq"],
            "event_hash": event["event_hash"],
            "validation_event_seq": payload["validation_event_seq"],
            "path": payload["path"],
        }
        state["transcript_cursor"] = event["seq"]
        state["status"] = "idle"
        state["next_action"] = payload["next_action"]
    elif kind == "runtime.recovered":
        state["status"] = payload["status"]
        state["transcript_cursor"] = int(payload["transcript_cursor"])
        state["next_action"] = payload["next_action"]


def replay_state(events: list[dict[str, Any]], persona: dict[str, Any]) -> dict[str, Any]:
    state = initial_state(persona)
    for event in events:
        apply_event(state, event)
    return state


def claims_by_id(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    claims: dict[str, dict[str, Any]] = {}
    for event in events:
        if event["kind"] == "claim.recorded":
            claims[str(event["payload"]["claim_id"])] = event
    return claims


def expected_facts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    claims = claims_by_id(events)
    facts: list[dict[str, Any]] = []
    promoted: set[str] = set()
    for event in events:
        if event["kind"] != "claim.validated" or event["payload"].get("status") != "supported":
            continue
        claim_id = str(event["payload"]["claim_id"])
        claim = claims.get(claim_id)
        if claim is None:
            raise BloomError(f"validation references unknown claim: {claim_id}")
        if claim_id in promoted:
            raise BloomError(f"claim was promoted more than once: {claim_id}")
        facts.append({
            "schema": "leafos.continual-bloom-fact.v1",
            "claim_id": claim_id,
            "text": claim["payload"]["text"],
            "origin_event": claim["seq"],
            "validation_event": event["seq"],
            "validated_at": event["timestamp"],
            "evidence_refs": event["payload"]["evidence_refs"],
            "validation_hash": event["event_hash"],
        })
        promoted.add(claim_id)
    return facts


def claim_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    claims = claims_by_id(events)
    outcomes = {
        str(event["payload"]["claim_id"]): str(event["payload"]["status"])
        for event in events
        if event["kind"] == "claim.validated"
    }
    total = len(claims)
    supported = sum(status == "supported" for status in outcomes.values())
    refuted = sum(status == "refuted" for status in outcomes.values())
    return {
        "total_claims": total,
        "supported_claims": supported,
        "refuted_claims": refuted,
        "unverified_claims": total - len(outcomes),
        "evidence_coverage": None if total == 0 else round(supported / total, 4),
        "evidence_coverage_percent": None if total == 0 else round(100 * supported / total, 2),
    }


def read_facts(instance: Path) -> list[dict[str, Any]]:
    path = instance / "facts.ndjson"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise BloomError(f"fact log is missing: {path}") from error
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise BloomError(f"invalid fact JSON at line {line_number}: {error.msg}") from error
        if not isinstance(value, dict):
            raise BloomError(f"fact line {line_number} is not an object")
        values.append(value)
    return values


def checkpoint_value(
    instance: Path,
    event: dict[str, Any],
    state: dict[str, Any],
    facts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": "leafos.continual-bloom-checkpoint.v1",
        "instance_id": "monday-primary",
        "persona_full_name": FULL_NAME,
        "committed_at": event["timestamp"],
        "event_head": {"seq": event["seq"], "hash": event["event_hash"]},
        "validation_event": {
            "seq": event["payload"]["validation_event_seq"],
            "hash": event["payload"]["validation_event_hash"],
        },
        "facts_sha256": digest(facts),
        "system_contract_hash": state["system_contract_hash"],
        "next_action": event["payload"]["next_action"],
        "kv_cache_authoritative": False,
        "relative_path": str(Path(event["payload"]["path"]).as_posix()),
    }


def commit_event(
    instance: Path,
    events: list[dict[str, Any]],
    persona: dict[str, Any],
    kind: str,
    actor: str,
    read_head: int,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    event = make_event(events, kind, actor, read_head, payload)
    append_event_locked(instance / "events.ndjson", event)
    events.append(event)
    state = replay_state(events, persona)
    atomic_write_json(instance / "state.json", state)
    return event, state


def initialize(instance: Path) -> dict[str, Any]:
    contract = load_contract()
    persona = persona_from_contract(contract)
    if (instance / "events.ndjson").exists() or (instance / "state.json").exists():
        raise BloomError(f"instance already exists: {instance}")
    instance.mkdir(parents=True, exist_ok=True)
    (instance / "evidence").mkdir(exist_ok=True)
    (instance / "checkpoints").mkdir(exist_ok=True)
    atomic_write_json(instance / "persona.json", persona)
    write_ndjson(instance / "events.ndjson", [])
    write_ndjson(instance / "facts.ndjson", [])
    with instance_lock(instance):
        event, state = commit_event(
            instance,
            [],
            persona,
            "instance.initialized",
            "native-supervisor",
            0,
            {
                "instance_id": "monday-primary",
                "persona_full_name": FULL_NAME,
                "system_contract_hash": persona["system_contract_hash"],
                "kv_cache_authoritative": False,
            },
        )
    return {"event": event, "state": state, "instance": str(instance)}


def append_input(instance: Path, text: str, actor: str = "operator") -> dict[str, Any]:
    if not text.strip():
        raise BloomError("input text must not be empty")
    with instance_lock(instance):
        persona = read_json(instance / "persona.json")
        events = read_events(instance)
        event, state = commit_event(
            instance,
            events,
            persona,
            "input.received",
            actor,
            len(events),
            {"text": text},
        )
    return {"event": event, "state": state}


def record_claim(instance: Path, claim_id: str, text: str, read_head: int) -> dict[str, Any]:
    if not CLAIM_ID.fullmatch(claim_id):
        raise BloomError("claim id must use 1-128 letters, digits, dot, underscore, or hyphen")
    if not text.strip():
        raise BloomError("claim text must not be empty")
    with instance_lock(instance):
        persona = read_json(instance / "persona.json")
        events = read_events(instance)
        if claim_id in claims_by_id(events):
            raise BloomError(f"claim id already exists: {claim_id}")
        current_head = len(events)
        if read_head != current_head:
            event, state = commit_event(
                instance,
                events,
                persona,
                "proposal.rejected_stale",
                FULL_NAME,
                read_head,
                {
                    "proposal_kind": "claim",
                    "claim_id": claim_id,
                    "generated_from_head": read_head,
                    "current_head": current_head,
                    "disposition": "stale",
                },
            )
            return {"accepted": False, "event": event, "state": state}
        event, state = commit_event(
            instance,
            events,
            persona,
            "claim.recorded",
            FULL_NAME,
            read_head,
            {
                "claim_id": claim_id,
                "text": text,
                "status": "unverified",
                "evidence_refs": [],
            },
        )
    return {"accepted": True, "event": event, "state": state}


def validate_claim(
    instance: Path,
    claim_id: str,
    status: str,
    evidence_path: Path,
) -> dict[str, Any]:
    if status not in {"supported", "refuted"}:
        raise BloomError("validation status must be supported or refuted")
    if not evidence_path.is_file():
        raise BloomError(f"evidence file is missing: {evidence_path}")
    resolved_evidence = evidence_path.resolve()
    evidence = {
        "type": "native_file",
        "path": str(resolved_evidence),
        "sha256": file_digest(resolved_evidence),
        "bytes": resolved_evidence.stat().st_size,
    }
    with instance_lock(instance):
        persona = read_json(instance / "persona.json")
        events = read_events(instance)
        claim = claims_by_id(events).get(claim_id)
        if claim is None:
            raise BloomError(f"unknown claim: {claim_id}")
        if any(
            event["kind"] == "claim.validated" and event["payload"].get("claim_id") == claim_id
            for event in events
        ):
            raise BloomError(f"claim already validated: {claim_id}")
        evidence_record = {
            "schema": "leafos.continual-bloom-evidence.v1",
            "claim_id": claim_id,
            "captured_at": utc_now(),
            **evidence,
        }
        evidence_relative = Path("evidence") / f"{claim_id}.json"
        atomic_write_json(instance / evidence_relative, evidence_record)
        evidence_ref = {**evidence, "record": evidence_relative.as_posix()}
        event, state = commit_event(
            instance,
            events,
            persona,
            "claim.validated",
            "native-validator",
            len(events),
            {
                "claim_id": claim_id,
                "status": status,
                "evidence_refs": [evidence_ref],
                "origin_event": claim["seq"],
            },
        )
        facts = expected_facts(events)
        write_ndjson(instance / "facts.ndjson", facts)
    return {"event": event, "state": state, "evidence": evidence_ref}


def commit_checkpoint(
    instance: Path,
    next_capability: str = "input.append",
    reason: str = "await the next operator or tool event",
) -> dict[str, Any]:
    if not next_capability.strip() or not reason.strip():
        raise BloomError("checkpoint next action requires a capability and reason")
    with instance_lock(instance):
        persona = read_json(instance / "persona.json")
        events = read_events(instance)
        state_before = replay_state(events, persona)
        validation = state_before.get("last_validation")
        if not isinstance(validation, dict):
            raise BloomError("checkpoint requires a successful native validation")
        prior = state_before.get("last_checkpoint")
        if isinstance(prior, dict) and int(prior["validation_event_seq"]) >= int(validation["event_seq"]):
            raise BloomError("checkpoint requires new native validation evidence")
        relative = Path("checkpoints") / f"checkpoint-{len(events) + 1:06d}.json"
        event, state = commit_event(
            instance,
            events,
            persona,
            "checkpoint.committed",
            "native-supervisor",
            len(events),
            {
                "validation_event_seq": validation["event_seq"],
                "validation_event_hash": validation["event_hash"],
                "path": relative.as_posix(),
                "next_action": {"capability": next_capability, "reason": reason},
            },
        )
        facts = expected_facts(events)
        checkpoint = checkpoint_value(instance, event, state, facts)
        atomic_write_json(instance / relative, checkpoint)
        atomic_write_json(instance / "state.json", state)
    return {"event": event, "state": state, "checkpoint": checkpoint}


def verify(instance: Path) -> dict[str, Any]:
    with instance_lock(instance):
        persona = read_json(instance / "persona.json")
        if persona.get("identity", {}).get("full_name") != FULL_NAME:
            raise BloomError("durable instance identity is not Monday — Rescue and Analysis")
        contract = load_contract()
        expected_persona = persona_from_contract(contract)
        if persona.get("system_contract_hash") != expected_persona["system_contract_hash"]:
            raise BloomError("persona system contract hash does not match the canonical contract")
        events = read_events(instance)
        if not events or events[0]["kind"] != "instance.initialized":
            raise BloomError("instance initialization event is missing")
        expected_state = replay_state(events, persona)
        stored_state = read_json(instance / "state.json")
        if stored_state != expected_state:
            raise BloomError("state.json does not match replayed transcript state")
        facts = expected_facts(events)
        if read_facts(instance) != facts:
            raise BloomError("facts.ndjson does not match native validation events")
        checkpoints = 0
        for event in events:
            if event["kind"] != "checkpoint.committed":
                continue
            path = instance / event["payload"]["path"]
            stored = read_json(path)
            replayed_at_event = replay_state(events[: event["seq"]], persona)
            expected = checkpoint_value(instance, event, replayed_at_event, expected_facts(events[: event["seq"]]))
            if stored != expected:
                raise BloomError(f"checkpoint does not match transcript event: {path}")
            checkpoints += 1
        if not isinstance(expected_state.get("next_action"), dict) or set(expected_state["next_action"]) != {
            "capability",
            "reason",
        }:
            raise BloomError("state must preserve exactly one typed next action")
    metrics = claim_metrics(events)
    return {
        "leafos_object": "leafos.continual_bloom_verification",
        "version": 1,
        "status": "ok",
        "instance": str(instance),
        "persona": FULL_NAME,
        "event_count": len(events),
        "fact_count": len(facts),
        "checkpoint_count": checkpoints,
        "transcript_head": expected_state["transcript_head"],
        "transcript_cursor": expected_state["transcript_cursor"],
        "stale_rejections": expected_state["stale_rejections"],
        "claim_metrics": metrics,
        "next_action": expected_state["next_action"],
        "kv_cache_authoritative": False,
    }


def recover(instance: Path) -> dict[str, Any]:
    with instance_lock(instance):
        persona = read_json(instance / "persona.json")
        events = read_events(instance)
        state = replay_state(events, persona)
        facts = expected_facts(events)
        write_ndjson(instance / "facts.ndjson", facts)
        for event in events:
            if event["kind"] != "checkpoint.committed":
                continue
            checkpoint_state = replay_state(events[: event["seq"]], persona)
            checkpoint = checkpoint_value(
                instance,
                event,
                checkpoint_state,
                expected_facts(events[: event["seq"]]),
            )
            atomic_write_json(instance / event["payload"]["path"], checkpoint)
        recovery_payload = {
            "recovered_from_head": state["transcript_head"],
            "status": state["status"],
            "transcript_cursor": state["transcript_cursor"],
            "next_action": state["next_action"],
            "kv_cache_used": False,
        }
        event, state = commit_event(
            instance,
            events,
            persona,
            "runtime.recovered",
            "native-supervisor",
            len(events),
            recovery_payload,
        )
    report = verify(instance)
    return {"event": event, "state": state, "verification": report}


def status(instance: Path) -> dict[str, Any]:
    if not (instance / "persona.json").is_file():
        return {
            "leafos_object": "leafos.continual_bloom_status",
            "version": 1,
            "status": "not_initialized",
            "instance": str(instance),
            "persona": FULL_NAME,
            "event_count": 0,
            "fact_count": 0,
            "checkpoint_count": 0,
            "transcript_head": 0,
            "transcript_cursor": 0,
            "stale_rejections": 0,
            "claim_metrics": {
                "total_claims": 0,
                "supported_claims": 0,
                "refuted_claims": 0,
                "unverified_claims": 0,
                "evidence_coverage": None,
                "evidence_coverage_percent": None,
            },
            "next_action": {
                "capability": "instance.initialize",
                "reason": "run `leafos bloom init` to create the durable Monday instance",
            },
            "kv_cache_authoritative": False,
        }
    report = verify(instance)
    report["state"] = read_json(instance / "state.json")
    return report


def print_value(value: Any, as_json: bool = True) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        state = value.get("state", value) if isinstance(value, dict) else value
        print(f"Monday continual bloom: {state.get('status', value.get('status', 'unknown'))}")
        print(f"Instance    {value.get('instance', '')}")
        print(f"Head        {state.get('transcript_head', value.get('transcript_head', 0))}")
        print(f"Cursor      {state.get('transcript_cursor', value.get('transcript_cursor', 0))}")
        metrics = value.get("claim_metrics", {}) if isinstance(value, dict) else {}
        coverage = metrics.get("evidence_coverage_percent")
        coverage_text = "n/a" if coverage is None else f"{coverage:.2f}%"
        print(
            "Evidence    "
            f"{coverage_text} "
            f"({metrics.get('supported_claims', 0)}/{metrics.get('total_claims', 0)} supported)"
        )
        print(f"Stale       {state.get('stale_rejections', value.get('stale_rejections', 0))}")
        action = state.get("next_action", value.get("next_action", {}))
        print(f"Next        {action.get('capability', 'unknown')} — {action.get('reason', '')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="leafos bloom")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        item = subparsers.add_parser(name, help=help_text)
        item.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
        return item

    initialize_parser = command("init", "create the durable Monday instance")
    initialize_parser.add_argument("--json", action="store_true")

    status_parser = command("status", "verify and show current state")
    status_parser.add_argument("--json", action="store_true")

    input_parser = command("input", "append an operator or tool input")
    input_parser.add_argument("--text", required=True)
    input_parser.add_argument("--actor", default="operator")

    claim_parser = command("claim", "record an unverified Monday claim")
    claim_parser.add_argument("--id", required=True)
    claim_parser.add_argument("--text", required=True)
    claim_parser.add_argument("--read-head", required=True, type=int)

    validation_parser = command("validate", "validate or refute a claim with native evidence")
    validation_parser.add_argument("--claim-id", required=True)
    validation_parser.add_argument("--status", required=True, choices=("supported", "refuted"))
    validation_parser.add_argument("--evidence", required=True, type=Path)

    checkpoint_parser = command("checkpoint", "commit state after new native validation")
    checkpoint_parser.add_argument("--next-action", default="input.append")
    checkpoint_parser.add_argument("--reason", default="await the next operator or tool event")

    verify_parser = command("verify", "verify transcript, state, facts, and checkpoints")
    verify_parser.add_argument("--json", action="store_true")

    recover_parser = command("recover", "rebuild derived state without using KV cache")
    recover_parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "init":
            value = initialize(args.instance)
        elif args.command == "status":
            value = status(args.instance)
        elif args.command == "input":
            value = append_input(args.instance, args.text, args.actor)
        elif args.command == "claim":
            value = record_claim(args.instance, args.id, args.text, args.read_head)
            print_value(value)
            return 0 if value["accepted"] else 3
        elif args.command == "validate":
            value = validate_claim(args.instance, args.claim_id, args.status, args.evidence)
        elif args.command == "checkpoint":
            value = commit_checkpoint(args.instance, args.next_action, args.reason)
        elif args.command == "verify":
            value = verify(args.instance)
        elif args.command == "recover":
            value = recover(args.instance)
        else:
            parser.error(f"unknown command: {args.command}")
            return 2
        print_value(value, getattr(args, "json", True))
        return 0
    except (BloomError, OSError, ValueError) as error:
        print(f"leafos bloom: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
