import unittest

from leaf_moe_bench.plan import build_plan


def artifact(path, kind="language_model", experts=93, blocks=40, blockers=None):
    return {
        "artifact_id": "unverified:" + path,
        "relative_path": path,
        "absolute_path": "C:/models/" + path,
        "bytes": 1234,
        "modified_at_ns": 5678,
        "content_sha256": None,
        "metadata_sha256": "b" * 64,
        "gguf": {"valid": True},
        "model": {
            "artifact_kind": kind,
            "architecture": "qwen35moe" if experts else "dense",
            "expert_count": experts,
            "block_count": blocks,
        },
        "catalog_matches": [],
        "benchmark_admission": {"eligible": False, "blockers": blockers or ["content_sha256_missing"]},
    }


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.inventory = {
            "schema": "leafos.moe.inventory/0.1",
            "inventory_id": "inventory:test",
            "artifacts": [artifact("reasoner.gguf"), artifact("projector.gguf", kind="projector", experts=None)],
        }
        self.provider = {
            "schema": "leafos.moe.provider-probe/0.1",
            "executable": "C:/bin/llama-bench.exe",
            "executable_sha256": "a" * 64,
            "usable": True,
            "gpu_available": False,
            "capabilities": {"n_cpu_moe": True, "device": True, "no_op_offload": True},
        }
        self.matrix = {
            "schema": "leafos.moe.benchmark-matrix/0.1",
            "matrix_id": "test",
            "workloads": [{"id": "small", "prompt_tokens": 32, "generation_tokens": 8}],
            "placements": [
                {
                    "id": "cpu-strict-16t",
                    "applies_to": "all",
                    "requires_gpu": False,
                    "args": {
                        "threads": 2,
                        "n_gpu_layers": 0,
                        "device": "none",
                        "no_op_offload": True,
                    },
                },
                {
                    "id": "moe-half",
                    "applies_to": "moe",
                    "requires_gpu": True,
                    "args": {"threads": 2, "n_gpu_layers": 99, "n_cpu_moe": "half"},
                },
            ],
        }

    def test_skips_projector_and_marks_missing_gpu(self):
        plan = build_plan(self.inventory, self.provider, self.matrix)
        self.assertEqual(plan["entry_count"], 2)
        by_placement = {item["placement_id"]: item for item in plan["entries"]}
        self.assertTrue(by_placement["cpu-strict-16t"]["ready"])
        self.assertFalse(by_placement["moe-half"]["ready"])
        self.assertIn("provider_has_no_gpu_device", by_placement["moe-half"]["execution_blockers"])
        self.assertIn(
            "statistical_promotion_analysis_missing",
            by_placement["cpu-strict-16t"]["promotion_blockers"],
        )
        cpu_command = by_placement["cpu-strict-16t"]["command"]
        self.assertEqual(cpu_command[cpu_command.index("--device") + 1], "none")
        self.assertEqual(cpu_command[cpu_command.index("--no-op-offload") + 1], "1")
        command = by_placement["moe-half"]["command"]
        self.assertEqual(command[command.index("--n-cpu-moe") + 1], "20")

    def test_plan_identity_is_stable(self):
        first = build_plan(self.inventory, self.provider, self.matrix)
        second = build_plan(self.inventory, self.provider, self.matrix)
        self.assertEqual(first["plan_id"], second["plan_id"])

    def test_strict_cpu_is_blocked_without_both_isolation_capabilities(self):
        self.provider["capabilities"] = {"n_cpu_moe": True}
        plan = build_plan(self.inventory, self.provider, self.matrix)
        strict = next(item for item in plan["entries"] if item["placement_id"] == "cpu-strict-16t")
        self.assertFalse(strict["ready"])
        self.assertIn("provider_lacks_device_selection", strict["execution_blockers"])
        self.assertIn("provider_lacks_no_op_offload", strict["execution_blockers"])

    def test_legacy_and_tensor_identity_blockers_both_require_override(self):
        for blocker in (
            "catalog_metadata_parameter_label_mismatch",
            "catalog_tensor_parameter_count_mismatch",
        ):
            with self.subTest(blocker=blocker):
                self.inventory["artifacts"][0]["benchmark_admission"] = {
                    "eligible": False,
                    "blockers": [blocker],
                }
                plan = build_plan(self.inventory, self.provider, self.matrix)
                self.assertTrue(all(item["requires_experimental_identity_override"] for item in plan["entries"]))


if __name__ == "__main__":
    unittest.main()
