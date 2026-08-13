from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from .catalog import CATALOG, get_model
from .downloader import (
    DEFAULT_MAX_WORKERS,
    DownloadError,
    DownloadReport,
    benchmark_download,
    benchmark_to_dict,
    check_disk_space,
    download_model,
    estimate_size_gb,
    list_matching_files,
    matching_urls,
    resolve_patterns,
    verify_local_files,
)
from .ui import UI
from .preflight import animate_loading, make_preflight_report

ui = UI()


def _default_model_dir() -> Path:
    env_dir = os.environ.get("LEAF_MODEL_DIR")
    if env_dir:
        return Path(env_dir).expanduser()
    return Path.cwd() / "models"


def _bytes_to_gb(value: int) -> str:
    return f"{value / (1024 ** 3):.2f} GB"


def _print_report(report: DownloadReport) -> None:
    status = "VERIFIED" if report.success else "FAILED"
    color = "green" if report.success else "red"
    ui.print(f"[{color}]Status: {status}[/{color}]")
    if report.nickname:
        role = f" - {report.role}" if report.role else ""
        ui.print(f"Identity: {report.nickname}{role}")
    ui.print(f"Target:   {report.target_dir}")
    ui.print(f"Manifest: {report.manifest_path}")
    ui.print(f"Expected files: {len(report.expected_files)}")

    if report.elapsed_seconds is not None:
        accel = "Xet high-performance" if report.high_performance else "default transport"
        workers = f", {report.max_workers} workers" if report.max_workers else ""
        downloaded = _bytes_to_gb(report.downloaded_bytes) if report.downloaded_bytes else "0 bytes"
        speed = f"{report.mbps:.2f} MB/s" if report.mbps is not None else "n/a (likely cached)"
        ui.print(f"Throughput: {speed} ({downloaded} in {report.elapsed_seconds:.1f}s, {accel}{workers})")

    for item in report.local_files:
        marker = "OK" if item.exists and item.repo_file not in report.tiny_files else "BAD"
        size = _bytes_to_gb(item.bytes) if item.bytes else "0 bytes"
        ui.print(f"  {marker:3} {size:>10}  {item.local_path}")
        if item.sha256:
            ui.print(f"      sha256: {item.sha256}")

    if report.missing_files:
        ui.print("[red]Missing files:[/red]")
        for name in report.missing_files:
            ui.print(f"  - {name}")
    if report.tiny_files:
        ui.print("[red]Suspiciously tiny files:[/red]")
        for name in report.tiny_files:
            ui.print(f"  - {name}")


def print_catalog() -> None:
    ui.banner()
    try:
        from rich.table import Table

        table = Table(title="Allowlisted model catalog")
        table.add_column("Key")
        table.add_column("Repository")
        table.add_column("Quant options")
        table.add_column("Default")
        for key, model in CATALOG.items():
            quants = ", ".join(model.quant_options) if model.quant_options else "all *.gguf"
            table.add_row(key, model.repo_id, quants, ", ".join(model.default_patterns))
        ui.console.print(table) if ui.console else print(table)
    except Exception:
        for key, model in CATALOG.items():
            ui.print(f"{key}: {model.repo_id}")


def run_doctor() -> int:
    ui.banner()
    ui.print(f"Python: {sys.version.split()[0]}")
    try:
        import huggingface_hub

        ui.print(f"huggingface_hub: {huggingface_hub.__version__}")
    except Exception as exc:
        ui.print(f"huggingface_hub: missing ({exc})")
        return 1

    hf_cli = shutil_which("huggingface-cli")
    ui.print(f"huggingface-cli: {hf_cli or 'not found, but Python API can still work'}")
    ui.print(f"Default model root: {_default_model_dir().expanduser().resolve()}")
    ui.print("Tip: private/gated repos may require: huggingface-cli login")
    return 0


def shutil_which(name: str) -> Optional[str]:
    from shutil import which

    return which(name)


