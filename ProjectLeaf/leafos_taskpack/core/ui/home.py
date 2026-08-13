#!/usr/bin/env python3
"""Terminal and JSON operator home backed by home_state."""

from __future__ import annotations

import argparse
import json
import os
import time

from home_state import build_state

# Windows terminals often default to cp1252; force UTF-8 for glyph rendering.
if hasattr(__import__("sys").stdout, "reconfigure"):
    try:
        __import__("sys").stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BRAND_DIR = os.path.dirname(__file__).replace("/ui", "/brand").replace("\\ui", "\\brand")
if BRAND_DIR not in __import__("sys").path:
    __import__("sys").path.insert(0, BRAND_DIR)
from flower_palette import ascii_mode, glyph as brand_glyph, paint  # noqa: E402


# Glyph palette mirrored from config/glyphs.conf
GLYPHS = {
    "ok": ("\u2713", "[ok]"),
    "warn": ("\u26a0", "[!]"),
    "error": ("\u00d7", "[x]"),
    "pending": ("\u25cc", "[..]"),
    "leaf": ("\U0001f331", "LeafOS"),
    "flower": ("\u273f", "*"),
    "work": ("\u2766", "WO"),
    "home": ("\u2302", "home"),
    "runtime": ("\u26a1", ">"),
    "provider": ("\U0001f4e1", "net"),
    "chat": ("\u270d", "<>"),
    "reference": ("\u2712", "ref"),
    "monitor": ("\u23f8", "||"),
    "stack": ("\u25d1", "[o]"),
    "flower-os": ("\u273f", "FOS"),
}


def _glyph(alias: str) -> str:
    return brand_glyph(*GLYPHS.get(alias, GLYPHS["flower"]))


def _status_glyph(status: str) -> str:
    status = str(status).lower()
    if status in {"ok", "ready", "available", "complete", "verified", "passed"}:
        return paint(_glyph("ok"), "ok")
    if status in {"warn", "warning", "degraded", "partial", "blocked"}:
        return paint(_glyph("warn"), "warn")
    if status in {"fail", "error", "failed", "missing", "unavailable"}:
        return paint(_glyph("error"), "error")
    return paint(_glyph("pending"), "info")


def _hline(width: int = 62, char: str = "\u2500") -> str:
    return ("-" if ascii_mode() else char) * width


def _box(title: str, width: int = 62) -> list[str]:
    top = _hline(width, "\u2550")
    return [
        "",
        paint(top, "leaf"),
        paint(f"  {_glyph('leaf')}  {title}", "mint", "semibold"),
        paint(_hline(width), "leaf"),
    ]


def _field(label: str, width: int = 11) -> str:
    """Pad before painting so ANSI bytes do not break visible alignment."""
    return paint(f"{label:<{width}}", "sky")


