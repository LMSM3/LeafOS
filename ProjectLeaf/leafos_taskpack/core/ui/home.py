#!/usr/bin/env python3
"""Terminal and JSON operator home backed by home_state."""

from __future__ import annotations

import argparse
import json
import time

from home_state import build_state


def render(state: dict) -> str:
    defaults = state["runtime"]["defaults"]
    operator = state.get("operator", {})
    benchmark = state.get("benchmark", {})
    best = benchmark.get("best_generation") or {}
    gross_hour = best.get("projected_gross_cloud_equivalent_usd_per_hour")
    price = benchmark.get("comparison", {}).get("comparison_output_usd_per_million")
    reference = state.get("reference", {})
    reference_path = reference.get("markdown")
    lines = [
        f"{operator.get('name', 'LeafOS')} Home", f"Engine       {operator.get('engine', 'LeafOS')}  stage={operator.get('stage', 'unknown')}", "",
        f"Readiness    {state['readiness']['status']}",
        f"Provider     {state['provider']['health']}  {state['provider']['endpoint']}",
        f"Accelerator  {state['accelerator']['state']}  backend={state['gpu']['backend']}",
        f"Stack        {state['stack']['model_count']} local model(s)",
        f"Runtime      main={defaults.get('main_model', 'unknown')}  coder={defaults.get('coder_model', 'unknown')}",
        f"Work Order   {state['work_order']['id'] or 'none'}  {state['work_order']['state']}",
        f"Latest Run   {(state['task_loop']['latest_run'] or {}).get('name', 'none')}",
        f"Benchmark    {benchmark.get('status', 'not_run')}  {benchmark.get('completed_cells', 0)}/{benchmark.get('planned_cells', 0)} cells",
        f"Local Value  {('$' + format(gross_hour, '.4f') + '/h') if isinstance(gross_hour, (int, float)) else 'n/a'}  at ${price:g}/M output" if isinstance(price, (int, float)) else "Local Value  n/a",
        f"Reference    {reference_path or reference.get('status', 'not registered')}",
        f"LaTeX        {reference.get('tex') or reference.get('status', 'not registered')}",
        "", "Next Actions",
    ]
    lines.extend(f"  {index}. {item['label']}: {item['command']}" for index, item in enumerate(state["next_actions"], 1))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(prog="leafctl home")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--watch", type=float, default=0)
    parser.add_argument("--next", action="store_true")
    args = parser.parse_args()
    while True:
        state = build_state()
        if args.next:
            item = state["next_actions"][0]
            print(json.dumps(item, sort_keys=True) if args.json else f"{item['label']}: {item['command']}")
        else:
            print(json.dumps(state, sort_keys=True, separators=(",", ":")) if args.json else render(state))
        if args.watch <= 0:
            break
        time.sleep(max(args.watch, 0.2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
