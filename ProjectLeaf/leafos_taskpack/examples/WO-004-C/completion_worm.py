#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WO-004-C-02 -- completion worm.

Walks the wakeup module and emits:

    completion_map.json   -- file-by-file completion status
    completion_tree.txt   -- annotated completion traversal

Also emits the symbolic training examples (section 11) as symbolic_training.jsonl.

This is the "completion worm pass" from WO-004-C-02 section 8. It is read by the
future Brain/Coder/Reviewer parser layer, which has no soul and therefore no
opinion about how nicely this is formatted.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent

SYMBOL_DONE = "\u235D"            # complete marker used in the tree
SYMBOL_WARNING = "\u26A0\uFE0E"   # degraded-but-allowed marker

# Files the worm walks (WO-004-C-02 section 8.1).
REQUIRED_FILES = [
    "wakeup.py",
    "wakeup.sh",
    "tickers.txt",
    "README.md",
    "tests/test_wakeup_shell.sh",
    "tests/test_wakeup_json.py",
    "docs/wakeup_node.md",
]

# Files packaged by the export gate (WO-004-C-02 section 9).
EXPORT_FILES = set(REQUIRED_FILES) | {
    "completion_map.json",
    "completion_tree.txt",
    "runs/latest/wakeup_result.json",
    "runs/wakeup_log.csv",
}

REQUIRED_README_SECTIONS = [
    "Purpose", "Run", "Test branches",
    "Optional stock quote module", "Output", "Safety note",
]

PY = sys.executable or "python3"


def _exists(rel):
    return (MODULE_ROOT / rel).exists()


def _size(rel):
    path = MODULE_ROOT / rel
    return path.stat().st_size if path.exists() else 0


def _check_python_compile(rel):
    try:
        subprocess.run([PY, "-m", "py_compile", str(MODULE_ROOT / rel)],
                       check=True, capture_output=True)
        return "pass"
    except Exception:
        return "fail"


def _check_bash_syntax(rel):
    bash = _find_bash()
    if not bash:
        return "skipped"
    try:
        subprocess.run([bash, "-n", str(MODULE_ROOT / rel)],
                       check=True, capture_output=True)
        return "pass"
    except Exception:
        return "fail"


def _find_bash():
    import shutil
    found = shutil.which("bash")
    if found:
        return found
    for cand in (r"C:\msys64\usr\bin\bash.exe", "/bin/bash", "/usr/bin/bash"):
        if Path(cand).exists():
            return cand
    return None


def _check_readme_sections(rel):
    try:
        text = (MODULE_ROOT / rel).read_text(encoding="utf-8")
    except OSError:
        return "fail"
    missing = [s for s in REQUIRED_README_SECTIONS if s not in text]
    return "pass" if not missing else "fail"


def _check_valid_json(rel):
    try:
        with open(MODULE_ROOT / rel, "r", encoding="utf-8") as fh:
            json.load(fh)
        return "pass"
    except (OSError, ValueError):
        return "fail"


def build_file_entry(rel):
    exists = _exists(rel)
    entry = {
        "path": rel,
        "exists": exists,
        "size_bytes": _size(rel),
        "included_in_export": rel in EXPORT_FILES,
        "status": "verified" if exists else "missing",
    }
    if exists:
        if rel.endswith(".py"):
            entry["python_compile"] = _check_python_compile(rel)
        elif rel.endswith(".sh"):
            entry["bash_syntax"] = _check_bash_syntax(rel)
        elif rel == "README.md":
            entry["required_sections"] = _check_readme_sections(rel)
    return entry


def collect_logs():
    logs = []
    for rel in ("runs/latest/wakeup_result.json", "runs/wakeup_log.csv"):
        logs.append({
            "path": rel,
            "exists": _exists(rel),
            "size_bytes": _size(rel),
        })
    return logs


