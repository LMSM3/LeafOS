#!/usr/bin/env python3
"""CLI for applying deterministic cosmetic identity to LeafOS model packs.

Cosmetic identity is limited to flower, colour, symbol, and display_name.
It must never influence persona, capability, authority, confidence, priority,
assignment, routing, validation, or runtime state.

Usage:
    python pack_identity_cli.py generate <pack-id> [--flower rose] [--colour red]
    python pack_identity_cli.py apply --file config/packs/ficus.json [--flower fern] [--colour green] [--only-if-missing]
    python pack_identity_cli.py apply --registry config/pack-registry.json --pack penstemon-atlas-b9326c [--flower violet] [--colour purple] [--only-if-missing]
    python pack_identity_cli.py apply --all-packs [--only-if-missing]
    python pack_identity_cli.py apply --registry config/pack-registry.json --all-entries [--only-if-missing]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pack_identity import build_identity


ROOT = Path(__file__).resolve().parents[1]
PACKS_DIR = ROOT / "config" / "packs"


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cmd_generate(args: argparse.Namespace) -> int:
    identity = build_identity(args.pack_id, args.flower, args.colour)
    emit({"pack_id": args.pack_id, "identity": identity})
    return 0


def _resolve_registry(args: argparse.Namespace) -> Path | None:
    if args.registry:
        return Path(args.registry).resolve()
    default = ROOT / "config" / "pack-registry.json"
    return default if default.is_file() else None


def cmd_apply(args: argparse.Namespace) -> int:
    results: list[dict[str, Any]] = []
    force = not args.only_if_missing

    if args.all_packs:
        if not PACKS_DIR.is_dir():
            emit({"ok": False, "error": f"packs directory not found: {PACKS_DIR}"})
            return 1
        for path in sorted(PACKS_DIR.glob("*.json")):
            data = load_json(path)
            if not force and data.get("identity"):
                results.append({"path": str(path), "pack_id": data.get("id") or data.get("pack_id"), "action": "skipped", "reason": "identity exists"})
                continue
            pack_id = str(data.get("pack_id") or data.get("id") or path.stem)
            identity = build_identity(pack_id, args.flower, args.colour)
            data["identity"] = identity
            save_json(path, data)
            results.append({"path": str(path), "pack_id": pack_id, "action": "applied", "identity": identity})

    if args.file:
        path = Path(args.file).resolve()
        data = load_json(path)
        if not force and data.get("identity"):
            results.append({"path": str(path), "pack_id": data.get("id") or data.get("pack_id"), "action": "skipped", "reason": "identity exists"})
        else:
            pack_id = str(data.get("pack_id") or data.get("id") or path.stem)
            identity = build_identity(pack_id, args.flower, args.colour)
            data["identity"] = identity
            save_json(path, data)
            results.append({"path": str(path), "pack_id": pack_id, "action": "applied", "identity": identity})

    registry_path = _resolve_registry(args)
    if args.all_entries and registry_path:
        registry = load_json(registry_path)
        entries = registry.get("entries") or []
        for entry in entries:
            pack_id = entry.get("pack_id")
            if not pack_id:
                continue
            if not force and entry.get("identity"):
                results.append({"registry": str(registry_path), "pack_id": pack_id, "action": "skipped", "reason": "identity exists"})
                continue
            identity = build_identity(pack_id, args.flower, args.colour)
            entry["identity"] = identity
            entry["display_name"] = identity["display_name"]
            results.append({"registry": str(registry_path), "pack_id": pack_id, "action": "applied", "identity": identity})
        save_json(registry_path, registry)
    elif args.pack and registry_path:
        registry = load_json(registry_path)
        entries = registry.get("entries") or []
        for entry in entries:
            if entry.get("pack_id") == args.pack:
                if not force and entry.get("identity"):
                    results.append({"registry": str(registry_path), "pack_id": args.pack, "action": "skipped", "reason": "identity exists"})
                else:
                    identity = build_identity(args.pack, args.flower, args.colour)
                    entry["identity"] = identity
                    entry["display_name"] = identity["display_name"]
                    results.append({"registry": str(registry_path), "pack_id": args.pack, "action": "applied", "identity": identity})
                save_json(registry_path, registry)
                break
        else:
            emit({"ok": False, "error": f"pack_id {args.pack!r} not found in registry"})
            return 1

    if not results:
        emit({"ok": False, "error": "nothing to apply; provide --file, --all-packs, --registry/--pack, or --registry --all-entries"})
        return 1

    emit({"ok": True, "results": results})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="leafos pack-identity")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen = subparsers.add_parser("generate", help="generate cosmetic identity for a pack id")
    gen.add_argument("pack_id", help="stable pack identifier used as randomization seed")
    gen.add_argument("--flower", help="flower identity (default: randomized)")
    gen.add_argument("--colour", help="colour identity (default: randomized)")

    apply = subparsers.add_parser("apply", help="apply cosmetic identity to model-pack files or registry entries")
    apply.add_argument("--file", type=Path, help="path to a leafos.model-pack/v1 JSON file")
    apply.add_argument("--registry", type=Path, help="path to pack-registry.json")
    apply.add_argument("--pack", help="pack_id within the registry (required with --registry unless --all-entries)")
    apply.add_argument("--all-packs", action="store_true", help="apply to every config/packs/*.json file")
    apply.add_argument("--all-entries", action="store_true", help="apply to every entry in the registry")
    apply.add_argument("--only-if-missing", action="store_true", help="skip entries that already have an identity block")
    apply.add_argument("--flower", help="flower identity (default: randomized)")
    apply.add_argument("--colour", help="colour identity (default: randomized)")

    args = parser.parse_args()
    if args.command == "generate":
        return cmd_generate(args)
    if args.command == "apply":
        return cmd_apply(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
