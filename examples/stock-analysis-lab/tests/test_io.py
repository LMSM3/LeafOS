from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stocklab.io import DataError, load_config, read_prices


class InputTests(unittest.TestCase):
    def test_rejects_non_increasing_dates_and_nonpositive_prices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("date,A\n2026-01-02,1\n2026-01-01,0\n", encoding="utf-8")
            with self.assertRaisesRegex(DataError, "strictly increasing"):
                read_prices(path)

    def test_rejects_unknown_config_instead_of_silently_ignoring_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({"magic_success": True}), encoding="utf-8")
            with self.assertRaisesRegex(DataError, "unknown configuration"):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
