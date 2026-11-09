"""Trusted local registry tests, with no model calls or network access.

Three integrations fully replay two real V2 preparations: shared-budget restart,
concurrent claiming, and fail-closed incomplete-journal recovery. Other registry
unit cases reuse only the already-verified input scope; registry identity, locking,
claim integrity, ledger replay and filesystem checks remain production code.
"""
from __future__ import annotations

import copy
import contextlib
import io
import json
import multiprocessing
import queue
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from turbo.agents.batch_authorization import build_authorization, canonical_bytes
from turbo.agents.batch_execution import BatchExecution
from turbo.agents.batch_registry import BatchRegistry, ManagedBatchExecution, initialize_registry, inspect_registry, validate_registry_execution
from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT
from turbo.universe.family_pack_v2 import prepare_family_v2


NOW = "2026-11-09T07:00:00Z"
FAMILIES = ["family:coverage:napcs-collection:10:001",
            "family:coverage:prior-candidate:global-challenger:001"]


def clock():
    return NOW


def failure_response():
    return {"outcome": "failed", "output": {"simulation": True},
            "usage": {"input_tokens": 10, "output_tokens": 5}}


def stop_process(process):
    if process.is_alive():
        process.terminate()
    process.join(timeout=5)


def registry_contender(path, authorization, preparation_dirs, start, results, ordinal):
    try:
        registry = BatchRegistry(Path(path), root=ROOT)
        results.put(("ready", ordinal))
        if not start.wait(30):
            results.put(("timeout", ordinal))
            return
        managed = registry.open(authorization, [Path(p) for p in preparation_dirs], clock=clock)
        managed.reserve("request-" + str(ordinal), "worker-" + str(ordinal))
        results.put(("admitted", ordinal))
    except ValueError:
        results.put(("rejected", ordinal))
    except Exception as error:
        results.put((type(error).__name__ + ": " + str(error), ordinal))


def inspect_during_transport(path, authorization, preparation_dirs, results):
    try:
        registry = BatchRegistry(Path(path), root=ROOT)
        managed = registry.open(authorization, [Path(p) for p in preparation_dirs], clock=clock)
        managed.reserve("request-1", "worker-1")
        observed = []
        def transport(_):
            observed.append(managed.status()["requests"]["request-1"]["status"])
            observed.append(isinstance(inspect_registry(Path(path), root=ROOT), dict))
            return failure_response()
        managed.dispatch("request-1", "worker-1", transport)
        results.put(("completed", observed, managed.status()["committed_microusd"]))
    except Exception as error:
        results.put((type(error).__name__, str(error)))


class BatchRegistryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix="turbo-registry-inputs-")
        cls.preparations = []
        for family_id in FAMILIES:
            receipt = prepare_family_v2(family_id, root=ROOT, output_root=Path(cls.fixture.name))
            cls.preparations.append(Path(receipt["preparation_path"]))
        cls.authorization = build_authorization(
            cls.preparations, root=ROOT, authorized_by="simulation-registry-test",
            valid_from_utc="2026-11-09T06:00:00Z", expires_at_utc="2026-11-09T08:00:00Z",
            model="simulation", prompt_sha256="a" * 64,
            pricing={"input_microusd_per_token": 1, "output_microusd_per_token": 2},
            max_cost_microusd=300, max_calls=3, max_input_tokens=100,
            max_output_tokens=100, max_retries=1, max_concurrency=1, lease_seconds=60,
        )

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="turbo-registry-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.path = self.base / "trusted-registry"
        self.auth = copy.deepcopy(self.authorization)
        self.digest = canonical_sha256(self.auth)
        self.journal = self.path / "journals" / self.digest
        if self._testMethodName not in {
            "test_reopening_uses_same_journal_and_cannot_reset_budget",
            "test_two_processes_share_one_claim_and_budget",
            "test_claimed_partial_journal_is_not_recreated",
        }:
            scope = (copy.deepcopy(self.authorization["families"]), self.authorization["batch_id"])
            isolation = patch("turbo.agents.batch_authorization._scope", return_value=scope)
            isolation.start()
            self.addCleanup(isolation.stop)

    def registry(self):
        initialize_registry(self.path, root=ROOT, clock=clock)
        return BatchRegistry(self.path, root=ROOT)

    def managed(self, registry=None):
        return (registry or BatchRegistry(self.path, root=ROOT)).open(
            self.auth, self.preparations, clock=clock
        )

    def test_registry_requires_explicit_initialization(self):
        with self.assertRaises(ValueError):
            BatchRegistry(self.path, root=ROOT)
        with self.assertRaises(ValueError):
            inspect_registry(self.path, root=ROOT)
        self.assertFalse(self.path.exists())
        registry = self.registry()
        self.assertIsNotNone(registry)
        before = {p.relative_to(self.path): p.read_bytes() for p in self.path.rglob("*") if p.is_file()}
        inspect_registry(self.path, root=ROOT)
        after = {p.relative_to(self.path): p.read_bytes() for p in self.path.rglob("*") if p.is_file()}
        self.assertEqual(after, before)
        with self.assertRaises(ValueError):
            initialize_registry(self.path, root=ROOT, clock=clock)

    def test_initialization_refuses_existing_empty_directory(self):
        self.path.mkdir()
        with self.assertRaises(ValueError):
            initialize_registry(self.path, root=ROOT, clock=clock)
        self.assertEqual(list(self.path.iterdir()), [])

    def test_reopening_uses_same_journal_and_cannot_reset_budget(self):
        managed = self.managed(self.registry())
        managed.reserve("request-1", "worker-1")
        managed.dispatch("request-1", "worker-1", lambda _: failure_response())
        original = managed.status()
        journal_bytes = {p.name: p.read_bytes() for p in self.journal.iterdir() if p.is_file()}
        reopened = self.managed()
        self.assertEqual(reopened.status(), original)
        self.assertEqual({p.name: p.read_bytes() for p in self.journal.iterdir() if p.is_file()}, journal_bytes)
        self.assertEqual(reopened.status()["committed_microusd"], 20)
        self.assertEqual(reopened.status()["calls_reserved"], 1)
        with self.assertRaises(ValueError):
            reopened.reserve("request-2", "worker-2", retry_of="request-1")
        self.assertEqual(reopened.status(), original)
        self.assertEqual([p.name for p in (self.path / "journals").iterdir()], [self.digest])

    def test_two_processes_share_one_claim_and_budget(self):
        self.registry()
        context = multiprocessing.get_context("fork")
        start, results = context.Event(), context.Queue()
        processes = [context.Process(target=registry_contender,
            args=(str(self.path), self.auth, [str(p) for p in self.preparations], start, results, n))
            for n in (1, 2)]
        for process in processes:
            process.start()
            self.addCleanup(stop_process, process)
        ready = [results.get(timeout=30) for _ in processes]
        self.assertEqual(sorted(value[0] for value in ready), ["ready", "ready"])
        start.set()
        outcomes = [results.get(timeout=120) for _ in processes]
        for process in processes:
            process.join(timeout=30)
            if process.is_alive():
                process.terminate()
                process.join()
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(sorted(value[0] for value in outcomes), ["admitted", "rejected"])
        state = self.managed().status()
        self.assertEqual(state["calls_reserved"], 1)
        self.assertEqual(state["outstanding_microusd"], 300)
        self.assertEqual(len(state["requests"]), 1)
        self.assertEqual([p.name for p in (self.path / "journals").iterdir()], [self.digest])

    def test_claimed_partial_journal_is_not_recreated(self):
        self.managed(self.registry())
        (self.journal / "events.jsonl").unlink()
        before = sorted(p.relative_to(self.path) for p in self.path.rglob("*"))
        with self.assertRaises(ValueError):
            self.managed()
        self.assertFalse((self.journal / "events.jsonl").exists())
        self.assertEqual(sorted(p.relative_to(self.path) for p in self.path.rglob("*")), before)

    def test_claimed_missing_journal_is_not_recreated(self):
        self.managed(self.registry())
        shutil.rmtree(self.journal)
        with self.assertRaises(ValueError):
            self.managed()
        self.assertFalse(self.journal.exists())

    def test_missing_ready_marker_leaves_claim_unresolved(self):
        self.managed(self.registry())
        ready = self.path / "claims" / (self.digest + ".ready.json")
        ready.unlink()
        with self.assertRaises(ValueError):
            self.managed()
        self.assertFalse(ready.exists())

    def test_orphan_journal_cannot_acquire_new_claim(self):
        self.registry()
        self.journal.mkdir()
        (self.journal / "sentinel").write_text("orphan")
        with self.assertRaises(ValueError):
            self.managed()
        self.assertEqual((self.journal / "sentinel").read_text(), "orphan")
        self.assertFalse((self.journal / "events.jsonl").exists())

    def test_registry_marker_replacement_invalidates_open_handle(self):
        managed = self.managed(self.registry())
        other = self.base / "other-registry"
        initialize_registry(other, root=ROOT, clock=clock)
        (self.path / "registry.json").write_bytes((other / "registry.json").read_bytes())
        with self.assertRaises(ValueError):
            managed.reserve("request-1", "worker-1")
        with self.assertRaises(ValueError):
            BatchRegistry(self.path, root=ROOT)

    def test_copied_registry_cannot_be_rebound_to_new_path(self):
        self.managed(self.registry())
        copied = self.base / "copied-registry"
        shutil.copytree(self.path, copied)
        with self.assertRaises(ValueError):
            BatchRegistry(copied, root=ROOT)

    def test_missing_registry_lock_is_not_recreated(self):
        managed = self.managed(self.registry())
        lock = self.path / ".lock"
        lock.unlink()
        with self.assertRaises(ValueError):
            managed.reserve("request-1", "worker-1")
        self.assertFalse(lock.exists())

    def test_claim_paths_and_digest_traversal_fail_closed(self):
        self.managed(self.registry())
        for digest in ("../outside", self.digest + "/../outside", "A" * 64):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                validate_registry_execution(self.path, digest, self.preparations, root=ROOT)
        claim_path = self.path / "claims" / (self.digest + ".json")
        claim = json.loads(claim_path.read_text())
        claim["journal_path"] = "../outside"
        claim_path.write_bytes(canonical_bytes(claim))
        with self.assertRaises(ValueError):
            self.managed()

    def test_registry_symlink_is_not_a_trusted_location(self):
        self.registry()
        alias = self.base / "alias"
        alias.symlink_to(self.path, target_is_directory=True)
        with self.assertRaises(ValueError):
            BatchRegistry(alias, root=ROOT)

    def test_journal_directory_symlink_cannot_redirect_a_managed_handle(self):
        managed = self.managed(self.registry())
        outside = self.base / "outside"
        outside.mkdir()
        marker = outside / "sentinel"
        marker.write_text("unchanged")
        shutil.rmtree(self.journal)
        self.journal.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            managed.reserve("request-1", "worker-1")
        self.assertEqual(list(outside.iterdir()), [marker])
        self.assertEqual(marker.read_text(), "unchanged")

    def test_journal_file_symlink_cannot_redirect_writes(self):
        managed = self.managed(self.registry())
        outside = self.base / "outside.jsonl"
        outside.write_text("untouched")
        (self.journal / "events.jsonl").unlink()
        (self.journal / "events.jsonl").symlink_to(outside)
        with self.assertRaises(ValueError):
            managed.reserve("request-1", "worker-1")
        self.assertEqual(outside.read_text(), "untouched")

    def test_claim_symlink_is_rejected_without_reading_or_modifying_target(self):
        self.managed(self.registry())
        claim = self.path / "claims" / (self.digest + ".json")
        outside = self.base / "outside-claim.json"
        outside.write_bytes(claim.read_bytes())
        before = outside.read_bytes()
        claim.unlink()
        claim.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.managed()
        self.assertEqual(outside.read_bytes(), before)

    def test_managed_api_does_not_accept_an_alternate_output_directory(self):
        registry = self.registry()
        destination = self.base / "fresh-budget"
        with self.assertRaises(TypeError):
            registry.open(self.auth, self.preparations, clock=clock, output_root=destination)
        self.assertFalse(destination.exists())

    def test_transport_can_inspect_status_without_registry_lock_deadlock(self):
        self.registry()
        context = multiprocessing.get_context("fork")
        results = context.Queue()
        process = context.Process(target=inspect_during_transport,
            args=(str(self.path), self.auth, [str(p) for p in self.preparations], results))
        process.start()
        try:
            result = results.get(timeout=30)
        except queue.Empty:
            self.fail("transport callback blocked while reading registry or journal status")
        finally:
            process.join(timeout=2)
            if process.is_alive():
                process.terminate()
                process.join()
        self.assertEqual(process.exitcode, 0)
        self.assertEqual(result, ("completed", ["dispatched", True], 20))

    def test_existing_journal_cannot_change_authorization_under_same_claim(self):
        managed = self.managed(self.registry())
        changed = copy.deepcopy(self.auth)
        changed["max_cost_microusd"] = 600
        (self.journal / "authorization.json").write_bytes(canonical_bytes(changed))
        with self.assertRaises(ValueError):
            managed.reserve("request-1", "worker-1")
        with self.assertRaises(ValueError):
            self.managed()

    def test_changed_document_is_a_distinct_unsigned_simulation_scenario(self):
        registry = self.registry()
        first = self.managed(registry)
        first.reserve("request-1", "worker-1")
        changed = copy.deepcopy(self.auth)
        changed["max_cost_microusd"] = 600
        changed_digest = canonical_sha256(changed)
        self.assertNotEqual(changed_digest, self.digest)
        second = registry.open(changed, self.preparations, clock=clock)
        self.assertEqual(second.status()["calls_reserved"], 0)
        self.assertEqual(first.status()["calls_reserved"], 1)
        self.assertEqual({p.name for p in (self.path / "journals").iterdir()},
                         {self.digest, changed_digest})

    def test_public_managed_wrapper_cannot_delegate_to_an_unrelated_journal(self):
        registry = self.registry()
        self.managed(registry)
        outside = BatchExecution(self.base / "unmanaged", self.auth, self.preparations,
                                 root=ROOT, clock=clock)
        with self.assertRaises(ValueError):
            forged = ManagedBatchExecution(registry, self.digest, outside)
            forged.reserve("request-1", "worker-1")
        self.assertEqual(outside.status()["calls_reserved"], 0)
        self.assertEqual(self.managed(registry).status()["calls_reserved"], 0)

    def test_managed_handle_rejects_rebound_execution_directory_auth_or_root(self):
        registry = self.registry()
        managed = self.managed(registry)
        outside = BatchExecution(self.base / "unmanaged", self.auth, self.preparations,
                                 root=ROOT, clock=clock)
        execution = managed._execution
        original = (execution.directory, copy.deepcopy(execution.authorization), execution.root)
        mutations = (
            lambda: setattr(execution, "directory", outside.directory),
            lambda: execution.authorization.update(model="different-simulation"),
            lambda: setattr(execution, "root", self.base),
        )
        for mutation in mutations:
            execution.directory, execution.authorization, execution.root = (
                original[0], copy.deepcopy(original[1]), original[2])
            mutation()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                managed.reserve("request-1", "worker-1")
        execution.directory, execution.authorization, execution.root = original
        self.assertEqual(managed.status()["calls_reserved"], 0)
        self.assertEqual(outside.status()["calls_reserved"], 0)

    def test_legacy_single_journal_execution_remains_available(self):
        path = self.base / "legacy"
        ledger = BatchExecution(path, self.auth, self.preparations, root=ROOT, clock=clock)
        ledger.reserve("request-1", "worker-1")
        self.assertEqual(ledger.status()["budget_scope"], "single_journal_simulation")
        self.assertEqual(ledger.status()["calls_reserved"], 1)
        self.assertFalse(self.path.exists())

    def invoke_cli(self, *arguments):
        from turbo.cli import main
        output = io.StringIO()
        with patch("sys.argv", ["turbo", *map(str, arguments)]), contextlib.redirect_stdout(output):
            code = main()
        return code, json.loads(output.getvalue())

    def test_cli_explicit_init_status_and_validation(self):
        code, initialized = self.invoke_cli("batch-registry-init", self.path)
        self.assertEqual(code, 0, initialized)
        self.assertEqual(initialized["mode"], "simulation_only")
        code, empty = self.invoke_cli("batch-registry-status", self.path)
        self.assertEqual(code, 0, empty)
        self.assertEqual(empty["claims"], [])
        managed = self.managed()
        managed.reserve("request-1", "worker-1")
        before = {p.relative_to(self.path): p.read_bytes() for p in self.path.rglob("*") if p.is_file()}
        code, status = self.invoke_cli("batch-registry-status", self.path)
        self.assertEqual(code, 0, status)
        self.assertEqual(status["claims"][0]["calls_reserved"], 1)
        code, validation = self.invoke_cli("batch-registry-validate", self.path, self.digest, *self.preparations)
        self.assertEqual(code, 0, validation)
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["managed_budget_scope"], "single_registry_exact_authorization")
        after = {p.relative_to(self.path): p.read_bytes() for p in self.path.rglob("*") if p.is_file()}
        self.assertEqual(after, before)

    def test_cli_missing_status_never_initializes_registry(self):
        code, result = self.invoke_cli("batch-registry-status", self.path)
        self.assertEqual(code, 1)
        self.assertFalse(result["valid"])
        self.assertFalse(self.path.exists())
        code, result = self.invoke_cli("batch-registry-validate", self.path, "../outside", *self.preparations)
        self.assertEqual(code, 1)
        self.assertFalse(result["valid"])
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
