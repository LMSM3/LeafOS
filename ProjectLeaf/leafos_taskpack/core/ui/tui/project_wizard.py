#!/usr/bin/env python3
"""Guided, renderer-neutral project onboarding for the LeafOS TUI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, TextIO


Preview = Callable[[dict[str, Any]], dict[str, Any]]
Apply = Callable[[dict[str, Any]], dict[str, Any]]


class WizardCancelled(Exception):
    pass


class WizardRestart(Exception):
    pass


def _write(output: TextIO, value: str = "") -> None:
    output.write(value + "\n")
    output.flush()


def _screen(output: TextIO, step: int, title: str, detail: str) -> None:
    if getattr(output, "isatty", lambda: False)():
        output.write("\033[2J\033[H")
    _write(output, "+------------------------------------------------------------------+")
    _write(output, "| LEAFOS PROJECT ONBOARDING                                        |")
    _write(output, f"| Step {step}/6  {title[:54]:<54}|")
    _write(output, "+------------------------------------------------------------------+")
    _write(output, detail)


def _readline(input_stream: TextIO, output: TextIO, label: str, *, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    output.write(f"{label}{suffix}: ")
    output.flush()
    line = input_stream.readline()
    if line == "":
        raise WizardCancelled
    value = line.rstrip("\r\n")
    lowered = value.strip().lower()
    if lowered in {"q", ".cancel", "cancel"}:
        raise WizardCancelled
    if lowered == ".back":
        raise WizardRestart
    return value if value else default


def _choice(
    input_stream: TextIO,
    output: TextIO,
    label: str,
    choices: dict[str, str],
    *,
    default: str,
) -> str:
    while True:
        value = _readline(input_stream, output, label, default=default).strip().lower()
        selected = choices.get(value)
        if selected:
            return selected
        _write(output, "Choose " + ", ".join(sorted(choices)))


def _read_document(input_stream: TextIO, output: TextIO, label: str) -> str:
    _write(output, f"Paste {label} below. Finish with .done on a line by itself.")
    _write(output, "Use .back to restart onboarding or .cancel to leave without writing.")
    lines: list[str] = []
    while True:
        line = input_stream.readline()
        if line == "":
            raise WizardCancelled
        value = line.rstrip("\r\n")
        command = value.strip().lower()
        if command == ".done":
            document = "\n".join(lines).strip("\n")
            if document.strip():
                return document + "\n"
            _write(output, f"{label} cannot be empty; paste content before .done.")
            continue
        if command in {".cancel", "cancel"}:
            raise WizardCancelled
        if command == ".back":
            raise WizardRestart
        lines.append(value)


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _review(output: TextIO, request: dict[str, Any], preview: dict[str, Any]) -> None:
    _screen(output, 6, "Review and start", "No project file has been changed yet.")
    _write(output, f"Mode       : {request['mode']}")
    _write(output, f"Target     : {preview['target']}")
    if request["mode"] == "new":
        _write(output, f"Top level  : {request['workspace_root']}")
        _write(output, f"Project    : {request['project_name']}")
    _write(output, f"Sandbox    : {request['sandbox_profile']}")
    kv_cache = request["model_optimizations"]["kv_cache"]
    _write(output, f"KV cache   : {kv_cache}" + (" (queued work)" if kv_cache != "inherit" else ""))
    _write(output, f"Provider   : {request['provider']}")
    _write(output, f"Resident   : {request['resident_mode']}")
    _write(output, f"Approval   : {'pre-approved' if request['approved'] else 'wait at mutation gate'}")
    if request["mode"] == "new":
        _write(output, f"Template   : {preview['template']}")
        _write(output, "Create     : README.md, skeleton.md, leafos.project.json")
        _write(output, f"README     : {preview['content']['readme_characters']} characters")
        _write(output, f"Skeleton   : {preview['content']['skeleton_characters']} characters")
        if preview.get("conflicts"):
            _write(output, "Conflicts  : " + ", ".join(preview["conflicts"]))
    else:
        inventory = preview["inventory"]
        _write(output, f"Detected   : {inventory['state']} | {inventory['file_count']} files | {inventory['source_file_count']} source")
        _write(output, f"Project    : {inventory['name']}")
    if request.get("objective"):
        _write(output, "Objective  : " + request["objective"])


def run_project_wizard(
    *,
    preview: Preview,
    apply: Apply,
    recent_targets: list[str] | None = None,
    input_stream: TextIO = sys.stdin,
    output: TextIO = sys.stdout,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Collect, preview, confirm, and apply one project onboarding request."""
    settings = defaults or {}
    while True:
        try:
            _screen(output, 1, "Choose project direction", "Open an existing project or create one from pasted intent.")
            mode = _choice(
                input_stream, output, "[1] New project  [2] Existing project  [q] Cancel",
                {"1": "new", "new": "new", "2": "existing", "existing": "existing"}, default="1",
            )
            _screen(output, 2, "Select project", "Paths may be absolute or relative to the current directory.")
            recent = recent_targets or []
            if mode == "existing" and recent:
                _write(output, "Recent projects:")
                for index, target in enumerate(recent[:8], 1):
                    _write(output, f"  [{index}] {target}")
            workspace_root = ""
            project_name = ""
            if mode == "new":
                workspace_root = _readline(
                    input_stream, output, "Top-level project directory",
                    default=str(settings.get("workspace_root") or Path.cwd()),
                )
                workspace_root = _strip_quotes(workspace_root)
                project_name = _readline(input_stream, output, "New project folder name")
                target_value = str(Path(workspace_root).expanduser() / project_name)
            else:
                target_value = _readline(input_stream, output, "Existing project path or recent number")
                if target_value.isdigit() and 1 <= int(target_value) <= len(recent[:8]):
                    target_value = recent[int(target_value) - 1]
                target_value = _strip_quotes(target_value)
            request: dict[str, Any] = {
                "leafos_object": "leafos.project_onboarding_request",
                "version": 1,
                "mode": mode,
                "target": str(Path(target_value).expanduser()),
                "workspace_root": workspace_root,
                "project_name": project_name,
                "template": "auto",
                "readme": "",
                "skeleton": "",
                "objective": "",
                "provider": settings.get("provider", "required"),
                "approved": bool(settings.get("approved", False)),
                "resident": bool(settings.get("resident", True)),
                "resident_mode": settings.get("resident_mode", "auto"),
                "budget_minutes": settings.get("budget_minutes"),
                "spawn": bool(settings.get("spawn", True)),
                "sandbox_profile": "project-only",
                "model_optimizations": {"kv_cache": "inherit"},
            }
            if mode == "new":
                request["template"] = _choice(
                    input_stream, output, "Template [auto/generic]",
                    {"auto": "auto", "generic": "generic"}, default="auto",
                )
                _screen(output, 3, "Paste README", "The README states what the project is and what useful means.")
                request["readme"] = _read_document(input_stream, output, "README")
                _screen(output, 4, "Paste skeleton", "The skeleton may be a file tree, interfaces, pseudocode, or constraints.")
                request["skeleton"] = _read_document(input_stream, output, "skeleton")
            else:
                _screen(output, 3, "Inspect existing project", "LeafOS will inventory this directory without adding control files.")
                inspection = preview(request)["inventory"]
                _write(output, f"Detected {inspection['state']}: {inspection['file_count']} files, {inspection['source_file_count']} source, {inspection['test_file_count']} tests.")
                _readline(input_stream, output, "Press Enter to keep this project")
                _screen(output, 4, "Keep existing project content", "README and skeleton paste steps are skipped for existing projects.")
            _screen(output, 5, "Set initial direction", "Leave the objective blank to let project facts choose the first bounded improvement.")
            request["objective"] = _readline(input_stream, output, "Optional objective")
            request["sandbox_profile"] = _choice(
                input_stream, output, "Sandbox [project-only]",
                {"project-only": "project-only", "project": "project-only"}, default="project-only",
            )
            request["model_optimizations"]["kv_cache"] = _choice(
                input_stream, output, "KV-cache work [inherit/investigate/enable/disable]",
                {
                    "inherit": "inherit", "investigate": "investigate",
                    "enable": "enable", "disable": "disable",
                }, default="inherit",
            )
            approval = _choice(
                input_stream, output, "Initial mutation gate [review/approve]",
                {"review": "review", "approve": "approve", "r": "review", "a": "approve"}, default="review",
            )
            request["approved"] = approval == "approve"
            preview_value = preview(request)
            _review(output, request, preview_value)
            if not preview_value.get("can_apply", False):
                _write(output, "Cannot continue: the target contains onboarding file conflicts.")
                _readline(input_stream, output, "Press Enter to restart")
                continue
            expected = "CREATE" if mode == "new" else "OPEN"
            confirmation = _readline(input_stream, output, f"Type {expected} to continue").strip()
            if confirmation != expected:
                _write(output, "Confirmation did not match. Nothing was changed.")
                return None
            result = apply(request)
            _write(output, f"Ready: {result['target']}")
            if result.get("optimization_task"):
                task = result["optimization_task"]
                _write(output, f"Queued stack optimization: {task['task_id']} (priority {task['priority']})")
            _write(output, "Opening the active LeafOS window...")
            return result
        except WizardRestart:
            continue
        except WizardCancelled:
            _write(output, "Onboarding cancelled. Nothing was changed.")
            return None