def render_card(state: dict) -> str:
    operator = state.get("operator", {})
    name = operator.get("name", "LeafOS")
    engine = operator.get("engine", "LeafOS")
    stage = operator.get("stage", "unknown")
    title = f"{name} Home / {engine} Operator Home  [{stage}]"

    defaults = state["runtime"]["defaults"]
    benchmark = state.get("benchmark", {})
    best = benchmark.get("best_generation") or {}
    gross_hour = best.get("projected_gross_cloud_equivalent_usd_per_hour")
    price = benchmark.get("comparison", {}).get("comparison_output_usd_per_million")
    reference = state.get("reference", {})
    readiness = state.get("readiness", {})
    installer = state.get("installer", {})

    lines: list[str] = []
    lines.extend(_box(title))
    lines.append("")

    lines.append(paint("Readiness", "blossom", "semibold"))
    ro = installer.get("readiness", {})
    if "checks" in ro:
        for label, passed in ro["checks"].items():
            lines.append(f"  {_status_glyph('ok' if passed else 'error')}  {paint(label, 'leaf')}")
    else:
        lines.append(f"  {_status_glyph(readiness.get('status', 'unknown'))}  layout: {readiness.get('status', 'unknown')}")
    lines.append("")

    provider = state.get("provider", {})
    accelerator = state.get("accelerator", {})
    stack = state.get("stack", {})
    gpu = state.get("gpu", {})
    lines.append(paint("Runtime", "lavender", "semibold"))
    lines.append(f"  {_status_glyph(provider.get('health'))}  {_field('Provider')} {provider.get('health', 'unknown')}  {paint(provider.get('endpoint', ''), 'dim')}")
    lines.append(f"  {_status_glyph(accelerator.get('state'))}  {_field('Accelerator')} {accelerator.get('state', 'unknown')}  backend={paint(gpu.get('backend', 'unknown'), 'dim')}")
    lines.append(f"  {paint(_glyph('leaf'), 'fern')}  {_field('Stack')} {stack.get('model_count', 0)} local model(s)")
    lines.append(f"  {paint(_glyph('work'), 'peach')}  {_field('Runtime')} main={paint(defaults.get('main_model', 'unknown'), 'blossom')}  coder={paint(defaults.get('coder_model', 'unknown'), 'blossom')}")
    lines.append("")

    wo = state.get("work_order", {})
    latest = (state.get("task_loop", {}) or {}).get("latest_run") or {}
    lines.append(paint("Work", "butter", "semibold"))
    lines.append(f"  {paint(_glyph('work'), 'peach')}  {_field('Work Order')} {paint(wo.get('id') or 'none', 'blossom')}  {wo.get('state', 'unknown')}")
    lines.append(f"  {paint(_glyph('home'), 'fern')}  {_field('Latest Run')} {latest.get('name', 'none')}")
    lines.append(f"  {_status_glyph(benchmark.get('status'))}  {_field('Benchmark')} {benchmark.get('status', 'not_run')}  {benchmark.get('completed_cells', 0)}/{benchmark.get('planned_cells', 0)} cells")
    if isinstance(gross_hour, (int, float)) and isinstance(price, (int, float)):
        lines.append(f"  {paint(_glyph('flower'), 'fern')}  {_field('Local Value')} ${gross_hour:.4f}/h at ${price:g}/M output")
    else:
        lines.append(f"  {paint(_glyph('flower'), 'fern')}  {_field('Local Value')} n/a")
    lines.append("")

    lines.append(paint("Reference", "peach", "semibold"))
    ref_status = reference.get("status", "not registered")
    lines.append(f"  {_status_glyph(ref_status)}  {_field('Markdown')} {reference.get('markdown') or ref_status}")
    lines.append(f"  {_status_glyph(ref_status)}  {_field('LaTeX')} {reference.get('tex') or ref_status}")
    lines.append("")

    lines.append(paint("Next Actions", "mint", "semibold"))
    current_category = None
    items = state.get("next_actions", [])
    for index, item in enumerate(items, 1):
        category = item.get("category")
        if category and category != current_category:
            lines.append(f"  {paint(category, 'blossom', 'semibold')}")
            current_category = category
        glyph = item.get("glyph", "flower")
        lines.append(f"  {paint(str(index), 'blossom')}. {paint(_glyph(glyph), 'fern')} {paint(item['label'], 'leaf')}")
        lines.append(f"     {paint(item['command'], 'dim')}")
    lines.append("")

    return "\n".join(lines)


def render(state: dict) -> str:
    """Compatibility entrypoint retained for existing callers and tests."""
    return render_card(state)


def main() -> int:
    parser = argparse.ArgumentParser(prog="leafctl home")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--watch", type=float, default=0, help="refresh interval in seconds")
    parser.add_argument("--next", action="store_true", help="emit only the top next action")
    args = parser.parse_args()
    while True:
        state = build_state()
        if args.next:
            item = state["next_actions"][0]
            print(json.dumps(item, sort_keys=True) if args.json else f"{item['label']}: {item['command']}")
        else:
            if args.json:
                print(json.dumps(state, sort_keys=True, separators=(",", ":")))
            else:
                print(render_card(state), end="")
        if args.watch <= 0:
            break
        time.sleep(max(args.watch, 0.2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
