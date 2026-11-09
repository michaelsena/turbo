"""Simulation-only tests for journal settlement plus immutable B3 output artifacts.

Every case starts from real V2 preparations. Selected ledger/artifact unit cases
reuse only the verified input-scope binding; output parsing, B3 context generation,
semantic validation, registry identity, accounting, and artifact replay stay real.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import multiprocessing
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from turbo.agents import batch_research
from turbo.agents.batch_authorization import build_authorization, canonical_bytes
from turbo.agents.batch_execution import inspect_execution
from turbo.agents.batch_registry import initialize_registry
from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT
from turbo.universe.family_pack_v2 import prepare_family_v2
from test_batch_output import unresolved_output

NOW = "2026-11-09T07:00:00Z"
FAMILIES = ["family:coverage:napcs-collection:10:001",
            "family:coverage:prior-candidate:global-challenger:001"]


def clock():
    return NOW


def response_for(context, *, confidence=0.25):
    output = unresolved_output(context)
    output["families"][0]["identity_dispositions"][0]["confidence"] = confidence
    return {"body": json.dumps(output, indent=2).encode(),
            "usage": {"input_tokens": 10, "output_tokens": 5}}


def stop_process(process):
    if process.is_alive():
        process.terminate()
    process.join(timeout=5)


def contender(registry, authorization, preparations, start, results, calls):
    try:
        research = batch_research.BatchResearch(Path(registry), authorization,
            [Path(p) for p in preparations], root=ROOT, clock=clock)
        results.put(("ready", os.getpid()))
        if not start.wait(30):
            results.put(("timeout", os.getpid()))
            return
        def transport(context):
            descriptor = os.open(calls, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(descriptor, (str(os.getpid()) + "\n").encode())
            finally:
                os.close(descriptor)
            return response_for(context)
        result = research.run("request-1", "worker-1", transport)
        results.put((result["status"], os.getpid()))
    except ValueError as error:
        results.put(("rejected", str(error)))
    except Exception as error:
        results.put((type(error).__name__, str(error)))


class BatchResearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix="turbo-research-inputs-")
        cls.preparations = []
        for family in FAMILIES:
            prepared = prepare_family_v2(family, root=ROOT, output_root=Path(cls.fixture.name))
            cls.preparations.append(Path(prepared["preparation_path"]))
        cls.authorization = build_authorization(cls.preparations, root=ROOT,
            authorized_by="simulation-only-test", valid_from_utc="2026-11-09T06:00:00Z",
            expires_at_utc="2026-11-09T08:00:00Z", model="simulation",
            prompt_sha256=batch_research.research_contract_sha256(root=ROOT),
            pricing={"input_microusd_per_token": 1, "output_microusd_per_token": 2},
            max_cost_microusd=900, max_calls=3, max_retries=1, max_concurrency=1,
            max_input_tokens=100, max_output_tokens=100, lease_seconds=60)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="turbo-research-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.registry = self.base / "registry"
        self.auth = copy.deepcopy(self.authorization)
        self.digest = canonical_sha256(self.auth)
        self.journal = self.registry / "journals" / self.digest
        initialize_registry(self.registry, root=ROOT, clock=clock)
        if self._testMethodName not in {
            "test_float_output_is_preserved_and_known_usage_settles_then_replays",
            "test_invalid_coverage_is_failed_and_charged_not_accepted",
            "test_changed_preparation_is_rejected_before_transport",
            "test_two_processes_dispatch_exactly_one_callback",
        }:
            scope = (copy.deepcopy(self.authorization["families"]), self.authorization["batch_id"])
            for name in ("turbo.agents.batch_authorization._scope", "turbo.agents.batch_output._scope"):
                isolation = patch(name, return_value=scope)
                isolation.start()
                self.addCleanup(isolation.stop)

    def research(self, authorization=None):
        return batch_research.BatchResearch(self.registry, authorization or self.auth,
            self.preparations, root=ROOT, clock=clock)

    def state(self):
        return inspect_execution(self.journal, root=ROOT)

    def validate(self):
        return batch_research.validate_batch_research(self.registry, self.digest, self.preparations, root=ROOT)

    def artifact(self, request_id="request-1"):
        invocation = batch_research.research_invocation_id(self.digest, request_id)
        return self.journal / "research-artifacts" / invocation.removeprefix("invocation:")

    def assert_settled(self, status, cost=20):
        state = self.state()
        self.assertEqual(state["requests"]["request-1"]["status"], status)
        self.assertEqual(state["committed_microusd"], cost)
        self.assertEqual(state["outstanding_microusd"], 0)
        self.assertEqual(state["calls_reserved"], 1)

    def test_float_output_is_preserved_and_known_usage_settles_then_replays(self):
        captured = []
        def transport(context):
            response = response_for(context)
            captured.append((copy.deepcopy(context), response["body"]))
            return response
        result = self.research().run("request-1", "worker-1", transport)
        self.assertEqual(result["status"], "succeeded", result)
        self.assert_settled("succeeded")
        self.assertEqual(len(captured), 1)
        self.assertEqual([f["family_id"] for f in captured[0][0]["families"]], FAMILIES)
        self.assertEqual((self.artifact() / "output.raw").read_bytes(), captured[0][1])
        raw_output = json.loads(captured[0][1])
        self.assertEqual(raw_output["families"][0]["identity_dispositions"][0]["confidence"], 0.25)
        reference = self.state()["requests"]["request-1"]["response"]["output"]
        self.assertEqual(reference["kind"], "batch_research_artifact_v1")
        self.assertEqual(reference["output_sha256"], hashlib.sha256(captured[0][1]).hexdigest())
        validation = self.validate()
        self.assertTrue(validation["valid"], validation)

    def test_invalid_coverage_is_failed_and_charged_not_accepted(self):
        def transport(context):
            response = response_for(context)
            output = json.loads(response["body"])
            output["families"][1]["candidate_dispositions"].pop()
            response["body"] = json.dumps(output).encode()
            return response
        result = self.research().run("request-1", "worker-1", transport)
        self.assertEqual(result["status"], "failed", result)
        self.assert_settled("failed")
        validation = self.validate()
        self.assertTrue(validation["valid"], validation)

    def test_invalid_json_with_known_usage_is_failed_and_charged(self):
        result = self.research().run("request-1", "worker-1",
            lambda _: {"body": b"not-json", "usage": {"input_tokens": 10, "output_tokens": 5}})
        self.assertEqual(result["status"], "failed", result)
        self.assert_settled("failed")
        self.assertEqual((self.artifact() / "output.raw").read_bytes(), b"not-json")
        self.assertTrue(self.validate()["valid"])

    def test_missing_noninteger_and_over_limit_usage_remain_unresolved(self):
        cases = [None, {}, {"input_tokens": True, "output_tokens": 5},
                 {"input_tokens": 10, "output_tokens": 5.5},
                 {"input_tokens": 101, "output_tokens": 5},
                 {"input_tokens": -1, "output_tokens": 5}]
        for index, usage in enumerate(cases):
            registry = self.base / f"usage-registry-{index}"
            initialize_registry(registry, root=ROOT, clock=clock)
            research = batch_research.BatchResearch(registry, self.auth, self.preparations, root=ROOT, clock=clock)
            def transport(context):
                return {"body": response_for(context)["body"], "usage": usage}
            result = research.run("request-1", "worker-1", transport)
            state = inspect_execution(registry / "journals" / self.digest, root=ROOT)
            with self.subTest(usage=usage):
                self.assertEqual(result["status"], "unresolved", result)
                self.assertEqual(state["outstanding_microusd"], 300)
                self.assertEqual(state["committed_microusd"], 0)

    def test_oversize_or_malformed_transport_response_retains_reservation(self):
        packets = [
            {"body": b" " * 1_000_001, "usage": {"input_tokens": 10, "output_tokens": 5}},
            {"body": "text instead of raw bytes", "usage": {"input_tokens": 10, "output_tokens": 5}},
            {"usage": {"input_tokens": 10, "output_tokens": 5}},
            [],
        ]
        for index, packet in enumerate(packets):
            registry = self.base / f"packet-registry-{index}"
            initialize_registry(registry, root=ROOT, clock=clock)
            research = batch_research.BatchResearch(registry, self.auth, self.preparations, root=ROOT, clock=clock)
            result = research.run("request-1", "worker-1", lambda _, value=packet: value)
            state = inspect_execution(registry / "journals" / self.digest, root=ROOT)
            with self.subTest(index=index):
                self.assertEqual(result["status"], "unresolved", result)
                self.assertEqual(state["committed_microusd"], 0)
                self.assertEqual(state["outstanding_microusd"], 300)

    def test_transport_timeout_retains_reservation_and_resume_never_calls_again(self):
        calls = []
        def transport(_):
            calls.append(1)
            raise TimeoutError("ambiguous delivery")
        result = self.research().run("request-1", "worker-1", transport)
        self.assertEqual(result["status"], "unresolved", result)
        self.research().run("request-1", "worker-1", transport)
        self.assertEqual(calls, [1])
        self.assertEqual(self.state()["outstanding_microusd"], 300)
        self.assertEqual(self.state()["committed_microusd"], 0)

    def test_duplicate_completed_run_replays_without_rewriting_or_calling_transport(self):
        calls = []
        def transport(context):
            calls.append(1)
            return response_for(context)
        self.research().run("request-1", "worker-1", transport)
        before = {p.relative_to(self.registry): p.read_bytes() for p in self.registry.rglob("*") if p.is_file()}
        resumed = self.research().run("request-1", "worker-1", transport)
        self.assertEqual(resumed["status"], "succeeded")
        self.assertEqual(calls, [1])
        self.assertEqual({p.relative_to(self.registry): p.read_bytes() for p in self.registry.rglob("*") if p.is_file()}, before)

    def test_invalid_result_retry_has_distinct_invocation_and_preserves_first_artifact(self):
        research = self.research()
        research.run("request-1", "worker-1", lambda _: {
            "body": b"broken JSON", "usage": {"input_tokens": 10, "output_tokens": 5}})
        first = (self.artifact() / "output.raw").read_bytes()
        result = research.run("request-2", "worker-2", response_for, retry_of="request-1")
        self.assertEqual(result["status"], "succeeded", result)
        self.assertNotEqual(self.artifact(), self.artifact("request-2"))
        self.assertEqual((self.artifact() / "output.raw").read_bytes(), first)
        self.assertEqual(self.state()["committed_microusd"], 40)
        self.assertEqual(self.state()["calls_reserved"], 2)
        self.assertTrue(self.validate()["valid"])

    def test_prompt_mismatch_fails_before_transport_or_reservation(self):
        auth = copy.deepcopy(self.auth)
        auth["prompt_sha256"] = "0" * 64
        calls = []
        with self.assertRaises(ValueError):
            self.research(auth).run("request-1", "worker-1", lambda context: calls.append(context))
        self.assertEqual(calls, [])
        path = self.registry / "journals" / canonical_sha256(auth)
        if path.exists():
            self.assertEqual(inspect_execution(path, root=ROOT)["calls_reserved"], 0)

    def test_raw_prompt_hash_is_not_the_bound_execution_contract(self):
        auth = copy.deepcopy(self.auth)
        auth["prompt_sha256"] = hashlib.sha256(
            (ROOT / "prompts/universe/batch-primary-v1.md").read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            self.research(auth)
        self.assertEqual(list((self.registry / "claims").iterdir()), [])

    def test_schema_only_change_rejects_before_claim_or_transport(self):
        isolated_root = self.base / "contract-root"
        for relative in (batch_research.PROMPT_PATH, batch_research.SCHEMA_PATH):
            destination = isolated_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        self.assertEqual(batch_research.research_contract_sha256(root=isolated_root),
                         self.auth["prompt_sha256"])
        schema = isolated_root / batch_research.SCHEMA_PATH
        schema.write_bytes(schema.read_bytes() + b" ")
        self.assertNotEqual(batch_research.research_contract_sha256(root=isolated_root),
                            self.auth["prompt_sha256"])
        calls = []
        with self.assertRaisesRegex(ValueError, "contract"):
            batch_research.BatchResearch(self.registry, self.auth, self.preparations,
                root=isolated_root, clock=clock).run(
                    "request-1", "worker-1", lambda context: calls.append(context))
        self.assertEqual(calls, [])
        self.assertEqual(list((self.registry / "claims").iterdir()), [])

    def test_wrong_request_invocation_or_context_binding_is_charged_failure(self):
        for index, field in enumerate(("request_id", "invocation_id", "context_sha256")):
            registry = self.base / f"binding-registry-{index}"
            initialize_registry(registry, root=ROOT, clock=clock)
            research = batch_research.BatchResearch(registry, self.auth, self.preparations, root=ROOT, clock=clock)
            def transport(context):
                response = response_for(context)
                output = json.loads(response["body"])
                output[field] = "0" * 64
                response["body"] = json.dumps(output).encode()
                return response
            result = research.run("request-1", "worker-1", transport)
            state = inspect_execution(registry / "journals" / self.digest, root=ROOT)
            with self.subTest(field=field):
                self.assertEqual(result["status"], "failed", result)
                self.assertEqual(state["committed_microusd"], 20)

    def test_changed_preparation_is_rejected_before_transport(self):
        research = self.research()
        path = self.preparations[0] / "family-evidence-pack-v2.json"
        original = path.read_bytes()
        calls = []
        try:
            path.write_bytes(original + b" ")
            with self.assertRaises(ValueError):
                research.run("request-1", "worker-1", lambda context: calls.append(context))
            self.assertEqual(calls, [])
        finally:
            path.write_bytes(original)

    def test_missing_artifact_is_not_recreated_on_resume(self):
        research = self.research()
        research.run("request-1", "worker-1", response_for)
        path = self.artifact() / "output.raw"
        path.unlink()
        validation = self.validate()
        self.assertFalse(validation["valid"], validation)
        calls = []
        with self.assertRaises(ValueError):
            self.research().run("request-1", "worker-1", lambda context: calls.append(context))
        self.assertEqual(calls, [])
        self.assertFalse(path.exists())

    def test_changed_raw_artifact_or_context_is_rejected(self):
        self.research().run("request-1", "worker-1", response_for)
        for name in ("output.raw", "context.json", "receipt.json"):
            path = self.artifact() / name
            original = path.read_bytes()
            try:
                path.write_bytes(original + b" ")
                with self.subTest(name=name):
                    self.assertFalse(self.validate()["valid"])
            finally:
                path.write_bytes(original)

    def test_recomputed_artifact_hash_cannot_override_settled_journal_reference(self):
        self.research().run("request-1", "worker-1", response_for)
        raw_path = self.artifact() / "output.raw"
        receipt_path = self.artifact() / "receipt.json"
        output = json.loads(raw_path.read_bytes())
        output["families"][0]["analysis_summary"] = "A different but structurally valid result."
        rewritten = json.dumps(output, indent=2).encode()
        raw_path.write_bytes(rewritten)
        receipt = json.loads(receipt_path.read_bytes())
        receipt["output_sha256"] = hashlib.sha256(rewritten).hexdigest()
        receipt["output_bytes"] = len(rewritten)
        receipt_path.write_bytes(canonical_bytes(receipt))
        self.assertFalse(self.validate()["valid"])
        self.assertEqual(self.state()["committed_microusd"], 20)

    def test_facade_rebinding_to_other_registry_inputs_or_journal_is_rejected(self):
        research = self.research()
        other_registry = self.base / "other-registry"
        initialize_registry(other_registry, root=ROOT, clock=clock)
        other = batch_research.BatchResearch(other_registry, self.auth, self.preparations, root=ROOT, clock=clock)
        mutations = (
            ("_managed", other._managed),
            ("_journal", other._journal),
            ("_preparations", tuple(reversed(research._preparations))),
            ("_root", self.base),
        )
        calls = []
        for field, value in mutations:
            original = getattr(research, field)
            try:
                setattr(research, field, value)
                with self.subTest(field=field), self.assertRaises(ValueError):
                    research.run("request-1", "worker-1", lambda context: calls.append(context))
            finally:
                setattr(research, field, original)
        self.assertEqual(calls, [])
        self.assertEqual(self.state()["calls_reserved"], 0)
        self.assertEqual(inspect_execution(other._journal, root=ROOT)["calls_reserved"], 0)

    def test_callback_mutation_does_not_rewrite_the_frozen_context(self):
        def transport(context):
            response = response_for(context)
            context["request_id"] = "mutated-after-building-output"
            context["families"].clear()
            return response
        result = self.research().run("request-1", "worker-1", transport)
        self.assertEqual(result["status"], "succeeded", result)
        stored = json.loads((self.artifact() / "context.json").read_bytes())
        self.assertEqual(stored["request_id"], "request-1")
        self.assertEqual(len(stored["families"]), 2)
        self.assertTrue(self.validate()["valid"])

    def test_artifact_from_another_request_cannot_be_transplanted(self):
        research = self.research()
        research.run("request-1", "worker-1", lambda _: {
            "body": b"broken JSON", "usage": {"input_tokens": 10, "output_tokens": 5}})
        research.run("request-2", "worker-2", response_for, retry_of="request-1")
        first = self.artifact()
        second = self.artifact("request-2")
        shutil.rmtree(first)
        shutil.copytree(second, first)
        validation = self.validate()
        self.assertFalse(validation["valid"], validation)

    def test_artifact_persistence_failure_leaves_usage_unsettled(self):
        with patch.object(batch_research, "_persist_artifact", side_effect=OSError("simulated write failure")):
            result = self.research().run("request-1", "worker-1", response_for)
        self.assertEqual(result["status"], "unresolved", result)
        self.assertEqual(self.state()["committed_microusd"], 0)
        self.assertEqual(self.state()["outstanding_microusd"], 300)

    def test_two_processes_dispatch_exactly_one_callback(self):
        context = multiprocessing.get_context("fork")
        start, results = context.Event(), context.Queue()
        calls = self.base / "transport-calls.txt"
        processes = [context.Process(target=contender,
            args=(str(self.registry), self.auth, [str(p) for p in self.preparations], start, results, str(calls)))
            for _ in range(2)]
        for process in processes:
            process.start()
            self.addCleanup(stop_process, process)
        ready = [results.get(timeout=90) for _ in processes]
        self.assertEqual([item[0] for item in ready], ["ready", "ready"], ready)
        start.set()
        outcomes = [results.get(timeout=120) for _ in processes]
        for process in processes:
            process.join(timeout=30)
            self.assertEqual(process.exitcode, 0)
        self.assertTrue(any(item[0] == "succeeded" for item in outcomes), outcomes)
        self.assertTrue(all(item[0] in {"succeeded", "dispatched", "rejected"} for item in outcomes), outcomes)
        self.assertEqual(len(calls.read_text().splitlines()), 1)
        self.assert_settled("succeeded")
        self.assertTrue(self.validate()["valid"])

    def invoke_cli(self, *arguments):
        from turbo.cli import main
        output = io.StringIO()
        with patch("sys.argv", ["turbo", *map(str, arguments)]), contextlib.redirect_stdout(output):
            code = main()
        return code, json.loads(output.getvalue())

    def test_cli_artifact_validation_is_read_only(self):
        self.research().run("request-1", "worker-1", response_for)
        before = {p.relative_to(self.registry): p.read_bytes() for p in self.registry.rglob("*") if p.is_file()}
        code, result = self.invoke_cli("batch-research-validate", self.registry, self.digest, *self.preparations)
        self.assertEqual(code, 0, result)
        self.assertTrue(result["valid"])
        self.assertFalse(result["model_invoked"])
        self.assertEqual({p.relative_to(self.registry): p.read_bytes() for p in self.registry.rglob("*") if p.is_file()}, before)
        (self.artifact() / "output.raw").unlink()
        code, result = self.invoke_cli("batch-research-validate", self.registry, self.digest, *self.preparations)
        self.assertEqual(code, 1)
        self.assertFalse(result["valid"])
        self.assertFalse((self.artifact() / "output.raw").exists())

    def test_cli_missing_registry_or_malformed_digest_never_creates_state(self):
        missing = self.base / "missing-registry"
        code, result = self.invoke_cli("batch-research-validate", missing, self.digest, *self.preparations)
        self.assertEqual(code, 1)
        self.assertFalse(result["valid"])
        self.assertFalse(missing.exists())
        code, result = self.invoke_cli("batch-research-validate", self.registry, "../escape", *self.preparations)
        self.assertEqual(code, 1)
        self.assertFalse(result["valid"])


if __name__ == "__main__":
    unittest.main()
