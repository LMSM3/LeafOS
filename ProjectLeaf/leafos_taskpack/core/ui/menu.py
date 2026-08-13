#!/usr/bin/env python3
"""Shared palette-aware menu helper for LeafOS/FlowerOS CLI surfaces.

A menu is a list of actions.  Each action may live in a category.
Categories are rendered as pastel section headers.  Action lines use
numbered indexes and the shared flower glyph vocabulary.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BRAND_DIR = os.path.dirname(__file__).replace("/ui", "/brand").replace("\\ui", "\\brand")
if BRAND_DIR not in sys.path:
    sys.path.insert(0, BRAND_DIR)
from flower_palette import ascii_mode, glyph as brand_glyph, paint  # noqa: E402


# Box drawing is disabled when color is off (narrow/ASCII mode).
def _hchar(default: str, ascii: str = "-") -> str:
    return ascii if ascii_mode() else default


def render_menu(
    title: str,
    actions: list[dict],
    *,
    width: int = 62,
    numbered: bool = True,
    start_index: int = 1,
) -> str:
    """Render a styled menu string.

    actions is a list of dicts:
      {
        "label": str,            # displayed text
        "command": str,          # command shown dimly below (optional)
        "category": str,         # section header (optional)
        "glyph": str,            # key in GLYPHS (optional, default "flower")
        "disabled": bool,        # greyed out if True
        "shortcut": str,         # letter shortcut shown after label
      }
    """
    lines: list[str] = []
    line_char = _hchar("\u2500", "-")
    top_char = _hchar("\u2550", "=")

    lines.append("")
    lines.append(paint(top_char * width, "leaf"))
    lines.append(paint(f"  \U0001f331  {title}", "mint", "semibold"))
    lines.append(paint(line_char * width, "leaf"))

    current_category = None
    index = start_index
    for item in actions:
        cat = item.get("category")
        if cat and cat != current_category:
            lines.append("")
            lines.append(paint(f"  {cat}", "blossom", "semibold"))
            current_category = cat

        glyph_key = item.get("glyph", "flower")
        glyph = _glyph(glyph_key)
        label = item["label"]
        shortcut = item.get("shortcut")
        disabled = item.get("disabled", False)

        if numbered:
            num = paint(f"{index:>2}", "blossom")
            prefix = f"  {num}. "
        else:
            prefix = "      "

        if disabled:
            rendered = paint(f"{glyph} {label}", "dim")
        else:
            rendered = f"{paint(glyph, 'fern')} {paint(label, 'leaf')}"

        shortcut_part = f" {paint(f'[{shortcut}]', 'lavender')}" if shortcut else ""
        lines.append(f"{prefix}{rendered}{shortcut_part}")

        cmd = item.get("command")
        if cmd:
            lines.append(f"       {paint(cmd, 'dim')}")

        index += 1

    lines.append("")
    return "\n".join(lines)


def prompt_choice(
    actions: list[dict],
    prompt_text: str = "choice",
    allow_quit: bool = True,
) -> dict | None:
    """Print a menu and read a choice from stdin.

    Returns the selected action dict, or None for quit/empty.
    """
    print(render_menu(prompt_text, actions))
    if allow_quit:
        print(paint("  0. \u2717 quit", "peach"))
    print()

    try:
        raw = input(paint(f"{prompt_text}> ", "mint")).strip().lstrip("\ufeff").lstrip("\ufeff")
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if raw.lower() in {"q", "quit", "exit", "0"}:
        return None

    for alias in {"1", "2", "3", "4", "5", "6", "7", "8", "9"}:
        if raw == alias:
            idx = int(raw) - 1
            if 0 <= idx < len(actions):
                return actions[idx]
            break

    # Allow typing the label or shortcut.
    lowered = raw.lower()
    for action in actions:
        if action["label"].lower().startswith(lowered):
            return action
        if action.get("shortcut", "").lower() == lowered:
            return action

    print(paint(f"  unknown choice: {raw}", "error"))
    return None


def _glyph(alias: str) -> str:
    glyphs = {
        "ok": ("\u2713", "[ok]"),
        "warn": ("\u26a0", "[!]"),
        "error": ("\u00d7", "[x]"),
        "pending": ("\u25cc", "[..]"),
        "leaf": ("\U0001f331", "LeafOS"),
        "flower": ("\u273f", "*"),
        "work": ("\u2766", "WO"),
        "home": ("\u2302", "home"),
        "runtime": ("\u26a1", ">"),
        "reference": ("\u2712", "ref"),
        "provider": ("\U0001f4e1", "net"),
        "monitor": ("\u23f8", "||"),
        "chat": ("\u270d", "<>"),
        "stack": ("\u25d1", "[o]"),
        "flower-os": ("\u273f", "FOS"),
    }
    return brand_glyph(*glyphs.get(alias, glyphs["flower"]))


def _default_actions() -> list[dict]:
    # Resolve repo root from script path so the menu is correct regardless of cwd.
    script = Path(__file__).resolve()
    # menu.py is at ProjectLeaf/leafos_taskpack/core/ui/menu.py -> repo is 4 parents up.
    # LEAF_ROOT is the taskpack root. LEAFOS_ROOT is the optional repository-root override.
    configured = os.environ.get("LEAFOS_ROOT", "").strip()
    repo_path = Path(configured).expanduser().resolve() if configured else script.parents[4]
    if not repo_path.joinpath("PowerShell-Version", "leaf.ps1").is_file():
        raise RuntimeError(f"LeafOS root is missing its PowerShell surface: {repo_path}")
    repo = str(repo_path)
    flower_root = os.path.join(os.path.dirname(repo), "FlowerOS")
    flower_available = os.path.isdir(flower_root)
    return [
        {"label": "Open operator home", "command": f"& '{repo}\\PowerShell-Version\\leaf.ps1' home", "category": "LeafOS", "glyph": "home", "shortcut": "h"},
        {"label": "Check runtime / provider", "command": f"& '{repo}\\PowerShell-Version\\leaf.ps1' status", "category": "LeafOS", "glyph": "provider", "shortcut": "r"},
        {"label": "Run doctor", "command": f"& '{repo}\\PowerShell-Version\\leaf.ps1' doctor", "category": "LeafOS", "glyph": "ok", "shortcut": "d"},
        {"label": "Inspect latest run", "command": f"& '{repo}\\PowerShell-Version\\leaf.ps1' trace latest", "category": "Work", "glyph": "work", "shortcut": "w"},
        {"label": "Benchmark matrix (dry)", "command": f"& '{repo}\\PowerShell-Version\\leaf.ps1' realbench matrix --manifest '{repo}\\ProjectLeaf\\leafos_taskpack\\config\\inference-benchmark-matrix.json' --dry-run", "category": "Work", "glyph": "runtime", "shortcut": "b"},
        {"label": "Open local chat", "command": f"& '{repo}\\PowerShell-Version\\leaf.ps1' chat", "category": "Chat", "glyph": "chat", "shortcut": "c"},
        {"label": "Open local stack", "command": f"& '{repo}\\PowerShell-Version\\leaf.ps1' stack --agent-inlet", "category": "Agentic Stack", "glyph": "stack", "shortcut": "s"},
        {"label": "View FlowerOS state", "command": f"bash '{flower_root}\\bin\\flower-state' show", "category": "FlowerOS layer", "glyph": "flower-os", "shortcut": "f", "disabled": not flower_available},
        {"label": "View FlowerOS theme", "command": f"bash '{flower_root}\\bin\\flower-state' theme", "category": "FlowerOS layer", "glyph": "flower-os", "shortcut": "t", "disabled": not flower_available},
    ]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    actions = _default_actions()
    choice = prompt_choice(actions, prompt_text="leaf menu")
    if choice is None:
        print(paint("Goodbye.", "mint"))
        return 0

    print(paint(f"Running: {choice['label']}", "leaf"))
    print(paint(f"  {choice['command']}", "dim"))
    if "stack" in choice.get("glyph", ""):
        print()
        print(paint("  Agentic Stack inlet (visual demo)", "mint", "semibold"))
        print(paint("  [input]    user idea -> flag as user-input", "sky"))
        print(paint("  [brain]    accept -> create one or more plans", "leaf"))
        print(paint("  [output]   push generated plans back to stack", "blossom"))
        print(paint("  This surface will become the primary inlet for continual stack item assignments.", "dim"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
