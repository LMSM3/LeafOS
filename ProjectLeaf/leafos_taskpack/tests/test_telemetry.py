import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "python"))

import leaf_telemetry


class TelemetryTests(unittest.TestCase):
    def test_fast_hardware_collection_skips_io_probe(self):
        gpu = {
            **leaf_telemetry._empty_hardware()["gpu"],
            "utilization_percent": 82.0,
            "power_watts": 135.0,
        }
        cpu_patch = "_cpu_sample_windows" if leaf_telemetry.platform.system() == "Windows" else "_cpu_sample_posix"
        with (
            mock.patch.object(leaf_telemetry, cpu_patch, return_value=(25.0, 3.0, "collected")),
            mock.patch.object(leaf_telemetry, "_memory_sample", return_value=(10.0, 32.0, "collected")),
            mock.patch.object(leaf_telemetry, "_gpu_sample", return_value=(gpu, {"gpu_counters": "collected"})),
            mock.patch.object(leaf_telemetry, "_io_sample") as io_sample,
        ):
            result = leaf_telemetry.collect_fast_hardware()

        io_sample.assert_not_called()
        self.assertEqual(82.0, result["hardware"]["gpu"]["utilization_percent"])
        self.assertEqual(25.0, result["hardware"]["cpu"]["utilization_percent"])
        self.assertEqual("not_collected", result["availability"]["io_counters"])

    def test_event_validation_requires_core_fields(self):
        errors = leaf_telemetry.validate_event({"schema_version": 1})
        self.assertIn("missing event_id", errors)
        self.assertIn("missing metrics", errors)

    def test_append_and_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "telemetry.jsonl"
            event = leaf_telemetry.make_event(
                "overnight-01",
                "coding-cli",
                "sample",
                {"generation_tokens_per_second": 0.4, "checkpoint_valid": True},
            )
            leaf_telemetry.append_event(log, event)
            summary = leaf_telemetry.summarize(leaf_telemetry.read_events(log))
            self.assertEqual(1, summary["event_count"])
            self.assertEqual(1, summary["valid_checkpoint_count"])
            self.assertEqual(0.4, summary["generation_rate"]["average"])

    def test_tensor_event_preserves_optional_metadata(self):
        tensor = {
            "name": "blk.0.attn_q",
            "shape": [8, 128, 4096],
            "dtype": "q4_k",
            "placement": "gpu",
            "bytes": 1048576,
            "transfer_bytes": 1048576,
            "transfer_seconds": 0.002,
            "expert_id": 3,
            "layer": 0,
        }
        event = leaf_telemetry.tensor_event("overnight-01", "game-chess", tensor)
        self.assertEqual("tensor_snapshot", event["event_type"])
        self.assertEqual("gpu", event["tensor"]["placement"])
        self.assertEqual(3, event["tensor"]["expert_id"])

    def test_invalid_tensor_event_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                leaf_telemetry.append_event(
                    Path(directory) / "telemetry.jsonl",
                    leaf_telemetry.make_event(
                        "overnight-01", "coding-cli", "tensor_snapshot", {}, tensor={"name": "incomplete"}
                    ),
                )

    def test_universal_run_log_artifacts_define_operator_columns(self):
        schema = json.loads((ROOT / "schemas" / "leafos.universal-run-log.v1.schema.json").read_text(encoding="utf-8"))
        sample = json.loads((ROOT / "config" / "universal_run_log.sample.json").read_text(encoding="utf-8"))
        columns = json.loads((ROOT / "config" / "universal_run_log.columns.json").read_text(encoding="utf-8"))

        self.assertEqual("leafos.universal_run_log.event", sample["leafos_object"])
        self.assertEqual("LeafOS Universal Run Log Event", schema["title"])
        keys = {item["key"] for item in columns["primary_columns"]}
        for key in {
            "instances_initiated",
            "instances_alive",
            "brain_tk_s",
            "coder_tk_s",
            "gpu_percent",
            "cpu_percent",
        }:
            self.assertIn(key, keys)
        self.assertIn("gpu_starved", {item["key"] for item in columns["derived_columns"]})

    def test_universal_event_is_null_safe_and_ordered(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / leaf_telemetry.UNIVERSAL_LOG_NAME
            first = leaf_telemetry.make_universal_event(
                "run-01", "manual", collect_hardware=False,
            )
            second = leaf_telemetry.make_universal_event(
                "run-01", "manual", sequence=99, collect_hardware=False,
            )
            leaf_telemetry.append_universal_event(log, first)
            written = leaf_telemetry.append_universal_event(log, second)
            events = leaf_telemetry.read_universal_events(log)

            self.assertEqual(2, written["sequence"])
            self.assertEqual([1, 2], [event["sequence"] for event in events])
            self.assertEqual("not_collected", events[0]["availability"]["gpu_counters"])
            self.assertIsNone(events[0]["hardware"]["gpu"]["utilization_percent"])
            self.assertEqual(0, events[0]["instances"]["initiated"])
            self.assertEqual(0, events[0]["instances"]["alive"])
            self.assertEqual(10.0, events[0]["economics"]["comparison_output_usd_per_million"])

    def test_historical_universal_event_without_economics_remains_readable(self):
        event = leaf_telemetry.make_universal_event("historical", "manual", collect_hardware=False)
        event.pop("economics")
        self.assertEqual([], leaf_telemetry.validate_universal_event(event))

    def test_universal_summary_sums_only_interval_token_value(self):
        events = []
        for index, scope in enumerate(("interval", "interval", "cumulative"), 1):
            event = leaf_telemetry.make_universal_event(
                "economics", "manual", sequence=index, collect_hardware=False,
                economics=leaf_telemetry.economics_for_tokens(100, scope=scope),
            )
            events.append(event)
        summary = leaf_telemetry.summarize_universal_log(events)
        self.assertEqual(200, summary["economics"]["generated_tokens"])
        self.assertEqual(0.002, summary["economics"]["gross_cloud_equivalent_usd"])

    def test_universal_summary_flags_underuse(self):
        events = []
        for index in range(3):
            event = leaf_telemetry.make_universal_event(
                "run-underuse",
                "manual",
                sequence=index + 1,
                instances={
                    "initiated": 2, "alive": 2, "brain_initiated": 1, "brain_alive": 1,
                    "coder_initiated": 1, "coder_alive": 1, "provider_initiated": 0,
                    "provider_alive": 0, "crashed": 0, "restarted": 0,
                },
                throughput={
                    "brain_prompt_tk_s": None, "brain_generation_tk_s": 12.0,
                    "coder_prompt_tk_s": None, "coder_generation_tk_s": 0.0,
                    "helper_generation_tk_s": None, "aggregate_generation_tk_s": 12.0,
                    "time_to_first_token_seconds": None, "prompt_tokens": None, "generated_tokens": None,
                },
                hardware={
                    **leaf_telemetry._empty_hardware(),
                    "cpu": {**leaf_telemetry._empty_hardware()["cpu"], "utilization_percent": 91.0},
                    "gpu": {**leaf_telemetry._empty_hardware()["gpu"], "utilization_percent": 20.0},
                },
                collect_hardware=False,
            )
            self.assertEqual("collected", event["availability"]["throughput_counters"])
            events.append(event)
        summary = leaf_telemetry.summarize_universal_log(events)
        self.assertTrue(summary["warnings"]["gpu_starved"])
        self.assertTrue(summary["warnings"]["cpu_bound"])
        self.assertTrue(summary["warnings"]["coder_idle"])
        self.assertFalse(summary["warnings"]["brain_idle"])


if __name__ == "__main__":
    unittest.main()
