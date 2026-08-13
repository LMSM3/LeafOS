#!/usr/bin/env python3
"""LeafOS readiness doctor shared by the Bash command surface."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def check(check_id: str, ok: bool, detail: str, repair: str | None = None) -> dict[str, Any]:
    return {"id": check_id, "required": True, "ok": ok, "detail": detail, "repair": repair}


def native_memory(root: Path) -> tuple[bool, str]:
    candidates = []
    if os.environ.get("LEAF_MEMORY_BIN"):
        candidates.append(Path(os.environ["LEAF_MEMORY_BIN"]))
    candidates.extend((root / "build" / "leaf-memory.exe", root / "build" / "leaf-memory"))
    executable = next((item for item in candidates if item.is_file()), None)
    if executable is None:
        return False, "native leaf-memory executable not found"
    journal_name = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="leaf-doctor-", suffix=".ndjson", delete=False) as journal:
            journal_name = journal.name
        result = subprocess.run(
            [str(executable), "verify", "--journal", journal_name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return True, f"verification probe passed: {executable}"
        evidence = (result.stderr or result.stdout).strip()
        return False, f"verification probe failed (exit {result.returncode}): {evidence}"
    except (OSError, subprocess.SubprocessError) as error:
        return False, f"native executable could not run: {error}"
    finally:
        if journal_name:
            Path(journal_name).unlink(missing_ok=True)


def durable_monday(root: Path) -> tuple[bool, str]:
    instance = Path(os.environ.get("LEAF_MONDAY_INSTANCE", root / "instances" / "monday-primary"))
    required = ("persona.json", "state.json", "events.ndjson", "facts.ndjson")
    missing = [name for name in required if not (instance / name).is_file()]
    if missing:
        return False, "missing: " + ", ".join(missing)
    try:
        sys.path.insert(0, str(root / "core" / "python"))
        import leaf_continual_bloom as bloom

        result = bloom.verify(instance)
        if result.get("status") != "ok":
            return False, f"durable verification returned: {result.get('status', 'unknown')}"
        return True, f"identity, transcript, facts, and state verified: {instance}"
    except Exception as error:  # The report must convert every corrupt-state failure into evidence.
        return False, f"durable verification failed: {error}"


def build_report(root: Path) -> dict[str, Any]:
    root = root.resolve()
    directories = ("bin", "core", "config", "share", "logs", "tests", "docs")
    missing_directories = [f"{name}/" for name in directories if not (root / name).is_dir()]
    files = (
        "config/brand.conf", "config/loaders.conf", "config/glyphs.conf", "config/runtime.json",
        "core/brand/brand.sh", "core/log/log.sh", "core/loaders/loaders.sh",
        "core/glyphs/glyphs.sh", "core/runtime/runtime.sh",
    )
    missing_files = [name for name in files if not (root / name).is_file()]
    memory_ok, memory_detail = native_memory(root)
    monday_ok, monday_detail = durable_monday(root)
    checks = [
        check(
            "layout.directories", not missing_directories,
            "required project directories are present" if not missing_directories else "missing: " + ", ".join(missing_directories),
            None if not missing_directories else "restore the taskpack checkout; generated runtime data cannot replace source directories",
        ),
        check(
            "layout.files", not missing_files,
            "required project files are present" if not missing_files else "missing: " + ", ".join(missing_files),
            None if not missing_files else "restore the missing tracked files from the taskpack checkout",
        ),
        check("runtime.python", True, f"available: {sys.executable}"),
        check(
            "memory.native", memory_ok, memory_detail,
            None if memory_ok else f'run: make -C "{root}" all  (or set LEAF_MEMORY_BIN to a verified leaf-memory executable)',
        ),
        check(
            "persona.monday", monday_ok, monday_detail,
            None if monday_ok else "run: leafos bloom init --json",
        ),
    ]
    failed = [item for item in checks if item["required"] and not item["ok"]]
    ready = not failed
    layout_ready = checks[0]["ok"] and checks[1]["ok"]
    return {
        "leafos_object": "leafos.doctor_report",
        "version": 1,
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "root": str(root),
        "capabilities": {"cli": layout_ready, "live_project": ready},
        "checks": checks,
        "repairs": [{"check": item["id"], "command": item["repair"]} for item in failed],
    }


def print_human(report: dict[str, Any]) -> None:
    color = not os.environ.get("NO_COLOR") and sys.stdout.isatty()
    mint, leaf, red, butter, dim, reset = (
        ("\033[38;2;183;240;199m", "\033[38;2;119;221;119m", "\033[38;2;255;154;162m",
         "\033[38;2;255;250;181m", "\033[2m", "\033[0m") if color else ("", "", "", "", "", "")
    )
    print(f"{mint}🍃 LeafOS: readiness: {report['status']}{reset}")
    for item in report["checks"]:
        if item["ok"]:
            print(f"  {leaf}✓{reset} {item['id']}  {dim}{item['detail']}{reset}")
        else:
            print(f"  {red}✗{reset} {item['id']}  {item['detail']}")
            print(f"      {butter}{item['repair']}{reset}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="leafos doctor")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_report(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    else:
        print_human(report)
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
