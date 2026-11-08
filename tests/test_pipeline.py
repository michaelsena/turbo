import unittest
from unittest.mock import patch

from turbo.pipeline import RUNS, run


class PipelineTest(unittest.TestCase):
    def test_run_fails_closed_when_source_validation_fails(self) -> None:
        with patch("turbo.pipeline.validate", return_value=["tampered NAPCS snapshot"]):
            with self.assertRaisesRegex(ValueError, "tampered NAPCS snapshot"):
                run()

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


if __name__ == "__main__":
    unittest.main()

