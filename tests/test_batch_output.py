"""B3 output-contract tests; every synthetic answer remains unactivated.

The semantic matrix calls the pure validator with a context constructed from real
verified V2 preparations. Public and CLI integrations separately rebuild context,
exercise exact input binding, and reject malformed output bytes.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from turbo.agents import batch_output
from turbo.pipeline_paths import ROOT
from turbo.agents.boundary_harness import canonical_sha256
from turbo.universe.family_pack_v2 import _canonical_bytes, _pack_hash, _preparation_receipt
from turbo.universe.family_pack_v2 import prepare_family_v2


REQUEST = "request-test-1"
INVOCATION = "invocation:" + "a" * 24
FAMILIES = ["family:coverage:napcs-collection:10:001",
            "family:coverage:prior-candidate:global-challenger:001"]
DIMENSIONS = ["buyer", "job", "delivery", "workforce", "economics_risk",
              "acquisition_universe", "ambient_ai_workflow"]


def evidence_for(family, subject):
    return next(row["evidence_id"] for row in family["evidence_catalog"]
                if subject in row["subject_ids"])


def unresolved_output(context):
    output = {
        "schema_version": 1, "contract_version": "batch-primary-v1", "role_id": "batch_primary",
        "request_id": context["request_id"], "invocation_id": context["invocation_id"],
        "context_sha256": context["context_sha256"],
        "output_schema_sha256": context["output_schema_sha256"], "prompt_sha256": context["prompt_sha256"],
        "families": [],
    }
    for family in context["families"]:
        result = {key: family[key] for key in ("family_id", "preparation_id", "input_pack_sha256")}
        result.update(analysis_summary="Synthetic unresolved fixture; no market decision.",
                      proposed_markets=[], identity_dispositions=[], candidate_dispositions=[], research_gaps=[])
        for kind, key, subjects in (
            ("identity", "identity_id", family["required_identity_ids"]),
            ("candidate", "candidate_market_id", family["required_candidate_ids"]),
        ):
            for number, subject in enumerate(subjects):
                evidence = [evidence_for(family, subject)]
                gap_id = family["gap_id_prefix"] + f"{kind}-{number}"
                result[kind + "_dispositions"].append({
                    key: subject, "disposition": "unresolved", "proposal_ids": [],
                    "rationale": "Synthetic fixture retains the unresolved subject.",
                    "evidence_label": "unknown", "confidence": 0,
                    "supporting_evidence_ids": evidence, "counterevidence_ids": [], "gap_id": gap_id,
                })
                result["research_gaps"].append({
                    "gap_id": gap_id, "question": "What operating boundary applies?",
                    "affected_identity_ids": [subject] if kind == "identity" else [],
                    "affected_candidate_ids": [subject] if kind == "candidate" else [],
                    "current_judgment": "Unresolved synthetic fixture.", "evidence_label": "unknown",
                    "confidence": 0, "retry_trigger": "Additional verified operating-boundary evidence arrives.",
                    "supporting_evidence_ids": evidence, "counterevidence_ids": [],
                })
        output["families"].append(result)
    return output


def proposal(family, subject, suffix):
    evidence = [evidence_for(family, subject)]
    return {
        "proposal_id": family["proposal_id_prefix"] + suffix,
        "canonical_name": "Synthetic operating market " + suffix,
        "definition": "A synthetic fixture used only to test proposal linkage.",
        "boundary": "Only the explicitly reviewed subject is included.",
        "dimensions": {dimension: {
            "statement": "Synthetic operating identity statement.",
            "evidence_label": "inference", "confidence": 0.5,
            "supporting_evidence_ids": evidence, "counterevidence_ids": [],
        } for dimension in DIMENSIONS},
        "explicit_exclusions": ["Unreviewed adjacent operating activities."],
        "related_graph_market_ids": [], "supporting_evidence_ids": evidence,
        "counterevidence_ids": [],
    }


class BatchOutputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix="turbo-output-inputs-")
        cls.preparations = []
        for family_id in FAMILIES:
            receipt = prepare_family_v2(family_id, root=ROOT, output_root=Path(cls.fixture.name))
            cls.preparations.append(Path(receipt["preparation_path"]))
        cls.context = batch_output.build_batch_context(
            cls.preparations, request_id=REQUEST, invocation_id=INVOCATION, root=ROOT
        )
        cls.baseline = unresolved_output(cls.context)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.output = copy.deepcopy(self.baseline)
        self.temporary = tempfile.TemporaryDirectory(prefix="turbo-output-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "output.json"

    def errors(self, output=None):
        return batch_output._validate_against_context(
            self.output if output is None else output, self.context, root=ROOT
        )

    def validate_public(self, output=None, **overrides):
        options = {"expected_request_id": REQUEST, "expected_invocation_id": INVOCATION, "root": ROOT}
        options.update(overrides)
        return batch_output.validate_batch_output(
            self.output if output is None else output, self.preparations, **options
        )

    def map_identity(self):
        family = self.output["families"][0]
        row = family["identity_dispositions"][0]
        market = proposal(self.context["families"][0], row["identity_id"], "one")
        family["proposed_markets"] = [market]
        family["research_gaps"] = []
        row.update(disposition="map_to_proposals", proposal_ids=[market["proposal_id"]],
                   evidence_label="inference", confidence=0.5, gap_id=None)
        return family, row, market

    def map_candidate(self, disposition="adopt", count=1):
        family = self.output["families"][1]
        row = family["candidate_dispositions"][0]
        family["research_gaps"] = [gap for gap in family["research_gaps"] if gap["gap_id"] != row["gap_id"]]
        markets = [proposal(self.context["families"][1], row["candidate_market_id"], f"market-{index}")
                   for index in range(count)]
        family["proposed_markets"] = markets
        row.update(disposition=disposition, proposal_ids=[market["proposal_id"] for market in markets],
                   evidence_label="inference", confidence=0.5, gap_id=None)
        return family, row, markets

    def test_all_unresolved_and_candidates_only_zero_proposals_are_valid(self):
        self.assertEqual(self.errors(), [])
        candidate_family = self.output["families"][1]
        self.assertEqual(candidate_family["identity_dispositions"], [])
        self.assertEqual(candidate_family["proposed_markets"], [])
        self.assertEqual(len(candidate_family["candidate_dispositions"]), 58)
        result = self.validate_public()
        self.assertTrue(result["valid"], result)

    def test_context_preserves_manifest_order_and_subject_evidence_ownership(self):
        self.assertEqual([family["family_id"] for family in self.context["families"]], FAMILIES)
        for family in self.context["families"]:
            evidence_ids = [row["evidence_id"] for row in family["evidence_catalog"]]
            self.assertEqual(len(evidence_ids), len(set(evidence_ids)))
            self.assertTrue(all(row["json_pointer"] and row["item_sha256"] for row in family["evidence_catalog"]))
            for subject in family["required_identity_ids"] + family["required_candidate_ids"]:
                self.assertTrue(evidence_for(family, subject))

    def test_required_subjects_and_families_are_complete_exactly_once(self):
        mutations = [
            lambda out: out["families"].pop(),
            lambda out: out["families"].append(copy.deepcopy(out["families"][0])),
            lambda out: out["families"][0]["identity_dispositions"].clear(),
            lambda out: out["families"][0]["identity_dispositions"].append(copy.deepcopy(out["families"][0]["identity_dispositions"][0])),
            lambda out: out["families"][1]["candidate_dispositions"].pop(),
            lambda out: out["families"][1]["candidate_dispositions"].append(copy.deepcopy(out["families"][1]["candidate_dispositions"][0])),
        ]
        for mutation in mutations:
            output = copy.deepcopy(self.baseline)
            mutation(output)
            with self.subTest(mutation=mutation):
                self.assertTrue(self.errors(output))

    def test_context_subjects_must_not_become_primary_dispositions(self):
        context_family = self.context["families"][0]
        self.assertTrue(context_family["context_identity_ids"])
        self.assertTrue(context_family["context_candidate_ids"])
        for field, key, context_id in (
            ("identity_dispositions", "identity_id", context_family["context_identity_ids"][0]),
            ("candidate_dispositions", "candidate_market_id", context_family["context_candidate_ids"][0]),
        ):
            output = copy.deepcopy(self.baseline)
            row = copy.deepcopy(output["families"][0]["identity_dispositions"][0])
            row.pop("identity_id")
            row[key] = context_id
            output["families"][0][field].append(row)
            with self.subTest(field=field):
                self.assertTrue(self.errors(output))

    def test_evidence_must_exist_in_own_family_and_support_own_subject(self):
        first = self.context["families"][0]
        second = self.context["families"][1]
        wrong_subject = second["required_candidate_ids"][1]
        bad_refs = ["evidence:invented", second["evidence_catalog"][0]["evidence_id"]]
        for ref in bad_refs:
            output = copy.deepcopy(self.baseline)
            output["families"][0]["identity_dispositions"][0]["supporting_evidence_ids"] = [ref]
            with self.subTest(ref=ref):
                self.assertTrue(self.errors(output))
        row = self.output["families"][1]["candidate_dispositions"][0]
        row["supporting_evidence_ids"] = [evidence_for(second, wrong_subject)]
        self.assertTrue(self.errors())

    def test_request_invocation_context_schema_prompt_and_family_bindings_are_external(self):
        for field in ("request_id", "invocation_id", "context_sha256", "output_schema_sha256", "prompt_sha256"):
            output = copy.deepcopy(self.baseline)
            output[field] = "0" * 64
            with self.subTest(field=field):
                self.assertTrue(self.errors(output))
        for field in ("preparation_id", "input_pack_sha256"):
            output = copy.deepcopy(self.baseline)
            output["families"][0][field] = "0" * 64
            with self.subTest(field=field):
                self.assertTrue(self.errors(output))
        result = self.validate_public(expected_request_id="another-request")
        self.assertFalse(result["valid"])

    def test_mapping_proposals_have_valid_cardinality_and_no_orphans(self):
        self.map_identity()
        self.assertEqual(self.errors(), [])
        self.output["families"][0]["identity_dispositions"][0]["proposal_ids"] = []
        self.assertTrue(self.errors())
        for disposition, count in (("adopt", 1), ("change", 1), ("merge_input", 1), ("split_input", 2)):
            self.output = copy.deepcopy(self.baseline)
            family, row, markets = self.map_candidate(disposition, count)
            with self.subTest(disposition=disposition, valid=True):
                self.assertEqual(self.errors(), [])
            row["proposal_ids"] = [] if count == 1 else row["proposal_ids"][:1]
            with self.subTest(disposition=disposition, valid=False):
                self.assertTrue(self.errors())
        self.output = copy.deepcopy(self.baseline)
        self.map_identity()
        self.output["families"][0]["proposed_markets"].append(
            proposal(self.context["families"][0], self.context["families"][0]["required_identity_ids"][0], "orphan"))
        self.assertTrue(self.errors())

    def test_nonmapping_outcomes_forbid_proposal_links(self):
        family, row, _ = self.map_identity()
        for disposition in ("no_mapping_to_family", "non_market_source_identity", "unresolved"):
            row["disposition"] = disposition
            with self.subTest(disposition=disposition):
                self.assertTrue(self.errors())
        self.output = copy.deepcopy(self.baseline)
        _, row, _ = self.map_candidate()
        for disposition in ("reject", "unresolved"):
            row["disposition"] = disposition
            with self.subTest(disposition=disposition):
                self.assertTrue(self.errors())

    def test_unknown_proposals_graph_references_and_cross_family_links_reject(self):
        family, row, market = self.map_identity()
        row["proposal_ids"] = [self.context["families"][1]["proposal_id_prefix"] + "foreign"]
        self.assertTrue(self.errors())
        row["proposal_ids"] = [market["proposal_id"]]
        market["related_graph_market_ids"] = ["market:unverified"]
        self.assertTrue(self.errors())
        market["related_graph_market_ids"] = []
        market["proposal_id"] = self.context["families"][1]["proposal_id_prefix"] + "foreign"
        row["proposal_ids"] = [market["proposal_id"]]
        self.assertTrue(self.errors())

    def test_gaps_must_apply_to_subject_and_have_retry_triggers(self):
        mutations = [
            lambda out: out["families"][0]["identity_dispositions"][0].update(gap_id=None),
            lambda out: out["families"][0]["identity_dispositions"][0].update(gap_id="gap:unknown"),
            lambda out: out["families"][0]["research_gaps"][0].update(affected_identity_ids=[]),
            lambda out: out["families"][0]["research_gaps"][0].update(retry_trigger=" "),
            lambda out: out["families"][1]["research_gaps"][0].update(affected_candidate_ids=[self.context["families"][1]["required_candidate_ids"][1]]),
            lambda out: out["families"][0]["research_gaps"][0].update(affected_candidate_ids=[self.context["families"][1]["required_candidate_ids"][0]]),
        ]
        for mutation in mutations:
            output = copy.deepcopy(self.baseline)
            mutation(output)
            with self.subTest(mutation=mutation):
                self.assertTrue(self.errors(output))

    def test_provisional_and_unknown_claims_require_applicable_gaps(self):
        family, row, _ = self.map_identity()
        row["disposition"] = "provisional_map_to_proposals"
        self.assertTrue(self.errors())
        family["research_gaps"] = copy.deepcopy(self.baseline["families"][0]["research_gaps"])
        row["gap_id"] = family["research_gaps"][0]["gap_id"]
        self.assertEqual(self.errors(), [])
        row["disposition"] = "map_to_proposals"
        row["evidence_label"] = "unknown"
        row["gap_id"] = None
        self.assertTrue(self.errors())

    def test_confidence_and_evidence_labels_are_strict_but_finite_fractions_valid(self):
        for confidence in (0, 0.25, 1):
            self.output["families"][0]["identity_dispositions"][0]["confidence"] = confidence
            with self.subTest(valid_confidence=confidence):
                self.assertEqual(self.errors(), [])
        for confidence in (True, False, -0.1, 1.1, math.nan, math.inf, -math.inf, "0.5", None):
            self.output["families"][0]["identity_dispositions"][0]["confidence"] = confidence
            with self.subTest(invalid_confidence=repr(confidence)):
                self.assertTrue(self.errors())
        self.output = copy.deepcopy(self.baseline)
        for label in ("fact", "inference", "assumption", "unknown"):
            self.output["families"][0]["identity_dispositions"][0]["evidence_label"] = label
            self.assertEqual(self.errors(), [])
        self.output["families"][0]["identity_dispositions"][0]["evidence_label"] = "probably"
        self.assertTrue(self.errors())

    def test_proposal_dimensions_require_finite_confidence_and_family_evidence(self):
        family, row, market = self.map_identity()
        self.assertEqual(self.errors(), [])
        dimension = market["dimensions"]["buyer"]
        dimension["confidence"] = True
        self.assertTrue(self.errors())
        dimension["confidence"] = 0.5
        dimension["supporting_evidence_ids"] = [self.context["families"][1]["evidence_catalog"][0]["evidence_id"]]
        self.assertTrue(self.errors())
        dimension["supporting_evidence_ids"] = row["supporting_evidence_ids"]
        dimension["evidence_label"] = "unknown"
        self.assertTrue(self.errors())

    def test_malformed_nested_types_return_errors_instead_of_exceptions(self):
        for output in ([], None, 42, "text"):
            with self.subTest(top_level=output):
                self.assertTrue(batch_output._validate_against_context(output, self.context, root=ROOT))
        for field in ("families",):
            for value in ({}, None, "text"):
                output = copy.deepcopy(self.baseline)
                output[field] = value
                self.assertTrue(self.errors(output))
        for field in ("proposed_markets", "identity_dispositions", "candidate_dispositions", "research_gaps"):
            output = copy.deepcopy(self.baseline)
            output["families"][0][field] = {"malformed": True}
            with self.subTest(field=field):
                self.assertTrue(self.errors(output))

    def test_changed_preparation_bytes_fail_public_regeneration(self):
        path = self.preparations[0] / "family-evidence-pack-v2.json"
        original = path.read_bytes()
        try:
            path.write_bytes(original + b" ")
            result = self.validate_public()
            self.assertFalse(result["valid"], result)
        finally:
            path.write_bytes(original)

    def test_canonical_self_rehashed_preparation_cannot_replace_verified_evidence(self):
        original = self.preparations[1]
        config = json.loads((original / "family-config-v2.json").read_text())
        pack = json.loads((original / "family-evidence-pack-v2.json").read_text())
        pack["required_candidate_cards"][0]["name"] = "Invented replacement evidence"
        pack["metadata"]["pack_sha256"] = _pack_hash(pack)
        preparation_id = "family-preparation:" + canonical_sha256({
            "config_sha256": canonical_sha256(config), "pack_sha256": pack["metadata"]["pack_sha256"],
        })[:24]
        forged = Path(self.temporary.name) / preparation_id
        forged.mkdir()
        (forged / "family-config-v2.json").write_bytes(_canonical_bytes(config))
        (forged / "family-evidence-pack-v2.json").write_bytes(_canonical_bytes(pack))
        (forged / "preparation-receipt.json").write_bytes(
            _canonical_bytes(_preparation_receipt(preparation_id, config, pack)))
        with self.assertRaises(ValueError):
            batch_output.build_batch_context([self.preparations[0], forged],
                request_id=REQUEST, invocation_id=INVOCATION, root=ROOT)

    def test_supplementary_gap_can_remain_after_resolved_mapping(self):
        family, _, _ = self.map_identity()
        family["research_gaps"] = copy.deepcopy(self.baseline["families"][0]["research_gaps"])
        self.assertEqual(self.errors(), [])
        gap = family["research_gaps"][0]
        gap["affected_identity_ids"] = [self.context["families"][0]["context_identity_ids"][0]]
        self.assertTrue(self.errors())
        gap["affected_identity_ids"] = []
        self.assertTrue(self.errors())

    def validate_file(self, raw, **overrides):
        self.path.write_bytes(raw)
        options = {"expected_request_id": REQUEST, "expected_invocation_id": INVOCATION, "root": ROOT}
        options.update(overrides)
        return batch_output.validate_batch_output_file(self.path, self.preparations, **options)

    def test_output_file_rejects_duplicate_keys_nonfinite_json_and_trailing_documents(self):
        valid = json.dumps(self.baseline, separators=(",", ":")).encode()
        malformed = [
            b'{"schema_version":1,' + valid[1:],
            valid.replace(b'"confidence":0', b'"confidence":0,"confidence":0', 1),
            valid.replace(b'"confidence":0', b'"confidence":NaN', 1),
            valid.replace(b'"confidence":0', b'"confidence":Infinity', 1),
            valid + b"\n{}", b"\xff", b"null", b"[]",
        ]
        for raw in malformed:
            with self.subTest(prefix=raw[:60]):
                result = self.validate_file(raw)
                self.assertFalse(result["valid"], result)
        result = self.validate_file(valid)
        self.assertTrue(result["valid"], result)

    def test_raw_output_byte_cap_is_checked_before_parsing(self):
        raw = json.dumps(self.baseline, separators=(",", ":")).encode()
        result = self.validate_file(b" " * 100 + raw, max_output_bytes=len(raw))
        self.assertFalse(result["valid"], result)

    def test_context_build_rejects_input_order_and_enforces_context_byte_cap(self):
        with self.assertRaises(ValueError):
            batch_output.build_batch_context(list(reversed(self.preparations)),
                request_id=REQUEST, invocation_id=INVOCATION, root=ROOT)
        with self.assertRaises(ValueError):
            batch_output.build_batch_context(self.preparations, request_id=REQUEST,
                invocation_id=INVOCATION, root=ROOT, max_context_bytes=10)

    def invoke_cli(self, *arguments):
        from turbo.cli import main
        output = io.StringIO()
        with patch("sys.argv", ["turbo", *map(str, arguments)]), contextlib.redirect_stdout(output):
            code = main()
        return code, json.loads(output.getvalue())

    def test_cli_context_and_output_validation_are_read_only(self):
        self.path.write_text(json.dumps(self.baseline))
        before = {str(p): p.read_bytes() for directory in self.preparations
                  for p in directory.iterdir() if p.is_file()}
        output_before = self.path.read_bytes()
        paths_before = sorted(Path(self.temporary.name).rglob("*"))
        code, context = self.invoke_cli("batch-output-context", REQUEST, INVOCATION, *self.preparations)
        self.assertEqual(code, 0, context)
        self.assertEqual(context, self.context)
        code, result = self.invoke_cli("batch-output-validate", self.path, REQUEST, INVOCATION, *self.preparations)
        self.assertEqual(code, 0, result)
        self.assertTrue(result["valid"])
        self.assertTrue(result["structural_validation_only"])
        self.assertFalse(result["model_invoked"])
        self.assertEqual(self.path.read_bytes(), output_before)
        self.assertEqual(sorted(Path(self.temporary.name).rglob("*")), paths_before)
        self.assertEqual({str(p): p.read_bytes() for directory in self.preparations
                          for p in directory.iterdir() if p.is_file()}, before)

    def test_cli_malformed_json_and_missing_inputs_return_structured_failures(self):
        for raw in (b"not-json", b'{"confidence":NaN}', b'{"key":1,"key":2}'):
            self.path.write_bytes(raw)
            code, result = self.invoke_cli("batch-output-validate", self.path, REQUEST, INVOCATION, *self.preparations)
            self.assertEqual(code, 1)
            self.assertFalse(result["valid"])
        missing = Path(self.temporary.name) / "absent"
        code, result = self.invoke_cli("batch-output-context", REQUEST, INVOCATION, missing, *self.preparations[:1])
        self.assertEqual(code, 1)
        self.assertFalse(result["valid"])
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
