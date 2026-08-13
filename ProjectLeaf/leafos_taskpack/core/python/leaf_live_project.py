#!/usr/bin/env python3
"""Minimal project inlet for the interactive LeafOS live stack."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PYTHON_DIR = Path(__file__).resolve().parent
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import leaf_agent_loop as engine  # noqa: E402
import leaf_loop_inlet as inlet  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
IGNORED_PARTS = {
    ".git", ".hg", ".svn", ".idea", ".vs", ".vscode", "__pycache__",
    "node_modules", "dist", "build", ".venv", "venv", "runs",
}
SOURCE_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cs", ".go", ".h", ".hpp", ".html", ".java",
    ".js", ".jsx", ".lua", ".php", ".ps1", ".py", ".rb", ".rs", ".sh",
    ".ts", ".tsx",
}
LANGUAGES = {
    ".c": "C", ".cc": "C++", ".cpp": "C++", ".cs": "C#", ".go": "Go",
    ".java": "Java", ".js": "JavaScript", ".jsx": "JavaScript", ".lua": "Lua",
    ".php": "PHP", ".ps1": "PowerShell", ".py": "Python", ".rb": "Ruby",
    ".rs": "Rust", ".sh": "Shell", ".ts": "TypeScript", ".tsx": "TypeScript",
}
MANIFEST_NAMES = ("leafos.project.json", "project.json", "project_state.json")
README_NAMES = ("README.md", "README.txt", "readme.md", "readme.txt")
MAX_INVENTORY_FILES = 4000
MAX_COMMAND_CHARS = 512
MAX_ONBOARDING_DOCUMENT_CHARS = 65_536
MAX_ONBOARDING_TARGET_CHARS = 1_024
ONBOARDING_OBJECT = "leafos.project_onboarding_request"
SANDBOX_PROFILES = {"project-only"}
KV_CACHE_PREFERENCES = {"inherit", "investigate", "enable", "disable"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _bounded_files(target: Path) -> tuple[list[Path], bool]:
    files: list[Path] = []
    truncated = False
    for root, directories, names in os.walk(target):
        directories[:] = sorted(name for name in directories if name.lower() not in IGNORED_PARTS)
        for name in sorted(names):
            files.append(Path(root) / name)
            if len(files) >= MAX_INVENTORY_FILES:
                truncated = True
                return files, truncated
    return files, truncated


def _manifest(target: Path, files: list[Path]) -> tuple[Path | None, dict[str, Any]]:
    for name in MANIFEST_NAMES:
        candidate = target / name
        if candidate.is_file():
            value = _safe_read_json(candidate)
            if value:
                return candidate, value
    for candidate in files:
        if (
            candidate.suffix.lower() != ".json" or candidate.stat().st_size > 256_000
            or (candidate.parent != target and len(files) > 10)
        ):
            continue
        value = _safe_read_json(candidate)
        if any(key in value for key in ("objective", "intent", "acceptance", "improvement_goals")):
            return candidate, value
    return None, {}


def _string_list(value: Any, *, limit: int = 32) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value[:limit] if isinstance(item, str) and item.strip()]


def _command_list(value: Any) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    commands: list[list[str]] = []
    for command in value[:16]:
        if isinstance(command, list) and command and all(isinstance(part, str) and part for part in command):
            commands.append(list(command))
    return commands


def _declared_paths(value: Any) -> list[str]:
    paths = _string_list(value, limit=64)
    for path in paths:
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts or "\x00" in path:
            return []
    return paths


def _infer_commands(target: Path, relative_files: set[str], manifest: dict[str, Any]) -> list[list[str]]:
    validation = manifest.get("validation", {}) if isinstance(manifest.get("validation"), dict) else {}
    declared = _command_list(validation.get("commands") or manifest.get("validation_commands"))
    if declared:
        return declared
    if "run_tests.ps1" in relative_files and os.name == "nt":
        return [["pwsh", "-NoProfile", "-File", "run_tests.ps1"]]
    if "run_tests.sh" in relative_files:
        return [["bash", "run_tests.sh"]]
    if any(path.startswith("tests/") and path.endswith(".py") for path in relative_files):
        return [[sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"]]
    return []


def inspect_project(target_value: str | Path) -> dict[str, Any]:
    target = Path(target_value).expanduser().resolve(strict=True)
    if not target.is_dir():
        raise ValueError(f"project target is not a directory: {target}")
    files, truncated = _bounded_files(target)
    relative = [str(path.relative_to(target)).replace("\\", "/") for path in files]
    relative_set = set(relative)
    manifest_path, manifest = _manifest(target, files)
    readme_path = next((target / name for name in README_NAMES if (target / name).is_file()), None)
    skeleton_paths = [path for path in files if "skeleton" in path.name.lower()]
    source_files = [path for path in files if path.suffix.lower() in SOURCE_SUFFIXES]
    test_files = [path for path in files if "tests" in {part.lower() for part in path.relative_to(target).parts}]
    languages = Counter(LANGUAGES[path.suffix.lower()] for path in source_files if path.suffix.lower() in LANGUAGES)
    seed_inputs = bool(readme_path and manifest_path and skeleton_paths)
    if not files:
        state = "empty"
    elif seed_inputs and len(source_files) == 0:
        state = "seed"
    elif source_files:
        state = "codebase"
    else:
        state = "documents"
    allowed_paths = _declared_paths(manifest.get("allowed_paths")) or ["."]
    acceptance = _string_list(manifest.get("acceptance")) or [
        "One coherent improvement is implemented within the declared project boundary.",
        "Existing behavior is preserved unless the project intent explicitly changes it.",
        "Deterministic validation or a clear validation artifact covers the increment.",
        "The completion report identifies changed files, evidence, and the next opportunity.",
    ]
    commands = _infer_commands(target, relative_set, manifest)
    return {
        "leafos_object": "leafos.live_project_inventory",
        "version": 1,
        "target": str(target),
        "name": str(manifest.get("project") or target.name),
        "state": state,
        "file_count": len(files),
        "inventory_truncated": truncated,
        "source_file_count": len(source_files),
        "test_file_count": len(test_files),
        "languages": dict(sorted(languages.items())),
        "readme": str(readme_path.relative_to(target)).replace("\\", "/") if readme_path else "",
        "manifest": str(manifest_path.relative_to(target)).replace("\\", "/") if manifest_path else "",
        "skeletons": [str(path.relative_to(target)).replace("\\", "/") for path in skeleton_paths[:16]],
        "allowed_paths": allowed_paths,
        "denied_paths": _string_list(manifest.get("denied_paths"), limit=64) or [".git", ".env", "secrets", "credentials"],
        "acceptance": acceptance,
        "constraints": _string_list(manifest.get("constraints")),
        "commands": commands,
        "intent": manifest,
    }


def _seed_content(template: str, name: str) -> dict[str, str]:
    if template not in {"generic", "auto"}:
        raise ValueError(f"unsupported seed template: {template}")
    readme = f"""# {name}

