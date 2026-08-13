#!/usr/bin/env python3
"""Pastel + green color palette shared by FlowerOS-facing surfaces.

This module is intentionally dependency-free so it can be imported by any
shell-facing Python component without dragging in the rest of the runtime.
"""

from __future__ import annotations

import os


# Several shades of green plus pastels. Indices follow a spring-garden gradient.
PALETTE = {
    "mint": "\033[38;2;183;240;199m",
    "leaf": "\033[38;2;119;221;119m",
    "fern": "\033[38;2;80;180;80m",
    "forest": "\033[38;2;34;139;34m",
    "blossom": "\033[38;2;255;183;197m",
    "lavender": "\033[38;2;204;178;255m",
    "sky": "\033[38;2;178;223;255m",
    "butter": "\033[38;2;255;250;181m",
    "peach": "\033[38;2;255;210;183m",
    "semibold": "\033[1m",
    "dim": "\033[2m",
    "reset": "\033[0m",
    "ok": "\033[38;2;119;221;119m",
    "warn": "\033[38;2;255;210;183m",
    "error": "\033[38;2;255;154;162m",
    "info": "\033[38;2;178;223;255m",
}

# One motion sequence for Python terminal surfaces.  It matches the canonical
# Bash ``braille`` transition so chat, dashboard, and stream status do not each
# carry a slightly different spinner.
SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

# The default terminal theme uses the softer Flower palette while retaining
# the stable semantic keys consumed by the existing UI modules.
DEFAULT_THEME = {
    "accent": PALETTE["semibold"] + PALETTE["lavender"],
    "dim": PALETTE["dim"],
    "bold": PALETTE["semibold"],
    "ok": PALETTE["semibold"] + PALETTE["leaf"],
    "warn": PALETTE["semibold"] + PALETTE["butter"],
    "err": PALETTE["semibold"] + PALETTE["error"],
    "you": PALETTE["semibold"] + PALETTE["sky"],
    "bot": PALETTE["mint"],
    "border": PALETTE["fern"],
    "reset": PALETTE["reset"],
    "spinner": PALETTE["semibold"] + PALETTE["blossom"],
    "bar_fill": "█",
    "bar_empty": "░",
}

DASHBOARD_THEME = {
    "reset": PALETTE["reset"],
    "bold": PALETTE["semibold"],
    "dim": PALETTE["dim"],
    "green": PALETTE["leaf"],
    "cyan": PALETTE["sky"],
    "yellow": PALETTE["butter"],
    "red": PALETTE["error"],
    "magenta": PALETTE["blossom"],
    "blue": PALETTE["lavender"],
    "green_b": PALETTE["semibold"] + PALETTE["leaf"],
    "cyan_b": PALETTE["semibold"] + PALETTE["sky"],
    "yellow_b": PALETTE["semibold"] + PALETTE["butter"],
    "red_b": PALETTE["semibold"] + PALETTE["error"],
}


def default_theme(disable_color: bool = False) -> dict[str, str]:
    """Return an isolated default theme, preserving non-color bar glyphs."""
    theme = dict(DEFAULT_THEME)
    if disable_color:
        for key in theme.keys() - {"bar_fill", "bar_empty"}:
            theme[key] = ""
        theme["bar_fill"] = "#"
        theme["bar_empty"] = "-"
    return theme


def dashboard_theme(disable_color: bool = False) -> dict[str, str]:
    """Return dashboard-compatible semantic colors from the shared palette."""
    if disable_color:
        return {key: "" for key in DASHBOARD_THEME}
    return dict(DASHBOARD_THEME)


def no_color() -> bool:
    if os.environ.get("NO_COLOR") == "1":
        return True
    forced = {os.environ.get("FORCE_COLOR", "").lower(), os.environ.get("LEAF_COLOR", "").lower()}
    if forced.intersection({"1", "yes", "true"}):
        return False
    return not os.isatty(1)


def color_enabled() -> bool:
    """Return presentation capability without probing a nonexistent color."""
    return not no_color()


def ascii_mode() -> bool:
    """Keep glyph choice independent from the color-output decision."""
    glyph_mode = os.environ.get("LEAF_GLYPHS", "auto").lower()
    return (
        os.environ.get("NO_EMOJI") == "1"
        or os.environ.get("LEAF_NO_EMOJI") == "1"
        or glyph_mode == "ascii"
    )


def glyph(unicode_value: str, ascii_value: str) -> str:
    return ascii_value if ascii_mode() else unicode_value


def color(name: str) -> str:
    return "" if no_color() else PALETTE.get(name, "")


def paint(text: str, *names: str) -> str:
    if no_color():
        return text
    prefix = "".join(PALETTE[n] for n in names if n in PALETTE)
    return f"{prefix}{text}{PALETTE['reset']}"