def download_command(args: argparse.Namespace) -> int:
    model = get_model(args.model)
    patterns = resolve_patterns(model, args.quant)
    dest = Path(args.dest).expanduser().resolve()
    target = dest / model.local_dir
    estimate = estimate_size_gb(model, args.quant)

    ui.banner()
    if model.nickname:
        ui.print(f"[bold cyan]{model.nickname}[/bold cyan] ({model.role}) -> {model.key}")
    ui.print(f"Model: {model.title}")
    ui.print(f"Repo:  {model.repo_id}")
    ui.print(f"Files: {', '.join(patterns)}")
    ui.print(f"Dest:  {target}")
    if model.disclaimer:
        ui.print(f"[yellow]{model.disclaimer}[/yellow]")

    try:
        remote_files = list_matching_files(model, patterns, revision=args.revision)
    except DownloadError as exc:
        ui.print(f"[red]Remote inspection failed before download:[/red] {exc}")
        return 1
    if not remote_files:
        ui.print("[red]No remote files match the selected pattern. Refusing to pretend this worked.[/red]")
        return 1
    ui.print(f"Remote matches: {len(remote_files)}")
    for name in remote_files[:10]:
        ui.print(f"  - {name}")
    if len(remote_files) > 10:
        ui.print(f"  ... {len(remote_files) - 10} more")

    ok, space_msg = check_disk_space(dest, estimate)
    ui.print(space_msg)
    if not ok and not args.force:
        ui.print("[red]Not enough free disk space for a sane download buffer. Refusing, because apparently I have to be the adult.[/red]")
        return 2

    if args.dry_run:
        ui.print("Dry run only. No download performed, no success implied.")
        return 0

    if not args.yes:
        if not ui.confirm("Download and verify these GGUF files now?", default=False):
            ui.print("Cancelled. No download performed.")
            return 130

    try:
        report = download_model(
            model,
            dest,
            patterns,
            revision=args.revision,
            min_bytes=args.min_bytes,
            compute_hash=args.hash,
            max_workers=getattr(args, "max_workers", None),
            high_performance=not getattr(args, "no_accel", False),
        )
    except DownloadError as exc:
        ui.print(f"[red]Download failed:[/red] {exc}")
        ui.print("No fake victory lap. Check the manifest if one was written, then try `huggingface-cli login` if auth is the issue.")
        return 1

    _print_report(report)
    if report.success:
        ui.print("[green]Download verified. Actual files exist where the CLI says they exist.[/green]")
        return 0
    return 1


def verify_command(args: argparse.Namespace) -> int:
    model = get_model(args.model)
    patterns = resolve_patterns(model, args.quant)
    dest = Path(args.dest).expanduser().resolve()
    ui.banner()
    ui.print(f"Verifying local target for {model.key}")
    try:
        report = verify_local_files(
            model,
            dest,
            patterns,
            revision=args.revision,
            min_bytes=args.min_bytes,
            compute_hash=args.hash,
        )
    except DownloadError as exc:
        ui.print(f"[red]Verification failed before local check:[/red] {exc}")
        return 1
    _print_report(report)
    return 0 if report.success else 1


def inspect_command(args: argparse.Namespace) -> int:
    model = get_model(args.model)
    patterns = resolve_patterns(model, args.quant)
    ui.print(f"Inspecting {model.repo_id} for: {', '.join(patterns)}")
    try:
        files = list_matching_files(model, patterns, revision=args.revision)
    except DownloadError as exc:
        ui.print(f"[red]Inspect failed:[/red] {exc}")
        return 1
    if not files:
        ui.print("No matching files found. Either the pattern changed or the repository is being adorable.")
        return 1
    for file in files:
        ui.print(file)
    ui.print(f"Total matches: {len(files)}")
    return 0


def urls_command(args: argparse.Namespace) -> int:
    model = get_model(args.model)
    patterns = resolve_patterns(model, args.quant)
    try:
        urls = matching_urls(model, patterns, revision=args.revision)
    except DownloadError as exc:
        ui.print(f"[red]URL lookup failed:[/red] {exc}")
        return 1
    if not urls:
        ui.print("No matching URLs found.")
        return 1
    for url in urls:
        ui.print(url)
    ui.print("Use Invoke-WebRequest on one of those resolved file URLs, not the Hugging Face homepage. Civilization narrowly survives.")
    return 0