This project is intentionally minimal. LeafOS should inspect the current state, choose one bounded improvement, implement it, validate it, and leave the next iteration clearer than it found it.
"""
    skeleton = """# Project Skeleton

- Add the smallest coherent source boundary needed for the current objective.
- Add deterministic validation alongside behavior.
- Keep generated artifacts and reports separate from source.
- Prefer repeated bounded improvements over one oversized rewrite.
"""
    objective = "Turn this seed into a useful, tested project through repeated bounded improvements."
    goals = ["working baseline", "deterministic validation", "incremental complexity", "clear operator evidence"]
    manifest = {
        "leafos_object": "leafos.live_project",
        "version": 1,
        "project": name,
        "template": template,
        "objective": objective,
        "improvement_goals": goals,
        "allowed_paths": ["."],
        "denied_paths": [".git", ".env", "secrets", "credentials"],
        "constraints": [
            "Work only inside the project directory.",
            "Use the local stack for proposals and CPU policy for execution and validation.",
            "Implement one coherent increment per queued improvement.",
        ],
        "acceptance": [
            "The project remains runnable or gains a runnable baseline.",
            "Deterministic tests cover the new behavior.",
            "The iteration records evidence and identifies a next improvement.",
        ],
        "validation": {"commands": [[sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"]]},
    }
    return {
        "README.md": readme,
        "skeleton.md": skeleton,
        "leafos.project.json": json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
    }


def _onboarding_document(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in normalized or len(normalized) > MAX_ONBOARDING_DOCUMENT_CHARS:
        raise ValueError(f"{label} must contain 1-{MAX_ONBOARDING_DOCUMENT_CHARS} safe characters")
    if not normalized.strip():
        raise ValueError(f"{label} must not be empty")
    return normalized if normalized.endswith("\n") else normalized + "\n"


def validate_onboarding_request(value: Any) -> dict[str, Any]:
    """Normalize the sole backend contract used by interactive project onboarding."""
    if not isinstance(value, dict):
        raise ValueError("project onboarding request must be a JSON object")
    try:
        version = int(value.get("version", 1))
    except (TypeError, ValueError) as error:
        raise ValueError("unsupported project onboarding request") from error
    if value.get("leafos_object", ONBOARDING_OBJECT) != ONBOARDING_OBJECT or version != 1:
        raise ValueError("unsupported project onboarding request")
    mode = str(value.get("mode", "")).strip().lower()
    if mode not in {"new", "existing"}:
        raise ValueError("project onboarding mode must be new or existing")
    target_text = str(value.get("target", "")).strip()
    if not target_text or len(target_text) > MAX_ONBOARDING_TARGET_CHARS or "\x00" in target_text:
        raise ValueError(f"project target must contain 1-{MAX_ONBOARDING_TARGET_CHARS} safe characters")
    target = Path(target_text).expanduser().resolve()
    workspace_root_text = str(value.get("workspace_root", "")).strip()
    project_name = str(value.get("project_name", "")).strip()
    if mode == "new":
        if not workspace_root_text:
            workspace_root_text = str(target.parent)
        if not project_name:
            project_name = target.name
        if (
            project_name in {".", ".."} or len(project_name) > 80
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]*", project_name)
        ):
            raise ValueError("project name must be 1-80 safe filename characters")
        workspace_root = Path(workspace_root_text).expanduser().resolve()
        located_target = (workspace_root / project_name).resolve()
        if located_target != target:
            raise ValueError("project target must equal workspace_root joined with project_name")
    else:
        workspace_root = target.parent
        project_name = target.name
    template = str(value.get("template", "auto")).strip().lower()
    if template not in {"auto", "generic"}:
        raise ValueError("project template must be auto or generic")
    provider = str(value.get("provider", "required")).strip().lower()
    if provider not in {"required", "auto", "off"}:
        raise ValueError("project provider must be required, auto, or off")
    resident_mode = str(value.get("resident_mode", "auto")).strip().lower()
    if resident_mode not in {"auto", "quiet", "full"}:
        raise ValueError("resident mode must be auto, quiet, or full")
    objective = str(value.get("objective", "")).strip()
    if len(objective) > 2000 or "\x00" in objective:
        raise ValueError("project objective must contain at most 2000 safe characters")
    budget = value.get("budget_minutes")
    if budget is not None:
        if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= 10_080:
            raise ValueError("resident budget must be an integer from 1 to 10080 minutes")
    sandbox_profile = str(value.get("sandbox_profile", "project-only")).strip().lower()
    if sandbox_profile not in SANDBOX_PROFILES:
        raise ValueError("sandbox profile currently supports only project-only")
    optimizations = value.get("model_optimizations", {})
    if not isinstance(optimizations, dict):
        raise ValueError("model_optimizations must be an object")
    unknown_optimizations = sorted(set(optimizations) - {"kv_cache"})
    if unknown_optimizations:
        raise ValueError("unknown model optimizations: " + ", ".join(unknown_optimizations))
    kv_cache = str(optimizations.get("kv_cache", "inherit")).strip().lower()
    if kv_cache not in KV_CACHE_PREFERENCES:
        raise ValueError("KV-cache preference must be inherit, investigate, enable, or disable")
    normalized = {
        "leafos_object": ONBOARDING_OBJECT,
        "version": 1,
        "mode": mode,
        "target": str(target),
        "workspace_root": str(workspace_root),
        "project_name": project_name,
        "template": template,
        "readme": "",
        "skeleton": "",
        "objective": objective,
        "provider": provider,
        "approved": bool(value.get("approved", False)),
        "resident": bool(value.get("resident", True)),
        "resident_mode": resident_mode,
        "budget_minutes": budget,
        "spawn": bool(value.get("spawn", True)),
        "sandbox_profile": sandbox_profile,
        "model_optimizations": {"kv_cache": kv_cache},
    }
    if mode == "new":
        normalized["readme"] = _onboarding_document(value.get("readme", ""), "README")
        normalized["skeleton"] = _onboarding_document(value.get("skeleton", ""), "skeleton")
    elif value.get("readme") or value.get("skeleton"):
        raise ValueError("existing-project onboarding does not write README or skeleton content")
    return normalized


def preview_project_onboarding(value: Any) -> dict[str, Any]:
    request = validate_onboarding_request(value)
    target = Path(request["target"])
    if request["mode"] == "existing":
        inventory = inspect_project(target)
        return {
            "leafos_object": "leafos.project_onboarding_preview",
            "version": 1,
            "mode": "existing",
            "target": str(target),
            "workspace_root": request["workspace_root"],
            "project_name": request["project_name"],
            "sandbox_profile": request["sandbox_profile"],
            "model_optimizations": request["model_optimizations"],
            "can_apply": True,
            "files_to_create": [],
            "inventory": inventory,
        }
    if target.exists() and not target.is_dir():
        raise ValueError(f"new project target is not a directory: {target}")
    conflicts = [name for name in ("README.md", "skeleton.md", "leafos.project.json") if (target / name).exists()]
    selected_template = "generic"
    return {
        "leafos_object": "leafos.project_onboarding_preview",
        "version": 1,
        "mode": "new",
        "target": str(target),
        "workspace_root": request["workspace_root"],
        "project_name": request["project_name"],
        "template": selected_template,
        "sandbox_profile": request["sandbox_profile"],
        "model_optimizations": request["model_optimizations"],
        "can_apply": not conflicts,
        "conflicts": conflicts,
        "files_to_create": ["README.md", "skeleton.md", "leafos.project.json"],
        "content": {
            "readme_characters": len(request["readme"]),
            "skeleton_characters": len(request["skeleton"]),
        },
    }


def recent_project_targets(limit: int = 8) -> list[str]:
    """Return unique project targets ordered by their most recently updated run."""
    matches: list[tuple[float, str]] = []
    if inlet.RUNS_ROOT.is_dir():
        for run_file in inlet.RUNS_ROOT.glob("*/run.json"):
            run = engine.read_json(run_file, {})
            target = str(run.get("target", "")).strip()
            if target:
                matches.append((run_file.stat().st_mtime, str(Path(target).expanduser().resolve())))
    result: list[str] = []
    for _, target in sorted(matches, reverse=True):
        if target not in result:
            result.append(target)
        if len(result) >= max(1, min(limit, 20)):
            break
    return result


def initialize_project_from_inputs(
    target_value: str | Path,
    *,
    readme: str,
    skeleton: str,
    template: str = "auto",
    objective: str = "",
    sandbox_profile: str = "project-only",
    model_optimizations: dict[str, str] | None = None,
) -> list[str]:
    """Create the three authoritative seed files without replacing operator content."""
    target = Path(target_value).expanduser().resolve()
    request = validate_onboarding_request({
        "mode": "new", "target": str(target), "template": template,
        "readme": readme, "skeleton": skeleton, "objective": objective,
        "sandbox_profile": sandbox_profile, "model_optimizations": model_optimizations or {},
    })
    preview = preview_project_onboarding(request)
    if not preview["can_apply"]:
        raise ValueError("project onboarding will not overwrite: " + ", ".join(preview["conflicts"]))
    target.mkdir(parents=True, exist_ok=True)
    selected_template = preview["template"]
    files = _seed_content(selected_template, target.name or "LeafOS Project")
    manifest = json.loads(files["leafos.project.json"])
    manifest["source"] = "operator_onboarding"
    manifest["sandbox_profile"] = request["sandbox_profile"]
    manifest["model_optimizations"] = request["model_optimizations"]
    if request["objective"]:
        manifest["objective"] = request["objective"]
    files["README.md"] = request["readme"]
    files["skeleton.md"] = request["skeleton"]
    files["leafos.project.json"] = json.dumps(manifest, indent=2, ensure_ascii=True) + "\n"
    written: list[Path] = []
    try:
        for name, content in files.items():
            path = target / name
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
            written.append(path)
    except OSError:
        for path in reversed(written):
            path.unlink(missing_ok=True)
        raise
    return [str(path) for path in written]


def apply_project_onboarding(value: Any, *, run_dir: str = "") -> dict[str, Any]:
    request = validate_onboarding_request(value)
    preview = preview_project_onboarding(request)
    if not preview["can_apply"]:
        raise ValueError("project onboarding cannot continue because seed files already exist")
    written: list[str] = []
    if request["mode"] == "new":
        written = initialize_project_from_inputs(
            request["target"], readme=request["readme"], skeleton=request["skeleton"],
            template=request["template"], objective=request["objective"],
            sandbox_profile=request["sandbox_profile"], model_optimizations=request["model_optimizations"],
        )
    result = start_project(
        request["target"], objective=request["objective"], provider=request["provider"],
        approved=request["approved"], fresh_run=request["mode"] == "new",
        spawn=False, resident=request["resident"], resident_mode=request["resident_mode"],
        budget_minutes=request["budget_minutes"], run_dir=run_dir,
    )
    result["seed_files"] = written
    result["onboarding"] = {key: preview[key] for key in preview if key != "inventory"}
    preferences = {
        "leafos_object": "leafos.stack_preferences",
        "version": 1,
        "sandbox_profile": request["sandbox_profile"],
        "model_optimizations": request["model_optimizations"],
        "application": {"status": "inherited", "task_id": None, "applied": False},
    }
    kv_cache = request["model_optimizations"]["kv_cache"]
    if kv_cache != "inherit":
        preferences["application"]["status"] = "pending_queue"
    preferences_path = Path(result["run_dir"]) / "stack-preferences.json"
    engine.write_json(preferences_path, preferences)
    if kv_cache != "inherit":
        queue = engine.read_json(Path(result["run_dir"]) / "queue.json", {})
        report_tasks = [task for task in queue.get("tasks", []) if task.get("kind") == "report"]
        dependencies = [str(report_tasks[-1]["task_id"])] if report_tasks else []
        direction = {
            "investigate": "investigate the safest useful KV-cache configuration",
            "enable": "implement an explicit KV-cache enable path",
            "disable": "implement an explicit KV-cache disable path",
        }[kv_cache]
        optimization = queue_improvement(
            result["run_dir"],
            "High-value stack optimization: " + direction + ". First detect whether this project owns a llama.cpp or local-model launch surface. "
            "If it does not, do not fabricate a toggle; record a precise integration recommendation instead. Preserve current behavior until deterministic validation, "
            "include rollback, and capture throughput and VRAM evidence where the provider can be exercised.",
            spawn=False, source="operator", priority=1, dependencies=dependencies,
            metadata={"model_optimization": "kv_cache", "requested_mode": kv_cache, "applied": False},
        )
        preferences["application"].update(status="queued", task_id=optimization["task"]["task_id"])
        engine.write_json(preferences_path, preferences)
        result["optimization_task"] = optimization["task"]
    else:
        result["optimization_task"] = None
    run = engine.read_json(Path(result["run_dir"]) / "run.json", {})
    run["onboarding_preferences"] = {
        "sandbox_profile": request["sandbox_profile"],
        "model_optimizations": request["model_optimizations"],
        "preferences_file": str(preferences_path),
    }
    engine.write_json(Path(result["run_dir"]) / "run.json", run)
    engine.append_event(
        Path(result["run_dir"]), "project.onboarded", mode=request["mode"],
        seed_files=[Path(path).name for path in written], operator_documents=bool(written),
        sandbox_profile=request["sandbox_profile"], kv_cache=kv_cache,
    )
    if request["spawn"]:
        active_run = Path(result["run_dir"])
        if request["resident"]:
            import leaf_resident_supervisor as resident_supervisor

            resident_supervisor.initialize_resident(
                active_run, mode=request["resident_mode"], budget_minutes=request["budget_minutes"],
            )
            result["resident_pid"] = resident_supervisor.ensure_supervisor(active_run)
        else:
            lease = engine.read_json(active_run / "worker.lock", {})
            result["worker_pid"] = (
                int(lease.get("pid", 0)) if inlet._pid_alive(int(lease.get("pid", 0)))
                else inlet.spawn_worker(active_run, 1.0)
            )
    return result


def initialize_seed(target_value: str | Path, template: str = "auto") -> list[str]:
    target = Path(target_value).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    if not target.is_dir():
        raise ValueError(f"seed target is not a directory: {target}")
    requested = template.lower()
    template = "generic" if requested in {"auto", "generic"} else requested
    files = _seed_content(template, target.name or "LeafOS Project")
    conflicts = [name for name in files if (target / name).exists()]
    if conflicts:
        raise ValueError("seed initialization will not overwrite: " + ", ".join(conflicts))
    written: list[str] = []
    for name, content in files.items():
        path = target / name
        path.write_text(content, encoding="utf-8")
        written.append(str(path))
    return written


def _project_iterations(target: Path) -> int:
    count = 0
    if inlet.RUNS_ROOT.is_dir():
        for run_file in inlet.RUNS_ROOT.glob("*/run.json"):
            run = engine.read_json(run_file, {})
            if Path(str(run.get("target", ""))).resolve() != target:
                continue
            queue = engine.read_json(run_file.parent / "queue.json", {})
            count += sum(task.get("kind") == "operator" for task in queue.get("tasks", []))
    return count


def derive_objective(inventory: dict[str, Any], explicit: str = "", iteration: int | None = None) -> str:
    if explicit.strip():
        return explicit.strip()[:2000]
    target = Path(inventory["target"])
    number = iteration if iteration is not None else _project_iterations(target) + 1
    intent = inventory.get("intent", {})
    objective = str(intent.get("objective") or intent.get("intent") or "").strip()
    goals = _string_list(intent.get("improvement_goals"), limit=12)
    if objective:
        base = f"Project improvement iteration {number}: advance this intent through one coherent bounded increment: {objective}"
    else:
        base = (
            f"Project improvement iteration {number}: inspect the project from its current {inventory['state']} state, select "
            "the highest-value bounded improvement, implement it, strengthen deterministic validation, and record evidence plus "
            "the next recommended increment."
        )
    if goals:
        base += " Long-term goals include: " + "; ".join(goals) + "."
    return base[:2000]


def create_intake_work_order(inventory: dict[str, Any], objective: str, *, approval_mode: str = "required") -> Path:
    target = Path(inventory["target"])
    slug = engine.slug(str(inventory.get("name") or target.name))[:24] or "project"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work_order_id = f"LIVE-{slug}-{stamp}-{secrets.token_hex(2)}".upper()
    intake_root = inlet.LIVE_INTAKE_ROOT
    intake_root.mkdir(parents=True, exist_ok=True)
    path = intake_root / f"{work_order_id}.json"
    data = {
        "leafos_object": "leafos.work_order",
        "version": 2,
        "work_order_id": work_order_id,
        "title": f"Live project intake: {inventory['name']}",
        "target": str(target),
        "objective": objective,
        "scope": inventory["allowed_paths"],
        "constraints": [
            "Inspect the current project state before proposing changes.",
            "Make one coherent bounded increment; do not replace the project wholesale.",
            "Use only exact declared commands and provide complete runnable source rather than placeholder instructions.",
            "Use only the configured local provider endpoint for model traffic.",
            "Do not request, display, or persist private chain-of-thought.",
            *inventory.get("constraints", []),
        ],
        "allowed_paths": inventory["allowed_paths"],
        "denied_paths": inventory["denied_paths"],
        "commands": {"tests": inventory["commands"]},
        "acceptance": inventory["acceptance"],
        "approval_mode": approval_mode,
        "allow_mutation": True,
        "max_attempts": 2,
        "timeout_seconds": 900,
        "live_project": {
            "state": inventory["state"],
            "source_files": inventory["source_file_count"],
            "tests": inventory["test_file_count"],
        },
    }
    engine.write_json(path, data)
    return path


def _latest_project_run(target: Path) -> Path | None:
    matches: list[tuple[float, Path]] = []
    if not inlet.RUNS_ROOT.is_dir():
        return None
    for run_file in inlet.RUNS_ROOT.glob("*/run.json"):
        run = engine.read_json(run_file, {})
        if int(run.get("version", 1)) < 2:
            continue
        try:
            same_target = Path(str(run.get("target", ""))).resolve() == target
        except OSError:
            same_target = False
        if same_target:
            matches.append((run_file.stat().st_mtime, run_file.parent))
    return max(matches, default=(0.0, None), key=lambda item: item[0])[1]


def _activate(run_dir: Path, target: Path) -> None:
    inlet.RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    run = engine.read_json(run_dir / "run.json", {})
    engine.write_json(inlet.RUNS_ROOT / "active.json", {
        "run_dir": str(run_dir), "run_id": run.get("run_id", run_dir.name), "target": str(target),
    })


def _refresh_provider(run_dir: Path, mode: str) -> tuple[str, str]:
    run = engine.read_json(run_dir / "run.json", {})
    effective = mode or str(run.get("provider_mode", "required"))
    status, reason = inlet.ensure_provider(effective)
    run.update(provider_mode=effective, provider_status=status, provider_reason=reason)
    if effective != "off":
        run["provider_endpoint"] = inlet.provider_endpoint(inlet.load_provider_config())
    engine.write_json(run_dir / "run.json", run)
    return status, reason


def start_project(
    target_value: str | Path,
    *,
    create_seed: bool = False,
    template: str = "auto",
    objective: str = "",
    provider: str = "required",
    approved: bool = False,
    fresh_run: bool = False,
    spawn: bool = True,
    resident: bool = True,
    resident_mode: str = "auto",
    budget_minutes: int | None = None,
    run_dir: str = "",
) -> dict[str, Any]:
    target = Path(target_value).expanduser().resolve()
    written = initialize_seed(target, template) if create_seed else []
    if not target.is_dir():
        raise ValueError(f"project directory not found: {target}")
    existing = None if fresh_run or create_seed else _latest_project_run(target)
    if existing is not None:
        status, reason = _refresh_provider(existing, provider)
        _activate(existing, target)
        resident_pid = 0
        worker_pid = 0
        if spawn:
            if resident:
                import leaf_resident_supervisor as resident_supervisor
                resident_supervisor.initialize_resident(existing, mode=resident_mode, budget_minutes=budget_minutes)
                resident_pid = resident_supervisor.ensure_supervisor(existing)
            else:
                lease = engine.read_json(existing / "worker.lock", {})
                worker_pid = int(lease.get("pid", 0)) if inlet._pid_alive(int(lease.get("pid", 0))) else inlet.spawn_worker(existing, 1.0)
        return {
            "action": "attached", "run_dir": str(existing), "target": str(target),
            "provider_status": status, "provider_reason": reason, "seed_files": written,
            "resident_pid": resident_pid, "worker_pid": worker_pid,
        }
    inventory = inspect_project(target)
    derived = derive_objective(inventory, objective)
    work_order = create_intake_work_order(inventory, derived, approval_mode="required")
    args = argparse.Namespace(
        target=str(target), target_option="", work_order=str(work_order), profile="live-project",
        provider=provider, run_id="", run_dir=run_dir, max_minutes=64, timeout_seconds=900,
        interval=1.0, no_start_provider=False, yes=approved, foreground=False,
        create_only=not spawn, json=False, check=[], objective=derived,
    )
    created = inlet.create_work_order_run(args)
    run = engine.read_json(created / "run.json", {})
    run["live_project"] = {
        "state": inventory["state"], "iteration": 0,
        "intake": str(work_order),
        "syntax": ":improve | :again | :<objective> | :mode | :targets | :budget",
    }
    engine.write_json(created / "run.json", run)
    engine.append_event(created, "project.intake", state=inventory["state"], source_files=inventory["source_file_count"])
    worker_pid = 0
    resident_pid = 0
    if spawn:
        if resident:
            import leaf_resident_supervisor as resident_supervisor
            resident_supervisor.initialize_resident(created, mode=resident_mode, budget_minutes=budget_minutes)
            resident_pid = resident_supervisor.spawn_supervisor(created, 1.0)
        else:
            worker_pid = inlet.spawn_worker(created, 1.0)
    return {
        "action": "created", "run_dir": str(created), "target": str(target),
        "provider_status": run.get("provider_status"), "worker_pid": worker_pid,
        "resident_pid": resident_pid,
        "seed_files": written, "inventory": inventory, "objective": derived,
    }


def queue_improvement(
    run_value: str | Path,
    objective: str = "",
    *,
    spawn: bool = True,
    source: str = "operator",
    priority: int | None = None,
    dependencies: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_dir = inlet.resolve_run(str(run_value))
    run = engine.read_json(run_dir / "run.json", {})
    if int(run.get("version", 1)) < 2:
        raise ValueError("live improvements require a version 2 work-order run")
    target = Path(str(run.get("target", ""))).resolve(strict=True)
    inventory = inspect_project(target)
    queue = engine.read_json(run_dir / "queue.json", {})
    operator_tasks = [task for task in queue.get("tasks", []) if task.get("kind") == "operator"]
    iteration = len(operator_tasks) + 1
    derived = derive_objective(inventory, objective, iteration)
    task_dependencies: list[str] = list(dependencies) if dependencies is not None else []
    if dependencies is None and operator_tasks:
        previous = operator_tasks[-1]
        previous_ok = previous.get("status") not in {"failed", "blocked", "cancelled"}
        operator_may_preempt = source == "operator" and previous.get("admission_source") == "resident"
        if previous_ok and not operator_may_preempt:
            task_dependencies = [str(previous["task_id"])]
    request = {
        "leafos_object": "leafos.task_control_request",
        "version": 1,
        "action": "submit",
        "task": {
            "objective": derived,
            "allowed_paths": inventory["allowed_paths"],
            "denied_paths": inventory["denied_paths"],
            "constraints": [
                "Inspect current files and prior validation evidence before choosing the increment.",
                "Implement one coherent improvement and preserve unrelated behavior.",
                "Use the local stack for proposals; CPU policy executes and validates.",
                *inventory.get("constraints", []),
            ],
            "commands": {"tests": inventory["commands"]},
            "acceptance": inventory["acceptance"],
            "allow_mutation": True,
            "approval_mode": "automatic",
            "priority": priority if priority is not None else (4 if source == "resident" else 2),
            "max_attempts": 3,
            "timeout_seconds": 900,
            "stack_role": "coder",
            "dependencies": task_dependencies,
        },
    }
    mode = str(run.get("provider_mode", "required"))
    if mode != "off":
        _refresh_provider(run_dir, mode)
    task = inlet.apply_task_control(run_dir, request)
    with engine.queue_write_lock(run_dir):
        queue = engine.read_json(run_dir / "queue.json", {})
        current = next((item for item in queue.get("tasks", []) if item.get("task_id") == task["task_id"]), None)
        if current is not None:
            current["admission_source"] = source
            if metadata:
                current["metadata"] = dict(metadata)
            engine.write_json(run_dir / "queue.json", queue)
            task = current
    run = engine.read_json(run_dir / "run.json", run)
    live = run.setdefault("live_project", {})
    live.update(iteration=iteration, last_task_id=task["task_id"], last_objective=derived, state=inventory["state"])
    engine.write_json(run_dir / "run.json", run)
    engine.append_event(
        run_dir, "project.improvement_queued", task_id=task["task_id"], iteration=iteration,
        inferred=not bool(objective.strip()), source=source,
    )
    pid = 0
    resident_pid = 0
    if spawn:
        resident_state = engine.read_json(run_dir / "resident-state.json", {})
        if resident_state.get("enabled"):
            import leaf_resident_supervisor as resident_supervisor
            resident_pid = resident_supervisor.ensure_supervisor(run_dir)
        else:
            lease = engine.read_json(run_dir / "worker.lock", {})
            if not inlet._pid_alive(int(lease.get("pid", 0))):
                pid = inlet.spawn_worker(run_dir, 1.0)
    return {
        "action": "improve", "run_dir": str(run_dir), "task": task, "iteration": iteration,
        "objective": derived, "worker_pid": pid, "resident_pid": resident_pid,
    }


def _split_arguments(value: str) -> list[str]:
    lexer = shlex.shlex(value, posix=False)
    lexer.whitespace_split = True
    lexer.commenters = ""
    parts = list(lexer)
    return [part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in {'"', "'"} else part for part in parts]


def parse_active_command(value: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise ValueError("active command must be text")
    command = value.strip()
    if not command or len(command) > MAX_COMMAND_CHARS or any(ord(char) < 32 for char in command):
        raise ValueError("active command must contain 1-512 printable characters")
    body = command[1:].strip() if command.startswith(":") else command
    verb, _, remainder = body.partition(" ")
    verb = verb.lower()
    remainder = remainder.strip()
    if verb in {"help", "?"}:
        return {"action": "help"}
    if verb in {"improve", "do"}:
        return {"action": "improve", "objective": remainder}
    if verb in {"queue", "add"}:
        return {"action": "improve", "objective": remainder}
    if verb == "again":
        if remainder:
            raise ValueError(":again does not take arguments")
        return {"action": "improve", "objective": ""}
    if verb == "project":
        parts = _split_arguments(remainder)
        if len(parts) != 1:
            raise ValueError(':project requires one path; quote paths containing spaces')
        return {"action": "project", "target": parts[0], "create": False, "template": "auto"}
    if verb == "new":
        parts = _split_arguments(remainder)
        if not 1 <= len(parts) <= 2:
            raise ValueError(':new requires PATH and optional template "generic"')
        template = parts[1].lower() if len(parts) == 2 else "auto"
        if template not in {"auto", "generic"}:
            raise ValueError("live project template must be auto or generic")
        return {"action": "project", "target": parts[0], "create": True, "template": template}
    if verb == "status":
        return {"action": "status"}
    if verb == "mode":
        mode = remainder.lower()
        if mode not in {"auto", "quiet", "full"}:
            raise ValueError(":mode requires auto, quiet, or full")
        return {"action": "resident_mode", "mode": mode}
    if verb == "targets":
        match = re.fullmatch(r"cpu\s+(\d+(?:\.\d+)?)\s+gpu\s+(\d+(?:\.\d+)?)", remainder, re.IGNORECASE)
        if not match:
            raise ValueError(":targets requires: cpu PERCENT gpu PERCENT")
        return {"action": "resident_targets", "cpu": float(match.group(1)), "gpu": float(match.group(2))}
    if verb == "budget":
        match = re.fullmatch(r"(\d+)\s*(m|min|minutes)?", remainder, re.IGNORECASE)
        if not match:
            raise ValueError(":budget requires a number of minutes, for example :budget 64m")
        return {"action": "resident_budget", "minutes": int(match.group(1))}
    if verb in {"pause", "resume", "drain", "stop"}:
        if remainder:
            raise ValueError(f":{verb} does not take arguments")
        return {"action": "resident_control", "control": verb}
    return {"action": "improve", "objective": body}


def execute_active_command(value: str, current_run: str | Path = "active", *, spawn: bool = True) -> dict[str, Any]:
    parsed = parse_active_command(value)
    action = parsed["action"]
    if action == "help":
        return {
            "action": "help",
            "message": ':improve [objective] | :again | :mode auto|quiet|full | :targets cpu 80 gpu 90 | :budget 64m | :pause|:resume|:drain|:stop',
        }
    if action == "status":
        run_dir = inlet.resolve_run(str(current_run))
        run = engine.read_json(run_dir / "run.json", {})
        import leaf_resident_supervisor as resident_supervisor
        return {
            "action": "status", "run_dir": str(run_dir), "target": run.get("target"),
            "live_project": run.get("live_project", {}), "resident": resident_supervisor.resident_status(run_dir),
        }
    if action.startswith("resident_"):
        import leaf_resident_supervisor as resident_supervisor
        if action == "resident_mode":
            state = resident_supervisor.set_resident_control(current_run, "mode", mode=parsed["mode"])
        elif action == "resident_targets":
            state = resident_supervisor.set_resident_control(current_run, "targets", cpu=parsed["cpu"], gpu=parsed["gpu"])
        elif action == "resident_budget":
            state = resident_supervisor.set_resident_control(current_run, "budget", minutes=parsed["minutes"])
        else:
            state = resident_supervisor.set_resident_control(current_run, parsed["control"])
        return {
            "action": action, "run_dir": str(inlet.resolve_run(str(current_run))), "resident": state,
            "message": f"resident {parsed.get('control') or parsed.get('mode') or action} accepted",
        }
    if action == "project":
        result = start_project(
            parsed["target"], create_seed=parsed["create"], template=parsed["template"],
            provider="required", approved=False, fresh_run=parsed["create"], spawn=spawn,
        )
        result["message"] = f"{result['action']} live project {result['target']}"
        return result
    result = queue_improvement(current_run, parsed.get("objective", ""), spawn=spawn)
    result["message"] = f"queued iteration {result['iteration']} as {result['task']['task_id']}"
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open a project in the LeafOS live agentic stack.")
    parser.add_argument("target", nargs="?", default=None)
    parser.add_argument("--new", action="store_true", help="create the three-file seed before intake")
    parser.add_argument("--wizard", action="store_true", help="open guided new/existing project onboarding")
    parser.add_argument("--onboard-json", help="apply a typed project onboarding request from JSON")
    parser.add_argument("--template", choices=("auto", "generic"), default="auto")
    parser.add_argument("--objective", default="", help="optional first objective; project discovery is the default")
    parser.add_argument("--provider", choices=("required", "auto", "off"), default="required")
    parser.add_argument("--yes", action="store_true", help="pre-approve the initial mutation gate")
    parser.add_argument("--fresh-run", action="store_true")
    parser.add_argument("--no-worker", action="store_true")
    parser.add_argument("--no-resident", action="store_true", help="use the legacy one-shot worker instead of the resident supervisor")
    parser.add_argument("--mode", choices=("auto", "quiet", "full"), default="auto")
    parser.add_argument("--budget", type=int, help="unattended resident budget in minutes")
    parser.add_argument("--no-tui", action="store_true")
    parser.add_argument("--inspect", action="store_true", help="inspect project intake without creating a run")
    parser.add_argument("--command", default="", help="send one active-window command noninteractively")
    parser.add_argument("--json", action="store_true")
    renderer = parser.add_mutually_exclusive_group()
    renderer.add_argument("--native", action="store_true")
    renderer.add_argument("--python-renderer", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command:
            result = execute_active_command(args.command)
        elif args.onboard_json:
            request = json.loads(Path(args.onboard_json).read_text(encoding="utf-8"))
            result = apply_project_onboarding(request)
        elif args.wizard or (args.target is None and sys.stdin.isatty() and sys.stdout.isatty() and not args.inspect):
            tui_dir = ROOT / "core" / "ui" / "tui"
            if str(tui_dir) not in sys.path:
                sys.path.insert(0, str(tui_dir))
            import project_wizard

            result = project_wizard.run_project_wizard(
                preview=preview_project_onboarding,
                apply=apply_project_onboarding,
                recent_targets=recent_project_targets(),
                defaults={
                    "provider": args.provider, "approved": args.yes,
                    "resident": not args.no_resident, "resident_mode": args.mode,
                    "budget_minutes": args.budget, "spawn": not args.no_worker,
                },
            )
            if result is None:
                return 0
        elif args.inspect:
            result = inspect_project(args.target or ".")
        else:
            result = start_project(
                args.target or ".", create_seed=args.new, template=args.template, objective=args.objective,
                provider=args.provider, approved=args.yes, fresh_run=args.fresh_run,
                spawn=not args.no_worker, resident=not args.no_resident,
                resident_mode=args.mode, budget_minutes=args.budget,
            )
        if args.json or args.no_tui or args.inspect or args.command:
            print(json.dumps(result, indent=2, ensure_ascii=True) if args.json else result.get("message", result.get("run_dir", result)))
            return 0
        command = [sys.executable, str(ROOT / "core" / "ui" / "tui" / "main.py"), "--run", "active"]
        if args.native:
            command.append("--native")
        elif args.python_renderer:
            command.append("--python-renderer")
        return subprocess.run(command, cwd=ROOT, check=False).returncode
    except (OSError, ValueError, RuntimeError) as error:
        print(f"live: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
