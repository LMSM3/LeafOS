"""Catalog-aware GGUF inventory for the isolated MOE-001 demo."""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .gguf import GGUFError, read_gguf_header
from .util import host_summary, sha256_file, sha256_json, utc_now


INVENTORY_SCHEMA = "leafos.moe.inventory/0.1"
_PARAMETER_LABEL = re.compile(
    r"(?i)(?<![a-z0-9])(?P<active>a)?(?P<count>\d+(?:\.\d+)?)b(?![a-z0-9])"
)


def _total_parameter_labels(text: str) -> List[Dict[str, Any]]:
    labels: Dict[str, float] = {}
    for match in _PARAMETER_LABEL.finditer(text or ""):
        if match.group("active"):
            continue
        normalized = match.group(0).upper()
        labels[normalized] = float(match.group("count"))
    return [{"label": label, "billions": labels[label]} for label in sorted(labels)]


def _label_matches_parameter_count(label_billions: float, parameter_count: int) -> bool:
    observed_billions = parameter_count / 1_000_000_000.0
    tolerance_billions = max(0.5, label_billions * 0.05)
    return abs(observed_billions - label_billions) <= tolerance_billions


def _load_catalog(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("models"), list):
        raise ValueError("Unsupported LeafOS model catalog shape")
    return payload