def benchmark_command(args: argparse.Namespace) -> int:
    model = get_model(args.model)
    patterns = resolve_patterns(model, args.quant)
    high_perf = not getattr(args, "no_accel", False)
    sample_bytes = int(args.sample_mb * 1024 * 1024)

    ui.banner()
    if model.nickname:
        ui.print(f"[bold cyan]{model.nickname}[/bold cyan] ({model.role}) -> {model.key}")
    transport = "Xet high-performance" if high_perf else "default transport"
    ui.print(f"Benchmarking {model.repo_id} using {transport}")
    ui.print(f"Sampling first {args.sample_mb:g} MB of a matching file (no full download).")

    try:
        result = benchmark_download(
            model,
            patterns,
            revision=args.revision,
            sample_bytes=sample_bytes,
            high_performance=high_perf,
        )
    except DownloadError as exc:
        ui.print(f"[red]Benchmark failed:[/red] {exc}")
        return 1

    speed = f"{result.mbps:.2f} MB/s" if result.mbps is not None else "n/a"
    ui.print(f"Sample file: {result.sample_file}")
    ui.print(
        f"[green]Measured throughput:[/green] {speed} "
        f"({result.sampled_bytes / (1024 ** 2):.1f} MB in {result.elapsed_seconds:.2f}s)"
    )
    if args.json_out:
        destination = Path(args.json_out).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(benchmark_to_dict(result), indent=2) + "\n", encoding="utf-8")
        ui.print(f"Benchmark report: {destination}")
    return 0


def preflight_command(args: argparse.Namespace) -> int:
    model = get_model(args.model)
    dest = Path(args.dest).expanduser().resolve()

    ui.banner()
    ui.print(f"Preflight model: {model.key}")
    ui.print(f"Destination root: {dest}")
    ui.print(f"Expected target:   {dest / model.local_dir}")

    if args.wait_seconds > 0:
        animate_loading(args.wait_seconds)

    report, messages = make_preflight_report(model, dest, flush_dns=args.flush_dns)

    ui.print("[bold]System[/bold]")
    ui.print(f"  OS:      {report.platform_system} {report.platform_release} ({report.machine})")
    ui.print(f"  Python:  {report.python_version}")
    ui.print(f"  CWD:     {report.cwd}")

    ui.print("[bold]NVIDIA[/bold]")
    if report.gpus:
        for gpu in report.gpus:
            ui.print(f"  {gpu.name}, driver {gpu.driver_version}, {gpu.memory_total_mb} MB")
    else:
        ui.print("  NVIDIA SMI not found or no GPUs reported.")

    ui.print("[bold]RAM[/bold]")
    if report.ram_modules:
        ram_line = ", ".join(f"{item.capacity_gb:g}GB x {item.count}" for item in report.ram_modules)
        ui.print(f"  Modules: {ram_line}")
    if report.ram_total_gb is not None:
        ui.print(f"  Total:   {report.ram_total_gb:g} GB")
    else:
        ui.print("  Total:   unknown")

    rec = report.recommendation
    if rec.recommended_quant:
        ui.print(f"[green]Recommended quant:[/green] {rec.recommended_quant}")
    else:
        ui.print("[yellow]Recommended quant:[/yellow] not applicable for this model entry")
    ui.print(f"Reason: {rec.reason}")

    ui.print("[bold]Download location verification target[/bold]")
    ui.print(f"  {report.target_dir}")
    ui.print(f"  Preflight report: {report.report_path}")

    if args.flush_dns:
        dns = report.dns_flush
        color = "green" if dns.success else "red"
        ui.print(f"[{color}]DNS flush requested: {'OK' if dns.success else 'FAILED'}[/{color}]")
        for line in dns.attempted:
            ui.print(f"  tried: {line}")
        for line in dns.messages:
            ui.print(f"  {line}")
        if not dns.success:
            ui.print("[red]Preflight failed because DNS flush was explicitly requested and did not complete.[/red]")
            return 1

    if messages:
        ui.print("[yellow]Notes:[/yellow]")
        for msg in messages:
            ui.print(f"  - {msg}")

    ui.print("Preflight complete. This proves the scan/report finished, not that any model downloaded. Miracles remain unavailable.")
    return 0


