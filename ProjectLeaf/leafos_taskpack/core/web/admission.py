#!/usr/bin/env python3
"""Strict WO-044 action admission into the CPU-authoritative LeafOS inlet."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = ROOT / "core" / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))
import leaf_loop_inlet as inlet

RUNS_ROOT = ROOT / "runs" / "agent-loop"
_REQUEST = re.compile(r"^req_[A-Za-z0-9._-]{8,96}$")
_SESSION = re.compile(r"^ses_[A-Za-z0-9._-]{8,96}$")
_RESOURCE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{2,127}$")
_ALLOWED_FIELDS = {
    "leafos_object", "version", "capability_id", "request_id", "session_id",
    "subject", "target", "nonce", "issued_at", "expires_at", "host_facts_hash",
    "precondition_hash", "preview_digest", "approval_ref", "payload",
}


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def canonical_digest(request: Dict[str, Any]) -> str:
    data = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def validate_action(request: Any) -> Dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("action request must be an object")
    unknown = sorted(set(request) - _ALLOWED_FIELDS)
    if unknown:
        raise ValueError("unknown action fields: " + ", ".join(unknown))
    required = {"leafos_object", "version", "capability_id", "request_id", "session_id", "subject", "target", "nonce", "issued_at", "expires_at", "payload"}
    missing = sorted(required - set(request))
    if missing:
        raise ValueError("missing action fields: " + ", ".join(missing))
    if request["leafos_object"] != "leafos.midend_action_request" or request["version"] != 1:
        raise ValueError("unsupported action contract")
    if request["capability_id"] != "run.pause":
        raise ValueError("only run.pause is admitted in the initial vertical slice")
    if not _REQUEST.fullmatch(str(request["request_id"])) or not _SESSION.fullmatch(str(request["session_id"])):
        raise ValueError("invalid request or session identifier")
    if not isinstance(request["nonce"], str) or not 16 <= len(request["nonce"]) <= 256:
        raise ValueError("nonce must contain 16-256 characters")
    if not isinstance(request["payload"], dict) or set(request["payload"]) - {"reason"}:
        raise ValueError("run.pause payload accepts only reason")
    reason = str(request["payload"].get("reason", ""))
    if not 1 <= len(reason) <= 500:
        raise ValueError("run.pause reason must contain 1-500 characters")
    subject = request["subject"]
    target = request["target"]
    if not isinstance(subject, dict) or set(subject) != {"type", "id"} or subject["type"] != "operator":
        raise ValueError("run.pause requires an operator subject")
    if not isinstance(target, dict) or set(target) != {"type", "id", "version"} or target["type"] != "run":
        raise ValueError("run.pause requires a versioned run target")
    if not _RESOURCE.fullmatch(str(target["id"])):
        raise ValueError("run.pause requires a safe run identifier")
    if not isinstance(target["version"], int) or isinstance(target["version"], bool) or target["version"] < 0:
        raise ValueError("target version must be a non-negative integer")
    issued = _parse_time(str(request["issued_at"])); expires = _parse_time(str(request["expires_at"])); now = datetime.now(timezone.utc)
    if issued > now or expires <= now or (expires - issued).total_seconds() > 300:
        raise ValueError("action time window is invalid or expired")
    return request


def _replay_path(run_dir: Path) -> Path:
    return run_dir / "midend-admission.jsonl"


def _prior_disposition(run_dir: Path, request_id: str, nonce: str) -> Dict[str, Any] | None:
    path = _replay_path(run_dir)
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if value.get("request_id") == request_id or value.get("nonce") == nonce:
            disposition = value.get("disposition")
            return disposition if isinstance(disposition, dict) else None
    return None


def admit(request: Any) -> Tuple[int, Dict[str, Any]]:
    normalized = validate_action(request)
    target = normalized["target"]
    run_dir = RUNS_ROOT / str(target["id"])
    if run_dir.parent != RUNS_ROOT or not (run_dir / "run.json").is_file():
        return 404, _error(normalized["request_id"], "RESOURCE_NOT_FOUND")
    prior = _prior_disposition(run_dir, normalized["request_id"], normalized["nonce"])
    if prior is not None:
        return 200, prior
    run = inlet.engine.read_json(run_dir / "run.json", {})
    state = inlet.engine.read_json(run_dir / "state.json", {})
    actual_version = int(run.get("version") or 0)
    actual_state = str(state.get("status") or run.get("state") or run.get("status") or "unknown")
    if target["version"] != actual_version or actual_state not in {"active", "executing", "running", "resumed", "validating"}:
        return 409, _error(normalized["request_id"], "STATE_CONFLICT")
    digest = canonical_digest(normalized)
    control_id = "ctl_" + digest.removeprefix("sha256:")[:20]
    inlet.set_control_state(
        run_dir,
        "pause",
        request_id=normalized["request_id"],
        request_digest=digest,
        capability_id="run.pause",
    )
    disposition = {
        "leafos_object": "leafos.midend_native_disposition", "version": 1,
        "request_id": normalized["request_id"], "control_id": control_id,
        "capability_id": "run.pause", "status": "accepted",
        "recorded_at": datetime.now(timezone.utc).isoformat(), "request_digest": digest,
        "reason_code": None, "evidence_ref": f"evidence://runs/{target['id']}/events/run.paused",
        "checkpoint_ref": None,
    }
    with _replay_path(run_dir).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "request_id": normalized["request_id"],
            "nonce": normalized["nonce"],
            "disposition": disposition,
        }, sort_keys=True) + "\n")
    return 202, disposition


def _error(request_id: str, code: str) -> Dict[str, Any]:
    return {"leafos_object": "leafos.midend_error", "version": 1, "request_id": request_id, "code": code}
