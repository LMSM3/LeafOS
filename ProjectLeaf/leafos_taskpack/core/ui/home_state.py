#!/usr/bin/env python3
"""Build the read-only LeafOS operator home state contract."""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from accelerator_state import build_state as build_accelerator_state


ROOT = Path(__file__).resolve().parents[2]
PYTHON_DIR = ROOT / "core" / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from leaf_economics import load_operator_config, summarize_benchmark  # noqa: E402


def _json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _stack(root: Path) -> dict[str, Any]:
    candidates = [root.parent / "leaf_model_installer" / "models", Path.home() / ".leaf" / "models"]
    model_root = next((path for path in candidates if path.is_dir()), candidates[0])
    files = sorted(model_root.rglob("*.gguf")) if model_root.is_dir() else []
    return {
        "definition": "all downloaded and locally available models within this instance",
        "root": str(model_root), "model_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "models": [{"name": path.name, "path": str(path), "bytes": path.stat().st_size} for path in files],
    }


def _work_order(root: Path) -> dict[str, Any]:
    files = list((root / "docs" / "work-orders").glob("WO-*.md")) + list((root / "docs").glob("WO-*.md"))
    items = []
    for path in files:
        match = re.match(r"WO-(\d+)", path.name)
        if match:
            text = path.read_text(encoding="utf-8", errors="replace")
            state = "DONE" if "[I] DONE" in text else "ACTIVE" if "[I] ACTIVE" in text else "PLANNED"
            items.append((int(match.group(1)), path.name, state, path))
    active = next((item for item in sorted(items, reverse=True) if item[2] == "ACTIVE"), None)
    selected = active or (max(items) if items else None)
    return {
        "id": f"WO-{selected[0]:03d}" if selected else None,
        "document": str(selected[3]) if selected else None,
        "state": selected[2] if selected else "missing",
    }


