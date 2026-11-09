"""Explicit predecessor recovery; controlled transports only, no live billing."""
import copy
import hashlib
import json
import unittest

import test_batch_provider as fixtures
from turbo.agents import batch_provider as provider, batch_recovery as recovery
from turbo.agents import batch_execution_v2 as ledger


class RecoveryTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.BatchProviderTest.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.BatchProviderTest.tearDownClass.__func__)
    setUp = fixtures.BatchProviderTest.setUp
    payload = fixtures.BatchProviderTest.payload
    transport_for = fixtures.BatchProviderTest.transport_for
    run_role = fixtures.BatchProviderTest.run_role
    verifier_document = fixtures.BatchProviderTest.verifier_document
    compiled_preview = fixtures.BatchProviderTest.compiled_preview
    review_document = fixtures.BatchProviderTest.review_document

    def reject(self, status=402):
        self.assertEqual(self.run_role('primary', {'payload': self.payload()})['status'], 'succeeded')
        result = provider.run_batch_role(self.directory, self.registry, self.authorization,
            'verifier', 'rejected-verifier', input_root=self.input_root,
            api_key='synthetic-secret', clock=lambda: fixtures.NOW,
            transport=lambda *args: (status, {}, b'{"error":{"message":"controlled rejection"}}'))
        self.assertEqual(result['status'], 'unresolved')

    def prepare(self, replacement='replacement-verifier'):
        return recovery.prepare_successor(self.registry, self.authorization,
            workflow_dir=self.directory, input_root=self.input_root,
            replacement_attempt_id=replacement, authorized_by='explicit controlled recovery',
            valid_from_utc='2026-11-09T16:00:00Z', expires_at_utc='2026-11-09T18:00:00Z')

    def test_recovery_preserves_primary_and_full_unknown_exposure_without_resending(self):
        self.reject()
        source = ledger.BatchExecutionV2(self.registry, self.authorization)
        source_events = (source.journal_path / 'events.jsonl').read_bytes()
        auth, cp = self.prepare()
        self.assertEqual(auth['max_cost_microusd'], 980)  # 20 known + 200 unknown retained.
        self.assertEqual(auth['max_calls'], 4)  # Both physical predecessor calls count.
        path = recovery.claim_successor(self.registry, auth, cp)
        self.assertEqual(recovery.claim_successor(self.registry, auth, cp), path)
        doc = self.verifier_document()
        options = dict(input_root=self.input_root, api_key='synthetic-secret',
            clock=lambda: fixtures.NOW, recovery_checkpoint=path, transport=self.transport_for(doc))
        result = provider.run_batch_role(self.directory, self.registry, auth,
            'verifier', 'replacement-verifier', **options)
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(len(self.calls), 2)  # One original primary and one replacement verifier.
        replay = provider.run_batch_role(self.directory, self.registry, auth,
            'verifier', 'replacement-verifier', **options)
        self.assertEqual(replay, result)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual((source.journal_path / 'events.jsonl').read_bytes(), source_events)
        self.assertEqual(source.status()['requests']['rejected-verifier']['status'], 'unresolved')
        preview = self.compiled_preview()
        options['transport'] = self.transport_for(self.review_document(preview))
        review = provider.run_batch_role(self.directory, self.registry, auth,
            'release_reviewer', 'recovered-review', **options)
        self.assertEqual(review['status'], 'succeeded')
        self.assertEqual(len(self.calls), 3)
        from turbo.universe.batch_closure import finalize_batch_closure, validate_batch_closure
        from turbo.pipeline_paths import ROOT
        from pathlib import Path
        closed = finalize_batch_closure(self.directory, output_root=self.base / 'closures', root=ROOT)
        self.assertTrue(validate_batch_closure(Path(closed['closure_dir']), self.directory, root=ROOT)['valid'])
        self.assertEqual((source.journal_path / 'events.jsonl').read_bytes(), source_events)

    def test_no_fork_no_changed_budget_and_exact_replacement(self):
        self.reject()
        auth, cp = self.prepare()
        path = recovery.claim_successor(self.registry, auth, cp)
        other_auth, other_cp = self.prepare('second-replacement')
        with self.assertRaisesRegex(ValueError, 'already claimed'):
            recovery.claim_successor(self.registry, other_auth, other_cp)
        changed = copy.deepcopy(auth); changed['max_cost_microusd'] += 1
        with self.assertRaises(ValueError): recovery.claim_successor(self.registry, changed, cp)
        engine = recovery.RecoveryExecution(self.registry, auth, path, clock=lambda: fixtures.NOW)
        for role, attempt in [('primary', 'another-primary'), ('verifier', 'wrong-replacement')]:
            with self.assertRaises(ValueError):
                engine.run(role, attempt, lambda _: self.fail('must not dispatch'), input_sha256='a' * 64)

    def test_unknown_provider_failure_is_not_recoverable(self):
        self.reject(status=503)
        with self.assertRaisesRegex(ValueError, 'HTTP 402'): self.prepare()

    def test_changed_checkpoint_or_model_is_rejected(self):
        self.reject()
        auth, cp = self.prepare()
        cp['retained_unknown_microusd'] = 0
        with self.assertRaises(ValueError): recovery.claim_successor(self.registry, auth, cp)

    def test_post_claim_tampering_is_bound_to_immutable_successor_authority(self):
        self.reject()
        auth, cp = self.prepare()
        other_auth, _ = self.prepare('other-exact-attempt')
        self.assertNotEqual(ledger._hash(auth), ledger._hash(other_auth))
        path = recovery.claim_successor(self.registry, auth, cp)
        for field, value in [('replacement_attempt_id', 'changed'), ('authorized_by', 'changed'),
                             ('workflow_path', '/changed'), ('input_root', '/changed')]:
            changed = copy.deepcopy(cp); changed[field] = value
            path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                recovery.RecoveryExecution(self.registry, auth, path)
        path.write_text(json.dumps(cp))
        auth, cp = self.prepare()
        auth['roles']['verifier']['model'] = 'test/other'
        with self.assertRaises(ValueError): recovery.claim_successor(self.registry, auth, cp)

    def test_legacy_v2_replay_source_is_unchanged(self):
        # Recovery must never mutate the implementation that old authorizations pin.
        expected = '0a9c19bde71e5d55843581ca406e6b28ad5dad4e8c234c957dbf195b8804f56a'
        from pathlib import Path
        self.assertEqual(hashlib.sha256(Path(ledger.__file__).read_bytes()).hexdigest(), expected)

    def test_missing_predecessor_is_read_only(self):
        before = sorted(str(p.relative_to(self.registry)) for p in self.registry.rglob('*'))
        with self.assertRaises(ValueError): self.prepare()
        self.assertEqual(before, sorted(str(p.relative_to(self.registry)) for p in self.registry.rglob('*')))


if __name__ == '__main__': unittest.main()
