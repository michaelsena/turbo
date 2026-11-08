import unittest

from turbo.pipeline import RUNS, run


class PipelineTest(unittest.TestCase):
    def test_replay_reuses_same_immutable_run(self) -> None:
        first = run()
        receipt = RUNS / first["run_id"] / "run-receipt.json"
        before = receipt.read_bytes()
        second = run()
        after = receipt.read_bytes()
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(before, after)
        self.assertEqual(first["blank_factor_scores"], 0)


if __name__ == "__main__":
    unittest.main()

