import unittest

from turbo.universe.multisource import parse_napcs, parse_prior, reconcile


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
        self.assertEqual(sum(result["mapping_counts"].values()), len(result["mappings"]))
        self.assertNotIn("accepted_exact_label", result["mapping_counts"])
        self.assertEqual(result["mapping_counts"]["exact_label_candidate"], 207)


if __name__ == "__main__":
    unittest.main()

