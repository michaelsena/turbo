"""Selective batch review: preregistered targeting and conditional escalation.

The two-family context comes from verified frozen V2 preparations. Transition
unit tests isolate only expensive context rebuilding; immutable stage, policy,
output, review, and hash checks remain real.
"""
from __future__ import annotations

import copy
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from turbo.agents import batch_workflow
from turbo.agents.batch_output import build_batch_context
from turbo.pipeline_paths import ROOT
from turbo.universe.family_pack_v2 import prepare_family_v2
from test_batch_output import unresolved_output, proposal, FAMILIES

REQUEST = "workflow-test"
INVOCATION = "invocation:" + "c" * 24
ACTORS = {role: "actor-" + role for role in
          ("primary", "verifier", "escalation_a", "escalation_b", "adjudicator", "release_reviewer")}


class BatchWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix="turbo-workflow-inputs-")
        frozen = Path("/tmp/turbo-live-batch-work")
        summary = Path("/tmp/turbo-first-real-batch/summary.json")
        if frozen.exists() and summary.exists():
            cls.input_root = frozen
            by_family = {row["family_id"]: Path(row["preparation_path"])
                         for row in json.loads(summary.read_text())["families"]}
            cls.preparations = [by_family[family] for family in FAMILIES]
        else:
            cls.input_root = ROOT
            cls.preparations = [Path(prepare_family_v2(family, root=ROOT,
                output_root=Path(cls.fixture.name))["preparation_path"]) for family in FAMILIES]
        cls.context = build_batch_context(cls.preparations, root=cls.input_root,
            request_id=REQUEST, invocation_id=INVOCATION)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="turbo-workflow-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve() / "workflow"
        if self._testMethodName != "test_real_routine_agreement_skips_escalation_and_retains_retry_gaps":
            isolation = patch.object(batch_workflow, "build_batch_context",
                                     side_effect=lambda *args, **kwargs: copy.deepcopy(self.context))
            isolation.start()
            self.addCleanup(isolation.stop)

    def initialize(self, **changes):
        arguments = dict(input_root=self.input_root, request_id=REQUEST,
                         invocation_id=INVOCATION, actors=copy.deepcopy(ACTORS))
        arguments.update(changes)
        return batch_workflow.initialize_workflow(self.directory, self.preparations, **arguments)

    def submit(self, role, document, actor=None):
        return batch_workflow.submit(self.directory, role, actor or ACTORS[role], document)

    def payload(self):
        return unresolved_output(copy.deepcopy(self.context))

    def files(self):
        return {str(p.relative_to(self.directory)): p.read_bytes()
                for p in self.directory.rglob("*") if p.is_file()}


    def test_role_actors_must_be_distinct(self):
        actors = copy.deepcopy(ACTORS)
        actors["verifier"] = actors["primary"]
        with self.assertRaises(ValueError):
            self.initialize(actors=actors)
        self.assertFalse(self.directory.exists())

    def test_policy_is_preregistered_and_cannot_be_changed(self):
        policy = copy.deepcopy(batch_workflow.CANARY_POLICY)
        policy["undeclared_override"] = True
        with self.assertRaises(ValueError):
            self.initialize(policy=policy)
        self.initialize()
        self.submit("primary", {"payload": self.payload()})
        path = self.directory / "plan.json"
        plan = json.loads(path.read_bytes())
        plan["policy"] = policy
        plan["plan_sha256"] = batch_workflow._hash({key: value for key, value in plan.items()
                                                   if key != "plan_sha256"})
        path.write_text(json.dumps(plan))
        with self.assertRaises(ValueError):
            batch_workflow.inspect_workflow(self.directory)

    def test_cannot_skip_primary_or_verification(self):
        self.initialize()
        for role in ("verifier", "escalation_a", "adjudicator", "release_reviewer"):
            with self.subTest(role=role), self.assertRaises(ValueError):
                batch_workflow.assignment(self.directory, role)
        self.submit("primary", {"payload": self.payload()})
        for role in ("escalation_a", "adjudicator", "release_reviewer"):
            with self.subTest(role=role), self.assertRaises(ValueError):
                batch_workflow.assignment(self.directory, role)

    def test_submission_hash_bindings_and_idempotent_resume(self):
        self.initialize()
        document = {"payload": self.payload()}
        first = self.submit("primary", document)
        before = self.files()
        self.assertEqual(first, self.submit("primary", copy.deepcopy(document)))
        self.assertEqual(before, self.files())
        document["payload"]["families"][0]["analysis_summary"] = "Replacement"
        with self.assertRaises(ValueError):
            self.submit("primary", document)
        path = self.directory / "primary.json"
        envelope = json.loads(path.read_bytes())
        envelope["submission_sha256"] = "0" * 64
        path.write_text(json.dumps(envelope))
        with self.assertRaises(ValueError):
            batch_workflow.inspect_workflow(self.directory)

    def test_wrong_actor_old_artifact_and_wrong_context_are_rejected(self):
        self.initialize()
        with self.assertRaises(ValueError):
            self.submit("primary", {"payload": self.payload()}, actor=ACTORS["verifier"])
        for document in ({"kind": "batch_research_artifact_v1"}, self.payload(), {"refusal": "No answer"}):
            with self.subTest(document=document), self.assertRaises(ValueError):
                self.submit("primary", document)
        for field in ("context_sha256", "request_id", "invocation_id"):
            payload = self.payload()
            payload[field] = "incorrect"
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.submit("primary", {"payload": payload})

    def adjudication_document(self, submissions):
        return {"payload": self.payload(),
                "input_hashes": {role: receipt["submission_sha256"]
                                 for role, receipt in submissions.items()},
                "comparisons": [
                    {"family_id": family["family_id"], "subject_id": subject,
                     "subject_kind": kind,
                     "rationale": "Compared the independently submitted interpretations and retained an explicit gap."}
                    for family in self.context["families"]
                    for kind, key in (("identity", "required_identity_ids"),
                                      ("candidate", "required_candidate_ids"))
                    for subject in family[key]],
                "proposal_comparisons": []}

    def high_confidence_no_movement_payload(self):
        payload = self.payload()
        for family in payload["families"]:
            family["research_gaps"] = []
            for key, disposition in (("identity_dispositions", "no_mapping_to_family"),
                                     ("candidate_dispositions", "reject")):
                for row in family[key]:
                    row.update(disposition=disposition, evidence_label="fact", confidence=1.0, gap_id=None)
        return payload

    def review_document(self, submissions, preview, *, verdict="approve", findings=None):
        return {"input_hashes": {role: receipt["submission_sha256"]
                                 for role, receipt in submissions.items()},
                "approved_plan_sha256": preview["preview_sha256"], "verdict": verdict,
                "findings": findings or [],
                "checks": {name: "pass" for name in (
                    "coverage", "operating_identity", "evidence",
                    "cross_family_conflicts", "closure_outcomes")}}

    def verification_document(self, primary, *, disagree=False):
        assignment = batch_workflow.assignment(self.directory, "verifier")
        families = {family["family_id"]: family for family in self.context["families"]}
        assessments = []
        for target in assignment["targets"]:
            family = families[target["family_id"]]
            evidence = next(item["evidence_id"] for item in family["evidence_catalog"]
                            if target["target_id"] in item["subject_ids"])
            assessments.append({key: target[key] for key in ("family_id", "target_kind", "target_id")} | {
                "verdict": "agree", "rationale": "Independently checked the frozen subject evidence.",
                "supporting_evidence_ids": [evidence]})
        if disagree:
            assessments[0]["verdict"] = "material_disagreement"
        return {"input_hashes": {"primary": primary["submission_sha256"]}, "assessments": assessments}

    def verified(self, *, disagree=False):
        primary = self.submit("primary", {"payload": self.payload()})
        verifier = self.submit("verifier", self.verification_document(primary, disagree=disagree))
        return {"primary": primary, "verifier": verifier}

    def unit_preview(self):
        stage = batch_workflow.verified_stage(self.directory)
        return batch_workflow.bind_release_preview(self.directory, {
            "graph_base_sha256": self.context["families"][0]["pack_metadata"]["graph_projection_sha256"],
            "workflow_plan_sha256": stage["plan"]["plan_sha256"],
            "final_submission_sha256": stage["final_submission_sha256"],
            "movements": [], "closure_outcomes": []})

    def test_confident_no_movement_has_only_preregistered_qa_not_all_evidence_subjects(self):
        plan = self.initialize()
        self.submit("primary", {"payload": self.high_confidence_no_movement_payload()})
        selected = batch_workflow.assignment(self.directory, "verifier")["targets"]
        actual = {(r["family_id"], r["target_kind"], r["target_id"]) for r in selected}
        self.assertEqual(actual, {tuple(row) for row in plan["qa_targets"]})
        self.assertLess(len(actual), 59)
        self.assertTrue(all(row["reasons"] == ["preregistered_qa"] for row in selected))
        path = self.directory / "plan.json"
        tampered = json.loads(path.read_bytes())
        tampered["qa_targets"] = []
        tampered["plan_sha256"] = batch_workflow._hash({k: v for k, v in tampered.items() if k != "plan_sha256"})
        path.write_text(json.dumps(tampered))
        with self.assertRaises(ValueError):
            batch_workflow.inspect_workflow(self.directory)

    def test_selector_includes_graph_movements_weak_conflicts_and_qa(self):
        plan = self.initialize()
        payload = self.high_confidence_no_movement_payload()
        family = payload["families"][0]
        identity = family["identity_dispositions"][0]
        market = proposal(self.context["families"][0], identity["identity_id"], "selected")
        family["proposed_markets"] = [market]
        identity.update(disposition="map_to_proposals", proposal_ids=[market["proposal_id"]])
        candidates = payload["families"][1]["candidate_dispositions"]
        candidates[0]["confidence"] = 0.2
        candidates[1]["counterevidence_ids"] = [next(item["evidence_id"]
            for item in self.context["families"][1]["evidence_catalog"]
            if item["evidence_id"] not in candidates[1]["supporting_evidence_ids"])]
        self.submit("primary", {"payload": payload})
        selected = batch_workflow.assignment(self.directory, "verifier")["targets"]
        by_id = {row["target_id"]: row for row in selected}
        self.assertIn("all_proposals", by_id[market["proposal_id"]]["reasons"])
        self.assertIn("graph_movement_candidate", by_id[identity["identity_id"]]["reasons"])
        self.assertIn("weak_confidence", by_id[candidates[0]["candidate_market_id"]]["reasons"])
        self.assertIn("counterevidence_conflict", by_id[candidates[1]["candidate_market_id"]]["reasons"])
        selected_keys = {(r["family_id"], r["target_kind"], r["target_id"]) for r in selected}
        self.assertTrue({tuple(row) for row in plan["qa_targets"]} <= selected_keys)

    def test_verification_requires_exact_coverage_hash_and_owned_evidence(self):
        self.initialize()
        primary = self.submit("primary", {"payload": self.payload()})
        valid = self.verification_document(primary)
        variants = []
        missing = copy.deepcopy(valid); missing["assessments"].pop(); variants.append(missing)
        duplicate = copy.deepcopy(valid); duplicate["assessments"].append(duplicate["assessments"][0]); variants.append(duplicate)
        wrong_hash = copy.deepcopy(valid); wrong_hash["input_hashes"]["primary"] = "0" * 64; variants.append(wrong_hash)
        wrong_evidence = copy.deepcopy(valid); wrong_evidence["assessments"][0]["supporting_evidence_ids"] = ["evidence:" + "0" * 64]; variants.append(wrong_evidence)
        for invalid in variants:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.submit("verifier", invalid)
        self.submit("verifier", valid)
        self.assertEqual(batch_workflow.inspect_workflow(self.directory)["status"], "release_pending")

    def test_routine_agreement_does_not_admit_blind_escalation_or_adjudication(self):
        self.initialize()
        self.verified()
        state = batch_workflow.inspect_workflow(self.directory)
        self.assertFalse(state["escalation_required"])
        for role in ("escalation_a", "escalation_b", "adjudicator"):
            with self.subTest(role=role), self.assertRaises(ValueError):
                batch_workflow.assignment(self.directory, role)
        self.assertEqual(batch_workflow.verified_stage(self.directory)["final_role"], "primary")

    def test_material_disagreement_requires_two_blind_roles_and_adjudication(self):
        self.initialize()
        submissions = self.verified(disagree=True)
        self.assertEqual(batch_workflow.inspect_workflow(self.directory)["status"], "escalation_pending")
        with self.assertRaises(ValueError):
            self.unit_preview()
        before = batch_workflow.assignment(self.directory, "escalation_b")
        self.assertEqual(before["inputs"], {})
        submissions["escalation_a"] = self.submit("escalation_a", {"payload": self.payload()})
        self.assertEqual(before, batch_workflow.assignment(self.directory, "escalation_b"))
        with self.assertRaises(ValueError):
            batch_workflow.assignment(self.directory, "adjudicator")
        submissions["escalation_b"] = self.submit("escalation_b", {"payload": self.payload()})
        self.assertNotEqual(submissions["escalation_a"]["role_invocation_id"], submissions["escalation_b"]["role_invocation_id"])
        with self.assertRaises(ValueError):
            self.unit_preview()
        document = self.adjudication_document(submissions)
        missing = copy.deepcopy(document); missing["comparisons"].pop()
        with self.assertRaises(ValueError):
            self.submit("adjudicator", missing)
        self.submit("adjudicator", document)
        self.assertEqual(batch_workflow.verified_stage(self.directory)["final_role"], "adjudicator")

    def test_release_approval_requires_exact_preview_all_checks_and_no_open_findings(self):
        self.initialize()
        submissions = self.verified()
        with self.assertRaises(ValueError):
            batch_workflow.assignment(self.directory, "release_reviewer")
        preview = self.unit_preview()
        valid = self.review_document(submissions, preview)
        wrong = copy.deepcopy(valid); wrong["approved_plan_sha256"] = "0" * 64
        open_finding = copy.deepcopy(valid); open_finding["findings"] = [{"finding_id": "gap", "status": "unresolved", "rationale": "Blocking review finding."}]
        failed_check = copy.deepcopy(valid); failed_check["checks"]["coverage"] = "fail"
        for invalid in (wrong, open_finding, failed_check):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.submit("release_reviewer", invalid)
        self.submit("release_reviewer", valid)
        before = self.files()
        self.assertEqual(batch_workflow.closure_payload(self.directory), self.payload())
        self.assertEqual(before, self.files())
        path = self.directory / "release-preview.json"
        tampered = json.loads(path.read_bytes()); tampered["preview"]["movements"] = ["tampered"]
        path.write_text(json.dumps(tampered))
        with self.assertRaises(ValueError):
            batch_workflow.closure_payload(self.directory)

    def test_real_routine_agreement_skips_escalation_and_retains_retry_gaps(self):
        import subprocess
        from turbo.universe.batch_closure import prepare_batch_release, finalize_batch_closure, validate_batch_closure
        self.initialize()
        submissions = self.verified()
        config = {"schema_version": 1, "recorded_at_utc": "2026-11-09T17:00:00Z",
                  "execution_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  "graph_base_sha256": self.context["families"][0]["pack_metadata"]["graph_projection_sha256"],
                  "families": [{"family_id": fid, "outcome": "reviewed_no_graph_movement",
                                "reason": "Reviewed synthetic fixture retains all explicit research gaps.",
                                "proposals": [], "mappings": []} for fid in FAMILIES]}
        preview = prepare_batch_release(self.directory, config, root=ROOT)
        self.submit("release_reviewer", self.review_document(submissions, preview))
        before = self.files()
        result = finalize_batch_closure(self.directory, output_root=Path(self.temporary.name) / "closures", root=ROOT)
        validation = validate_batch_closure(Path(result["closure_dir"]), self.directory, root=ROOT)
        self.assertTrue(validation["valid"], validation)
        self.assertIsNone(result["graph_release"])
        self.assertEqual({row["status"] for row in result["families"]}, {"reviewed_no_graph_movement"})
        payload = batch_workflow.closure_payload(self.directory)
        self.assertEqual(sum(len(f["research_gaps"]) for f in payload["families"]), 59)
        self.assertEqual(sum(len(f["proposed_markets"]) for f in payload["families"]), 0)
        self.assertEqual(batch_workflow.inspect_workflow(self.directory)["completed_roles"], ["primary", "verifier", "release_reviewer"])
        self.assertEqual(before, self.files())

    def test_envelope_overhead_cannot_exceed_persisted_size_limit(self):
        self.initialize()
        document = {"payload": self.payload()}
        limit = len(batch_workflow._bytes(document)) + 1
        before = self.files()
        with patch.object(batch_workflow, "MAX_DOCUMENT_BYTES", limit), self.assertRaisesRegex(ValueError, "envelope"):
            self.submit("primary", document)
        self.assertEqual(before, self.files())

    def invoke_cli(self, *arguments):
        from turbo.cli import main
        output = io.StringIO()
        with patch("sys.argv", ["turbo", *map(str, arguments)]), contextlib.redirect_stdout(output):
            code = main()
        return code, json.loads(output.getvalue())

    def test_cli_duplicate_keys_rejected_and_missing_status_is_read_only(self):
        missing = Path(self.temporary.name) / "missing"
        code, result = self.invoke_cli("batch-workflow-status", missing)
        self.assertEqual(code, 1)
        self.assertFalse(result["valid"])
        self.assertFalse(missing.exists())
        self.initialize()
        duplicate = Path(self.temporary.name) / "duplicate.json"
        duplicate.write_text('{"payload": {}, "payload": {}}')
        before = self.files()
        code, result = self.invoke_cli("batch-workflow-submit", self.directory,
                                       "primary", ACTORS["primary"], duplicate)
        self.assertEqual(code, 1)
        self.assertFalse(result["valid"])
        self.assertEqual(before, self.files())
        code, result = self.invoke_cli("batch-workflow-status", self.directory)
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "primary_pending")
