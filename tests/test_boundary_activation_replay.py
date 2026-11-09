import json
import shutil
import tempfile
import unittest
from pathlib import Path

from turbo.pipeline_paths import ROOT
from turbo.universe.boundary_activation import validate_boundary_activation


ACTIVATION_CONFIG = (
    ROOT / "config/universe/activations/office-administrative-services-v2.json"
)
ACTIVATION_DIR = (
    ROOT
    / "data/market_graph/activations/boundary-activation-9d3772f0364b4632dc62"
)


class BoundaryActivationReplayTest(unittest.TestCase):
    def test_committed_activation_replays_exactly(self) -> None:
        result = validate_boundary_activation(ACTIVATION_DIR, ACTIVATION_CONFIG)
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["market_count"], 3)
        self.assertEqual(
            result["event_counts"],
            {"create_market": 3, "map": 1, "reject_candidate": 0},
        )

    def test_tampered_event_fails_replay(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            copied = Path(raw_temp) / "activation"
            shutil.copytree(ACTIVATION_DIR, copied)
            events_path = copied / "events.json"
            events = json.loads(events_path.read_text(encoding="utf-8"))
            events[0]["activation_status"] = "final"
            events_path.write_text(
                json.dumps(events, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = validate_boundary_activation(copied, ACTIVATION_CONFIG)

        self.assertFalse(result["valid"])
        self.assertIn(
            "persisted events do not match deterministic compilation",
            result["errors"],
        )


if __name__ == "__main__":
    unittest.main()
