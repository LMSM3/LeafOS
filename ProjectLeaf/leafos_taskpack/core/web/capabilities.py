#!/usr/bin/env python3
"""Read-only WO-044 capability catalog and advisory discovery."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "config" / "midend-capabilities.json"
_ACTIVE_RUN_STATES = {"active", "executing", "running", "validating"}
_PAUSED_RUN_STATES = {"paused"}
_TERMINAL_RUN_STATES = {"complete", "completed", "failed", "cancelled", "stopped"}


def _read_catalog() -> Dict[str, Any]:
    try:
        value = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        if value.get("schema") == "leafos.midend-capability-catalog.v1" and isinstance(value.get("capabilities"), list):
            return value
    except (OSError, json.JSONDecodeError):
        pass
    return {"schema": "leafos.midend-capability-catalog.v1", "version": 1, "capabilities": []}


def catalog() -> Dict[str, Any]:
    source = _read_catalog()
    values = sorted(source["capabilities"], key=lambda item: item["capability_id"])
    return {
        "leafos_object": "leafos.midend_capability_catalog",
        "version": 1,
        "authority": "advisory_only_native_inlet_required",
        "capabilities": values,
        "count": len(values),
    }


def _available_ids(resource_type: str, state: str, facts: Dict[str, Any]) -> List[str]:
    state = state.lower()
    if resource_type == "run":
        if state in _ACTIVE_RUN_STATES:
            return ["run.pause", "run.cancel"]
        if state in _PAUSED_RUN_STATES:
            values = ["run.cancel"]
            if facts.get("checkpoint_available"):
                values.append("run.resume")
            return values
        return [] if state in _TERMINAL_RUN_STATES else ["run.cancel"]
    if resource_type == "task":
        if state in {"blocked", "approval_required", "awaiting_approval"}:
            return ["task.approve", "task.reject"]
        if state in {"failed", "rejected"}:
            return ["task.retry"]
    if resource_type == "report" and facts.get("validated"):
        return ["report.export"]
    if resource_type == "install_plan":
        if state == "previewed":
            return ["install.apply"]
        if state in {"applied", "failed"} and facts.get("rollback_available"):
            return ["install.rollback"]
    if resource_type == "profile" and facts.get("compatible"):
        return ["profile.activate"]
    if resource_type == "project":
        return ["project.open", "run.start"]
    return []


def discover(resource_type: str, resource_id: str, version: int, state: str, facts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    facts = facts or {}
    declarations = {item["capability_id"]: item for item in catalog()["capabilities"]}
    expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    values = []
    for capability_id in sorted(_available_ids(resource_type, state, facts)):
        declaration = declarations.get(capability_id)
        if declaration is None:
            continue
        values.append({
            "id": capability_id,
            "schema_version": "1.0",
            "status": "available",
            "payload_schema_ref": declaration["payload_schema_ref"],
            "requires_preview": declaration["approval_policy"] == "explicit_digest_bound",
            "requires_approval": declaration["approval_policy"] in {"explicit", "explicit_digest_bound"},
            "expires_at": expires,
            "authority": "advisory_only",
        })
    return {
        "leafos_object": "leafos.midend_capability_discovery",
        "version": 1,
        "resource": {"type": resource_type, "id": resource_id, "version": version},
        "projected_state": state,
        "capabilities": values,
        "native_admission_required": True,
        "mutations_enabled": False,
    }
