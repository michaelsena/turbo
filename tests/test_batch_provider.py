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
            expires_at_utc="2026-11-09T18:00:00Z", max_calls=3, max_cost_microusd=900,
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

    def test_escalation_and_release_are_not_dispatched_by_this_increment(self):
        for role in ("escalation_a", "escalation_b", "adjudicator", "release_reviewer"):
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
