#!/usr/bin/env python3
"""USB 3.0 file-backed interceptor for the LeafOS typed loop inlet."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PYTHON_DIR = Path(__file__).resolve().parent
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import leaf_agent_loop as engine  # noqa: E402
import leaf_loop_inlet as inlet  # noqa: E402


SPOOL_DIRS = ("inbox", "outbox", "processing", "complete", "rejected", "quarantine", "state")
STATE_FILE = Path("state") / "interceptor.json"
MESSAGE_ID_PATTERN = re.compile(r"^msg-[A-Za-z0-9._-]{3,96}$")
INBOUND_TYPES = {
    "monitor.snapshot",
    "task.submit",
    "task.approve",
    "run.pause",
    "run.resume",
    "run.drain",
    "run.stop",
    "report.get",
}
OUTBOUND_TYPES = {"transport.ack", "transport.reject"}
ALL_TYPES = INBOUND_TYPES | OUTBOUND_TYPES


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest_payload(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _parse_time(value: Any, field: str) -> datetime:
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from error
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def spool_root(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _state_path(root: Path) -> Path:
    return root / STATE_FILE


def _new_state(root: Path, identity: str = "operator-selected") -> dict[str, Any]:
    return {
        "leafos_object": "leafos.usb_interceptor_state",
        "version": 1,
        "root": str(root),
        "identity": identity,
        "created_utc": utc_now(),
        "last_inbound_sequence": 0,
        "next_outbound_sequence": 1,
        "messages": {},
    }


def initialize(root_value: str | Path, identity: str = "operator-selected") -> dict[str, Any]:
    root = spool_root(root_value)
    if not isinstance(identity, str) or not identity.strip() or len(identity) > 128:
        raise ValueError("identity must be a non-empty string of at most 128 characters")
    root.mkdir(parents=True, exist_ok=True)
    for name in SPOOL_DIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    path = _state_path(root)
    state = engine.read_json(path, {}) if path.is_file() else _new_state(root, identity.strip())
    if state.get("leafos_object") != "leafos.usb_interceptor_state" or state.get("version") != 1:
        raise ValueError(f"invalid interceptor state: {path}")
    state["root"] = str(root)
    state.setdefault("identity", identity.strip())
    _atomic_write_json(path, state)
    return state


def _require_state(root_value: str | Path) -> tuple[Path, dict[str, Any]]:
    root = spool_root(root_value)
    path = _state_path(root)
    if not path.is_file():
        raise ValueError(f"USB interceptor is not initialized: {root}")
    state = engine.read_json(path, {})
    if state.get("leafos_object") != "leafos.usb_interceptor_state" or state.get("version") != 1:
        raise ValueError(f"invalid interceptor state: {path}")
    return root, state


def _save_state(root: Path, state: dict[str, Any]) -> None:
    messages = state.setdefault("messages", {})
    if len(messages) > 2048:
        ordered = sorted(messages.items(), key=lambda item: str(item[1].get("processed_utc", "")))
        state["messages"] = dict(ordered[-2048:])
    _atomic_write_json(_state_path(root), state)


def make_envelope(
    *,
    direction: str,
    message_id: str,
    sequence: int,
    sender_id: str,
    target_id: str,
    target_run: str,
    payload_type: str,
    payload: dict[str, Any],
    expires_utc: str | None = None,
) -> dict[str, Any]:
    envelope = {
        "leafos_object": "leafos.transport.envelope",
        "version": 1,
        "direction": direction,
        "message_id": message_id,
        "sequence": sequence,
        "sender_id": sender_id,
        "target_id": target_id,
        "target_run": target_run,
        "payload_type": payload_type,
        "created_utc": utc_now(),
        "expires_utc": expires_utc,
        "payload_sha256": digest_payload(payload),
        "payload": payload,
    }
    validate_envelope(envelope, expected_direction=direction)
    return envelope


def validate_envelope(envelope: Any, expected_direction: str = "inbound") -> dict[str, Any]:
    if not isinstance(envelope, dict):
        raise ValueError("transport envelope must be an object")
    required = {
        "leafos_object", "version", "direction", "message_id", "sequence",
        "sender_id", "target_id", "target_run", "payload_type", "created_utc",
        "expires_utc", "payload_sha256", "payload",
    }
    unknown = sorted(set(envelope) - required)
    missing = sorted(required - set(envelope))
    if unknown:
        raise ValueError("transport envelope has unknown fields: " + ", ".join(unknown))
    if missing:
        raise ValueError("transport envelope is missing fields: " + ", ".join(missing))
    if envelope["leafos_object"] != "leafos.transport.envelope" or envelope["version"] != 1:
        raise ValueError("transport envelope requires leafos.transport.envelope version 1")
    if envelope["direction"] != expected_direction:
        raise ValueError(f"transport envelope direction must be {expected_direction}")
    message_id = envelope["message_id"]
    if not isinstance(message_id, str) or not MESSAGE_ID_PATTERN.fullmatch(message_id):
        raise ValueError("message_id must match msg-<safe identifier>")
    if not isinstance(envelope["sequence"], int) or isinstance(envelope["sequence"], bool) or envelope["sequence"] < 1:
        raise ValueError("sequence must be a positive integer")
    for field in ("sender_id", "target_id", "target_run"):
        if not isinstance(envelope[field], str) or not envelope[field] or len(envelope[field]) > 256:
            raise ValueError(f"{field} must be a non-empty string of at most 256 characters")
    payload_type = envelope["payload_type"]
    if not isinstance(payload_type, str):
        raise ValueError("payload_type must be a string")
    if payload_type not in (INBOUND_TYPES if expected_direction == "inbound" else OUTBOUND_TYPES):
        raise ValueError(f"unsupported {expected_direction} payload type: {payload_type}")
    if not isinstance(envelope["payload"], dict):
        raise ValueError("transport payload must be an object")
    _parse_time(envelope["created_utc"], "created_utc")
    expires = envelope.get("expires_utc")
    if expires is not None:
        expiry = _parse_time(expires, "expires_utc")
        if expiry <= _parse_time(envelope["created_utc"], "created_utc"):
            raise ValueError("expires_utc must be after created_utc")
        if expiry <= datetime.now(timezone.utc):
            raise ValueError("transport envelope has expired")
    if envelope["payload_sha256"] != digest_payload(envelope["payload"]):
        raise ValueError("transport payload hash does not match payload")
    return envelope


def _safe_destination(directory: Path, source: Path) -> Path:
    candidate = directory / source.name
    if not candidate.exists():
        return candidate
    suffix = digest_bytes(source.read_bytes())[:12]
    return directory / f"{source.stem}.{suffix}{source.suffix}"


def _move(source: Path, directory: Path) -> Path:
    destination = _safe_destination(directory, source)
    source.replace(destination)
    return destination


def _resolve_run(target_run: str) -> Path:
    run_dir = inlet.resolve_run(target_run)
    runs_root = inlet.RUNS_ROOT.resolve()
    try:
        run_dir.relative_to(runs_root)
    except ValueError as error:
        raise ValueError("transport target run must be inside the registered LeafOS runs root") from error
    return run_dir


def _validate_payload(envelope: dict[str, Any]) -> None:
    payload_type = envelope["payload_type"]
    payload = envelope["payload"]
    if payload_type == "task.submit":
        if payload.get("leafos_object") != "leafos.task_control_request" or payload.get("version") != 1:
            raise ValueError("task.submit payload must be a version-1 task control request")
        if payload.get("action") != "submit" or not payload.get("request_id"):
            raise ValueError("task.submit payload requires action=submit and request_id")
        inlet._normalize_task_control(payload)
    elif payload_type == "task.approve":
        if set(payload) != {"task_id"} or not isinstance(payload["task_id"], str) or not payload["task_id"]:
            raise ValueError("task.approve payload requires only task_id")
    elif payload_type.startswith("run."):
        action = payload_type[4:]
        if set(payload) != {"action"} or payload.get("action") != action:
            raise ValueError(f"{payload_type} payload must contain only action={action}")
    elif payload_type == "monitor.snapshot":
        allowed = {"after", "heartbeat_timeout"}
        if set(payload) - allowed:
            raise ValueError("monitor.snapshot payload has unknown fields")
        after = payload.get("after", 0)
        if not isinstance(after, int) or isinstance(after, bool) or after < 0:
            raise ValueError("monitor.snapshot after must be a non-negative integer")
        heartbeat_value = payload.get("heartbeat_timeout", 90.0)
        if isinstance(heartbeat_value, bool) or not isinstance(heartbeat_value, (int, float)):
            raise ValueError("monitor.snapshot heartbeat_timeout must be a positive number")
        heartbeat_timeout = float(heartbeat_value)
        if not math.isfinite(heartbeat_timeout) or heartbeat_timeout <= 0:
            raise ValueError("monitor.snapshot heartbeat_timeout must be positive")
    elif payload_type == "report.get":
        report_format = payload.get("format", "md")
        if set(payload) - {"format"} or not isinstance(report_format, str) or report_format not in {"md", "json"}:
            raise ValueError("report.get format must be md or json")


def _request_id_for(message_id: str) -> str:
    return "req-" + hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:24]


def _already_submitted(run_dir: Path, request_id: str) -> dict[str, Any] | None:
    queue = engine.read_json(run_dir / "queue.json", {})
    return next((task for task in queue.get("tasks", []) if task.get("request_id") == request_id), None)


def _execute(envelope: dict[str, Any]) -> dict[str, Any]:
    _validate_payload(envelope)
    run_dir = _resolve_run(envelope["target_run"])
    payload_type = envelope["payload_type"]
    payload = envelope["payload"]
    if payload_type == "monitor.snapshot":
        return inlet.monitor_snapshot(
            run_dir,
            int(payload.get("after", 0)),
            float(payload.get("heartbeat_timeout", 90.0)),
        )
    if payload_type == "report.get":
        report_format = payload.get("format", "md")
        if report_format == "json":
            return {"format": "json", "status": inlet.status_payload(run_dir)}
        report = run_dir / "report.md"
        content = report.read_text(encoding="utf-8", errors="replace") if report.is_file() else ""
        if len(content) > 1_000_000:
            raise ValueError("report exceeds transport response limit")
        return {"format": "md", "content": content}
    if payload_type == "task.submit":
        existing = _already_submitted(run_dir, str(payload["request_id"]))
        if existing is not None:
            return {"duplicate": True, "task": existing}
        return {"task": inlet.apply_task_control(run_dir, payload)}
    if payload_type == "task.approve":
        request = {
            "leafos_object": "leafos.task_control_request",
            "version": 1,
            "request_id": _request_id_for(envelope["message_id"]),
            "action": "approve",
            "task_id": payload["task_id"],
        }
        return {"task": inlet.apply_task_control(run_dir, request)}
    action = payload_type[4:]
    inlet.set_control_state(run_dir, action)
    return {"status": inlet.status_payload(run_dir)}


def _write_outbound(
    root: Path,
    inbound: dict[str, Any] | None,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    error: str = "",
) -> tuple[dict[str, Any], Path]:
    state = engine.read_json(_state_path(root), _new_state(root))
    outbound_sequence = int(state.get("next_outbound_sequence", 1))
    original_id = str(inbound.get("message_id", "msg-invalid-unknown")) if inbound else "msg-invalid-unknown"
    target_run = str(inbound.get("target_run", "unknown")) if inbound else "unknown"
    target_id = str(inbound.get("sender_id", "unknown-device")) if inbound else "unknown-device"
    payload = {
        "status": status,
        "message_id": original_id,
        "sequence": inbound.get("sequence") if inbound else None,
        "payload_type": inbound.get("payload_type") if inbound else None,
        "result": result,
        "error": error or None,
    }
    payload_type = "transport.ack" if status in {"accepted", "duplicate"} else "transport.reject"
    message_id = "msg-ack-" + re.sub(r"[^A-Za-z0-9._-]", "-", original_id[4:])[:80]
    envelope = make_envelope(
        direction="outbound",
        message_id=message_id,
        sequence=outbound_sequence,
        sender_id="leafos-host",
        target_id=target_id,
        target_run=target_run,
        payload_type=payload_type,
        payload=payload,
    )
    path = root / "outbox" / f"{original_id}.json"
    _atomic_write_json(path, envelope)
    state["next_outbound_sequence"] = outbound_sequence + 1
    _save_state(root, state)
    return envelope, path


def _record_message(root: Path, envelope: dict[str, Any], status: str, ack_path: Path, error: str = "") -> None:
    state = engine.read_json(_state_path(root), _new_state(root))
    message_id = envelope["message_id"]
    state.setdefault("messages", {})[message_id] = {
        "status": status,
        "sequence": envelope["sequence"],
        "payload_type": envelope["payload_type"],
        "ack_path": str(ack_path),
        "processed_utc": utc_now(),
        "error": error or None,
    }
    state["last_inbound_sequence"] = max(int(state.get("last_inbound_sequence", 0)), int(envelope["sequence"]))
    _save_state(root, state)


def _reject_malformed(root: Path, source: Path, reason: str) -> dict[str, Any]:
    token = digest_bytes(source.read_bytes())[:16]
    inbound = {
        "message_id": f"msg-invalid-{token}",
        "sequence": None,
        "payload_type": None,
        "target_run": "unknown",
        "sender_id": "unknown-device",
    }
    _, ack_path = _write_outbound(root, inbound, "rejected", error=reason)
    moved = _move(source, root / "quarantine")
    return {"message_id": inbound["message_id"], "status": "rejected", "error": reason, "ack_path": str(ack_path), "path": str(moved)}


def process_file(root: Path, source: Path) -> dict[str, Any]:
    try:
        envelope = json.loads(source.read_text(encoding="utf-8"))
        validate_envelope(envelope, expected_direction="inbound")
    except (OSError, TypeError, json.JSONDecodeError, ValueError) as error:
        return _reject_malformed(root, source, str(error))

    state = engine.read_json(_state_path(root), _new_state(root))
    message_id = envelope["message_id"]
    previous = state.get("messages", {}).get(message_id)
    if previous is not None:
        _, ack_path = _write_outbound(root, envelope, "duplicate", error="message_id already processed")
        moved = _move(source, root / "complete")
        return {"message_id": message_id, "status": "duplicate", "ack_path": str(ack_path), "path": str(moved)}
    if int(envelope["sequence"]) <= int(state.get("last_inbound_sequence", 0)):
        error = "inbound sequence is older than the committed cursor"
        _, ack_path = _write_outbound(root, envelope, "rejected", error=error)
        _record_message(root, envelope, "rejected", ack_path, error)
        moved = _move(source, root / "rejected")
        return {"message_id": message_id, "status": "rejected", "error": error, "ack_path": str(ack_path), "path": str(moved)}

    status = "accepted"
    result: dict[str, Any] | None = None
    error_text = ""
    try:
        result = _execute(envelope)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as error:
        status = "rejected"
        error_text = str(error)
    _, ack_path = _write_outbound(root, envelope, status, result=result, error=error_text)
    _record_message(root, envelope, status, ack_path, error_text)
    moved = _move(source, root / ("complete" if status == "accepted" else "rejected"))
    return {
        "message_id": message_id,
        "status": status,
        "payload_type": envelope["payload_type"],
        "error": error_text or None,
        "ack_path": str(ack_path),
        "path": str(moved),
    }


def _recover_processing(root: Path) -> None:
    for source in sorted((root / "processing").glob("*.json")):
        _move(source, root / "inbox")


def pump_once(root_value: str | Path, max_messages: int = 64) -> list[dict[str, Any]]:
    root, _ = _require_state(root_value)
    _recover_processing(root)
    results = []
    for source in sorted((root / "inbox").glob("*.json"))[:max_messages]:
        processing = root / "processing" / source.name
        source.replace(processing)
        results.append(process_file(root, processing))
    return results


def status(root_value: str | Path) -> dict[str, Any]:
    root, state = _require_state(root_value)
    counts = {name: len(list((root / name).glob("*.json"))) for name in SPOOL_DIRS if name != "state"}
    return {
        "leafos_object": "leafos.usb_interceptor_status",
        "version": 1,
        "root": str(root),
        "counts": counts,
        "last_inbound_sequence": int(state.get("last_inbound_sequence", 0)),
        "next_outbound_sequence": int(state.get("next_outbound_sequence", 1)),
        "remembered_messages": len(state.get("messages", {})),
    }


def publish(root_value: str | Path, args: argparse.Namespace) -> dict[str, Any]:
    root, state = _require_state(root_value)
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("payload file must contain a JSON object")
    sequence = args.sequence or int(state.get("last_inbound_sequence", 0)) + 1
    message_id = args.message_id or f"msg-{sequence:08d}"
    if any(
        message_id in state.get("messages", {})
        or (root / directory / f"{message_id}.json").exists()
        for directory in ("inbox", "processing", "complete", "rejected", "quarantine")
    ):
        raise ValueError(f"message_id already exists: {message_id}")
    envelope = make_envelope(
        direction="inbound",
        message_id=message_id,
        sequence=sequence,
        sender_id=args.sender,
        target_id="leafos-host",
        target_run=args.target_run,
        payload_type=args.payload_type,
        payload=payload,
        expires_utc=args.expires_utc or None,
    )
    path = root / "inbox" / f"{message_id}.json"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(envelope, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return {"message_id": message_id, "sequence": sequence, "path": str(path), "payload_type": args.payload_type}


def command_init(args: argparse.Namespace) -> int:
    state = initialize(args.root, args.identity)
    print(json.dumps(state, indent=2, ensure_ascii=True) if args.json else f"initialized: {spool_root(args.root)} ({state['identity']})")
    return 0


def command_status(args: argparse.Namespace) -> int:
    payload = status(args.root)
    print(json.dumps(payload, indent=2, ensure_ascii=True) if args.json else "\n".join(f"{key}: {value}" for key, value in payload.items()))
    return 0


def command_pump(args: argparse.Namespace) -> int:
    while True:
        results = pump_once(args.root, args.max_messages)
        for result in results:
            print(json.dumps(result, separators=(",", ":"), ensure_ascii=True) if args.json else f"{result['status']}: {result['message_id']}", flush=True)
        if args.once:
            return 0
        time.sleep(args.interval)


def command_publish(args: argparse.Namespace) -> int:
    result = publish(args.root, args)
    print(json.dumps(result, indent=2, ensure_ascii=True) if args.json else result["path"])
    return 0


def command_validate(args: argparse.Namespace) -> int:
    envelope = json.loads(Path(args.file).read_text(encoding="utf-8"))
    validate_envelope(envelope, expected_direction=args.direction)
    print(json.dumps({"status": "valid", "message_id": envelope["message_id"], "payload_type": envelope["payload_type"]}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="initialize a USB interceptor root")
    init.add_argument("root")
    init.add_argument("--identity", default="operator-selected")
    init.add_argument("--json", action="store_true")
    init.set_defaults(handler=command_init)

    stat = sub.add_parser("status", help="show interceptor spool status")
    stat.add_argument("root")
    stat.add_argument("--json", action="store_true")
    stat.set_defaults(handler=command_status)

    pump = sub.add_parser("pump", help="process ready inbound envelopes")
    pump.add_argument("root")
    pump.add_argument("--once", action="store_true")
    pump.add_argument("--interval", type=float, default=1.0)
    pump.add_argument("--max-messages", type=int, default=64)
    pump.add_argument("--json", action="store_true")
    pump.set_defaults(handler=command_pump)

    pub = sub.add_parser("publish", help="write one typed envelope atomically to inbox")
    pub.add_argument("root")
    pub.add_argument("--payload", required=True)
    pub.add_argument("--type", dest="payload_type", choices=sorted(INBOUND_TYPES), required=True)
    pub.add_argument("--target-run", required=True)
    pub.add_argument("--sender", default="usb-device")
    pub.add_argument("--sequence", type=int, default=0)
    pub.add_argument("--message-id", default="")
    pub.add_argument("--expires-utc", default="")
    pub.add_argument("--json", action="store_true")
    pub.set_defaults(handler=command_publish)

    validate = sub.add_parser("validate", help="validate one envelope file")
    validate.add_argument("file")
    validate.add_argument("--direction", choices=("inbound", "outbound"), default="inbound")
    validate.set_defaults(handler=command_validate)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if getattr(args, "interval", 1.0) <= 0:
            raise ValueError("interval must be greater than zero")
        if getattr(args, "max_messages", 1) <= 0:
            raise ValueError("max-messages must be greater than zero")
        return int(args.handler(args) or 0)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"usb-interceptor: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
