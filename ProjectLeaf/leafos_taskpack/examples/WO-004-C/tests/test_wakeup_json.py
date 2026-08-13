#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WO-004-C-02 -- structured output validation for the wakeup node.

Usage:
    python3 tests/test_wakeup_json.py [PATH_TO_wakeup_result.json]

Defaults to runs/latest/wakeup_result.json relative to the module root.

Validates (WO-004-C-02 section 5.2):
    leafos_object == leafos_wakeup_result
    version exists
    branch is heads or tails
    context.local_date exists
    context.local_time exists
    message exists
    heads branch has importstring
    tails branch has importstring == null
"""

import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent.parent


def _fail(msg):
    print("FAIL: {}".format(msg))
    raise SystemExit(1)


def validate(result):
    checks = []

    def check(label, condition):
        checks.append((label, bool(condition)))

    check("leafos_object == leafos_wakeup_result",
          result.get("leafos_object") == "leafos_wakeup_result")
    check("version exists", bool(result.get("version")))

    branch = result.get("branch")
    check("branch is heads or tails", branch in ("heads", "tails"))

    context = result.get("context") or {}
    check("context.local_date exists", bool(context.get("local_date")))
    check("context.local_time exists", bool(context.get("local_time")))

    check("message exists", bool(result.get("message")))

    importstring = result.get("importstring")
    if branch == "heads":
        check("heads branch has importstring", bool(importstring))
        if importstring:
            try:
                payload = json.loads(importstring)
                check("heads importstring is valid JSON", isinstance(payload, dict))
                check("heads payload has ticker", bool(payload.get("ticker")))
            except (ValueError, TypeError):
                check("heads importstring is valid JSON", False)
    elif branch == "tails":
        check("tails branch has importstring == null", importstring is None)

    failed = [label for label, ok in checks if not ok]
    for label, ok in checks:
        print("  [{}] {}".format("ok" if ok else "XX", label))
    return failed


def main(argv):
    target = Path(argv[1]) if len(argv) > 1 else (
        MODULE_ROOT / "runs" / "latest" / "wakeup_result.json")
    if not target.exists():
        _fail("result file not found: {}".format(target))

    try:
        with open(target, "r", encoding="utf-8") as fh:
            result = json.load(fh)
    except (OSError, ValueError) as exc:
        _fail("could not read JSON: {}".format(exc))

    print("validating: {}".format(target))
    failed = validate(result)
    if failed:
        _fail("{} check(s) failed: {}".format(len(failed), ", ".join(failed)))
    print("test_wakeup_json.py: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
