from __future__ import annotations

import os
import sys
import types
import unittest
from unittest.mock import patch

try:
    import huggingface_hub  # noqa: F401
except ModuleNotFoundError:
    sys.modules["huggingface_hub"] = types.SimpleNamespace(
        HfApi=object,
        hf_hub_url=lambda repo_id, filename, revision: f"https://example.invalid/{repo_id}/{revision}/{filename}",
        snapshot_download=lambda **kwargs: kwargs,
    )

from leaf_models.catalog import get_model
from leaf_models.downloader import DownloadError, benchmark_download, benchmark_to_dict, enable_fast_transfer


class FakeResponse:
    status_code = 200
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def raise_for_status(self):
        return None

    def iter_bytes(self, chunk_size):
        del chunk_size
        yield b"x" * 11
        yield b"y" * 11


class FakeClient:
    def __init__(self, **_):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def stream(self, *_args, **_kwargs):
        return FakeResponse()


class DownloaderBenchmarkTests(unittest.TestCase):
    def test_fast_transfer_sets_current_transport_flag(self):
        os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
        enable_fast_transfer(True)
        self.assertEqual("1", os.environ["HF_XET_HIGH_PERFORMANCE"])
        self.assertNotIn("HF_HUB_ENABLE_HF_TRANSFER", os.environ)

    def test_benchmark_never_counts_more_than_requested(self):
        fake_httpx = types.SimpleNamespace(Client=FakeClient)
        model = get_model("gemma4-coder")
        with patch("leaf_models.downloader.list_matching_files", return_value=["fixture.gguf"]), \
             patch("leaf_models.downloader.hf_hub_url", return_value="https://example.invalid/model"), \
             patch.dict(sys.modules, {"httpx": fake_httpx}):
            result = benchmark_download(model, ["*.gguf"], sample_bytes=16, high_performance=False)
        self.assertEqual(16, result.sampled_bytes)
        self.assertEqual(16, result.requested_bytes)
        self.assertFalse(result.range_honored)
        payload = benchmark_to_dict(result)
        self.assertEqual("leafos.model-download-benchmark.v1", payload["schema"])
        self.assertEqual(200, payload["http_status"])

    def test_invalid_sample_is_rejected_before_network(self):
        with self.assertRaises(DownloadError):
            benchmark_download(get_model("gemma4-coder"), ["*.gguf"], sample_bytes=0)

    def test_missing_remote_match_is_clear_failure(self):
        with patch("leaf_models.downloader.list_matching_files", return_value=[]):
            with self.assertRaisesRegex(DownloadError, "Nothing to benchmark"):
                benchmark_download(get_model("gemma4-coder"), ["*.gguf"], sample_bytes=8)


if __name__ == "__main__":
    unittest.main()
