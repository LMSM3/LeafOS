from __future__ import annotations

import copy
import re
import time
from pathlib import Path
from typing import Any

from . import storage, validator_runner


CONTRACT_ROOT = Path(__file__).resolve().parents[1] / "contracts" / "allocation"
REGISTRY_PATH = CONTRACT_ROOT / "task-type-registry.json"
READ_ONLY_TASK_TYPES = {
    "ccis.command_validator", "debug.evidence_integrity", "probe.llamacpp.capability"
}


class TaskContractError(storage.CCISError):
    """A typed task or result failed closed at the registry boundary."""


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def _schema_error(location: str, message: str) -> TaskContractError:
    return TaskContractError(f"contract violation at {location}: {message}")


def _validate_node(value: Any, rule: dict[str, Any], root: dict[str, Any], location: str) -> None:
    reference = rule.get("$ref")
    if reference:
        prefix = "#/$defs/"
        if not isinstance(reference, str) or not reference.startswith(prefix):
            raise _schema_error(location, f"unsupported schema reference {reference!r}")
        name = reference[len(prefix):]
        definition = root.get("$defs", {}).get(name)
        if not isinstance(definition, dict):
            raise _schema_error(location, f"missing schema definition {name!r}")
        _validate_node(value, definition, root, location)
        return

    if "const" in rule and value != rule["const"]:
        raise _schema_error(location, f"expected constant {rule['const']!r}")
    if "enum" in rule and value not in rule["enum"]:
        raise _schema_error(location, f"value {value!r} is not registered in the enum")

    expected = rule.get("type")
    if expected is not None:
        choices = expected if isinstance(expected, list) else [expected]
        if not any(_json_type_matches(value, item) for item in choices):
            raise _schema_error(location, f"expected type {' or '.join(choices)}")

    if isinstance(value, dict):
        properties = rule.get("properties", {})
        missing = [name for name in rule.get("required", []) if name not in value]
        if missing:
            raise _schema_error(location, f"missing required field(s): {', '.join(missing)}")
        if rule.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise _schema_error(location, f"unknown field(s): {', '.join(unknown)}")
        for name, child in value.items():
            child_rule = properties.get(name)
            if isinstance(child_rule, dict):
                _validate_node(child, child_rule, root, f"{location}.{name}")

    if isinstance(value, list):
        minimum = rule.get("minItems")
        maximum = rule.get("maxItems")
        if minimum is not None and len(value) < minimum:
            raise _schema_error(location, f"requires at least {minimum} item(s)")
        if maximum is not None and len(value) > maximum:
            raise _schema_error(location, f"allows at most {maximum} item(s)")
        if rule.get("uniqueItems") and len({storage.canonical(item) for item in value}) != len(value):
            raise _schema_error(location, "items must be unique")
        item_rule = rule.get("items")
        if isinstance(item_rule, dict):
            for index, child in enumerate(value):
                _validate_node(child, item_rule, root, f"{location}[{index}]")

    if isinstance(value, str):
        minimum = rule.get("minLength")
        maximum = rule.get("maxLength")
        pattern = rule.get("pattern")
        if minimum is not None and len(value) < minimum:
            raise _schema_error(location, f"must contain at least {minimum} character(s)")
        if maximum is not None and len(value) > maximum:
            raise _schema_error(location, f"must contain at most {maximum} character(s)")
        if pattern is not None and re.search(pattern, value) is None:
            raise _schema_error(location, f"does not match {pattern!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = rule.get("minimum")
        maximum = rule.get("maximum")
        if minimum is not None and value < minimum:
            raise _schema_error(location, f"must be at least {minimum}")
        if maximum is not None and value > maximum:
            raise _schema_error(location, f"must be at most {maximum}")


def validate_contract(name: str, value: Any) -> None:
    path = CONTRACT_ROOT / f"{name}.schema.json"
    schema = storage.read_json(path)
    if not isinstance(schema, dict):
        raise TaskContractError(f"contract schema is missing or invalid: {path}")
    _validate_node(value, schema, schema, "$")


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    registry = storage.read_json(path)
    if not isinstance(registry, dict) or set(registry) != {"ccis_object", "schema_version", "entries"}:
        raise TaskContractError("task registry has an invalid root contract")
    if registry["ccis_object"] != "ccis.task_type_registry" or registry["schema_version"] != 1:
        raise TaskContractError("task registry identity/version is unsupported")
    if not isinstance(registry["entries"], list):
        raise TaskContractError("task registry entries must be an array")
    seen: set[tuple[str, int]] = set()
    allowed_fields = {
        "task_type", "task_version", "status", "native_handler", "result_type", "allowed_resources"
    }
    for index, entry in enumerate(registry["entries"]):
        if not isinstance(entry, dict) or set(entry) != allowed_fields:
            raise TaskContractError(f"registry entry {index} has unknown or missing fields")
        key = (entry.get("task_type"), entry.get("task_version"))
        if not isinstance(key[0], str) or not isinstance(key[1], int) or isinstance(key[1], bool):
            raise TaskContractError(f"registry entry {index} has an invalid task identity")
        if key in seen:
            raise TaskContractError(f"duplicate task registry entry: {key[0]}/v{key[1]}")
        seen.add(key)
        if entry.get("status") not in {"implemented", "reserved"}:
            raise TaskContractError(f"registry entry {index} has an invalid status")
        if entry["status"] == "implemented" and not isinstance(entry.get("native_handler"), str):
            raise TaskContractError(f"implemented registry entry {index} has no native handler")
        if entry["status"] == "reserved" and entry.get("native_handler") is not None:
            raise TaskContractError(f"reserved registry entry {index} unexpectedly has a handler")
    return registry


def registry_digest(registry: dict[str, Any] | None = None) -> str:
    return storage.digest(registry or load_registry())


def resolve(task_type: str, task_version: int, *, require_implemented: bool = True) -> dict[str, Any]:
    registry = load_registry()
    matches = [
        entry for entry in registry["entries"]
        if entry["task_type"] == task_type and entry["task_version"] == task_version
    ]
    if not matches:
        raise TaskContractError(f"unregistered task type/version: {task_type}/v{task_version}")
    entry = matches[0]
    if require_implemented and entry["status"] != "implemented":
        raise TaskContractError(f"task type is reserved but has no executable authority: {task_type}/v{task_version}")
    return entry


def task_digest(task: dict[str, Any]) -> str:
    bound = copy.deepcopy(task)
    bound.pop("task_digest", None)
    return storage.digest(bound)


def _validate_evidence_integrity_task(task: dict[str, Any]) -> None:
    if task.get("task_type") != "debug.evidence_integrity":
        return
    target = task.get("target", {})
    if target.get("kind") not in {"ccis-run", "ccis-evidence-bundle", "benchmark-run"}:
        raise TaskContractError("evidence integrity tasks accept only CCIS run, evidence-bundle, or benchmark-run references")
    if not isinstance(target.get("digest"), str):
        raise TaskContractError("evidence integrity tasks require a trusted external SHA-256 anchor")
    if task.get("inputs") != [] or task.get("dependencies") != []:
        raise TaskContractError("evidence integrity tasks accept only one run/bundle target reference")
    if task.get("resource_claims") != [] or task.get("validators") != []:
        raise TaskContractError("evidence integrity tasks cannot claim execution resources or launch validators")
    authority = task.get("authority", {})
    if authority.get("capabilities") != ["evidence.inspect"]:
        raise TaskContractError("evidence integrity authority is limited to evidence.inspect")
    budget = task.get("budget", {})
    if (
        budget.get("evidence_bytes") is None
        or budget.get("max_attempts") != 1
        or budget.get("max_processes") != 1
        or any(budget.get(name) is not None for name in ("max_tokens", "context_tokens", "max_memory_mb"))
    ):
        raise TaskContractError("evidence integrity tasks accept only bounded wall-time and evidence-byte inspection budgets")
    if task.get("retry_policy") != {"max_attempts": 1, "backoff_ticks": 0, "retryable_reasons": []}:
        raise TaskContractError("evidence integrity inspection is single-attempt and non-retrying")


def _validate_llamacpp_capability_task(task: dict[str, Any]) -> None:
    if task.get("task_type") != "probe.llamacpp.capability":
        return
    if task.get("target", {}).get("kind") != "host-capability":
        raise TaskContractError("llama.cpp preflight target must be a host-capability")
    inputs = task.get("inputs", [])
    by_name = {item.get("name"): item for item in inputs if isinstance(item, dict)}
    if set(by_name) not in ({"executable", "model", "backend"}, {"executable", "model", "backend", "expected-version"}):
        raise TaskContractError("llama.cpp preflight requires explicit executable, model, and backend inputs")
    expected_kinds = {
        "executable": "filesystem-executable", "model": "gguf-model",
        "backend": "accelerator-backend", "expected-version": "llamacpp-version",
    }
    if any(item.get("kind") != expected_kinds[name] for name, item in by_name.items()):
        raise TaskContractError("llama.cpp preflight input kinds do not match the native contract")
    if not all(isinstance(by_name[name].get("ref"), str) and by_name[name]["ref"] for name in by_name):
        raise TaskContractError("llama.cpp preflight inputs cannot be empty")
    backend = by_name["backend"]["ref"].lower()
    if backend not in {"cpu", "cuda", "hip", "metal", "sycl", "vulkan"}:
        raise TaskContractError(f"llama.cpp preflight backend is unsupported: {backend}")
    if task.get("dependencies") != [] or task.get("validators") != []:
        raise TaskContractError("llama.cpp preflight cannot depend on tasks or launch validators")
    authority = task.get("authority", {})
    if authority.get("capabilities") != ["llamacpp.preflight"] or authority.get("canonical_write") is not False:
        raise TaskContractError("llama.cpp preflight authority is strictly read-only")
    budget = task.get("budget", {})
    if (
        budget.get("max_attempts") != 1
        or budget.get("max_processes") != 2
        or budget.get("evidence_bytes") is None
        or any(budget.get(name) is not None for name in ("max_tokens", "context_tokens", "max_memory_mb"))
    ):
        raise TaskContractError("llama.cpp preflight accepts only wall-time, two metadata probes, and evidence-byte budgets")
    if task.get("retry_policy") != {"max_attempts": 1, "backoff_ticks": 0, "retryable_reasons": []}:
        raise TaskContractError("llama.cpp preflight is single-attempt and non-retrying")
    claims = task.get("resource_claims", [])
    resources = {claim.get("resource") for claim in claims if isinstance(claim, dict)}
    required = {"cpu", f"model:{by_name['model']['ref']}"}
    requested_accelerator = "cpu:backend" if backend == "cpu" else f"gpu:{backend}"
    required.add(requested_accelerator)
    if resources != required or len(claims) != 3:
        raise TaskContractError("llama.cpp preflight must claim CPU, the explicit model path, and requested accelerator")


def admit_task(proposal: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(proposal, dict):
        raise TaskContractError("typed task proposal must be an object")
    task = copy.deepcopy(proposal)
    task_type = task.get("task_type")
    task_version = task.get("task_version")
    if not isinstance(task_type, str) or not isinstance(task_version, int) or isinstance(task_version, bool):
        raise TaskContractError("typed task proposal lacks a valid task type/version")
    registry = load_registry()
    entry = resolve(task_type, task_version)
    supplied_handler = task.get("native_handler")
    if supplied_handler not in {None, entry["native_handler"]}:
        raise TaskContractError("model- or caller-supplied handler does not match the trusted registry")
    task["native_handler"] = entry["native_handler"]
    provenance = task.setdefault("provenance", {})
    if not isinstance(provenance, dict):
        raise TaskContractError("typed task provenance must be an object")
    expected_registry = registry_digest(registry)
    supplied_registry = provenance.get("registry_digest")
    if supplied_registry not in {None, expected_registry}:
        raise TaskContractError("task registry digest is stale or caller-supplied")
    provenance["registry_digest"] = expected_registry
    authority = task.get("authority", {})
    if authority.get("automatic_acceptance") is not False:
        raise TaskContractError("typed allocation tasks cannot possess automatic acceptance authority")
    if task_type in READ_ONLY_TASK_TYPES and authority.get("canonical_write") is not False:
        raise TaskContractError(f"{task_type} cannot write the canonical project")
    allowed_resources = entry["allowed_resources"]
    for claim in task.get("resource_claims", []):
        if not isinstance(claim, dict):
            continue
        resource = claim.get("resource")
        if not isinstance(resource, str) or not any(
            resource == allowed or resource.startswith(allowed + ":") for allowed in allowed_resources
        ):
            raise TaskContractError(
                f"resource {resource!r} is outside handler capability for {task_type}/v{task_version}"
            )
    budget = task.get("budget", {})
    retry = task.get("retry_policy", {})
    if budget.get("max_attempts") != retry.get("max_attempts"):
        raise TaskContractError("budget and retry-policy max_attempts disagree")
    dependencies = task.get("dependencies", [])
    identifiers = [item.get("task_id") for item in dependencies if isinstance(item, dict)]
    if len(identifiers) != len(set(identifiers)) or task.get("task_id") in identifiers:
        raise TaskContractError("task dependencies must be unique and cannot be self-referential")
    _validate_evidence_integrity_task(task)
    _validate_llamacpp_capability_task(task)
    supplied_digest = task.get("task_digest")
    task["task_digest"] = "sha256:" + "0" * 64
    computed = task_digest(task)
    if supplied_digest not in {None, "sha256:" + "0" * 64, computed}:
        raise TaskContractError("task digest does not bind the submitted task contract")
    task["task_digest"] = computed
    validate_contract("typed-task", task)
    return task


def verify_task(task: dict[str, Any]) -> dict[str, Any]:
    validate_contract("typed-task", task)
    entry = resolve(task["task_type"], task["task_version"])
    if task["native_handler"] != entry["native_handler"]:
        raise TaskContractError("typed task handler no longer matches the trusted registry")
    if task["provenance"]["registry_digest"] != registry_digest():
        raise TaskContractError("typed task was planned under a different registry digest")
    if task["task_digest"] != task_digest(task):
        raise TaskContractError("typed task digest verification failed")
    _validate_evidence_integrity_task(task)
    _validate_llamacpp_capability_task(task)
    return task


def _resource_use(task: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "resource": claim["resource"], "requested": claim["amount"],
        "reserved": claim["amount"], "consumed": 0, "remaining": 0,
        "unit": claim["unit"],
    } for claim in task["resource_claims"]]


def adapt_ccis_validator(run_dir: Path, workspace: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    workspace = workspace.expanduser().resolve()
    envelope = storage.read_json(run_dir / "task-envelope.json")
    metadata = storage.read_json(run_dir / "run.json")
    if not isinstance(envelope, dict) or not isinstance(metadata, dict):
        raise TaskContractError("CCIS validator adapter requires a valid run directory")
    original_id = str(envelope.get("task_id", "unknown"))
    validators = envelope.get("validators", [])
    typed_validators = [{
        "validator_id": str(item.get("validator_id", "validator")),
        "kind": str(item.get("kind", "command")), "required": bool(item.get("required", False)),
        "timeout_seconds": int(item.get("timeout_seconds", 300)),
    } for item in validators if isinstance(item, dict)]
    wall = int(envelope.get("budget", {}).get("wall_time_seconds", 300))
    proposal = {
        "ccis_object": "ccis.typed_task", "schema_version": 1,
        "task_id": f"{original_id}:validate", "task_type": "ccis.command_validator", "task_version": 1,
        "objective": {
            "summary": f"Run the declared validators for CCIS task {original_id}.",
            "invariants": ["The authoritative repository is never used as the validator workspace."],
            "tolerances": [],
            "stopping_conditions": ["All validators finish or the bounded wall-time budget is exhausted."],
        },
        "target": {"kind": "ccis-run", "id": original_id, "ref": str(run_dir), "digest": storage.digest(envelope)},
        "inputs": [{"name": "isolated-workspace", "kind": "filesystem-path", "ref": str(workspace), "digest": None}],
        "authority": {
            "requester": str(envelope.get("authority", {}).get("requester", "ccis.adapter")),
            "capabilities": ["validator.execute", "evidence.write"],
            "canonical_write": False, "automatic_acceptance": False,
        },
        "budget": {
            "wall_time_seconds": max(1, wall), "max_attempts": 1, "max_processes": 1,
            "max_tokens": None, "context_tokens": None, "max_memory_mb": None, "evidence_bytes": None,
        },
        "dependencies": [],
        "resource_claims": [
            {"resource": "cpu", "mode": "shared", "amount": 1, "unit": "process"},
            {"resource": f"workspace:{workspace}", "mode": "exclusive", "amount": 1, "unit": "workspace"},
        ],
        "retry_policy": {"max_attempts": 1, "backoff_ticks": 0, "retryable_reasons": []},
        "validators": typed_validators,
        "output_contract": {"result_type": "ccis.typed_result", "result_version": 1},
        "provenance": {
            "source_wo": "WO-051", "instruction_digest": storage.digest(envelope.get("instruction", "")),
            "source_event": None,
        },
        "priority": 50, "not_before_tick": 0, "deadline_tick": None,
    }
    return admit_task(proposal)


def adapt_evidence_integrity(
    target_ref: Path,
    target_kind: str,
    *,
    evidence_bytes: int,
    wall_time_seconds: int = 30,
    expected_digest: str | None = None,
    task_id: str | None = None,
    requester: str = "leafos.ccis.evidence_debugger",
) -> dict[str, Any]:
    from . import evidence_integrity

    reference = target_ref.expanduser().resolve(strict=False)
    if target_kind not in evidence_integrity.TARGET_KINDS:
        raise TaskContractError(f"unsupported evidence target kind: {target_kind}")
    if isinstance(evidence_bytes, bool) or not isinstance(evidence_bytes, int) or evidence_bytes < 1:
        raise TaskContractError("evidence inspection requires a positive byte budget")
    if isinstance(wall_time_seconds, bool) or not isinstance(wall_time_seconds, int) or wall_time_seconds < 1:
        raise TaskContractError("evidence inspection requires a positive wall-time budget")
    evidence_integrity.manifest_path(target_kind, reference).resolve(strict=True)
    target_digest_value = evidence_integrity.normalize_digest(expected_digest)
    if target_digest_value is None:
        raise TaskContractError("evidence inspection requires a trusted expected SHA-256 digest")
    identity = storage.digest({
        "kind": target_kind,
        "ref": str(reference),
        "digest": target_digest_value,
        "evidence_bytes": evidence_bytes,
        "wall_time_seconds": wall_time_seconds,
    })
    identifier = task_id or f"integrity:{identity.removeprefix('sha256:')[:24]}"
    proposal = {
        "ccis_object": "ccis.typed_task", "schema_version": 1,
        "task_id": identifier, "task_type": "debug.evidence_integrity", "task_version": 1,
        "objective": {
            "summary": f"Inspect {target_kind} evidence without mutation.",
            "invariants": ["The inspected target, Git index, and working tree remain byte-identical."],
            "tolerances": [],
            "stopping_conditions": ["The first integrity fault is localized or the inspection budget is exhausted."],
        },
        "target": {"kind": target_kind, "id": identifier, "ref": str(reference), "digest": target_digest_value},
        "inputs": [],
        "authority": {
            "requester": requester, "capabilities": ["evidence.inspect"],
            "canonical_write": False, "automatic_acceptance": False,
        },
        "budget": {
            "wall_time_seconds": wall_time_seconds, "max_attempts": 1, "max_processes": 1,
            "max_tokens": None, "context_tokens": None, "max_memory_mb": None,
            "evidence_bytes": evidence_bytes,
        },
        "dependencies": [], "resource_claims": [],
        "retry_policy": {"max_attempts": 1, "backoff_ticks": 0, "retryable_reasons": []},
        "validators": [],
        "output_contract": {"result_type": "ccis.typed_result", "result_version": 1},
        "provenance": {"source_wo": "WO-052", "instruction_digest": identity, "source_event": None},
        "priority": 60, "not_before_tick": 0, "deadline_tick": None,
    }
    return admit_task(proposal)


def adapt_llamacpp_capability(
    executable: Path,
    model: Path,
    backend: str,
    *,
    expected_version: str | None = None,
    evidence_bytes: int = 1_000_000,
    wall_time_seconds: int = 30,
    task_id: str | None = None,
    requester: str = "leafos.ccis.llamacpp_preflight",
) -> dict[str, Any]:
    executable_ref = str(executable.expanduser().resolve(strict=False))
    model_ref = str(model.expanduser().resolve(strict=False))
    backend_ref = backend.strip().lower()
    if not executable_ref or not model_ref or not backend_ref:
        raise TaskContractError("llama.cpp preflight requires explicit executable, model, and backend values")
    if isinstance(evidence_bytes, bool) or not isinstance(evidence_bytes, int) or evidence_bytes < 1:
        raise TaskContractError("llama.cpp preflight requires a positive evidence-byte budget")
    if isinstance(wall_time_seconds, bool) or not isinstance(wall_time_seconds, int) or wall_time_seconds < 2:
        raise TaskContractError("llama.cpp preflight requires at least two seconds of wall time")
    identity = storage.digest({
        "executable": executable_ref, "model": model_ref, "backend": backend_ref,
        "expected_version": expected_version, "evidence_bytes": evidence_bytes,
        "wall_time_seconds": wall_time_seconds,
    })
    identifier = task_id or f"llamacpp-preflight:{identity.removeprefix('sha256:')[:24]}"
    inputs = [
        {"name": "executable", "kind": "filesystem-executable", "ref": executable_ref, "digest": None},
        {"name": "model", "kind": "gguf-model", "ref": model_ref, "digest": None},
        {"name": "backend", "kind": "accelerator-backend", "ref": backend_ref, "digest": None},
    ]
    if expected_version is not None:
        if not isinstance(expected_version, str) or not expected_version.strip():
            raise TaskContractError("expected llama.cpp version must be a non-empty string")
        inputs.append({
            "name": "expected-version", "kind": "llamacpp-version",
            "ref": expected_version.strip(), "digest": None,
        })
    accelerator = "cpu:backend" if backend_ref == "cpu" else f"gpu:{backend_ref}"
    proposal = {
        "ccis_object": "ccis.typed_task", "schema_version": 1,
        "task_id": identifier, "task_type": "probe.llamacpp.capability", "task_version": 1,
        "objective": {
            "summary": "Inspect one explicit llama.cpp executable, GGUF model, and backend without inference.",
            "invariants": [
                "No model is loaded and no tokens are generated.",
                "No server, network request, download, or canonical write occurs.",
            ],
            "tolerances": [],
            "stopping_conditions": ["All metadata checks finish or the bounded wall-time expires."],
        },
        "target": {"kind": "host-capability", "id": identifier, "ref": "local-host", "digest": None},
        "inputs": inputs,
        "authority": {
            "requester": requester, "capabilities": ["llamacpp.preflight"],
            "canonical_write": False, "automatic_acceptance": False,
        },
        "budget": {
            "wall_time_seconds": wall_time_seconds, "max_attempts": 1, "max_processes": 2,
            "max_tokens": None, "context_tokens": None, "max_memory_mb": None,
            "evidence_bytes": evidence_bytes,
        },
        "dependencies": [],
        "resource_claims": [
            {"resource": "cpu", "mode": "shared", "amount": 1, "unit": "process"},
            {"resource": f"model:{model_ref}", "mode": "shared", "amount": 1, "unit": "model"},
            {"resource": accelerator, "mode": "shared", "amount": 1, "unit": "backend"},
        ],
        "retry_policy": {"max_attempts": 1, "backoff_ticks": 0, "retryable_reasons": []},
        "validators": [],
        "output_contract": {"result_type": "ccis.typed_result", "result_version": 1},
        "provenance": {"source_wo": "WO-053-B", "instruction_digest": identity, "source_event": None},
        "priority": 70, "not_before_tick": 0, "deadline_tick": None,
    }
    return admit_task(proposal)


def execute_typed_task(task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    task = verify_task(task)
    started_at = storage.now()
    started = time.monotonic()
    handler = task["native_handler"]
    if handler == "ccis.validator.command":
        legacy = validator_runner.run_validators(Path(context["run_dir"]), Path(context["workspace"]))
        passed = bool(legacy["validation"]["required_passed"])
        status = "SUCCEEDED" if passed else "REVISE"
        summary = "Required CCIS validators passed." if passed else "One or more required CCIS validators failed."
        output = {"legacy_validation": legacy, "duration_ms": round((time.monotonic() - started) * 1000)}
        evidence_refs = [str(path) for path in legacy["artifacts"].values()]
    elif handler == "ccis.allocation.rebuild":
        from . import allocation_heap

        snapshot = allocation_heap.rebuild(Path(context["allocation_root"]))
        status = "SUCCEEDED"
        summary = "Allocation projection rebuilt from authoritative events."
        output = {"snapshot": snapshot, "duration_ms": round((time.monotonic() - started) * 1000)}
        evidence_refs = [str(allocation_heap.snapshot_path(Path(context["allocation_root"])))]
    elif handler == "ccis.debug.evidence_integrity":
        from . import evidence_integrity

        diagnostic = evidence_integrity.inspect_task(task)
        validate_contract("evidence-integrity-diagnostic", diagnostic)
        disposition = diagnostic["disposition"]
        if disposition == "CLEAN":
            status = "SUCCEEDED"
            summary = "Evidence integrity inspection found no mismatch."
        elif disposition in evidence_integrity.TAMPER_DISPOSITIONS:
            status = "REVISE"
            summary = f"Evidence integrity inspection localized {disposition.lower()}."
        else:
            status = "BLOCKED"
            summary = f"Evidence integrity inspection stopped with {disposition.lower()}."
        output = {"diagnostic": diagnostic, "diagnostic_digest": storage.digest(diagnostic)}
        evidence_refs = [task["target"]["ref"]]
    elif handler == "ccis.probe.llamacpp.capability":
        import sys

        runtime_root = Path(__file__).resolve().parents[2] / "ProjectLeaf" / "leafos_taskpack" / "core" / "runtime"
        if str(runtime_root) not in sys.path:
            sys.path.insert(0, str(runtime_root))
        from llamacpp_preflight import probe

        inputs = {item["name"]: item["ref"] for item in task["inputs"]}
        capability = probe(
            executable=inputs["executable"], model=inputs["model"], backend=inputs["backend"],
            expected_version=inputs.get("expected-version"),
            timeout_seconds=max(1, task["budget"]["wall_time_seconds"] // 2),
            task_digest=task["task_digest"],
        )
        if capability["capable"]:
            status = "SUCCEEDED"
            summary = "Explicit llama.cpp binary, GGUF model, backend, and host preflight passed."
        elif any(item["code"] == "OPT_IN_REQUIRED" for item in capability["failures"]):
            status = "BLOCKED"
            summary = "llama.cpp preflight requires explicit operator opt-in."
        else:
            status = "FAILED"
            summary = "llama.cpp capability preflight failed explicit prerequisite checks."
        output = {"capability": capability}
        evidence_refs = [inputs["executable"], inputs["model"]]
    else:
        raise TaskContractError(f"registered handler has no native dispatcher: {handler}")
    result = {
        "ccis_object": "ccis.typed_result", "schema_version": 1,
        "task_id": task["task_id"], "task_digest": task["task_digest"],
        "task_type": task["task_type"], "task_version": task["task_version"],
        "status": status, "summary": summary, "started_at": started_at,
        "completed_at": storage.now(), "evidence_refs": evidence_refs,
        "resource_use": _resource_use(task), "output": output,
    }
    validate_contract("typed-result", result)
    return result
