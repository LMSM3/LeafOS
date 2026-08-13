#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ccis.kernel import acceptance_policy, storage, validator_runner  # noqa: E402
from loop import scientific_change_loop as change_loop  # noqa: E402


def json_file(value: str) -> Any:
    path = Path(value).expanduser().resolve()
    result = storage.read_json(path)
    if result is None:
        raise storage.CCISError(f"JSON file is missing or invalid: {path}")
    return result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="leafos ccis")
    commands = root.add_subparsers(dest="command", required=True)

    item = commands.add_parser("init")
    item.add_argument("--task", required=True)
    item.add_argument("--run-root")

    item = commands.add_parser("candidate")
    item.add_argument("--run", required=True)
    item.add_argument("--candidate-id", required=True)
    item.add_argument("--patch", required=True)
    item.add_argument("--changes", required=True)
    item.add_argument("--revision", type=int, default=0)
    item.add_argument("--created-by", default="leafos.ccis.candidate_builder")

    item = commands.add_parser("validate")
    item.add_argument("--run", required=True)
    item.add_argument("--workspace", required=True)

    item = commands.add_parser("evaluate")
    item.add_argument("--run", required=True)
    item.add_argument("--questions", required=True)
    item.add_argument("--validator-results")
    item.add_argument("--evaluator", default="leafos.ccis.evidence_gate")
    item.add_argument("--failure-outcome", choices=("REVISE", "REJECTED"), default="REVISE")

    item = commands.add_parser("decide")
    item.add_argument("--run", required=True)
    item.add_argument("--outcome", choices=("ACCEPTED", "REVISE", "REJECTED", "BLOCKED", "ESCALATED"), required=True)
    item.add_argument("--actor", required=True)
    item.add_argument("--reason", action="append", required=True)

    item = commands.add_parser("accept")
    item.add_argument("task_id", nargs="?", help="task ID under .leafos/ccis/runs")
    item.add_argument("--run")
    item.add_argument("--operator")
    item.add_argument("--confirm")

    item = commands.add_parser("rollback")
    item.add_argument("--run", required=True)

    for name in ("resume", "status"):
        item = commands.add_parser(name)
        item.add_argument("--run", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            run_dir = change_loop.initialize(
                Path(args.task).expanduser().resolve(),
                Path(args.run_root).expanduser().resolve() if args.run_root else None,
            )
            result: Any = {"status": "created", "run": str(run_dir), "state": storage.resume(run_dir)}
        elif args.command == "candidate":
            changes = json_file(args.changes)
            if not isinstance(changes, list):
                raise storage.CCISError("candidate changes JSON must be an array")
            result = change_loop.register_candidate(
                Path(args.run), args.candidate_id, Path(args.patch), changes,
                revision=args.revision, created_by=args.created_by,
            )
        elif args.command == "evaluate":
            questions = json_file(args.questions)
            validator_path = args.validator_results or str(Path(args.run) / "validation" / "validator-results.json")
            validators = json_file(validator_path)
            if not isinstance(questions, list) or not isinstance(validators, list):
                raise storage.CCISError("questions and validator results must be arrays")
            result = change_loop.evaluate_candidate(
                Path(args.run), questions, validators,
                evaluator=args.evaluator, requested_failure=args.failure_outcome,
            )
        elif args.command == "validate":
            result = validator_runner.run_validators(Path(args.run), Path(args.workspace))
        elif args.command == "decide":
            result = change_loop.decide(Path(args.run), args.outcome, args.actor, args.reason)
        elif args.command == "accept":
            if not args.run and not args.task_id:
                raise storage.CCISError("accept requires <task-id> or --run")
            run_dir = Path(args.run).expanduser().resolve() if args.run else (
                Path(os.environ.get(
                    "LEAFOS_CCIS_RUN_ROOT",
                    str(REPO_ROOT / ".leafos" / "ccis" / "runs"),
                )).expanduser().resolve() / args.task_id
            )
            confirmation = args.confirm or args.task_id
            if not confirmation:
                raise storage.CCISError("--run acceptance requires --confirm <task-id>")
            result = acceptance_policy.stage_accepted_candidate(
                run_dir,
                args.operator or getpass.getuser(),
                confirmation,
            )
        elif args.command == "rollback":
            result = acceptance_policy.rollback_rejected_candidate(Path(args.run))
        elif args.command in {"resume", "status"}:
            result = storage.resume(Path(args.run))
        else:
            raise storage.CCISError(f"unsupported command: {args.command}")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (storage.CCISError, OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
