import tempfile
import unittest
from pathlib import Path

from gguf_fixture import qwen_metadata, write_fake_gguf
from leaf_moe_bench.gguf import GGUFError, read_gguf_header


class GGUFTests(unittest.TestCase):
    def test_reads_selected_scalars_and_skips_tokenizer_arrays(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "model.gguf"
            write_fake_gguf(path, qwen_metadata())
            header = read_gguf_header(path)
            self.assertEqual(header.version, 3)
            self.assertEqual(header.metadata["general.architecture"], "qwen35moe")
            self.assertEqual(header.metadata["qwen35moe.expert_count"], 93)
            self.assertNotIn("tokenizer.ggml.tokens", header.metadata)
            self.assertLessEqual(header.metadata_bytes_read, path.stat().st_size)
            self.assertEqual(header.parameter_count, 0)
            self.assertEqual(header.tensor_info_bytes_read, 0)

    def test_counts_parameters_from_tensor_descriptors_without_reading_payloads(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "model.gguf"
            write_fake_gguf(
                path,
                qwen_metadata(),
                tensors=[("token_embd.weight", (2048, 32000), 1, 0), ("output.weight", (2048, 8), 1, 0)],
            )
            header = read_gguf_header(path)
            self.assertEqual(header.tensor_count, 2)
            self.assertEqual(header.parameter_count, 2048 * 32000 + 2048 * 8)
            self.assertGreater(header.tensor_info_bytes_read, 0)

    def test_rejects_invalid_magic(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.gguf"
            path.write_bytes(b"NOPE")
            with self.assertRaises(GGUFError):
                read_gguf_header(path)


if __name__ == "__main__":
    unittest.main()
