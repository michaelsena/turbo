from pathlib import Path
import unittest

from turbo.pipeline import SOURCE, sha256
from turbo.universe.naics import parse_naics


class NaicsParsingTest(unittest.TestCase):
    def test_parses_official_workbook_and_hierarchy(self) -> None:
        nodes = parse_naics(Path(SOURCE))
        by_id = {node.node_id: node for node in nodes}
        self.assertGreater(len(nodes), 1_000)
        self.assertIn("naics-11", by_id)
        self.assertIn("naics-111110", by_id)
        self.assertEqual(by_id["naics-111110"].parent_id, "naics-11111")
        self.assertEqual(by_id["naics-31-33"].level, 2)
        self.assertEqual(len(nodes), 2_125)
        self.assertEqual(
            sha256(SOURCE),
            "217c9e0d4d74e7517bc288f5f308b73aa0de5ee787976a6dd222412be28ada22",
        )
        self.assertEqual(by_id["naics-11"].source_indicator, "trilateral")
        self.assertTrue(by_id["naics-11"].raw_title.endswith("T"))


if __name__ == "__main__":
    unittest.main()

