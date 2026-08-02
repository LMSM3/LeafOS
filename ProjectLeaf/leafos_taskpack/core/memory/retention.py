#!/usr/bin/env python3
"""Verified LMEM quota and non-destructive archive operations."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from journal import replay, verify


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quota_status(journal: Path, max_bytes: int) -> dict[str, Any]:
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")
    used = journal.stat().st_size if journal.is_file() else 0
    return {
        "ok": used <= max_bytes, "state": "within_quota" if used <= max_bytes else "quota_exceeded",
        "used_bytes": used, "max_bytes": max_bytes, "remaining_bytes": max(max_bytes - used, 0),
    }


def archive(journal: Path, destination: Path) -> dict[str, Any]:
    verification = verify(journal)
    events = replay(journal)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + f".tmp.{os.getpid()}")
    try:
        shutil.copyfile(journal, temporary)
        verify(temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    manifest = {
        "schema": "leafos.memory.archive.v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(journal.resolve()), "archive": str(destination.resolve()),
        "bytes": destination.stat().st_size, "sha256": _sha256(destination),
        "records": len(events),
        "head_hash": events[-1]["integrity"]["payload_sha256"] if events else None,
        "source_verification": verification,
        "source_deleted": False,
    }
    manifest_path = destination.with_name(destination.name + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"ok": True, "archive": str(destination), "manifest": str(manifest_path), "metadata": manifest}


def verify_archive(destination: Path) -> dict[str, Any]:
    manifest_path = destination.with_name(destination.name + ".manifest.json")
    if not destination.is_file() or not manifest_path.is_file():
        return {"ok": False, "state": "missing"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        verification = verify(destination)
    except Exception as exc:  # native verifier supplies the detailed reason
        return {"ok": False, "state": "corrupt", "message": str(exc)}
    digest_ok = _sha256(destination) == manifest.get("sha256")
    return {"ok": digest_ok, "state": "valid" if digest_ok else "corrupt", "journal": verification}
