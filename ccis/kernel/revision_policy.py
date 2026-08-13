from __future__ import annotations

from typing import Any

from .storage import CCISError


def assert_revision_allowed(task_envelope: dict[str, Any], revision: int) -> None:
    if revision < 0:
        raise CCISError("candidate revision cannot be negative")
    limit = int(task_envelope["budget"]["revision_limit"])
    if revision > limit:
        raise CCISError(f"candidate revision {revision} exceeds task limit {limit}")


def assert_candidate_budget(task_envelope: dict[str, Any], candidate_count: int) -> None:
    limit = int(task_envelope["budget"]["candidate_limit"])
    if candidate_count >= limit:
        raise CCISError(f"candidate limit exhausted ({limit})")
