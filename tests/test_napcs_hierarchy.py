import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from turbo.universe.identity_sources import (
    parse_collection_to_trilateral,
    parse_trilateral_to_collection,
)
from turbo.universe.napcs_hierarchy import (
    CAPTURE,
    EXPECTED_LEVEL_COUNTS,
    EXPECTED_SECTIONS,
    capture_pages,
    napcs_hierarchy_artifacts,
    parse_napcs_hierarchy,
)


class NapcsHierarchyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pages = capture_pages()
        cls.nodes = parse_napcs_hierarchy()
        cls.summary, cls.evidence = napcs_hierarchy_artifacts()

    def test_capture_preserves_all_official_page_responses(self) -> None:
        self.assertEqual(tuple(page.section for page in self.pages), EXPECTED_SECTIONS)
        self.assertEqual(len(self.pages), 24)
        self.assertEqual(sum(page.byte_length for page in self.pages), 1_064_705)
        self.assertTrue(all(page.status == 200 for page in self.pages))
        self.assertTrue(all(len(page.sha256) == 64 for page in self.pages))
        self.assertTrue(all(page.retrieved_at_utc.endswith("Z") for page in self.pages))
        self.assertTrue(all(page.headers for page in self.pages))

    def test_full_six_level_hierarchy_has_exact_counts(self) -> None:
        self.assertEqual(len(self.nodes), 2_182)
        counts = Counter(node.level_name for node in self.nodes)
        self.assertEqual(dict(counts), EXPECTED_LEVEL_COUNTS)
        self.assertEqual(self.summary["level_counts"], EXPECTED_LEVEL_COUNTS)

    def test_hierarchy_closes_every_published_parent_except_documented_anomaly(self) -> None:
        codes = {node.code for node in self.nodes}
        anomalies = [
            node for node in self.nodes if node.parent_status == "missing_published_parent"
        ]
        self.assertEqual(
            [(node.code, node.expected_parent_code) for node in anomalies],
            [("1110201", "11102")],
        )
        self.assertNotIn("11102", codes)
        self.assertTrue(
            all(
                node.parent_code is None or node.parent_code in codes
                for node in self.nodes
            )
        )

    def test_hierarchy_adds_exactly_87_products_beyond_concordances(self) -> None:
        hierarchy_products = {
            node.code for node in self.nodes if node.level_name == "trilateral_product"
        }
        concordance_products = {
            row.trilateral_code
            for rows in (
                parse_collection_to_trilateral(),
                parse_trilateral_to_collection(),
            )
            for row in rows
            if row.trilateral_code not in {"", "NA"}
        }
        self.assertEqual(concordance_products - hierarchy_products, set())
        self.assertEqual(len(hierarchy_products - concordance_products), 87)
        self.assertEqual(
            set(self.evidence["hierarchy_only_product_codes"]),
            hierarchy_products - concordance_products,
        )

    def test_every_node_has_unique_exact_source_locator(self) -> None:
        locators = {
            (node.snapshot_id, node.locator)
            for node in self.nodes
        }
        self.assertEqual(len(locators), len(self.nodes))
        self.assertTrue(
            all(
                f"section{node.section}.html:table.data:row:" in node.locator
                and node.locator.endswith(f":code:{node.code}")
                for node in self.nodes
            )
        )

    def test_capture_fails_closed_on_page_hash_change(self) -> None:
        payload = json.loads(CAPTURE.read_text(encoding="utf-8"))
        payload["pages"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tampered.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA-256 does not match"):
                capture_pages(path)

    def test_capture_fails_closed_on_invalid_provenance(self) -> None:
        payload = json.loads(CAPTURE.read_text(encoding="utf-8"))
        payload["capture_method"] = "unknown"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tampered.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unexpected capture method"):
                capture_pages(path)

    def test_capture_fails_closed_on_non_utc_retrieval_time(self) -> None:
        payload = json.loads(CAPTURE.read_text(encoding="utf-8"))
        payload["pages"][0]["retrieved_at_utc"] = "2026-11-08T22:51:36-04:00"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tampered.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be a UTC timestamp"):
                capture_pages(path)


if __name__ == "__main__":
    unittest.main()
