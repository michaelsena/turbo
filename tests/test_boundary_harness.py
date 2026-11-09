import copy
import unittest

from turbo.agents.boundary_harness import canonical_sha256, validate_boundary_output
from turbo.pipeline_paths import ROOT
from turbo.universe.boundary_pack import build_boundary_pack


CONFIG = ROOT / "config/universe/families/office-administrative-services-v1.json"
DIMENSIONS = {
    "buyer": "inference",
    "job": "fact",
    "delivery": "inference",
    "workforce": "assumption",
    "economics_risk": "assumption",
    "acquisition_universe": "assumption",
    "ambient_ai_workflow": "assumption",
}
CONFIDENCE = {dimension: 0.4 for dimension in DIMENSIONS}


class BoundaryHarnessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pack = build_boundary_pack(CONFIG)
        cls.evidence_id = cls.pack["evidence_catalog"][0]["evidence_id"]

    def specialist(self, role: str = "specialist-a", suffix: str = "a") -> dict:
        proposal_id = "proposal:office-administrative-services"
        proposal = {
            "proposal_id": proposal_id,
            "canonical_name": "Office administrative services",
            "definition": "Contract provision of a coordinated range of office administration services.",
            "boundary": "Includes coordinated administration; excludes single-function providers.",
            "buyer": "Organizations outsourcing coordinated office administration.",
            "job_to_be_done": "Operate recurring day-to-day administrative processes.",
            "delivery_model": "Contract or fee-based managed administrative service.",
            "workforce_model": "Administrative operations staff.",
            "economics_risk": "Not established by classification evidence.",
            "acquisition_universe": "Not established by classification evidence.",
            "ambient_ai_workflow": "Potential is an assumption pending workflow evidence.",
            "aliases": [],
            "explicit_exclusions": ["single-function providers"],
            "candidate_market_ids": [],
            "supporting_evidence_ids": [self.evidence_id],
            "counterevidence_ids": [],
            "evidence_by_dimension": DIMENSIONS,
            "confidence_by_dimension": CONFIDENCE,
        }
        identity_dispositions = [
            {
                "identity_id": identity_id,
                "disposition": "map_to_proposal",
                "proposal_id": proposal_id,
                "relationship_type": "partial_overlap",
                "rationale": "Bounded pilot fixture.",
                "evidence_label": "inference",
                "confidence": 0.4,
                "supporting_evidence_ids": [self.evidence_id],
                "counterevidence_ids": [],
                "gap_id": None,
            }
            for identity_id in self.pack["scope"]["required_disposition_identity_ids"]
        ]
        candidate_dispositions = [
            {
                "candidate_market_id": candidate["candidate_market_id"],
                "disposition": "not_resolved_in_family",
                "proposal_ids": [],
                "rationale": "The bounded fixture does not adopt this prior candidate.",
                "evidence_label": "inference",
                "confidence": 0.3,
                "supporting_evidence_ids": [self.evidence_id],
                "counterevidence_ids": [],
            }
            for candidate in self.pack["retrieved_prior_candidate_details"]
        ]
        return {
            "schema_version": 1,
            "family_id": self.pack["metadata"]["family_id"],
            "role_id": role,
            "invocation_id": f"invocation:{suffix * 24}",
            "input_pack_sha256": self.pack["metadata"]["pack_sha256"],
            "analysis_summary": "Complete bounded fixture.",
            "proposed_markets": [proposal],
            "identity_dispositions": identity_dispositions,
            "candidate_dispositions": candidate_dispositions,
            "alternatives_considered": [],
            "research_gaps": [],
        }

    def test_complete_specialist_output_passes_closed_world_validation(self) -> None:
        output = self.specialist()
        self.assertEqual(
            validate_boundary_output(
                output,
                self.pack,
                expected_role="specialist-a",
            ),
            [],
        )

    def test_missing_identity_and_invented_evidence_fail(self) -> None:
        output = self.specialist()
        missing = output["identity_dispositions"].pop()
        output["proposed_markets"][0]["supporting_evidence_ids"] = [
            "evidence:invented:000000000000000000000000"
        ]
        errors = validate_boundary_output(
            output,
            self.pack,
            expected_role="specialist-a",
        )
        self.assertTrue(
            any(missing["identity_id"] in error for error in errors),
            errors,
        )
        self.assertTrue(any("unknown supporting_evidence_ids" in error for error in errors))

    def test_provisional_disposition_requires_a_known_gap(self) -> None:
        output = self.specialist()
        disposition = output["identity_dispositions"][0]
        disposition["disposition"] = "provisional_map_to_proposal"
        disposition["gap_id"] = "gap:not-declared"
        errors = validate_boundary_output(
            output,
            self.pack,
            expected_role="specialist-a",
        )
        self.assertTrue(any("must reference a known gap" in error for error in errors))

    def test_adjudication_binds_both_exact_specialist_outputs(self) -> None:
        first = self.specialist("specialist-a", "a")
        second = self.specialist("specialist-b", "b")
        adjudication = copy.deepcopy(first)
        adjudication["role_id"] = "adjudicator"
        adjudication["invocation_id"] = f"invocation:{'c' * 24}"
        adjudication["specialist_output_sha256"] = [
            canonical_sha256(first),
            canonical_sha256(second),
        ]
        adjudication["specialist_resolution"] = [
            {
                "role_id": role,
                "assessment": "Reviewed against the same frozen pack.",
                "adopted_elements": [],
                "rejected_elements": [],
            }
            for role in ("specialist-a", "specialist-b")
        ]
        self.assertEqual(
            validate_boundary_output(
                adjudication,
                self.pack,
                expected_role="adjudicator",
                specialist_outputs=[first, second],
            ),
            [],
        )
        adjudication["specialist_output_sha256"][0] = "0" * 64
        errors = validate_boundary_output(
            adjudication,
            self.pack,
            expected_role="adjudicator",
            specialist_outputs=[first, second],
        )
        self.assertIn(
            "specialist_output_sha256 does not match specialist inputs",
            errors,
        )


if __name__ == "__main__":
    unittest.main()
