"""Canonical, declarative LeafOS model catalog."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass(frozen=True)
class QuantOption:
    key: str
    patterns: tuple[str, ...]
    estimated_bytes: Optional[int]
    format: str
    excludes: tuple[str, ...] = ()

    @property
    def pattern(self) -> str:
        return self.patterns[0]

    @property
    def exclude_patterns(self) -> tuple[str, ...]:
        return self.excludes

    @property
    def size_gb(self) -> Optional[float]:
        if self.estimated_bytes is None:
            return None
        return self.estimated_bytes / 1_000_000_000

    @property
    def label(self) -> str:
        return self.format

    @property
    def notes(self) -> str:
        return ""


@dataclass(frozen=True)
class ModelEntry:
    slot: int
    key: str
    nickname: str
    title: str
    repo_id: str
    local_dir: str
    role: str
    default_quant: str
    fallback_quants: tuple[str, ...]
    default_enabled: bool
    experimental: bool
    quant_options: Dict[str, QuantOption]
    notes: tuple[str, ...] = ()

    @property
    def variants(self) -> Dict[str, QuantOption]:
        return self.quant_options

    @property
    def default_patterns(self) -> tuple[str, ...]:
        return self.quant_options[self.default_quant].patterns

    @property
    def description(self) -> str:
        return self.role

    @property
    def disclaimer(self) -> str:
        return ""

    def label(self) -> str:
        return f"{self.nickname} ({self.role})"


@dataclass(frozen=True)
class Catalog:
    schema_version: int
    catalog_version: str
    storage: dict
    profiles: dict
    models: tuple[ModelEntry, ...]

    def by_key(self) -> Dict[str, ModelEntry]:
        return {model.key: model for model in self.models}

    def by_slot(self) -> Dict[int, ModelEntry]:
        return {model.slot: model for model in self.models}


def load_catalog(path: Optional[Path] = None) -> Catalog:
    source = path or Path(__file__).with_name("model_catalog.json")
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError(f"Unsupported model catalog schema: {data.get('schema_version')!r}")

    models: list[ModelEntry] = []
    seen_slots: set[int] = set()
    seen_keys: set[str] = set()
    for raw in data["models"]:
        slot = int(raw["slot"])
        key = str(raw["key"])
        if slot in seen_slots:
            raise ValueError(f"Duplicate model slot: {slot}")
        if key in seen_keys:
            raise ValueError(f"Duplicate model key: {key}")
        seen_slots.add(slot)
        seen_keys.add(key)

        variants = {
            variant_key: QuantOption(
                key=variant_key,
                patterns=tuple(variant["patterns"]),
                estimated_bytes=variant.get("estimated_bytes"),
                format=variant["format"],
                excludes=tuple(variant.get("exclude_patterns", [])),
            )
            for variant_key, variant in raw["variants"].items()
        }
        default_quant = raw["default_quant"]
        if default_quant not in variants:
            raise ValueError(f"{key}: default quant {default_quant!r} is not defined")
        for fallback in raw.get("fallback_quants", []):
            if fallback not in variants:
                raise ValueError(f"{key}: fallback quant {fallback!r} is not defined")

        models.append(
            ModelEntry(
                slot=slot,
                key=key,
                nickname=raw["nickname"],
                title=raw["title"],
                repo_id=raw["repo_id"],
                local_dir=raw["local_dir"],
                role=raw["role"],
                default_quant=default_quant,
                fallback_quants=tuple(raw.get("fallback_quants", [])),
                default_enabled=bool(raw["default_enabled"]),
                experimental=bool(raw["experimental"]),
                quant_options=variants,
                notes=tuple(raw.get("notes", [])),
            )
        )

    models.sort(key=lambda item: item.slot)
    valid_slots = {model.slot for model in models}
    for profile_name, profile in data["profiles"].items():
        unknown = set(profile["slots"]) - valid_slots
        if unknown:
            raise ValueError(f"Profile {profile_name!r} references unknown slots: {sorted(unknown)}")

    return Catalog(
        schema_version=data["schema_version"],
        catalog_version=data["catalog_version"],
        storage=data["storage"],
        profiles=data["profiles"],
        models=tuple(models),
    )


MODEL_CATALOG = load_catalog()
CATALOG: Dict[str, ModelEntry] = MODEL_CATALOG.by_key()


def get_model(key: str) -> ModelEntry:
    try:
        return CATALOG[key]
    except KeyError as exc:
        valid = ", ".join(CATALOG)
        raise KeyError(f"Unknown model '{key}'. Valid choices: {valid}") from exc


def get_slot(slot: int) -> ModelEntry:
    by_slot = MODEL_CATALOG.by_slot()
    try:
        return by_slot[slot]
    except KeyError as exc:
        raise KeyError(f"Unknown model slot {slot}. Valid slots: {sorted(by_slot)}") from exc