def build_completion_map(file_entries, logs):
    all_required_present = all(e["exists"] for e in file_entries)
    result_json_ok = _exists("runs/latest/wakeup_result.json") and \
        _check_valid_json("runs/latest/wakeup_result.json") == "pass"
    status = "verified" if (all_required_present and result_json_ok) else "incomplete"
    return {
        "leafos_object": "completion_map",
        "version": "0.4.0-C",
        "work_order": "WO-004-C",
        "status": status,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "required_files": file_entries,
        "required_tests": [
            "tests/test_wakeup_shell.sh",
            "tests/test_wakeup_json.py",
        ],
        "logs": logs,
        "export": {
            "files": sorted(EXPORT_FILES),
            "exclude": ["__pycache__/", ".pytest_cache/", ".env"],
        },
    }


def write_completion_map(cmap):
    path = MODULE_ROOT / "completion_map.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cmap, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return path


def write_completion_tree(cmap):
    lines = []
    for entry in cmap["required_files"]:
        mark = SYMBOL_DONE if entry["exists"] else SYMBOL_WARNING
        lines.append("{} {}".format(mark, entry["path"]))
        lines.append("  exists: {}".format("yes" if entry["exists"] else "no"))
        if "python_compile" in entry:
            lines.append("  python_compile: {}".format(entry["python_compile"]))
        if "bash_syntax" in entry:
            lines.append("  bash_syntax: {}".format(entry["bash_syntax"]))
        if "required_sections" in entry:
            lines.append("  required_sections: {}".format(entry["required_sections"]))
        lines.append("  size_bytes: {}".format(entry["size_bytes"]))
        lines.append("  export: {}".format(
            "yes" if entry["included_in_export"] else "no"))
        lines.append("")

    result_rel = "runs/latest/wakeup_result.json"
    result_ok = _exists(result_rel)
    lines.append("{} {}".format(SYMBOL_DONE if result_ok else SYMBOL_WARNING, result_rel))
    lines.append("  exists: {}".format("yes" if result_ok else "no"))
    lines.append("  valid_json: {}".format(
        "yes" if result_ok and _check_valid_json(result_rel) == "pass" else "no"))
    lines.append("  export: yes")
    lines.append("")

    lines.append("{} yfinance quote".format(SYMBOL_WARNING))
    lines.append("  required: no")
    lines.append("  degraded_allowed: yes")
    lines.append("")

    lines.append("status: {}".format(cmap["status"]))

    path = MODULE_ROOT / "completion_tree.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_symbolic_training():
    """Section 11 -- machine action form training examples."""
    records = [
        {
            "work_order": "WO-004-C",
            "action": "wakeup",
            "branch": "tails",
            "unicode": "\U0001F343 WO-004-C wakeup tails -> print greeting with local time",
            "ascii_alias": "@leaf.active WO-004-C wakeup tails -> print greeting with local time",
            "output_contract": "wakeup_greeting",
            "offline_analysis": False,
        },
        {
            "work_order": "WO-004-C",
            "action": "wakeup",
            "branch": "heads",
            "unicode": "\u22C6 WO-004-C wakeup heads -> collect ticker payload and print offline analysis prompt",
            "ascii_alias": "@leaf.model WO-004-C wakeup heads -> collect ticker payload and print offline analysis prompt",
            "output_contract": "wakeup_stock_payload",
            "offline_analysis": True,
        },
    ]
    path = MODULE_ROOT / "symbolic_training.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def main():
    file_entries = [build_file_entry(rel) for rel in REQUIRED_FILES]
    logs = collect_logs()
    cmap = build_completion_map(file_entries, logs)

    map_path = write_completion_map(cmap)
    tree_path = write_completion_tree(cmap)
    train_path = write_symbolic_training()

    print("completion worm pass: {}".format(cmap["status"]))
    for path in (map_path, tree_path, train_path):
        print("  wrote {}".format(path.relative_to(MODULE_ROOT)))
    return 0 if cmap["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
