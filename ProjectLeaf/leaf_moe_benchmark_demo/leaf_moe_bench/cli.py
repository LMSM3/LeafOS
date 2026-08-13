"""Command-line surface for the isolated MOE-001 demonstration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .inventory import build_inventory
from .plan import build_plan, load_matrix
from .provider import probe_llama_bench
from .runner import ExecutionRefused, run_plan
from .util import atomic_write_json, default_catalog_path, default_model_root, read_json


def _default_matrix_path() -> Path:
    return Path(__file__).with_name("default_matrix.json").resolve()


def _optional_default_catalog() -> Optional[str]:
    try:
        return str(default_catalog_path())
    except FileNotFoundError:
        return None


def _print_inventory(payload: Dict[str, Any], output: Path) -> None:
    print(f"inventory : {payload['inventory_id']}")
    print(f"model root: {payload['model_root']}")
    print(f"artifacts : {payload['artifact_count']} ({payload['valid_gguf_count']} valid GGUF)")
    print(f"admissible : {payload['benchmark_admissible_count']} (identity gate only)")
    print(f"hash mode : {payload['hash_mode']}")
    print(f"report    : {output.expanduser().resolve()}")


def command_inventory(args: argparse.Namespace) -> int:
    payload = build_inventory(
        model_root=Path(args.model_root),
        catalog_path=Path(args.catalog),
        hash_mode=args.hash_mode,
        include_patterns=args.include,
    )
    output = Path(args.out)
    atomic_write_json(output, payload)
    _print_inventory(payload, output)
    return 0 if payload["valid_gguf_count"] else 1


def _print_provider(payload: Dict[str, Any], output: Path) -> None:
    print(f"provider  : {payload['executable']}")
    print(f"sha256    : {payload['executable_sha256']}")
    print(f"backends  : {', '.join(payload['loaded_backends']) or '<none reported>'}")
    print(f"devices   : {', '.join(payload['devices']) or '<none reported>'}")
    print(f"gpu ready : {payload['gpu_available']}")
    print(f"usable    : {payload['usable']}")
    print(f"report    : {output.expanduser().resolve()}")


def command_probe(args: argparse.Namespace) -> int:
    payload = probe_llama_bench(Path(args.llama_bench))
    output = Path(args.out)
    atomic_write_json(output, payload)
    _print_provider(payload, output)
    return 0 if payload["usable"] else 1


def _print_plan(payload: Dict[str, Any], output: Path) -> None:
    print(f"plan      : {payload['plan_id']}")
    print(f"matrix    : {payload['matrix_id']}")
    print(f"entries   : {payload['entry_count']} ({payload['ready_count']} provider-ready)")
    blocked = payload["entry_count"] - payload["ready_count"]
    print(f"blocked   : {blocked}")
    print(f"report    : {output.expanduser().resolve()}")


def command_plan(args: argparse.Namespace) -> int:
    inventory = read_json(Path(args.inventory))
    provider = read_json(Path(args.provider))
    matrix = load_matrix(Path(args.matrix))
    payload = build_plan(inventory, provider, matrix, artifact_paths=args.artifact)
    output = Path(args.out)
    atomic_write_json(output, payload)
    _print_plan(payload, output)
    return 0 if payload["entry_count"] else 1


def command_prepare(args: argparse.Namespace) -> int:
    output_directory = Path(args.out_dir).expanduser().resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    inventory_path = output_directory / "inventory.json"
    provider_path = output_directory / "provider.json"
    plan_path = output_directory / "plan.json"

    inventory = build_inventory(
        model_root=Path(args.model_root),
        catalog_path=Path(args.catalog),
        hash_mode=args.hash_mode,
        include_patterns=args.include,
    )
    provider = probe_llama_bench(Path(args.llama_bench))
    matrix = load_matrix(Path(args.matrix))
    plan = build_plan(inventory, provider, matrix, artifact_paths=args.artifact)
    atomic_write_json(inventory_path, inventory)
    atomic_write_json(provider_path, provider)
    atomic_write_json(plan_path, plan)

    _print_inventory(inventory, inventory_path)
    print()
    _print_provider(provider, provider_path)
    print()
    _print_plan(plan, plan_path)
    print("\nNo model was loaded and no inference benchmark was executed.")
    return 0 if inventory["valid_gguf_count"] and provider["usable"] and plan["entry_count"] else 1


def command_run(args: argparse.Namespace) -> int:
    plan = read_json(Path(args.plan))
    manifest = run_plan(
        plan=plan,
        output_root=Path(args.out_dir),
        execute=args.execute,
        selected_entry_ids=args.entry,
        allow_experimental_identity=args.allow_experimental_identity,
        timeout_seconds=args.timeout_seconds,
        telemetry_interval_seconds=args.telemetry_interval_seconds,
    )
    print(f"run       : {manifest['run_id']}")
    print(f"success   : {manifest['success']}")
    for result in manifest["results"]:
        print(f"  {result['status']:<10} {result['entry_id']}")
        for blocker in result.get("execution_blockers", []):
            print(f"    blocker: {blocker}")
    print(f"manifest  : {manifest['manifest_path']}")
    if manifest["success"]:
        return 0
    if any(item["status"] == "failed" or item["status"] == "timed_out" for item in manifest["results"]):
        return 1
    return 2


def _add_inventory_options(parser: argparse.ArgumentParser) -> None:
    catalog_default = _optional_default_catalog()
    parser.add_argument("--model-root", default=str(default_model_root()), help="Local GGUF model root")
    parser.add_argument(
        "--catalog",
        default=catalog_default,
        required=catalog_default is None,
        help="LeafOS model_catalog.json",
    )
    parser.add_argument(
        "--hash-mode",
        choices=["none", "sha256"],
        default="none",
        help="Full SHA-256 is promotion evidence but reads every model byte; default: none",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=None,
        help="Recursive filename pattern to include; repeatable; default: *.gguf",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="leaf-moe-bench",
        description="Isolated MOE-001 inventory and llama.cpp benchmark evidence demo.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inventory = sub.add_parser("inventory", help="Inspect local GGUF headers and catalog identity without loading models")
    _add_inventory_options(inventory)
    inventory.add_argument("--out", required=True, help="Inventory JSON destination")
    inventory.set_defaults(handler=command_inventory)

    probe = sub.add_parser("probe", help="Probe a llama-bench executable without loading a model")
    probe.add_argument("--llama-bench", required=True, help="Path to llama-bench or llama-bench.exe")
    probe.add_argument("--out", required=True, help="Provider probe JSON destination")
    probe.set_defaults(handler=command_probe)

    plan = sub.add_parser("plan", help="Build a deterministic benchmark plan from inventory and provider evidence")
    plan.add_argument("--inventory", required=True)
    plan.add_argument("--provider", required=True)
    plan.add_argument("--matrix", default=str(_default_matrix_path()))
    plan.add_argument("--artifact", action="append", default=None, help="Relative artifact path to include; repeatable")
    plan.add_argument("--out", required=True)
    plan.set_defaults(handler=command_plan)

    prepare = sub.add_parser("prepare", help="Run inventory, probe, and plan only; never execute inference")
    _add_inventory_options(prepare)
    prepare.add_argument("--llama-bench", required=True, help="Path to llama-bench or llama-bench.exe")
    prepare.add_argument("--matrix", default=str(_default_matrix_path()))
    prepare.add_argument("--artifact", action="append", default=None, help="Relative artifact path to include; repeatable")
    prepare.add_argument("--out-dir", required=True, help="Directory for inventory.json, provider.json, and plan.json")
    prepare.set_defaults(handler=command_prepare)

    run = sub.add_parser("run", help="Sequentially execute provider-ready entries from an existing plan")
    run.add_argument("plan", help="Benchmark plan JSON")
    run.add_argument("--out-dir", required=True, help="Root for immutable run evidence")
    run.add_argument("--entry", action="append", default=None, help="Entry ID to execute; repeatable; default: all")
    run.add_argument("--execute", action="store_true", help="Required acknowledgement that inference will run")
    run.add_argument(
        "--allow-experimental-identity",
        action="store_true",
        help="Allow measurement of a catalog/tensor identity mismatch; never removes its promotion blocker",
    )
    run.add_argument("--timeout-seconds", type=float, default=1800.0)
    run.add_argument("--telemetry-interval-seconds", type=float, default=0.5)
    run.set_defaults(handler=command_run)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (ExecutionRefused, FileNotFoundError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
