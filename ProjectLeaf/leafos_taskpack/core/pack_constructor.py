#!/usr/bin/env python3
"""Build and validate simple, installable LeafOS flower packs.

The constructor deliberately stops at the installer boundary.  It selects
catalog artifacts, records honest storage/resource requirements, and applies a
visual flower identity.  It does not grant authority or manufacture runtime
model groups, profiles, personas, or routing claims.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable

from pack_identity import COLOURS, FLOWERS, build_identity


TASKPACK_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = TASKPACK_ROOT.parent
DEFAULT_CATALOG_PATH = PROJECT_ROOT / "leaf_model_installer" / "leaf_models" / "model_catalog.json"
DEFAULT_PACK_DIR = TASKPACK_ROOT / "config" / "packs"
PACK_SCHEMA = "leafos.model-pack.v1"
CONSTRUCTOR_VERSION = 1
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Presentation metadata stays cosmetic.  Keys point back to the canonical
# FlowerOS palette in core/brand/flower_palette.py.
COLOUR_PRESENTATION: dict[str, dict[str, Any]] = {
    "red": {"palette_key": "blossom", "hex": "#FFB7C5", "ansi_256": 217},
    "orange": {"palette_key": "peach", "hex": "#FFD2B7", "ansi_256": 223},
    "yellow": {"palette_key": "butter", "hex": "#FFFAB5", "ansi_256": 229},
    "green": {"palette_key": "leaf", "hex": "#77DD77", "ansi_256": 114},
    "blue": {"palette_key": "sky", "hex": "#B2DFFF", "ansi_256": 153},
    "purple": {"palette_key": "lavender", "hex": "#CCB2FF", "ansi_256": 183},
    "pink": {"palette_key": "blossom", "hex": "#FFB7C5", "ansi_256": 217},
    "gray": {"palette_key": "dim", "hex": "#B8B8B8", "ansi_256": 250},
    "white": {"palette_key": "mint", "hex": "#F4FFF7", "ansi_256": 255},
    "black": {"palette_key": "forest", "hex": "#228B22", "ansi_256": 28},
}


class PackConstructorError(ValueError):
    """Raised when a requested pack cannot satisfy the catalog contract."""


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "flower-pack"


def load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> dict[str, Any]:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise PackConstructorError(f"unable to read model catalog {path}: {error}") from error
    models = catalog.get("models")
    profiles = catalog.get("profiles")
    if not isinstance(models, list) or not models:
        raise PackConstructorError("model catalog has no models")
    if not isinstance(profiles, dict):
        raise PackConstructorError("model catalog has no profiles")
    return catalog


def _models_by_key(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(model["key"]): model for model in catalog["models"]}


def _models_by_slot(catalog: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(model["slot"]): model for model in catalog["models"]}


def _split_spec(raw: str) -> tuple[str, str | None]:
    value = raw.strip()
    if not value:
        raise PackConstructorError("model selections must not be empty")
    if ":" not in value:
        return value, None
    key, quant = value.rsplit(":", 1)
    if not key or not quant:
        raise PackConstructorError(f"invalid model selection {raw!r}; use MODEL[:QUANT]")
    return key, quant


def select_items(
    catalog: dict[str, Any],
    *,
    model_specs: Iterable[str] = (),
    profile: str | None = None,
    include_experimental: bool = False,
) -> list[dict[str, Any]]:
    """Resolve user selections to deduplicated installer items."""
    specs = list(model_specs)
    if specs and profile:
        raise PackConstructorError("choose either a catalog profile or explicit models, not both")
    if not specs:
        selected_profile = profile or "runtime-default"
        profile_data = catalog["profiles"].get(selected_profile)
        if not isinstance(profile_data, dict) or not isinstance(profile_data.get("slots"), list):
            valid = ", ".join(sorted(catalog["profiles"]))
            raise PackConstructorError(f"unknown catalog profile {selected_profile!r}; valid: {valid}")
        specs = [str(slot) for slot in profile_data["slots"]]

    by_key = _models_by_key(catalog)
    by_slot = _models_by_slot(catalog)
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in specs:
        selector, quant_override = _split_spec(raw)
        model = by_slot.get(int(selector)) if selector.isdigit() else by_key.get(selector)
        if model is None:
            valid = ", ".join(sorted(by_key))
            raise PackConstructorError(f"unknown model {selector!r}; valid catalog keys: {valid}")
        experimental = bool(model.get("experimental"))
        if experimental and not include_experimental:
            raise PackConstructorError(
                f"{model['key']} is experimental; repeat with --include-experimental"
            )
        quant = quant_override or str(model.get("default_quant", ""))
        variants = model.get("variants") or {}
        if quant not in variants:
            valid = ", ".join(variants)
            raise PackConstructorError(
                f"{model['key']} does not provide {quant!r}; valid quantizations: {valid}"
            )
        dedup = (str(model["key"]), quant)
        if dedup in seen:
            continue
        seen.add(dedup)
        item: dict[str, Any] = {"catalog_key": model["key"], "quant": quant}
        if experimental:
            item["experimental"] = True
        items.append(item)
    if not items:
        raise PackConstructorError("a pack requires at least one model artifact")
    return items


def _requirements(catalog: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    by_key = _models_by_key(catalog)
    total = 0
    known = True
    experimental: set[str] = set()
    for item in items:
        model = by_key[item["catalog_key"]]
        variant = model["variants"][item["quant"]]
        size = variant.get("estimated_bytes")
        if not isinstance(size, int):
            known = False
        else:
            total += size
        if bool(item.get("experimental")) or bool(model.get("experimental")):
            experimental.add(str(model["key"]))
    return {
        "catalog_version": str(catalog.get("catalog_version", "unknown")),
        "unique_artifacts": len(items),
        "estimated_bytes": total if known else None,
        "disk_with_safety_bytes": math.ceil(total * 1.15) if known else None,
        "experimental_confirmation_keys": sorted(experimental),
    }


def build_pack(
    catalog: dict[str, Any],
    *,
    name: str,
    pack_id: str | None = None,
    description: str = "",
    model_specs: Iterable[str] = (),
    profile: str | None = None,
    include_experimental: bool = False,
    flower: str | None = None,
    colour: str | None = None,
    allow_fallback: bool = False,
    max_concurrent_local_models: int = 1,
    max_ram_gib: float | None = None,
    max_vram_gib: float | None = None,
) -> dict[str, Any]:
    specs = list(model_specs)
    clean_name = name.strip()
    if not clean_name:
        raise PackConstructorError("pack name must not be empty")
    clean_id = pack_id.strip() if pack_id else slugify(clean_name)
    if not SLUG.fullmatch(clean_id):
        raise PackConstructorError("pack id must be a lowercase hyphenated slug")
    if max_concurrent_local_models < 1:
        raise PackConstructorError("max concurrent local models must be at least 1")
    for label, value in (("max RAM", max_ram_gib), ("max VRAM", max_vram_gib)):
        if value is not None and value <= 0:
            raise PackConstructorError(f"{label} must be positive")

    items = select_items(
        catalog,
        model_specs=specs,
        profile=profile,
        include_experimental=include_experimental,
    )
    identity = build_identity(clean_id, flower, colour)
    style = COLOUR_PRESENTATION[identity["colour"]]
    identity = {
        **identity,
        "colour_hex": style["hex"],
        "ansi_256": style["ansi_256"],
    }
    policy: dict[str, Any] = {
        "parallel_load": max_concurrent_local_models > 1,
        "require_grouped_activation": True,
        "max_concurrent_local_models": max_concurrent_local_models,
    }
    if max_ram_gib is not None:
        policy["max_pack_ram_gib"] = max_ram_gib
    if max_vram_gib is not None:
        policy["max_pack_vram_gib"] = max_vram_gib

    selected_profile = profile or ("custom" if specs else "runtime-default")
    return {
        "schema": PACK_SCHEMA,
        "id": clean_id,
        "name": clean_name,
        "version": "0.1.0",
        "description": description.strip() or f"A LeafOS flower pack built from {selected_profile}.",
        "compatible_catalog_min": str(catalog.get("catalog_version", "unknown")),
        "default": False,
        "identity": identity,
        "presentation": {
            "palette_key": style["palette_key"],
            "motion": "garden-bloom-v1",
            "capability_bearing": False,
            "indicator_evidence_contract": "leafos.subsystem_indicator_evidence.v1",
        },
        "source": {
            "constructor": "leafos.pack-constructor",
            "constructor_version": CONSTRUCTOR_VERSION,
            "selection": selected_profile,
        },
        "policy": policy,
        "requirements": _requirements(catalog, items),
        "install": {
            "allow_fallback": bool(allow_fallback),
            "items": items,
        },
        "notes": [
            "Pack identity does not grant capability; an active indicator may bind its symbol to bounded subsystem-presence evidence.",
            "Installer artifacts are deduplicated by catalog key and quantization.",
            "Runtime profiles and groups are intentionally not generated by the simple constructor.",
        ],
    }


def validate_pack(pack: Any, catalog: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(pack, dict):
        return {"ok": False, "errors": ["pack must be a JSON object"], "warnings": []}
    if pack.get("schema") != PACK_SCHEMA:
        errors.append(f"schema must be {PACK_SCHEMA!r}")
    pack_id = pack.get("id")
    if not isinstance(pack_id, str) or not SLUG.fullmatch(pack_id):
        errors.append("id must be a lowercase hyphenated slug")
    if not isinstance(pack.get("name"), str) or not pack["name"].strip():
        errors.append("name must be a non-empty string")
    identity = pack.get("identity")
    if not isinstance(identity, dict):
        errors.append("identity must be an object")
    else:
        if identity.get("flower") not in FLOWERS:
            warnings.append("identity.flower is outside the constructor's canonical flower set")
        if identity.get("colour") not in COLOURS:
            warnings.append("identity.colour is outside the constructor's canonical colour set")
        canonical_symbol = FLOWERS.get(identity.get("flower"), {}).get("symbol")
        if canonical_symbol and identity.get("symbol") != canonical_symbol:
            warnings.append("identity.symbol differs from the canonical flower symbol")

    install = pack.get("install")
    items = install.get("items") if isinstance(install, dict) else None
    if not isinstance(items, list) or not items:
        errors.append("install.items must be a non-empty array")
        items = []
    by_key = _models_by_key(catalog)
    seen: set[tuple[str, str]] = set()
    by_model: dict[str, set[str]] = {}
    total = 0
    known = True
    experimental: set[str] = set()
    for index, item in enumerate(items):
        label = f"install.items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        key = item.get("catalog_key")
        quant = item.get("quant")
        model = by_key.get(key)
        if model is None:
            errors.append(f"{label}.catalog_key is unknown: {key!r}")
            continue
        variants = model.get("variants") or {}
        if quant not in variants:
            errors.append(f"{label}.quant {quant!r} is unavailable for {key}")
            continue
        dedup = (str(key), str(quant))
        if dedup in seen:
            warnings.append(f"duplicate artifact {key}:{quant}; the installer will deduplicate it")
        seen.add(dedup)
        by_model.setdefault(str(key), set()).add(str(quant))
        if bool(item.get("experimental")) or bool(model.get("experimental")):
            experimental.add(str(key))
    total = 0
    for key, quant in seen:
        size = by_key[key]["variants"][quant].get("estimated_bytes")
        if not isinstance(size, int):
            known = False
        else:
            total += size
    for key, quants in sorted(by_model.items()):
        if len(quants) > 1:
            warnings.append(f"{key} includes {len(quants)} quantizations; keep only tiers you expect to use")

    policy = pack.get("policy")
    if not isinstance(policy, dict):
        warnings.append("policy is missing; safe runtime residency limits will be unknown")
    else:
        concurrent = policy.get("max_concurrent_local_models")
        if not isinstance(concurrent, int) or concurrent < 1:
            errors.append("policy.max_concurrent_local_models must be a positive integer")
        if concurrent and concurrent > 1:
            warnings.append("parallel local residency requires runtime RAM/VRAM enforcement")
    if known and total >= 100 * 1024**3:
        warnings.append("pack exceeds 100 GiB; offer it in core/quality/experimental tiers")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "pack_id": pack_id,
            "unique_artifacts": len(seen),
            "estimated_bytes": total if known else None,
            "disk_with_safety_bytes": math.ceil(total * 1.15) if known else None,
            "experimental_confirmation_keys": sorted(experimental),
        },
    }


def load_pack(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise PackConstructorError(f"unable to read pack {path}: {error}") from error


def write_pack(path: Path, pack: dict[str, Any], *, force: bool = False) -> Path:
    target = path.expanduser().resolve()
    if target.exists() and not force:
        raise PackConstructorError(f"refusing to overwrite existing pack: {target}; use --force")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(pack, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        try:
            Path(temporary).unlink(missing_ok=True)
        except OSError:
            pass
    return target
