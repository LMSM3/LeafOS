#!/usr/bin/env python3
"""Friendly FlowerOS terminal surface for constructing model packs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


CORE = Path(__file__).resolve().parent
BRAND = CORE / "brand"
for directory in (CORE, BRAND):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from flower_palette import ascii_mode, glyph, paint  # noqa: E402
from pack_constructor import (  # noqa: E402
    COLOUR_PRESENTATION,
    DEFAULT_CATALOG_PATH,
    DEFAULT_PACK_DIR,
    PackConstructorError,
    build_pack,
    load_catalog,
    load_pack,
    select_items,
    slugify,
    validate_pack,
    write_pack,
)
from pack_identity import COLOURS, FLOWERS  # noqa: E402


def _bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    return f"{value / 1024**3:.1f} GiB"


def _motion_enabled(disabled: bool = False) -> bool:
    if disabled or not sys.stdout.isatty():
        return False
    reduced = any(
        os.environ.get(name) == "1"
        for name in ("NO_ANIMATION", "LEAF_NO_ANIMATION", "REDUCE_MOTION")
    )
    if reduced or os.environ.get("CI") or os.environ.get("TERM", "") == "dumb":
        return False
    return os.environ.get("LEAF_MOTION", "auto").lower() not in {
        "0", "off", "never", "none", "reduce", "reduced"
    }


def _bloom(label: str, *, disabled: bool = False, palette: str = "leaf") -> None:
    if not _motion_enabled(disabled):
        return
    frames = [("·", "."), ("❧", "/"), ("❀", "*"), ("✿", "*")]
    for unicode_frame, ascii_frame in frames:
        frame = glyph(unicode_frame, ascii_frame)
        print("\r" + paint(f"  {frame}  {label}", palette), end="", flush=True)
        time.sleep(0.07)
    print("\r" + " " * (len(label) + 8) + "\r", end="", flush=True)


def _banner() -> None:
    flower = glyph("❀", "*")
    leaf = glyph("❧", "/")
    print()
    print(paint(f"  {flower} Flower Pack Garden {leaf}", "lavender", "semibold"))
    print(paint("  Compose a small, honest model ecology. Grow it later.", "mint"))
    print()


def _catalog_rows(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in catalog["models"]:
        variant = model["variants"].get(model["default_quant"], {})
        rows.append({
            "slot": int(model["slot"]),
            "key": str(model["key"]),
            "role": str(model.get("role", "")),
            "default_quant": str(model["default_quant"]),
            "estimated_bytes": variant.get("estimated_bytes"),
            "experimental": bool(model.get("experimental")),
            "quants": list(model["variants"]),
        })
    return rows


def _print_catalog(catalog: dict[str, Any]) -> None:
    print(paint("  Available models", "sky", "semibold"))
    for row in _catalog_rows(catalog):
        marker = paint("experimental", "warn") if row["experimental"] else paint("stable", "leaf")
        print(
            f"  {row['slot']:>2}  {paint(row['key'], 'mint'):<36} "
            f"{row['default_quant']:<10} {_bytes(row['estimated_bytes']):>9}  {marker}"
        )
    print(paint("  Selection syntax: 1,3,6:Q2_K or catalog-key:QUANT", "dim"))


def _preview(pack: dict[str, Any], report: dict[str, Any], output: Path) -> None:
    identity = pack["identity"]
    palette = pack["presentation"]["palette_key"]
    symbol = glyph(identity["symbol"], "*")
    summary = report["summary"]
    rule = "-" * 62 if ascii_mode() else "─" * 62
    print(paint(f"  {rule}", palette))
    print(paint(f"  {symbol} {pack['name']}", palette, "semibold"))
    print(f"  id          {pack['id']}")
    print(f"  identity    {identity['flower']} / {identity['colour']}  {identity['colour_hex']}")
    print(f"  artifacts   {summary['unique_artifacts']} unique")
    print(f"  storage     {_bytes(summary['estimated_bytes'])}  ({_bytes(summary['disk_with_safety_bytes'])} with safety)")
    print(f"  residency   {pack['policy']['max_concurrent_local_models']} local model(s) max")
    print(f"  output      {output}")
    experiments = summary["experimental_confirmation_keys"]
    if experiments:
        print(paint(f"  experimental {', '.join(experiments)}", "warn"))
    for warning in report["warnings"]:
        print(paint(f"  ! {warning}", "warn"))
    print(paint(f"  {rule}", palette))


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(paint(f"  {prompt}{suffix}: ", "sky")).strip()
    return value or default


def _yes(prompt: str, default: bool = True) -> bool:
    marker = "Y/n" if default else "y/N"
    value = input(paint(f"  {prompt} [{marker}]: ", "sky")).strip().lower()
    if not value:
        return default
    return value in {"y", "yes"}


def _profile_size(catalog: dict[str, Any], profile: str) -> int | None:
    try:
        items = select_items(catalog, profile=profile, include_experimental=True)
    except PackConstructorError:
        return None
    by_key = {model["key"]: model for model in catalog["models"]}
    sizes = [by_key[item["catalog_key"]]["variants"][item["quant"]].get("estimated_bytes") for item in items]
    return sum(sizes) if all(isinstance(size, int) for size in sizes) else None


def _wizard(args: argparse.Namespace, catalog: dict[str, Any]) -> argparse.Namespace:
    _banner()
    args.name = _ask("Pack name", "My Flower Pack")
    args.pack_id = _ask("Pack id", slugify(args.name))
    print()
    profiles = [name for name in catalog["profiles"] if name != "default"]
    print(paint("  Start from a catalog profile", "sky", "semibold"))
    for index, profile in enumerate(profiles, start=1):
        description = catalog["profiles"][profile].get("description", "")
        print(f"  {index:>2}  {paint(profile, 'mint'):<30} {_bytes(_profile_size(catalog, profile)):>9}  {description}")
    print(f"  {len(profiles) + 1:>2}  {paint('custom selection', 'butter')}")
    raw = _ask("Choice", "1")
    try:
        choice = int(raw)
    except ValueError as error:
        raise PackConstructorError("profile choice must be a number") from error
    if choice == len(profiles) + 1:
        print()
        _print_catalog(catalog)
        custom = _ask("Models")
        args.model = [part.strip() for part in custom.split(",") if part.strip()]
        args.profile = None
    elif 1 <= choice <= len(profiles):
        args.profile = profiles[choice - 1]
        args.model = []
    else:
        raise PackConstructorError("profile choice is out of range")

    try:
        select_items(catalog, model_specs=args.model, profile=args.profile)
    except PackConstructorError as error:
        if "experimental" not in str(error) or not _yes("This selection contains dormant experimental models. Include them?", False):
            raise
        args.include_experimental = True

    print()
    print(paint("  Cosmetic identity (blank means deterministic surprise)", "blossom", "semibold"))
    args.flower = _ask("Flower: " + ", ".join(sorted(FLOWERS))) or None
    args.colour = _ask("Colour: " + ", ".join(sorted(COLOURS))) or None
    args.description = _ask("Description", f"A focused model ecology for {args.name}.")
    if _yes("Open advanced controls?", False):
        args.max_concurrent_local_models = int(_ask("Max concurrent local models", "1"))
        raw_ram = _ask("Maximum pack RAM GiB (blank = unspecified)")
        raw_vram = _ask("Maximum pack VRAM GiB (blank = unspecified)")
        args.max_ram_gib = float(raw_ram) if raw_ram else None
        args.max_vram_gib = float(raw_vram) if raw_vram else None
        args.allow_fallback = _yes("Allow explicit catalog fallbacks?", False)
    args.output = args.output or DEFAULT_PACK_DIR / f"{args.pack_id}.json"
    return args


def _create(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog)
    interactive = not args.name and not args.pack_id and not args.profile and not args.model
    if interactive:
        args = _wizard(args, catalog)
    elif not args.name:
        raise PackConstructorError("--name is required outside the interactive wizard")

    _bloom("composing pack requirements", disabled=args.no_animation or args.json, palette="lavender")
    pack = build_pack(
        catalog,
        name=args.name,
        pack_id=args.pack_id,
        description=args.description,
        model_specs=args.model,
        profile=args.profile,
        include_experimental=args.include_experimental,
        flower=args.flower,
        colour=args.colour,
        allow_fallback=args.allow_fallback,
        max_concurrent_local_models=args.max_concurrent_local_models,
        max_ram_gib=args.max_ram_gib,
        max_vram_gib=args.max_vram_gib,
    )
    report = validate_pack(pack, catalog)
    if not report["ok"]:
        raise PackConstructorError("; ".join(report["errors"]))
    output = (args.output or DEFAULT_PACK_DIR / f"{pack['id']}.json").expanduser().resolve()

    if args.json:
        payload = {"ok": True, "state": "preview" if args.dry_run else "ready", "output": str(output), "pack": pack, "validation": report}
        if not args.dry_run:
            if not args.yes:
                raise PackConstructorError("--json writes require --yes; use --dry-run to preview")
            write_pack(output, pack, force=args.force)
            payload["state"] = "written"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    _banner()
    _preview(pack, report, output)
    if args.dry_run:
        print(paint("  Preview only; no files written.", "info"))
        return 0
    if not args.yes and not _yes("Plant this pack?", True):
        print(paint("  Nothing written.", "dim"))
        return 0
    _bloom("planting pack manifest", disabled=args.no_animation, palette=pack["presentation"]["palette_key"])
    written = write_pack(output, pack, force=args.force)
    print(paint(f"  {glyph('✓', '[ok]')} Pack planted: {written}", "ok", "semibold"))
    experimental_flag = (
        " --include-experimental"
        if pack["requirements"]["experimental_confirmation_keys"]
        else ""
    )
    next_command = f'  Next: leafos models-install plan-pack "{written}"{experimental_flag}'
    print(paint(next_command, "dim"))
    return 0


def _validate(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog)
    pack = load_pack(args.pack)
    report = validate_pack(pack, catalog)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        state = glyph("✓", "[ok]") if report["ok"] else glyph("×", "[x]")
        colour = "ok" if report["ok"] else "error"
        print(paint(f"  {state} {args.pack}: {'valid' if report['ok'] else 'invalid'}", colour, "semibold"))
        for error in report["errors"]:
            print(paint(f"  x {error}", "error"))
        for warning in report["warnings"]:
            print(paint(f"  ! {warning}", "warn"))
        summary = report.get("summary", {})
        print(f"  artifacts {summary.get('unique_artifacts', 0)}   storage {_bytes(summary.get('estimated_bytes'))}")
    return 0 if report["ok"] else 1


def _catalog(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog)
    payload = {
        "catalog_version": catalog.get("catalog_version"),
        "profiles": catalog.get("profiles"),
        "models": _catalog_rows(catalog),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _banner()
        _print_catalog(catalog)
        print()
        print(paint("  Presets", "sky", "semibold"))
        for name, profile in catalog["profiles"].items():
            print(f"  {paint(name, 'mint'):<32} slots={','.join(map(str, profile['slots']))}  {_bytes(_profile_size(catalog, name))}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="leafos pack", description="Build installable FlowerOS model packs")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command")

    create = sub.add_parser("create", help="open the guided constructor or build from flags")
    create.add_argument("--name", default="")
    create.add_argument("--id", dest="pack_id", default="")
    create.add_argument("--description", default="")
    source = create.add_mutually_exclusive_group()
    source.add_argument("--profile", help="catalog profile such as runtime-default or viola-nocturne")
    source.add_argument("--model", action="append", default=[], metavar="MODEL[:QUANT]", help="select a model; repeat as needed")
    create.add_argument("--include-experimental", action="store_true")
    create.add_argument("--flower", choices=sorted(FLOWERS))
    create.add_argument("--colour", choices=sorted(COLOURS))
    create.add_argument("--allow-fallback", action="store_true")
    create.add_argument("--max-concurrent-local-models", type=int, default=1)
    create.add_argument("--max-ram-gib", type=float)
    create.add_argument("--max-vram-gib", type=float)
    create.add_argument("--output", type=Path)
    create.add_argument("--dry-run", action="store_true")
    create.add_argument("--yes", action="store_true", help="write without an interactive confirmation")
    create.add_argument("--force", action="store_true", help="replace an existing output file")
    create.add_argument("--json", action="store_true")
    create.add_argument("--no-animation", action="store_true")

    validate = sub.add_parser("validate", help="validate a pack against the canonical catalog")
    validate.add_argument("pack", type=Path)
    validate.add_argument("--json", action="store_true")

    catalog = sub.add_parser("catalog", help="show models, quantizations, sizes, and presets")
    catalog.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        values = ["create"]
    parser = build_parser()
    args = parser.parse_args(values)
    try:
        if args.command == "create":
            return _create(args)
        if args.command == "validate":
            return _validate(args)
        if args.command == "catalog":
            return _catalog(args)
        parser.print_help()
        return 0
    except (PackConstructorError, ValueError) as error:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        else:
            print(paint(f"  {glyph('×', '[x]')} {error}", "error"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
