from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
os.sys.path.insert(0, str(ROOT))

from core.config import Settings
from core.control.service import ControlService, _parse_verifier_response
from core.control.store import CURRENT_CONTROL_PHASE, ControlError, ProjectStore
from core.control.tools import MAX_TOOL_OUTPUT_BYTES, TOOL_ALLOWLIST, execute_tool


WORKER_MODEL = {
    "id": "worker-model",
    "path": "worker.gguf",
    "architecture": "test-worker",
    "quant": "Q4",
}
VERIFIER_MODEL = {
    "id": "independent-verifier-model",
    "path": "verifier.gguf",
    "architecture": "test-verifier",
    "quant": "Q4",
}


def worker_result(response: str = "Repository claim") -> dict[str, object]:
    return {
        "return_code": 0,
        "stdout": response,
        "stderr": "",
        "response": response,
        "started_at": "2026-08-19T00:00:00+00:00",
        "finished_at": "2026-08-19T00:00:01+00:00",
    }


def verifier_result(payload: dict[str, object]) -> dict[str, object]:
    response = json.dumps(payload)
    return {
        "return_code": 0,
        "stdout": response,
        "stderr": "",
        "response": response,
        "started_at": "2026-08-19T00:01:00+00:00",
        "finished_at": "2026-08-19T00:01:01+00:00",
    }


def seed_verifying_task(
    project: Path,
    *,
    source_backed: bool = True,
    tool_attempts: int = 3,
    verifier_attempts: int = 2,
) -> tuple[ProjectStore, dict[str, object]]:
    store = ProjectStore(project)
    store.initialize("Phase B test")
    inputs = []
    if source_backed:
        (project / "facts.md").write_text("VERSION is 0.2.4.\n", encoding="utf-8")
        inputs = ["facts.md"]
    task = store.create_task(
        "Verify the repository fact",
        "fast",
        input_paths=inputs,
        context=2048,
        tokens=32,
        tool_attempts=tool_attempts,
        verifier_attempts=verifier_attempts,
    )
    sources = store.source_contents(task)
    store.claim_task(task["id"])
    completed = store.finalize_execution(
        task["id"],
        worker_result(),
        lane="fast",
        model=WORKER_MODEL,
        input_sources=sources,
    )
    return store, completed


def accepting_payload(evidence_id: str) -> dict[str, object]:
    return {
        "verdict": "accept",
        "confidence": "high",
        "claims": [{"text": "VERSION is 0.2.4", "evidence_ids": [evidence_id]}],
        "contradictions": [],
    }


