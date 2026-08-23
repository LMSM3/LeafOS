from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from core.state import utc_now


TOOL_ALLOWLIST = {"artifact", "inspect", "search", "test"}
MAX_TEXT_BYTES = 128 * 1024
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_SEARCH_FILES = 256
MAX_SEARCH_MATCHES = 200
MAX_TOOL_OUTPUT_BYTES = 256 * 1024
TEST_SELECTOR_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
BLOCKED_PARTS = {".git", ".leaf", "__pycache__", "logs"}
BLOCKED_NAMES = {".env", "credentials", "credentials.json", "id_dsa", "id_ed25519", "id_rsa"}


class ToolError(ValueError):
    pass


def _project_path(project_root: Path, value: str | None) -> tuple[Path, str]:
    if not isinstance(value, str) or not value.strip():
        raise ToolError("tool path is required")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = project_root / candidate
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(project_root)
    except ValueError as error:
        raise ToolError(f"tool path escapes the project: {value}") from error
    folded_parts = {part.casefold() for part in relative.parts}
    if folded_parts & BLOCKED_PARTS or relative.name.casefold() in BLOCKED_NAMES:
        raise ToolError(f"tool path is excluded from evidence: {relative.as_posix()}")
    return resolved, relative.as_posix() or "."


def _read_text(path: Path, relative: str) -> str:
    if not path.is_file():
        raise ToolError(f"tool path is missing or not a file: {relative}")
    size = path.stat().st_size
    if size > MAX_TEXT_BYTES:
        raise ToolError(f"text tool input exceeds {MAX_TEXT_BYTES} bytes: {relative}")
    data = path.read_bytes()
    if b"\x00" in data:
        raise ToolError(f"text tool input is binary: {relative}")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ToolError(f"text tool input is not UTF-8: {relative}") from error


def _base_result(tool: str, command: dict[str, Any], started_at: str) -> dict[str, Any]:
    return {
        "tool": tool,
        "command": command,
        "started_at": started_at,
        "finished_at": utc_now(),
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
        "next_action": None,
        "mutation_policy": "bounded-test-process" if tool == "test" else "read-only",
    }


def _finish_result(result: dict[str, Any]) -> dict[str, Any]:
    truncated = False
    for field in ("stdout", "stderr"):
        value = str(result.get(field) or "")
        data = value.encode("utf-8")
        if len(data) <= MAX_TOOL_OUTPUT_BYTES:
            result[field] = value
            continue
        marker = f"\n[LeafOS truncated {field} at {MAX_TOOL_OUTPUT_BYTES} bytes]\n"
        room = MAX_TOOL_OUTPUT_BYTES - len(marker.encode("utf-8"))
        result[field] = data[:room].decode("utf-8", errors="ignore") + marker
        truncated = True
    if truncated:
        result["output_truncated"] = True
        if not result.get("next_action"):
            result["next_action"] = "Narrow the bounded tool target before relying on truncated output."
    return result


def execute_tool(
    project_root: Path,
    tool: str,
    *,
    path: str | None = None,
    query: str | None = None,
    selector: str | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    root = project_root.resolve()
    started_at = utc_now()
    command: dict[str, Any] = {"tool": tool}
    if path is not None:
        command["path"] = path
    if query is not None:
        command["query"] = query
    if selector is not None:
        command["selector"] = selector
    try:
        if tool not in TOOL_ALLOWLIST:
            raise ToolError(f"tool is not allowlisted: {tool}")
        if not 1 <= timeout_seconds <= 300:
            raise ToolError("tool timeout must be between 1 and 300 seconds")

        if tool == "inspect":
            target, relative = _project_path(root, path)
            content = _read_text(target, relative)
            result = _base_result(tool, {"tool": tool, "path": relative}, started_at)
            result["stdout"] = content
            return _finish_result(result)

        if tool == "artifact":
            target, relative = _project_path(root, path)
            if not target.is_file():
                raise ToolError(f"artifact is missing or not a file: {relative}")
            size = target.stat().st_size
            if size > MAX_ARTIFACT_BYTES:
                raise ToolError(f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes: {relative}")
            data = target.read_bytes()
            result = _base_result(tool, {"tool": tool, "path": relative}, started_at)
            result["stdout"] = f"captured {relative} ({len(data)} bytes)\n"
            result["capture"] = {
                "path": relative,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "data": data,
            }
            return _finish_result(result)

        if tool == "search":
            if not isinstance(query, str) or not query:
                raise ToolError("search query is required")
            if len(query) > 512:
                raise ToolError("search query is too large")
            target, relative = _project_path(root, path or ".")
            if not target.exists():
                raise ToolError(f"search path is missing: {relative}")
            if target.is_file():
                candidates = [target]
            else:
                candidates = []
                for candidate in sorted(target.rglob("*")):
                    if not candidate.is_file():
                        continue
                    rel = candidate.relative_to(root)
                    folded = {part.casefold() for part in rel.parts}
                    if folded & BLOCKED_PARTS or candidate.name.casefold() in BLOCKED_NAMES:
                        continue
                    if candidate.suffix.casefold() == ".gguf" or candidate.stat().st_size > MAX_TEXT_BYTES:
                        continue
                    candidates.append(candidate)
                    if len(candidates) >= MAX_SEARCH_FILES:
                        break
            matches = []
            folded_query = query.casefold()
            for candidate in candidates:
                candidate_relative = candidate.relative_to(root).as_posix()
                try:
                    content = _read_text(candidate, candidate_relative)
                except ToolError:
                    continue
                for number, line in enumerate(content.splitlines(), start=1):
                    if folded_query in line.casefold():
                        matches.append(f"{candidate_relative}:{number}:{line}")
                        if len(matches) >= MAX_SEARCH_MATCHES:
                            break
                if len(matches) >= MAX_SEARCH_MATCHES:
                    break
            result = _base_result(
                tool,
                {"tool": tool, "path": relative, "query": query, "max_matches": MAX_SEARCH_MATCHES},
                started_at,
            )
            result["stdout"] = "\n".join(matches) + ("\n" if matches else "")
            if not matches:
                result["exit_code"] = 1
                result["stderr"] = "no matches\n"
                result["next_action"] = "Revise the literal query or inspect the selected project path."
            return _finish_result(result)

        if not isinstance(selector, str) or not TEST_SELECTOR_PATTERN.fullmatch(selector):
            raise ToolError("test selector must be a dotted Python unittest name")
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "unittest", selector, "-v"],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
            result = _base_result(tool, {"tool": tool, "selector": selector}, started_at)
            result["exit_code"] = int(completed.returncode)
            result["stdout"] = completed.stdout or ""
            result["stderr"] = completed.stderr or ""
        except subprocess.TimeoutExpired as error:
            result = _base_result(tool, {"tool": tool, "selector": selector}, started_at)
            result["exit_code"] = 124
            result["stdout"] = str(error.stdout or "")
            result["stderr"] = str(error.stderr or "") + f"\ntest timed out after {timeout_seconds} seconds\n"
        if result["exit_code"] != 0:
            result["next_action"] = "Inspect captured test output, fix or narrow the test target, then retry within budget."
        return _finish_result(result)
    except (OSError, ToolError) as error:
        result = _base_result(tool, command, started_at)
        result["exit_code"] = 2
        result["stderr"] = str(error) + "\n"
        result["next_action"] = "Correct the bounded tool request before retrying."
        return _finish_result(result)
