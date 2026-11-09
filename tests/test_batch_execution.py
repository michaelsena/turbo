"""No-network acceptance tests for the batch admission and recovery ledger.

All tests start from real, replay-verified V2 preparations. Scope/byte integrity,
batch dispatch, restart, process-race, hard-crash, and CLI integrations recompile
those inputs through production validation. Other ledger unit cases isolate only
that expensive input replay using the already-verified scope; authorization
schemas, hashes, arithmetic, locks, transitions, and disk replay remain real.
"""
from __future__ import annotations

import copy
import contextlib
import io
import json
import multiprocessing
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from turbo.agents.batch_authorization import build_authorization, validate_authorization
from turbo.agents.boundary_harness import canonical_sha256
from turbo.agents.batch_execution import BatchExecution, inspect_execution, replay_events
from turbo.pipeline_paths import ROOT
from turbo.universe.family_pack_v2 import prepare_family_v2


NOW = "2026-11-09T07:00:00Z"
LATER = "2026-11-09T07:02:00Z"
FAMILIES = [
    "family:coverage:napcs-collection:10:001",
    "family:coverage:prior-candidate:global-challenger:001",
]


class Clock:
    def __init__(self, value: str = NOW):
        self.value = value

    def __call__(self) -> str:
        return self.value


def successful_response(input_tokens: int = 10, output_tokens: int = 5) -> dict:
    return {
        "outcome": "succeeded",
        "output": {"simulation": True},
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def contend_for_reservation(directory, authorization, preparations, start, results, request_id):
    """A separate process must participate in the same on-disk admission lock."""
    try:
        ledger = BatchExecution(
            Path(directory), authorization, [Path(p) for p in preparations], root=ROOT, clock=Clock()
        )
        if not start.wait(30):
            results.put((request_id, "timeout"))
            return
        ledger.reserve(request_id, "worker-" + request_id)
        results.put((request_id, "admitted"))
    except ValueError:
        results.put((request_id, "rejected"))
    except Exception as error:
        results.put((request_id, type(error).__name__ + ": " + str(error)))


class BatchExecutionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix="turbo-batch-test-inputs-")
        cls.preparations = []
        for family_id in FAMILIES:
            result = prepare_family_v2(family_id, root=ROOT, output_root=Path(cls.fixture.name))
            cls.preparations.append(Path(result["preparation_path"]))
        cls.base_options = {
            "authorized_by": "test-only-no-spend",
            "valid_from_utc": "2026-11-09T06:00:00Z",
            "expires_at_utc": "2026-11-09T08:00:00Z",
            "model": "simulation",
            "prompt_sha256": "a" * 64,
            "pricing": {"input_microusd_per_token": 1, "output_microusd_per_token": 2},
            "max_cost_microusd": 900,
            "max_calls": 4,
            "max_input_tokens": 100,
            "max_output_tokens": 100,
            "max_retries": 1,
            "max_concurrency": 1,
            "lease_seconds": 60,
        }
        cls.base_authorization = build_authorization(cls.preparations, root=ROOT, **cls.base_options)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="turbo-batch-test-ledger-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "execution"
        self.clock = Clock()
        self.auth = copy.deepcopy(self.base_authorization)
        integration_tests = {
            "test_one_request_contains_both_manifest_ordered_families",
            "test_exact_preparation_order_and_scope_are_required",
            "test_changed_pack_bytes_are_rejected",
            "test_two_processes_cannot_spend_the_last_budget_slot",
            "test_process_crash_after_dispatch_never_releases_or_retries",
            "test_restart_and_recovery_do_not_rewrite_completed_events",
            "test_read_only_cli_dry_run_status_and_validation",
        }
        if self._testMethodName not in integration_tests:
            scope = (copy.deepcopy(self.base_authorization["families"]),
                     self.base_authorization["batch_id"])
            replay = patch("turbo.agents.batch_authorization._scope", return_value=scope)
            replay.start()
            self.addCleanup(replay.stop)

    def authorization(self, **overrides):
        options = {**self.base_options, **overrides}
        return build_authorization(self.preparations, root=ROOT, **options)

    def ledger(self, authorization=None):
        return BatchExecution(
            self.directory, authorization or self.auth, self.preparations, root=ROOT, clock=self.clock
        )

    def test_one_request_contains_both_manifest_ordered_families(self):
        ledger = self.ledger()
        captured = []
        def transport(envelope):
            captured.append(envelope)
            return successful_response()
        ledger.reserve("request-1", "worker-1")
        ledger.dispatch("request-1", "worker-1", transport)
        self.assertEqual(len(captured), 1)
        self.assertEqual([f["family_id"] for f in captured[0]["families"]], FAMILIES)
        self.assertTrue(all(f["preparation_id"] and f["pack"] for f in captured[0]["families"]))
        status = ledger.status()
        self.assertEqual(status["requests"]["request-1"]["status"], "succeeded")
        self.assertEqual(status["committed_microusd"], 20)
        self.assertEqual(status["outstanding_microusd"], 0)
        self.assertEqual(status["budget_scope"], "single_journal_simulation")
        self.assertEqual(self.auth["budget_scope"], "single_journal_simulation")

    def test_exact_preparation_order_and_scope_are_required(self):
        for preparations in (self.preparations[:1], list(reversed(self.preparations)),
                             [self.preparations[0], self.preparations[0]]):
            with self.subTest(preparations=preparations), self.assertRaises(ValueError):
                validate_authorization(self.auth, preparations, root=ROOT, now=NOW)

    def test_authorization_requires_exact_family_and_preparation_hashes(self):
        for field in ("family_id", "preparation_id", "config_sha256", "pack_file_sha256", "receipt_sha256"):
            auth = copy.deepcopy(self.auth)
            auth["families"][0][field] = "0" * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_authorization(auth, self.preparations, root=ROOT, now=NOW)

    def test_changed_pack_bytes_are_rejected(self):
        path = self.preparations[0] / "family-evidence-pack-v2.json"
        original = path.read_bytes()
        try:
            path.write_bytes(original + b" ")
            with self.assertRaises(ValueError):
                validate_authorization(self.auth, self.preparations, root=ROOT, now=NOW)
        finally:
            path.write_bytes(original)

    def test_expired_and_not_yet_valid_authorization_reject_before_admission(self):
        ledger = self.ledger()
        for now in ("2026-11-09T05:59:59Z", "2026-11-09T08:00:00Z"):
            self.clock.value = now
            with self.subTest(now=now), self.assertRaises(ValueError):
                ledger.reserve("request-1", "worker-1")
        self.assertEqual(ledger.status()["calls_reserved"], 0)

    def test_unsupported_provider_and_malformed_caps_are_rejected(self):
        for key, value in (("provider", "openrouter"), ("max_concurrency", 2),
                           ("max_calls", True), ("max_cost_microusd", -1)):
            auth = copy.deepcopy(self.auth)
            auth[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_authorization(auth, self.preparations, root=ROOT, now=NOW)

    def test_reopening_with_changed_model_pricing_or_scope_is_rejected(self):
        self.ledger()
        for mutation in (lambda auth: auth.update(model="other-model"),
                         lambda auth: auth["pricing"].update(input_microusd_per_token=100)):
            auth = copy.deepcopy(self.auth)
            mutation(auth)
            with self.subTest(authorization=auth), self.assertRaises(ValueError):
                self.ledger(auth)

    def test_reservation_requires_worst_case_budget_not_actual_usage(self):
        ledger = self.ledger(self.authorization(max_cost_microusd=300))
        ledger.reserve("request-1", "worker-1")
        self.assertEqual(ledger.status()["outstanding_microusd"], 300)
        failed = {**successful_response(), "outcome": "failed"}
        ledger.dispatch("request-1", "worker-1", lambda _: failed)
        self.assertEqual(ledger.status()["committed_microusd"], 20)
        with self.assertRaises(ValueError):
            ledger.reserve("request-2", "worker-2", retry_of="request-1")
        self.assertEqual(ledger.status()["calls_reserved"], 1)

    def test_budget_exact_boundary_allows_retry_reservation(self):
        ledger = self.ledger(self.authorization(max_cost_microusd=320))
        ledger.reserve("request-1", "worker-1")
        failed = {**successful_response(), "outcome": "failed"}
        ledger.dispatch("request-1", "worker-1", lambda _: failed)
        ledger.reserve("request-2", "worker-2", retry_of="request-1")
        status = ledger.status()
        self.assertEqual(status["committed_microusd"] + status["outstanding_microusd"], 320)
        with self.assertRaises(ValueError):
            ledger.reserve("request-3", "worker-3", retry_of="request-1")
        self.assertEqual(ledger.status()["calls_reserved"], 2)

    def test_default_concurrency_blocks_second_outstanding_request(self):
        ledger = self.ledger()
        ledger.reserve("request-1", "worker-1")
        with self.assertRaises(ValueError):
            ledger.reserve("request-2", "worker-2")

    def test_two_processes_cannot_spend_the_last_budget_slot(self):
        authorization = self.authorization(max_cost_microusd=300)
        ledger = self.ledger(authorization)
        context = multiprocessing.get_context("fork")
        start, results = context.Event(), context.Queue()
        processes = [context.Process(target=contend_for_reservation,
            args=(str(self.directory), authorization, [str(p) for p in self.preparations],
                  start, results, "request-" + str(i))) for i in range(2)]
        for process in processes:
            process.start()
        start.set()
        answers = [results.get(timeout=90) for _ in processes]
        for process in processes:
            process.join(timeout=30)
            if process.is_alive():
                process.terminate()
                process.join()
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(sorted(answer[1] for answer in answers), ["admitted", "rejected"])
        self.assertEqual(ledger.status()["outstanding_microusd"], 300)
        self.assertEqual(ledger.status()["calls_reserved"], 1)

    def test_settled_failure_retry_consumes_separate_call_and_retry_caps(self):
        ledger = self.ledger()
        failed = successful_response()
        failed["outcome"] = "failed"
        ledger.reserve("request-1", "worker-1")
        ledger.dispatch("request-1", "worker-1", lambda _: failed)
        ledger.reserve("request-2", "worker-2", retry_of="request-1")
        ledger.dispatch("request-2", "worker-2", lambda _: failed)
        self.assertEqual(ledger.status()["calls_reserved"], 2)
        self.assertEqual(ledger.status()["retries_reserved"], 1)
        self.assertEqual(ledger.status()["committed_microusd"], 40)
        with self.assertRaises(ValueError):
            ledger.reserve("request-3", "worker-3", retry_of="request-2")

    def test_new_root_ids_and_forked_retry_chains_cannot_bypass_retry_cap(self):
        ledger = self.ledger(self.authorization(max_calls=4, max_retries=2))
        failed = {**successful_response(), "outcome": "failed"}
        ledger.reserve("request-1", "worker-1")
        ledger.dispatch("request-1", "worker-1", lambda _: failed)
        with self.assertRaises(ValueError):
            ledger.reserve("unrelated-root", "worker-2")
        ledger.reserve("request-2", "worker-2", retry_of="request-1")
        ledger.dispatch("request-2", "worker-2", lambda _: failed)
        with self.assertRaises(ValueError):
            ledger.reserve("fork-request", "worker-3", retry_of="request-1")
        ledger.reserve("request-3", "worker-3", retry_of="request-2")
        self.assertEqual(ledger.status()["calls_reserved"], 3)
        self.assertEqual(ledger.status()["retries_reserved"], 2)

    def test_successful_request_cannot_be_retried(self):
        ledger = self.ledger()
        ledger.reserve("request-1", "worker-1")
        ledger.dispatch("request-1", "worker-1", lambda _: successful_response())
        with self.assertRaises(ValueError):
            ledger.reserve("request-2", "worker-2", retry_of="request-1")

    def test_call_cap_survives_reserved_lease_expiry(self):
        ledger = self.ledger(self.authorization(max_calls=1, max_retries=0))
        ledger.reserve("request-1", "worker-1")
        self.clock.value = LATER
        ledger.recover_expired()
        status = ledger.status()
        self.assertEqual(status["requests"]["request-1"]["status"], "released")
        self.assertEqual(status["outstanding_microusd"], 0)
        self.assertEqual(status["calls_reserved"], 1)
        with self.assertRaises(ValueError):
            ledger.reserve("request-2", "worker-2")

    def test_undispatched_expired_request_can_resume_as_explicit_retry(self):
        ledger = self.ledger()
        ledger.reserve("request-1", "worker-1")
        self.clock.value = LATER
        ledger.recover_expired()
        ledger.reserve("request-2", "worker-2", retry_of="request-1")
        status = ledger.status()
        self.assertEqual(status["requests"]["request-2"]["worker_id"], "worker-2")
        self.assertEqual(status["requests"]["request-2"]["status"], "reserved")
        self.assertEqual(status["calls_reserved"], 2)
        self.assertEqual(status["retries_reserved"], 1)
        self.assertEqual(status["outstanding_microusd"], 300)
        ledger.dispatch("request-2", "worker-2", lambda _: successful_response())
        self.assertEqual(ledger.status()["committed_microusd"], 20)

    def test_dispatch_intent_is_durable_before_transport_and_timeout_is_unresolved(self):
        ledger = self.ledger()
        calls = []
        observed_statuses = []
        def failing_transport(_):
            calls.append(1)
            disk = inspect_execution(self.directory, root=ROOT)
            observed_statuses.append(disk["requests"]["request-1"]["status"])
            raise TimeoutError("delivery may already have occurred")
        ledger.reserve("request-1", "worker-1")
        ledger.dispatch("request-1", "worker-1", failing_transport)
        self.clock.value = LATER
        ledger.recover_expired()
        status = ledger.status()
        self.assertEqual(status["requests"]["request-1"]["status"], "unresolved")
        self.assertEqual(status["outstanding_microusd"], 300)
        repeated = ledger.dispatch("request-1", "worker-1", failing_transport)
        self.assertEqual(repeated["status"], "unresolved")
        with self.assertRaises(ValueError):
            ledger.reserve("request-2", "worker-2", retry_of="request-1")
        self.assertEqual(calls, [1])
        self.assertEqual(observed_statuses, ["dispatched"])

    def test_process_crash_after_dispatch_never_releases_or_retries(self):
        ledger = self.ledger()
        ledger.reserve("request-1", "worker-1")
        def crash(_):
            raise SystemExit("simulated process death after dispatch intent")
        with self.assertRaises(SystemExit):
            ledger.dispatch("request-1", "worker-1", crash)
        self.assertEqual(ledger.status()["requests"]["request-1"]["status"], "dispatched")
        self.clock.value = LATER
        restarted = self.ledger()
        restarted.recover_expired()
        before = restarted.status()
        self.assertEqual(before["requests"]["request-1"]["status"], "unresolved")
        self.assertEqual(before["outstanding_microusd"], 300)
        restarted.recover_expired()
        self.assertEqual(restarted.status(), before)
        restarted.settle("request-1", "worker-1", successful_response())
        self.assertEqual(restarted.status()["committed_microusd"], 20)
        self.assertEqual(restarted.status()["outstanding_microusd"], 0)

    def test_malformed_missing_and_over_limit_usage_keep_reservation(self):
        cases = [None, {}, {"input_tokens": True, "output_tokens": 1},
                 {"input_tokens": -1, "output_tokens": 1},
                 {"input_tokens": 101, "output_tokens": 1},
                 {"input_tokens": 1, "output_tokens": 1.5}]
        for index, usage in enumerate(cases):
            with self.subTest(usage=usage):
                directory = Path(self.temporary.name) / str(index)
                ledger = BatchExecution(directory, self.auth, self.preparations, root=ROOT, clock=self.clock)
                response = successful_response()
                response["usage"] = usage
                ledger.reserve("request-1", "worker-1")
                ledger.dispatch("request-1", "worker-1", lambda _, r=response: r)
                self.assertEqual(ledger.status()["requests"]["request-1"]["status"], "unresolved")
                self.assertEqual(ledger.status()["outstanding_microusd"], 300)
                self.assertEqual(ledger.status()["committed_microusd"], 0)

    def test_unrepresentable_output_keeps_reservation_unresolved(self):
        ledger = self.ledger()
        ledger.reserve("request-1", "worker-1")
        response = successful_response()
        response["output"] = {"unaccepted_fraction": 1.5}
        ledger.dispatch("request-1", "worker-1", lambda _: response)
        self.assertEqual(ledger.status()["requests"]["request-1"]["status"], "unresolved")
        self.assertEqual(ledger.status()["outstanding_microusd"], 300)
        self.assertEqual(ledger.status()["committed_microusd"], 0)

    def test_duplicate_response_is_idempotent_but_conflicting_response_rejected(self):
        ledger = self.ledger()
        response = successful_response()
        ledger.reserve("request-1", "worker-1")
        ledger.dispatch("request-1", "worker-1", lambda _: response)
        before = ledger.status()
        ledger.settle("request-1", "worker-1", response)
        self.assertEqual(ledger.status(), before)
        with self.assertRaises(ValueError):
            ledger.settle("request-1", "worker-1", successful_response(11, 5))
        self.assertEqual(ledger.status(), before)

    def test_wrong_worker_cannot_dispatch_or_settle(self):
        ledger = self.ledger()
        ledger.reserve("request-1", "worker-1")
        calls = []
        with self.assertRaises(ValueError):
            ledger.dispatch("request-1", "worker-other", lambda _: calls.append(1))
        with self.assertRaises(ValueError):
            ledger.settle("request-1", "worker-other", successful_response())
        self.assertEqual(calls, [])

    def test_restart_and_recovery_do_not_rewrite_completed_events(self):
        ledger = self.ledger()
        ledger.reserve("request-1", "worker-1")
        ledger.dispatch("request-1", "worker-1", lambda _: successful_response())
        before = ledger.status()
        files_before = {p.name: p.read_bytes() for p in self.directory.iterdir() if p.is_file()}
        restarted = self.ledger()
        restarted.recover_expired()
        self.assertEqual(restarted.status(), before)
        self.assertEqual({p.name: p.read_bytes() for p in self.directory.iterdir() if p.is_file()}, files_before)

    def test_ledger_tampering_and_noncanonical_bytes_fail_closed(self):
        ledger = self.ledger()
        ledger.reserve("request-1", "worker-1")
        event_path = self.directory / "events.jsonl"
        original = event_path.read_bytes()
        try:
            event_path.write_bytes(original + b"\n")
            with self.assertRaises(ValueError):
                ledger.status()
            lines = original.decode().splitlines()
            event = json.loads(lines[-1])
            event["unexpected"] = "tampered"
            lines[-1] = json.dumps(event, sort_keys=True, separators=(",", ":"))
            event_path.write_text("\n".join(lines) + "\n")
            with self.assertRaises(ValueError):
                ledger.status()
        finally:
            event_path.write_bytes(original)

    def test_rehashed_events_cannot_change_reservation_or_settlement_arithmetic(self):
        ledger = self.ledger()
        ledger.reserve("request-1", "worker-1")
        ledger.dispatch("request-1", "worker-1", lambda _: successful_response())
        original = [json.loads(line) for line in (self.directory / "events.jsonl").read_text().splitlines()]
        self.assertEqual(replay_events(original, self.auth, root=ROOT), ledger.status())
        for kind, field in (("reserved", "reserved_microusd"), ("settled", "cost_microusd")):
            events = copy.deepcopy(original)
            target = next(event for event in events if event["kind"] == kind)
            target["data"][field] = 0
            previous = None
            for event in events:
                event["previous_sha256"] = previous
                event["sha256"] = canonical_sha256({k: v for k, v in event.items() if k != "sha256"})
                previous = event["sha256"]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                replay_events(events, self.auth, root=ROOT)

    def invoke_cli(self, *arguments):
        from turbo.cli import main
        output = io.StringIO()
        with patch("sys.argv", ["turbo", *map(str, arguments)]), contextlib.redirect_stdout(output):
            code = main()
        return code, json.loads(output.getvalue())

    def test_read_only_cli_dry_run_status_and_validation(self):
        auth = self.authorization(valid_from_utc="2000-01-01T00:00:00Z",
                                  expires_at_utc="2100-01-01T00:00:00Z")
        authorization_path = Path(self.temporary.name) / "input.json"
        authorization_path.write_text(json.dumps(auth))
        before = sorted(Path(self.temporary.name).rglob("*"))
        code, result = self.invoke_cli("batch-dry-run", authorization_path, *self.preparations)
        self.assertEqual(code, 0, result)
        self.assertEqual(sorted(Path(self.temporary.name).rglob("*")), before)
        ledger = self.ledger(auth)
        ledger.reserve("request-1", "worker-1")
        code, result = self.invoke_cli("batch-status", self.directory)
        self.assertEqual(code, 0, result)
        code, result = self.invoke_cli("batch-validate-execution", self.directory, *self.preparations)
        self.assertEqual(code, 0, result)
        (self.directory / "events.jsonl").write_text("{}\n")
        code, result = self.invoke_cli("batch-validate-execution", self.directory, *self.preparations)
        self.assertEqual(code, 1)
        self.assertFalse(result["valid"])



if __name__ == "__main__":
    unittest.main()
