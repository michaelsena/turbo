import json
import tempfile
import unittest
from pathlib import Path

from turbo.pipeline_paths import ROOT
from turbo.universe.boundary_activation import compile_boundary_activation


ACTIVATION_CONFIG = (
    ROOT / "config/universe/activations/office-administrative-services-v2.json"
)
EXECUTION_COMMIT = "1" * 40


class BoundaryActivationTest(unittest.TestCase):
    def test_approved_proposal_compiles_without_broadening_scope(self) -> None:
        compiled = compile_boundary_activation(
            ACTIVATION_CONFIG, execution_commit=EXECUTION_COMMIT
        )
        events = compiled["events"]
        self.assertEqual(
            [event["event_type"] for event in events],
            ["create_market", "create_market", "create_market", "map"],
        )
        self.assertFalse(
            any(event["event_type"] == "reject_candidate" for event in events)
        )
        self.assertEqual(len(compiled["projection"]["markets"]), 3)
        self.assertEqual(len(compiled["projection"]["mappings"]), 1)
        statuses = {
            market["proposal_id"]: market["activation_status"]
            for market in compiled["projection"]["markets"]
        }
        self.assertEqual(
            statuses,
            {
                "proposal:integrated-outsourced-office-administration": "accepted_with_open_gaps",
                "proposal:medical-practice-administration": "provisional",
                "proposal:dental-practice-administration": "provisional",
            },
        )
        mapping = compiled["projection"]["mappings"][0]
        self.assertEqual(mapping["identity_id"], "identity:naics:561110")
        self.assertEqual(mapping["activation_status"], "provisional")
        self.assertEqual(
            mapping["research_gap_ids"], ["gap:vertical-administration-boundary"]
        )

    def test_candidate_rejection_policy_cannot_be_enabled(self) -> None:
        config = json.loads(ACTIVATION_CONFIG.read_text(encoding="utf-8"))
        config["candidate_disposition_policy"]["emit_reject_candidate_events"] = True
        with tempfile.TemporaryDirectory() as raw_temp:
            path = Path(raw_temp) / "activation.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, "preserve family-local candidate non-mappings"
            ):
                compile_boundary_activation(path, execution_commit=EXECUTION_COMMIT)


if __name__ == "__main__":
    unittest.main()
