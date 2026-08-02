from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("leaf_midend", ROOT / "core" / "web" / "midend.py")
midend = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(midend)


class MidendGatewayTests(unittest.TestCase):
    def test_index_and_assets_are_traditional_static_routes(self) -> None:
        for path, content_type in (("/", "text/html"), ("/app.css", "text/css"), ("/app.js", "text/javascript"), ("/favicon.ico", "image/x-icon")):
            response = midend.route(path)
            self.assertIsNotNone(response)
            self.assertEqual(200, response[0])
            self.assertTrue(response[1].startswith(content_type))
            self.assertTrue(response[2])

        script = midend.route("/app.js")[2].decode("utf-8")
        self.assertIn("commands/pause", script)
        self.assertIn("leafos.midend_action_request", script)
        self.assertIn("await refresh()", script)
        self.assertIn("hardware-hz", script)
        self.assertIn("requestAnimationFrame(drawGraphs)", script)
        self.assertIn("hardwarePending", script)

    def test_api_index_is_explicitly_read_only(self) -> None:
        status, _, payload = midend.route("/api/v1")
        value = json.loads(payload)
        self.assertEqual(200, status)
        self.assertTrue(value["read_only"])
        self.assertIn("WO-044", value["mutations"])

    def test_hardware_route_uses_existing_fast_telemetry(self) -> None:
        sample = {"hardware": {"cpu": {"utilization_percent": 12}}, "availability": {"cpu_counters": "available"}}
        with mock.patch.object(midend.telemetry, "collect_fast_hardware", return_value=sample):
            status, _, payload = midend.route("/api/v1/hardware")
        value = json.loads(payload)
        self.assertEqual(200, status)
        self.assertEqual(12, value["hardware"]["cpu"]["utilization_percent"])

    def test_project_start_supports_existing_and_new_codebases(self) -> None:
        for mode, create_seed in (("existing", False), ("new", True)):
            with self.subTest(mode=mode), mock.patch.object(
                midend.live_projects, "start_project", return_value={"action": "created", "run_dir": "C:/run"}
            ) as start:
                body = json.dumps({"mode": mode, "target": "C:/R/Example", "provider": "off", "approved": True}).encode()
                status, _, payload = midend.action_route("/api/v1/projects/commands/start", body)
                self.assertEqual(202, status)
                self.assertEqual("leafos.midend_project_disposition", json.loads(payload)["leafos_object"])
                self.assertEqual(create_seed, start.call_args.kwargs["create_seed"])

    def test_task_deploy_calls_live_project_queue_authority(self) -> None:
        original = midend.RUNS_ROOT
        try:
            with tempfile.TemporaryDirectory() as directory:
                midend.RUNS_ROOT = Path(directory)
                run_dir = midend.RUNS_ROOT / "run_deploy01"
                run_dir.mkdir()
                (run_dir / "run.json").write_text("{}", encoding="utf-8")
                result = {"action": "improve", "task": {"task_id": "TASK-0001"}}
                with mock.patch.object(midend.live_projects, "queue_improvement", return_value=result) as queue:
                    status, _, payload = midend.action_route(
                        "/api/v1/runs/run_deploy01/commands/deploy", json.dumps({"objective": "Improve validation"}).encode()
                    )
                self.assertEqual(202, status)
                self.assertEqual("TASK-0001", json.loads(payload)["task"]["task_id"])
                queue.assert_called_once_with(run_dir, "Improve validation", spawn=True, source="operator")
        finally:
            midend.RUNS_ROOT = original

    def test_run_resource_rejects_path_traversal(self) -> None:
        status, _, payload = midend.route("/api/v1/runs/%2e%2e%2fsecret")
        self.assertEqual(404, status)
        self.assertEqual("RESOURCE_NOT_FOUND", json.loads(payload)["code"])

    def test_run_detail_reads_durable_files_without_mutation(self) -> None:
        original = midend.RUNS_ROOT
        try:
            with tempfile.TemporaryDirectory() as directory:
                midend.RUNS_ROOT = Path(directory)
                run_dir = midend.RUNS_ROOT / "run_test01"
                run_dir.mkdir()
                run = {"run_id": "run_test01", "version": 4, "state": "executing", "target": "C:/R/Test"}
                (run_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")
                before = (run_dir / "run.json").read_bytes()
                status, _, payload = midend.route("/api/v1/runs/run_test01")
                value = json.loads(payload)
                self.assertEqual(200, status)
                self.assertEqual("run_test01", value["resource"]["id"])
                self.assertEqual(["run.cancel", "run.pause"], [item["id"] for item in value["capabilities"]])
                self.assertTrue(all(item["authority"] == "advisory_only" for item in value["capabilities"]))
                self.assertEqual(before, (run_dir / "run.json").read_bytes())
        finally:
            midend.RUNS_ROOT = original

    def test_run_pause_requires_strict_envelope_and_native_admission(self) -> None:
        original_midend_runs = midend.RUNS_ROOT
        original_admission_runs = midend.admit_action.__globals__["RUNS_ROOT"]
        try:
            with tempfile.TemporaryDirectory() as directory:
                runs = Path(directory)
                midend.RUNS_ROOT = runs
                midend.admit_action.__globals__["RUNS_ROOT"] = runs
                run_dir = runs / "run_pause01"
                run_dir.mkdir()
                (run_dir / "run.json").write_text(json.dumps({"run_id": "run_pause01", "version": 2, "target": str(runs)}), encoding="utf-8")
                (run_dir / "state.json").write_text(json.dumps({"status": "running", "accepting_tasks": True}), encoding="utf-8")
                (run_dir / "queue.json").write_text(json.dumps({"tasks": []}), encoding="utf-8")
                now = datetime.now(timezone.utc)
                request = {
                    "leafos_object": "leafos.midend_action_request", "version": 1,
                    "capability_id": "run.pause", "request_id": "req_pause0001",
                    "session_id": "ses_local0001", "subject": {"type": "operator", "id": "local-user"},
                    "target": {"type": "run", "id": "run_pause01", "version": 2},
                    "nonce": "single-use-nonce-0001", "issued_at": now.isoformat(),
                    "expires_at": (now + timedelta(minutes=2)).isoformat(),
                    "payload": {"reason": "operator requested pause"},
                }
                status, _, payload = midend.action_route("/api/v1/runs/run_pause01/commands/pause", json.dumps(request).encode())
                disposition = json.loads(payload)
                self.assertEqual(202, status)
                self.assertEqual("accepted", disposition["status"])
                self.assertEqual("paused", json.loads((run_dir / "state.json").read_text())["status"])
                replay_status, _, replay_payload = midend.action_route("/api/v1/runs/run_pause01/commands/pause", json.dumps(request).encode())
                self.assertEqual(200, replay_status)
                self.assertEqual(disposition, json.loads(replay_payload))
                events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
                self.assertIn("run.paused", events)
                self.assertIn(disposition["request_digest"], events)
        finally:
            midend.RUNS_ROOT = original_midend_runs
            midend.admit_action.__globals__["RUNS_ROOT"] = original_admission_runs

    def test_run_pause_rejects_unknown_fields_and_target_mismatch(self) -> None:
        request = {"target": {"id": "other"}, "shell": "rm -rf /"}
        status, _, payload = midend.action_route("/api/v1/runs/run_pause01/commands/pause", json.dumps(request).encode())
        self.assertEqual(400, status)
        self.assertEqual("TARGET_MISMATCH", json.loads(payload)["code"])

    def test_unknown_route_is_not_claimed(self) -> None:
        self.assertIsNone(midend.route("/manifest.json"))

    def test_secondary_resource_adapters_are_deterministic_and_read_only(self) -> None:
        original_runs = midend.RUNS_ROOT
        original_profiles = midend.RUNTIME_PROFILES
        original_manifests = midend.INSTALL_MANIFESTS
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                midend.RUNS_ROOT = root / "runs"
                run_dir = midend.RUNS_ROOT / "run_test01"
                run_dir.mkdir(parents=True)
                (run_dir / "run.json").write_text(json.dumps({"run_id": "run_test01"}), encoding="utf-8")
                (run_dir / "queue.json").write_text(json.dumps({"tasks": [
                    {"task_id": "task_b01", "status": "queued", "dependencies": ["task_a01"]},
                    {"task_id": "task_a01", "status": "complete", "dependencies": []},
                ]}), encoding="utf-8")
                (run_dir / "report.md").write_text("validated report", encoding="utf-8")
                midend.RUNTIME_PROFILES = root / "profiles.json"
                midend.RUNTIME_PROFILES.write_text(json.dumps({"profiles": {"zeta": {"use": "z"}, "alpha": {"use": "a"}}}), encoding="utf-8")
                manifest = root / "install-manifest.json"
                manifest.write_text(json.dumps({"schema": "leafos.application-install.v1", "files": [{"path": "a"}]}), encoding="utf-8")
                midend.INSTALL_MANIFESTS = (manifest,)

                tasks = json.loads(midend.route("/api/v1/tasks")[2])
                reports = json.loads(midend.route("/api/v1/reports")[2])
                profiles = json.loads(midend.route("/api/v1/profiles")[2])
                plans = json.loads(midend.route("/api/v1/install-plans")[2])
                self.assertEqual(["task_a01", "task_b01"], [item["id"] for item in tasks["items"]])
                self.assertEqual("evidence://runs/run_test01/report.md", reports["items"][0]["evidence_ref"])
                self.assertEqual(["alpha", "zeta"], [item["id"] for item in profiles["items"]])
                self.assertEqual(1, plans["items"][0]["file_count"])
                self.assertTrue(all(value["read_only"] for value in (tasks, reports, profiles, plans)))
        finally:
            midend.RUNS_ROOT = original_runs
            midend.RUNTIME_PROFILES = original_profiles
            midend.INSTALL_MANIFESTS = original_manifests

    def test_capability_catalog_and_discovery_never_enable_mutation(self) -> None:
        catalog = json.loads(midend.route("/api/v1/capabilities")[2])
        self.assertEqual(14, catalog["count"])
        self.assertEqual("advisory_only_native_inlet_required", catalog["authority"])
        original = midend.RUNS_ROOT
        try:
            with tempfile.TemporaryDirectory() as directory:
                midend.RUNS_ROOT = Path(directory)
                run_dir = midend.RUNS_ROOT / "run_pause01"
                run_dir.mkdir()
                (run_dir / "run.json").write_text(json.dumps({"run_id": "run_pause01", "version": 2, "state": "paused"}), encoding="utf-8")
                (run_dir / "checkpoint.json").write_text("{}", encoding="utf-8")
                status, _, payload = midend.route("/api/v1/runs/run_pause01/capabilities")
                value = json.loads(payload)
                self.assertEqual(200, status)
                self.assertEqual(["run.cancel", "run.resume"], [item["id"] for item in value["capabilities"]])
                self.assertTrue(value["native_admission_required"])
                self.assertFalse(value["mutations_enabled"])
        finally:
            midend.RUNS_ROOT = original


if __name__ == "__main__":
    unittest.main()
