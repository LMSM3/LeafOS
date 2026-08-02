#!/usr/bin/env python3
"""Recent durable event renderer."""

from __future__ import annotations

from typing import Any


def render(records: list[dict[str, Any]], width: int, limit: int = 8) -> list[str]:
    lines = []
    for record in records[-limit:]:
        timestamp = str(record.get("time", ""))[11:19] or "--:--:--"
        line = f"{timestamp} {record.get('type', 'EVENT'):<18} {record.get('task_id', 'RUN'):<12} {record.get('summary', '')}"
        lines.append(line[:width])
    return lines or ["No durable events recorded."]
