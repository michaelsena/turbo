import json
import shutil
import tempfile
import unittest
from pathlib import Path

from turbo.agents.boundary_review import validate_independent_review_run
from turbo.pipeline_paths import ROOT


BOUNDARY_CONFIG = ROOT / "config/universe/families/office-administrative-services-v1.json"
REVIEW_CONFIG = (
    ROOT
    / "config/universe/reviews/office-administrative-services-v1-boundary-review-gemini.json"
)
REVIEW_DIR = (
    ROOT / "data/agent_reviews/independent-review-e6058823bd1c604ffb36"
)


class BoundaryReviewReplayTest(unittest.TestCase):
    def test_committed_review_replays_exactly(self) -> None:
        result = validate_independent_review_run(
            REVIEW_DIR, REVIEW_CONFIG, BOUNDARY_CONFIG
        )
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["verdict"], "request_changes")
        self.assertEqual(result["finding_counts"], {"P0": 1, "P1": 2, "P2": 2})

    def test_tampered_review_fails_replay(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            copied = Path(raw_temp) / "review"
            shutil.copytree(REVIEW_DIR, copied)
            review_path = copied / "review.json"
            review = json.loads(review_path.read_text(encoding="utf-8"))
            review["confidence"] = 0.5
            review_path.write_text(
                json.dumps(review, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = validate_independent_review_run(
                copied, REVIEW_CONFIG, BOUNDARY_CONFIG
            )

        self.assertFalse(result["valid"])
        self.assertIn("review receipt output_sha256 mismatch", result["errors"])


if __name__ == "__main__":
    unittest.main()
