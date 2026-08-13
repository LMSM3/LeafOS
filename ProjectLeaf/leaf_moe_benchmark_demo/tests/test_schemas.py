import json
import unittest
from pathlib import Path


class SchemaTests(unittest.TestCase):
    def test_all_schema_documents_are_valid_json_with_unique_ids(self):
        schema_root = Path(__file__).resolve().parents[1] / "schemas"
        payloads = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(schema_root.glob("*.json"))]
        self.assertEqual(len(payloads), 5)
        ids = [payload["$id"] for payload in payloads]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(payload["$schema"].endswith("2020-12/schema") for payload in payloads))


if __name__ == "__main__":
    unittest.main()
