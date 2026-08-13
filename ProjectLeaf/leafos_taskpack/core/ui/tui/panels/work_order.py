#!/usr/bin/env python3
"""Work-order summary renderer."""

from __future__ import annotations

import textwrap
from typing import Any


def render(snapshot: dict[str, Any], width: int) -> list[str]:
    order = snapshot["work_order"]
    lines = [f"{order['id']}  {order['title']}"]
    lines.extend(textwrap.wrap(order["objective"], width=max(20, width)) or [""])
    mutation = "enabled by order" if order["allow_mutation"] else "disabled"
    lines.append(f"Mutation: {mutation} | acceptance gates: {len(order['acceptance'])}")
    return lines