def interactive() -> int:
    ui.banner()
    ui.print("1) Download Qwen reasoning distill GGUF")
    ui.print("2) Download Gemma4 coder GGUF by quant")
    ui.print("3) List catalog")
    ui.print("4) Inspect remote matching files")
    ui.print("5) Print direct resolved URLs")
    ui.print("6) Verify local download location")
    ui.print("7) System preflight + target report")
    ui.print("0) Exit")
    choice = ui.choice("Choose", ["1", "2", "3", "4", "5", "6", "7", "0"], default="2")

    if choice == "0":
        return 0
    if choice == "3":
        print_catalog()
        return 0

    if choice == "1":
        model_key = "qwen-opus-reasoning"
        quant = None
    else:
        model_key = "gemma4-coder"
        model = get_model(model_key)
        ui.print("Available quantizations:")
        for key, option in model.quant_options.items():
            size = f"{option.size_gb:.2f} GB" if option.size_gb else "size unknown"
            ui.print(f"  {key:7}  {option.label:24}  {size:>10}  {option.notes}")
        quant = ui.choice("Quant", list(model.quant_options), default="Q4_K_M")

    dest = ui.prompt("Model directory", default=str(_default_model_dir()))

    ns = argparse.Namespace(
        model=model_key,
        quant=quant,
        dest=dest,
        yes=False,
        force=False,
        dry_run=False,
        revision="main",
        min_bytes=1024 * 1024,
        hash=False,
        max_workers=DEFAULT_MAX_WORKERS,
        no_accel=False,
    )
    if choice == "4":
        return inspect_command(ns)
    if choice == "5":
        return urls_command(ns)
    if choice == "6":
        return verify_command(ns)
    if choice == "7":
        ns.wait_seconds = 12
        ns.flush_dns = False
        return preflight_command(ns)
    return download_command(ns)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="leaf-models",
        description="Safe interactive downloader for a tiny allowlist of local GGUF model packages.",
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list", help="Show allowlisted models")
    sub.add_parser("doctor", help="Check local Python and Hugging Face tooling")

    def add_model_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--model", choices=sorted(CATALOG), default="gemma4-coder")
        p.add_argument("--quant", default=None, help="Quant key, for models that support it. Example: Q4_K_M")
        p.add_argument("--revision", default="main")

    def add_verify_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--min-bytes", type=int, default=1024 * 1024, help="Minimum believable GGUF file size. Default: 1 MiB")
        p.add_argument("--hash", action="store_true", help="Compute SHA256 for verified files. Slow but useful.")

    p_download = sub.add_parser("download", help="Download selected model files, then verify the exact local location")
    add_model_args(p_download)
    p_download.add_argument("--dest", default=str(_default_model_dir()), help="Destination root directory")
    p_download.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    p_download.add_argument("--force", action="store_true", help="Ignore disk-space warning")
    p_download.add_argument("--dry-run", action="store_true", help="Show plan without downloading")
    p_download.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=f"Concurrent file workers for downloads. Default: {DEFAULT_MAX_WORKERS}",
    )
    p_download.add_argument(
        "--no-accel",
        action="store_true",
        help="Disable the Xet high-performance transport (use the slow default path)",
    )
    add_verify_args(p_download)

    p_verify = sub.add_parser("verify", help="Verify existing local files against the selected remote pattern")
    add_model_args(p_verify)
    p_verify.add_argument("--dest", default=str(_default_model_dir()), help="Destination root directory")
    add_verify_args(p_verify)

    p_inspect = sub.add_parser("inspect", help="List remote files matching the selected model/pattern")
    add_model_args(p_inspect)

    p_urls = sub.add_parser("urls", help="Print resolved Hugging Face file URLs for matching files")
    add_model_args(p_urls)

    p_benchmark = sub.add_parser(
        "benchmark",
        help="Measure real download throughput by sampling a bounded byte range (no full download)",
    )
    add_model_args(p_benchmark)
    p_benchmark.add_argument(
        "--sample-mb",
        type=float,
        default=48.0,
        help="How many MB to sample for the throughput measurement. Default: 48",
    )
    p_benchmark.add_argument(
        "--no-accel",
        action="store_true",
        help="Benchmark the slow default transport instead of Xet high-performance",
    )
    p_benchmark.add_argument("--json-out", default="", help="write a machine-readable bounded benchmark report")

    p_preflight = sub.add_parser("preflight", help="Scan system info, recommend a quant, and write a target-location report")
    add_model_args(p_preflight)
    p_preflight.add_argument("--dest", default=str(_default_model_dir()), help="Destination root directory")
    p_preflight.add_argument("--wait-seconds", type=float, default=12.0, help="Loading animation duration. Default: 12 seconds")
    p_preflight.add_argument("--flush-dns", action="store_true", help="Explicitly flush DNS cache and fail if that requested cleanup fails")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Compatibility entrypoint for callers pinned to leaf_models.cli."""
    from .install_cli import main as install_main

    return install_main(argv)


if __name__ == "__main__":
    from .install_cli import main as install_main

    raise SystemExit(install_main())
