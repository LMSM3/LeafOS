import unittest

from floweros_hwmon.sensors import SensorCollector


class SnapshotTests(unittest.TestCase):
    def test_snapshot_contains_core_sections(self):
        collector = SensorCollector(include_external=False)
        snapshot = collector.sample()
        self.assertIn("cpu", snapshot)
        self.assertIn("memory", snapshot)
        self.assertIn("disks", snapshot)
        self.assertIn("network", snapshot)
        self.assertIn("fans", snapshot)
        self.assertTrue(snapshot["fans"], "fan list should include real data or an estimate")


if __name__ == "__main__":
    unittest.main()
