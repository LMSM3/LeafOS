#!/usr/bin/env python3
"""Read-only WO-043 resource gateway for the LeafOS browser surface."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote

MODULE_ROOT = Path(__file__).resolve().parent
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))
from capabilities import catalog as capability_catalog, discover as discover_capabilities
from admission import admit as admit_action

ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = ROOT / "core" / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))
import leaf_live_project as live_projects
import leaf_telemetry as telemetry

RUNS_ROOT = ROOT / "runs" / "agent-loop"
WEB_ROOT = ROOT / "core" / "web" / "app"
RUNTIME_PROFILES = ROOT / "config" / "runtime-profiles.json"
INSTALL_MANIFESTS = (ROOT.parents[1] / "install-manifest.json", ROOT / "install-manifest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except (OSError, json.JSONDecodeError):
        return default


def _safe_id(value: str) -> Optional[str]:
    decoded = unquote(value)
    if not decoded or decoded in {".", ".."} or "/" in decoded or "\\" in decoded:
        return None
    if not decoded[0].isalpha() or any(not (char.isalnum() or char in "._-") for char in decoded):
        return None
    return decoded


def action_route(path: str, body: bytes) -> Optional[Tuple[int, str, bytes]]:
    clean = path.split("?", 1)[0]
    if len(body) > 16384:
        return _json(413, _error("REQUEST_TOO_LARGE"))
    try:
        request = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        value = _error("SCHEMA_INVALID")
        value["message"] = str(exc)
        return _json(400, value)
    if clean == "/api/v1/projects/commands/start":
        return _start_project_action(request)
    prefix = "/api/v1/runs/"
    if not clean.startswith(prefix):
        return None
    command = None
    for suffix, candidate in (("/commands/pause", "pause"), ("/commands/deploy", "deploy")):
        if clean.endswith(suffix):
            command = candidate
            run_id = clean[len(prefix):-len(suffix)]
            break
    if command is None:
        return None
    if _safe_id(run_id) is None:
        return _json(404, _error("RESOURCE_NOT_FOUND"))
    try:
        if command == "deploy":
            return _deploy_action(run_id, request)
        if not isinstance(request, dict) or request.get("target", {}).get("id") != run_id:
            return _json(400, _error("TARGET_MISMATCH"))
        status, value = admit_action(request)
        return _json(status, value)
    except ValueError as exc:
        value = _error("SCHEMA_INVALID")
        value["message"] = str(exc)
        return _json(400, value)


def _deploy_action(run_id: str, request: Any) -> Tuple[int, str, bytes]:
    if not isinstance(request, dict) or set(request) - {"objective"}:
        return _json(400, _error("SCHEMA_INVALID"))
    objective = str(request.get("objective", "")).strip()
    if not 1 <= len(objective) <= 2000:
        return _json(400, _error("SCHEMA_INVALID"))
    run_dir = RUNS_ROOT / run_id
    if run_dir.parent != RUNS_ROOT or not (run_dir / "run.json").is_file():
        return _json(404, _error("RESOURCE_NOT_FOUND"))
    result = live_projects.queue_improvement(run_dir, objective, spawn=True, source="operator")
    return _json(202, {"leafos_object": "leafos.midend_task_disposition", "version": 1, **result})


def _start_project_action(request: Any) -> Tuple[int, str, bytes]:
    allowed = {"mode", "target", "template", "objective", "provider", "approved"}
    if not isinstance(request, dict) or set(request) - allowed:
        return _json(400, _error("SCHEMA_INVALID"))
    mode = str(request.get("mode", ""))
    target = str(request.get("target", "")).strip()
    if mode not in {"existing", "new"} or not target or len(target) > 1024:
        return _json(400, _error("SCHEMA_INVALID"))
    result = live_projects.start_project(
        target, create_seed=mode == "new", template=str(request.get("template", "auto")),
        objective=str(request.get("objective", "")), provider=str(request.get("provider", "required")),
        approved=bool(request.get("approved", False)), spawn=True, resident=True,
    )
    return _json(202, {"leafos_object": "leafos.midend_project_disposition", "version": 1, **result})


def _run_files() -> List[Path]:
    if not RUNS_ROOT.is_dir():
        return []
    return sorted(RUNS_ROOT.glob("*/run.json"), key=lambda item: item.stat().st_mtime, reverse=True)


def _run_summary(run_file: Path) -> Dict[str, Any]:
    run = _read_json(run_file, {})
    run_id = str(run.get("run_id") or run_file.parent.name)
    target = str(run.get("target") or run.get("project_root") or "")
    return {
        "id": run_id,
        "version": int(run.get("version") or 0),
        "state": str(run.get("state") or run.get("status") or "unknown"),
        "target": target,
        "mode": str(run.get("mode") or ""),
        "updated_at": datetime.fromtimestamp(run_file.stat().st_mtime, timezone.utc).isoformat(),
        "links": {"self": f"/api/v1/runs/{run_id}", "page": f"/runs/{run_id}"},
    }


def _collection(resource_type: str, values: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "leafos_object": "leafos.midend_collection",
        "version": 1,
        "resource_type": resource_type,
        "generated_at": _utc_now(),
        "items": values,
        "count": len(values),
        "read_only": True,
    }


def list_tasks() -> Dict[str, Any]:
    values: List[Dict[str, Any]] = []
    for run_file in _run_files():
        run_id = str(_read_json(run_file, {}).get("run_id") or run_file.parent.name)
        queue = _read_json(run_file.parent / "queue.json", {})
        for task in queue.get("tasks", []) if isinstance(queue, dict) else []:
            if not isinstance(task, dict):
                continue
            values.append({
                "id": str(task.get("task_id") or "unknown"),
                "run_id": run_id,
                "kind": str(task.get("kind") or ""),
                "objective": str(task.get("objective") or ""),
                "status": str(task.get("status") or "unknown"),
                "attempts": int(task.get("attempts") or 0),
                "dependencies": sorted(str(value) for value in task.get("dependencies", [])),
            })
    values.sort(key=lambda item: (item["run_id"], item["id"]))
    return _collection("task", values)


def list_reports() -> Dict[str, Any]:
    values: List[Dict[str, Any]] = []
    for run_file in _run_files():
        report = run_file.parent / "report.md"
        if not report.is_file():
            continue
        run_id = str(_read_json(run_file, {}).get("run_id") or run_file.parent.name)
        values.append({
            "id": f"report-{run_id}",
            "run_id": run_id,
            "media_type": "text/markdown",
            "size_bytes": report.stat().st_size,
            "updated_at": datetime.fromtimestamp(report.stat().st_mtime, timezone.utc).isoformat(),
            "evidence_ref": f"evidence://runs/{run_id}/report.md",
        })
    values.sort(key=lambda item: item["updated_at"], reverse=True)
    return _collection("report", values)


def list_profiles() -> Dict[str, Any]:
    document = _read_json(RUNTIME_PROFILES, {})
    profiles = document.get("profiles", {}) if isinstance(document, dict) else {}
    values = [dict({"id": key}, **value) for key, value in sorted(profiles.items()) if isinstance(value, dict)]
    return _collection("profile", values)


def list_install_plans() -> Dict[str, Any]:
    values: List[Dict[str, Any]] = []
    for manifest in INSTALL_MANIFESTS:
        if not manifest.is_file():
            continue
        value = _read_json(manifest, {})
        if not isinstance(value, dict):
            continue
        values.append({
            "id": manifest.parent.name or "leafos",
            "schema": value.get("schema"),
            "installed_at": value.get("installed_at"),
            "prefix": value.get("prefix"),
            "file_count": len(value.get("files", [])) if isinstance(value.get("files"), list) else 0,
            "status": "installed",
        })
    values.sort(key=lambda item: item["id"])
    return _collection("install_plan", values)


def list_runs() -> Dict[str, Any]:
    values = [_run_summary(path) for path in _run_files()]
    return {
        "leafos_object": "leafos.midend_collection",
        "version": 1,
        "resource_type": "run",
        "generated_at": _utc_now(),
        "items": values,
        "count": len(values),
        "read_only": True,
    }


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    safe = _safe_id(run_id)
    if safe is None:
        return None
    run_dir = RUNS_ROOT / safe
    run_file = run_dir / "run.json"
    if not run_file.is_file():
        return None
    run = _read_json(run_file, {})
    summary = _run_summary(run_file)
    evidence_refs = []
    for name in ("checkpoint.json", "report.md", "universal-run-log.jsonl", "events.jsonl"):
        if (run_dir / name).is_file():
            evidence_refs.append(f"evidence://runs/{safe}/{name}")
    return {
        "leafos_object": "leafos.midend_resource",
        "version": 1,
        "resource": {"type": "run", "id": safe, "version": summary["version"]},
        "projection": {"summary": summary, "run": run},
        "capabilities": discover_capabilities(
            "run", safe, summary["version"], summary["state"],
            {"checkpoint_available": (run_dir / "checkpoint.json").is_file()},
        )["capabilities"],
        "evidence_refs": evidence_refs,
        "freshness": {
            "generated_at": _utc_now(),
            "source_cursor": f"run:{safe}:{summary['version']}",
            "degraded": False,
            "reason": None,
        },
    }


def list_projects() -> Dict[str, Any]:
    projects: Dict[str, Dict[str, Any]] = {}
    for run_file in _run_files():
        summary = _run_summary(run_file)
        target = summary["target"]
        if not target:
            continue
        key = Path(target).name or target
        current = projects.get(key)
        if current is None:
            projects[key] = {
                "id": key,
                "name": key,
                "target": target,
                "run_count": 1,
                "latest_run": summary["id"],
                "latest_state": summary["state"],
            }
        else:
            current["run_count"] += 1
    values = sorted(projects.values(), key=lambda item: item["name"].lower())
    return {
        "leafos_object": "leafos.midend_collection",
        "version": 1,
        "resource_type": "project",
        "generated_at": _utc_now(),
        "items": values,
        "count": len(values),
        "read_only": True,
    }


def route(path: str) -> Optional[Tuple[int, str, bytes]]:
    clean = path.split("?", 1)[0]
    if clean in {"/", "/index.html"}:
        file_path = WEB_ROOT / "index.html"
        if file_path.is_file():
            return 200, "text/html; charset=utf-8", file_path.read_bytes()
        return None
    if clean == "/app.js":
        return _static("app.js", "text/javascript; charset=utf-8")
    if clean == "/app.css":
        return _static("app.css", "text/css; charset=utf-8")
    if clean == "/favicon.ico":
        return _static("favicon.ico", "image/x-icon")
    if clean == "/api/v1":
        return _json(200, {
            "leafos_object": "leafos.midend_index", "version": 1, "read_only": True,
            "resources": {
                "projects": "/api/v1/projects", "runs": "/api/v1/runs",
                "tasks": "/api/v1/tasks", "reports": "/api/v1/reports",
                "profiles": "/api/v1/profiles", "install_plans": "/api/v1/install-plans",
                "capabilities": "/api/v1/capabilities",
            },
            "mutations": "unavailable until WO-044 native admission",
        })
    if clean == "/api/v1/projects":
        return _json(200, list_projects())
    if clean == "/api/v1/runs":
        return _json(200, list_runs())
    if clean == "/api/v1/tasks":
        return _json(200, list_tasks())
    if clean == "/api/v1/reports":
        return _json(200, list_reports())
    if clean == "/api/v1/profiles":
        return _json(200, list_profiles())
    if clean == "/api/v1/install-plans":
        return _json(200, list_install_plans())
    if clean == "/api/v1/capabilities":
        return _json(200, capability_catalog())
    if clean == "/api/v1/hardware":
        return _json(200, {
            "leafos_object": "leafos.hardware_snapshot", "version": 1,
            "generated_at": _utc_now(), **telemetry.collect_fast_hardware(),
        })
    prefix = "/api/v1/runs/"
    if clean.startswith(prefix):
        tail = clean[len(prefix):]
        suffix = "/capabilities"
        if tail.endswith(suffix):
            run_id = tail[:-len(suffix)]
            value = get_run(run_id)
            if value is None:
                return _json(404, _error("RESOURCE_NOT_FOUND"))
            resource = value["resource"]
            summary = value["projection"]["summary"]
            facts = {"checkpoint_available": any(ref.endswith("checkpoint.json") for ref in value["evidence_refs"])}
            return _json(200, discover_capabilities("run", resource["id"], resource["version"], summary["state"], facts))
        value = get_run(tail)
        return _json(200, value) if value is not None else _json(404, _error("RESOURCE_NOT_FOUND"))
    return None


def _static(name: str, content_type: str) -> Optional[Tuple[int, str, bytes]]:
    path = WEB_ROOT / name
    return (200, content_type, path.read_bytes()) if path.is_file() else None


def _json(status: int, payload: Dict[str, Any]) -> Tuple[int, str, bytes]:
    return status, "application/json; charset=utf-8", (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _error(code: str) -> Dict[str, Any]:
    return {"leafos_object": "leafos.midend_error", "version": 1, "code": code, "read_only": True}
