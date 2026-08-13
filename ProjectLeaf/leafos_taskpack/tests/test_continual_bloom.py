#!/usr/bin/env python3
from __future__ import annotations

import json
import concurrent.futures
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LEAFOS_ROOT = ROOT.parents[1]
PWSH = shutil.which("pwsh")
sys.path.insert(0, str(ROOT / "core" / "python"))

import leaf_continual_bloom as bloom  # noqa: E402
from leaf_durable_bridge import MondayDurableBridge  # noqa: E402


class ContinualBloomTests(unittest.TestCase):
    def test_ndjson_replace_retries_transient_windows_file_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.ndjson"
            real_replace = bloom.os.replace
            attempts = 0

            def flaky_replace(source: Path, destination: Path) -> None:
                nonlocal attempts
                attempts += 1
                if attempts < 4:
                    raise PermissionError(5, "simulated sync lock", str(destination))
                real_replace(source, destination)

            with mock.patch.object(bloom.os, "replace", side_effect=flaky_replace):
                bloom.write_ndjson(path, [{"seq": 1}])

            self.assertEqual(4, attempts)
            self.assertEqual('{"seq":1}\n', path.read_text(encoding="utf-8"))

    def test_concurrent_capability_requests_are_serialized_per_instance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            instance = Path(directory) / "monday-primary"
            bloom.initialize(instance)
            bridge = MondayDurableBridge(instance=instance, source="concurrency-test")

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                futures = [
                    pool.submit(
                        bridge.request_capability,
                        "loop.event.append",
                        actor="leafos.test",
                        reason=f"concurrent request {index}",
                    )
                    for index in range(40)
                ]
                responses = [future.result() for future in futures]

            self.assertTrue(all(response["payload"]["allowed"] for response in responses))
            report = bloom.verify(instance)
            self.assertEqual(81, report["event_count"])
            events = bloom.read_events(instance)
            self.assertEqual(list(range(1, 82)), [event["seq"] for event in events])

    def make_lifecycle(self, directory: str) -> Path:
        instance = Path(directory) / "monday-primary"
        initialized = bloom.initialize(instance)
        self.assertEqual("idle", initialized["state"]["status"])

        with self.assertRaisesRegex(bloom.BloomError, "requires a successful native validation"):
            bloom.commit_checkpoint(instance)

        received = bloom.append_input(instance, "Inspect the current acceptance evidence.")
        self.assertEqual(2, received["event"]["seq"])

        stale = bloom.record_claim(instance, "claim-stale", "This proposal is obsolete.", read_head=1)
        self.assertFalse(stale["accepted"])
        self.assertEqual("proposal.rejected_stale", stale["event"]["kind"])
        self.assertEqual(1, stale["state"]["stale_rejections"])

        claim = bloom.record_claim(
            instance,
            "claim-0042",
            "The test evidence exists and is readable.",
            read_head=stale["event"]["seq"],
        )
        self.assertTrue(claim["accepted"])
        self.assertEqual("unverified", claim["event"]["payload"]["status"])
        self.assertEqual([], json.loads("[" + ",".join(
            (instance / "facts.ndjson").read_text(encoding="utf-8").splitlines()
        ) + "]"))

        evidence = Path(directory) / "native-test-result.txt"
        evidence.write_text("PASS: deterministic native validation\n", encoding="utf-8")
        validated = bloom.validate_claim(instance, "claim-0042", "supported", evidence)
        self.assertEqual("native-validator", validated["event"]["actor"])
        self.assertEqual("supported", validated["event"]["payload"]["status"])

        checkpoint = bloom.commit_checkpoint(instance)
        self.assertEqual("checkpoint.committed", checkpoint["event"]["kind"])
        self.assertEqual(
            {"capability": "input.append", "reason": "await the next operator or tool event"},
            checkpoint["state"]["next_action"],
        )
        return instance

    def test_single_monday_instance_contract_and_required_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            instance = Path(directory) / "monday-primary"
            result = bloom.initialize(instance)
            expected = {
                "persona.json",
                "state.json",
                "events.ndjson",
                "facts.ndjson",
                "evidence",
                "checkpoints",
            }
            self.assertTrue(expected.issubset({path.name for path in instance.iterdir()}))
            persona = json.loads((instance / "persona.json").read_text(encoding="utf-8"))
            self.assertEqual("monday", persona["identity"]["key"])
            self.assertEqual("Monday — Rescue and Analysis", persona["identity"]["full_name"])
            self.assertFalse(persona["durability"]["kv_cache_authoritative"])
            serialized = json.dumps(persona, ensure_ascii=False).lower()
            self.assertNotIn("wednesday", serialized)
            self.assertNotIn("friday", serialized)
            self.assertEqual(1, result["state"]["transcript_head"])
            self.assertEqual(result["state"]["transcript_head"], result["state"]["transcript_cursor"])

    def test_claim_evidence_checkpoint_and_hash_chain_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            instance = self.make_lifecycle(directory)
            report = bloom.verify(instance)
            self.assertEqual("ok", report["status"])
            self.assertEqual(6, report["event_count"])
            self.assertEqual(1, report["fact_count"])
            self.assertEqual(1, report["checkpoint_count"])
            self.assertEqual(1, report["stale_rejections"])
            self.assertEqual(
                {
                    "total_claims": 1,
                    "supported_claims": 1,
                    "refuted_claims": 0,
                    "unverified_claims": 0,
                    "evidence_coverage": 1.0,
                    "evidence_coverage_percent": 100.0,
                },
                report["claim_metrics"],
            )
            self.assertEqual(report["transcript_head"], report["transcript_cursor"])
            facts = [
                json.loads(line)
                for line in (instance / "facts.ndjson").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual("claim-0042", facts[0]["claim_id"])
            self.assertEqual("sha256:", facts[0]["validation_hash"][:7])

    def test_recovery_rebuilds_state_facts_and_checkpoint_without_kv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            instance = self.make_lifecycle(directory)
            checkpoint_path = next((instance / "checkpoints").glob("checkpoint-*.json"))
            (instance / "kv-cache.bin").write_bytes(b"disposable")
            (instance / "kv-cache.bin").unlink()
            (instance / "state.json").unlink()
            (instance / "facts.ndjson").unlink()
            checkpoint_path.unlink()

            recovered = bloom.recover(instance)
            self.assertEqual("runtime.recovered", recovered["event"]["kind"])
            self.assertFalse(recovered["event"]["payload"]["kv_cache_used"])
            self.assertTrue((instance / "state.json").is_file())
            self.assertTrue((instance / "facts.ndjson").is_file())
            self.assertTrue(checkpoint_path.is_file())
            self.assertEqual("ok", recovered["verification"]["status"])
            self.assertEqual("input.append", recovered["state"]["next_action"]["capability"])

    def test_tampering_is_detected_before_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            instance = Path(directory) / "monday-primary"
            bloom.initialize(instance)
            path = instance / "events.ndjson"
            path.write_text(
                path.read_text(encoding="utf-8").replace("native-supervisor", "invented-authority"),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(bloom.BloomError, "event hash mismatch"):
                bloom.verify(instance)
            with self.assertRaisesRegex(bloom.BloomError, "event hash mismatch"):
                bloom.recover(instance)

    def test_published_contract_files_are_valid_json(self) -> None:
        files = (
            ROOT / "config" / "continual-bloom-monday.json",
            ROOT / "schemas" / "leafos.continual-bloom-event.v1.schema.json",
            ROOT / "schemas" / "leafos.continual-bloom-state.v1.schema.json",
        )
        for path in files:
            self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)

    def test_uninitialized_status_is_read_only_and_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            instance = Path(directory) / "monday-primary"
            result = bloom.status(instance)
            self.assertEqual("not_initialized", result["status"])
            self.assertEqual("instance.initialize", result["next_action"]["capability"])
            self.assertIsNone(result["claim_metrics"]["evidence_coverage"])
            self.assertFalse(instance.exists())

    @unittest.skipUnless(PWSH, "PowerShell 7 is required")
    def test_root_shell_route_initializes_and_reports_instance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            instance = Path(directory) / "monday-primary"
            initialized = subprocess.run(
                [
                    PWSH,
                    "-NoProfile",
                    "-File",
                    str(LEAFOS_ROOT / "leafos.ps1"),
                    "bloom",
                    "init",
                    "--instance",
                    str(instance),
                    "--json",
                ],
                cwd=LEAFOS_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            self.assertEqual(0, initialized.returncode, initialized.stderr)
            self.assertEqual("monday-primary", json.loads(initialized.stdout)["state"]["instance_id"])
            status = subprocess.run(
                [
                    PWSH,
                    "-NoProfile",
                    "-File",
                    str(LEAFOS_ROOT / "leafos.ps1"),
                    "b",
                    "--instance",
                    str(instance),
                    "--json",
                ],
                cwd=LEAFOS_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            self.assertEqual(0, status.returncode, status.stderr)
            self.assertEqual("ok", json.loads(status.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
