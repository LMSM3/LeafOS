#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MEMORY = ROOT / "core" / "memory"
sys.path.insert(0, str(MEMORY))

import checkpoint  # noqa: E402
import index as memory_index  # noqa: E402
import pack as memory_pack  # noqa: E402
import retention as memory_retention  # noqa: E402
from journal import append_native, replay  # noqa: E402
from reflection import ReflectionError, append_reflection  # noqa: E402


def artifact(summary: str, task: str = "WO-021") -> dict:
    return {
        "schema": "leafos.reasoning-artifact.v1",
        "run_id": "memory-pipeline-test",
        "task_id": task,
        "created_at": "2026-07-19T12:00:00Z",
        "producer": {"provider": "llama.cpp", "model": "fixture.gguf", "mode": "requested_summary"},
        "decision_summary": summary,
        "assumptions": ["journal is authoritative"],
        "alternatives": ["do not index"],
        "evidence_refs": ["fixture"],
        "constraint_refs": ["WO-021"],
        "uncertainties": [],
        "unresolved_questions": [],
        "proposed_next_action": "verify",
        "token_accounting": {
            "context_limit": 4096, "input_tokens": 10, "memory_tokens": 0,
            "reasoning_budget_requested": "auto", "output_tokens": 8,
        },
        "phase_timeline": {
            "schema": "leafos.thinking-loop.v1", "run_id": "memory-pipeline-test",
            "phases": [], "events": [],
        },
    }


class MemoryPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.journal = self.root / "memory.lmem"
        self.payload = self.root / "reflection.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def append(self, value: dict) -> dict:
        self.payload.write_text(json.dumps(value), encoding="utf-8")
        return append_reflection(self.journal, self.payload, "leafos-test")

    def append_tombstone(self, target_event_id: str) -> None:
        events = replay(self.journal)
        prior = events[-1]
        event = {
            "schema": "leafos.memory.event.v1", "event_id": "mem_tombstone01",
            "run_id": "memory-pipeline-test", "project_id": "leafos-test",
            "sequence": int(prior["sequence"]) + 1, "timestamp_utc": "2026-07-19T12:01:00Z",
            "kind": "tombstone", "epistemic_class": "record",
            "source": {"actor": "operator", "model": None, "tool": "redaction-test", "parent_event_ids": []},
            "scope": {"task_id": "WO-019", "paths": [], "symbols": []},
            "content": {
                "mime": "application/json", "text": "redaction requested",
                "data": {"target_event_ids": [target_event_id], "reason": "fixture"},
            },
            "retrieval": {"importance": 1.0, "expires_at": None, "sensitivity": "private", "indexable": True},
            "integrity": {
                "payload_sha256": "0" * 64,
                "previous_event_sha256": prior["integrity"]["payload_sha256"],
                "writer_version": "leaf-memory/0.2.2.1",
            },
        }
        append_native(self.journal, event)

    def test_reflection_append_replay_and_self_promotion_rejection(self) -> None:
        committed = []
        self.payload.write_text(json.dumps(artifact("alpha planning decision")), encoding="utf-8")
        result = append_reflection(self.journal, self.payload, "leafos-test", on_commit=committed.append)
        self.assertTrue(result["ok"])
        self.assertEqual(committed[0]["event_id"], result["event"]["event_id"])
        events = replay(self.journal)
        self.assertEqual(events[0]["kind"], "reflection")
        self.assertEqual(events[0]["epistemic_class"], "record")
        before = self.journal.read_bytes()
        promoted = artifact("untrusted promotion")
        promoted["authority"] = "committed_fact"
        with self.assertRaises(ReflectionError):
            self.append(promoted)
        self.assertEqual(before, self.journal.read_bytes())

    def test_cli_rejects_promotion_with_structured_error(self) -> None:
        promoted = artifact("untrusted promotion")
        promoted["epistemic_class"] = "evidence"
        self.payload.write_text(json.dumps(promoted), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(MEMORY / "memory_cli.py"), "append", "--kind", "reflection",
             "--journal", str(self.journal), "--payload", str(self.payload)],
            capture_output=True, text=True,
        )
        response = json.loads(completed.stdout)
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(response["ok"])
        self.assertFalse(self.journal.exists())

    def test_index_rebuild_has_byte_identical_queries(self) -> None:
        self.append(artifact("alpha planning decision", "one"))
        self.append(artifact("beta implementation decision", "two"))
        database = self.root / "memory.sqlite3"
        first_status = memory_index.build(self.journal, database)
        queries = ["alpha", "beta", "decision"]
        first = json.dumps(
            [memory_index.query(database, query) for query in queries],
            sort_keys=True, separators=(",", ":"),
        ).encode()
        second_status = memory_index.build(self.journal, database, replace=True)
        second = json.dumps(
            [memory_index.query(database, query) for query in queries],
            sort_keys=True, separators=(",", ":"),
        ).encode()
        self.assertEqual(first, second)
        self.assertEqual(first_status["head_hash"], second_status["head_hash"])
        self.assertEqual(second_status["row_count"], 2)

    def test_context_pack_is_reproducible_bounded_and_verifiable(self) -> None:
        self.append(artifact("alpha planning decision", "one"))
        self.append(artifact("beta implementation decision", "two"))
        first = self.root / "first.pack.json"
        second = self.root / "second.pack.json"
        arguments = (self.journal, first, "decision", 20, "pack-run", "WO-019", "fixture.gguf")
        pack = memory_pack.build(*arguments)
        memory_pack.build(self.journal, second, "decision", 20, "pack-run", "WO-019", "fixture.gguf")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertLessEqual(pack["budget"]["measured_tokens"], 20)
        self.assertEqual(2, len(pack["records"]))
        self.assertTrue(all(record["epistemic_class"] == "record" for record in pack["records"]))
        self.assertTrue(all("actor" in record["excerpt"] for record in pack["records"]))
        self.assertEqual("valid", memory_pack.verify(first)["state"])
        self.assertEqual(2, memory_pack.inspect(first)["records"])
        checkpoint_path = self.root / "pack-bound.checkpoint.json"
        binding = checkpoint.bind(self.journal, checkpoint_path, "pack-bound", context_pack=first)
        self.assertEqual(pack["pack_sha256"], binding["binding"]["context_pack_hash"])

    def test_tombstone_removes_content_from_new_index_and_pack(self) -> None:
        result = self.append(artifact("private-redaction-sentinel decision", "secret"))
        target_id = result["event"]["event_id"]
        self.append_tombstone(target_id)
        database = self.root / "redacted.sqlite3"
        memory_index.build(self.journal, database)
        self.assertEqual([], memory_index.query(database, "private-redaction-sentinel"))
        self.assertNotIn(b"private-redaction-sentinel", database.read_bytes())
        output = self.root / "redacted.pack.json"
        pack = memory_pack.build(
            self.journal, output, "", 100, "redaction-run", "WO-019", "fixture.gguf", database=database
        )
        self.assertEqual([], pack["records"])
        reasons = {(item["sequence"], item["reason"]) for item in pack["exclusions"]}
        self.assertIn((1, "redacted"), reasons)
        self.assertIn((2, "tombstoned"), reasons)
        self.assertNotIn("private-redaction-sentinel", output.read_text(encoding="utf-8"))

    def test_quota_and_non_destructive_archive(self) -> None:
        self.append(artifact("archive fixture decision", "archive"))
        used = self.journal.stat().st_size
        self.assertEqual("within_quota", memory_retention.quota_status(self.journal, used)["state"])
        self.assertEqual("quota_exceeded", memory_retention.quota_status(self.journal, used - 1)["state"])
        source_before = self.journal.read_bytes()
        archive = self.root / "archive" / "memory.lmem"
        result = memory_retention.archive(self.journal, archive)
        self.assertTrue(result["ok"])
        self.assertEqual(source_before, self.journal.read_bytes())
        self.assertEqual(source_before, archive.read_bytes())
        self.assertEqual("valid", memory_retention.verify_archive(archive)["state"])
        damaged = bytearray(archive.read_bytes())
        damaged[-1] ^= 0x01
        archive.write_bytes(damaged)
        self.assertEqual("corrupt", memory_retention.verify_archive(archive)["state"])

    def test_checkpoint_exact_advanced_diverged_corrupt_and_missing(self) -> None:
        self.append(artifact("alpha checkpoint baseline", "one"))
        checkpoint_path = self.root / "run.checkpoint.json"
        checkpoint.bind(self.journal, checkpoint_path, "fixture")
        interrupted = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
        interrupted.terminate()
        interrupted.wait(timeout=5)
        self.assertEqual(checkpoint.verify(checkpoint_path)["state"], "exact")

        alternate = self.root / "alternate.lmem"
        alternate_payload = self.root / "alternate.json"
        alternate_payload.write_text(json.dumps(artifact("different baseline", "alternate")), encoding="utf-8")
        append_reflection(alternate, alternate_payload, "leafos-test")
        self.assertEqual(checkpoint.verify(checkpoint_path, alternate)["state"], "diverged")

        self.append(artifact("beta clean continuation", "two"))
        self.assertEqual(checkpoint.verify(checkpoint_path)["state"], "advanced")

        corrupt = self.root / "corrupt.lmem"
        damaged = bytearray(self.journal.read_bytes())
        damaged[len(damaged) // 2] ^= 0x01
        corrupt.write_bytes(damaged)
        self.assertEqual(checkpoint.verify(checkpoint_path, corrupt)["state"], "corrupt")
        self.assertEqual(checkpoint.verify(checkpoint_path, self.root / "missing.lmem")["state"], "missing")


if __name__ == "__main__":
    unittest.main()
