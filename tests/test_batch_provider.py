"""Controlled-HTTP integration of workflow roles, V2 journal and one-shot adapter."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from turbo.agents import batch_provider, batch_workflow
from turbo.agents import batch_execution_v2 as execution
import test_batch_workflow as workflow_tests

NOW = "2026-11-09T17:00:00Z"


class BatchProviderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        workflow_tests.BatchWorkflowTest.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="turbo-provider-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.directory = self.base / "workflow"
        self.registry = self.base / "registry"
        isolation = patch.object(batch_workflow, "build_batch_context",
            side_effect=lambda *args, **kwargs: copy.deepcopy(self.context))
        isolation.start()
        self.addCleanup(isolation.stop)
        self.plan = batch_workflow.initialize_workflow(self.directory, self.preparations,
            input_root=self.input_root, request_id=workflow_tests.REQUEST,
            invocation_id=workflow_tests.INVOCATION, actors=workflow_tests.ACTORS)
        execution.initialize_registry(self.registry)
        roles = {role: {**binding, "model": "test/" + role,
                       "max_input_tokens": 10_000_000, "max_output_tokens": 100,
                       "input_microusd_per_token": 0, "output_microusd_per_token": 2,
                       "max_attempts": 1, "reasoning_effort": "high", "timeout_seconds": 30,
                       "allow_fallbacks": False}
                 for role, binding in batch_provider.contract_bindings(input_root=self.input_root).items()}
        self.authorization = execution.build_authorization(
            workflow_plan_sha256=self.plan["plan_sha256"], roles=roles,
            authorized_by="controlled-test-no-real-spend", valid_from_utc="2026-11-09T16:00:00Z",
            expires_at_utc="2026-11-09T18:00:00Z", max_calls=6, max_cost_microusd=1200,
            execution_contract_hashes=batch_provider.execution_contract_hashes())
        self.calls = []

    def payload(self):
        return workflow_tests.unresolved_output(copy.deepcopy(self.context))

    def transport_for(self, document, *, cost="0.000020", usage=True, served_model=None):
        def transport(url, headers, raw, timeout):
            request = json.loads(raw)
            self.calls.append(request)
            response = {"id": "generation-synthetic", "model": served_model or request["model"],
                        "provider": "controlled-test", "choices": [{"message": {
                            "content": json.dumps(document)}}]}
            if usage:
                response["usage"] = {"prompt_tokens": 10, "completion_tokens": 5}
                if cost is not None:
                    response["usage"]["cost"] = cost
            return 200, {}, json.dumps(response).encode()
        return transport

    def run_role(self, role, document, *, attempt_id=None, **kwargs):
        return batch_provider.run_batch_role(self.directory, self.registry, self.authorization,
            role, attempt_id or role + "-1", input_root=self.input_root,
            preparation_dirs=self.preparations, api_key="synthetic-never-used-credential",
            transport=self.transport_for(document, **kwargs), clock=lambda: NOW)

    def verifier_document(self):
        task = batch_workflow.assignment(self.directory, "verifier")
        families = {row["family_id"]: row for row in self.context["families"]}
        return {"input_hashes": {"primary": task["inputs"]["primary"]["submission_sha256"]},
                "assessments": [{**{key: row[key] for key in ("family_id", "target_kind", "target_id")},
                    "verdict": "agree", "rationale": "Checked frozen evidence in controlled integration.",
                    "supporting_evidence_ids": [next(e["evidence_id"]
                        for e in families[row["family_id"]]["evidence_catalog"]
                        if row["target_id"] in e["subject_ids"])]} for row in task["targets"]]}

    def ledger(self):
        return execution.BatchExecutionV2(self.registry, self.authorization, clock=lambda: NOW)

    def test_primary_and_verifier_share_journal_and_replay_without_http(self):
        primary_document = {"payload": self.payload()}
        primary = self.run_role("primary", primary_document)
        self.assertEqual(primary["status"], "succeeded", primary)
        verifier_document = self.verifier_document()
        verifier = self.run_role("verifier", verifier_document)
        self.assertEqual(verifier["status"], "succeeded", verifier)
        self.assertEqual(len(self.calls), 2)
        self.assertNotEqual(self.calls[0]["model"], self.calls[1]["model"])
        state = self.ledger().status()
        self.assertEqual(state["committed_microusd"], 40)
        self.assertEqual(state["outstanding_microusd"], 0)
        self.assertEqual(len(list((self.registry / "journals").iterdir())), 1)
        before = {str(p.relative_to(self.base)): p.read_bytes()
                  for p in self.base.rglob("*") if p.is_file()}
        self.assertEqual(self.run_role("primary", primary_document)["status"], "succeeded")
        self.assertEqual(self.run_role("verifier", verifier_document)["status"], "succeeded")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(before, {str(p.relative_to(self.base)): p.read_bytes()
                                 for p in self.base.rglob("*") if p.is_file()})
        self.assertEqual(batch_workflow.inspect_workflow(self.directory)["status"], "release_pending")

    def test_prompt_schema_plan_and_execution_binding_mismatch_prevents_http(self):
        baseline = copy.deepcopy(self.authorization)
        for field in ("prompt_sha256", "schema_sha256", "workflow_plan_sha256", "execution_contract_hashes"):
            self.authorization = copy.deepcopy(baseline)
            if field in ("prompt_sha256", "schema_sha256"):
                self.authorization["roles"]["primary"][field] = "0" * 64
            elif field == "execution_contract_hashes":
                first = next(iter(self.authorization[field])); self.authorization[field][first] = "0" * 64
            else:
                self.authorization[field] = "0" * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.run_role("primary", {"payload": self.payload()})
        self.authorization = baseline
        self.assertEqual(self.calls, [])
        self.assertFalse((self.directory / "primary.json").exists())
        self.assertEqual(list((self.registry / "journals").iterdir()), [])

    def test_same_model_primary_verifier_is_rejected(self):
        self.authorization["roles"]["verifier"]["model"] = self.authorization["roles"]["primary"]["model"]
        with self.assertRaises(ValueError):
            self.run_role("primary", {"payload": self.payload()})
        self.assertEqual(self.calls, [])

    def test_invalid_output_with_known_usage_is_failed_and_charged(self):
        payload = self.payload()
        payload["families"][-1]["candidate_dispositions"].pop()
        result = self.run_role("primary", {"payload": payload})
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(self.ledger().status()["committed_microusd"], 20)
        self.assertFalse((self.directory / "primary.json").exists())
        self.assertEqual(self.run_role("primary", {"payload": payload})["status"], "failed")
        self.assertEqual(len(self.calls), 1)

    def test_unknown_cost_retains_reservation_and_does_not_submit_or_retry(self):
        document = {"payload": self.payload()}
        result = self.run_role("primary", document, cost=None)
        self.assertEqual(result["status"], "unresolved", result)
        state = self.ledger().status()
        self.assertEqual(state["committed_microusd"], 0)
        self.assertEqual(state["outstanding_microusd"], 200)
        self.assertFalse((self.directory / "primary.json").exists())
        self.assertEqual(self.run_role("primary", document)["status"], "unresolved")
        self.assertEqual(len(self.calls), 1)

    def test_unknown_usage_does_not_publish_valid_document(self):
        result = self.run_role("primary", {"payload": self.payload()}, usage=False)
        self.assertEqual(result["status"], "unresolved", result)
        self.assertFalse((self.directory / "primary.json").exists())
        self.assertEqual(self.ledger().status()["outstanding_microusd"], 200)

    def test_artifact_tampering_blocks_settled_replay_without_http(self):
        self.assertEqual(self.run_role("primary", {"payload": self.payload()})["status"], "succeeded")
        artifact = next(self.ledger().journal_path.glob("provider-*.json"))
        artifact.write_bytes(artifact.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.run_role("primary", {"payload": self.payload()})
        self.assertEqual(len(self.calls), 1)

    def test_offline_submission_cannot_be_relabelled_as_paid_attempt(self):
        document = {"payload": self.payload()}
        batch_workflow.submit(self.directory, "primary", workflow_tests.ACTORS["primary"], document)
        with self.assertRaises(ValueError):
            self.run_role("primary", document)
        self.assertEqual(self.calls, [])

    def test_unknown_roles_are_not_dispatched(self):
        for role in ("unknown", "specialist_a", ""):
            with self.subTest(role=role), self.assertRaises(ValueError):
                self.run_role(role, {})
        self.assertEqual(self.calls, [])

    def test_tiny_input_cap_refuses_before_any_http(self):
        self.authorization["roles"]["primary"]["max_input_tokens"] = 1
        with self.assertRaisesRegex(ValueError, "token bound"):
            self.run_role("primary", {"payload": self.payload()})
        self.assertEqual(self.calls, [])
        self.assertFalse((self.directory / "primary.json").exists())

    def test_wrong_served_model_is_charged_but_never_submitted(self):
        result = self.run_role("primary", {"payload": self.payload()}, served_model="other/model")
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(self.ledger().status()["committed_microusd"], 20)
        self.assertFalse((self.directory / "primary.json").exists())

    def paid_verified(self, *, disagree=False):
        primary = {"payload": self.payload()}
        primary["payload"]["families"][0]["analysis_summary"] = "PRIMARY_PRIVATE_CONCLUSION_SENTINEL"
        self.assertEqual(self.run_role("primary", primary)["status"], "succeeded")
        verifier = self.verifier_document()
        verifier["assessments"][0]["rationale"] = "VERIFIER_PRIVATE_CONCLUSION_SENTINEL"
        if disagree:
            verifier["assessments"][0]["verdict"] = "material_disagreement"
        self.assertEqual(self.run_role("verifier", verifier)["status"], "succeeded")
        return {"primary": primary, "verifier": verifier}

    def compiled_preview(self):
        import subprocess
        from turbo.pipeline_paths import ROOT
        from turbo.universe.batch_closure import prepare_batch_release
        config = {"schema_version": 1, "recorded_at_utc": NOW,
                  "execution_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  "graph_base_sha256": self.context["families"][0]["pack_metadata"]["graph_projection_sha256"],
                  "families": [{"family_id": family["family_id"], "outcome": "reviewed_no_graph_movement",
                                "reason": "Controlled integration preserves explicit unresolved research gaps.",
                                "proposals": [], "mappings": []} for family in self.context["families"]]}
        return prepare_batch_release(self.directory, config, root=ROOT)

    def review_document(self, preview, *, verdict="approve"):
        task = batch_workflow.assignment(self.directory, "release_reviewer")
        return {"input_hashes": {role: envelope["submission_sha256"] for role, envelope in task["inputs"].items()},
                "approved_plan_sha256": preview["preview_sha256"], "verdict": verdict,
                "findings": [] if verdict == "approve" else [{"finding_id": "needs-evidence", "status": "unresolved",
                                                               "rationale": "Independent reviewer refuses release."}],
                "checks": {name: "pass" for name in ("coverage", "operating_identity", "evidence",
                                                     "cross_family_conflicts", "closure_outcomes")}}

    def adjudication_document(self):
        task = batch_workflow.assignment(self.directory, "adjudicator")
        return {"payload": self.payload(),
                "input_hashes": {role: envelope["submission_sha256"] for role, envelope in task["inputs"].items()},
                "comparisons": [{"family_id": family["family_id"], "subject_kind": kind, "subject_id": subject,
                                 "rationale": "Compared both blind specialist answers and retained an explicit gap."}
                                for family in self.context["families"]
                                for kind, key in (("identity", "required_identity_ids"), ("candidate", "required_candidate_ids"))
                                for subject in family[key]], "proposal_comparisons": []}

    def test_routine_provider_review_compiles_and_replays_real_no_movement_closure(self):
        from turbo.pipeline_paths import ROOT
        from turbo.universe.batch_closure import finalize_batch_closure, validate_batch_closure
        self.paid_verified()
        preview = self.compiled_preview()
        document = self.review_document(preview)
        result = self.run_role("release_reviewer", document)
        self.assertEqual(result["status"], "succeeded", result)
        closure = finalize_batch_closure(self.directory, output_root=self.base / "closures", root=ROOT)
        self.assertTrue(validate_batch_closure(Path(closure["closure_dir"]), self.directory, root=ROOT)["valid"])
        self.assertIsNone(closure["graph_release"])
        self.assertEqual(batch_workflow.inspect_workflow(self.directory)["completed_roles"], ["primary", "verifier", "release_reviewer"])
        self.assertEqual(self.ledger().status()["committed_microusd"], 60)
        self.assertEqual(self.ledger().status()["outstanding_microusd"], 0)
        self.assertEqual(self.run_role("release_reviewer", document)["status"], "succeeded")
        self.assertEqual(len(self.calls), 3)

    def test_model_view_reviewer_literal_compiles_closure_and_replays(self):
        from turbo.agents import model_view
        self.authorization['execution_contract_hashes'] = batch_provider.execution_contract_hashes(model_view=model_view.VERSION)
        for role, binding in batch_provider.contract_bindings(input_root=self.input_root, model_view=model_view.VERSION).items():
            self.authorization['roles'][role].update(binding)
        self.test_routine_provider_review_compiles_and_replays_real_no_movement_closure()
        content = self.calls[-1]['messages'][0]['content']
        literal, encoded = content.split('\n# Literal assignment navigation\n', 1)[1].split('\n# Frozen assignment\n', 1)
        task = model_view.decode(json.loads(encoded))
        self.assertEqual(json.loads(literal)['approved_plan_sha256'], task['release_preview']['preview_sha256'])

    def test_disagreement_dispatches_blind_pair_adjudicator_and_exact_review_once(self):
        for role in ("escalation_a", "escalation_b", "adjudicator"):
            self.authorization["roles"][role]["model"] = self.authorization["roles"]["primary"]["model"]
        documents = self.paid_verified(disagree=True)
        for role in ("escalation_a", "escalation_b"):
            document = {"payload": self.payload()}
            document["payload"]["families"][0]["analysis_summary"] = role.upper() + "_PRIVATE_CONCLUSION_SENTINEL"
            documents[role] = document
            self.assertEqual(self.run_role(role, document)["status"], "succeeded")
            serialized = json.dumps(self.calls[-1])
            for secret in ("PRIMARY_PRIVATE_CONCLUSION_SENTINEL", "VERIFIER_PRIVATE_CONCLUSION_SENTINEL",
                           "ESCALATION_A_PRIVATE_CONCLUSION_SENTINEL", "ESCALATION_B_PRIVATE_CONCLUSION_SENTINEL"):
                self.assertNotIn(secret, serialized)
            assignment = batch_workflow.assignment(self.directory, role)
            self.assertEqual(assignment["inputs"], {})
        documents["adjudicator"] = self.adjudication_document()
        self.assertEqual(self.run_role("adjudicator", documents["adjudicator"])["status"], "succeeded")
        preview = self.compiled_preview()
        documents["release_reviewer"] = self.review_document(preview)
        self.assertEqual(self.run_role("release_reviewer", documents["release_reviewer"])["status"], "succeeded")
        state = self.ledger().status()
        self.assertEqual(state["committed_microusd"], 120)
        self.assertEqual(state["outstanding_microusd"], 0)
        self.assertEqual(len(state["requests"]), 6)
        self.assertEqual(len({request["session_id"] for request in self.calls}), 6)
        self.assertTrue(all(len(request["messages"]) == 1 and request["messages"][0]["role"] == "user"
                            for request in self.calls))
        self.assertEqual(batch_workflow.inspect_workflow(self.directory)["status"], "approved")
        for role, document in documents.items():
            self.assertEqual(self.run_role(role, document)["status"], "succeeded")
        self.assertEqual(len(self.calls), 6)

    def test_release_wrong_preview_is_charged_failed_and_not_published(self):
        from turbo.agents import model_view
        self.authorization['execution_contract_hashes'] = batch_provider.execution_contract_hashes(model_view=model_view.VERSION)
        for role, binding in batch_provider.contract_bindings(input_root=self.input_root, model_view=model_view.VERSION).items():
            self.authorization['roles'][role].update(binding)
        self.paid_verified()
        preview = self.compiled_preview()
        document = self.review_document(preview)
        document["approved_plan_sha256"] = preview['preview']['base_events_sha256']
        self.assertNotEqual(document['approved_plan_sha256'], preview['preview_sha256'])
        result = self.run_role("release_reviewer", document)
        self.assertEqual(result["status"], "failed", result)
        content = self.calls[-1]['messages'][0]['content']
        literal = json.loads(content.split('\n# Literal assignment navigation\n', 1)[1].split('\n# Frozen assignment\n', 1)[0])
        self.assertEqual(literal['approved_plan_sha256'], preview['preview_sha256'])
        self.assertFalse((self.directory / "release_reviewer.json").exists())
        self.assertEqual(self.ledger().status()["committed_microusd"], 60)
        with self.assertRaises(ValueError):
            batch_workflow.closure_payload(self.directory)
        self.assertEqual(self.run_role('release_reviewer', document)['status'], 'failed')
        self.assertEqual(len(self.calls), 3)

    def test_rejected_paid_review_is_settled_but_prevents_closure(self):
        from turbo.pipeline_paths import ROOT
        from turbo.universe.batch_closure import finalize_batch_closure
        self.paid_verified()
        preview = self.compiled_preview()
        result = self.run_role("release_reviewer", self.review_document(preview, verdict="reject"))
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(batch_workflow.inspect_workflow(self.directory)["status"], "rejected")
        with self.assertRaises(ValueError):
            finalize_batch_closure(self.directory, output_root=self.base / "closures", root=ROOT)
        self.assertEqual(self.ledger().status()["committed_microusd"], 60)

    def test_offline_or_blended_upstream_provenance_is_denied_before_http(self):
        batch_workflow.submit(self.directory, "primary", workflow_tests.ACTORS["primary"], {"payload": self.payload()})
        with self.assertRaises(ValueError):
            self.run_role("verifier", self.verifier_document())
        self.assertEqual(self.calls, [])
        # A fresh separate workflow demonstrates that one paid ancestor cannot
        # legitimize a later offline submission in the same chain.
        self.directory = self.base / "second-workflow"
        self.plan = batch_workflow.initialize_workflow(self.directory, self.preparations,
            input_root=self.input_root, request_id=workflow_tests.REQUEST,
            invocation_id=workflow_tests.INVOCATION, actors=workflow_tests.ACTORS)
        self.authorization["workflow_plan_sha256"] = self.plan["plan_sha256"]
        # Same plan digest is possible for identical inputs; use a distinct clean registry.
        self.registry = self.base / "second-registry"
        execution.initialize_registry(self.registry)
        self.assertEqual(self.run_role("primary", {"payload": self.payload()})["status"], "succeeded")
        verifier = self.verifier_document()
        verifier["assessments"][0]["verdict"] = "material_disagreement"
        batch_workflow.submit(self.directory, "verifier", workflow_tests.ACTORS["verifier"], verifier)
        with self.assertRaises(ValueError):
            self.run_role("escalation_a", {"payload": self.payload()})
        self.assertEqual(len(self.calls), 1)

    def test_adjudicator_missing_blind_dependency_never_dispatches(self):
        self.paid_verified(disagree=True)
        self.assertEqual(self.run_role("escalation_a", {"payload": self.payload()})["status"], "succeeded")
        with self.assertRaises(ValueError):
            self.run_role("adjudicator", {})
        self.assertEqual(len(self.calls), 3)

    def test_release_model_must_differ_from_every_configured_author(self):
        original = self.authorization["roles"]["release_reviewer"]["model"]
        for author in ("primary", "verifier", "escalation_a", "escalation_b", "adjudicator"):
            self.authorization["roles"]["release_reviewer"]["model"] = self.authorization["roles"][author]["model"]
            with self.subTest(author=author), self.assertRaises(ValueError):
                self.run_role("primary", {"payload": self.payload()})
        self.authorization["roles"]["release_reviewer"]["model"] = original
        self.assertEqual(self.calls, [])

    def test_self_rehashed_release_preview_must_recompile_before_http(self):
        self.paid_verified()
        self.compiled_preview()
        path = self.directory / "release-preview.json"
        preview = json.loads(path.read_bytes())
        preview["preview"]["movements"] = [{"fabricated": "event"}]
        preview["preview_sha256"] = batch_workflow._hash(preview["preview"])
        path.write_text(json.dumps(preview))
        document = self.review_document(preview)
        with self.assertRaises(ValueError):
            self.run_role("release_reviewer", document)
        self.assertEqual(len(self.calls), 2)

    def test_valid_preview_replacement_during_http_is_charged_failed(self):
        from turbo.pipeline_paths import ROOT
        from turbo.universe.batch_closure import _compile
        self.paid_verified()
        original = self.compiled_preview()
        def transport(url, headers, raw, timeout):
            stage = batch_workflow.verified_stage(self.directory)
            config = copy.deepcopy(original["preview"]["config"])
            config["families"][0]["reason"] = "Changed decision rationale after dispatch"
            compiled = _compile(stage, config, root=ROOT)
            replacement = copy.deepcopy(original)
            replacement["preview"] = compiled
            replacement["preview_sha256"] = batch_workflow._hash(compiled)
            (self.directory / "release-preview.json").write_text(json.dumps(replacement))
            return self.transport_for(self.review_document(replacement))(url, headers, raw, timeout)
        result = batch_provider.run_batch_role(self.directory, self.registry, self.authorization,
            "release_reviewer", "release_reviewer-1", input_root=self.input_root,
            preparation_dirs=self.preparations, api_key="synthetic-never-used-credential",
            transport=transport, clock=lambda: NOW)
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(self.ledger().status()["committed_microusd"], 60)
        self.assertFalse((self.directory / "release_reviewer.json").exists())
        self.assertEqual(len(self.calls), 3)

    def test_upstream_artifact_changed_during_http_is_charged_failed(self):
        self.assertEqual(self.run_role("primary", {"payload": self.payload()})["status"], "succeeded")
        document = self.verifier_document()
        artifact = next(self.ledger().journal_path.glob("provider-*.json"))
        def transport(url, headers, raw, timeout):
            artifact.write_bytes(artifact.read_bytes() + b" ")
            return self.transport_for(document)(url, headers, raw, timeout)
        result = batch_provider.run_batch_role(self.directory, self.registry, self.authorization,
            "verifier", "verifier-1", input_root=self.input_root,
            preparation_dirs=self.preparations, api_key="synthetic-never-used-credential",
            transport=transport, clock=lambda: NOW)
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(self.ledger().status()["committed_microusd"], 40)
        self.assertFalse((self.directory / "verifier.json").exists())
        self.assertEqual(len(self.calls), 2)

    def test_provider_schemas_support_both_exact_release_dependency_branches(self):
        from jsonschema import Draft202012Validator
        from turbo.agents.openrouter_runner import openrouter_schema
        def inspect(value):
            if isinstance(value, dict):
                self.assertNotIn("oneOf", value)
                self.assertNotIn("uniqueItems", value)
                for child in value.values():
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)
        schemas = {role: openrouter_schema(batch_provider.role_schema(role, input_root=self.input_root))
                   for role in batch_workflow.ROLES}
        for role, schema in schemas.items():
            with self.subTest(role=role):
                inspect(schema)
        validator = Draft202012Validator(schemas["release_reviewer"])
        base = {"input_hashes": {"primary": "1" * 64, "verifier": "2" * 64},
                "approved_plan_sha256": "3" * 64, "verdict": "approve", "findings": [],
                "checks": {key: "pass" for key in ("coverage", "operating_identity", "evidence",
                                                  "cross_family_conflicts", "closure_outcomes")}}
        self.assertTrue(validator.is_valid(base))
        escalated = copy.deepcopy(base)
        escalated["input_hashes"].update({role: "4" * 64 for role in ("escalation_a", "escalation_b", "adjudicator")})
        self.assertTrue(validator.is_valid(escalated))
        missing = copy.deepcopy(base); missing["input_hashes"].pop("verifier")
        mixed = copy.deepcopy(base); mixed["input_hashes"]["escalation_a"] = "4" * 64
        extra = copy.deepcopy(escalated); extra["input_hashes"]["release_reviewer"] = "5" * 64
        for document in (missing, mixed, extra):
            self.assertFalse(validator.is_valid(document))
