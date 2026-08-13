#!/usr/bin/env python3
"""Deterministic bounded context packs derived from verified LMEM replay."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import index as memory_index
from journal import canonical_digest, redacted_event_ids, replay


AUTHORITY_WEIGHT = {"committed_fact": 3.0, "evidence": 2.0, "record": 1.0}


class PackError(ValueError):
    pass


def _tokens(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _seal(pack: dict[str, Any]) -> str:
    unsealed = dict(pack)
    unsealed["pack_sha256"] = "0" * 64
    return canonical_digest(unsealed)


def build(
    journal: Path, output: Path, query: str, token_budget: int, run_id: str, task_id: str,
    model_id: str, tokenizer_id: str = "leafos.whitespace.v1", database: Path | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if token_budget < 0:
        raise PackError("token budget must be non-negative")
    events = replay(journal)
    database = database or memory_index.default_path(journal)
    memory_index.build(journal, database, replace=True)
    redacted = redacted_event_ids(events)
    filters = filters or {}
    allowed_authority = set(filters.get("epistemic_class", AUTHORITY_WEIGHT))
    allowed_kinds = set(filters.get("kind", []))
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_]+", query)]
    candidates: list[tuple[float, dict[str, Any], int, int]] = []
    exclusions: list[dict[str, Any]] = []
    for event in events:
        sequence = int(event["sequence"])
        if event["event_id"] in redacted:
            exclusions.append({"sequence": sequence, "reason": "redacted"})
            continue
        if event["kind"] == "tombstone":
            exclusions.append({"sequence": sequence, "reason": "tombstoned"})
            continue
        if event["epistemic_class"] not in allowed_authority or (allowed_kinds and event["kind"] not in allowed_kinds):
            exclusions.append({"sequence": sequence, "reason": "authority"})
            continue
        text = str(event.get("content", {}).get("text", ""))
        lower = text.lower()
        matches = sum(lower.count(term) for term in terms)
        if terms and matches == 0:
            continue
        tokens = _tokens(text)
        score = AUTHORITY_WEIGHT[event["epistemic_class"]] + float(matches)
        candidates.append((score, event, tokens, matches))
    candidates.sort(key=lambda item: (-item[0], int(item[1]["sequence"])))
    records: list[dict[str, Any]] = []
    measured = 0
    for score, event, tokens, matches in candidates:
        if measured + tokens > token_budget:
            exclusions.append({"sequence": int(event["sequence"]), "reason": "token_budget"})
            continue
        measured += tokens
        source = event.get("source", {})
        records.append({
            "sequence": int(event["sequence"]), "event_id": event["event_id"],
            "payload_sha256": event["integrity"]["payload_sha256"],
            "epistemic_class": event["epistemic_class"], "kind": event["kind"],
            "score": score,
            "score_components": {"authority": AUTHORITY_WEIGHT[event["epistemic_class"]], "term_matches": matches},
            "inclusion_reason": "query and authority filters matched",
            "tokens": tokens,
            "excerpt": {
                "text": str(event.get("content", {}).get("text", "")),
                "actor": source.get("actor"), "model": source.get("model"), "tool": source.get("tool"),
            },
        })
    exclusions.sort(key=lambda item: (item["sequence"], item["reason"]))
    head_sequence = int(events[-1]["sequence"]) if events else 0
    head_hash = events[-1]["integrity"]["payload_sha256"] if events else None
    created_at = events[-1]["timestamp_utc"] if events else "1970-01-01T00:00:00Z"
    identity = {
        "head_hash": head_hash, "query": query, "filters": filters,
        "tokenizer_id": tokenizer_id, "model_id": model_id, "token_budget": token_budget,
        "run_id": run_id, "task_id": task_id,
    }
    pack_id = "pack_" + canonical_digest(identity)[:20]

    pack = {
        "schema": "leafos.context-pack.v1", "pack_id": pack_id,
        "created_at": created_at, "run_id": run_id, "task_id": task_id,
        "source": {"journal_path": str(journal.resolve()), "head_sequence": head_sequence, "head_hash": head_hash},
        "query": {"text": query, "filters": filters, "weights_version": "leafos.context-rank.v1"},
        "tokenizer": {"model_id": model_id, "tokenizer_id": tokenizer_id},
        "budget": {"token_budget": token_budget, "measured_tokens": measured},
        "records": records, "exclusions": exclusions, "pack_sha256": "0" * 64,
    }
    pack["pack_sha256"] = _seal(pack)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(pack, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return pack


def inspect(path: Path) -> dict[str, Any]:
    pack = json.loads(path.read_text(encoding="utf-8"))
    return {
        "ok": True, "pack_id": pack["pack_id"], "pack_sha256": pack["pack_sha256"],
        "head_sequence": pack["source"]["head_sequence"], "records": len(pack["records"]),
        "exclusions": len(pack["exclusions"]), "budget": pack["budget"],
    }


def remove(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise PackError(f"pack not found: {path}")
    path.unlink()
    return {"ok": True, "deleted": str(path)}


def verify(path: Path) -> dict[str, Any]:
    pack = json.loads(path.read_text(encoding="utf-8"))
    digest_ok = pack.get("pack_sha256") == _seal(pack)
    journal = Path(pack.get("source", {}).get("journal_path", ""))
    if not journal.is_file():
        return {"ok": False, "state": "missing", "message": "source journal does not exist"}
    events = replay(journal)
    sequence = int(events[-1]["sequence"]) if events else 0
    head_hash = events[-1]["integrity"]["payload_sha256"] if events else None
    source_ok = sequence == pack["source"]["head_sequence"] and head_hash == pack["source"]["head_hash"]
    return {
        "ok": digest_ok and source_ok, "state": "valid" if digest_ok and source_ok else "diverged",
        "digest_ok": digest_ok, "source_ok": source_ok,
    }
