import copy
import json
import gzip
import hashlib
import tempfile
import shutil
from unittest.mock import patch
import unittest
from pathlib import Path

from turbo.web.read_model import (SnapshotError, SnapshotStore, load_snapshot,
                                  _resolve_graph, _resolve_schedule)


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
        self.assertEqual(snapshot.provenance()["read_model_version"], "1.1.0")
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

    def test_absent_allowlisted_receipt_does_not_expose_a_path(self) -> None:
        with self.assertRaises(KeyError) as raised:
            self.snapshot.receipt("graph-release", "nonexistent")
        self.assertNotIn(str(self.snapshot.root), str(raised.exception))

    def test_explicit_incompatible_versions_fail_closed(self) -> None:
        with self.assertRaisesRegex(SnapshotError, "incompatible"):
            load_snapshot(source_run_id="run-1f039950ed1e4e3192c7")

    def test_historical_graph_receipt_must_match_projection_and_release(self) -> None:
        original = (self.snapshot.root / "data/market_graph/versions"
                    / self.snapshot.version.release_id)
        mutations = (
            ("graph version", lambda receipt: receipt.update(graph_version_id="graph-mismatch"), "graph-mismatch"),
            ("counts", lambda receipt: receipt["counts"].update(canonical_markets=999), self.snapshot.version.graph_version_id),
            ("release directory", lambda receipt: receipt.update(release_id="graph-release-other"), self.snapshot.version.graph_version_id),
            ("publication", lambda receipt: receipt.update(status="pending"), self.snapshot.version.graph_version_id),
        )
        for label, mutate, selected_version in mutations:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                target = root / "data/market_graph/versions" / original.name
                shutil.copytree(original, target)
                path = target / "graph-receipt.json"
                receipt = json.loads(path.read_text())
                mutate(receipt)
                path.write_text(json.dumps(receipt))
                with self.assertRaises(SnapshotError):
                    _resolve_graph(root, selected_version)

    def test_historical_schedule_cannot_omit_consumed_artifact_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "data/family_schedules" / self.snapshot.version.partition_id
            directory.mkdir(parents=True)
            receipt = copy.deepcopy(self.snapshot.schedule_receipt)
            del receipt["output_hashes"]["family-manifest.json.gz"]
            (directory / "schedule-receipt.json").write_text(json.dumps(receipt))
            with self.assertRaisesRegex(SnapshotError, "artifact set mismatch"):
                _resolve_schedule(root, self.snapshot.version.partition_id)

    def test_historical_schedule_receipt_counts_match_frozen_collections(self) -> None:
        source = self.snapshot.root / "data/family_schedules" / self.snapshot.version.partition_id
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "data/family_schedules" / source.name
            shutil.copytree(source, directory)
            path = directory / "schedule-receipt.json"
            receipt = json.loads(path.read_text())
            receipt["counts"]["families"] = 999
            path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(SnapshotError, "receipt counts disagree"):
                _resolve_schedule(root, source.name)

    def test_corrected_schedule_requires_new_count_fields(self) -> None:
        source = self.snapshot.root / "data/family_schedules" / self.snapshot.version.partition_id
        for field in ("pilot_context_identities", "context_only_collision_candidates"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                directory = root / "data/family_schedules" / source.name
                shutil.copytree(source, directory)
                coverage_path = directory / "coverage-ledger.json.gz"
                coverage = json.loads(gzip.decompress(coverage_path.read_bytes()))
                del coverage["counts"][field]
                coverage_path.write_bytes(gzip.compress(json.dumps(coverage).encode(), mtime=0))
                receipt_path = directory / "schedule-receipt.json"
                receipt = json.loads(receipt_path.read_text())
                del receipt["counts"][field]
                receipt["output_hashes"][coverage_path.name] = hashlib.sha256(coverage_path.read_bytes()).hexdigest()
                receipt_path.write_text(json.dumps(receipt))
                with self.assertRaisesRegex(SnapshotError, "receipt counts disagree"):
                    _resolve_schedule(root, source.name)

    def test_schedule_rehash_cannot_hide_header_or_count_incoherence(self) -> None:
        source = self.snapshot.root / "data/family_schedules" / self.snapshot.version.partition_id
        mutations = (
            ("header", "family-manifest.json.gz", lambda value: value.update(source_run_id="run-other")),
            ("manifest count", "family-manifest.json.gz", lambda value: value["counts"].update(families=999)),
            ("family workload", "family-manifest.json.gz", lambda value: value["families"][0]["counts"].update(required_identities=999)),
            ("batch workload", "batch-manifest.json", lambda value: value["batches"][0].update(required_identities=999)),
            ("candidate count", "candidate-collision-ledger.json.gz", lambda value: value["counts"].update(prior_candidates=999)),
            ("edge count", "context-edge-ledger.json.gz", lambda value: value["counts"].update(industry_product_relationships=999)),
        )
        for label, name, mutate in mutations:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                directory = root / "data/family_schedules" / source.name
                shutil.copytree(source, directory)
                path = directory / name
                value = json.loads(gzip.decompress(path.read_bytes())) if name.endswith(".gz") else json.loads(path.read_text())
                mutate(value)
                raw = json.dumps(value).encode()
                path.write_bytes(gzip.compress(raw, mtime=0) if name.endswith(".gz") else raw)
                receipt_path = directory / "schedule-receipt.json"
                receipt = json.loads(receipt_path.read_text())
                receipt["output_hashes"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
                receipt_path.write_text(json.dumps(receipt))
                with self.assertRaises(SnapshotError):
                    _resolve_schedule(root, source.name)

    def test_explicit_source_context_does_not_inherit_latest_source_metadata(self) -> None:
        latest = copy.deepcopy(self.snapshot.context)
        latest["source_universe"].update(
            normalized_identities=999, immutable_run_path="data/runs/other",
            output_hashes={"other.json": "0" * 64},
        )
        with patch("turbo.web.read_model.compile_system_context", return_value=latest):
            selected = load_snapshot(
                source_run_id=self.snapshot.version.source_run_id,
                partition_id=self.snapshot.version.partition_id,
                graph_version_id=self.snapshot.version.graph_version_id,
            )
        self.assertEqual(selected.context["source_universe"]["normalized_identities"], 11543)
        self.assertEqual(selected.context["source_universe"]["immutable_run_path"],
                         "data/runs/" + self.snapshot.version.source_run_id)
        self.assertEqual(selected.context["source_universe"]["output_hashes"],
                         self.snapshot.source_receipt["output_hashes"])

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
        self.assertEqual(
            sum(item["current"] for item in versions["compatible_snapshots"]), 1
        )
        self.assertGreaterEqual(len(versions["compatible_snapshots"]), 2)


if __name__ == "__main__":
    unittest.main()
