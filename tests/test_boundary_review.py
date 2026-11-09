import unittest

from turbo.agents.boundary_review import (
    REQUIRED_CHECK_IDS,
    build_review_envelope,
    validate_review_output,
)
from turbo.pipeline_paths import ROOT


BOUNDARY_CONFIG = ROOT / "config/universe/families/office-administrative-services-v1.json"
REVIEW_CONFIG = (
    ROOT
    / "config/universe/reviews/office-administrative-services-v1-boundary-review.json"
)


class BoundaryIndependentReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.envelope = build_review_envelope(REVIEW_CONFIG, BOUNDARY_CONFIG)

    def valid_output(self) -> dict[str, object]:
        config = self.envelope["review_config"]
        evidence_id = self.envelope["frozen_evidence_pack"]["evidence_catalog"][0][
            "evidence_id"
        ]
        return {
            "schema_version": 1,
            "review_id": config["review_id"],
            "target_run_id": config["target_run_id"],
            "target_pack_sha256": config["target_pack_sha256"],
            "target_adjudication_sha256": config["target_adjudication_sha256"],
            "verdict": "approve_activation",
            "summary": "Every registered review check passes.",
            "confidence": 0.8,
            "checks": [
                {
                    "check_id": check_id,
                    "status": "pass",
                    "rationale": "The frozen evidence and output agree.",
                    "evidence_ids": [evidence_id],
                }
                for check_id in sorted(REQUIRED_CHECK_IDS)
            ],
            "findings": [],
            "activation_conditions": [],
            "alternatives_considered": ["Request changes."],
        }

    def test_preregistered_review_envelope_is_exact(self) -> None:
        self.assertEqual(
            self.envelope["target_run_receipt"]["boundary_run_id"],
            "boundary-run-1d9b04b683a3544c2644",
        )
        self.assertEqual(len(self.envelope["review_input_sha256"]), 64)

    def test_complete_zero_finding_approval_validates(self) -> None:
        self.assertEqual(validate_review_output(self.valid_output(), self.envelope), [])

    def test_approval_fails_with_nonpassing_check_or_finding(self) -> None:
        output = self.valid_output()
        output["checks"][0]["status"] = "uncertain"
        output["findings"] = [
            {
                "finding_id": "review-finding:scope-ambiguity",
                "severity": "P1",
                "category": "scope",
                "summary": "Scope is ambiguous.",
                "detail": "The disposition could affect global state.",
                "affected_output_paths": ["candidate_dispositions"],
                "evidence_ids": [],
                "recommendation": "Define family-local semantics.",
            }
        ]
        errors = validate_review_output(output, self.envelope)
        self.assertIn("approval requires zero findings and every check passing", errors)


if __name__ == "__main__":
    unittest.main()
