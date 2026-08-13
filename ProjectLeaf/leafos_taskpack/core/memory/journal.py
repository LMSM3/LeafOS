#!/usr/bin/env python3
"""Verified LMEM replay and native append adapters."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


class JournalError(RuntimeError):
    pass


def native_binary() -> Path:
    candidates = [
        Path(os.environ["LEAF_MEMORY_BIN"]) if os.environ.get("LEAF_MEMORY_BIN") else None,
        ROOT / "build" / "leaf-memory.exe",
        ROOT / "build" / "leaf-memory",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    raise JournalError("native leaf-memory executable not found")


def _native(*args: str) -> dict[str, Any]:
    completed = subprocess.run(
        [str(native_binary()), *args], capture_output=True, text=True, encoding="utf-8"
    )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise JournalError(completed.stderr.strip() or "invalid native leaf-memory response") from exc
    if completed.returncode or not result.get("ok"):
        raise JournalError(str(result.get("message", "native leaf-memory command failed")))
    return result


def verify(journal: Path) -> dict[str, Any]:
    return _native("verify", "--journal", str(journal))


def replay(journal: Path) -> list[dict[str, Any]]:
    result = _native("replay", "--journal", str(journal))
    events = result.get("events")
    if not isinstance(events, list):
        raise JournalError("native replay did not return an event list")
    return events


def head(journal: Path) -> tuple[int, str | None]:
    events = replay(journal)
    if not events:
        return 0, None
    last = events[-1]
    return int(last["sequence"]), str(last["integrity"]["payload_sha256"])


def append_native(journal: Path, event: dict[str, Any]) -> dict[str, Any]:
    journal.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", encoding="utf-8", delete=False, dir=journal.parent
    ) as handle:
        json.dump(event, handle, ensure_ascii=True, separators=(",", ":"))
        event_path = Path(handle.name)
    try:
        result = _native("append", "--journal", str(journal), "--event", str(event_path))
    finally:
        event_path.unlink(missing_ok=True)
    return result


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def redacted_event_ids(events: list[dict[str, Any]]) -> set[str]:
    """Return event ids targeted by valid tombstone records."""
    targets: set[str] = set()
    for event in events:
        if event.get("kind") != "tombstone":
            continue
        data = event.get("content", {}).get("data", {})
        if not isinstance(data, dict):
            continue
        one = data.get("target_event_id")
        many = data.get("target_event_ids", [])
        if isinstance(one, str) and one:
            targets.add(one)
        if isinstance(many, list):
            targets.update(item for item in many if isinstance(item, str) and item)
    return targets
