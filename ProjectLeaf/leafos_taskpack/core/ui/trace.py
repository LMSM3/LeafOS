#!/usr/bin/env python3
"""Read-only observable loop trace assembled from existing run artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def _latest(root: Path) -> Path | None:
    run_root = root / "runs"
    items = [path for path in run_root.iterdir() if path.is_dir() and path.name != "latest"] if run_root.is_dir() else []
    return max(items, key=lambda path: path.stat().st_mtime) if items else None


def build_trace(target: str = "latest", root: Path = ROOT) -> dict[str, Any]:
    run = _latest(root) if target == "latest" else root / "runs" / target
    if run is None or not run.is_dir():
        return {"leafos_object": "observable_loop_trace", "status": "missing", "target": target, "artifacts": [], "events": []}
    artifacts = []
    events = []
    for path in sorted(run.rglob("*")):
        if not path.is_file():
            continue
        artifacts.append({"path": str(path.relative_to(run)), "bytes": path.stat().st_size})
        if path.suffix == ".jsonl" and path.stat().st_size <= 16 * 1024 * 1024:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return {
        "leafos_object": "observable_loop_trace", "status": "ok", "run": run.name,
        "path": str(run), "artifacts": artifacts, "events": events[-50:],
        "private_chain_of_thought_exposed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="leafctl trace")
    parser.add_argument("target", nargs="?", default="latest")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    trace = build_trace(args.target)
    if args.json:
        print(json.dumps(trace, sort_keys=True, separators=(",", ":")))
    else:
        print(f"Observable Loop Trace: {trace.get('run', args.target)} ({trace['status']})")
        for artifact in trace["artifacts"][:30]:
            print(f"  {artifact['path']}  {artifact['bytes']} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
