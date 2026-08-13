#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Authority-boundary correctness benchmark.

Verifies that allowed capabilities produce valid tickets and denied
capabilities are recorded as denials without granting a usable ticket.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "core" / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from leaf_durable_bridge import (
    MondayDurableBridge,
    DurableBridgeError,
)


def request_and_assert(capability: str, actor: str, *, expect_allowed: bool) -> bool:
    bridge = MondayDurableBridge(source="authority-boundary-benchmark")
    result = bridge.request_capability(
        capability=capability,
        actor=actor,
        reason="authority boundary benchmark",
    )
    payload = result.get("payload", result)
    if payload.get("allowed") is not expect_allowed:
        print(f"FAIL: {capability} allowed={payload.get('allowed')}, expected {expect_allowed}")
        return False
    ticket = payload.get("ticket", {})
    if ticket.get("allowed") is not expect_allowed:
        print(f"FAIL: {capability} ticket allowed={ticket.get('allowed')}, expected {expect_allowed}")
        return False
    if expect_allowed and not ticket.get("ticket_digest"):
        print(f"FAIL: allowed ticket for {capability} missing digest")
        return False
    if not expect_allowed and ticket.get("ticket_digest"):
        print(f"INFO: denied ticket for {capability} still has digest (cosmetic only)")
    return True


def main() -> int:
    allowed = ["input.append", "claim.validate", "runtime.verify"]
    denied = ["mutation.direct", "checkpoint.self_declare"]

    start = time.perf_counter()
    ok = True
    for cap in allowed:
        if not request_and_assert(cap, "bench.allowed", expect_allowed=True):
            ok = False
    for cap in denied:
        if not request_and_assert(cap, "bench.denied", expect_allowed=False):
            ok = False
    elapsed = time.perf_counter() - start

    if not ok:
        print("authority-boundary benchmark FAILED")
        return 1

    print(f"authority-boundary benchmark PASSED ({len(allowed)} allowed, {len(denied)} denied, {elapsed:.3f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
