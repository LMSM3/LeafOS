"""Plan-first, resumable model installation orchestration."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .catalog import Catalog, MODEL_CATALOG


PLAN_SCHEMA_VERSION = 1
MIN_WEIGHT_BYTES = 1024 * 1024


class OrchestrationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    data = json.dumps(payload, indent=2) + "\n"
    try:
        temporary.write_text(data, encoding="utf-8")
        temporary.replace(path)
    except PermissionError:
        # Some Windows/OneDrive sandboxes allow normal writes but deny the
        # delete/rename privilege needed for atomic replacement. The fallback is
        # intentionally less elegant but keeps the plan-first installer usable.
        path.write_text(data, encoding="utf-8")
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def default_model_root(catalog: Catalog = MODEL_CATALOG) -> Path:
    configured = os.environ.get(catalog.storage["environment_variable"])
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / catalog.storage["default_relative_to_home"]).resolve()


@dataclass(frozen=True)
class PlanItem:
    slot: int
    key: str
    nickname: str
    role: str
    repo_id: str
    local_dir: str
    requested_quant: str
    selected_quant: str
    fallback_used: bool
    format: str
    patterns: list[str]
    excludes: list[str]
    estimated_bytes: Optional[int]
    experimental: bool
    revision: Optional[str] = None
    expected_files: Optional[list[dict]] = None


@dataclass(frozen=True)
class InstallPlan:
    schema_version: int
    plan_id: str
    created_at_utc: str
    catalog_version: str
    profile: str
    destination_root: str
    resolved: bool
    allow_fallback: bool
    items: list[PlanItem]

    @property
    def estimated_bytes(self) -> Optional[int]:
        values = [item.estimated_bytes for item in self.items]
        if any(value is None for value in values):
            return None
        return sum(int(value) for value in values if value is not None)


def _parse_quant_overrides(overrides: Iterable[str]) -> dict[int, str]:
    result: dict[int, str] = {}
    for raw in overrides:
        try:
            slot_text, quant = raw.split("=", 1)
            slot = int(slot_text)
        except ValueError as exc:
            raise OrchestrationError(f"Invalid quant override {raw!r}; expected SLOT=QUANT") from exc
        result[slot] = quant
    return result


def create_pack_plan(
    *,
    pack_path: Path,
    destination_root: Optional[Path] = None,
    catalog: Catalog = MODEL_CATALOG,
) -> InstallPlan:
    """Create an installation plan from a model-pack JSON with an install.items section."""
    if not pack_path.is_file():
        raise OrchestrationError(f"Pack file not found: {pack_path}")
    data = json.loads(pack_path.read_text(encoding="utf-8"))
    install = data.get("install") or {}
    items_data = install.get("items")
    if not items_data:
        raise OrchestrationError("Pack has no install.items section")

    by_key = catalog.by_key()
    items: list[PlanItem] = []
    seen_keys: set[tuple[str, str]] = set()
    for entry in items_data:
        key = entry["catalog_key"]
        quant = entry["quant"]
        dedup = (key, quant)
        if dedup in seen_keys:
            # Multiple pack roles may reference the same catalog key + quant;
            # the weight only needs to be downloaded once.
            continue
        seen_keys.add(dedup)
        if key not in by_key:
            valid = ", ".join(sorted(by_key))
            raise OrchestrationError(f"Unknown catalog_key in pack: {key!r}. Valid: {valid}")
        model = by_key[key]
        if quant not in model.variants:
            valid = ", ".join(model.variants)
            raise OrchestrationError(
                f"Pack item {key!r} does not support quant {quant!r}. Valid: {valid}"
            )
        variant = model.variants[quant]
        items.append(
            PlanItem(
                slot=model.slot,
                key=model.key,
                nickname=model.nickname,
                role=model.role,
                repo_id=model.repo_id,
                local_dir=model.local_dir,
                requested_quant=quant,
                selected_quant=quant,
                fallback_used=False,
                format=variant.format,
                patterns=list(variant.patterns),
                excludes=list(variant.excludes),
                estimated_bytes=variant.estimated_bytes,
                experimental=model.experimental,
            )
        )

    destination = (destination_root or default_model_root(catalog)).expanduser().resolve()
    return InstallPlan(
        schema_version=PLAN_SCHEMA_VERSION,
        plan_id=f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}",
        created_at_utc=utc_now(),
        catalog_version=catalog.catalog_version,
        profile=pack_path.stem,
        destination_root=str(destination),
        resolved=False,
        allow_fallback=bool(install.get("allow_fallback", False)),
        items=items,
    )


def create_plan(
    *,
    profile: str = "default",
    slots: Optional[Iterable[int]] = None,
    quant_overrides: Iterable[str] = (),
    destination_root: Optional[Path] = None,
    allow_fallback: bool = False,
    catalog: Catalog = MODEL_CATALOG,
) -> InstallPlan:
    if profile not in catalog.profiles:
        raise OrchestrationError(f"Unknown profile {profile!r}. Valid: {', '.join(catalog.profiles)}")
    selected_slots = list(slots) if slots else list(catalog.profiles[profile]["slots"])
    if not selected_slots:
        raise OrchestrationError("An installation plan must contain at least one slot")

    by_slot = catalog.by_slot()
    overrides = _parse_quant_overrides(quant_overrides)
    unknown_overrides = set(overrides) - set(selected_slots)
    if unknown_overrides:
        raise OrchestrationError(
            f"Quant overrides reference unselected slots: {sorted(unknown_overrides)}"
        )

    items: list[PlanItem] = []
    for slot in selected_slots:
        if slot not in by_slot:
            raise OrchestrationError(f"Unknown model slot: {slot}")
        model = by_slot[slot]
        quant = overrides.get(slot, model.default_quant)
        if quant not in model.variants:
            valid = ", ".join(model.variants)
            raise OrchestrationError(f"Slot {slot} does not support {quant!r}. Valid: {valid}")
        variant = model.variants[quant]
        items.append(
            PlanItem(
                slot=model.slot,
                key=model.key,
                nickname=model.nickname,
                role=model.role,
                repo_id=model.repo_id,
                local_dir=model.local_dir,
                requested_quant=quant,
                selected_quant=quant,
                fallback_used=False,
                format=variant.format,
                patterns=list(variant.patterns),
                excludes=list(variant.excludes),
                estimated_bytes=variant.estimated_bytes,
                experimental=model.experimental,
            )
        )

    destination = (destination_root or default_model_root(catalog)).expanduser().resolve()
    return InstallPlan(
        schema_version=PLAN_SCHEMA_VERSION,
        plan_id=f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}",
        created_at_utc=utc_now(),
        catalog_version=catalog.catalog_version,
        profile=profile,
        destination_root=str(destination),
        resolved=False,
        allow_fallback=allow_fallback,
        items=items,
    )


def plan_to_dict(plan: InstallPlan) -> dict:
    payload = asdict(plan)
    payload["estimated_bytes"] = plan.estimated_bytes
    return payload


def write_plan(plan: InstallPlan, path: Path) -> Path:
    atomic_write_json(path, plan_to_dict(plan))
    return path


def read_plan(path: Path) -> InstallPlan:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise OrchestrationError(f"Unsupported plan schema: {data.get('schema_version')!r}")
    items = [PlanItem(**item) for item in data["items"]]
    return InstallPlan(
        schema_version=data["schema_version"],
        plan_id=data["plan_id"],
        created_at_utc=data["created_at_utc"],
        catalog_version=data["catalog_version"],
        profile=data["profile"],
        destination_root=data["destination_root"],
        resolved=bool(data["resolved"]),
        allow_fallback=bool(data.get("allow_fallback", False)),
        items=items,
    )


def _remote_files(repo_id: str, revision: str) -> tuple[str, list[dict]]:
    try:
        from huggingface_hub import HfApi
    except Exception as exc:  # noqa: BLE001
        raise OrchestrationError(
            "huggingface_hub is required for resolve/apply; install the Leaf model installer first"
        ) from exc

    try:
        info = HfApi().model_info(repo_id=repo_id, revision=revision, files_metadata=True)
    except Exception as exc:  # noqa: BLE001
        raise OrchestrationError(f"Could not inspect {repo_id}@{revision}: {exc}") from exc

    files: list[dict] = []
    for sibling in info.siblings or []:
        size = getattr(sibling, "size", None)
        if size is None and getattr(sibling, "lfs", None):
            size = sibling.lfs.get("size")
        files.append({"path": sibling.rfilename, "bytes": size})
    return info.sha, files


def _matching(
    files: list[dict],
    patterns: Iterable[str],
    excludes: Iterable[str] = (),
) -> list[dict]:
    patterns = list(patterns)
    excludes = list(excludes)
    return sorted(
        (
            file
            for file in files
            if any(fnmatch.fnmatch(file["path"], pattern) for pattern in patterns)
            and not any(fnmatch.fnmatch(file["path"], exclude) for exclude in excludes)
        ),
        key=lambda item: item["path"],
    )


def resolve_plan(plan: InstallPlan, *, revision: str = "main", catalog: Catalog = MODEL_CATALOG) -> InstallPlan:
    by_slot = catalog.by_slot()
    resolved_items: list[PlanItem] = []
    for item in plan.items:
        model = by_slot[item.slot]
        commit, files = _remote_files(item.repo_id, revision)
        selected = item.selected_quant
        variant = model.variants[selected]
        matches = _matching(files, variant.patterns, variant.excludes)
        fallback_used = False

        if not matches and plan.allow_fallback:
            for fallback in model.fallback_quants:
                fallback_variant = model.variants[fallback]
                matches = _matching(files, fallback_variant.patterns, fallback_variant.excludes)
                if matches:
                    selected = fallback
                    variant = fallback_variant
                    fallback_used = True
                    break

        if not matches:
            fallback_hint = (
                f" Available explicit fallbacks: {', '.join(model.fallback_quants)}."
                if model.fallback_quants
                else ""
            )
            raise OrchestrationError(
                f"Slot {item.slot} ({item.key}) found no files for {item.selected_quant}: "
                f"{list(variant.patterns)}.{fallback_hint}"
            )

        remote_size = sum(int(file["bytes"]) for file in matches if file.get("bytes") is not None)
        resolved_items.append(
            replace(
                item,
                selected_quant=selected,
                fallback_used=fallback_used,
                format=variant.format,
                patterns=list(variant.patterns),
                excludes=list(variant.excludes),
                estimated_bytes=remote_size or variant.estimated_bytes,
                revision=commit,
                expected_files=matches,
            )
        )
    return replace(plan, resolved=True, items=resolved_items)


def _state_root(plan: InstallPlan, catalog: Catalog = MODEL_CATALOG) -> Path:
    return Path(plan.destination_root) / catalog.storage["state_directory"]


def append_event(plan: InstallPlan, event: dict) -> None:
    path = _state_root(plan) / "runs" / plan.plan_id / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"at_utc": utc_now(), **event}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


@contextmanager
def install_lock(plan: InstallPlan):
    lock_path = _state_root(plan) / "install.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise OrchestrationError(
            f"Another installation may be active: {lock_path}. Remove only after confirming no installer is running."
        ) from exc
    try:
        os.write(descriptor, f"{os.getpid()} {plan.plan_id}\n".encode("ascii"))
        os.close(descriptor)
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _validate_heavy(plan: InstallPlan, include_experimental: bool, confirm_heavy: Optional[str]) -> None:
    experimental = [item for item in plan.items if item.experimental]
    if not experimental:
        return
    if not include_experimental:
        raise OrchestrationError("Experimental slots require --include-experimental")
    keys = {item.key for item in experimental}
    if confirm_heavy not in keys:
        raise OrchestrationError(
            "Heavyweight confirmation missing; pass --confirm-heavy followed by the experimental model key"
        )


def _check_disk(plan: InstallPlan, safety_multiplier: float = 1.15) -> None:
    required = plan.estimated_bytes
    if required is None:
        raise OrchestrationError("Resolved plan still has unknown sizes; refusing an unbounded install")
    destination = Path(plan.destination_root)
    destination.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(destination).free
    needed = int(required * safety_multiplier)
    if free < needed:
        raise OrchestrationError(
            f"Insufficient disk space: need {needed} bytes with safety margin, have {free}"
        )


def _local_size(target: Path, expected_files: list[dict]) -> int:
    return sum(
        (target / file["path"]).stat().st_size
        for file in expected_files
        if (target / file["path"]).is_file()
    )


def verify_item(plan: InstallPlan, item: PlanItem, compute_hash: bool = False) -> dict:
    if not item.expected_files:
        raise OrchestrationError(f"Slot {item.slot} is unresolved")
    target = Path(plan.destination_root) / item.local_dir
    files: list[dict] = []
    missing: list[str] = []
    invalid: list[str] = []
    for expected in item.expected_files:
        local = target / expected["path"]
        exists = local.is_file()
        size = local.stat().st_size if exists else 0
        expected_size = expected.get("bytes")
        if not exists:
            missing.append(expected["path"])
        elif expected_size is not None and size != int(expected_size):
            invalid.append(expected["path"])
        elif local.suffix.lower() in {".gguf", ".safetensors"} and size < MIN_WEIGHT_BYTES:
            invalid.append(expected["path"])
        digest = None
        if exists and compute_hash:
            hasher = hashlib.sha256()
            with local.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
        files.append(
            {
                "repo_file": expected["path"],
                "local_path": str(local),
                "exists": exists,
                "bytes": size,
                "expected_bytes": expected_size,
                "sha256": digest,
            }
        )
    return {
        "slot": item.slot,
        "key": item.key,
        "selected_quant": item.selected_quant,
        "target_dir": str(target),
        "files": files,
        "missing_files": missing,
        "invalid_files": invalid,
        "success": not missing and not invalid,
    }


def verify_plan(plan: InstallPlan, compute_hash: bool = False) -> dict:
    if not plan.resolved:
        raise OrchestrationError("Verification requires a resolved plan")
    reports = [verify_item(plan, item, compute_hash=compute_hash) for item in plan.items]
    return {
        "schema_version": 1,
        "plan_id": plan.plan_id,
        "verified_at_utc": utc_now(),
        "success": all(report["success"] for report in reports),
        "items": reports,
    }


def apply_plan(
    plan: InstallPlan,
    *,
    max_workers: int = 8,
    include_experimental: bool = False,
    confirm_heavy: Optional[str] = None,
    continue_on_error: bool = False,
) -> dict:
    if not plan.resolved:
        raise OrchestrationError("Apply requires a resolved plan")
    _validate_heavy(plan, include_experimental, confirm_heavy)
    _check_disk(plan)

    try:
        from huggingface_hub import snapshot_download
    except Exception as exc:  # noqa: BLE001
        raise OrchestrationError("huggingface_hub is required to apply a plan") from exc

    os.environ["HF_XET_HIGH_PERFORMANCE"] = "1"
    os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)
    results: list[dict] = []

    with install_lock(plan):
        append_event(plan, {"event": "run_started", "items": len(plan.items)})
        for item in plan.items:
            target = Path(plan.destination_root) / item.local_dir
            target.mkdir(parents=True, exist_ok=True)
            before = _local_size(target, item.expected_files or [])
            started = time.perf_counter()
            append_event(plan, {"event": "item_started", "slot": item.slot, "key": item.key})
            try:
                expected_paths = [f["path"] for f in (item.expected_files or [])]
                download_kwargs: dict[str, object] = {
                    "repo_id": item.repo_id,
                    "revision": item.revision,
                    "allow_patterns": expected_paths if expected_paths else item.patterns,
                    "local_dir": str(target),
                    "max_workers": max_workers,
                }
                if item.excludes:
                    download_kwargs["ignore_patterns"] = item.excludes
                snapshot_download(**download_kwargs)
                verification = verify_item(plan, item)
                if not verification["success"]:
                    raise OrchestrationError(
                        f"Verification failed for slot {item.slot}: "
                        f"missing={verification['missing_files']} invalid={verification['invalid_files']}"
                    )
                elapsed = time.perf_counter() - started
                after = _local_size(target, item.expected_files or [])
                result = {
                    "slot": item.slot,
                    "key": item.key,
                    "status": "verified",
                    "elapsed_seconds": elapsed,
                    "transferred_bytes": max(0, after - before),
                    "verification": verification,
                }
                results.append(result)
                append_event(
                    plan,
                    {
                        "event": "item_verified",
                        "slot": item.slot,
                        "key": item.key,
                        "elapsed_seconds": elapsed,
                        "transferred_bytes": result["transferred_bytes"],
                    },
                )
            except Exception as exc:  # noqa: BLE001
                result = {"slot": item.slot, "key": item.key, "status": "failed", "error": str(exc)}
                results.append(result)
                append_event(plan, {"event": "item_failed", **result})
                if not continue_on_error:
                    break

        manifest = {
            "schema_version": 1,
            "plan_id": plan.plan_id,
            "completed_at_utc": utc_now(),
            "success": len(results) == len(plan.items)
            and all(item["status"] == "verified" for item in results),
            "results": results,
        }
        manifest_path = _state_root(plan) / "runs" / plan.plan_id / "manifest.json"
        atomic_write_json(manifest_path, manifest)
        append_event(plan, {"event": "run_finished", "success": manifest["success"]})
        return {**manifest, "manifest_path": str(manifest_path)}
