from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from . import storage, task_registry


def events_path(allocation_root: Path) -> Path:
    return allocation_root / "allocation-events.jsonl"


def read_events(allocation_root: Path) -> list[dict[str, Any]]:
    path = events_path(allocation_root)
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise storage.CCISError(f"invalid authoritative allocation event at line {line_number}: {error}") from error
        if not isinstance(value, dict):
            raise storage.CCISError(f"invalid authoritative allocation event object at line {line_number}")
        events.append(value)
    verify_events(events)
    return events


def verify_events(events: list[dict[str, Any]]) -> None:
    previous: str | None = None
    logical_tick = 0
    for sequence, event in enumerate(events, 1):
        task_registry.validate_contract("allocation-event", event)
        if event["sequence"] != sequence or event["event_id"] != f"alloc_evt_{sequence:08d}":
            raise storage.CCISError(f"allocation event sequence mismatch at line {sequence}")
        if event["previous_event_hash"] != previous:
            raise storage.CCISError(f"allocation event hash chain mismatch at line {sequence}")
        if event["payload_hash"] != storage.digest(event["payload"]):
            raise storage.CCISError(f"allocation event payload hash mismatch at line {sequence}")
        unsigned = {key: value for key, value in event.items() if key != "event_hash"}
        if event["event_hash"] != storage.digest(unsigned):
            raise storage.CCISError(f"allocation event hash mismatch at line {sequence}")
        if event["logical_tick"] < logical_tick:
            raise storage.CCISError(f"allocation logical clock moved backwards at line {sequence}")
        if event["event_type"] != "allocation.clock_observed" and event["logical_tick"] != logical_tick:
            raise storage.CCISError(f"logical time changed without a clock event at line {sequence}")
        if event["event_type"] == "allocation.clock_observed":
            if event["payload"].get("from_tick") != logical_tick or event["payload"].get("to_tick") != event["logical_tick"]:
                raise storage.CCISError(f"invalid logical clock payload at line {sequence}")
            logical_tick = event["logical_tick"]
        previous = event["event_hash"]


def make_event(
    events: list[dict[str, Any]], event_type: str, payload: dict[str, Any], *,
    logical_tick: int, task_id: str | None = None,
) -> dict[str, Any]:
    sequence = len(events) + 1
    event = {
        "ccis_object": "ccis.allocation_event", "schema_version": 1,
        "event_id": f"alloc_evt_{sequence:08d}", "sequence": sequence,
        "recorded_at": storage.now(), "logical_tick": logical_tick,
        "task_id": task_id, "event_type": event_type,
        "previous_event_hash": events[-1]["event_hash"] if events else None,
        "payload_hash": storage.digest(payload), "payload": payload,
    }
    event["event_hash"] = storage.digest(event)
    task_registry.validate_contract("allocation-event", event)
    return event


def append_event_unlocked(allocation_root: Path, event: dict[str, Any]) -> None:
    path = events_path(allocation_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
