from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ccis.kernel import acceptance_policy, evidence_gate, storage, transition_gate, validator_runner
from loop import scientific_change_loop as change_loop


REPO_ROOT = Path(__file__).resolve().parents[2]
LEAFCTL = REPO_ROOT / "ProjectLeaf" / "leafos_taskpack" / "bin" / "leafctl"


def shell_path(path: Path) -> str:
    value = path.resolve().as_posix()
    if os.name == "nt" and len(value) > 2 and value[1] == ":":
        return f"/{value[0].lower()}{value[2:]}"
    return value


def command(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def make_repo(root: Path) -> Path:
    repo = root / "repository"
    repo.mkdir()
    command(repo, "init")
    command(repo, "config", "user.email", "ccis@example.invalid")
    command(repo, "config", "user.name", "CCIS Test")
    (repo / "baseline.txt").write_text("original\n", encoding="utf-8")
    command(repo, "add", "baseline.txt")
    command(repo, "commit", "-m", "baseline")
    return repo


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def envelope(repo: Path, task_id: str, allowed_path: str) -> dict:
    return {
        "ccis_object": "ccis.task_envelope",
        "schema_version": 1,
        "task_id": task_id,
        "instruction": "Exercise one real repository through the CCIS gate.",
        "target": str(repo),
        "mode": "once",
        "created_at": "2026-08-03T08:00:00Z",
        "objective": {
            "summary": "Exercise one real repository through the CCIS gate.",
            "invariants": ["The working tree is never changed automatically."],
            "tolerances": [{"name": "failures", "operator": "eq", "threshold": 0, "unit": "count"}],
            "stopping_conditions": ["A constitutional outcome is recorded."],
        },
        "scope": {
            "repository": str(repo),
            "base_revision": command(repo, "rev-parse", "HEAD"),
            "allowed_paths": [allowed_path],
            "denied_paths": [".git/**"],
        },
        "budget": {
            "wall_seconds": 300,
            "wall_time_seconds": 300,
            "candidate_limit": 2,
            "revision_limit": 1,
            "max_iterations": 2,
            "max_changed_files": 2,
            "compute_units": None,
        },
        "validators": [{
            "validator_id": "contract_tests", "kind": "command", "required": True,
            "command": ["python", "-m", "unittest"], "timeout_seconds": 120,
        }],
        "authority": {
            "requester": "test.operator",
            "decision_actor": "leafos.ccis.transition_gate",
            "acceptance_mode": "explicit_operator",
            "automatic_working_tree_merge": False,
            "may_modify": True,
            "may_install": False,
            "may_merge": False,
            "capabilities": ["inspect", "propose", "evaluate", "stage", "accept", "rollback"],
        },
    }


def patch_for(path: str, content: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{path}\n"
        "@@ -0,0 +1 @@\n"
        f"+{content}\n"
    )


def changes(path: str, content: str) -> list[dict]:
    after = "sha256:" + hashlib.sha256((content + "\n").encode()).hexdigest()
    return [{
        "path": path,
        "operation": "add",
        "previous_path": None,
        "before_sha256": None,
        "after_sha256": after,
    }]


def questions(failing: bool = False) -> list[dict]:
    authority = [
        ("principles://ccis/bounded-change", "Is the proposed transition bounded?"),
        ("principles://ccis/evidence-before-acceptance", "Is there sufficient evidence?"),
        ("principles://ccis/continual-improvement", "Is the new state better, or at least defensibly safer?"),
        ("principles://ccis/legal-next-action", "What is the only legal next action?"),
    ]
    values = []
    for index in range(1, 5):
        result = "FAIL" if failing and index == 1 else "PASS"
        values.append({
            "question_id": f"constitutional.q{index}",
            "question_ref": authority[index - 1][0],
            "question": authority[index - 1][1],
            "result": result,
            "rationale": "Fixture answer from configured principle authority.",
            "evidence_refs": [f"evidence://fixture/q{index}.json"],
        })
    return values


def validators() -> list[dict]:
    return [{
        "validator_id": "contract_tests",
        "status": "PASSED",
        "required": True,
        "exit_code": 0,
        "summary": "Fixture validator passed.",
        "evidence_refs": ["evidence://fixture/validator.txt"],
    }]


class CCISMilestoneOneTests(unittest.TestCase):
    def test_scope_normalization_preserves_leading_dotfiles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = make_repo(Path(temporary))
            task = envelope(repo, "task_dotfile_fixture", ".gitignore")
            self.assertTrue(change_loop._path_allowed(".gitignore", task))
            self.assertTrue(change_loop._path_allowed("./.gitignore", task))
            self.assertFalse(change_loop._path_allowed(".git/config", task))

    def test_validator_runner_captures_real_evidence_and_refuses_authoritative_repo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root)
            task = envelope(repo, "task_validator_fixture", "science.txt")
            task["validators"] = [{
                "validator_id": "echo_validator",
                "kind": "command",
                "required": True,
                "command": [
                    sys.executable,
                    "-c",
                    "import sys; print('captured stdout'); print('captured stderr', file=sys.stderr)",
                ],
                "timeout_seconds": 10,
            }]
            task_path = root / "task.json"
            write_json(task_path, task)
            run_dir = change_loop.initialize(task_path, root / "runs")
            patch = root / "candidate.patch"
            patch.write_text(patch_for("science.txt", "validated"), encoding="utf-8", newline="\n")
            change_loop.register_candidate(
                run_dir, "candidate_validator_r0", patch, changes("science.txt", "validated")
            )

            with self.assertRaisesRegex(storage.CCISError, "authoritative repository"):
                validator_runner.run_validators(run_dir, repo)
            (repo / "nested").mkdir()
            with self.assertRaisesRegex(storage.CCISError, "authoritative repository"):
                validator_runner.run_validators(run_dir, repo / "nested")

            workspace = root / "isolated-workspace"
            workspace.mkdir()
            executed = validator_runner.run_validators(run_dir, workspace)
            self.assertEqual("VALIDATING", executed["state"]["state"])
            self.assertEqual("PASSED", executed["results"][0]["status"])
            self.assertIn("captured stdout", (run_dir / "validation" / "stdout.log").read_text())
            self.assertIn("captured stderr", (run_dir / "validation" / "stderr.log").read_text())

            evaluation = change_loop.evaluate_candidate(run_dir, questions(), executed["results"])
            self.assertEqual("ACCEPTED", evaluation["recommendation"])
            results_path = run_dir / "validation" / "validator-results.json"
            original_results = results_path.read_bytes()
            results_path.write_text("[]\n", encoding="utf-8")
            with self.assertRaisesRegex(storage.CCISError, "captured validator results"):
                change_loop.decide(run_dir, "ACCEPTED", "test.operator", ["Tampered evidence must fail."])
            results_path.write_bytes(original_results)
            decided = change_loop.decide(run_dir, "ACCEPTED", "test.operator", ["Executed evidence passed."])
            bundle_dir = Path(decided["evidence_bundle"]).parent
            self.assertIn("captured stdout", (bundle_dir / "stdout.log").read_text())
            self.assertIn("captured stderr", (bundle_dir / "stderr.log").read_text())
            self.assertIn("echo_validator", (bundle_dir / "commands.jsonl").read_text())

    def test_validator_failures_and_timeouts_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root)
            task = envelope(repo, "task_validator_failure", "science.txt")
            task["validators"] = [
                {
                    "validator_id": "failing_validator",
                    "kind": "command",
                    "required": True,
                    "command": [sys.executable, "-c", "import sys; print('failure', file=sys.stderr); sys.exit(3)"],
                    "timeout_seconds": 10,
                },
                {
                    "validator_id": "timeout_validator",
                    "kind": "command",
                    "required": True,
                    "command": [sys.executable, "-c", "import time; print('before timeout', flush=True); time.sleep(2)"],
                    "timeout_seconds": 1,
                },
            ]
            task_path = root / "task.json"
            write_json(task_path, task)
            run_dir = change_loop.initialize(task_path, root / "runs")
            patch = root / "candidate.patch"
            patch.write_text(patch_for("science.txt", "failed"), encoding="utf-8", newline="\n")
            change_loop.register_candidate(
                run_dir, "candidate_validator_failure_r0", patch, changes("science.txt", "failed")
            )
            workspace = root / "isolated-workspace"
            workspace.mkdir()
            executed = validator_runner.run_validators(run_dir, workspace)
            self.assertEqual(["FAILED", "ERROR"], [item["status"] for item in executed["results"]])
            self.assertEqual(3, executed["results"][0]["exit_code"])
            self.assertIsNone(executed["results"][1]["exit_code"])
            self.assertEqual(
                "REVISE",
                evidence_gate.recommendation({
                    "constitutional_questions": questions(),
                    "validator_results": [executed["results"][0]],
                }),
            )
            evaluation = change_loop.evaluate_candidate(run_dir, questions(), executed["results"])
            self.assertEqual("BLOCKED", evaluation["recommendation"])
            decided = change_loop.decide(run_dir, "BLOCKED", "test.operator", ["Timeout requires intervention."])
            self.assertEqual("BLOCKED", decided["state"]["state"])

    def test_illegal_transition_and_tampered_event_stream_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root)
            task_path = root / "task.json"
            write_json(task_path, envelope(repo, "task_tamper_fixture", "science.txt"))
            run_dir = change_loop.initialize(task_path, root / "runs")
            with self.assertRaises(storage.CCISError):
                transition_gate.advance(run_dir, "ACCEPTED", "bypass", outcome="ACCEPTED")

            event_path = run_dir / "events.jsonl"
            lines = event_path.read_text(encoding="utf-8").splitlines()
            event = json.loads(lines[0])
            event["payload"]["state"] = "ACCEPTED"
            lines[0] = json.dumps(event)
            event_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(storage.CCISError, "payload hash mismatch"):
                storage.resume(run_dir)

    def test_accepted_transition_resumes_and_requires_explicit_index_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root)
            task_path = root / "task.json"
            write_json(task_path, envelope(repo, "task_accept_fixture", "science.txt"))
            run_dir = change_loop.initialize(task_path, root / "runs")

            patch = root / "candidate.patch"
            patch.write_text(patch_for("science.txt", "accepted"), encoding="utf-8", newline="\n")
            change_loop.register_candidate(
                run_dir, "candidate_accept_r0", patch, changes("science.txt", "accepted")
            )
            self.assertFalse((repo / "science.txt").exists())

            # Simulate interruption by deleting disposable projections. Resume
            # must recover only from the authoritative event stream.
            (run_dir / "state.json").unlink()
            (run_dir / "checkpoint.json").unlink()
            self.assertEqual("CANDIDATE_SELECTED", storage.resume(run_dir)["state"])

            evaluation = change_loop.evaluate_candidate(run_dir, questions(), validators())
            self.assertEqual("ACCEPTED", evaluation["recommendation"])
            decided = change_loop.decide(run_dir, "ACCEPTED", "test.operator", ["All gates passed."])
            self.assertEqual("ACCEPTED", decided["state"]["state"])
            manifest = evidence_gate.verify_evidence_bundle(Path(decided["evidence_bundle"]))
            self.assertEqual(set(evidence_gate.REQUIRED_ARTIFACTS), set(manifest["artifacts"]))
            self.assertEqual(18, len(manifest["artifacts"]))

            with self.assertRaises(storage.CCISError):
                acceptance_policy.stage_accepted_candidate(run_dir, "test.operator", "wrong-task")
            self.assertEqual("", command(repo, "diff", "--cached", "--name-only"))

            bash_candidates = [
                Path(r"C:\msys64\usr\bin\bash.exe"),
                Path(r"C:\Program Files\Git\bin\bash.exe"),
            ] if os.name == "nt" else []
            bash = next((str(path) for path in bash_candidates if path.is_file()), shutil.which("bash"))
            self.assertTrue(bash, "bash is required to verify the leafos task accept route")
            invocation = " ".join([
                f"LEAFCTL_PYTHON={shlex.quote(shell_path(Path(sys.executable)))}",
                f"LEAFOS_CCIS_RUN_ROOT={shlex.quote(shell_path(root / 'runs'))}",
                shlex.quote(shell_path(LEAFCTL)),
                "task", "accept",
                "task_accept_fixture",
            ])
            accepted = subprocess.run(
                [bash, "-lc", invocation], capture_output=True, text=True, check=False, timeout=30
            )
            self.assertEqual(0, accepted.returncode, accepted.stderr)
            staged = json.loads(accepted.stdout)
            self.assertEqual("STAGED", staged["state"]["state"])
            self.assertEqual("science.txt", command(repo, "diff", "--cached", "--name-only"))
            self.assertFalse((repo / "science.txt").exists())
            self.assertFalse(staged["staging"]["working_tree_merged"])
            events = storage.read_events(run_dir)
            storage.verify_events(events)
            self.assertEqual(
                [
                    "SNAPSHOTTED",
                    "OBJECTIVE_DEFINED",
                    "INSPECTING",
                    "CANDIDATES_GENERATED",
                    "CANDIDATE_SELECTED",
                    "MUTATING",
                    "VALIDATING",
                    "GATED",
                    "ACCEPTED",
                    "STAGED",
                ],
                [
                    event["payload"]["to_state"]
                    for event in events
                    if event["event_type"] == "ccis.transition.committed"
                ],
            )

    def test_rejected_candidate_rolls_back_to_hash_verified_original_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root)
            task_path = root / "task.json"
            write_json(task_path, envelope(repo, "task_reject_fixture", "rejected.txt"))
            run_dir = change_loop.initialize(task_path, root / "runs")
            baseline = storage.tracked_worktree_snapshot(repo)

            patch = root / "candidate.patch"
            patch.write_text(patch_for("rejected.txt", "rejected"), encoding="utf-8", newline="\n")
            change_loop.register_candidate(
                run_dir, "candidate_reject_r0", patch, changes("rejected.txt", "rejected")
            )
            evaluation = change_loop.evaluate_candidate(
                run_dir, questions(failing=True), validators(), requested_failure="REJECTED"
            )
            self.assertEqual("REJECTED", evaluation["recommendation"])
            decided = change_loop.decide(run_dir, "REJECTED", "test.operator", ["Question one failed."])
            self.assertEqual("REJECTED", decided["state"]["state"])
            rolled_back = acceptance_policy.rollback_rejected_candidate(run_dir)
            self.assertEqual("ROLLED_BACK", rolled_back["state"]["state"])
            self.assertTrue(rolled_back["transition"]["rollback"]["verified"])
            self.assertEqual(baseline, storage.tracked_worktree_snapshot(repo))
            self.assertFalse((repo / "rejected.txt").exists())
            storage.verify_events(storage.read_events(run_dir))

    def test_acceptance_refuses_a_tampered_evidence_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root)
            task_path = root / "task.json"
            write_json(task_path, envelope(repo, "task_evidence_fixture", "science.txt"))
            run_dir = change_loop.initialize(task_path, root / "runs")
            patch = root / "candidate.patch"
            patch.write_text(patch_for("science.txt", "accepted"), encoding="utf-8", newline="\n")
            change_loop.register_candidate(
                run_dir, "candidate_evidence_r0", patch, changes("science.txt", "accepted")
            )
            change_loop.evaluate_candidate(run_dir, questions(), validators())
            decided = change_loop.decide(run_dir, "ACCEPTED", "test.operator", ["All gates passed."])
            evaluation_path = Path(decided["evidence_bundle"]).parent / "evaluation.json"
            evaluation_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(storage.CCISError, "artifact hash mismatch"):
                acceptance_policy.stage_accepted_candidate(
                    run_dir, "test.operator", "task_evidence_fixture"
                )
            self.assertEqual("", command(repo, "diff", "--cached", "--name-only"))


if __name__ == "__main__":
    unittest.main()
