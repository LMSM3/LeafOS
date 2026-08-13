from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

from ccis.kernel import (
    allocation_events,
    allocation_heap,
    allocation_lease,
    allocation_reducer,
    storage,
    task_registry,
)
from ccis.tests.test_milestone1 import changes, envelope, make_repo, patch_for, write_json
from loop import scientific_change_loop as change_loop


def proposal(
    task_id: str,
    *,
    priority: int = 50,
    not_before_tick: int = 0,
    deadline_tick: int | None = None,
    dependencies: list[dict] | None = None,
    resource: str | None = None,
    max_attempts: int = 2,
) -> dict:
    claims = [] if resource is None else [
        {"resource": resource, "mode": "exclusive", "amount": 1, "unit": "slot"}
    ]
    return {
        "ccis_object": "ccis.typed_task",
        "schema_version": 1,
        "task_id": task_id,
        "task_type": "system.allocation.rebuild",
        "task_version": 1,
        "objective": {
            "summary": f"Rebuild allocation fixture {task_id}.",
            "invariants": ["Authoritative allocation events remain unchanged."],
            "tolerances": [],
            "stopping_conditions": ["The projection is rebuilt or integrity verification fails."],
        },
        "target": {"kind": "allocation-root", "id": task_id, "ref": ".leafos/ccis/allocation", "digest": None},
        "inputs": [],
        "authority": {
            "requester": "ccis.test", "capabilities": ["allocation.rebuild"],
            "canonical_write": False, "automatic_acceptance": False,
        },
        "budget": {
            "wall_time_seconds": 30, "max_attempts": max_attempts, "max_processes": 1,
            "max_tokens": None, "context_tokens": None, "max_memory_mb": 128, "evidence_bytes": 100000,
        },
        "dependencies": dependencies or [],
        "resource_claims": claims,
        "retry_policy": {"max_attempts": max_attempts, "backoff_ticks": 1, "retryable_reasons": ["LEASE_EXPIRED"]},
        "validators": [],
        "output_contract": {"result_type": "ccis.typed_result", "result_version": 1},
        "provenance": {
            "source_wo": "WO-051", "instruction_digest": storage.digest(task_id), "source_event": None,
        },
        "priority": priority,
        "not_before_tick": not_before_tick,
        "deadline_tick": deadline_tick,
    }


