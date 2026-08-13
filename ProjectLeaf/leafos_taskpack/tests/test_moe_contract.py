from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "core" / "python"
sys.path.insert(0, str(PYTHON_DIR))

CONTRACT_SPEC = importlib.util.spec_from_file_location("leaf_moe_contract", PYTHON_DIR / "leaf_moe_contract.py")
leaf_moe_contract = importlib.util.module_from_spec(CONTRACT_SPEC)
CONTRACT_SPEC.loader.exec_module(leaf_moe_contract)

OVERNIGHT_SPEC = importlib.util.spec_from_file_location("leaf_overnight", PYTHON_DIR / "leaf_overnight.py")
leaf_overnight = importlib.util.module_from_spec(OVERNIGHT_SPEC)
OVERNIGHT_SPEC.loader.exec_module(leaf_overnight)

RUNTIME_SPEC = importlib.util.spec_from_file_location("leaf_runtime", PYTHON_DIR / "leaf_runtime.py")
leaf_runtime_module = importlib.util.module_from_spec(RUNTIME_SPEC)
RUNTIME_SPEC.loader.exec_module(leaf_runtime_module)


def load(name: str) -> dict:
    return json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))


def resolved_candidate() -> dict:
    candidate = load("medium_moe_candidate.template.json")
    candidate["status"] = "resolved"
    candidate["identity"] = {
        "model_id": "fixture-moe-72b-a8b",
        "source_repo": "local/fixture-moe",
        "revision": "fixture-revision",
        "artifact": "fixture-moe-Q4_K_M.gguf",
        "sha256": "a" * 64,
        "license": "fixture-only",
    }
    candidate["topology"] = {
        "total_parameters_billion": 72,
        "active_parameters_billion": 8,
        "expert_count": 64,
        "active_experts_per_token": 8,
    }
    candidate["runtime"].update(
        {
            "model_path": "C:/models/fixture-moe-Q4_K_M.gguf",
            "benchmark_command": [
                "llama-bench",
                "--model",
                "C:/models/fixture-moe-Q4_K_M.gguf",
            ],
            "context_tokens": 8192,
            "gpu_layers": 999,
        }
    )
    candidate["acceptance"] = {
        "minimum_generation_tokens_per_second": 1.0,
        "maximum_time_to_first_token_seconds": 60.0,
        "minimum_validated_useful_changes_per_hour": 0.0,
        "threshold_provenance": "Fixture thresholds fixed before the test run.",
    }
    return candidate


def measured_metrics(duration_minutes: int = 64, scenario: str = "resident_foreground") -> dict:
    return {
        "evidence_kind": "measured_local",
        "candidate_model_id": "fixture-moe-72b-a8b",
        "duration_minutes": duration_minutes,
        "scenario": scenario,
        "model_load_seconds": 10.0,
        "time_to_first_token_seconds": 2.0,
        "prompt_tokens_per_second": 40.0,
        "generation_tokens_per_second": 5.0,
        "gpu_process_alive_for_run": True,
        "provider_restarts": 0,
        "gpu_utilization_average_percent": 90.0,
        "gpu_vram_used_peak_percent": 90.0,
        "cpu_utilization_average_percent": 70.0,
        "ram_used_peak_percent": 90.0,
        "foreground_responsiveness_p95_ms": 150.0,
        "nvme_read_megabytes_per_second": 100.0,
        "major_page_faults": 0,
        "minor_page_faults": 10,
        "validated_patches": 1,
        "accepted_changes": 1,
        "rejected_changes": 0,
        "baseline_validation_passed": True,
        "oom_events": 0,
        "availability": {},
    }


class MediumMoeContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load("medium_moe_policy.json")

    def test_runtime_exposes_unresolved_moe_without_changing_active_route(self) -> None:
        selector = leaf_runtime_module.LeafRuntimeSelector(ROOT)
        status = selector.medium_moe_status()
        self.assertEqual("incumbent", status["active_route"])
        self.assertFalse(status["automatic_promotion"])
        self.assertEqual("template", status["candidate_status"])
        self.assertFalse(status["candidate_ready"])
        self.assertEqual([], status["candidate_errors"])

    def test_runtime_selection_includes_medium_moe_status(self) -> None:
        selection = leaf_runtime_module.LeafRuntimeSelector(ROOT).select()
        self.assertEqual("incumbent", selection["selection"]["medium_moe"]["active_route"])

    def test_policy_and_unresolved_template_are_valid_but_not_ready(self) -> None:
        template = load("medium_moe_candidate.template.json")
        self.assertEqual([], leaf_moe_contract.validate_policy(self.policy))
        self.assertEqual([], leaf_moe_contract.validate_candidate(template, self.policy))
        errors = leaf_moe_contract.validate_candidate(template, self.policy, require_resolved=True)
        self.assertIn("candidate status must be resolved", "\n".join(errors))

    def test_resolved_candidate_requires_full_identity_topology_and_thresholds(self) -> None:
        self.assertEqual([], leaf_moe_contract.validate_candidate(resolved_candidate(), self.policy, require_resolved=True))

    def test_candidate_outside_operator_parameter_band_is_rejected(self) -> None:
        candidate = resolved_candidate()
        candidate["topology"]["total_parameters_billion"] = 200
        errors = leaf_moe_contract.validate_candidate(candidate, self.policy, require_resolved=True)
        self.assertIn("47-156", "\n".join(errors))

    def test_active_topology_cannot_exceed_total_model_size(self) -> None:
        candidate = resolved_candidate()
        candidate["topology"]["active_parameters_billion"] = 80
        errors = leaf_moe_contract.validate_candidate(candidate, self.policy, require_resolved=True)
        self.assertIn("no greater than total", "\n".join(errors))

    def test_malformed_candidate_returns_contract_errors_instead_of_crashing(self) -> None:
        errors = leaf_moe_contract.validate_candidate(
            {"schema": "leafos.medium-moe-candidate.v1", "policy_id": self.policy["policy_id"]},
            self.policy,
        )
        self.assertIn("status must be template or resolved", errors)
        self.assertIn("identity must be an object", errors)

    def test_deprecated_glm_model_cannot_be_resolved(self) -> None:
        candidate = resolved_candidate()
        candidate["identity"]["model_id"] = "GLM-5.2"
        errors = leaf_moe_contract.validate_candidate(candidate, self.policy, require_resolved=True)
        self.assertIn("deprecated", "\n".join(errors))

    def test_contract_does_not_claim_leafos_managed_ssd_tiering(self) -> None:
        policy = copy.deepcopy(self.policy)
        policy["placement"]["leafos_managed_ssd_tiering"] = True
        errors = leaf_moe_contract.validate_policy(policy)
        self.assertIn("leafos_managed_ssd_tiering", "\n".join(errors))

    def test_manifest_preserves_mmap_and_operator_approval_truth(self) -> None:
        manifest = leaf_overnight.build_manifest(
            resolved_candidate(), self.policy, "leafos", "resident_foreground", 64
        )
        self.assertFalse(manifest["placement_truth"]["leafos_managed_ssd_tiering"])
        self.assertFalse(manifest["safety"]["automatic_promotion"])
        self.assertTrue(manifest["safety"]["operator_approval_required"])

    def test_single_measured_run_qualifies_only_for_the_portfolio(self) -> None:
        report, errors = leaf_overnight.evaluate_metrics(
            resolved_candidate(),
            self.policy,
            measured_metrics(),
            "leafos",
            "resident_foreground",
            64,
        )
        self.assertEqual([], errors)
        self.assertTrue(report["benchmark_passed"])
        self.assertTrue(report["run_qualifies_for_portfolio"])
        self.assertFalse(report["promotion_eligible"])
        self.assertFalse(report["automatic_promotion"])

    def test_promotion_eligibility_requires_all_three_policy_runs(self) -> None:
        candidate = resolved_candidate()
        reports = []
        for duration, scenario in ((4, "cold_cache"), (8, "warm_cache"), (64, "resident_foreground")):
            report, errors = leaf_overnight.evaluate_metrics(
                candidate,
                self.policy,
                measured_metrics(duration, scenario),
                "leafos",
                scenario,
                duration,
            )
            self.assertEqual([], errors)
            reports.append(report)

        incomplete, errors = leaf_overnight.qualify_reports(candidate, self.policy, reports[-1:])
        self.assertEqual([], errors)
        self.assertFalse(incomplete["promotion_eligible"])

        qualification, errors = leaf_overnight.qualify_reports(candidate, self.policy, reports)
        self.assertEqual([], errors)
        self.assertTrue(qualification["all_required_runs_passed"])
        self.assertTrue(qualification["promotion_eligible"])
        self.assertTrue(qualification["operator_approval_required"])
        self.assertFalse(qualification["automatic_promotion"])

    def test_gpu_process_death_fails_the_benchmark_gate(self) -> None:
        metrics = measured_metrics()
        metrics["gpu_process_alive_for_run"] = False
        metrics["provider_restarts"] = 1
        report, errors = leaf_overnight.evaluate_metrics(
            resolved_candidate(),
            self.policy,
            metrics,
            "leafos",
            "resident_foreground",
            64,
        )
        self.assertEqual([], errors)
        self.assertFalse(report["benchmark_passed"])
        self.assertFalse(report["gate_results"]["provider_survived"])

    def test_null_metrics_need_field_specific_availability_reasons(self) -> None:
        metrics = measured_metrics()
        metrics["nvme_read_megabytes_per_second"] = None
        _report, errors = leaf_overnight.evaluate_metrics(
            resolved_candidate(),
            self.policy,
            metrics,
            "leafos",
            "resident_foreground",
            64,
        )
        self.assertIn("field-specific availability reasons", "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
