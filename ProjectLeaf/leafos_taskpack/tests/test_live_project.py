from __future__ import annotations

import json
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.python import leaf_live_project as live

TUI = Path(__file__).resolve().parents[1] / "core" / "ui" / "tui"
if str(TUI) not in sys.path:
    sys.path.insert(0, str(TUI))
import project_wizard
import leaf_resident_supervisor as resident_supervisor


ROOT = Path(__file__).resolve().parents[1]


class LiveProjectTests(unittest.TestCase):
    def test_onboarding_schema_and_sample_match_runtime_contract(self) -> None:
        schema = json.loads((ROOT / "schemas" / "leafos.project-onboarding.v1.schema.json").read_text(encoding="utf-8"))
        preferences_schema = json.loads((ROOT / "schemas" / "leafos.stack-preferences.v1.schema.json").read_text(encoding="utf-8"))
        sample = json.loads((ROOT / "config" / "project-onboarding.sample.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            sample["workspace_root"] = temporary
            sample["project_name"] = "generic"
            sample["target"] = str(Path(temporary) / "generic")
            normalized = live.validate_onboarding_request(sample)
        self.assertEqual("LeafOS Project Onboarding Request", schema["title"])
        self.assertEqual("LeafOS Per-Run Stack Preferences", preferences_schema["title"])
        self.assertEqual("new", normalized["mode"])
        self.assertTrue(normalized["readme"].endswith("\n"))
        self.assertEqual("project-only", normalized["sandbox_profile"])
        self.assertEqual("investigate", normalized["model_optimizations"]["kv_cache"])

    def test_new_project_location_and_sandbox_are_validated_as_one_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = {
                "mode": "new", "target": str(root / "project"),
                "workspace_root": str(root), "project_name": "project",
                "readme": "# Project", "skeleton": "src/",
                "sandbox_profile": "project-only",
            }
            normalized = live.validate_onboarding_request(request)
            self.assertEqual(str(root.resolve()), normalized["workspace_root"])
            with self.assertRaisesRegex(ValueError, "must equal"):
                live.validate_onboarding_request({**request, "target": str(root / "elsewhere")})
            with self.assertRaisesRegex(ValueError, "project name"):
                live.validate_onboarding_request({**request, "project_name": "../escape"})
            with self.assertRaisesRegex(ValueError, "only project-only"):
                live.validate_onboarding_request({**request, "sandbox_profile": "unrestricted"})
            with self.assertRaisesRegex(ValueError, "KV-cache preference"):
                live.validate_onboarding_request({**request, "model_optimizations": {"kv_cache": "magic"}})

    def test_new_project_preview_is_read_only_and_reports_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "new-project"
            request = {
                "mode": "new", "target": str(target), "template": "generic",
                "readme": "# New project", "skeleton": "- src\n- tests",
            }
            preview = live.preview_project_onboarding(request)
            self.assertFalse(target.exists())
            self.assertTrue(preview["can_apply"])
            self.assertEqual(["README.md", "skeleton.md", "leafos.project.json"], preview["files_to_create"])
            target.mkdir()
            (target / "README.md").write_text("owned", encoding="utf-8")
            conflict = live.preview_project_onboarding(request)
            self.assertFalse(conflict["can_apply"])
            self.assertEqual(["README.md"], conflict["conflicts"])

    def test_onboarding_preserves_pasted_documents_and_enters_normal_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "from-scratch"
            runs = root / "runs"
            request = {
                "mode": "new", "target": str(target), "template": "generic",
                "readme": "# Operator README\n\nExact intent.\n",
                "skeleton": "src/\n  engine.py\ntests/\n",
                "objective": "Build the first deterministic slice.",
                "provider": "off", "spawn": False,
                "sandbox_profile": "project-only",
                "model_optimizations": {"kv_cache": "investigate"},
            }
            with mock.patch.object(live.inlet, "RUNS_ROOT", runs), mock.patch.object(
                live.inlet, "LIVE_INTAKE_ROOT", runs / "live-intake"
            ):
                result = live.apply_project_onboarding(request, run_dir=str(root / "run"))
            self.assertEqual(request["readme"], (target / "README.md").read_text(encoding="utf-8"))
            self.assertEqual(request["skeleton"], (target / "skeleton.md").read_text(encoding="utf-8"))
            manifest = json.loads((target / "leafos.project.json").read_text(encoding="utf-8"))
            self.assertEqual("operator_onboarding", manifest["source"])
            self.assertEqual(request["objective"], manifest["objective"])
            self.assertEqual("project-only", manifest["sandbox_profile"])
            self.assertTrue((Path(result["run_dir"]) / "queue.json").is_file())
            self.assertEqual("new", result["onboarding"]["mode"])
            self.assertEqual("kv_cache", result["optimization_task"]["metadata"]["model_optimization"])
            self.assertEqual(1, result["optimization_task"]["priority"])
            preferences = json.loads((Path(result["run_dir"]) / "stack-preferences.json").read_text(encoding="utf-8"))
            self.assertEqual("queued", preferences["application"]["status"])
            self.assertFalse(preferences["application"]["applied"])
            report_id = next(
                task["task_id"] for task in json.loads((Path(result["run_dir"]) / "queue.json").read_text())["tasks"]
                if task["kind"] == "report"
            )
            self.assertEqual([report_id], result["optimization_task"]["dependencies"])

    def test_inherited_model_settings_do_not_create_optimization_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "inherit-project"
            runs = root / "runs"
            request = {
                "mode": "new", "target": str(target), "readme": "# Inherit\n",
                "skeleton": "src/\n", "provider": "off", "spawn": False,
                "model_optimizations": {"kv_cache": "inherit"},
            }
            with mock.patch.object(live.inlet, "RUNS_ROOT", runs), mock.patch.object(
                live.inlet, "LIVE_INTAKE_ROOT", runs / "live-intake"
            ):
                result = live.apply_project_onboarding(request, run_dir=str(root / "run"))
            self.assertIsNone(result["optimization_task"])
            preferences = json.loads((Path(result["run_dir"]) / "stack-preferences.json").read_text(encoding="utf-8"))
            self.assertEqual("inherited", preferences["application"]["status"])
            queue = json.loads((Path(result["run_dir"]) / "queue.json").read_text(encoding="utf-8"))
            self.assertFalse(any(task.get("kind") == "operator" for task in queue["tasks"]))

    def test_onboarding_admits_preferences_before_starting_resident(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "existing"
            run_dir = root / "run"
            target.mkdir()
            run_dir.mkdir()
            (run_dir / "run.json").write_text("{}", encoding="utf-8")
            (run_dir / "queue.json").write_text('{"tasks":[]}', encoding="utf-8")
            started = {"preferences_present": False}

            def ensure(_run_dir):
                started["preferences_present"] = (run_dir / "stack-preferences.json").is_file()
                return 4242

            with mock.patch.object(
                live, "start_project", return_value={"action": "attached", "run_dir": str(run_dir), "target": str(target)}
            ) as start, mock.patch.object(live.engine, "append_event"), mock.patch.object(
                resident_supervisor, "initialize_resident"
            ) as initialize, mock.patch.object(resident_supervisor, "ensure_supervisor", side_effect=ensure):
                result = live.apply_project_onboarding({
                    "mode": "existing", "target": str(target), "provider": "off", "spawn": True,
                })
            self.assertFalse(start.call_args.kwargs["spawn"])
            self.assertTrue(started["preferences_present"])
            self.assertEqual(4242, result["resident_pid"])
            initialize.assert_called_once()

    def test_existing_onboarding_inspects_without_writing_project_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "existing"
            target.mkdir()
            (target / "README.md").write_text("# Existing\n", encoding="utf-8")
            before = {path.name: path.read_bytes() for path in target.iterdir()}
            preview = live.preview_project_onboarding({"mode": "existing", "target": str(target)})
            after = {path.name: path.read_bytes() for path in target.iterdir()}
            self.assertEqual(before, after)
            self.assertEqual("documents", preview["inventory"]["state"])
            self.assertEqual([], preview["files_to_create"])
            with self.assertRaisesRegex(ValueError, "does not write"):
                live.validate_onboarding_request({"mode": "existing", "target": str(target), "readme": "replace"})

    def test_guided_wizard_collects_multiline_project_intent_and_requires_create(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "guided"
            input_stream = io.StringIO(
                "1\n" + str(target.parent) + "\nguided\ngeneric\n# Guided\nPurpose.\n.done\nsrc/\ntests/\n.done\n\n\ninvestigate\nreview\nCREATE\n"
            )
            output = io.StringIO()
            captured = {}

            def preview(request):
                captured.update(request)
                return live.preview_project_onboarding(request)

            def apply(request):
                return {"target": request["target"], "run_dir": "C:/runs/guided"}

            result = project_wizard.run_project_wizard(
                preview=preview, apply=apply, input_stream=input_stream, output=output,
                defaults={"provider": "off", "spawn": False},
            )
            self.assertEqual("C:/runs/guided", result["run_dir"])
            self.assertEqual("# Guided\nPurpose.\n", captured["readme"])
            self.assertEqual("src/\ntests/\n", captured["skeleton"])
            self.assertEqual(str(target.parent.resolve()), str(Path(captured["workspace_root"]).resolve()))
            self.assertEqual("guided", captured["project_name"])
            self.assertEqual("project-only", captured["sandbox_profile"])
            self.assertEqual("investigate", captured["model_optimizations"]["kv_cache"])
            self.assertIn("Step 6/6", output.getvalue())
            self.assertIn("Type CREATE", output.getvalue())

    def test_guided_wizard_selects_and_inspects_a_recent_existing_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "existing"
            target.mkdir()
            (target / "README.md").write_text("# Existing\n", encoding="utf-8")
            input_stream = io.StringIO("2\n1\n\n\n\n\nreview\nOPEN\n")
            output = io.StringIO()
            applied = []

            def apply(request):
                applied.append(request)
                return {"target": request["target"], "run_dir": "C:/runs/existing"}

            result = project_wizard.run_project_wizard(
                preview=live.preview_project_onboarding, apply=apply,
                recent_targets=[str(target)], input_stream=input_stream, output=output,
            )
            self.assertEqual("C:/runs/existing", result["run_dir"])
            self.assertEqual("existing", applied[0]["mode"])
            self.assertEqual(str(target.resolve()), applied[0]["target"])
            self.assertIn("Detected documents", output.getvalue())
            self.assertIn("Type OPEN", output.getvalue())

    def test_real_repository_is_detected_as_codebase(self) -> None:
        inventory = live.inspect_project(ROOT)
        self.assertEqual("codebase", inventory["state"])
        self.assertGreater(inventory["source_file_count"], 0)
        self.assertEqual(["."], inventory["allowed_paths"])

    def test_blank_generic_seed_contains_only_readme_skeleton_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "generic"
            written = live.initialize_seed(target, "generic")
            self.assertEqual({"README.md", "skeleton.md", "leafos.project.json"}, {Path(path).name for path in written})
            self.assertEqual(3, len(list(target.iterdir())))
            inventory = live.inspect_project(target)
            self.assertEqual("seed", inventory["state"])
            self.assertEqual(0, inventory["source_file_count"])

    def test_generic_manifest_template_is_detected_independent_of_directory_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "project"
            live.initialize_seed(target, "generic")
            inventory = live.inspect_project(target)
            objective = live.derive_objective(inventory, iteration=1)
            self.assertIn("Project improvement iteration 1", objective)

    def test_seed_initialization_never_overwrites_project_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            (target / "README.md").write_text("operator content", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "will not overwrite"):
                live.initialize_seed(target, "generic")
            self.assertEqual("operator content", (target / "README.md").read_text(encoding="utf-8"))

    def test_active_command_parser_accepts_minimal_and_natural_syntax(self) -> None:
        self.assertEqual({"action": "improve", "objective": ""}, live.parse_active_command(":improve"))
        self.assertEqual({"action": "improve", "objective": ""}, live.parse_active_command(":again"))
        self.assertEqual("make bots trade", live.parse_active_command(":make bots trade")["objective"])
        project = live.parse_active_command(':project "C:\\R\\Games\\Catan Two"')
        self.assertEqual("C:\\R\\Games\\Catan Two", project["target"])
        created = live.parse_active_command(':new "C:\\R\\Games\\Catan Two" generic')
        self.assertTrue(created["create"])
        self.assertEqual("generic", created["template"])
        with self.assertRaisesRegex(ValueError, "does not take arguments"):
            live.parse_active_command(":again now")
        self.assertEqual({"action": "resident_mode", "mode": "quiet"}, live.parse_active_command(":mode quiet"))
        self.assertEqual(
            {"action": "resident_targets", "cpu": 80.0, "gpu": 90.0},
            live.parse_active_command(":targets cpu 80 gpu 90"),
        )
        self.assertEqual({"action": "resident_budget", "minutes": 64}, live.parse_active_command(":budget 64m"))

    def test_missing_objective_derives_iteration_from_current_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "generic"
            live.initialize_seed(target, "generic")
            inventory = live.inspect_project(target)
            first = live.derive_objective(inventory, iteration=1)
            second = live.derive_objective(inventory, iteration=2)
            self.assertIn("Project improvement iteration 1", first)
            self.assertIn("iteration 2", second)
            self.assertNotEqual(first, second)

    def test_generated_intake_is_valid_under_trusted_run_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "project"
            live.initialize_seed(target, "generic")
            inventory = live.inspect_project(target)
            with mock.patch.object(live.inlet, "LIVE_INTAKE_ROOT", root / "runs" / "live-intake"):
                path = live.create_intake_work_order(inventory, live.derive_objective(inventory))
                loaded = live.inlet.work_orders.load_work_order(path)
                validated = live.inlet.work_orders.validate_work_order(loaded, target)
            self.assertTrue(validated["allow_mutation"])
            self.assertEqual(["."], validated["allowed_paths"])

    def test_starting_existing_codebase_does_not_add_control_files_to_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "existing"
            target.mkdir()
            (target / "README.md").write_text("# Existing\n", encoding="utf-8")
            (target / "main.py").write_text("print('ready')\n", encoding="utf-8")
            before = {path.name: path.read_bytes() for path in target.iterdir()}
            runs = root / "runs"
            with mock.patch.object(live.inlet, "RUNS_ROOT", runs), mock.patch.object(
                live.inlet, "LIVE_INTAKE_ROOT", runs / "live-intake"
            ):
                result = live.start_project(
                    target, provider="off", fresh_run=True, spawn=False, run_dir=str(root / "run")
                )
            after = {path.name: path.read_bytes() for path in target.iterdir()}
            self.assertEqual(before, after)
            self.assertEqual(2, json.loads((Path(result["run_dir"]) / "run.json").read_text())["version"])

    def test_repeated_improvements_share_one_run_and_form_a_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "project"
            runs = root / "runs"
            with mock.patch.object(live.inlet, "RUNS_ROOT", runs), mock.patch.object(
                live.inlet, "LIVE_INTAKE_ROOT", runs / "live-intake"
            ):
                started = live.start_project(
                    target, create_seed=True, template="generic", provider="off", fresh_run=True,
                    spawn=False, run_dir=str(root / "run"),
                )
                first = live.queue_improvement(started["run_dir"], spawn=False)
                second = live.execute_active_command(":again", started["run_dir"], spawn=False)
                run = live.engine.read_json(Path(started["run_dir"]) / "run.json", {})
            self.assertEqual(1, first["iteration"])
            self.assertEqual(2, second["iteration"])
            self.assertEqual([first["task"]["task_id"]], second["task"]["dependencies"])
            self.assertEqual(2, run["live_project"]["iteration"])
            self.assertEqual("off", second["task"]["provider"])

    def test_operator_input_is_not_blocked_behind_resident_generated_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "project"
            runs = root / "runs"
            with mock.patch.object(live.inlet, "RUNS_ROOT", runs), mock.patch.object(
                live.inlet, "LIVE_INTAKE_ROOT", runs / "live-intake"
            ):
                started = live.start_project(
                    target, create_seed=True, template="generic", provider="off", fresh_run=True,
                    spawn=False, run_dir=str(root / "run"),
                )
                resident_task = live.queue_improvement(started["run_dir"], source="resident", spawn=False)
                operator_task = live.queue_improvement(started["run_dir"], "add a bounded rule", source="operator", spawn=False)
            self.assertEqual([], resident_task["task"]["dependencies"])
            self.assertEqual([], operator_task["task"]["dependencies"])
            self.assertEqual(4, resident_task["task"]["priority"])
            self.assertEqual(2, operator_task["task"]["priority"])
            self.assertEqual(3, operator_task["task"]["max_attempts"])


if __name__ == "__main__":
    unittest.main()
