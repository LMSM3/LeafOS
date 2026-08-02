#!/usr/bin/env python3
"""Render the versioned FlowerOS quick shell syntax contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "config" / "quick-syntax.json"


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "leafos.quick-syntax.v1":
        raise ValueError("quick syntax schema must be leafos.quick-syntax.v1")
    if value.get("surface") != "FlowerOS" or value.get("engine") != "LeafOS":
        raise ValueError("quick syntax must preserve the FlowerOS surface and LeafOS engine")
    entries = value.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("quick syntax entries must be a non-empty list")
    aliases: set[str] = set()
    for entry in entries:
        alias = entry.get("alias") if isinstance(entry, dict) else None
        expansion = entry.get("expansion") if isinstance(entry, dict) else None
        if not isinstance(alias, str) or not alias or alias in aliases:
            raise ValueError(f"quick syntax alias is missing or duplicated: {alias!r}")
        if not isinstance(expansion, list) or not expansion or not all(
            isinstance(token, str) and token for token in expansion
        ):
            raise ValueError(f"quick syntax expansion is invalid: {alias}")
        if not isinstance(entry.get("description"), str) or not entry["description"]:
            raise ValueError(f"quick syntax description is invalid: {alias}")
        if not isinstance(entry.get("read_only"), bool) or not isinstance(entry.get("interactive"), bool):
            raise ValueError(f"quick syntax safety flags are invalid: {alias}")
        aliases.add(alias)
    return value


def render(contract: dict[str, Any]) -> str:
    rows = []
    for entry in contract["entries"]:
        mode = "read-only" if entry["read_only"] else "active"
        if entry["interactive"]:
            mode += ", interactive"
        rows.append((
            f"{contract['command']} {entry['alias']}",
            " ".join(entry["expansion"]),
            mode,
            entry["description"],
        ))
    alias_width = max(len(row[0]) for row in rows)
    expansion_width = max(len(row[1]) for row in rows)
    lines = [
        f"{contract['surface']} quick syntax ({contract['engine']} engine)",
        f"Usage: {contract['command']} <shortcut> [arguments]",
        "",
        f"{'Shortcut':<{alias_width}}  {'Expands to':<{expansion_width}}  Mode",
    ]
    lines.extend(
        f"{alias:<{alias_width}}  {expansion:<{expansion_width}}  {mode} - {description}"
        for alias, expansion, mode, description in rows
    )
    lines.extend([
        "",
        f"No arguments: {contract['command']} -> home",
        f"Full command list: {contract['command']} help",
        f"Machine-readable card: {contract['command']} q --json",
        "Shortcuts expand fixed command tokens; extra arguments are forwarded unchanged.",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(prog="leafos quick")
    parser.add_argument("--json", action="store_true", help="emit the machine-readable contract")
    args = parser.parse_args()
    contract = load_contract()
    print(
        json.dumps(contract, sort_keys=True, separators=(",", ":"))
        if args.json
        else render(contract)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
