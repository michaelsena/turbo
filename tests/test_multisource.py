import unittest

from turbo.universe.multisource import (
    parse_napcs,
    parse_prior,
    prior_records,
    reconcile,
    semantic_conflicts,
    semantic_flags,
)


class MultiSourceUniverseTest(unittest.TestCase):
    def test_all_initial_lists_are_loaded(self) -> None:
        self.assertEqual(len(parse_napcs()), 6_290)
        self.assertEqual(len(parse_prior()), 978)

    def test_reconciliation_preserves_every_source_row(self) -> None:
        result = reconcile()
        counts = result["source_counts"]
        self.assertEqual(
            len(result["mappings"]),
            counts["naics_six_digit"] + counts["napcs_products"],
        )
        self.assertEqual(len(result["candidate_markets"]), counts["prior_seed_markets"])
        self.assertEqual(
            len(result["source_records"]),
            counts["naics_six_digit"] + counts["napcs_products"] + counts["prior_seed_markets"],
        )
        self.assertEqual(sum(result["mapping_counts"].values()), len(result["mappings"]))
        self.assertNotIn("accepted_exact_label", result["mapping_counts"])
        self.assertEqual(result["mapping_counts"]["exact_label_candidate"], 207)
        self.assertTrue(all(len(item["candidates"]) <= 5 for item in result["mappings"]))

    def test_prior_ids_survive_input_reordering(self) -> None:
        first = {item.name: item.record_id for item in prior_records(["Alpha Services", "Beta Services"])}
        second = {item.name: item.record_id for item in prior_records(["Beta Services", "Alpha Services"])}
        self.assertEqual(first, second)

    def test_scope_semantics_are_not_erased(self) -> None:
        self.assertIn(
            "candidate_contains_source_excluded_scope",
            semantic_conflicts(
                "Surveying and Mapping (except Geophysical) Services",
                "Geophysical surveying",
            ),
        )
        self.assertIn(
            "candidate_contains_source_excluded_scope",
            semantic_conflicts(
                "Project management services, except construction",
                "Construction project management",
            ),
        )
        self.assertIn(
            "hazard_scope_conflict",
            semantic_conflicts("Nonhazardous Waste Treatment", "Hazardous Waste Treatment"),
        )
        self.assertTrue(semantic_flags("All Other Warehousing and Storage")["residual"])

    def test_napcs_controls_are_typed(self) -> None:
        kinds = [record.record_kind for record in parse_napcs()]
        self.assertIn("survey_control", kinds)
        self.assertIn("napcs_broad_line", kinds)
        self.assertIn("napcs_detail_line", kinds)


if __name__ == "__main__":
    unittest.main()

