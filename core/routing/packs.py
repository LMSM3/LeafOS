from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.models.inventory import ModelError, resolve_model
from core.state import atomic_json, read_json, utc_now


class PackError(ValueError):
    pass


def pack_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob("*.json") if path.is_file()) if directory.is_dir() else []


def load_pack(path: Path) -> dict[str, Any]:
    try:
        pack = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PackError(f"malformed pack {path.name}: {error}") from error
    if pack.get("schema") != "leafos.pack.v1":
        raise PackError(f"unsupported pack schema in {path.name}")
    if not isinstance(pack.get("id"), str) or not isinstance(pack.get("name"), str):
        raise PackError(f"pack identity is invalid in {path.name}")
    if not isinstance(pack.get("lanes"), dict) or not pack["lanes"]:
        raise PackError(f"pack has no lanes: {path.name}")
    return pack


def find_pack(directory: Path, query: str) -> tuple[Path, dict[str, Any]]:
    matches = []
    for path in pack_files(directory):
        try:
            pack = load_pack(path)
        except PackError:
            continue
        if query.casefold() in {pack["id"].casefold(), pack["name"].casefold(), path.stem.casefold()}:
            matches.append((path, pack))
    if not matches:
        raise PackError(f"pack not found: {query}")
    if len(matches) > 1:
        raise PackError(f"pack reference is ambiguous: {query}")
    return matches[0]


def validate_pack(pack: dict[str, Any], inventory: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for lane, model_ref in pack["lanes"].items():
        if not isinstance(lane, str) or not isinstance(model_ref, str):
            errors.append("lane names and model references must be strings")
            continue
        try:
            resolve_model(inventory, model_ref)
        except ModelError as error:
            errors.append(f"{lane}: {error}")
    return errors


def use_pack(pack: dict[str, Any], inventory: dict[str, Any], state_path: Path) -> dict[str, Any]:
    errors = validate_pack(pack, inventory)
    if errors:
        raise PackError("pack is not usable: " + "; ".join(errors))
    default_lane = str(pack.get("default_lane") or next(iter(pack["lanes"])))
    if default_lane not in pack["lanes"]:
        raise PackError(f"default lane is missing: {default_lane}")
    state = read_json(state_path, {})
    state.update({
        "active_pack": pack["id"], "active_lane": default_lane,
        "model_id": pack["lanes"][default_lane], "pack_selected_at": utc_now(),
    })
    atomic_json(state_path, state)
    return state


def route_lane(pack: dict[str, Any], lane: str, inventory: dict[str, Any]) -> dict[str, Any]:
    if lane not in pack["lanes"]:
        raise PackError(f"lane not found in {pack['id']}: {lane}")
    try:
        return resolve_model(inventory, pack["lanes"][lane])
    except ModelError as error:
        raise PackError(str(error)) from error
