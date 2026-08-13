import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "python"))
SANDBOX = ROOT / "sandbox" / "overnight-01"

import leaf_sandbox


@unittest.skipUnless(
    (SANDBOX / "manifest.json").is_file(),
    "historical overnight sandbox fixture is not included in the reusable source snapshot",
)
class OvernightSandboxTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = SANDBOX
        self.manifest = leaf_sandbox.load_manifest(self.sandbox)

    def test_schedule_is_sequential_and_bounded(self):
        assignments = leaf_sandbox.task_order(self.sandbox)
        self.assertEqual(6, len(assignments))
        self.assertEqual(list(range(1, 7)), [item["sequence"] for item in assignments])
        self.assertTrue(all(item["budget_minutes"] == 182 for item in assignments))
        self.assertEqual(1092, sum(item["budget_minutes"] for item in assignments))
        self.assertEqual(1572, self.manifest["nominal_duration_minutes"])

    def test_transition_timing_is_explicit(self):
        transition = self.manifest["transition"]
        self.assertEqual(60, transition["cleanup_seconds"])
        self.assertEqual(20, transition["loading_animation_seconds"])
        self.assertEqual(5, transition["between_task_count"])
        self.assertTrue(transition["loading_animation_is_model_free"])

    def test_work_orders_and_sources_exist(self):
        for entry in leaf_sandbox.project_entries(self.manifest):
            self.assertTrue((self.sandbox / entry["work_order"]).is_file())
            self.assertTrue((self.sandbox / entry["source"]).resolve().is_dir())

    def test_checkpoint_policy_prevents_unbounded_work(self):
        policy = self.manifest["checkpoint_policy"]
        self.assertEqual(30, policy["first_validated_checkpoint_due_minutes"])
        self.assertTrue(policy["stop_if_checkpoint_missing"])
        self.assertEqual("unproductive_no_validated_checkpoint", policy["stop_reason"])


if __name__ == "__main__":
    unittest.main()
