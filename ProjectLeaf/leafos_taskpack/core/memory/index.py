#!/usr/bin/env python3
"""Disposable deterministic SQLite/FTS5 index over verified LMEM replay."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import re
from pathlib import Path
from typing import Any

from journal import canonical_digest, redacted_event_ids, replay


SCHEMA_VERSION = "leafos.memory.index.v1"


def default_path(journal: Path) -> Path:
    return journal.with_name(journal.name + ".index.sqlite3")


def build(journal: Path, database: Path, replace: bool = False) -> dict[str, Any]:
    if database.exists() and not replace:
        raise FileExistsError(f"index already exists: {database}")
    events = replay(journal)
    redacted_ids = redacted_event_ids(events)
    database.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=database.name + ".", suffix=".tmp", dir=database.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        connection = sqlite3.connect(temporary)
        try:
            connection.executescript("""
                PRAGMA journal_mode=DELETE;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE events (
                    sequence INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL, epistemic_class TEXT NOT NULL,
                    timestamp_utc TEXT NOT NULL, text TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL, redacted INTEGER NOT NULL,
                    event_json TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE event_fts USING fts5(
                    text, kind, event_id, content='events', content_rowid='sequence', tokenize='unicode61'
                );
            """)
            for event in events:
                redacted = event["event_id"] in redacted_ids
                stored_event = event
                if redacted:
                    stored_event = dict(event)
                    stored_event["content"] = {
                        "mime": "application/vnd.leafos.redacted+json",
                        "text": "", "data": {"redacted": True},
                    }
                row = (
                    int(event["sequence"]), event["event_id"], event["kind"], event["epistemic_class"],
                    event["timestamp_utc"], "" if redacted else str(event["content"].get("text", "")),
                    event["integrity"]["payload_sha256"], int(redacted),
                    json.dumps(stored_event, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
                )
                connection.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)", row)
                if not redacted and event["kind"] != "tombstone" and event.get("retrieval", {}).get("indexable", True):
                    connection.execute(
                        "INSERT INTO event_fts(rowid,text,kind,event_id) VALUES (?,?,?,?)",
                        (row[0], row[5], row[2], row[1]),
                    )
            head_sequence = int(events[-1]["sequence"]) if events else 0
            head_hash = events[-1]["integrity"]["payload_sha256"] if events else ""
            metadata = {
                "schema": SCHEMA_VERSION, "head_sequence": str(head_sequence),
                "head_hash": head_hash, "row_count": str(len(events)),
            }
            connection.executemany("INSERT INTO metadata VALUES (?,?)", sorted(metadata.items()))
            connection.commit()
        finally:
            connection.close()
        os.replace(temporary, database)
    finally:
        temporary.unlink(missing_ok=True)
    return status(database)


def status(database: Path) -> dict[str, Any]:
    if not database.is_file():
        return {"ok": False, "state": "missing", "database": str(database)}
    connection = sqlite3.connect(database)
    try:
        values = dict(connection.execute("SELECT key,value FROM metadata ORDER BY key"))
    finally:
        connection.close()
    return {
        "ok": True, "state": "ready", "database": str(database),
        "schema": values["schema"], "head_sequence": int(values["head_sequence"]),
        "head_hash": values["head_hash"] or None, "row_count": int(values["row_count"]),
    }


def query(database: Path, text: str, limit: int = 20) -> list[dict[str, Any]]:
    terms = re.findall(r"[A-Za-z0-9_]+", text)
    if not terms:
        return []
    expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
    connection = sqlite3.connect(database)
    try:
        rows = connection.execute(
            """SELECT e.event_json FROM event_fts f
               JOIN events e ON e.sequence=f.rowid
               WHERE event_fts MATCH ? ORDER BY bm25(event_fts), e.sequence LIMIT ?""",
            (expression, limit),
        ).fetchall()
    finally:
        connection.close()
    return [json.loads(row[0]) for row in rows]


def all_active(database: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(database)
    try:
        rows = connection.execute(
            "SELECT event_json FROM events WHERE redacted=0 AND kind<>'tombstone' ORDER BY sequence"
        ).fetchall()
    finally:
        connection.close()
    return [json.loads(row[0]) for row in rows]


def committed_fact_set_hash(database: Path) -> str:
    connection = sqlite3.connect(database)
    try:
        rows = connection.execute(
            "SELECT sequence,payload_sha256 FROM events WHERE epistemic_class='committed_fact' ORDER BY sequence"
        ).fetchall()
    finally:
        connection.close()
    return canonical_digest(rows)
