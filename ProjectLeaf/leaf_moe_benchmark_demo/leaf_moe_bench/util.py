"""Small dependency-free helpers shared by the MOE-001 demo."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_bytes), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def atomic_write_json(path: Path, value: Any) -> None:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, value: str) -> None:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def read_json(path: Path) -> Any:
    return json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))


def host_summary() -> Dict[str, Any]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "python": platform.python_version(),
    }


def find_workspace_root(start: Optional[Path] = None) -> Optional[Path]:
    current = (start or Path.cwd()).expanduser().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "leafos.root.json").is_file():
            return candidate
    return None


def default_model_root(workspace: Optional[Path] = None) -> Path:
    configured = os.environ.get("LEAF_MODEL_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    root = workspace or find_workspace_root(Path(__file__)) or find_workspace_root()
    if root:
        installer_models = root / "ProjectLeaf" / "leaf_model_installer" / "models"
        if installer_models.is_dir():
            return installer_models.resolve()
    return (Path.home() / ".leaf" / "models").resolve()


def default_catalog_path(workspace: Optional[Path] = None) -> Path:
    root = workspace or find_workspace_root(Path(__file__)) or find_workspace_root()
    if not root:
        raise FileNotFoundError("LeafOS workspace root not found; pass --catalog explicitly")
    return (root / "ProjectLeaf" / "leaf_model_installer" / "leaf_models" / "model_catalog.json").resolve()


def unique_preserving_order(values: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