class TypedTaskContractTests(unittest.TestCase):
    def test_registry_fails_closed_and_contract_rejects_private_authority(self) -> None:
        task = task_registry.admit_task(proposal("task-contract"))
        self.assertEqual("ccis.allocation.rebuild", task["native_handler"])
        self.assertEqual(task_registry.registry_digest(), task["provenance"]["registry_digest"])

        injected = proposal("task-injected")
        injected["native_handler"] = "tmp.run_generated_python"
        with self.assertRaisesRegex(storage.CCISError, "trusted registry"):
            task_registry.admit_task(injected)
        with self.assertRaisesRegex(storage.CCISError, "unregistered"):
            task_registry.resolve("model.do-whatever", 1)
        with self.assertRaisesRegex(storage.CCISError, "reserved"):
            task_registry.resolve("eval.llamacpp.stream", 1)

        unknown = proposal("task-unknown-field")
        unknown["shell_command"] = "python generated.py"
        with self.assertRaisesRegex(storage.CCISError, "unknown field"):
            task_registry.admit_task(unknown)

    def test_digest_binds_task_and_schema_represents_live_inference_resources(self) -> None:
        task = task_registry.admit_task(proposal("task-digest"))
        task["budget"]["wall_time_seconds"] += 1
        with self.assertRaisesRegex(storage.CCISError, "digest verification"):
            task_registry.verify_task(task)

        live = proposal("task-live-contract")
        live.update({
            "task_type": "eval.llamacpp.stream", "native_handler": "reserved.none",
            "resource_claims": [
                {"resource": "model:local.gguf", "mode": "shared", "amount": 1, "unit": "model"},
                {"resource": "accelerator:gpu:0", "mode": "exclusive", "amount": 8192, "unit": "MiB"},
                {"resource": "context", "mode": "shared", "amount": 4096, "unit": "tokens"},
                {"resource": "generation", "mode": "shared", "amount": 256, "unit": "tokens"},
                {"resource": "process", "mode": "exclusive", "amount": 1, "unit": "process"},
                {"resource": "tcp-port:8080", "mode": "exclusive", "amount": 1, "unit": "port"},
                {"resource": "stream:stdout", "mode": "exclusive", "amount": 1, "unit": "stream"},
                {"resource": "evidence", "mode": "shared", "amount": 100000, "unit": "bytes"},
            ],
        })
        live["budget"].update({"max_tokens": 256, "context_tokens": 4096, "evidence_bytes": 1000000})
        live["provenance"]["registry_digest"] = task_registry.registry_digest()
        live["task_digest"] = "sha256:" + "0" * 64
        live["task_digest"] = task_registry.task_digest(live)
        task_registry.validate_contract("typed-task", live)
        with self.assertRaisesRegex(storage.CCISError, "reserved"):
            task_registry.admit_task(live)

    def test_moe_task_types_are_handlerless_reservations_and_fail_closed(self) -> None:
        expected = {
            "bench.moe.inventory": ["cpu", "model"],
            "bench.moe.placement": ["cpu", "gpu", "model", "process"],
            "system.moe.contracts.verify": ["cpu"],
            "system.moe.scheduler.verify": ["cpu", "filesystem:allocation"],
            "system.gpu_lease.verify": ["cpu", "gpu", "model", "process"],
            "probe.moe.provider": ["cpu", "gpu", "model", "process"],
            "route.moe.expert": ["cpu"],
            "system.resource_governor.verify": ["cpu"],
            "debug.moe.evidence_repair": ["cpu", "workspace"],
            "system.moe_surface.verify": ["cpu"],
            "analysis.overnight_consolidation": ["cpu", "gpu", "model", "workspace"],
        }
        registry = task_registry.load_registry()
        self.assertEqual(32, len(registry["entries"]))
        for task_type, allowed_resources in expected.items():
            with self.subTest(task_type=task_type):
                entry = task_registry.resolve(task_type, 1, require_implemented=False)
                self.assertEqual("reserved", entry["status"])
                self.assertIsNone(entry["native_handler"])
                self.assertEqual("ccis.typed_result", entry["result_type"])
                self.assertEqual(allowed_resources, entry["allowed_resources"])
                with self.assertRaisesRegex(storage.CCISError, "reserved"):
                    task_registry.resolve(task_type, 1)

        reserved_proposal = proposal("task-moe-reserved")
        reserved_proposal["task_type"] = "bench.moe.inventory"
        with self.assertRaisesRegex(storage.CCISError, "reserved"):
            task_registry.admit_task(reserved_proposal)


