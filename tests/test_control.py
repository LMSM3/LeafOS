from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import os

ROOT = Path(__file__).resolve().parents[1]
os.sys.path.insert(0, str(ROOT))

from core.cli import _normalize_global_options, build_parser
from core.config import Settings
from core.control.service import ControlService, discover_project, render_context_packet
from core.control.store import ControlError, ProjectStore, _identity_key
from core.runtime.llama import _extract_response


class ProjectStoreTests(unittest.TestCase):
    def test_windows_and_wsl_paths_share_a_project_identity_key(self) -> None:
        self.assertEqual(_identity_key(r"C:\FlowerOS\L"), _identity_key("/mnt/c/FlowerOS/L"))

    def test_project_state_is_integrity_checked_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            store = ProjectStore(project)
            first = store.initialize("Prove one vertical slice")
            second = store.initialize("Prove one vertical slice")
            self.assertEqual(first["integrity"], second["integrity"])
            objective = json.loads(store.objective_path.read_text(encoding="utf-8"))
            objective["text"] = "silently changed"
            store.objective_path.write_text(json.dumps(objective), encoding="utf-8")
            with self.assertRaisesRegex(ControlError, "integrity"):
                store.load_objective()

    def test_different_objective_cannot_replace_a_live_graph(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory))
            store.initialize("First objective")
            store.create_task("Inspect current evidence", "fast")
            with self.assertRaisesRegex(ControlError, "cannot replace"):
                store.initialize("Second objective", replace=True)

    def test_dependencies_must_exist_and_block_until_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory))
            store.initialize("Dependency test")
            first = store.create_task("First", "fast")
            second = store.create_task("Second", "reasoning", dependencies=[first["id"]])
            self.assertEqual(first["status"], "ready")
            self.assertEqual(second["status"], "planned")
            with self.assertRaisesRegex(ControlError, "do not exist"):
                store.create_task("Bad dependency", "fast", dependencies=["task-999999"])

    def test_abandoned_single_worker_lease_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory))
            store.initialize("Recovery test")
            task = store.create_task("Recover me", "fast", attempts=2)
            store.claim_task(task["id"])
            with patch("core.control.store._pid_alive", return_value=False):
                recovered = store.recover()
            self.assertEqual(recovered, [task["id"]])
            self.assertEqual(store.get_task(task["id"])["status"], "ready")

    def test_project_sources_are_hashed_and_revalidated_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            source = project / "notes.md"
            source.write_text("repository fact\n", encoding="utf-8")
            store = ProjectStore(project)
            store.initialize("Source boundary")
            task = store.create_task("Read the supplied source", "fast", input_paths=["notes.md"])
            record = task["inputs"]["sources"][0]
            self.assertEqual(record["path"], "notes.md")
            self.assertEqual(record["bytes"], len(source.read_bytes()))
            self.assertEqual(store.source_contents(task)[0]["content"], source.read_bytes().decode("utf-8"))
            source.write_text("changed fact\n", encoding="utf-8")
            with self.assertRaisesRegex(ControlError, "changed after submission"):
                store.source_contents(task)

    def test_project_sources_cannot_escape_or_read_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            project = parent / "project"
            project.mkdir()
            outside = parent / "outside.md"
            outside.write_text("outside\n", encoding="utf-8")
            store = ProjectStore(project)
            store.initialize("Source boundary")
            (store.leaf_dir / "secret.txt").write_text("runtime\n", encoding="utf-8")
            with self.assertRaisesRegex(ControlError, "escapes the project"):
                store.create_task("Escape", "fast", input_paths=[str(outside)])
            with self.assertRaisesRegex(ControlError, "runtime state"):
                store.create_task("Runtime state", "fast", input_paths=[".leaf/secret.txt"])

    def test_project_sources_reject_binary_and_context_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            binary = project / "binary.dat"
            binary.write_bytes(b"text\x00binary")
            large = project / "large.md"
            large.write_text("x" * 4096, encoding="utf-8")
            store = ProjectStore(project)
            store.initialize("Source boundary")
            with self.assertRaisesRegex(ControlError, "not text"):
                store.create_task("Binary", "fast", input_paths=["binary.dat"])
            with self.assertRaisesRegex(ControlError, "context policy"):
                store.create_task(
                    "Too large for context",
                    "fast",
                    input_paths=["large.md"],
                    tokens=16,
                    context=512,
                )


