from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from ccis.kernel import (
    allocation_heap,
    allocation_lease,
    evidence_gate,
    evidence_integrity,
    storage,
    task_registry,
)
from ccis.tests.test_milestone1 import command, make_repo


def tree_digest(root: Path) -> str:
    entries = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        entries.append({"path": path.relative_to(root).as_posix(), "sha256": storage.file_digest(path)})
    return storage.digest(entries)


def write_bundle(root: Path) -> Path:
    root.mkdir(parents=True)
    artifacts: dict[str, dict[str, str]] = {}
    for name, filename in evidence_gate.REQUIRED_ARTIFACTS.items():
        path = root / filename
        if filename.endswith(".json"):
            path.write_text(json.dumps({"fixture": name}) + "\n", encoding="utf-8")
        elif filename.endswith(".jsonl"):
            path.write_text(json.dumps({"fixture": name}) + "\n", encoding="utf-8")
        else:
            path.write_text(f"fixture:{name}\n", encoding="utf-8")
        artifacts[name] = {"path": filename, "sha256": storage.file_digest(path)}
    manifest = {
        "ccis_object": "ccis.evidence_bundle",
        "schema_version": 1,
        "bundle_id": "bundle_fixture",
        "task_id": "task_fixture",
        "transition_id": "transition_fixture",
        "created_at": "2026-08-03T00:00:00Z",
        "artifacts": artifacts,
    }
    manifest["bundle_hash"] = storage.digest(manifest)
    path = root / "evidence-bundle.json"
    storage.atomic_json(path, manifest)
    evidence_gate.verify_evidence_bundle(path)
    return path


def write_benchmark_run(root: Path) -> tuple[Path, Path, Path]:
    root.mkdir(parents=True)
    stdout = root / "bench_fixture.stdout.txt"
    stderr = root / "bench_fixture.stderr.txt"
    stdout.write_text('{"avg_ts": 8.715705}\n', encoding="utf-8")
    stderr.write_text("", encoding="utf-8")
    manifest = {
        "schema": "leafos.moe.benchmark-run",
        "schema_version": 1,
        "run_id": "run-live-inference-fixture",
        "plan_id": "plan-fixture",
        "success": True,
        "results": [{
            "entry_id": "bench:fixture",
            "status": "succeeded",
            "command": ["llama-bench", "--offline", "--n-gpu-layers", "0", "--no-op-offload", "1"],
            "benchmark_rows": [{
                "model_type": "qwen35moe 35B.A3B MXFP4 MoE",
                "model_n_params": 14137111168,
                "model_size": 8829962752,
                "n_prompt": 0,
                "n_gen": 64,
                "avg_ts": 8.715705,
            }],
            "stdout": {"path": str(stdout.resolve()), "sha256": storage.file_digest(stdout).removeprefix("sha256:")},
            "stderr": {"path": str(stderr.resolve()), "sha256": storage.file_digest(stderr).removeprefix("sha256:")},
            "promotion": {"eligible": False, "blockers": ["statistical_promotion_analysis_missing"]},
        }],
    }
    path = root / "run.json"
    storage.atomic_json(path, manifest)
    return path, stdout, stderr


def write_event_run(root: Path) -> Path:
    root.mkdir(parents=True)
    events: list[dict] = []
    events.append(storage.make_event(events, "task_fixture", "ccis.run.initialized", {"state": "CREATED"}))
    events.append(storage.make_event(events, "task_fixture", "ccis.transition.committed", {"to_state": "SNAPSHOTTED"}))
    path = root / "events.jsonl"
    path.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events), encoding="utf-8")
    storage.verify_events(storage.read_events(root))
    return path


def execute(task: dict) -> dict:
    return task_registry.execute_typed_task(task, {})["output"]


