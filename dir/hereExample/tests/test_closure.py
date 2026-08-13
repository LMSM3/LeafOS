import unittest

from closure import classify


class ClosureTests(unittest.TestCase):
    def test_matching_known_values_are_confirmed(self):
        self.assertEqual(classify("20 frames", "20 frames"), "confirmed")

    def test_different_known_values_are_contradicted(self):
        self.assertEqual(classify("20 frames", "500 frames"), "contradicted")

    def test_missing_evidence_is_inconclusive(self):
        self.assertEqual(classify("20 frames", None), "inconclusive")
        self.assertEqual(classify(None, "20 frames"), "inconclusive")


if __name__ == "__main__":
    unittest.main()
