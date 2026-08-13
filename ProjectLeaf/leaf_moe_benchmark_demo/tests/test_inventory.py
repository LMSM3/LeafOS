import json
import os
import tempfile
import unittest
from pathlib import Path

from gguf_fixture import STRING, qwen_metadata, write_fake_gguf
from leaf_moe_bench.inventory import build_inventory


class InventoryTests(unittest.TestCase):
    def _catalog(self, root: Path) -> Path:
        path = root / "model_catalog.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "catalog_version": "test",
                    "models": [
                        {
                            "slot": 4,
                            "key": "reasoner",
                            "title": "Qwen Demo 14B A3B",
                            "repo_id": "example/reasoner-14b-a3b",
                            "local_dir": "Reasoner",
                            "role": "critic",
                            "experimental": False,
                            "variants": {
                                "MOE": {
                                    "format": "gguf",
                                    "patterns": ["*MOE.gguf"]
                                }
                            }
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_name_disagreement_is_advisory_without_tensor_count(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            models = root / "models"
            model = models / "Reasoner" / "Qwen-Demo-14B-A3B-MOE.gguf"
            write_fake_gguf(model, qwen_metadata("Qwen Demo 35B A3B"))
            inventory = build_inventory(models, self._catalog(root), hash_mode="none")
            artifact = inventory["artifacts"][0]
            codes = [item["code"] for item in artifact["identity_findings"]]
            self.assertIn("metadata_name_parameter_label_disagreement", codes)
            self.assertNotIn("metadata_name_parameter_label_disagreement", artifact["benchmark_admission"]["blockers"])
            self.assertIn("content_sha256_missing", artifact["benchmark_admission"]["blockers"])
            self.assertFalse(artifact["benchmark_admission"]["eligible"])
            self.assertEqual(artifact["model"]["artifact_kind"], "language_model")

    def test_tensor_count_resolves_catalog_label_and_keeps_name_disagreement_advisory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            models = root / "models"
            model = models / "Reasoner" / "Qwen-Demo-14B-A3B-MOE.gguf"
            write_fake_gguf(
                model,
                qwen_metadata("Qwen Demo 35B A3B"),
                tensors=[("model", (14_137_111_168,), 1, 0)],
            )
            inventory = build_inventory(models, self._catalog(root), hash_mode="sha256")
            artifact = inventory["artifacts"][0]
            codes = [item["code"] for item in artifact["identity_findings"]]
            self.assertEqual(artifact["model"]["parameter_count"], 14_137_111_168)
            self.assertIn("metadata_name_parameter_label_disagreement", codes)
            self.assertNotIn("catalog_tensor_parameter_count_mismatch", codes)
            self.assertTrue(artifact["benchmark_admission"]["eligible"])

    def test_tensor_count_mismatch_blocks_catalog_admission(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            models = root / "models"
            model = models / "Reasoner" / "Qwen-Demo-14B-A3B-MOE.gguf"
            write_fake_gguf(
                model,
                qwen_metadata("Qwen Demo 35B A3B"),
                tensors=[("model", (35_000_000_000,), 1, 0)],
            )
            inventory = build_inventory(models, self._catalog(root), hash_mode="sha256")
            artifact = inventory["artifacts"][0]
            codes = [item["code"] for item in artifact["identity_findings"]]
            self.assertIn("catalog_tensor_parameter_count_mismatch", codes)
            self.assertIn("catalog_tensor_parameter_count_mismatch", artifact["benchmark_admission"]["blockers"])
            self.assertFalse(artifact["benchmark_admission"]["eligible"])

    def test_classifies_clip_artifact_as_projector(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            models = root / "models"
            projector = models / "Other" / "mmproj.gguf"
            write_fake_gguf(
                projector,
                [
                    ("general.name", STRING, "Vision projector"),
                    ("general.architecture", STRING, "clip"),
                ],
            )
            inventory = build_inventory(models, self._catalog(root), hash_mode="none")
            self.assertEqual(inventory["artifacts"][0]["model"]["artifact_kind"], "projector")

    def test_full_hash_can_clear_the_missing_hash_blocker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            models = root / "models"
            model = models / "Reasoner" / "Qwen-Demo-14B-A3B-MOE.gguf"
            write_fake_gguf(model, qwen_metadata("Qwen Demo 14B A3B"))
            inventory = build_inventory(models, self._catalog(root), hash_mode="sha256")
            artifact = inventory["artifacts"][0]
            self.assertTrue(artifact["artifact_id"].startswith("sha256:"))
            self.assertTrue(artifact["benchmark_admission"]["eligible"])
            self.assertEqual(artifact["benchmark_admission"]["blockers"], [])

    def test_no_hash_inventory_identity_changes_when_file_stat_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            models = root / "models"
            model = models / "Reasoner" / "Qwen-Demo-14B-A3B-MOE.gguf"
            write_fake_gguf(model, qwen_metadata("Qwen Demo 14B A3B"))
            catalog = self._catalog(root)
            first = build_inventory(models, catalog, hash_mode="none")
            stat = model.stat()
            os.utime(model, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
            second = build_inventory(models, catalog, hash_mode="none")
            self.assertNotEqual(first["inventory_id"], second["inventory_id"])
            self.assertNotEqual(first["artifacts"][0]["artifact_id"], second["artifacts"][0]["artifact_id"])


if __name__ == "__main__":
    unittest.main()
