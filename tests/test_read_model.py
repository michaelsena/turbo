import copy
import json
import tempfile
import unittest
from pathlib import Path

from turbo.web.read_model import SnapshotError, SnapshotStore, load_snapshot


class ReadModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = load_snapshot()

    def test_current_snapshot_is_version_compatible_and_complete(self) -> None:
        snapshot = self.snapshot
        self.assertEqual(snapshot.version.source_run_id, "run-2ea0f00db84148de663f")
        self.assertEqual(
            snapshot.version.partition_id,
            "family-partition:60517981ab96e7f243c7033e",
        )
        self.assertEqual(snapshot.context["canonical_markets"], 3)
        self.assertEqual(len(snapshot.identities), 11_543)
        self.assertEqual(len(snapshot.families), 1_026)
        self.assertEqual(len(snapshot.batches), 129)
        self.assertEqual(len(snapshot.candidates), 978)
        self.assertEqual(len(snapshot.markets), 3)
        self.assertEqual(len(snapshot.graph_mappings), 1)

    def test_market_detail_exposes_boundary_gaps_sources_and_audit_chain(self) -> None:
        page = self.snapshot.list_markets(page_size=100)
        market_id = page["items"][0]["market_id"]
        detail = self.snapshot.market_detail(market_id)
        self.assertTrue(detail["boundary"])
        self.assertTrue(detail["source_records"])
        self.assertIn("graph_version_id", detail["audit_chain"])
        self.assertEqual(
            {gap["gap_id"] for gap in detail["research_gaps"]},
            set(detail["research_gap_ids"]),
        )

    def test_family_queue_is_neutral_and_deterministically_paginated(self) -> None:
        first = self.snapshot.list_families(page=1, page_size=10)
        replay = self.snapshot.list_families(page=1, page_size=10)
        self.assertEqual(first, replay)
        self.assertEqual(first["total"], 1_026)
        self.assertNotIn("score", json.dumps(first).casefold())
        detail = self.snapshot.family_detail(first["items"][0]["family_id"])
        self.assertIn("Administrative review ownership only", detail["ownership_notice"])

    def test_identity_and_candidate_search_are_joined_to_current_partition(self) -> None:
        identity = self.snapshot.identity_detail("identity:naics:561110")
        self.assertEqual(
            identity["assignment"]["owner_family_id"],
            "family:naics-2022:561110",
        )
        candidates = self.snapshot.list_candidates(
            coverage_status="unretrieved_global_challenger", page_size=100
        )
        self.assertEqual(candidates["total"], 58)
        results = self.snapshot.search("office administrative")
        self.assertTrue(any(item["kind"] == "family" for item in results))
        self.assertTrue(any(item["kind"] == "identity" for item in results))
        self.assertFalse(any(item["kind"] == "market" for item in results))

    def test_pagination_is_bounded(self) -> None:
        with self.assertRaisesRegex(SnapshotError, "page_size"):
            self.snapshot.list_families(page_size=101)
        with self.assertRaisesRegex(SnapshotError, "page must"):
            self.snapshot.list_markets(page=0)

    def test_receipts_are_whitelisted_and_path_safe(self) -> None:
        receipt = self.snapshot.receipt(
            "graph-release", "graph-release-aa5b6f83e7a06e073d3a"
        )
        self.assertEqual(receipt["kind"], "graph-release")
        with self.assertRaisesRegex(SnapshotError, "invalid receipt ID"):
            self.snapshot.receipt("graph-release", "../../.env")
        with self.assertRaises(KeyError):
            self.snapshot.receipt("arbitrary", "anything")

    def test_receipt_view_recursively_removes_sensitive_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = copy.copy(self.snapshot)
            snapshot.root = Path(temporary)
            receipt_dir = (
                snapshot.root
                / "data"
                / "market_graph"
                / "versions"
                / "synthetic-receipt"
            )
            receipt_dir.mkdir(parents=True)
            (receipt_dir / "graph-receipt.json").write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "api_key": "must-not-leak",
                        "nested": {
                            "authorization_header": "must-not-leak",
                            "safe": "visible",
                        },
                    }
                ),
                encoding="utf-8",
            )
            view = snapshot.receipt("graph-release", "synthetic-receipt")
        self.assertEqual(
            view["receipt"],
            {"status": "complete", "nested": {"safe": "visible"}},
        )
        self.assertEqual(
            view["redacted_paths"],
            ["$.api_key", "$.nested.authorization_header"],
        )

    def test_explicit_incompatible_versions_fail_closed(self) -> None:
        with self.assertRaisesRegex(SnapshotError, "incompatible"):
            load_snapshot(source_run_id="run-1f039950ed1e4e3192c7")

    def test_pointer_change_reloads_only_after_complete_validation(self) -> None:
        store = SnapshotStore()
        first = store.latest()
        second = store.latest()
        self.assertIs(first, second)

    def test_version_catalog_marks_one_current_version_per_layer(self) -> None:
        versions = SnapshotStore().versions()
        self.assertEqual(sum(item["current"] for item in versions["source_runs"]), 1)
        self.assertEqual(sum(item["current"] for item in versions["partitions"]), 1)
        self.assertEqual(sum(item["current"] for item in versions["graph_releases"]), 1)


if __name__ == "__main__":
    unittest.main()
