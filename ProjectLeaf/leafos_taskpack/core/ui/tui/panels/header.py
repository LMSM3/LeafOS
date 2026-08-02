#!/usr/bin/env python3
"""Persistent TUI header and milestone rail."""

from __future__ import annotations

from typing import Any


PAGES = ("Overview", "Tasks", "Hardware", "Queue", "Brain", "Ledger", "Results")


def clip(value: Any, width: int) -> str:
    text = str(value or "")
    if width <= 0:
        return ""
    return text if len(text) <= width else text[: max(0, width - 3)] + "..."


def render(snapshot: dict[str, Any], page_index: int, width: int) -> list[str]:
    run = snapshot["run"]
    operator = snapshot.get("operator", {})
    identity = (
        f"{operator.get('name', 'LeafOS')} | {operator.get('engine', 'LeafOS')} engine | run {run['id']} | {run['mode']} | {run['elapsed']} | "
        f"{run['safety']} | checkpoint {run['checkpoint_age']}"
    )
    if snapshot.get("dropped_events"):
        identity += f" | DROPPED {snapshot['dropped_events']}"
    if width < 80:
        tabs = " ".join(f"{index + 1}{name[:4]}" for index, name in enumerate(PAGES[:5]))
    else:
        tabs = " ".join(
            (f"<{index + 1} {name}>" if index == page_index else f"[{index + 1} {name}]")
            for index, name in enumerate(PAGES)
        )
    milestone_symbols = {"complete": "+", "active": "*", "blocked": "!", "waiting": "o"}
    rail = "--".join(
        f"[{milestone_symbols.get(item['state'], '?')} {item['name']}"
        + (f" {item['complete']}/{item['total']}" if item["state"] == "active" else "")
        + "]"
        for item in snapshot["milestones"]
    )
    return [clip(identity, width), clip(tabs, width), clip(rail, width)]
