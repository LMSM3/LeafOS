from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.sys.path.insert(0, str(ROOT))

from core.cli import build_parser
from core.control.context import render_context_packet
from core.control.epochs import CONTEXT_SCHEMA, DEFAULT_EPOCH_MINUTES, EpochManager
from core.control.store import CURRENT_CONTROL_PHASE, ControlError, ProjectStore


WORKER_MODEL = {
    "id": "epoch-worker-model",
    "path": "worker.gguf",
    "architecture": "test-worker",
    "quant": "Q4",
}
VERIFIER_MODEL = {
    "id": "epoch-verifier-model",
    "path": "verifier.gguf",
    "architecture": "test-verifier",
    "quant": "Q4",
}


def result(response: str) -> dict[str, object]:
    return {
        "return_code": 0,
        "stdout": response,
        "stderr": "",
        "response": response,
        "started_at": "2026-08-20T00:00:00+00:00",
        "finished_at": "2026-08-20T00:00:01+00:00",
    }


def add_verifying_task(store: ProjectStore, response: str, *, goal: str = "Establish the seeded fact") -> dict[str, object]:
    task = store.create_task(goal, "fast", input_paths=["facts.md"], context=65536, tokens=32)
    sources = store.source_contents(task)
    store.claim_task(task["id"])
    return store.finalize_execution(
        task["id"], result(response), lane="fast", model=WORKER_MODEL, input_sources=sources
    )


def verify_task(store: ProjectStore, task: dict[str, object], verdict: str = "accept") -> dict[str, object]:
    evidence_id = str(task["evidence"][0])
    payload = {
        "verdict": verdict,
        "confidence": "high",
        "claims": [{"text": f"Verifier returned {verdict}", "evidence_ids": [evidence_id]}],
        "contradictions": [] if verdict == "accept" else ["Independent verifier rejected the claim"],
    }
    return store.record_verification(
        str(task["id"]), result(json.dumps(payload)), payload,
        lane="reasoning", model=VERIFIER_MODEL,
    )


def initialized_project(root: Path) -> tuple[ProjectStore, EpochManager]:
    (root / "facts.md").write_text("The deterministic seed value is 17.\n", encoding="utf-8")
    store = ProjectStore(root)
    objective = store.initialize("Build a stable evidence-backed result from the seed")
    manager = EpochManager(store)
    manager.initialize()
    assert objective["phase"] == CURRENT_CONTROL_PHASE
    return store, manager


class EpochClockAndImmutabilityTests(unittest.TestCase):
    def test_default_clock_configuration_and_early_review_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, manager = initialized_project(Path(directory))
            self.assertEqual(DEFAULT_EPOCH_MINUTES, manager.status()["interval_minutes"])
            self.assertEqual(7, manager.configure(7)["interval_minutes"])
            add_verifying_task(store, "seed is 17")
            first = manager.review(manual=True)
            self.assertEqual("epoch-000001", first["manifest"]["id"])
            with self.assertRaisesRegex(ControlError, "not due"):
                manager.review()
            second = manager.review(manual=True)
            self.assertEqual("epoch-000002", second["manifest"]["id"])

    def test_epoch_documents_are_immutable_and_tamper_evident(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, manager = initialized_project(root)
            add_verifying_task(store, "seed is 17")
            reviewed = manager.review(manual=True)
            epoch_id = reviewed["manifest"]["id"]
            self.assertEqual(epoch_id, manager.verify_epoch(epoch_id)["id"])
            context_text = root / ".leaf" / "epochs" / epoch_id / "context.txt"
            context_text.write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ControlError, "integrity"):
                manager.verify_epoch(epoch_id)

    def test_cli_has_one_obvious_epoch_surface(self) -> None:
        parser = build_parser()
        status = parser.parse_args(["epoch", "status"])
        configure = parser.parse_args(["epoch", "configure", "--minutes", "15"])
        review = parser.parse_args(["epoch", "review", "--manual"])
        self.assertEqual((status.command, status.epoch_command), ("epoch", "status"))
        self.assertEqual(configure.minutes, 15)
        self.assertTrue(review.manual)


