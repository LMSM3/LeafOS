from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from stocklab.analysis import analyze
from stocklab.io import DataError


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="verdant-quant", description="Deterministic mathematical stock research")
    subcommands = parser.add_subparsers(dest="command", required=True)
    command = subcommands.add_parser("analyze", help="analyze aligned synthetic or user-supplied price/factor data")
    command.add_argument("--prices", required=True)
    command.add_argument("--factors", required=True)
    command.add_argument("--config", required=True)
    command.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = _json_safe(analyze(args.prices, args.factors, args.config))
        rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
        if args.output:
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
            print(target.resolve())
        else:
            print(rendered, end="")
        return 0
    except (DataError, ValueError, OSError) as error:
        print(f"verdant-quant: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