def _catalog_matches(path: Path, model_root: Path, catalog: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        relative = path.relative_to(model_root)
    except ValueError:
        return []
    matches: List[Dict[str, Any]] = []
    for model in catalog["models"]:
        local_dir = Path(str(model["local_dir"]))
        relative_prefix = tuple(part.casefold() for part in relative.parts[: len(local_dir.parts)])
        local_prefix = tuple(part.casefold() for part in local_dir.parts)
        if relative_prefix != local_prefix:
            continue
        candidate_relative = relative.as_posix()
        candidate_name = path.name
        for quant, variant in model.get("variants", {}).items():
            for pattern in variant.get("patterns", []):
                if fnmatch.fnmatch(candidate_name.casefold(), str(pattern).casefold()) or fnmatch.fnmatch(
                    candidate_relative.casefold(), str(pattern).casefold()
                ):
                    matches.append(
                        {
                            "slot": int(model["slot"]),
                            "key": str(model["key"]),
                            "title": str(model["title"]),
                            "repo_id": str(model["repo_id"]),
                            "role": str(model["role"]),
                            "quant": str(quant),
                            "pattern": str(pattern),
                            "experimental": bool(model.get("experimental", False)),
                        }
                    )
    matches.sort(key=lambda item: (item["slot"], item["quant"], item["pattern"]))
    return matches


def _architecture_summary(metadata: Dict[str, Any], parameter_count: Optional[int] = None) -> Dict[str, Any]:
    architecture = metadata.get("general.architecture")
    prefix = f"{architecture}." if architecture else ""

    def value(suffix: str) -> Any:
        direct = metadata.get(prefix + suffix) if prefix else None
        if direct is not None:
            return direct
        for key, item in metadata.items():
            if key.endswith("." + suffix):
                return item
        return None

    summary = {
        "architecture": architecture,
        "name": metadata.get("general.name"),
        "file_type": metadata.get("general.file_type"),
        "quantization_version": metadata.get("general.quantization_version"),
        "parameter_count": parameter_count,
        "block_count": value("block_count"),
        "context_length": value("context_length"),
        "embedding_length": value("embedding_length"),
        "expert_count": value("expert_count"),
        "expert_used_count": value("expert_used_count"),
        "expert_shared_count": value("expert_shared_count"),
        "attention_head_count": value("attention.head_count"),
        "attention_head_count_kv": value("attention.head_count_kv"),
    }
    summary["artifact_kind"] = (
        "projector"
        if architecture in {"clip", "siglip", "vision"}
        else "language_model"
    )
    return summary


def _identity_findings(path: Path, matches: List[Dict[str, Any]], summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    if not matches:
        findings.append(
            {
                "code": "catalog_untracked_artifact",
                "severity": "warning",
                "message": "The artifact does not match a catalog local directory and pattern.",
            }
        )
        return findings
    if len(matches) > 1:
        findings.append(
            {
                "code": "catalog_ambiguous_match",
                "severity": "error",
                "message": "The artifact matches more than one catalog variant.",
            }
        )

    declared_text = " ".join([path.name, *[str(item["title"]) for item in matches]])
    observed_text = str(summary.get("name") or "")
    declared_labels = _total_parameter_labels(declared_text)
    observed_labels = _total_parameter_labels(observed_text)
    parameter_count = summary.get("parameter_count")
    if isinstance(parameter_count, int) and parameter_count > 0:
        declared_mismatches = [
            item
            for item in declared_labels
            if not _label_matches_parameter_count(item["billions"], parameter_count)
        ]
        if declared_mismatches:
            findings.append(
                {
                    "code": "catalog_tensor_parameter_count_mismatch",
                    "severity": "error",
                    "message": "Catalog or filename parameter labels disagree with the tensor-derived parameter count.",
                    "declared_labels": [item["label"] for item in declared_labels],
                    "parameter_count": parameter_count,
                    "tolerance": "max(0.5B, 5% of the declared total-parameter label)",
                }
            )
        observed_mismatches = [
            item
            for item in observed_labels
            if not _label_matches_parameter_count(item["billions"], parameter_count)
        ]
        if observed_mismatches:
            findings.append(
                {
                    "code": "metadata_name_parameter_label_disagreement",
                    "severity": "warning",
                    "message": "Embedded general.name parameter labels disagree with the tensor-derived parameter count.",
                    "observed_labels": [item["label"] for item in observed_labels],
                    "parameter_count": parameter_count,
                }
            )
    elif declared_labels and observed_labels and declared_labels != observed_labels:
        findings.append(
            {
                "code": "metadata_name_parameter_label_disagreement",
                "severity": "warning",
                "message": "Catalog/filename and general.name labels differ, but no tensor-derived count is available.",
                "declared_labels": [item["label"] for item in declared_labels],
                "observed_labels": [item["label"] for item in observed_labels],
            }
        )
    return findings


def inspect_artifact(
    path: Path,
    model_root: Path,
    catalog: Dict[str, Any],
    hash_mode: str,
) -> Dict[str, Any]:
    source = path.expanduser().resolve()
    stat = source.stat()
    content_sha256: Optional[str] = None
    if hash_mode == "sha256":
        content_sha256 = sha256_file(source)

    errors: List[str] = []
    metadata: Dict[str, Any] = {}
    header_payload: Dict[str, Any] = {
        "valid": False,
        "version": None,
        "tensor_count": None,
        "parameter_count": None,
        "metadata_count": None,
        "metadata_bytes_read": None,
        "tensor_info_bytes_read": None,
    }
    try:
        header = read_gguf_header(source)
        metadata = header.metadata
        header_payload.update(
            {
                "valid": True,
                "version": header.version,
                "tensor_count": header.tensor_count,
                "parameter_count": header.parameter_count,
                "metadata_count": header.metadata_count,
                "metadata_bytes_read": header.metadata_bytes_read,
                "tensor_info_bytes_read": header.tensor_info_bytes_read,
            }
        )
    except (OSError, GGUFError) as exc:
        errors.append(str(exc))

    matches = _catalog_matches(source, model_root, catalog)
    summary = _architecture_summary(metadata, header_payload["parameter_count"])
    findings = _identity_findings(source, matches, summary) if header_payload["valid"] else []
    blockers = []
    if not header_payload["valid"]:
        blockers.append("invalid_gguf")
    if not content_sha256:
        blockers.append("content_sha256_missing")
    blockers.extend(item["code"] for item in findings if item["severity"] == "error")
    if not matches:
        blockers.append("catalog_untracked_artifact")

    try:
        relative = source.relative_to(model_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"Resolved artifact escaped the model root: {source}") from exc
    metadata_identity = {
        "gguf": header_payload,
        "model": summary,
        "inspection_errors": errors,
    }
    metadata_sha256 = sha256_json(metadata_identity)
    provisional_identity = sha256_json(
        {
            "relative_path": relative,
            "bytes": stat.st_size,
            "modified_at_ns": stat.st_mtime_ns,
            "metadata_sha256": metadata_sha256,
        }
    )
    return {
        "artifact_id": f"sha256:{content_sha256}" if content_sha256 else f"unverified:{provisional_identity}",
        "relative_path": relative,
        "absolute_path": str(source),
        "filename": source.name,
        "bytes": stat.st_size,
        "modified_at_ns": stat.st_mtime_ns,
        "content_sha256": content_sha256,
        "metadata_sha256": metadata_sha256,
        "gguf": header_payload,
        "model": summary,
        "catalog_matches": matches,
        "identity_findings": findings,
        "benchmark_admission": {
            "eligible": not blockers,
            "blockers": sorted(set(blockers)),
        },
        "inspection_errors": errors,
    }


def build_inventory(
    model_root: Path,
    catalog_path: Path,
    hash_mode: str = "none",
    include_patterns: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    if hash_mode not in {"none", "sha256"}:
        raise ValueError("hash_mode must be 'none' or 'sha256'")
    root = model_root.expanduser().resolve()
    catalog_source = catalog_path.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Model root not found: {root}")
    if not catalog_source.is_file():
        raise FileNotFoundError(f"Catalog not found: {catalog_source}")

    catalog = _load_catalog(catalog_source)
    patterns = list(include_patterns or ["*.gguf"])
    candidates = sorted(
        {
            path.resolve()
            for pattern in patterns
            for path in root.rglob(pattern)
            if path.is_file()
        },
        key=lambda path: str(path).casefold(),
    )
    artifacts = [inspect_artifact(path, root, catalog, hash_mode) for path in candidates]
    identity = {
        "model_root": str(root),
        "catalog_sha256": sha256_file(catalog_source),
        "hash_mode": hash_mode,
        "artifacts": [
            {
                "relative_path": item["relative_path"],
                "bytes": item["bytes"],
                "modified_at_ns": item["modified_at_ns"],
                "content_sha256": item["content_sha256"],
                "metadata_sha256": item["metadata_sha256"],
                "gguf_valid": item["gguf"]["valid"],
            }
            for item in artifacts
        ],
    }
    return {
        "schema": INVENTORY_SCHEMA,
        "schema_version": 1,
        "inventory_id": f"inventory:{sha256_json(identity)}",
        "generated_at": utc_now(),
        "host": host_summary(),
        "model_root": str(root),
        "catalog": {
            "path": str(catalog_source),
            "sha256": identity["catalog_sha256"],
            "catalog_version": catalog.get("catalog_version"),
        },
        "hash_mode": hash_mode,
        "artifact_count": len(artifacts),
        "valid_gguf_count": sum(1 for item in artifacts if item["gguf"]["valid"]),
        "benchmark_admissible_count": sum(1 for item in artifacts if item["benchmark_admission"]["eligible"]),
        "artifacts": artifacts,
    }
