#!/usr/bin/env python3
"""LeafOS stack CLI: inspect, validate, install, activate."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def load_stack(root: Path, name: str) -> dict:
    path = root / "config" / "stacks" / f"{name}.json"
    if not path.is_file():
        print(f"stack not found: {path}", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def validate_stack(stack: dict, name: str) -> int:
    required = ["schema", "id", "class", "models"]
    missing = [k for k in required if k not in stack]
    if missing:
        print(f"missing keys: {missing}", file=sys.stderr)
        return 1
    enabled = [m for m in stack.get("models", []) if m.get("enabled")]
    ids = [m["id"] for m in enabled]
    slots = [m["slot"] for m in enabled]
    if len(ids) != len(set(ids)):
        print("duplicate model ids", file=sys.stderr)
        return 1
    if len(slots) != len(set(slots)):
        print("duplicate model slots", file=sys.stderr)
        return 1
    for m in stack.get("models", []):
        if m.get("runtime", {}).get("mode") == "local" and m.get("artifact", {}).get("repo") is None:
            print(f"local mode without artifact repo: {m.get('id')}", file=sys.stderr)
            return 1
    if stack.get("policy", {}).get("download_full_upstream") is True:
        print("download_full_upstream must be false for controlled installs", file=sys.stderr)
        return 1
    print(f"valid: {stack['id']} ({len(ids)} models)")
    return 0


def install_stack(root: Path, stack: dict, dry_run: bool) -> int:
    hf = root / "bin" / "leaf-hf"
    plan = []
    for m in stack.get("models", []):
        art = m.get("artifact", {})
        repo = art.get("repo")
        if not repo:
            continue
        local = art.get("local_dir", os.path.join("models", stack["id"], m["id"]))
        local_path = Path(local)
        if not local_path.is_absolute():
            local_path = root / local
        cmd = [str(hf), "get", repo, str(local_path)]
        for pattern in art.get("include", []):
            cmd += ["--include", pattern]
        if dry_run:
            cmd.append("--dry-run")
        plan.append({"model": m["id"], "repo": repo, "local_dir": str(local_path), "cmd": cmd})
    print(json.dumps(plan, indent=2))
    for p in plan:
        print(f"--- {p['model']} ---")
        subprocess.run(p["cmd"], check=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser(prog="leaf stack")
    parser.add_argument("--root", default=os.environ.get("LEAF_ROOT", str(Path(__file__).resolve().parents[2])))
    sub = parser.add_subparsers(dest="subcmd", required=True)

    p_inspect = sub.add_parser("inspect")
    p_inspect.add_argument("name")

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("name")

    p_install = sub.add_parser("install")
    p_install.add_argument("name")
    p_install.add_argument("--dry-run", action="store_true")

    p_activate = sub.add_parser("activate")
    p_activate.add_argument("name")

    args = parser.parse_args(argv)
    root = Path(args.root)
    stack = load_stack(root, args.name)

    if args.subcmd == "inspect":
        print(json.dumps(stack, indent=2))
        return 0
    if args.subcmd == "validate":
        return validate_stack(stack, args.name)
    if args.subcmd == "install":
        return install_stack(root, stack, args.dry_run)
    if args.subcmd == "activate":
        print(f"activate: stack {args.name} (runtime loader consumes config/stacks/{args.name}.json)")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