class ControlServiceTests(unittest.TestCase):
    def test_single_worker_vertical_slice_records_unverified_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "leafos"
            project = Path(directory) / "project"
            root.mkdir()
            project.mkdir()
            (project / "notes.md").write_text("The repository marker is SOURCE_OK.\n", encoding="utf-8")
            settings = Settings(root, (root / "models",), "not-invoked", 4096, None)
            service = ControlService(settings, project)
            pack = {"id": "stubbed-control-pack", "lanes": {"fast": "stubbed-model"}}
            model = {
                "id": "stubbed-model",
                "path": "executor-is-stubbed",
                "architecture": "test-only",
                "quant": "test-only",
            }
            fake_result = {
                "return_code": 0,
                "stdout": "bounded worker result\n",
                "stderr": "",
                "started_at": "2026-08-19T00:00:00+00:00",
                "finished_at": "2026-08-19T00:00:01+00:00",
            }
            with (
                patch.object(service, "_active_pack", return_value=(pack, {"models": []})),
                patch("core.control.service.route_lane", return_value=model),
                patch("core.control.service.run_model_capture", return_value=fake_result) as run_capture,
            ):
                plan = service.plan("Run one bounded local worker")
                self.assertEqual(plan["mode"], "recovery-swarm")
                self.assertEqual(plan["epoch_interval_minutes"], 30)
                task = service.submit(
                    "Return bounded evidence",
                    "fast",
                    input_paths=["notes.md"],
                    tokens=16,
                    context=512,
                )
            worker_prompt = run_capture.call_args.args[2]
            self.assertIn("SOURCE notes.md sha256:", worker_prompt)
            self.assertIn("SOURCE_OK", worker_prompt)
            self.assertEqual(task["status"], "verifying")
            self.assertEqual(task["confidence"], "unverified")
            self.assertEqual(len(task["evidence"]), 1)
            output = project / task["output"]["path"]
            self.assertEqual(output.read_text(encoding="utf-8"), fake_result["stdout"])
            packet = service.export_context()
            self.assertEqual(packet["active_tasks"][0]["id"], task["id"])
            self.assertEqual(packet["active_tasks"][0]["inputs"][0]["path"], "notes.md")
            self.assertEqual(packet["new_evidence"][0]["input_sources"][0]["path"], "notes.md")
            snapshot = project / packet["new_evidence"][0]["input_sources"][0]["snapshot"]
            self.assertEqual(snapshot.read_bytes(), (project / "notes.md").read_bytes())
            self.assertIn("unaccepted", packet["unknown_or_conflicting"][0])
            self.assertIn("PROVENANCE", render_context_packet(packet))
            output.write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ControlError, "artifact integrity"):
                service.export_context()

    def test_plan_rejects_missing_active_pack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "leafos"
            project = Path(directory) / "project"
            root.mkdir()
            project.mkdir()
            settings = Settings(root, (root / "models",), "missing", 4096, None)
            with self.assertRaisesRegex(ControlError, "no active pack"):
                ControlService(settings, project).plan("Cannot invent a pack")


class ControlCliTests(unittest.TestCase):
    def test_global_project_and_json_options_work_after_subcommand(self) -> None:
        values = _normalize_global_options(
            ["task", "inspect", "task-000001", "--project", "C:/work", "--json"]
        )
        args = build_parser().parse_args(values)
        self.assertTrue(args.json)
        self.assertEqual(args.project, "C:/work")
        self.assertEqual(args.command, "task")
        self.assertEqual(args.task_command, "inspect")

    def test_task_submit_accepts_repeatable_project_inputs(self) -> None:
        args = build_parser().parse_args(
            ["task", "submit", "--goal", "Inspect", "--input", "README.md", "--input", "VERSION"]
        )
        self.assertEqual(args.input, ["README.md", "VERSION"])

    def test_project_discovery_prefers_leafos_identity_over_parent_git(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            (parent / ".git").mkdir()
            project = parent / "L"
            nested = project / "core" / "nested"
            nested.mkdir(parents=True)
            (project / "VERSION").write_text("0.2.4\n", encoding="utf-8")
            (project / "bin").mkdir()
            (project / "bin" / "leafctl").write_text("", encoding="utf-8")
            self.assertEqual(discover_project(nested), project.resolve())


class RuntimeCaptureTests(unittest.TestCase):
    def test_llama_cli_banner_and_timing_are_not_worker_output(self) -> None:
        prompt = "Reply with exactly OK and nothing else."
        raw = (
            "Loading model...\nmodel: real.gguf\navailable commands:\n\n"
            f"> {prompt}\nOK\n\n[ Prompt: 20 t/s | Generation: 10 t/s ]\n\nExiting...\n"
        )
        self.assertEqual(_extract_response(raw, prompt), "OK")

    def test_truncated_long_prompt_echo_is_not_worker_output(self) -> None:
        prompt = "source text " * 1000
        raw = (
            "Loading model...\nmodel: real.gguf\n\n"
            "> source text source text\nT ... (truncated)\n"
            "README.md establishes VERSION 0.2.4.\n\n"
            "[ Prompt: 20 t/s | Generation: 10 t/s ]\n\nExiting...\n"
        )
        self.assertEqual(_extract_response(raw, prompt), "README.md establishes VERSION 0.2.4.")


if __name__ == "__main__":
    unittest.main()
