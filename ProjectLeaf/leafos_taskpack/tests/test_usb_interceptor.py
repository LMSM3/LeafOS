#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "leaf_usb_interceptor_test",
    ROOT / "core" / "python" / "leaf_usb_interceptor.py",
)
transport = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(transport)


def write_run(base: pathlib.Path, run_id: str = "usb-fixture") -> pathlib.Path:
    target = base / "target"
    target.mkdir(exist_ok=True)
    run_dir = base / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({
        "leafos_object": "agent_loop_run",
        "version": 2,
        "run_id": run_id,
        "target": str(target),
        "run_dir": str(run_dir),
        "profile": "local-coding",
        "provider_mode": "off",
        "provider_status": "off",
        "stack_entry": "local-stack:test",
        "work_order": {"id": "WO-FIXTURE", "title": "USB fixture", "source": str(base / "WO-FIXTURE.json")},
    }), encoding="utf-8")
    (run_dir / "queue.json").write_text(json.dumps({
        "leafos_object": "agent_loop_queue", "version": 2, "run_id": run_id, "tasks": [],
    }), encoding="utf-8")
    (run_dir / "state.json").write_text(json.dumps({
        "leafos_object": "agent_loop_state", "version": 2, "run_id": run_id,
        "status": "created", "current_task_id": "", "accepting_tasks": True,
    }), encoding="utf-8")
    (run_dir / "checkpoint.json").write_text(json.dumps({}), encoding="utf-8")
    (run_dir / "events.jsonl").write_text(
        json.dumps({"seq": 1, "time": "2026-07-24T00:00:00+00:00", "kind": "run.started"}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "report.md").write_text("# Fixture report\n", encoding="utf-8")
    return run_dir


def write_message(root: pathlib.Path, envelope: dict, name: str | None = None) -> pathlib.Path:
    path = root / "inbox" / (name or f"{envelope['message_id']}.json")
    path.write_text(json.dumps(envelope), encoding="utf-8")
    return path


class UsbInterceptorTests(unittest.TestCase):
    def setup_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        base = pathlib.Path(temporary.name)
        spool = base / "usb"
        transport.initialize(spool, "fixture-usb-01")
        run_dir = write_run(base)
        return temporary, base, spool, run_dir

    def envelope(self, run_dir: pathlib.Path, **overrides):
        values = {
            "direction": "inbound",
            "message_id": "msg-usb-001",
            "sequence": 1,
            "sender_id": "fixture-device",
            "target_id": "leafos-host",
            "target_run": str(run_dir),
            "payload_type": "monitor.snapshot",
            "payload": {"after": 0, "heartbeat_timeout": 90},
        }
        values.update(overrides)
        return transport.make_envelope(**values)

    def test_init_creates_spool_and_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = transport.initialize(pathlib.Path(tmp) / "usb", "operator-stick-a")
            self.assertEqual("operator-stick-a", state["identity"])
            self.assertEqual(set(transport.SPOOL_DIRS), {
                path.name for path in pathlib.Path(tmp, "usb").iterdir()
            })

    def test_valid_monitor_request_is_delivered_once_and_acknowledged(self):
        temporary, _base, spool, run_dir = self.setup_fixture()
        with temporary, mock.patch.object(transport.inlet, "RUNS_ROOT", run_dir.parent):
            envelope = self.envelope(run_dir)
            write_message(spool, envelope)
            first = transport.pump_once(spool)
            self.assertEqual("accepted", first[0]["status"])
            self.assertEqual(1, len(list((spool / "complete").glob("*.json"))))
            self.assertEqual(1, len(list((spool / "outbox").glob("*.json"))))

            write_message(spool, envelope, "replayed-copy.json")
            duplicate = transport.pump_once(spool)
            self.assertEqual("duplicate", duplicate[0]["status"])
            state = transport.engine.read_json(spool / transport.STATE_FILE, {})
            self.assertEqual("accepted", state["messages"][envelope["message_id"]]["status"])

    def test_task_submit_enters_existing_inlet_and_duplicate_does_not_add_task(self):
        temporary, _base, spool, run_dir = self.setup_fixture()
        with temporary, mock.patch.object(transport.inlet, "RUNS_ROOT", run_dir.parent):
            payload = {
                "leafos_object": "leafos.task_control_request",
                "version": 1,
                "request_id": "req-usb-submit-001",
                "action": "submit",
                "task": {
                    "task_id": "TASK-USB-001",
                    "objective": "Run the bounded USB fixture command.",
                    "allowed_paths": ["."],
                    "acceptance": ["The declared command exits successfully."],
                    "commands": {"tests": [[sys.executable, "--version"]]},
                    "approval_mode": "automatic",
                    "allow_mutation": False,
                    "stack_role": "cpu",
                },
            }
            envelope = self.envelope(run_dir, payload_type="task.submit", payload=payload)
            write_message(spool, envelope)
            self.assertEqual("accepted", transport.pump_once(spool)[0]["status"])
            queue = transport.engine.read_json(run_dir / "queue.json", {})
            self.assertEqual(1, len(queue["tasks"]))
            self.assertEqual("req-usb-submit-001", queue["tasks"][0]["request_id"])

            write_message(spool, envelope, "task-replay.json")
            self.assertEqual("duplicate", transport.pump_once(spool)[0]["status"])
            queue = transport.engine.read_json(run_dir / "queue.json", {})
            self.assertEqual(1, len(queue["tasks"]))

    def test_malformed_and_hash_invalid_messages_are_quarantined_or_rejected(self):
        temporary, _base, spool, run_dir = self.setup_fixture()
        with temporary, mock.patch.object(transport.inlet, "RUNS_ROOT", run_dir.parent):
            (spool / "inbox" / "malformed.json").write_text("{not-json", encoding="utf-8")
            malformed = transport.pump_once(spool)
            self.assertEqual("rejected", malformed[0]["status"])
            self.assertEqual(1, len(list((spool / "quarantine").glob("*.json"))))

            invalid = self.envelope(run_dir, message_id="msg-usb-002", sequence=2)
            invalid["payload"]["after"] = 99
            write_message(spool, invalid)
            result = transport.pump_once(spool)[0]
            self.assertEqual("rejected", result["status"])
            self.assertIn("hash", result["error"])
            self.assertEqual(2, len(list((spool / "quarantine").glob("*.json"))))

    def test_old_sequence_is_rejected_and_partial_files_are_ignored(self):
        temporary, _base, spool, run_dir = self.setup_fixture()
        with temporary, mock.patch.object(transport.inlet, "RUNS_ROOT", run_dir.parent):
            write_message(spool, self.envelope(run_dir))
            self.assertEqual("accepted", transport.pump_once(spool)[0]["status"])
            stale = self.envelope(run_dir, message_id="msg-usb-003", sequence=1)
            write_message(spool, stale)
            (spool / "inbox" / "partial.json.tmp").write_text("{", encoding="utf-8")
            results = transport.pump_once(spool)
            self.assertEqual(["rejected"], [item["status"] for item in results])
            self.assertTrue((spool / "inbox" / "partial.json.tmp").is_file())

    def test_processing_files_are_recovered_after_restart(self):
        temporary, _base, spool, run_dir = self.setup_fixture()
        with temporary, mock.patch.object(transport.inlet, "RUNS_ROOT", run_dir.parent):
            envelope = self.envelope(run_dir)
            (spool / "processing" / "interrupted.json").write_text(json.dumps(envelope), encoding="utf-8")
            results = transport.pump_once(spool)
            self.assertEqual("accepted", results[0]["status"])
            self.assertFalse((spool / "processing" / "interrupted.json").exists())
            self.assertEqual(1, len(list((spool / "complete").glob("*.json"))))

    def test_report_json_returns_structured_status(self):
        temporary, _base, spool, run_dir = self.setup_fixture()
        with temporary, mock.patch.object(transport.inlet, "RUNS_ROOT", run_dir.parent):
            envelope = self.envelope(
                run_dir,
                payload_type="report.get",
                payload={"format": "json"},
            )
            write_message(spool, envelope)
            result = transport.pump_once(spool)[0]
            self.assertEqual("accepted", result["status"])
            ack = transport.engine.read_json(next((spool / "outbox").glob("*.json")), {})
            self.assertEqual("json", ack["payload"]["result"]["format"])
            self.assertIn("status", ack["payload"]["result"])

    def test_long_approval_message_id_stays_within_inlet_request_limit(self):
        message_id = "msg-" + ("long-" * 19)
        request_id = transport._request_id_for(message_id)
        self.assertLessEqual(len(request_id), 64)
        self.assertRegex(request_id, r"^[A-Za-z][A-Za-z0-9._-]{2,63}$")


if __name__ == "__main__":
    unittest.main()
