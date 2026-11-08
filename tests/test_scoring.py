import unittest

from turbo.models import MarketNode
from turbo.pipeline import SOURCE
from turbo.universe.naics import parse_naics
from turbo.universe.scoring import evaluate_market


def node(code: str, title: str) -> MarketNode:
    return MarketNode(
        f"naics-{code}", code, title, title, None, 6, None, "source_category", ("test",)
    )


class ScoringTest(unittest.TestCase):
    def test_every_factor_has_non_null_score_and_confidence(self) -> None:
        result = evaluate_market(node("999999", "Commercial Building Maintenance Services"))
        self.assertEqual(len(result.factor_scores), 5)
        for score in result.factor_scores:
            self.assertIsInstance(score.raw_score, float)
            self.assertGreater(score.confidence, 0)
            self.assertTrue(score.open_gaps)

    def test_clear_exclusions_are_recorded(self) -> None:
        result = evaluate_market(node("622110", "General Medical and Surgical Hospitals"))
        self.assertEqual(result.status, "provisional_excluded")
        self.assertIn("healthcare_delivery", result.exclusion_reasons)

    def test_risk_adjustment_moves_weak_evidence_toward_neutral(self) -> None:
        result = evaluate_market(node("999999", "Commercial Building Maintenance Services"))
        raw = result.factor_scores[0].raw_score
        adjusted = result.factor_scores[0].risk_adjusted_score
        self.assertLess(adjusted, raw)
        self.assertGreater(adjusted, 45)

    def test_full_source_leaf_universe_has_no_blank_scores(self) -> None:
        leaves = [item for item in parse_naics(SOURCE) if item.level == 6]
        self.assertEqual(len(leaves), 1_012)
        results = [evaluate_market(item) for item in leaves]
        self.assertEqual(sum(len(item.factor_scores) for item in results), 5_060)
        for result in results:
            for score in result.factor_scores:
                self.assertGreaterEqual(score.raw_score, 0)
                self.assertLessEqual(score.raw_score, 100)
                self.assertEqual(score.reasoning_label, "inference")
                self.assertTrue(score.open_gaps)



if __name__ == "__main__":
    unittest.main()

