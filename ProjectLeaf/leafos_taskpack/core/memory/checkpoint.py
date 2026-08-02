#!/usr/bin/env python3
"""Bind checkpoints to a verified LMEM head and classify resume state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import index as memory_index
from journal import JournalError, canonical_digest, replay


def bind(
    journal: Path, checkpoint: Path, label: str, database: Path | None = None,
    context_pack: Path | None = None,
) -> dict[str, Any]:
    events = replay(journal)
    sequence = int(events[-1]["sequence"]) if events else 0
    head_hash = events[-1]["integrity"]["payload_sha256"] if events else None
    database = database or memory_index.default_path(journal)
    index_state = memory_index.build(journal, database, replace=True)
    context_pack_hash = None
    if context_pack:
        pack_record = json.loads(context_pack.read_text(encoding="utf-8"))
        context_pack_hash = pack_record.get("pack_sha256")
        if not isinstance(context_pack_hash, str) or len(context_pack_hash) != 64:
            raise ValueError("context pack is not sealed")
    record = {
        "schema": "leafos.memory.checkpoint.v1",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_label": label,
        "journal": str(journal.resolve()),
        "memory": {"head_sequence": sequence, "head_hash": head_hash},
        "context_pack_hash": context_pack_hash,
        "committed_fact_set_hash": memory_index.committed_fact_set_hash(database),
        "index_head_hash": index_state["head_hash"],
    }
    record["checkpoint_sha256"] = canonical_digest(record)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"ok": True, "state": "bound", "checkpoint": str(checkpoint), "binding": record}


def verify(checkpoint: Path, journal: Path | None = None) -> dict[str, Any]:
    if not checkpoint.is_file():
        return {"ok": False, "state": "missing", "message": "checkpoint does not exist"}
    try:
        binding = json.loads(checkpoint.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "state": "corrupt", "message": "checkpoint is unreadable"}
    expected_digest = binding.pop("checkpoint_sha256", None)
    if expected_digest != canonical_digest(binding):
        return {"ok": False, "state": "corrupt", "message": "checkpoint digest mismatch"}
    journal = journal or Path(binding["journal"])
    if not journal.is_file():
        return {"ok": False, "state": "missing", "message": "bound journal does not exist"}
    try:
        events = replay(journal)
    except JournalError as exc:
        return {"ok": False, "state": "corrupt", "message": str(exc)}
    current_sequence = int(events[-1]["sequence"]) if events else 0
    current_hash = events[-1]["integrity"]["payload_sha256"] if events else None
    bound_sequence = int(binding["memory"]["head_sequence"])
    bound_hash = binding["memory"]["head_hash"]
    if current_sequence == bound_sequence and current_hash == bound_hash:
        state = "exact"
    elif current_sequence > bound_sequence and (
        (bound_sequence == 0 and bound_hash is None)
        or events[bound_sequence - 1]["integrity"]["payload_sha256"] == bound_hash
    ):
        state = "advanced"
    else:
        state = "diverged"
    return {
        "ok": state in {"exact", "advanced"}, "state": state,
        "bound_sequence": bound_sequence, "current_sequence": current_sequence,
        "bound_hash": bound_hash, "current_hash": current_hash,
    }
