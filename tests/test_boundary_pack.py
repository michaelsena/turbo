import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from turbo.pipeline_paths import ROOT
from turbo.universe import boundary_pack
from turbo.universe.boundary_pack import build_boundary_pack, validate_boundary_pack


CONFIG = ROOT / "config/universe/families/office-administrative-services-v1.json"


class BoundaryPackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pack = build_boundary_pack(CONFIG)

    def test_pack_closes_the_exact_preregistered_family(self) -> None:
        counts = self.pack["summary"]["counts"]
        self.assertEqual(counts["required_disposition_identities"], 66)
        self.assertEqual(counts["industry_product_relationships"], 65)
        self.assertEqual(counts["industry_product_source_observations"], 121)
        self.assertEqual(counts["collection_workbook_rows"], 38)
        self.assertEqual(counts["relationship_only_collection_identities"], 27)
        self.assertEqual(counts["collection_trilateral_relationships"], 55)
        self.assertEqual(counts["collection_trilateral_source_observations"], 110)
        self.assertEqual(counts["linked_trilateral_products"], 47)
        self.assertEqual(counts["linked_trilateral_context_nodes"], 149)
        self.assertEqual(counts["explicit_no_mapping_records"], 1)
        self.assertEqual(counts["selected_products_absent_from_concordance"], 9)
        self.assertEqual(counts["manual_definition_records"], 1)
        self.assertEqual(counts["manual_index_entries"], 13)
        self.assertEqual(counts["vintage_lineage_relationships"], 1)
        self.assertEqual(counts["existing_reconciliation_mappings"], 66)
        self.assertEqual(counts["retrieved_prior_candidates"], 127)
        self.assertEqual(counts["prior_candidate_catalog"], 978)
        self.assertEqual(
            self.pack["summary"]["cross_industry_prevalence"],
            {
                "minimum": 3,
                "median": 20,
                "maximum": 682,
                "interpretation_boundary": (
                    "Counts are relationship prevalence only, not revenue share, "
                    "importance, exclusivity, or core-workflow proof."
                ),
            },
        )

    def test_required_and_context_identities_are_separate(self) -> None:
        scope = self.pack["scope"]
        required = set(scope["required_disposition_identity_ids"])
        context = set(scope["context_only_identity_ids"])
        self.assertIn("identity:naics:561110", required)
        self.assertEqual(len(required), 66)
        self.assertEqual(
            {
                "identity:naics:56",
                "identity:naics:561",
                "identity:naics:5611",
                "identity:naics:56111",
            },
            {item for item in context if item.startswith("identity:naics:56")},
        )
        self.assertFalse(required & context)

    def test_evidence_catalog_is_closed_and_stable(self) -> None:
        evidence = self.pack["evidence_catalog"]
        evidence_ids = [item["evidence_id"] for item in evidence]
        self.assertEqual(len(evidence), 547)
        self.assertEqual(len(evidence_ids), len(set(evidence_ids)))
        self.assertEqual(evidence_ids, sorted(evidence_ids))
        self.assertEqual(validate_boundary_pack(self.pack), [])
        rebuilt = build_boundary_pack(CONFIG)
        self.assertEqual(
            rebuilt["metadata"]["pack_sha256"],
            self.pack["metadata"]["pack_sha256"],
        )
        self.assertEqual(rebuilt, self.pack)

    def test_pack_hash_detects_any_content_mutation(self) -> None:
        tampered = copy.deepcopy(self.pack)
        tampered["scope"]["purpose"] = "changed"
        self.assertEqual(
            validate_boundary_pack(tampered),
            ["pack_sha256 does not match canonical pack content"],
        )

    def test_compiler_rejects_a_tampered_run_artifact(self) -> None:
        original = boundary_pack._sha256_path

        def wrong_hash(path: Path) -> str:
            if path.name == "multisource-reconciliation.json.gz":
                return "0" * 64
            return original(path)

        with patch.object(boundary_pack, "_sha256_path", side_effect=wrong_hash):
            with self.assertRaisesRegex(
                ValueError,
                "immutable run artifact hash mismatch",
            ):
                build_boundary_pack(CONFIG)


if __name__ == "__main__":
    unittest.main()
