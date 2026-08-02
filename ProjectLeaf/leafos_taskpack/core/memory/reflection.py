#!/usr/bin/env python3
"""Validation and LMEM wrapping for bounded reasoning reflections."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from journal import append_native, canonical_digest, head, replay


REQUIRED_FIELDS = {
    "schema", "run_id", "task_id", "created_at", "producer", "decision_summary",
    "assumptions", "alternatives", "evidence_refs", "constraint_refs", "uncertainties",
    "unresolved_questions", "proposed_next_action", "token_accounting",
}
OPTIONAL_FIELDS = {"auxiliary_blob", "phase_timeline"}
LIST_FIELDS = {
    "assumptions", "alternatives", "evidence_refs", "constraint_refs",
    "uncertainties", "unresolved_questions",
}


class ReflectionError(ValueError):
    pass


def _date_time(value: Any, field: str) -> None:
    if not isinstance(value, str):
        raise ReflectionError(f"{field} must be an ISO-8601 string")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReflectionError(f"{field} must be an ISO-8601 date-time") from exc


def validate_artifact(artifact: Any) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        raise ReflectionError("reflection payload must be a JSON object")
    unknown = set(artifact) - REQUIRED_FIELDS - OPTIONAL_FIELDS
    missing = REQUIRED_FIELDS - set(artifact)
    if missing:
        raise ReflectionError("missing fields: " + ", ".join(sorted(missing)))
    if unknown:
        if "authority" in unknown or "epistemic_class" in unknown:
            raise ReflectionError("producer reflections cannot request evidence or committed_fact authority")
        raise ReflectionError("unknown fields: " + ", ".join(sorted(unknown)))
    if artifact["schema"] != "leafos.reasoning-artifact.v1":
        raise ReflectionError("unsupported reasoning artifact schema")
    for field in ("run_id", "task_id", "decision_summary"):
        if not isinstance(artifact[field], str) or not artifact[field].strip():
            raise ReflectionError(f"{field} must be a non-empty string")
    _date_time(artifact["created_at"], "created_at")
    for field in LIST_FIELDS:
        if not isinstance(artifact[field], list) or not all(isinstance(item, str) for item in artifact[field]):
            raise ReflectionError(f"{field} must be an array of strings")
    if artifact["proposed_next_action"] is not None and not isinstance(artifact["proposed_next_action"], str):
        raise ReflectionError("proposed_next_action must be a string or null")
    producer = artifact["producer"]
    if not isinstance(producer, dict) or set(producer) != {"provider", "model", "mode"}:
        raise ReflectionError("producer must contain provider, model, and mode")
    if producer["mode"] not in {"requested_summary", "provider_reasoning_summary"}:
        raise ReflectionError("invalid producer mode")
    if not all(isinstance(producer[key], str) and producer[key] for key in ("provider", "model")):
        raise ReflectionError("producer provider and model must be non-empty strings")
    accounting = artifact["token_accounting"]
    required_accounting = {
        "context_limit", "input_tokens", "memory_tokens", "reasoning_budget_requested", "output_tokens"
    }
    if not isinstance(accounting, dict) or set(accounting) != required_accounting:
        raise ReflectionError("token_accounting fields do not match the v1 contract")
    for field in required_accounting - {"reasoning_budget_requested"}:
        minimum = 1 if field == "context_limit" else 0
        if not isinstance(accounting[field], int) or accounting[field] < minimum:
            raise ReflectionError(f"token_accounting.{field} must be an integer >= {minimum}")
    budget = accounting["reasoning_budget_requested"]
    if not ((isinstance(budget, int) and budget >= 0) or budget == "auto"):
        raise ReflectionError("reasoning_budget_requested must be a non-negative integer or 'auto'")
    timeline = artifact.get("phase_timeline")
    if timeline is not None and (
        not isinstance(timeline, dict) or timeline.get("schema") != "leafos.thinking-loop.v1"
    ):
        raise ReflectionError("phase_timeline must be a leafos.thinking-loop.v1 object")
    return artifact


def append_reflection(
    journal: Path, payload: Path, project_id: str, actor: str = "producer-model",
    writer_version: str = "leaf-memory/0.2.2.1",
    on_commit: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    artifact = validate_artifact(json.loads(payload.read_text(encoding="utf-8")))
    sequence, previous_hash = head(journal)
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    identity = canonical_digest({"artifact": artifact, "sequence": sequence + 1, "timestamp": timestamp})[:20]
    event = {
        "schema": "leafos.memory.event.v1",
        "event_id": "mem_" + identity,
        "run_id": artifact["run_id"],
        "project_id": project_id,
        "sequence": sequence + 1,
        "timestamp_utc": timestamp,
        "kind": "reflection",
        "epistemic_class": "record",
        "source": {
            "actor": actor, "model": artifact["producer"]["model"],
            "tool": "leaf-memory-reflection", "parent_event_ids": [],
        },
        "scope": {"task_id": artifact["task_id"], "paths": [], "symbols": []},
        "content": {
            "mime": "application/vnd.leafos.reasoning-artifact+json",
            "text": artifact["decision_summary"], "data": artifact,
        },
        "retrieval": {
            "importance": 0.65, "expires_at": None, "sensitivity": "project", "indexable": True,
        },
        "integrity": {
            "payload_sha256": "0" * 64, "previous_event_sha256": previous_hash,
            "writer_version": writer_version,
        },
    }
    append_native(journal, event)
    persisted = replay(journal)[-1]
    if on_commit:
        on_commit(persisted)
    return {"ok": True, "event": persisted}
