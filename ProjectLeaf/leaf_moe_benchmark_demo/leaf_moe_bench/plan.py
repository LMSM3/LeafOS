"""Deterministic benchmark-plan construction from versioned evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .inventory import INVENTORY_SCHEMA
from .provider import PROVIDER_SCHEMA
from .util import read_json, sha256_json, utc_now


MATRIX_SCHEMA = "leafos.moe.benchmark-matrix/0.1"
PLAN_SCHEMA = "leafos.moe.benchmark-plan/0.1"


def _require_schema(payload: Dict[str, Any], expected: str, label: str) -> None:
    if payload.get("schema") != expected:
        raise ValueError(f"{label} schema must be {expected!r}, got {payload.get('schema')!r}")


def load_matrix(path: Path) -> Dict[str, Any]:
    payload = read_json(path)
    _require_schema(payload, MATRIX_SCHEMA, "matrix")
    if not payload.get("placements") or not payload.get("workloads"):
        raise ValueError("Benchmark matrix must define placements and workloads")
    placement_ids = [item["id"] for item in payload["placements"]]
    workload_ids = [item["id"] for item in payload["workloads"]]
    if len(placement_ids) != len(set(placement_ids)):
        raise ValueError("Benchmark placement IDs must be unique")
    if len(workload_ids) != len(set(workload_ids)):
        raise ValueError("Benchmark workload IDs must be unique")
    return payload


def _is_moe(artifact: Dict[str, Any]) -> bool:
    expert_count = artifact.get("model", {}).get("expert_count")
    return isinstance(expert_count, int) and expert_count > 0


def _resolve_cpu_moe(value: Any, artifact: Dict[str, Any]) -> int:
    if value in (None, 0, "0"):
        return 0
    blocks = artifact.get("model", {}).get("block_count")
    if not isinstance(blocks, int) or blocks <= 0:
        raise ValueError(f"Cannot resolve n_cpu_moe={value!r} without a positive block_count")
    if value == "half":
        return max(1, blocks // 2)
    if value == "all":
        return blocks
    resolved = int(value)
    if resolved < 0 or resolved > blocks:
        raise ValueError(f"n_cpu_moe={resolved} is outside 0..{blocks}")
    return resolved


def _validate_positive_int(value: Any, label: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _entry_command(
    provider: Dict[str, Any],
    artifact: Dict[str, Any],
    placement: Dict[str, Any],
    workload: Dict[str, Any],
) -> List[str]:
    args = placement.get("args", {})
    command = [
        str(provider["executable"]),
        "--offline",
        "--model",
        str(artifact["absolute_path"]),
        "--output",
        "jsonl",
        "--output-err",
        "none",
        "--repetitions",
        str(_validate_positive_int(workload.get("repetitions", 3), "repetitions")),
        "--n-prompt",
        str(_validate_positive_int(workload["prompt_tokens"], "prompt_tokens")),
        "--n-gen",
        str(_validate_positive_int(workload["generation_tokens"], "generation_tokens")),
        "--batch-size",
        str(_validate_positive_int(workload.get("batch_size", 512), "batch_size")),
        "--ubatch-size",
        str(_validate_positive_int(workload.get("ubatch_size", 256), "ubatch_size")),
        "--threads",
        str(_validate_positive_int(args.get("threads", 16), "threads")),
        "--n-gpu-layers",
        str(int(args.get("n_gpu_layers", 0))),
    ]
    if args.get("device") is not None:
        device = str(args["device"]).strip()
        if not device:
            raise ValueError("device must be a non-empty llama.cpp device selector")
        command.extend(["--device", device])
    if args.get("no_op_offload") is not None:
        command.extend(["--no-op-offload", "1" if args["no_op_offload"] else "0"])
    command.extend(["--mmap", "1" if args.get("mmap", True) else "0"])
    cpu_moe = _resolve_cpu_moe(args.get("n_cpu_moe", 0), artifact)
    if cpu_moe:
        command.extend(["--n-cpu-moe", str(cpu_moe)])
    if args.get("fit_target_mib") is not None:
        command.extend(["--fit-target", str(_validate_positive_int(args["fit_target_mib"], "fit_target_mib"))])
    if args.get("flash_attention"):
        flash = str(args["flash_attention"])
        if flash not in {"on", "off", "auto"}:
            raise ValueError("flash_attention must be on, off, or auto")
        command.extend(["--flash-attn", flash])
    return command


def _benchmark_admission_blockers(artifact: Dict[str, Any]) -> List[str]:
    return sorted(set(artifact.get("benchmark_admission", {}).get("blockers", [])))


def build_plan(
    inventory: Dict[str, Any],
    provider: Dict[str, Any],
    matrix: Dict[str, Any],
    artifact_paths: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    _require_schema(inventory, INVENTORY_SCHEMA, "inventory")
    _require_schema(provider, PROVIDER_SCHEMA, "provider")
    _require_schema(matrix, MATRIX_SCHEMA, "matrix")
    selected_paths = {str(item) for item in artifact_paths or []}

    entries: List[Dict[str, Any]] = []
    for artifact in inventory["artifacts"]:
        if selected_paths and artifact["relative_path"] not in selected_paths:
            continue
        if not artifact.get("gguf", {}).get("valid"):
            continue
        if artifact.get("model", {}).get("artifact_kind") != "language_model":
            continue
        artifact_is_moe = _is_moe(artifact)
        for placement in matrix["placements"]:
            applies_to = placement.get("applies_to", "all")
            if applies_to == "moe" and not artifact_is_moe:
                continue
            if applies_to == "dense" and artifact_is_moe:
                continue
            for workload in matrix["workloads"]:
                execution_blockers: List[str] = []
                if not provider.get("usable"):
                    execution_blockers.append("provider_probe_not_usable")
                if placement.get("requires_gpu") and not provider.get("gpu_available"):
                    execution_blockers.append("provider_has_no_gpu_device")
                placement_args = placement.get("args", {})
                capabilities = provider.get("capabilities", {})
                if placement_args.get("n_cpu_moe") and not capabilities.get("n_cpu_moe"):
                    execution_blockers.append("provider_lacks_n_cpu_moe")
                if placement_args.get("device") is not None and not capabilities.get("device"):
                    execution_blockers.append("provider_lacks_device_selection")
                if placement_args.get("no_op_offload") is not None and not capabilities.get("no_op_offload"):
                    execution_blockers.append("provider_lacks_no_op_offload")
                if placement_args.get("fit_target_mib") and not capabilities.get("fit_target"):
                    execution_blockers.append("provider_lacks_fit_target")
                if placement_args.get("flash_attention") and not capabilities.get("flash_attn"):
                    execution_blockers.append("provider_lacks_flash_attn")
                command = _entry_command(provider, artifact, placement, workload)
                entry_key = {
                    "inventory_id": inventory["inventory_id"],
                    "provider_sha256": provider["executable_sha256"],
                    "artifact": artifact["artifact_id"],
                    "placement": placement["id"],
                    "workload": workload["id"],
                    "command": command,
                }
                admission_blockers = _benchmark_admission_blockers(artifact)
                promotion_blockers = sorted(
                    set([*admission_blockers, "statistical_promotion_analysis_missing"])
                )
                entries.append(
                    {
                        "entry_id": f"bench:{sha256_json(entry_key)[:24]}",
                        "artifact_id": artifact["artifact_id"],
                        "relative_path": artifact["relative_path"],
                        "absolute_path": artifact["absolute_path"],
                        "bytes": artifact["bytes"],
                        "modified_at_ns": artifact["modified_at_ns"],
                        "content_sha256": artifact["content_sha256"],
                        "metadata_sha256": artifact["metadata_sha256"],
                        "model": artifact["model"],
                        "catalog_matches": artifact["catalog_matches"],
                        "placement_id": placement["id"],
                        "workload_id": workload["id"],
                        "command": command,
                        "ready": not execution_blockers,
                        "execution_blockers": sorted(set(execution_blockers)),
                        "benchmark_admission_blockers": admission_blockers,
                        "promotion_blockers": promotion_blockers,
                        "requires_experimental_identity_override": (
                            bool(
                                {
                                    "catalog_metadata_parameter_label_mismatch",
                                    "catalog_tensor_parameter_count_mismatch",
                                }.intersection(admission_blockers)
                            )
                        ),
                    }
                )

    entries.sort(key=lambda item: (item["relative_path"].casefold(), item["placement_id"], item["workload_id"]))
    identity = {
        "inventory_id": inventory["inventory_id"],
        "provider_sha256": provider["executable_sha256"],
        "matrix": matrix,
        "entries": [
            {
                "entry_id": item["entry_id"],
                "command": item["command"],
                "ready": item["ready"],
                "promotion_blockers": item["promotion_blockers"],
            }
            for item in entries
        ],
    }
    return {
        "schema": PLAN_SCHEMA,
        "schema_version": 1,
        "plan_id": f"plan:{sha256_json(identity)}",
        "generated_at": utc_now(),
        "inventory_id": inventory["inventory_id"],
        "provider": provider,
        "matrix_id": matrix.get("matrix_id"),
        "entry_count": len(entries),
        "ready_count": sum(1 for item in entries if item["ready"]),
        "entries": entries,
    }
