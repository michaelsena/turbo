import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from turbo.agents.boundary_review import (
    REQUIRED_CHECK_IDS,
    build_review_envelope,
    run_independent_review,
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

    def test_transport_failure_persists_sanitized_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary)
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-secret"}):
                with patch(
                    "turbo.agents.boundary_review._default_transport",
                    side_effect=TimeoutError("sensitive transport detail"),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, "independent review transport failed"
                    ):
                        run_independent_review(
                            REVIEW_CONFIG,
                            BOUNDARY_CONFIG,
                            output_root=output_root,
                        )
            receipts = list(output_root.glob("*/review.receipt.json"))
            self.assertEqual(len(receipts), 1)
            receipt_text = receipts[0].read_text(encoding="utf-8")
            receipt = json.loads(receipt_text)
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["failure_stage"], "transport")
            self.assertEqual(receipt["failure_type"], "TimeoutError")
            self.assertNotIn("test-secret", receipt_text)
            self.assertNotIn("sensitive transport detail", receipt_text)

    def test_empty_provider_choices_persist_failed_receipt(self) -> None:
        response = json.dumps(
            {
                "id": "generation-without-choice",
                "model": "anthropic/claude-opus-5.5",
                "choices": [],
                "usage": {"total_tokens": 0, "cost": 0},
            }
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary)
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-secret"}):
                with patch(
                    "turbo.agents.boundary_review._default_transport",
                    return_value=(200, {}, response),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, "structured output was invalid"
                    ):
                        run_independent_review(
                            REVIEW_CONFIG,
                            BOUNDARY_CONFIG,
                            output_root=output_root,
                        )
            receipts = list(output_root.glob("*/review.receipt.json"))
            self.assertEqual(len(receipts), 1)
            receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["failure_stage"], "structured_output_parse")
            self.assertEqual(receipt["failure_type"], "RuntimeError")
            self.assertEqual(receipt["generation_id"], "generation-without-choice")


if __name__ == "__main__":
    unittest.main()
