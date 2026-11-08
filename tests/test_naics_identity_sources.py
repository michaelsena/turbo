import unittest

from turbo.universe.naics_identity_sources import (
    naics_identity_source_artifacts,
    parse_naics_manual_index,
)


class NaicsIdentitySourcesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.summary, cls.details = naics_identity_source_artifacts()

    def test_manual_index_is_reconstructed_by_coordinate_and_column(self) -> None:
        entries = parse_naics_manual_index()
        self.assertEqual(len(entries), 20_317)
        self.assertEqual(len({entry.naics_2022_code for entry in entries}), 1_010)
        self.assertEqual(
            self.summary["manual_index"]["missing_six_digit_codes"],
            ["112130", "541120"],
        )
        self.assertTrue(all(entry.normalized_label for entry in entries))
        self.assertEqual(len({entry.locator for entry in entries}), len(entries))
        self.assertTrue(all(entry.column in {1, 2} for entry in entries))
        self.assertEqual(entries[0].page, 637)
        self.assertEqual(entries[-1].page, 958)

    def test_full_concordance_directions_are_exact_reverses(self) -> None:
        counts = self.summary["full_concordance"]
        self.assertEqual(counts["forward_rows"], 1_150)
        self.assertEqual(counts["reverse_rows"], 1_150)
        self.assertEqual(counts["unique_pairs"], 1_150)
        self.assertEqual(counts["unique_2017_codes"], 1_057)
        self.assertEqual(counts["unique_2022_codes"], 1_012)
        self.assertEqual(counts["same_code_pairs"], 918)
        self.assertEqual(counts["changed_pairs"], 232)
        self.assertEqual(counts["changed_2017_codes"], 140)
        self.assertEqual(counts["changed_2022_codes"], 95)
        self.assertEqual(counts["split_2017_codes"], 9)
        self.assertEqual(counts["merged_2022_codes"], 79)
        self.assertTrue(counts["directions_exact_reverses"])

        relationships = self.details["vintage_lineage_relationships"]
        self.assertEqual(len(relationships), 1_150)
        self.assertTrue(
            all(len(item["source_observations"]) == 2 for item in relationships)
        )
        self.assertTrue(
            all(
                {observation["direction"] for observation in item["source_observations"]}
                == {"2017_to_2022", "2022_to_2017"}
                for item in relationships
            )
        )

    def test_bridge_rows_remain_observations_not_identity_nodes(self) -> None:
        counts = self.summary["economic_census_bridges"]
        self.assertEqual(counts["2017_to_2022_observations"], 444)
        self.assertEqual(counts["2022_to_2017_observations"], 402)
        self.assertEqual(counts["industry_total_observations"], 236)
        self.assertEqual(counts["component_observations"], 610)
        rows = self.details["economic_census_bridge_observations"]
        self.assertEqual(len(rows), 846)
        self.assertTrue(all("identity_id" not in row for row in rows))
        self.assertEqual(
            len({(row["snapshot_id"], row["locator"]) for row in rows}),
            len(rows),
        )

    def test_current_identity_endpoints_are_explicit(self) -> None:
        index_entries = self.details["manual_index_entries"]
        lineage = self.details["vintage_lineage_relationships"]
        self.assertTrue(
            all(item["identity_id"].startswith("identity:naics:") for item in index_entries)
        )
        self.assertTrue(
            all(
                item["naics_2022_identity_id"].startswith("identity:naics:")
                for item in lineage
            )
        )


if __name__ == "__main__":
    unittest.main()
