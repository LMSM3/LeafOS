import unittest
from pathlib import Path

from leaf_models.orchestrator import OrchestrationError, create_plan, plan_to_dict


class PlanTests(unittest.TestCase):
    def test_default_plan_is_offline_and_nonexperimental(self):
        plan = create_plan(profile="default", destination_root=Path("models"))
        self.assertFalse(plan.resolved)
        self.assertEqual([item.slot for item in plan.items], [1, 3])
        self.assertFalse(any(item.experimental for item in plan.items))

    def test_quant_override(self):
        plan = create_plan(
            profile="default",
            quant_overrides=["3=Q2_K"],
            destination_root=Path("models"),
        )
        self.assertEqual(plan.items[1].selected_quant, "Q2_K")

    def test_unselected_override_is_rejected(self):
        with self.assertRaises(OrchestrationError):
            create_plan(profile="default", quant_overrides=["2=Q3_K_M"])

    def test_plan_serializes_to_expected_shape(self):
        plan = create_plan(profile="extended", destination_root=Path("models"))
        payload = plan_to_dict(plan)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual([item["slot"] for item in payload["items"]], [1, 3, 4])


if __name__ == "__main__":
    unittest.main()
