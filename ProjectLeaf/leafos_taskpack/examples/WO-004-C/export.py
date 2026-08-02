#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WO-004-C-02 -- export gate (portable).

Packages the verified wakeup module into exports/WO-004-C_wakeup_<stamp>_verified.zip.

Included (WO-004-C-02 section 9):
    wakeup.py, wakeup.sh, tickers.txt, README.md, tests/, docs/,
    agent_node.json, symbolic_training.jsonl,
    completion_map.json, completion_tree.txt,
    runs/latest/wakeup_result.json, runs/wakeup_log.csv

Excluded: __pycache__/, .pytest_cache/, .env, API keys, shell history.
"""

import sys
import zipfile
from datetime import datetime
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent

INCLUDE = [
    "wakeup.py",
    "wakeup.sh",
    "tickers.txt",
    "README.md",
    "tests",
    "docs",
    "agent_node.json",
    "symbolic_training.jsonl",
    "completion_map.json",
    "completion_tree.txt",
    "runs/latest/wakeup_result.json",
    "runs/wakeup_log.csv",
]

EXCLUDE_DIRS = {"__pycache__", ".pytest_cache"}
EXCLUDE_NAMES = {".env"}
EXCLUDE_SUFFIXES = {".pyc"}


def _excluded(path):
    if path.name in EXCLUDE_NAMES:
        return True
    if path.suffix in EXCLUDE_SUFFIXES:
        return True
    return any(part in EXCLUDE_DIRS for part in path.parts)


def _iter_files(rel):
    base = MODULE_ROOT / rel
    if not base.exists():
        return
    if base.is_file():
        if not _excluded(base):
            yield base
        return
    for child in sorted(base.rglob("*")):
        if child.is_file() and not _excluded(child):
            yield child


def main(argv):
    work_order = argv[1] if len(argv) > 1 else "WO-004-C"
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir = MODULE_ROOT / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / "{}_wakeup_{}_verified.zip".format(work_order, stamp)

    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE:
            for file_path in _iter_files(rel):
                arcname = file_path.relative_to(MODULE_ROOT).as_posix()
                zf.write(file_path, arcname)
                count += 1

    if count == 0:
        print("export gate: nothing to package", file=sys.stderr)
        return 1

    print("export complete: {}".format(zip_path.relative_to(MODULE_ROOT)))
    print("  packaged {} file(s)".format(count))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
