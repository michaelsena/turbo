import unittest

from turbo.universe.identity_sources import (
    identity_source_artifacts,
    identity_source_summary,
    relationship_product_records,
)
from turbo.universe.multisource import reconcile


class IdentitySourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.summary = identity_source_summary()

    def test_concordances_are_parsed_from_data_sheets(self) -> None:
        self.assertEqual(self.summary["collection_to_trilateral"]["rows"], 3_520)
        self.assertEqual(self.summary["trilateral_to_collection"]["rows"], 3_520)
        self.assertEqual(self.summary["concordance_pair_difference"]["forward_only"], 3)
        self.assertEqual(self.summary["concordance_pair_difference"]["reverse_only"], 3)

    def test_product_relationship_archives_are_streamed_completely(self) -> None:
        self.assertEqual(self.summary["industry_by_products"]["rows"], 569_027)
        self.assertEqual(self.summary["products_by_industry"]["rows"], 32_024)
        self.assertGreater(
            self.summary["products_by_industry"]["unique_national_six_digit_naics_napcs_pairs"],
            0,
        )

    def test_many_to_many_relationships_are_preserved(self) -> None:
        summary, relationships = identity_source_artifacts()
        self.assertEqual(
            len(relationships["industry_product_relationships"]),
            summary["relationship_artifact_counts"]["industry_product_relationships"],
        )
        self.assertGreater(len(relationships["industry_product_relationships"]), 37_000)
        self.assertGreater(len(relationship_product_records()), 3_000)

    def test_every_relationship_endpoint_resolves_to_an_identity(self) -> None:
        _, relationships = identity_source_artifacts()
        identity_ids = {
            item["identity_id"] for item in reconcile()["source_identities"]
        }
        endpoints: set[str] = set()
        for edge in relationships["napcs_concordance_relationships"]:
            endpoints.add(edge["collection_identity_id"])
            endpoints.add(edge["trilateral_identity_id"])
        for edge in relationships["napcs_concordance_non_mappings"]:
            endpoints.add(edge["collection_identity_id"])
        for edge in relationships["industry_product_relationships"]:
            endpoints.add(edge["industry_identity_id"])
            endpoints.add(edge["product_identity_id"])
        self.assertEqual(endpoints - identity_ids, set())
        self.assertEqual(
            len(relationships["napcs_concordance_non_mappings"]),
            7,
        )


if __name__ == "__main__":
    unittest.main()
