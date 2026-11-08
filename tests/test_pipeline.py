import gzip
import json
import unittest
from unittest.mock import patch

from turbo.pipeline import (
    RUNS,
    run,
    validate,
    validate_identity_references,
    validate_naics_identity_evidence,
    validate_napcs_hierarchy_evidence,
    validate_manifest_metadata,
)


class PipelineTest(unittest.TestCase):
    def test_manifest_metadata_requires_nonempty_utc_governance_fields(self) -> None:
        manifest = {
            "acquired_at": "2026-11-08T12:00:00",
            "dataset_id": "dataset",
            "file": "source.zip",
            "publisher": "",
            "reuse": "public",
            "role": "evidence",
            "sha256": "not-a-hash",
            "source_url": "http://example.com",
        }
        errors = validate_manifest_metadata(manifest, "test.snapshot.json")
        self.assertTrue(any("publisher" in error for error in errors))
        self.assertTrue(any("must be UTC" in error for error in errors))
        self.assertTrue(any("invalid sha256" in error for error in errors))
        self.assertTrue(any("must use https" in error for error in errors))

    def test_run_fails_closed_when_source_validation_fails(self) -> None:
        with patch("turbo.pipeline.validate", return_value=["tampered NAPCS snapshot"]):
            with self.assertRaisesRegex(ValueError, "tampered NAPCS snapshot"):
                run()

    def test_standalone_validation_runs_identity_reference_validation(self) -> None:
        with (
            patch("turbo.pipeline.reconcile", return_value={"source_records": []}),
            patch("turbo.pipeline.identity_source_artifacts", return_value=({}, {})),
            patch(
                "turbo.pipeline.validate_identity_references",
                return_value=["dangling normalized identity"],
            ) as reference_validator,
        ):
            errors = validate()
        self.assertIn("dangling normalized identity", errors)
        reference_validator.assert_called_once()

    def test_standalone_validation_fails_closed_when_identity_build_fails(self) -> None:
        with patch(
            "turbo.pipeline.reconcile",
            side_effect=ValueError("identity build failed"),
        ):
            errors = validate()
        self.assertIn(
            "identity/reference validation failed: identity build failed",
            errors,
        )

    def test_identity_validation_requires_one_complete_mapping_per_identity(self) -> None:
        reconciliation = {
            "source_records": [
                {
                    "record_id": "source-row:one",
                    "snapshot_id": "snapshot:one",
                    "normalized_identity_ids": ["identity:naics:1"],
                    "source_relationships": [],
                }
            ],
            "source_identities": [
                {
                    "identity_id": "identity:naics:1",
                    "source_record_ids": ["source-row:one"],
                }
            ],
            "mappings": [
                {
                    "normalized_identity_id": "identity:naics:1",
                    "supporting_source_record_ids": [],
                }
            ],
        }
        relationships = {
            "napcs_concordance_relationships": [],
            "napcs_concordance_non_mappings": [],
            "industry_product_relationships": [],
        }
        errors = validate_identity_references(
            reconciliation,
            relationships,
            {"snapshot:one"},
        )
        self.assertIn(
            "mapping identity:naics:1 does not preserve its complete source-record set",
            errors,
        )

    def test_naics_identity_evidence_fails_closed_on_endpoints_and_snapshots(self) -> None:
        evidence = {
            "manual_index_entries": [
                {
                    "identity_id": "identity:naics:999999",
                    "snapshot_id": "not-governed",
                    "locator": "pdf:page:1:entry:1",
                }
            ],
            "manual_index_cross_references": [],
            "manual_definitions": [],
            "vintage_lineage_relationships": [],
            "economic_census_bridge_observations": [],
        }
        errors = validate_naics_identity_evidence(
            evidence,
            {"identity:naics:111110"},
            {"census-naics-2022-manual"},
        )
        self.assertIn(
            "manual index entry references unknown identity identity:naics:999999",
            errors,
        )
        self.assertIn(
            "manual index entry references unknown snapshot not-governed",
            errors,
        )

    def test_napcs_hierarchy_evidence_fails_closed_on_endpoints_and_snapshots(self) -> None:
        evidence = {
            "nodes": [
                {
                    "code": "99999999999",
                    "parent_code": "999999999",
                    "snapshot_id": "not-governed",
                    "locator": "section99.html:table.data:row:2:code:99999999999",
                }
            ],
            "hierarchy_only_product_codes": ["99999999999"],
        }
        errors = validate_napcs_hierarchy_evidence(
            evidence,
            {"identity:napcs-trilateral:11101010101"},
            {"census-napcs-2022-trilateral-hierarchy"},
        )
        self.assertIn(
            "NAPCS hierarchy node references unknown identity "
            "identity:napcs-trilateral:99999999999",
            errors,
        )
        self.assertIn(
            "NAPCS hierarchy node references unknown snapshot not-governed",
            errors,
        )
        self.assertIn(
            "NAPCS hierarchy node references unknown parent identity "
            "identity:napcs-trilateral:999999999",
            errors,
        )

    def test_replay_reuses_same_immutable_run(self) -> None:
        first = run()
        receipt = RUNS / first["run_id"] / "run-receipt.json"
        before = receipt.read_bytes()
        second = run()
        after = receipt.read_bytes()
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(before, after)
        self.assertEqual(first["canonical_markets"], 0)
        self.assertEqual(first["research_scores"], 0)
        self.assertGreaterEqual(first["governed_source_snapshots"], 8)
        self.assertEqual(first["identity_source_counts"]["collection_to_trilateral_rows"], 3_520)
        self.assertEqual(first["run_config"]["dependency_versions"]["pypdf"], "6.21.4")
        self.assertIn("project_config_sha256", first["run_config"])
        for artifact in first["output_hashes"]:
            self.assertTrue(artifact.endswith(".json.gz"))
            payload = gzip.decompress((RUNS / first["run_id"] / artifact).read_bytes())
            self.assertIsInstance(json.loads(payload), dict)


if __name__ == "__main__":
    unittest.main()