class EpochReductionTests(unittest.TestCase):
    def test_duplicate_content_occurs_once_while_all_evidence_ids_survive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, manager = initialized_project(root)
            shared = "the same normalized worker conclusion"
            first = add_verifying_task(store, shared, goal="first task")
            second = add_verifying_task(store, shared, goal="second task")
            manager.review(manual=True)
            index = store._read_document(
                root / ".leaf" / "epochs" / "epoch-000001" / "evidence-index.json",
                "leafos.epoch-evidence-index.v1",
            )
            matches = [value for value in index["entries"] if value["text"] == shared]
            self.assertEqual(1, len(matches))
            self.assertGreaterEqual(matches[0]["occurrences"], 2)
            self.assertEqual(
                {str(first["evidence"][0]), str(second["evidence"][0])},
                set(matches[0]["evidence_ids"]),
            )

    def test_large_raw_epoch_meets_twenty_percent_gate_and_retains_acceptance_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, manager = initialized_project(root)
            large = ("matrix-return-evidence 0.125 -0.031 0.008\n" * 2300).strip()
            task = add_verifying_task(store, large)
            verify_task(store, task)
            accepted = store.accept_task(str(task["id"]), "independent source-backed verification passed")
            reviewed = manager.review(manual=True)
            context = reviewed["context"]
            accounting = context["accounting"]
            self.assertEqual(CONTEXT_SCHEMA, context["schema"])
            self.assertLessEqual(accounting["packet_bytes"], accounting["allowed_packet_bytes"])
            self.assertLessEqual(accounting["packet_to_raw_ratio"], 0.20)
            acceptance = next(value for value in context["last_decisions"] if value["id"] == accepted["decision"])
            self.assertTrue(acceptance["evidence_ids"])

    def test_evidence_floor_is_explicit_for_small_epochs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, manager = initialized_project(root)
            add_verifying_task(store, "short")
            accounting = manager.review(manual=True)["context"]["accounting"]
            self.assertEqual("evidence-floor", accounting["limit_basis"])
            self.assertLessEqual(accounting["packet_bytes"], accounting["allowed_packet_bytes"])

    def test_contradictions_are_detected_before_context_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, manager = initialized_project(root)
            task = add_verifying_task(store, "seed is 17")
            verify_task(store, task, "accept")
            verify_task(store, task, "reject")
            reviewed = manager.review(manual=True)
            index = store._read_document(
                root / ".leaf" / "epochs" / "epoch-000001" / "evidence-index.json",
                "leafos.epoch-evidence-index.v1",
            )
            self.assertTrue(index["contradictions"])
            self.assertTrue(reviewed["context"]["unknown_or_conflicting"])
            self.assertTrue(reviewed["next_plan"]["blocked_by_contradictions"])


class EpochHandoffTests(unittest.TestCase):
    def test_fresh_supervisor_reconstructs_objective_and_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, manager = initialized_project(root)
            task = add_verifying_task(store, "seed is 17")
            expected = manager.review(manual=True)["context"]
            fresh = EpochManager(ProjectStore(root)).export_context()
            self.assertEqual(expected["objective"], fresh["objective"])
            self.assertEqual(expected["next_recommended_actions"], fresh["next_recommended_actions"])
            self.assertEqual(expected["integrity"], fresh["integrity"])
            text = render_context_packet(fresh)
            for section in (
                "OBJECTIVE", "CURRENT STATE", "LAST DECISIONS", "ACTIVE TASKS", "NEW EVIDENCE",
                "UNRESOLVED FAILURES", "UNKNOWN / CONFLICTING", "NEXT RECOMMENDED ACTIONS", "PROVENANCE",
            ):
                self.assertIn(section, text)
            self.assertEqual("verifying", next(value for value in fresh["active_tasks"] if value["id"] == task["id"])["status"])


if __name__ == "__main__":
    unittest.main()