class ControlledToolTests(unittest.TestCase):
    def test_allowlist_executes_inspect_search_test_and_artifact_without_shell_input(self) -> None:
        self.assertEqual(TOOL_ALLOWLIST, {"artifact", "inspect", "search", "test"})
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "facts.md").write_text("LeafOS marker PHASE_B_OK\n", encoding="utf-8")
            (project / "sample_test.py").write_text(
                "import unittest\n"
                "class SampleTests(unittest.TestCase):\n"
                "    def test_ok(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            inspected = execute_tool(project, "inspect", path="facts.md")
            searched = execute_tool(project, "search", path=".", query="PHASE_B_OK")
            tested = execute_tool(project, "test", selector="sample_test.SampleTests.test_ok")
            captured = execute_tool(project, "artifact", path="facts.md")
            self.assertEqual([inspected["exit_code"], searched["exit_code"], tested["exit_code"], captured["exit_code"]], [0, 0, 0, 0])
            self.assertIn("PHASE_B_OK", searched["stdout"])
            self.assertEqual(captured["capture"]["sha256"], inspected_sha(project / "facts.md"))

    def test_path_escape_is_rejected_without_reading_outside_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            project = parent / "project"
            project.mkdir()
            (parent / "secret.txt").write_text("must not leak\n", encoding="utf-8")
            result = execute_tool(project, "inspect", path="../secret.txt")
            self.assertEqual(result["exit_code"], 2)
            self.assertIn("escapes the project", result["stderr"])
            self.assertNotIn("must not leak", result["stdout"] + result["stderr"])

    def test_artifact_capture_is_snapshotted_and_integrity_audited(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            store, task = seed_verifying_task(project)
            result = execute_tool(project, "artifact", path="facts.md")
            store.record_tool_execution(task["id"], result)
            evidence = store.evidence_records(task["id"])[-1]
            captured = next(item for item in evidence["artifacts"] if item["role"] == "captured-artifact")
            self.assertEqual((project / captured["path"]).read_bytes(), (project / "facts.md").read_bytes())
            self.assertEqual(store.audit()["evidence"], 2)

    def test_test_output_is_bounded_and_marks_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "loud_test.py").write_text(
                "import unittest\n"
                "class LoudTests(unittest.TestCase):\n"
                "    def test_loud(self):\n"
                f"        print('x' * {MAX_TOOL_OUTPUT_BYTES + 4096})\n",
                encoding="utf-8",
            )
            result = execute_tool(project, "test", selector="loud_test.LoudTests.test_loud")
            self.assertEqual(result["exit_code"], 0)
            self.assertTrue(result["output_truncated"])
            self.assertLessEqual(len(result["stdout"].encode("utf-8")), MAX_TOOL_OUTPUT_BYTES)
            self.assertTrue(result["next_action"])

    def test_failed_tool_retains_outputs_attempt_next_action_and_enforces_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            store, task = seed_verifying_task(project, tool_attempts=1)
            failed = execute_tool(project, "search", path="facts.md", query="ABSENT_MARKER")
            updated = store.record_tool_execution(task["id"], failed)
            evidence = store.evidence_records(task["id"])[-1]
            self.assertEqual(evidence["exit_code"], 1)
            self.assertEqual(evidence["attempt"], 1)
            self.assertTrue(evidence["next_action"])
            roles = {artifact["role"] for artifact in evidence["artifacts"]}
            self.assertEqual(roles, {"tool-stdout", "tool-stderr"})
            stderr = project / next(item["path"] for item in evidence["artifacts"] if item["role"] == "tool-stderr")
            self.assertEqual(stderr.read_text(encoding="utf-8"), "no matches\n")
            self.assertEqual(updated["status"], "verifying")
            with self.assertRaisesRegex(ControlError, "budget exhausted"):
                store.record_tool_execution(task["id"], failed)


class VerificationGateTests(unittest.TestCase):
    def test_phase_transition_is_one_way_and_journaled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory))
            objective = store.initialize("Phase transition")
            self.assertEqual(objective["phase"], CURRENT_CONTROL_PHASE)
            self.assertEqual(store.advance_phase(CURRENT_CONTROL_PHASE)["revision"], objective["revision"])
            with self.assertRaisesRegex(ControlError, "cannot move backward"):
                store.advance_phase("1.0.0-phase-a")

    def test_worker_cannot_verify_or_accept_its_own_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, task = seed_verifying_task(Path(directory))
            with self.assertRaisesRegex(ControlError, "independent"):
                store.record_verification(
                    task["id"],
                    verifier_result(accepting_payload(task["evidence"][0])),
                    accepting_payload(task["evidence"][0]),
                    lane="fast",
                    model=WORKER_MODEL,
                )
            with self.assertRaisesRegex(ControlError, "lacks an independent"):
                store.accept_task(task["id"], "worker prose is not authority")

    def test_acceptance_requires_independent_evidence_resolved_claims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, task = seed_verifying_task(Path(directory))
            payload = accepting_payload(task["evidence"][0])
            store.record_verification(
                task["id"],
                verifier_result(payload),
                payload,
                lane="reasoning",
                model=VERIFIER_MODEL,
            )
            accepted = store.accept_task(task["id"], "independent source-backed verification passed")
            self.assertEqual(accepted["status"], "accepted")
            self.assertEqual(accepted["confidence"], "verified")
            self.assertRegex(accepted["decision"], r"^decision-[0-9]{6}$")
            self.assertEqual(store.audit()["decisions"], 1)

        with tempfile.TemporaryDirectory() as directory:
            store, task = seed_verifying_task(Path(directory), source_backed=False)
            payload = accepting_payload(task["evidence"][0])
            store.record_verification(
                task["id"],
                verifier_result(payload),
                payload,
                lane="reasoning",
                model=VERIFIER_MODEL,
            )
            with self.assertRaisesRegex(ControlError, "evidence-resolved"):
                store.accept_task(task["id"], "unsupported model output must not pass")

    def test_conflicting_verifiers_remain_visible_and_block_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, task = seed_verifying_task(Path(directory), verifier_attempts=2)
            accept = accepting_payload(task["evidence"][0])
            reject = {
                "verdict": "reject",
                "confidence": "high",
                "claims": [{"text": "The worker conclusion is not established", "evidence_ids": [task["evidence"][0]]}],
                "contradictions": ["Verifier conclusions disagree"],
            }
            store.record_verification(task["id"], verifier_result(accept), accept, lane="reasoning", model=VERIFIER_MODEL)
            conflicted = store.record_verification(
                task["id"], verifier_result(reject), reject, lane="reasoning", model={**VERIFIER_MODEL, "id": "second-verifier"}
            )
            self.assertEqual(conflicted["confidence"], "conflicted")
            self.assertEqual(len(conflicted["contradictions"]), 1)
            packet = store.export_context()
            self.assertIn("Conflicting verifier records", " ".join(packet["unknown_or_conflicting"]))
            with self.assertRaisesRegex(ControlError, "unresolved verifier contradictions"):
                store.accept_task(task["id"], "conflict cannot auto-accept")

    def test_primary_agent_can_dispute_a_semantically_wrong_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, task = seed_verifying_task(Path(directory))
            payload = accepting_payload(task["evidence"][0])
            verified = store.record_verification(
                task["id"], verifier_result(payload), payload, lane="reasoning", model=VERIFIER_MODEL
            )
            disputed = store.dispute_task(
                task["id"],
                [verified["verifier_evidence"][0]],
                "the verifier's semantic conclusion conflicts with direct source inspection",
            )
            self.assertEqual(disputed["confidence"], "conflicted")
            self.assertEqual(disputed["contradictions"][0]["producer"], "leafos:primary-agent")
            with self.assertRaisesRegex(ControlError, "unresolved verifier contradictions"):
                store.accept_task(task["id"], "disputed evidence cannot pass")

    def test_verifier_parser_and_service_preserve_controller_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "leafos"
            project = Path(directory) / "project"
            root.mkdir()
            project.mkdir()
            store, task = seed_verifying_task(project)
            settings = Settings(root, (root / "models",), "not-invoked", 4096, None)
            service = ControlService(settings, project)
            payload = accepting_payload(task["evidence"][0])
            response = f"prefix ignored\n{json.dumps(payload)}\nsuffix ignored"
            parsed = _parse_verifier_response(response)
            self.assertEqual(parsed["verdict"], "accept")
            partial = _parse_verifier_response(
                '{"verdict":"accept","claims":[{"text":"nested","evidence_ids":[]}]'
            )
            self.assertEqual(partial["verdict"], "invalid")
            self.assertTrue(partial["parse_error"])
            pack = {"id": "phase-b-pack", "lanes": {"reasoning": VERIFIER_MODEL["id"]}}
            with (
                patch.object(service, "_active_pack", return_value=(pack, {"models": []})),
                patch("core.control.service.route_lane", return_value=VERIFIER_MODEL),
                patch(
                    "core.control.service.run_model_capture",
                    return_value=verifier_result(payload),
                ),
            ):
                result = service.verify(task["id"], tokens=64, context=4096)
            self.assertEqual(result["evidence"]["kind"], "verification")
            self.assertEqual(result["evidence"]["verdict"], "accept")
            self.assertEqual(result["task"]["status"], "verifying")


def inspected_sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