def _runs(root: Path) -> list[dict[str, Any]]:
    run_root = root / "runs"
    directories = sorted(
        (path for path in run_root.iterdir() if path.is_dir() and path.name != "latest"),
        key=lambda path: path.stat().st_mtime, reverse=True,
    ) if run_root.is_dir() else []
    return [
        {"name": path.name, "path": str(path), "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()}
        for path in directories[:5]
    ]


def _benchmark(root: Path, economics: dict[str, Any]) -> dict[str, Any]:
    benchmark_root = root / "reports" / "inference-benchmark"
    reports = list(benchmark_root.rglob("report.json")) if benchmark_root.is_dir() else []
    if not reports:
        return {
            "status": "not_run", "benchmark_id": None, "report": None,
            "completed_cells": 0, "planned_cells": 0, "comparison": economics,
            "measured": None, "best_generation": None,
        }
    path = max(reports, key=lambda item: item.stat().st_mtime)
    report = _json(path, {})
    summary = summarize_benchmark(report, economics)
    summary["report"] = str(path)
    return summary


def _canonical_root(root: Path) -> Path | None:
    candidate = root.parent.parent
    if root.name == "leafos_taskpack" and root.parent.name == "ProjectLeaf":
        return candidate
    return None


def _caller_path(path: Path) -> str:
    caller_shell = os.environ.get("LEAF_CALLER_SHELL", "").lower()
    if os.name == "nt" and caller_shell in {"bash", "wsl"} and path.drive:
        drive = path.drive.rstrip(":").lower()
        suffix = path.as_posix()[2:].lstrip("/")
        prefix = f"/mnt/{drive}" if caller_shell == "wsl" else f"/{drive}"
        return f"{prefix}/{suffix}" if suffix else prefix
    return str(path)


def _quoted_caller_path(path: Path) -> str:
    value = _caller_path(path)
    caller_shell = os.environ.get("LEAF_CALLER_SHELL", "").lower()
    if os.name == "nt" and caller_shell not in {"bash", "wsl"}:
        return f"'{value.replace(chr(39), chr(39) * 2)}'"
    return shlex.quote(value)


def _operator_cli(root: Path, surface_name: str) -> str:
    canonical_root = _canonical_root(root)
    if canonical_root is not None:
        caller_shell = os.environ.get("LEAF_CALLER_SHELL", "").lower()
        if caller_shell in {"bash", "wsl"}:
            launcher = canonical_root / "leafos.sh"
            if launcher.is_file():
                return f"bash {shlex.quote(_caller_path(launcher))}"
        elif os.name == "nt":
            launcher = canonical_root / "leafos.ps1"
            if launcher.is_file():
                return f"& '{str(launcher).replace(chr(39), chr(39) * 2)}'"
        else:
            launcher = canonical_root / "leafos.sh"
            if launcher.is_file():
                return f"bash {shlex.quote(str(launcher))}"
    if surface_name == "FlowerOS":
        return ".\\bin\\flower.ps1" if os.name == "nt" else "./bin/flowerctl"
    return "leafctl"


def _primary_reference(root: Path) -> dict[str, Any]:
    canonical_root = _canonical_root(root)
    if canonical_root is None:
        return {"status": "not_registered", "markdown": None, "tex": None}
    metadata = _json(canonical_root / "leafos.root.json", {})
    documentation = metadata.get("documentation", {}) if isinstance(metadata, dict) else {}
    markdown_value = documentation.get("primary_reference")
    tex_value = documentation.get("primary_reference_tex")
    markdown = canonical_root / markdown_value if isinstance(markdown_value, str) else None
    tex = canonical_root / tex_value if isinstance(tex_value, str) else None
    available = bool(markdown and markdown.is_file())
    tex_available = bool(tex and tex.is_file())
    status = "available" if available and tex_available else "partial" if available or tex_available else "missing"
    return {
        "status": status,
        "markdown": _caller_path(markdown) if markdown else None,
        "tex": _caller_path(tex) if tex else None,
    }


def build_state(root: Path = ROOT, health_timeout: float = 0.25) -> dict[str, Any]:
    required = ["bin", "core", "config", "docs", "tests"]
    missing = [name for name in required if not (root / name).is_dir()]
    accelerator = build_accelerator_state(root, timeout=health_timeout)
    runtime = _json(root / "config" / "runtime.json", {}).get("leafos_runtime", {})
    operator = load_operator_config(root)
    benchmark = _benchmark(root, operator["economics"])
    cli = _operator_cli(root, operator["surface"]["name"])

    def operator_command(command: str) -> str:
        return f"{cli} {command.removeprefix('leafctl ')}"
    recent_runs = _runs(root)
    work_order = _work_order(root)
    next_actions = []
    if accelerator["provider"]["health"] != "ok":
        next_actions.append({"label": "Check local provider", "command": operator_command(accelerator["safe_start_command"]), "safe": True})
    else:
        next_actions.append({"label": "Open local chat", "command": operator_command("leafctl chat"), "safe": True})
    next_actions.append({"label": "Inspect latest run", "command": operator_command("leafctl trace latest"), "safe": True})
    if benchmark["status"] in {"not_run", "blocked_busy", "partial", "failed"}:
        manifest = _quoted_caller_path(root / "config" / "inference-benchmark-matrix.json")
        next_actions.append({
            "label": "Check clean inference benchmark",
            "command": operator_command(f"leafctl realbench matrix --manifest {manifest} --dry-run"),
            "safe": True,
        })
    return {
        "leafos_object": "home_state", "version": "0.8.0-A",
        "generated_at": datetime.now(timezone.utc).isoformat(), "root": str(root),
        "operator": operator["surface"],
        "readiness": {"status": "ok" if not missing else "fail", "missing": missing, "python": sys.version.split()[0]},
        "provider": accelerator["provider"], "accelerator": accelerator,
        "stack": _stack(root), "runtime": {"defaults": runtime.get("defaults", {}), "mode": runtime.get("defaults", {}).get("mode")},
        "gpu": {"backend": accelerator["backend"], "available": accelerator["gpu_available"], "state": accelerator["state"]},
        "work_order": work_order,
        "benchmark": benchmark,
        "reference": _primary_reference(root),
        "task_loop": {"latest_run": recent_runs[0] if recent_runs else None},
        "recent_runs": recent_runs, "next_actions": next_actions,
    }
