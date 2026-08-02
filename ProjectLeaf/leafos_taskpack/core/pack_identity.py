#!/usr/bin/env python3
"""Deterministic cosmetic identity for LeafOS model packs.

This module assigns only display-level attributes to packs:
  - flower (visual seed)
  - colour (visual hue)
  - symbol (derived from flower; never a separate decision axis)
  - visual_family (broad rendering hint, e.g. "monochrome", "cool")

It must NOT assign or influence:
  - persona
  - capability
  - authority
  - confidence
  - priority
  - assignment
  - routing
  - validation policy
  - runtime state

Randomization is limited to *flower* and *colour*. The symbol follows the
flower deterministically. A stable seed derived from the pack id makes the
default identity reproducible, while different pack ids still receive
distinct cosmetic identities.
"""

from __future__ import annotations

import random
from typing import Any


# Unicode floral/geometric symbols from non-emoji blocks.
FLOWERS: dict[str, dict[str, str]] = {
    "rose":     {"symbol": "✿", "family": "classic"},
    "violet":   {"symbol": "❀", "family": "classic"},
    "fern":     {"symbol": "❧", "family": "foliage"},
    "lotus":    {"symbol": "✾", "family": "classic"},
    "daisy":    {"symbol": "❁", "family": "classic"},
    "lavender": {"symbol": "✽", "family": "classic"},
    "clover":   {"symbol": "☘", "family": "foliage"},
    "thistle":  {"symbol": "✤", "family": "classic"},
    "sage":     {"symbol": "✳", "family": "foliage"},
    "lily":     {"symbol": "✾", "family": "classic"},
    "poppy":    {"symbol": "✿", "family": "classic"},
    "amaranth": {"symbol": "❀", "family": "classic"},
}

COLOURS: dict[str, dict[str, str]] = {
    "red":      {"family": "warm"},
    "orange":   {"family": "warm"},
    "yellow":   {"family": "warm"},
    "green":    {"family": "cool"},
    "blue":     {"family": "cool"},
    "purple":   {"family": "cool"},
    "pink":     {"family": "warm"},
    "gray":     {"family": "monochrome"},
    "white":    {"family": "monochrome"},
    "black":    {"family": "monochrome"},
}


def _validate(flower: str | None, colour: str | None) -> None:
    if flower is not None and flower not in FLOWERS:
        raise ValueError(f"unknown flower: {flower!r}")
    if colour is not None and colour not in COLOURS:
        raise ValueError(f"unknown colour: {colour!r}")


def build_identity(
    seed_value: str,
    flower: str | None = None,
    colour: str | None = None,
) -> dict[str, Any]:
    """Return a purely cosmetic identity for a pack.

    *seed_value* should be a stable identifier such as pack_id or pack path.
    Any supplied *flower* or *colour* overrides the deterministic default.
    """
    _validate(flower, colour)
    rng = random.Random(seed_value)
    chosen_flower = flower if flower else rng.choice(sorted(FLOWERS))
    chosen_colour = colour if colour else rng.choice(sorted(COLOURS))

    flower_info = FLOWERS[chosen_flower]
    colour_info = COLOURS[chosen_colour]
    visual_family = colour_info["family"]
    symbol = flower_info["symbol"]
    compact_name = f"{chosen_colour}{symbol}"

    return {
        "flower": chosen_flower,
        "colour": chosen_colour,
        "symbol": symbol,
        "visual_family": visual_family,
        "display_name": compact_name,
    }


def display_name(identity: dict[str, Any]) -> str:
    return str(identity.get("display_name", ""))
