import unittest

from leaf_models.catalog import MODEL_CATALOG


class CatalogTests(unittest.TestCase):
    def test_slots_are_unique_and_ordered(self):
        slots = [model.slot for model in MODEL_CATALOG.models]
        self.assertEqual(slots, sorted(set(slots)))
        self.assertEqual(slots, list(range(1, len(slots) + 1)))

    def test_default_profile_is_fable_coder_and_opus_main_scheduler(self):
        self.assertEqual(MODEL_CATALOG.profiles["default"]["slots"], [1, 3])

    def test_runtime_default_profile_boots_main_and_coder(self):
        self.assertEqual(MODEL_CATALOG.profiles["runtime-default"]["slots"], [1, 3])

    def test_legacy_coder_pair_is_explicit_not_default(self):
        self.assertEqual(MODEL_CATALOG.profiles["legacy-coder-pair"]["slots"], [1, 2])

    def test_no_model_uses_blanket_gguf_wildcard(self):
        for model in MODEL_CATALOG.models:
            for variant in model.variants.values():
                self.assertNotIn("*.gguf", variant.patterns)

    def test_heavyweight_is_experimental_and_not_default(self):
        model = MODEL_CATALOG.by_slot()[5]
        self.assertTrue(model.experimental)
        self.assertNotIn(5, MODEL_CATALOG.profiles["default"]["slots"])
        self.assertNotIn(5, MODEL_CATALOG.profiles["extended"]["slots"])

    def test_reasoning_fallback_is_explicit(self):
        model = MODEL_CATALOG.by_slot()[4]
        self.assertEqual(model.default_quant, "Q4_K_M")
        self.assertIn("MXFP4_MOE", model.fallback_quants)


if __name__ == "__main__":
    unittest.main()
