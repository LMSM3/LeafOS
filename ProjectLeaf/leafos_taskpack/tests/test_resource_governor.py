import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "python"))

import leaf_resource_governor as governor


def sample(cpu=30.0, gpu=50.0, ram=(12.0, 32.0), vram=(6.0, 12.0), temperature=60.0):
    return {
        "hardware": {
            "cpu": {"utilization_percent": cpu},
            "gpu": {
                "utilization_percent": gpu,
                "vram_used_gb": vram[0],
                "vram_total_gb": vram[1],
                "temperature_celsius": temperature,
            },
            "memory": {"ram_used_gb": ram[0], "ram_total_gb": ram[1]},
        }
    }


class ResourceGovernorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = governor.load_policy()

    def test_default_policy_targets_requested_idle_utilization(self):
        decision = governor.decide(
            self.policy, sample(),
            {"queue_ready": 2, "queue_active": 0, "input_idle_seconds": 120, "provider_health": "ready"},
            now_monotonic=10,
        )
        self.assertEqual("auto-idle", decision["profile"])
        self.assertEqual({"cpu_percent": 80.0, "gpu_percent": 90.0}, decision["targets"])
        self.assertTrue(decision["claim_allowed"])

    def test_recent_input_reserves_foreground_headroom(self):
        decision = governor.decide(
            self.policy, sample(cpu=75, gpu=88),
            {"queue_ready": 3, "input_idle_seconds": 1, "provider_health": "ready"},
            now_monotonic=10,
        )
        self.assertEqual("auto-interactive", decision["profile"])
        self.assertEqual("recent_operator_input", decision["reason"])
        self.assertLess(decision["targets"]["cpu_percent"], 80)
        self.assertLess(decision["targets"]["gpu_percent"], 90)

    def test_idle_recovery_ramps_targets_instead_of_jumping(self):
        decision = governor.decide(
            self.policy, sample(),
            {"queue_ready": 3, "input_idle_seconds": 18, "provider_health": "ready"},
            now_monotonic=10,
        )
        self.assertEqual("auto-ramp", decision["profile"])
        self.assertEqual("idle_ramp", decision["reason"])
        self.assertGreater(decision["targets"]["cpu_percent"], 60)
        self.assertLess(decision["targets"]["cpu_percent"], 80)

    def test_hard_pressure_closes_claim_gate(self):
        decision = governor.decide(
            self.policy, sample(ram=(31.7, 32)),
            {"queue_ready": 3, "input_idle_seconds": 90, "provider_health": "ready"},
            now_monotonic=10,
        )
        self.assertEqual("pressure", decision["profile"])
        self.assertEqual("ram_pressure", decision["reason"])
        self.assertFalse(decision["claim_allowed"])
        self.assertEqual(0, decision["cpu_slots"])

    def test_missing_counters_remain_unknown_and_do_not_become_zero(self):
        decision = governor.decide(
            self.policy, {"hardware": {}},
            {"queue_ready": 1, "input_idle_seconds": None, "provider_health": "ready"},
            now_monotonic=10,
        )
        self.assertIsNone(decision["current"]["cpu_percent"])
        self.assertIsNone(decision["current"]["gpu_percent"])
        self.assertTrue(decision["claim_allowed"])

    def test_hysteresis_and_cooldown_prevent_worker_churn(self):
        first = governor.decide(
            self.policy, sample(cpu=10, gpu=20),
            {"queue_ready": 2, "input_idle_seconds": 60, "provider_health": "ready"},
            {"cpu_slots": 1, "changed_monotonic": 0}, now_monotonic=10,
        )
        self.assertEqual(2, first["cpu_slots"])
        second = governor.decide(
            self.policy, sample(cpu=99, gpu=99),
            {"queue_ready": 2, "input_idle_seconds": 60, "provider_health": "ready"},
            first, now_monotonic=11,
        )
        self.assertEqual(first["cpu_slots"], second["cpu_slots"])
        self.assertEqual(first["provider_delay_seconds"], second["provider_delay_seconds"])

    def test_provider_failure_is_explicit_for_gpu_work(self):
        decision = governor.decide(
            self.policy, sample(),
            {"queue_ready": 1, "gpu_needed": True, "input_idle_seconds": 60, "provider_health": "unavailable"},
            now_monotonic=10,
        )
        self.assertEqual("provider_unavailable", decision["reason"])
        self.assertFalse(decision["claim_allowed"])

    def test_schema_and_runtime_policy_are_valid_json(self):
        schema = json.loads((ROOT / "schemas" / "leafos.resource-policy.v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual("LeafOS Resident Stack Resource Policy", schema["title"])
        self.assertEqual(governor.POLICY_OBJECT, self.policy["leafos_object"])


if __name__ == "__main__":
    unittest.main()