class EvidenceIntegrityContractTests(unittest.TestCase):
    def test_registry_implements_a_strict_read_only_task_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, _, _ = write_benchmark_run(Path(temporary) / "benchmark")
            entry = task_registry.resolve("debug.evidence_integrity", 1)
            self.assertEqual("implemented", entry["status"])
            self.assertEqual("ccis.debug.evidence_integrity", entry["native_handler"])
            self.assertEqual([], entry["allowed_resources"])

            task = task_registry.adapt_evidence_integrity(
                manifest, "benchmark-run", evidence_bytes=100_000,
                expected_digest=storage.file_digest(manifest), task_id="integrity-contract"
            )
            self.assertEqual([], task["inputs"])
            self.assertEqual([], task["resource_claims"])
            self.assertEqual(["evidence.inspect"], task["authority"]["capabilities"])
            self.assertFalse(task["authority"]["canonical_write"])

            extra_input = copy.deepcopy(task)
            extra_input["inputs"] = [{"name": "extra", "kind": "file", "ref": "x", "digest": None}]
            with self.assertRaisesRegex(storage.CCISError, "only one run/bundle"):
                task_registry.admit_task(extra_input)

            mutable = copy.deepcopy(task)
            mutable["authority"]["canonical_write"] = True
            with self.assertRaisesRegex(storage.CCISError, "cannot write"):
                task_registry.admit_task(mutable)

            process_budget = copy.deepcopy(task)
            process_budget["budget"]["max_memory_mb"] = 128
            with self.assertRaisesRegex(storage.CCISError, "only bounded wall-time"):
                task_registry.admit_task(process_budget)

            with self.assertRaisesRegex(storage.CCISError, "must name run.json"):
                task_registry.adapt_evidence_integrity(
                    manifest.with_name("not-a-run.json"), "benchmark-run", evidence_bytes=100_000,
                    expected_digest=storage.file_digest(manifest),
                )

            with self.assertRaisesRegex(storage.CCISError, "trusted expected"):
                task_registry.adapt_evidence_integrity(
                    manifest, "benchmark-run", evidence_bytes=100_000
                )

    def test_allocation_output_must_not_overlap_the_inspected_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, _, _ = write_benchmark_run(root / "benchmark")
            with self.assertRaisesRegex(storage.CCISError, "cannot overlap"):
                allocation_lease.run_evidence_integrity_task(
                    root / "benchmark" / "allocation", manifest, "benchmark-run",
                    evidence_bytes=100_000, expected_digest=storage.file_digest(manifest),
                )


