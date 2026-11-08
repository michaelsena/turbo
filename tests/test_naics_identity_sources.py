import re
import unittest

from turbo.universe.naics_identity_sources import (
    naics_identity_source_artifacts,
    parse_naics_manual_definitions,
    parse_naics_manual_index,
    parse_naics_manual_index_cross_references,
)


class NaicsIdentitySourcesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.summary, cls.details = naics_identity_source_artifacts()

    def test_manual_index_is_reconstructed_by_coordinate_and_column(self) -> None:
        entries = parse_naics_manual_index()
        self.assertEqual(len(entries), 20_373)
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
        split_anchor = next(
            entry
            for entry in entries
            if entry.page == 725 and entry.naics_2022_code == "423830"
        )
        self.assertEqual(
            split_anchor.normalized_label,
            "Distillery machinery merchant wholesalers",
        )
        self.assertFalse(
            any("423830Distillery" in entry.normalized_label for entry in entries)
        )
        self.assertFalse(
            any(
                re.search(r"(?<!\d)\d{6}(?!\d)", entry.normalized_label)
                for entry in entries
            )
        )
        self.assertTrue(
            any(
                entry.naics_2022_code == "423120"
                and entry.page == 640
                and entry.normalized_label
                == "Aftermarket parts, automotive, merchant wholesalers"
                for entry in entries
            )
        )
        self.assertTrue(
            any(
                entry.naics_2022_code == "331314"
                and entry.page == 644
                and entry.normalized_label
                == "Aluminum billet made from purchased aluminum"
                for entry in entries
            )
        )

    def test_uncoded_index_cross_references_are_separate_rows(self) -> None:
        cross_references = parse_naics_manual_index_cross_references()
        self.assertEqual(len(cross_references), 25)
        self.assertEqual(
            self.summary["manual_index"]["uncoded_cross_reference_rows"],
            25,
        )
        self.assertEqual(
            len({entry.locator for entry in cross_references}),
            len(cross_references),
        )
        self.assertTrue(
            any(
                entry.normalized_label == "Cards, publishing -- see specific product"
                for entry in cross_references
            )
        )

    def test_manual_definitions_close_against_every_structure_identity(self) -> None:
        definitions = parse_naics_manual_definitions()
        self.assertEqual(len(definitions), 2_125)
        self.assertEqual(len({item.naics_2022_code for item in definitions}), 2_125)
        self.assertEqual(
            self.summary["manual_definitions"]["level_counts"],
            {2: 20, 3: 96, 4: 308, 5: 689, 6: 1_012},
        )
        self.assertEqual(
            self.summary["manual_definitions"]["disposition_counts"],
            {
                "delegated_definition": 522,
                "substantive_inline_definition": 1_572,
                "title_only_heading": 31,
            },
        )

    def test_manual_semantic_blocks_and_delegated_links_are_typed(self) -> None:
        definitions = parse_naics_manual_definitions()
        illustrative = [
            item for item in definitions if item.illustrative_examples_fragments
        ]
        cross_references = [
            item for item in definitions if item.cross_references_fragments
        ]
        delegated = [item for item in definitions if item.delegated_to_code]
        title_only = [
            item for item in definitions if item.disposition == "title_only_heading"
        ]
        self.assertEqual(len(illustrative), 381)
        self.assertEqual(len(cross_references), 1_095)
        self.assertEqual(len(delegated), 522)
        self.assertEqual(len(title_only), 31)
        self.assertTrue(all(item.level == 5 for item in delegated))
        self.assertEqual(
            {item.naics_2022_code for item in title_only},
            {
                "2111", "3122", "4242", "4251", "4453", "4492", "4551",
                "4552", "4561", "4572", "4581", "4582", "4592", "4593",
                "4595", "5178", "5621", "5622", "6111", "8131", "8132",
                "8133", "8134", "9211", "9221", "9231", "9241", "9251",
                "9261", "9271", "9281",
            },
        )
        split_heading = next(
            item for item in definitions if item.naics_2022_code == "323113"
        )
        self.assertEqual(split_heading.start_page, 188)
        split_target = next(
            item for item in definitions if item.naics_2022_code == "54112"
        )
        self.assertEqual(split_target.delegated_to_code, "541120")

    def test_manual_semantic_text_preserves_line_wrapped_compounds(self) -> None:
        definitions = {
            item.naics_2022_code: item for item in parse_naics_manual_definitions()
        }
        self.assertIn("air-conditioning", definitions["238220"].narrative_text)
        self.assertNotIn("air- conditioning", definitions["238220"].narrative_text)
        self.assertIn(
            "residential-type, installation",
            definitions["238350"].illustrative_examples_text,
        )
        self.assertIn(
            "peer-to-peer payment services",
            definitions["522320"].illustrative_examples_text,
        )
        self.assertIn("one-half", definitions["111140"].cross_references_text)

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