class AllocationProjectionTests(unittest.TestCase):
    def test_ready_and_delayed_order_rebuild_byte_identically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            allocator = allocation_lease.Allocator(root)
            fixtures = [
                proposal("task-a", priority=40),
                proposal("task-b", priority=70, deadline_tick=20),
                proposal("task-c", priority=70, deadline_tick=10),
                proposal("task-d", priority=90, not_before_tick=8),
            ]
            for item in fixtures:
                allocator.admit(item)
                allocator.queue(item["task_id"])
            snapshot = allocator.status()["snapshot"]
            self.assertEqual(["task-c", "task-b", "task-a"], [item["task_id"] for item in snapshot["ready"]])
            self.assertEqual(["task-d"], [item["task_id"] for item in snapshot["delayed"]])
            original_bytes = allocation_heap.snapshot_path(root).read_bytes()
            allocation_heap.snapshot_path(root).unlink()
            status = allocator.status()
            self.assertEqual("REBUILT_MISSING_CACHE", status["cache_action"])
            self.assertEqual(original_bytes, allocation_heap.snapshot_path(root).read_bytes())

    def test_logical_clock_and_priority_change_only_through_events(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            allocator = allocation_lease.Allocator(root)
            allocator.admit(proposal("task-low", priority=10))
            allocator.queue("task-low")
            allocator.admit(proposal("task-delayed", priority=80, not_before_tick=5))
            allocator.queue("task-delayed")
            first = allocator.status()["snapshot"]
            second = allocator.status()["snapshot"]
            self.assertEqual(first["projection_digest"], second["projection_digest"])
            self.assertEqual(0, second["logical_tick"])
            self.assertEqual(["task-delayed"], [item["task_id"] for item in second["delayed"]])

            allocator.observe_clock(5, "operator accepted elapsed-wall-time proposal")
            self.assertEqual("task-delayed", allocator.status()["snapshot"]["ready"][0]["task_id"])
            allocator.age_priority("task-low", 90, "recorded starvation prevention")
            self.assertEqual("task-low", allocator.status()["snapshot"]["ready"][0]["task_id"])
            event_types = [item["event_type"] for item in allocation_events.read_events(root)]
            self.assertIn("allocation.clock_observed", event_types)
            self.assertIn("task.priority_aged", event_types)

    def test_dependencies_and_exclusive_claims_gate_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            allocator = allocation_lease.Allocator(root)
            allocator.admit(proposal("task-parent", priority=80, resource="filesystem:allocation"))
            allocator.queue("task-parent")
            allocator.admit(proposal(
                "task-child", priority=100,
                dependencies=[{"task_id": "task-parent", "required_disposition": "SUCCEEDED"}],
            ))
            allocator.queue("task-child")
            allocator.admit(proposal("task-conflict", priority=70, resource="filesystem:allocation"))
            allocator.queue("task-conflict")

            lease = allocator.claim_next("worker-1", lease_ticks=10)
            self.assertEqual("task-parent", lease["task_id"])
            blocked = allocator.status()["snapshot"]["blocked"]
            self.assertEqual({"task-child", "task-conflict"}, {item["task_id"] for item in blocked})
            self.assertIsNone(allocator.claim_next("worker-2", lease_ticks=10))
            allocator.start("task-parent", lease["lease_id"])
            allocator.finish("task-parent", lease["lease_id"], "SUCCEEDED", "fixture", storage.digest("result"))
            ready = allocator.status()["snapshot"]["ready"]
            self.assertEqual(["task-child", "task-conflict"], [item["task_id"] for item in ready])

    def test_lease_requeue_requires_recorded_clock_and_expiry_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            allocator = allocation_lease.Allocator(root)
            allocator.admit(proposal("task-expiring", max_attempts=2))
            allocator.queue("task-expiring")
            lease = allocator.claim_next("worker-1", lease_ticks=3)
            allocator.start("task-expiring", lease["lease_id"])
            self.assertEqual([], allocator.expire_due())
            self.assertEqual("RUNNING", allocator.status()["snapshot"]["tasks"][0]["state"])
            allocator.observe_clock(3, "operator recorded bounded lease time")
            self.assertEqual([lease["lease_id"]], allocator.expire_due())
            snapshot = allocator.status()["snapshot"]
            self.assertEqual("QUEUED", snapshot["tasks"][0]["state"])
            self.assertEqual("task-expiring", snapshot["ready"][0]["task_id"])
            self.assertEqual("lease.expired", allocation_events.read_events(root)[-1]["event_type"])

    def test_corrupt_cache_rebuilds_but_corrupt_authoritative_events_halt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            allocator = allocation_lease.Allocator(root)
            allocator.admit(proposal("task-integrity"))
            allocator.queue("task-integrity")
            allocation_heap.snapshot_path(root).write_text("{broken", encoding="utf-8")
            self.assertEqual("REBUILT_CORRUPT_CACHE", allocator.status()["cache_action"])

            event_path = allocation_events.events_path(root)
            lines = event_path.read_text(encoding="utf-8").splitlines()
            tampered = json.loads(lines[0])
            tampered["payload"]["task"]["priority"] = 999
            lines[0] = json.dumps(tampered)
            event_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(storage.CCISError, "payload hash mismatch"):
                allocator.status()


class ExistingValidatorAdapterTests(unittest.TestCase):
    def test_real_ccis_command_validator_runs_through_typed_allocator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root)
            task = envelope(repo, "task_adapter", "science.txt")
            task["validators"] = [{
                "validator_id": "adapter_validator", "kind": "command", "required": True,
                "command": [sys.executable, "-c", "print('typed allocation adapter')"],
                "timeout_seconds": 10,
            }]
            task_path = root / "task.json"
            write_json(task_path, task)
            run_dir = change_loop.initialize(task_path, root / "runs")
            patch = root / "candidate.patch"
            patch.write_text(patch_for("science.txt", "adapter"), encoding="utf-8", newline="\n")
            change_loop.register_candidate(run_dir, "candidate_adapter_r0", patch, changes("science.txt", "adapter"))
            workspace = root / "isolated-workspace"
            workspace.mkdir()

            result = allocation_lease.run_ccis_validator_task(root / "allocation", run_dir, workspace)
            self.assertEqual("SUCCEEDED", result["status"])
            self.assertIn("typed allocation adapter", (run_dir / "validation" / "stdout.log").read_text())
            snapshot = allocation_lease.Allocator(root / "allocation").status()["snapshot"]
            record = next(item for item in snapshot["tasks"] if item["task_id"] == "task_adapter:validate")
            self.assertEqual("SUCCEEDED", record["state"])
            self.assertIsNone(record["lease_id"])
            self.assertTrue((root / "allocation" / "results" / "task_adapter_validate.json").is_file())


if __name__ == "__main__":
    unittest.main()
