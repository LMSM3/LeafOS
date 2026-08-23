from __future__ import annotations

import json
from typing import Any


def render_context_packet(packet: dict[str, Any]) -> str:
    """Render the stable human-readable context handoff format."""

    def block(title: str, value: Any) -> list[str]:
        if isinstance(value, str):
            lines = [value]
        elif not value:
            lines = ["none"]
        else:
            lines = json.dumps(value, indent=2, ensure_ascii=False).splitlines()
        return [title, *lines, ""]

    lines: list[str] = []
    lines += block("OBJECTIVE", packet["objective"])
    lines += block("PROJECT", packet["project"])
    lines += block("CURRENT STATE", packet["current_state"])
    lines += block("LAST DECISIONS", packet["last_decisions"])
    lines += block("ACTIVE TASKS", packet["active_tasks"])
    lines += block("NEW EVIDENCE", packet["new_evidence"])
    lines += block("UNRESOLVED FAILURES", packet["unresolved_failures"])
    lines += block("UNKNOWN / CONFLICTING", packet["unknown_or_conflicting"])
    lines += block("NEXT RECOMMENDED ACTIONS", packet["next_recommended_actions"])
    lines += block("PROVENANCE", packet["provenance"])
    return "\n".join(lines).rstrip() + "\n"
