#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core" / "runtime"))

from model_profiles import ModelProfileError, load_profile, load_profiles, route_lane  # noqa: E402


class ModelProfileTests(unittest.TestCase):
    def test_registry_materializes_all_documented_profiles(self) -> None:
        profiles = load_profiles()
        documented = {
            "brain-primary-27b-nvfp4-mtp",
            "brain-primary-14b-gguf",
            "coder-primary-12b-fable",
            "helper-coder-fable-lowquant",
        }
        ids = {profile["profile_id"] for profile in profiles}
        self.assertTrue(documented.issubset(ids), f"missing documented profiles: {documented - ids}")
        self.assertGreaterEqual(len(ids), len(documented))

    def test_lane_routing_preserves_brain_and_coder_authority(self) -> None:
        profiles = load_profiles()
        patch = route_lane("slot.coder.patch", profiles)
        architecture = route_lane("slot.review.architecture", profiles)
        self.assertEqual(["coder-primary-12b-fable"], [item["profile_id"] for item in patch])
        self.assertEqual(["brain-primary-14b-gguf"], [item["profile_id"] for item in architecture])
        self.assertTrue(all(item["role"] != "helper" for item in patch))

    def test_invalid_profile_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrong-name.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "leafos.model-profile.v1",
                        "profile_id": "different-id",
                        "model_repo": "local/test",
                        "role": "coder",
                        "lanes": ["slot.coder.patch"],
                        "contracts": ["unified_diff"],
                        "runtime": ["llama.cpp"],
                        "status": "test",
                        "notes": ["fixture"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ModelProfileError):
                load_profile(path)

    def test_unknown_lane_fails_closed(self) -> None:
        with self.assertRaises(ModelProfileError):
            route_lane("slot.unknown", load_profiles())


if __name__ == "__main__":
    unittest.main()