class EvidenceIntegrityExecutionTests(unittest.TestCase):
    def test_clean_bundle_is_read_only_queueable_rebuildable_and_replay_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root)
            manifest = write_bundle(repo / "evidence")
            command(repo, "add", "evidence")
            command(repo, "commit", "-m", "evidence fixture")
            before_tree = tree_digest(repo / "evidence")
            before_index = storage.index_tree(repo)
            before_worktree = storage.tracked_worktree_snapshot(repo)

            result = allocation_lease.run_evidence_integrity_task(
                root / "allocation-a", manifest, "ccis-evidence-bundle",
                evidence_bytes=1_000_000, expected_digest=storage.file_digest(manifest),
                task_id="integrity-clean-a",
            )
            diagnostic = result["output"]["diagnostic"]
            self.assertEqual("SUCCEEDED", result["status"])
            self.assertEqual("CLEAN", diagnostic["disposition"])
            self.assertTrue(diagnostic["read_only"])
            self.assertEqual(before_tree, tree_digest(repo / "evidence"))
            self.assertEqual(before_index, storage.index_tree(repo))
            self.assertEqual(before_worktree, storage.tracked_worktree_snapshot(repo))

            original_snapshot = allocation_heap.snapshot_path(root / "allocation-a").read_bytes()
            allocation_heap.snapshot_path(root / "allocation-a").unlink()
            rebuilt = allocation_lease.Allocator(root / "allocation-a").status()
            self.assertEqual("REBUILT_MISSING_CACHE", rebuilt["cache_action"])
            self.assertEqual(original_snapshot, allocation_heap.snapshot_path(root / "allocation-a").read_bytes())

            replay = allocation_lease.run_evidence_integrity_task(
                root / "allocation-b", manifest, "ccis-evidence-bundle",
                evidence_bytes=1_000_000, expected_digest=storage.file_digest(manifest),
                task_id="integrity-clean-b",
            )
            self.assertEqual(result["output"]["diagnostic_digest"], replay["output"]["diagnostic_digest"])
            self.assertEqual(result["output"], replay["output"])
            self.assertEqual(before_tree, tree_digest(repo / "evidence"))

    def test_bundle_artifact_and_manifest_tamper_have_distinct_localized_dispositions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_manifest = write_bundle(root / "artifact")
            artifact_task = task_registry.adapt_evidence_integrity(
                artifact_manifest, "ccis-evidence-bundle", evidence_bytes=1_000_000,
                expected_digest=storage.file_digest(artifact_manifest),
                task_id="integrity-artifact",
            )
            evaluation = artifact_manifest.parent / "evaluation.json"
            evaluation.write_text("{}\n", encoding="utf-8")
            artifact = execute(artifact_task)["diagnostic"]
            self.assertEqual("ARTIFACT_TAMPERED", artifact["disposition"])
            self.assertEqual("evaluation.json", artifact["first_bad_artifact"])
            self.assertNotEqual(artifact["expected_digest"], artifact["actual_digest"])
            self.assertEqual(str(artifact_manifest.resolve()), artifact["declaring_manifest"])
            self.assertEqual("decision:transition_fixture", artifact["affected_decision_or_event"])

            manifest_path = write_bundle(root / "manifest")
            manifest_task = task_registry.adapt_evidence_integrity(
                manifest_path, "ccis-evidence-bundle", evidence_bytes=1_000_000,
                expected_digest=storage.file_digest(manifest_path),
                task_id="integrity-manifest",
            )
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
            value["bundle_id"] = "bundle_tampered"
            storage.atomic_json(manifest_path, value)
            manifest = execute(manifest_task)["diagnostic"]
            self.assertEqual("MANIFEST_TAMPERED", manifest["disposition"])
            self.assertEqual("evidence-bundle.json", manifest["first_bad_artifact"])
            self.assertNotEqual(manifest["expected_digest"], manifest["actual_digest"])

    def test_event_tamper_localizes_the_first_affected_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            event_path = write_event_run(root)
            task = task_registry.adapt_evidence_integrity(
                root, "ccis-run", evidence_bytes=100_000,
                expected_digest=storage.file_digest(event_path), task_id="integrity-events"
            )
            lines = event_path.read_text(encoding="utf-8").splitlines()
            event = json.loads(lines[1])
            event["payload"]["to_state"] = "ACCEPTED"
            lines[1] = json.dumps(event, sort_keys=True)
            event_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            diagnostic = execute(task)["diagnostic"]
            self.assertEqual("EVENT_TAMPERED", diagnostic["disposition"])
            self.assertEqual("events.jsonl#2", diagnostic["first_bad_artifact"])
            self.assertEqual(f"event:{event['event_id']}", diagnostic["affected_decision_or_event"])
            self.assertNotEqual(diagnostic["expected_digest"], diagnostic["actual_digest"])

    def test_representative_moe_benchmark_fixture_is_inspected_without_launching_a_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "benchmark"
            manifest, stdout, _ = write_benchmark_run(root)
            task = task_registry.adapt_evidence_integrity(
                manifest, "benchmark-run", evidence_bytes=1_000_000,
                expected_digest=storage.file_digest(manifest),
                task_id="integrity-moe-live-fixture",
            )
            clean = execute(task)
            self.assertEqual("CLEAN", clean["diagnostic"]["disposition"])
            self.assertEqual("benchmark-run:run-live-inference-fixture", clean["diagnostic"]["affected_decision_or_event"])

            stdout.write_text('{"avg_ts": 999.0}\n', encoding="utf-8")
            tampered = execute(task)["diagnostic"]
            self.assertEqual("ARTIFACT_TAMPERED", tampered["disposition"])
            self.assertEqual(str(stdout.resolve()), tampered["first_bad_artifact"])
            self.assertEqual(
                "benchmark-run:run-live-inference-fixture/bench:fixture",
                tampered["affected_decision_or_event"],
            )
            self.assertEqual(
                storage.digest(clean["diagnostic"]), clean["diagnostic_digest"],
                "the stable debug digest covers only canonical diagnostic data",
            )

    def test_manifest_tamper_and_budget_exhaustion_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, _, _ = write_benchmark_run(root / "manifest")
            task = task_registry.adapt_evidence_integrity(
                manifest, "benchmark-run", evidence_bytes=1_000_000,
                expected_digest=storage.file_digest(manifest),
                task_id="integrity-benchmark-manifest",
            )
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["results"][0]["benchmark_rows"][0]["avg_ts"] = 1_000_000.0
            storage.atomic_json(manifest, value)
            diagnostic = execute(task)["diagnostic"]
            self.assertEqual("MANIFEST_TAMPERED", diagnostic["disposition"])
            self.assertEqual("run.json", diagnostic["first_bad_artifact"])

            limited_manifest, _, _ = write_benchmark_run(root / "limited")
            limited = task_registry.adapt_evidence_integrity(
                limited_manifest, "benchmark-run", evidence_bytes=1,
                expected_digest=storage.file_digest(limited_manifest),
                task_id="integrity-budget",
            )
            blocked = task_registry.execute_typed_task(limited, {})
            self.assertEqual("BLOCKED", blocked["status"])
            self.assertEqual("BUDGET_EXCEEDED", blocked["output"]["diagnostic"]["disposition"])


if __name__ == "__main__":
    unittest.main()
