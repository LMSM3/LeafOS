from __future__ import annotations

import os
import re
from pathlib import Path, PureWindowsPath
from typing import Any

from core.models.gguf import GGUFError, inspect_gguf
from core.state import atomic_json, read_json, utc_now


class ModelError(ValueError):
    pass


def local_model_path(value: str, platform_name: str | None = None) -> Path:
    platform_name = platform_name or os.name
    if platform_name != "nt" and re.match(r"^[A-Za-z]:[\\/]", value):
        windows = PureWindowsPath(value)
        drive = windows.drive.rstrip(":").lower()
        return Path("/mnt") / drive / Path(*windows.parts[1:])
    if platform_name == "nt":
        match = re.match(r"^/mnt/([A-Za-z])/(.*)$", value)
        if match:
            return Path(f"{match.group(1).upper()}:/{match.group(2)}")
    return Path(value).expanduser()


def scan_model_dirs(model_dirs: tuple[Path, ...], runtime_available: bool) -> dict[str, Any]:
    models: list[dict[str, Any]] = []
    roots: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for root in model_dirs:
        exists = root.is_dir()
        roots.append({"path": str(root), "exists": exists})
        if not exists:
            continue
        for path in sorted(root.rglob("*.gguf")):
            resolved = path.resolve()
            if resolved in seen or not resolved.is_file():
                continue
            seen.add(resolved)
            try:
                models.append(inspect_gguf(resolved, runtime_available))
            except (OSError, GGUFError) as error:
                models.append({
                    "id": resolved.stem,
                    "path": str(resolved),
                    "name": resolved.stem,
                    "size_bytes": resolved.stat().st_size if resolved.exists() else 0,
                    "mtime_ns": resolved.stat().st_mtime_ns if resolved.exists() else None,
                    "quant": "unknown",
                    "architecture": "unknown",
                    "gguf_version": None,
                    "tensor_count": None,
                    "required_size_bytes": None,
                    "runtime_compatible": False,
                    "runtime_compatibility": "unavailable",
                    "load_status": "invalid",
                    "error": str(error),
                })
    usable = sum(1 for model in models if model["runtime_compatible"])
    return {
        "schema": "leafos.model-inventory.v1",
        "scanned_at": utc_now(),
        "roots": roots,
        "models": models,
        "summary": {"found": len(models), "usable": usable, "invalid": len(models) - usable},
    }


def save_inventory(path: Path, inventory: dict[str, Any]) -> None:
    atomic_json(path, inventory)


def load_inventory(path: Path) -> dict[str, Any]:
    value = read_json(path, {})
    if value.get("schema") != "leafos.model-inventory.v1" or not isinstance(value.get("models"), list):
        return {"schema": "leafos.model-inventory.v1", "models": [], "summary": {"found": 0, "usable": 0, "invalid": 0}}
    return value


def resolve_model(inventory: dict[str, Any], query: str, *, require_usable: bool = True) -> dict[str, Any]:
    needle = query.casefold()
    matches = []
    for model in inventory.get("models", []):
        stored_path = Path(model["path"])
        path = local_model_path(model["path"])
        candidates = {
            str(model.get("id", "")).casefold(), str(stored_path).casefold(), str(path).casefold(),
            stored_path.name.casefold(), stored_path.stem.casefold(), path.name.casefold(), path.stem.casefold(),
        }
        if needle in candidates:
            matches.append(model)
    if not matches:
        raise ModelError(f"model not found in scanned inventory: {query}")
    if len(matches) > 1:
        raise ModelError(f"model reference is ambiguous: {query}")
    model = dict(matches[0])
    model["path"] = str(local_model_path(model["path"]).resolve())
    if not Path(model["path"]).is_file():
        raise ModelError(f"model path is missing: {model['path']}")
    if require_usable and not model.get("runtime_compatible"):
        raise ModelError(f"model is not runtime compatible: {model.get('error') or model['path']}")
    return model
