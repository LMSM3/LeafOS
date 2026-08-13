#!/usr/bin/env python3
"""Locate the canonical LeafOS primary reference documents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from home_state import _primary_reference


ROOT = Path(__file__).resolve().parents[2]


def build_state(root: Path = ROOT) -> dict[str, object]:
    reference = _primary_reference(root)
    return {
        "leafos_object": "leafos.primary_reference",
        "version": 1,
        **reference,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="leafos reference")
    parser.add_argument("--json", action="store_true")
    selected = parser.add_mutually_exclusive_group()
    selected.add_argument("--markdown", action="store_true", help="print only the Markdown path")
    selected.add_argument("--tex", action="store_true", help="print only the formatless TeX path")
    args = parser.parse_args()
    state = build_state()
    if args.json:
        print(json.dumps(state, sort_keys=True, separators=(",", ":")))
    elif args.markdown:
        print(state.get("markdown") or "")
    elif args.tex:
        print(state.get("tex") or "")
    else:
        print("LeafOS Primary Reference")
        print(f"Status    {state['status']}")
        print(f"Markdown  {state.get('markdown') or 'not available'}")
        print(f"LaTeX     {state.get('tex') or 'not available'}")
    return 0 if state["status"] in {"available", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
