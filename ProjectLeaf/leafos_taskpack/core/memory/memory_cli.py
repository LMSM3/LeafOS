#!/usr/bin/env python3
"""LeafOS advanced memory commands layered over the native LMEM journal."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import checkpoint as memory_checkpoint
import index as memory_index
import pack as memory_pack
import retention as memory_retention
from journal import JournalError, redacted_event_ids, replay
from reflection import ReflectionError, append_reflection


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="leafctl memory")
    commands = parser.add_subparsers(dest="command", required=True)

    append = commands.add_parser("append")
    append.add_argument("--kind", required=True, choices=["reflection"])
    append.add_argument("--journal", required=True, type=Path)
    append.add_argument("--payload", "--event", dest="payload", required=True, type=Path)
    append.add_argument("--project-id", default="leafos-local")
    append.add_argument("--actor", default="producer-model")
    append.add_argument("--writer-version", default="leaf-memory/0.2.2.1")

    index = commands.add_parser("index")
    index_commands = index.add_subparsers(dest="index_command", required=True)
    for name in ("build", "rebuild", "status"):
        child = index_commands.add_parser(name)
        child.add_argument("--journal", required=True, type=Path)
        child.add_argument("--index", dest="database", type=Path)
    query = index_commands.add_parser("query")
    query.add_argument("--journal", required=True, type=Path)
    query.add_argument("--index", dest="database", type=Path)
    query.add_argument("--text", required=True)
    query.add_argument("--limit", type=int, default=20)

    query_alias = commands.add_parser("query")
    query_alias.add_argument("--journal", required=True, type=Path)
    query_alias.add_argument("--index", dest="database", type=Path)
    query_alias.add_argument("--text", required=True)
    query_alias.add_argument("--limit", type=int, default=20)

    pack = commands.add_parser("pack")
    pack_commands = pack.add_subparsers(dest="pack_command", required=True)
    pack_build = pack_commands.add_parser("build")
    pack_build.add_argument("--journal", required=True, type=Path)
    pack_build.add_argument("--out", required=True, type=Path)
    pack_build.add_argument("--query", default="")
    pack_build.add_argument("--token-budget", required=True, type=int)
    pack_build.add_argument("--run-id", required=True)
    pack_build.add_argument("--task-id", required=True)
    pack_build.add_argument("--model-id", required=True)
    pack_build.add_argument("--tokenizer-id", default="leafos.whitespace.v1")
    pack_build.add_argument("--index", dest="database", type=Path)
    pack_delete = pack_commands.add_parser("delete")
    pack_delete.add_argument("pack", type=Path)
    pack_delete.add_argument("--yes", action="store_true", help="delete without confirmation")
    for name in ("inspect", "verify"):
        child = pack_commands.add_parser(name)
        child.add_argument("pack", type=Path)

    stats = commands.add_parser("stats")
    stats.add_argument("--journal", required=True, type=Path)
    stats.add_argument("--max-bytes", type=int)

    archive = commands.add_parser("archive")
    archive_commands = archive.add_subparsers(dest="archive_command", required=True)
    archive_create = archive_commands.add_parser("create")
    archive_create.add_argument("--journal", required=True, type=Path)
    archive_create.add_argument("--out", required=True, type=Path)
    archive_verify = archive_commands.add_parser("verify")
    archive_verify.add_argument("archive", type=Path)

    checkpoint = commands.add_parser("checkpoint")
    checkpoint_commands = checkpoint.add_subparsers(dest="checkpoint_command", required=True)
    bind = checkpoint_commands.add_parser("bind")
    bind.add_argument("--journal", required=True, type=Path)
    bind.add_argument("--checkpoint", required=True, type=Path)
    bind.add_argument("--index", dest="database", type=Path)
    bind.add_argument("--label", required=True)
    bind.add_argument("--pack", dest="context_pack", type=Path)
    verify = checkpoint_commands.add_parser("verify")
    verify.add_argument("checkpoint", nargs="?", type=Path)
    verify.add_argument("--checkpoint", dest="checkpoint_option", type=Path)
    verify.add_argument("--journal", type=Path)
    return parser


def execute(args: argparse.Namespace) -> object:
    if args.command == "append":
        return append_reflection(args.journal, args.payload, args.project_id, args.actor, args.writer_version)
    if args.command in {"index", "query"}:
        action = args.index_command if args.command == "index" else "query"
        database = args.database or memory_index.default_path(args.journal)
        if action == "build":
            return memory_index.build(args.journal, database)
        if action == "rebuild":
            return memory_index.build(args.journal, database, replace=True)
        if action == "status":
            return memory_index.status(database)
        return {"ok": True, "query": args.text, "results": memory_index.query(database, args.text, args.limit)}
    if args.command == "pack":
        if args.pack_command == "inspect":
            return memory_pack.inspect(args.pack)
        if args.pack_command == "verify":
            return memory_pack.verify(args.pack)
        if args.pack_command == "delete":
            return memory_pack.remove(args.pack)
        pack = memory_pack.build(
            args.journal, args.out, args.query, args.token_budget, args.run_id, args.task_id,
            args.model_id, args.tokenizer_id, args.database,
        )
        return {"ok": True, "pack": pack}
    if args.command == "stats":
        events = replay(args.journal)
        redacted = redacted_event_ids(events)
        result = {
            "ok": True, "records": len(events), "head_sequence": int(events[-1]["sequence"]) if events else 0,
            "head_hash": events[-1]["integrity"]["payload_sha256"] if events else None,
            "reflections": sum(event.get("kind") == "reflection" for event in events),
            "tombstones": sum(event.get("kind") == "tombstone" for event in events),
            "redacted_records": len(redacted),
        }
        if args.max_bytes is not None:
            result["quota"] = memory_retention.quota_status(args.journal, args.max_bytes)
            result["ok"] = result["quota"]["ok"]
        return result
    if args.command == "archive":
        if args.archive_command == "create":
            return memory_retention.archive(args.journal, args.out)
        return memory_retention.verify_archive(args.archive)
    if args.checkpoint_command == "bind":
        return memory_checkpoint.bind(args.journal, args.checkpoint, args.label, args.database, args.context_pack)
    checkpoint_path = args.checkpoint_option or args.checkpoint
    if checkpoint_path is None:
        raise ValueError("checkpoint verify requires a checkpoint path")
    return memory_checkpoint.verify(checkpoint_path, args.journal)


def main() -> int:
    try:
        emit(execute(build_parser().parse_args()))
        return 0
    except (ReflectionError, JournalError, FileExistsError, ValueError, OSError, json.JSONDecodeError, sqlite3.Error) as exc:
        emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
