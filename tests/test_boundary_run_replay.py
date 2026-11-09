import json
import shutil
import tempfile
import unittest
from pathlib import Path

from turbo.agents.boundary_runner import validate_boundary_run
from turbo.pipeline_paths import ROOT


CONFIG = ROOT / "config/universe/families/office-administrative-services-v1.json"
RUN_DIR = ROOT / "data/agent_runs/boundary-run-1d9b04b683a3544c2644"
CORRECTION_CONFIG = (
    ROOT / "config/universe/families/office-administrative-services-v2.json"
)
CORRECTION_RUN_DIR = (
    ROOT / "data/agent_runs/boundary-run-1a88e9a3acdf15d63b09"
)


class BoundaryRunReplayTest(unittest.TestCase):
    def test_committed_pilot_replays_exactly(self) -> None:
        result = validate_boundary_run(RUN_DIR, CONFIG)
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["errors"], [])

    def test_tampered_run_receipt_fails_replay(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            copied = Path(raw_temp) / "run"
            shutil.copytree(RUN_DIR, copied)
            receipt_path = copied / "run-receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["adjudication_output_sha256"] = "0" * 64
            receipt_path.write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = validate_boundary_run(copied, CONFIG)

        self.assertFalse(result["valid"])
        self.assertIn("run receipt adjudication hash mismatch", result["errors"])

    def test_correction_run_replays_exactly(self) -> None:
        result = validate_boundary_run(CORRECTION_RUN_DIR, CORRECTION_CONFIG)
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(
            result["input_pack_sha256"],
            "eccc87570dc259f3cea6449a5a87455ccba4e690ccb82851e28822c3a64346e5",
        )


if __name__ == "__main__":
    unittest.main()
