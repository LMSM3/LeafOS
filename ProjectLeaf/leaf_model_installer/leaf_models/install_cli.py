"""Command-line surface for the LeafOS model installation orchestrator."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .catalog import MODEL_CATALOG
from .orchestrator import (
    MIN_WEIGHT_BYTES,
    OrchestrationError,
    apply_plan,
    create_pack_plan,
    create_plan,
    default_model_root,
    plan_to_dict,
    read_plan,
    resolve_plan,
    verify_plan,
    write_plan,
)
from .state import inspect_resume_state as _inspect_resume_state
from .state import inspect_store as _inspect_store


def _json_out(payload: dict) -> str:
    return json.dumps(payload, indent=2, default=str) + "\n"


def _emit(args: argparse.Namespace, text: str) -> None:
    if not getattr(args, "json", False):
        print(text)


def _emit_json(args: argparse.Namespace, payload: dict) -> int:
    if getattr(args, "json", False):
        print(_json_out(payload))
        return 0 if payload.get("ok", True) else 1
    return -1

def human_bytes(value: Optional[int]) -> str:
    if value is None:
        return "unknown until resolve"
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.2f} {unit}"
        amount /= 1024
    return f"{amount:.2f} TiB"


def print_catalog() -> None:
    print(f"LeafOS model catalog {MODEL_CATALOG.catalog_version}")
    print()
    print("Slot  Default  Quant          Key                       Role")
    print("----  -------  -------------  ------------------------  ------------------------------")
    for model in MODEL_CATALOG.models:
        default = "yes" if model.default_enabled else ("never" if model.experimental else "optional")
        print(
            f"{model.slot:>4}  {default:<7}  {model.default_quant:<13}  "
            f"{model.key:<24}  {model.role}"
        )
        print(f"      repo: {model.repo_id}")
        if model.fallback_quants:
            print(f"      explicit fallbacks: {', '.join(model.fallback_quants)}")
        for note in model.notes:
            print(f"      note: {note}")


def print_plan(plan) -> None:
    state = "resolved and revision-pinned" if plan.resolved else "offline draft"
    print(f"Plan:        {plan.plan_id}")
    print(f"State:       {state}")
    print(f"Profile:     {plan.profile}")
    print(f"Destination: {plan.destination_root}")
    print(f"Estimate:    {human_bytes(plan.estimated_bytes)}")
    print()
    for item in plan.items:
        fallback = " (fallback)" if item.fallback_used else ""
        revision = f" @ {item.revision[:12]}" if item.revision else ""
        print(
            f"[{item.slot}] {item.nickname}: {item.key} / "
            f"{item.selected_quant}{fallback}{revision}"
        )
        print(f"    {item.repo_id}")
        print(f"    target: {item.local_dir}")
        print(f"    files:  {', '.join(item.patterns)}")
        print(f"    size:   {human_bytes(item.estimated_bytes)}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gguf_magic(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            return handle.read(4).decode("ascii", errors="replace")
    except OSError:
        return ""


def _artifact_status(
    *,
    path: Path,
    artifact_format: str,
    expected_bytes: Optional[int] = None,
) -> tuple[bool, int, str, bool, str]:
    present = path.is_file()
    size = path.stat().st_size if present else 0
    magic = ""
    reason = ""

    if not present:
        return False, 0, "", False, "missing"

    if expected_bytes is not None and size != int(expected_bytes):
        reason = f"size mismatch: expected {expected_bytes}, got {size}"

    is_gguf = path.suffix.lower() == ".gguf" or artifact_format == "gguf"
    is_weight = is_gguf or path.suffix.lower() == ".safetensors"
    if is_gguf:
        magic = _gguf_magic(path)
        if magic != "GGUF":
            reason = f"invalid GGUF magic: {magic or '<empty>'}"
    elif is_weight and expected_bytes is None and size < MIN_WEIGHT_BYTES:
        reason = f"weight file too small: {size}"

    return True, size, magic, reason == "", reason


def _row(
    *,
    slot: int,
    key: str,
    role: str,
    repo: str,
    quant: str,
    artifact_format: str,
    pattern: str,
    path: Path,
    fallback_used: bool,
    expected_bytes: Optional[int] = None,
) -> dict:
    present, size, magic, valid, reason = _artifact_status(
        path=path,
        artifact_format=artifact_format,
        expected_bytes=expected_bytes,
    )
    return {
        "slot": slot,
        "key": key,
        "role": role,
        "repo": repo,
        "quant": quant,
        "fallback_used": fallback_used,
        "format": artifact_format,
        "pattern": pattern,
        "path": str(path),
        "present": present,
        "bytes": size,
        "expected_bytes": expected_bytes,
        "magic": magic,
        "valid_artifact": valid,
        "reason": reason,
    }


def _rows_for_variant(model, quant: str, destination_root: Path, fallback_used: bool) -> list[dict]:
    variant = model.variants[quant]
    target_dir = destination_root / model.local_dir
    rows: list[dict] = []
    for pattern in variant.patterns:
        matches = sorted(
            (
                candidate
                for candidate in target_dir.glob(pattern)
                if candidate.is_file()
            ),
            key=lambda candidate: candidate.stat().st_size,
            reverse=True,
        )
        path = matches[0] if matches else target_dir / pattern
        rows.append(
            _row(
                slot=model.slot,
                key=model.key,
                role=model.role,
                repo=model.repo_id,
                quant=quant,
                artifact_format=variant.format,
                pattern=pattern,
                path=path,
                fallback_used=fallback_used,
                expected_bytes=None,
            )
        )
    return rows


def _complete(rows: list[dict]) -> bool:
    return bool(rows) and all(row["present"] and row["valid_artifact"] for row in rows)


def _catalog_status_rows(profile: str, destination_root: Path, allow_fallback: bool) -> list[dict]:
    by_slot = MODEL_CATALOG.by_slot()
    rows: list[dict] = []
    for slot in MODEL_CATALOG.profiles[profile]["slots"]:
        model = by_slot[int(slot)]
        candidates = [(model.default_quant, False)]
        if allow_fallback:
            candidates.extend((quant, True) for quant in model.fallback_quants)

        selected_rows: list[dict] = []
        for quant, fallback_used in candidates:
            candidate_rows = _rows_for_variant(model, quant, destination_root, fallback_used)
            if not selected_rows:
                selected_rows = candidate_rows
            if _complete(candidate_rows):
                selected_rows = candidate_rows
                break
        rows.extend(selected_rows)
    return rows


def _resolved_plan_status_rows(plan) -> list[dict]:
    if not plan.resolved:
        return []

    rows: list[dict] = []
    for item in plan.items:
        if not item.expected_files:
            return []
        target_dir = Path(plan.destination_root) / item.local_dir
        for expected in item.expected_files:
            repo_path = str(expected["path"])
            rows.append(
                _row(
                    slot=item.slot,
                    key=item.key,
                    role=item.role,
                    repo=item.repo_id,
                    quant=item.selected_quant,
                    artifact_format=item.format,
                    pattern=repo_path,
                    path=target_dir / repo_path,
                    fallback_used=item.fallback_used,
                    expected_bytes=expected.get("bytes"),
                )
            )
    return rows


def _try_resolved_status_rows(
    resolved_plan: Optional[str],
    profile: str,
    destination_root: Path,
) -> tuple[str, list[dict]]:
    if not resolved_plan:
        return "catalog", []
    path = Path(resolved_plan).expanduser().resolve()
    if not path.is_file():
        return "catalog", []
    plan = read_plan(path)
    if plan.profile != profile or not plan.resolved:
        return "catalog", []
    if Path(plan.destination_root).expanduser().resolve() != destination_root:
        return "catalog", []
    rows = _resolved_plan_status_rows(plan)
    if rows:
        return "resolved_plan", rows
    return "catalog", []


def command_local_status(args: argparse.Namespace) -> int:
    profile = args.profile
    if profile not in MODEL_CATALOG.profiles:
        valid = ", ".join(sorted(MODEL_CATALOG.profiles))
        raise OrchestrationError(f"Unknown profile {profile!r}. Valid: {valid}")

    destination_root = Path(args.dest).expanduser().resolve()
    source, rows = _try_resolved_status_rows(args.resolved_plan, profile, destination_root)
    if not rows:
        rows = _catalog_status_rows(profile, destination_root, allow_fallback=args.allow_fallback)
        source = "catalog"

    complete = _complete(rows)
    payload = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "model_dir": str(destination_root),
        "model_dir_reason": args.model_dir_reason,
        "profile": profile,
        "source": source,
        "complete": complete,
        "expected": rows,
        "plan": args.plan,
        "resolved_plan": args.resolved_plan,
        "verification_report": args.verification_report,
        "next_if_missing": [
            f"leaf-models plan --profile {profile} --dest {destination_root}",
            f"leaf-models resolve {args.plan or '<plan.json>'}",
            f"leaf-models apply {args.resolved_plan or '<plan.resolved.json>'} --yes",
        ],
    }

    if args.report:
        output = Path(args.report).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(
        f'{"slot":<4} {"model":<26} {"quant":<10} '
        f'{"fallback":<8} {"present":<8} {"valid":<8} {"bytes":>12}'
    )
    for row in rows:
        print(
            f'{row["slot"]:<4} {row["key"]:<26} {row["quant"]:<10} '
            f'{str(row["fallback_used"]):<8} {str(row["present"]):<8} '
            f'{str(row["valid_artifact"]):<8} {row["bytes"]:>12}'
        )
        if row["reason"]:
            print(f'      {row["reason"]}: {row["path"]}')

    if args.report:
        print(f"\nstatus report: {Path(args.report).expanduser().resolve()}")
    return 0 if complete else 1


def _color(text: str, name: str, enabled: bool) -> str:
    if not enabled:
        return text
    # Map legacy basic names to the FlowerOS pastel/green palette.
    codes = {
        "red":   "\033[38;2;255;154;162m",  # pastel error
        "green": "\033[38;2;119;221;119m",  # leaf green
        "yellow":"\033[38;2;255;250;181m",  # butter
        "cyan":  "\033[38;2;178;223;255m",  # pastel sky
        "bold":  "\033[1m",
    }
    return f"{codes[name]}{text}\033[0m"


def _has_model_like_files(path: Path) -> bool:
    if not path.is_dir():
        return False
    for suffix in ("*.gguf", "*.safetensors"):
        if next(path.rglob(suffix), None) is not None:
            return True
    return False


def _detect_doctor_root(dest: Optional[str]) -> tuple[Path, str]:
    if dest:
        return Path(dest).expanduser().resolve(), "explicit --dest/--model-dir"

    configured = os.environ.get(MODEL_CATALOG.storage["environment_variable"])
    if configured:
        return Path(configured).expanduser().resolve(), "LEAF_MODEL_DIR environment variable"

    installer_cache = Path(__file__).resolve().parent.parent / "models"
    if _has_model_like_files(installer_cache):
        return installer_cache.resolve(), "detected installer-local model cache"

    return default_model_root(MODEL_CATALOG), "catalog default"


def _file_hash(path: Path, algorithm: str) -> str:
    hasher = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024 * 8), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _doctor_known_rows(destination_root: Path, include_experimental: bool) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for model in MODEL_CATALOG.models:
        if model.experimental and not include_experimental:
            continue
        target_dir = destination_root / model.local_dir
        for quant, variant in model.variants.items():
            for pattern in variant.patterns:
                matches = sorted(
                    (candidate for candidate in target_dir.glob(pattern) if candidate.is_file()),
                    key=lambda candidate: str(candidate),
                )
                for path in matches:
                    resolved = str(path.resolve())
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    row = _row(
                        slot=model.slot,
                        key=model.key,
                        role=model.role,
                        repo=model.repo_id,
                        quant=quant,
                        artifact_format=variant.format,
                        pattern=pattern,
                        path=path,
                        fallback_used=quant in model.fallback_quants,
                        expected_bytes=None,
                    )
                    row.update(
                        {
                            "known_catalog_artifact": True,
                            "counted_for_minimum": not model.experimental,
                            "required_runtime_artifact": False,
                            "hash": None,
                            "hash_algorithm": None,
                        }
                    )
                    rows.append(row)
    return rows


def _doctor_required_runtime_rows(destination_root: Path, existing_paths: set[str]) -> list[dict]:
    missing_or_invalid: list[dict] = []
    for row in _catalog_status_rows("runtime-default", destination_root, allow_fallback=False):
        resolved = str(Path(row["path"]).resolve())
        if row["valid_artifact"] and resolved in existing_paths:
            continue
        row.update(
            {
                "known_catalog_artifact": True,
                "counted_for_minimum": False,
                "required_runtime_artifact": True,
                "hash": None,
                "hash_algorithm": None,
            }
        )
        missing_or_invalid.append(row)
    return missing_or_invalid


def _doctor_untracked_rows(destination_root: Path, known_paths: set[str]) -> list[dict]:
    rows: list[dict] = []
    if not destination_root.is_dir():
        return rows
    candidates = sorted(
        (
            path
            for path in destination_root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".gguf", ".safetensors"}
        ),
        key=lambda path: str(path),
    )
    for path in candidates:
        resolved = str(path.resolve())
        if resolved in known_paths:
            continue
        artifact_format = "gguf" if path.suffix.lower() == ".gguf" else "safetensors-snapshot"
        row = _row(
            slot=0,
            key="untracked",
            role="Untracked local model-like artifact",
            repo="",
            quant="",
            artifact_format=artifact_format,
            pattern=path.name,
            path=path,
            fallback_used=False,
            expected_bytes=None,
        )
        row.update(
            {
                "known_catalog_artifact": False,
                "counted_for_minimum": False,
                "required_runtime_artifact": False,
                "hash": None,
                "hash_algorithm": None,
            }
        )
        rows.append(row)
    return rows


def _doctor_label(row: dict) -> str:
    if not row["present"] or not row["valid_artifact"]:
        return "ERROR"
    if not row.get("known_catalog_artifact", False):
        return "WARN"
    return "OK"


def command_download_doctor(args: argparse.Namespace) -> int:
    destination_root, root_reason = _detect_doctor_root(args.dest)
    color_enabled = not args.no_color and not os.environ.get("NO_COLOR")

    rows = _doctor_known_rows(destination_root, include_experimental=args.include_experimental)
    known_paths = {str(Path(row["path"]).resolve()) for row in rows if row["present"]}
    rows.extend(_doctor_required_runtime_rows(destination_root, existing_paths=known_paths))
    if args.include_untracked:
        rows.extend(_doctor_untracked_rows(destination_root, known_paths=known_paths))

    rows.sort(key=lambda row: (row["slot"], row["key"], row["quant"], row["path"]))

    print(_color("LeafOS download doctor", "cyan", color_enabled))
    print(f"model dir : {destination_root}")
    print(f"reason    : {root_reason}")
    print(f"minimum   : {args.minimum} valid canonical artifacts")
    print(f"hash      : {args.algorithm}")
    print("network   : no downloads, no metadata resolve")
    print()

    print(_color("Integrity + hash pass", "bold", color_enabled))
    for row in rows:
        label = _doctor_label(row)
        label_color = "green" if label == "OK" else ("yellow" if label == "WARN" else "red")
        if row["present"] and row["valid_artifact"]:
            row["hash_algorithm"] = args.algorithm
            row["hash"] = _file_hash(Path(row["path"]), args.algorithm)
        marker = _color(f"{label:<5}", label_color, color_enabled)
        model = row["key"] if row["key"] != "untracked" else "untracked-extra"
        quant = row["quant"] or "-"
        digest = row["hash"] or "<not available>"
        print(f"{marker} slot={row['slot']:<2} {model:<26} {quant:<10} {args.algorithm}={digest}")
        if row["reason"]:
            print(_color(f"      {row['reason']}: {row['path']}", "red", color_enabled))

    if args.sleep > 0:
        print()
        print(f"sleeping {args.sleep:g}s before size/location pass...")
        time.sleep(args.sleep)

    print()
    print(_color("Size + location pass", "bold", color_enabled))
    print(f'{"state":<7} {"slot":<4} {"model":<26} {"quant":<10} {"size":>12}  location')
    for row in rows:
        label = _doctor_label(row)
        label_color = "green" if label == "OK" else ("yellow" if label == "WARN" else "red")
        marker = _color(f"{label:<7}", label_color, color_enabled)
        model = row["key"] if row["key"] != "untracked" else "untracked-extra"
        quant = row["quant"] or "-"
        print(
            f"{marker} {row['slot']:<4} {model:<26} {quant:<10} "
            f"{human_bytes(row['bytes']):>12}  {row['path']}"
        )

    counted_rows = [
        row
        for row in rows
        if row.get("counted_for_minimum") and row["present"] and row["valid_artifact"]
    ]
    error_rows = [row for row in rows if not row["present"] or not row["valid_artifact"]]
    valid_count = len(counted_rows)
    untracked_count = len([row for row in rows if not row.get("known_catalog_artifact", False)])

    success = valid_count >= args.minimum and not error_rows
    print()
    print(_color("Doctor summary", "bold", color_enabled))
    count_line = f"valid canonical artifacts: {valid_count}/{args.minimum} minimum"
    print(_color(count_line, "green" if valid_count >= args.minimum else "red", color_enabled))
    if untracked_count:
        print(_color(f"untracked model-like artifacts: {untracked_count} (hashed but not counted)", "yellow", color_enabled))
    if error_rows:
        print(_color(f"red errors: {len(error_rows)} file(s) missing or invalid", "red", color_enabled))
    if not rows:
        print(_color("red error: no model-like artifacts found", "red", color_enabled))
        success = False

    payload = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "model_dir": str(destination_root),
        "model_dir_reason": root_reason,
        "minimum": args.minimum,
        "algorithm": args.algorithm,
        "success": success,
        "valid_canonical_artifacts": valid_count,
        "untracked_artifacts": untracked_count,
        "red_errors": len(error_rows) + (0 if rows else 1),
        "artifacts": rows,
    }
    if args.report:
        report = Path(args.report).expanduser().resolve()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"report: {report}")

    return 0 if success else 1


def command_plan(args: argparse.Namespace) -> int:
    plan = create_plan(
        profile=args.profile,
        slots=args.slot or None,
        quant_overrides=args.quant,
        destination_root=Path(args.dest) if args.dest else None,
        allow_fallback=args.allow_fallback,
    )
    output = Path(args.out).expanduser().resolve()
    write_plan(plan, output)
    payload = {
        "ok": True,
        "operation": "plan",
        "state": "planned",
        "message": "Offline plan created.",
        "plan_path": str(output),
        "profile": plan.profile,
        "destination_root": plan.destination_root,
        "estimated_bytes": plan.estimated_bytes,
        "items": len(plan.items),
        "warnings": [],
        "errors": [],
        "next_actions": ["resolve"],
    }
    json_rc = _emit_json(args, payload)
    if json_rc >= 0:
        return json_rc
    print_plan(plan)
    print()
    print(f"Wrote offline plan: {output}")
    print("No network request or download was performed.")
    print(f"Next: leaf-models resolve {output}")
    return 0


def command_plan_pack(args: argparse.Namespace) -> int:
    plan = create_pack_plan(
        pack_path=Path(args.pack).expanduser().resolve(),
        destination_root=Path(args.dest) if args.dest else None,
    )
    output = Path(args.out).expanduser().resolve()
    write_plan(plan, output)
    payload = {
        "ok": True,
        "operation": "plan-pack",
        "state": "planned",
        "message": "Pack plan created.",
        "plan_path": str(output),
        "pack": args.pack,
        "profile": plan.profile,
        "destination_root": plan.destination_root,
        "estimated_bytes": plan.estimated_bytes,
        "items": len(plan.items),
        "warnings": [],
        "errors": [],
        "next_actions": ["resolve"],
    }
    json_rc = _emit_json(args, payload)
    if json_rc >= 0:
        return json_rc
    print_plan(plan)
    print()
    print(f"Wrote offline plan: {output}")
    print("No network request or download was performed.")
    print(f"Next: leaf-models resolve {output}")
    return 0


def command_resolve(args: argparse.Namespace) -> int:
    source = Path(args.plan).expanduser().resolve()
    plan = read_plan(source)
    resolved = resolve_plan(plan, revision=args.revision)
    output = (
        Path(args.out).expanduser().resolve()
        if args.out
        else source.with_name(f"{source.stem}.resolved.json")
    )
    write_plan(resolved, output)
    payload = {
        "ok": True,
        "operation": "resolve",
        "state": "resolved",
        "message": "Repository metadata read; plan pinned to revisions.",
        "plan_path": str(source),
        "resolved_path": str(output),
        "profile": resolved.profile,
        "destination_root": resolved.destination_root,
        "estimated_bytes": resolved.estimated_bytes,
        "items": len(resolved.items),
        "warnings": [],
        "errors": [],
        "next_actions": ["apply"],
    }
    json_rc = _emit_json(args, payload)
    if json_rc >= 0:
        return json_rc
    print_plan(resolved)
    print()
    print(f"Wrote resolved plan: {output}")
    print("Repository metadata was read; model weights were not downloaded.")
    print(f"Next: leaf-models apply {output} --yes")
    return 0


def command_show(args: argparse.Namespace) -> int:
    plan = read_plan(Path(args.plan).expanduser().resolve())
    if args.json:
        print(json.dumps(plan_to_dict(plan), indent=2))
    else:
        print_plan(plan)
    return 0


def command_status(args: argparse.Namespace) -> int:
    plan = read_plan(Path(args.plan).expanduser().resolve())
    print_plan(plan)
    if not plan.resolved:
        print("\nStatus: unresolved; no local verification is possible yet.")
        return 0
    report = verify_plan(plan, compute_hash=False)
    print()
    for item in report["items"]:
        state = "verified" if item["success"] else "incomplete"
        print(
            f"[{item['slot']}] {item['key']}: {state}; "
            f"missing={len(item['missing_files'])} invalid={len(item['invalid_files'])}"
        )
    return 0 if report["success"] else 1


def command_verify(args: argparse.Namespace) -> int:
    plan = read_plan(Path(args.plan).expanduser().resolve())
    report = verify_plan(plan, compute_hash=args.hash)
    if args.out:
        output = Path(args.out).expanduser().resolve()
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not args.json:
            print(f"Wrote verification report: {output}")
    payload = {
        "ok": report["success"],
        "operation": "verify",
        "state": "verified" if report["success"] else "incomplete",
        "verified_at_utc": report.get("verified_at_utc"),
        "plan_id": report.get("plan_id"),
        "items": report["items"],
        "warnings": [],
        "errors": [],
        "next_actions": [],
    }
    json_rc = _emit_json(args, payload)
    if json_rc >= 0:
        return json_rc
    for item in report["items"]:
        state = "VERIFIED" if item["success"] else "FAILED"
        print(f"[{item['slot']}] {item['key']}: {state}")
        for missing in item["missing_files"]:
            print(f"    missing: {missing}")
        for invalid in item["invalid_files"]:
            print(f"    invalid: {invalid}")
    return 0 if report["success"] else 1


def command_apply(args: argparse.Namespace) -> int:
    if not args.yes:
        raise OrchestrationError("Apply is the download boundary and requires --yes")
    plan = read_plan(Path(args.plan).expanduser().resolve())
    result = apply_plan(
        plan,
        max_workers=args.max_workers,
        include_experimental=args.include_experimental,
        confirm_heavy=args.confirm_heavy,
        continue_on_error=args.continue_on_error,
    )
    payload = {
        "ok": result["success"],
        "operation": "apply",
        "state": "completed" if result["success"] else "failed",
        "manifest_path": result["manifest_path"],
        "plan_id": result.get("plan_id"),
        "completed_at_utc": result.get("completed_at_utc"),
        "items": [
            {"slot": item["slot"], "key": item["key"], "status": item["status"]}
            for item in result["results"]
        ],
        "warnings": [],
        "errors": [
            {"slot": item["slot"], "key": item["key"], "error": item["error"]}
            for item in result["results"]
            if item["status"] == "failed"
        ],
        "next_actions": ["verify"] if result["success"] else ["retry", "verify"],
    }
    json_rc = _emit_json(args, payload)
    if json_rc >= 0:
        return json_rc
    for item in result["results"]:
        print(f"[{item['slot']}] {item['key']}: {item['status']}")
        if item["status"] == "failed":
            print(f"    {item['error']}")
    print(f"Manifest: {result['manifest_path']}")
    return 0 if result["success"] else 1


def command_doctor(_args: argparse.Namespace) -> int:
    print(f"Python: {sys.version.split()[0]}")
    print(f"Catalog: {MODEL_CATALOG.catalog_version} ({len(MODEL_CATALOG.models)} slots)")
    try:
        import huggingface_hub

        print(f"huggingface_hub: {huggingface_hub.__version__}")
    except Exception as exc:  # noqa: BLE001
        print(f"huggingface_hub: unavailable ({exc})")
        return 1
    try:
        import hf_xet  # noqa: F401

        print("hf_xet: available")
    except Exception:
        print("hf_xet: unavailable; downloads can still work but may be slower")
    print("Doctor performs no network requests.")
    return 0


def command_inspect_resume(args: argparse.Namespace) -> int:
    roots = [Path(r).expanduser().resolve() for r in (args.root or [])]
    if args.dest:
        roots.append(Path(args.dest).expanduser().resolve())
    payload = _inspect_resume_state(search_roots=roots)
    json_rc = _emit_json(args, payload)
    if json_rc >= 0:
        return json_rc
    print(f"Resume state: {payload['state']}")
    for t in payload["transfers"]:
        status = "running" if t["is_running"] else "resumable"
        pct = f"{100 * t['completed_items'] / t['total_items']:.1f}%"
        gb = f"{t['completed_bytes'] / (1024**3):.2f} GB" if t["total_bytes"] else "unknown"
        print(f"  [{status}] {t['profile']} {pct} ({gb} / {t['total_items']} items)  plan: {t['resolved_plan_path']}")
    print(f"Next: {', '.join(payload['next_actions'])}")
    return 0


def command_verify_store(args: argparse.Namespace) -> int:
    dest = Path(args.dest) if args.dest else default_model_root()
    payload = _inspect_store(destination_root=dest)
    json_rc = _emit_json(args, payload)
    if json_rc >= 0:
        return json_rc
    print(f"Store: {payload['destination_root']}")
    print(f"Transfers: {len(payload['transfers'])}")
    print(f"Artifacts: {len(payload['artifacts'])}")
    print(f"Next: {', '.join(payload['next_actions'])}")
    return 0



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="leaf-models",
        description="Plan, resolve, apply, resume, and verify the canonical LeafOS model installation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("catalog", help="Show the five-slot canonical model registry")
    sub.add_parser("doctor", help="Check local installer dependencies without network access")

    download_doctor = sub.add_parser(
        "download-doctor",
        help="Hash and inventory local model downloads without downloading anything",
    )
    download_doctor.add_argument(
        "--dest",
        "--model-dir",
        dest="dest",
        default=None,
        help="Model storage root; auto-detects LEAF_MODEL_DIR, installer cache, then catalog default",
    )
    download_doctor.add_argument(
        "--minimum",
        type=int,
        default=7,
        help="Minimum valid catalog artifacts required before the doctor exits green",
    )
    download_doctor.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="Seconds to pause between hash output and size/location output",
    )
    download_doctor.add_argument("--algorithm", default="sha256", help="Hash algorithm; default sha256")
    download_doctor.add_argument("--report", default=None, help="Optional JSON report path")
    download_doctor.add_argument("--include-experimental", action="store_true")
    download_doctor.add_argument(
        "--include-untracked",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Also hash model-like files that are not selected by the catalog",
    )
    download_doctor.add_argument("--no-color", action="store_true")

    plan = sub.add_parser("plan", help="Write an offline, non-mutating installation plan")
    plan.add_argument("--json", action="store_true", help="Emit structured response envelope")
    plan.add_argument("--profile", choices=sorted(MODEL_CATALOG.profiles), default="default")
    plan.add_argument("--slot", type=int, action="append", help="Select a slot; repeat for multiple")
    plan.add_argument("--quant", action="append", default=[], metavar="SLOT=QUANT")
    plan.add_argument("--dest", default=None, help="Model storage root; defaults to LEAF_MODEL_DIR or ~/.leaf/models")
    plan.add_argument("--out", default="leaf-model-plan.json")
    plan.add_argument(
        "--allow-fallback",
        action="store_true",
        help="Allow resolve to use only the catalog's explicit fallback variants",
    )

    plan_pack = sub.add_parser("plan-pack", help="Write an installation plan from a model-pack JSON")
    plan_pack.add_argument("--json", action="store_true", help="Emit structured response envelope")
    plan_pack.add_argument("pack", help="Path to a leafos.model-pack.v1 JSON containing install.items")
    plan_pack.add_argument("--dest", default=None, help="Model storage root; defaults to LEAF_MODEL_DIR or ~/.leaf/models")
    plan_pack.add_argument("--out", default="leaf-model-plan.json")

    resolve = sub.add_parser("resolve", help="Read repository metadata and pin an installation plan")
    resolve.add_argument("--json", action="store_true", help="Emit structured response envelope")
    resolve.add_argument("plan")
    resolve.add_argument("--revision", default="main")
    resolve.add_argument("--out", default=None)

    show = sub.add_parser("show", help="Display a plan")
    show.add_argument("plan")
    show.add_argument("--json", action="store_true")

    status = sub.add_parser("status", help="Show plan and local artifact status")
    status.add_argument("plan")

    local_status = sub.add_parser(
        "local-status",
        help="Check local artifacts directly from a profile, using explicit fallbacks when allowed",
    )
    local_status.add_argument("--profile", choices=sorted(MODEL_CATALOG.profiles), default="default")
    local_status.add_argument("--dest", required=True, help="Model storage root to inspect")
    local_status.add_argument("--allow-fallback", action="store_true")
    local_status.add_argument("--model-dir-reason", default="")
    local_status.add_argument("--report", default=None)
    local_status.add_argument("--plan", default=None)
    local_status.add_argument("--resolved-plan", default=None)
    local_status.add_argument("--verification-report", default=None)

    verify = sub.add_parser("verify", help="Verify files against a resolved plan")
    verify.add_argument("--json", action="store_true", help="Emit structured response envelope")
    verify.add_argument("plan")
    verify.add_argument("--hash", action="store_true")
    verify.add_argument("--out", default=None)

    apply = sub.add_parser("apply", help="Download/resume the exact artifacts in a resolved plan")
    apply.add_argument("--json", action="store_true", help="Emit structured response envelope")
    apply.add_argument("plan")
    apply.add_argument("--yes", action="store_true", help="Required acknowledgement of downloads")
    apply.add_argument("--max-workers", type=int, default=8)
    apply.add_argument("--continue-on-error", action="store_true")
    apply.add_argument("--include-experimental", action="store_true")
    apply.add_argument("--confirm-heavy", default=None, metavar="MODEL_KEY")

    inspect_resume = sub.add_parser("inspect-resume", help="Discover running and resumable installations")
    inspect_resume.add_argument("--json", action="store_true", help="Emit structured response envelope")
    inspect_resume.add_argument("--dest", default=None, help="Model storage root")
    inspect_resume.add_argument("--root", action="append", default=[], help="Additional search root; repeatable")

    verify_store = sub.add_parser("verify-store", help="Verify all installed artifacts under a destination root")
    verify_store.add_argument("--json", action="store_true", help="Emit structured response envelope")
    verify_store.add_argument("--dest", default=None, help="Model storage root; defaults to LEAF_MODEL_DIR or ~/.leaf/models")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "catalog":
            print_catalog()
            return 0
        if args.command == "doctor":
            return command_doctor(args)
        if args.command == "download-doctor":
            return command_download_doctor(args)
        if args.command == "plan":
            return command_plan(args)
        if args.command == "plan-pack":
            return command_plan_pack(args)
        if args.command == "resolve":
            return command_resolve(args)
        if args.command == "show":
            return command_show(args)
        if args.command == "status":
            return command_status(args)
        if args.command == "local-status":
            return command_local_status(args)
        if args.command == "verify":
            return command_verify(args)
        if args.command == "apply":
            return command_apply(args)
        if args.command == "inspect-resume":
            return command_inspect_resume(args)
        if args.command == "verify-store":
            return command_verify_store(args)
    except (OSError, ValueError, KeyError, OrchestrationError) as exc:
        if getattr(args, "json", False):
            print(_json_out({"ok": False, "operation": getattr(args, "command", None), "state": "failed", "message": str(exc), "errors": [str(exc)], "next_actions": []}))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
