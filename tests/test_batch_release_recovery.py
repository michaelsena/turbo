"""Release HTTP-400 successor uses controlled transports, never live billing."""
import copy
import hashlib
import json
import unittest

import test_batch_provider as fixtures
from turbo.agents import batch_provider as provider, batch_release_recovery as recovery
from turbo.agents import batch_execution_v2 as ledger


class ReleaseRecoveryTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.BatchProviderTest.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.BatchProviderTest.tearDownClass.__func__)
    setUp = fixtures.BatchProviderTest.setUp
    payload = fixtures.BatchProviderTest.payload
    transport_for = fixtures.BatchProviderTest.transport_for
    run_role = fixtures.BatchProviderTest.run_role
    verifier_document = fixtures.BatchProviderTest.verifier_document
    compiled_preview = fixtures.BatchProviderTest.compiled_preview
    review_document = fixtures.BatchProviderTest.review_document

    def reject(self, status=400, response=None):
        self.assertEqual(self.run_role('primary', {'payload': self.payload()})['status'], 'succeeded')
        self.assertEqual(self.run_role('verifier', self.verifier_document())['status'], 'succeeded')
        self.preview = self.compiled_preview()
        result = provider.run_batch_role(self.directory, self.registry, self.authorization,
            'release_reviewer', 'rejected-release', input_root=self.input_root,
            api_key='synthetic-secret', clock=lambda: fixtures.NOW,
            transport=lambda *args: (status, {}, json.dumps(response or {'error': {'message': 'controlled'}}).encode()))
        self.assertEqual(result['status'], 'unresolved')

    def prepare(self, replacement='replacement-release'):
        return recovery.prepare_successor(self.registry, self.authorization,
            workflow_dir=self.directory, input_root=self.input_root,
            replacement_attempt_id=replacement, authorized_by='explicit controlled recovery',
            valid_from_utc='2026-11-09T16:00:00Z', expires_at_utc='2026-11-09T18:00:00Z')

    def test_preserves_upstream_preview_unknown_exposure_and_replay(self):
        self.reject()
        source = ledger.BatchExecutionV2(self.registry, self.authorization)
        source_events = (source.journal_path / 'events.jsonl').read_bytes()
        before = {name: (self.directory / name).read_bytes()
                  for name in ('primary.json', 'verifier.json', 'release-preview.json')}
        auth, cp = self.prepare()
        self.assertEqual(auth['max_cost_microusd'], 960)  # 40 charged + 200 unknown retained.
        self.assertEqual(auth['max_calls'], 1)  # Narrower than remaining three physical calls.
        self.assertEqual(cp['carried_physical_calls'], 3)
        self.assertEqual(cp['retained_unknown_microusd'], 200)
        path = recovery.claim_successor(self.registry, auth, cp)
        self.assertEqual(recovery.claim_successor(self.registry, auth, cp), path)
        options = dict(input_root=self.input_root, api_key='synthetic-secret',
            clock=lambda: fixtures.NOW, recovery_checkpoint=path,
            transport=self.transport_for(self.review_document(self.preview)))
        result = provider.run_batch_role(self.directory, self.registry, auth,
            'release_reviewer', 'replacement-release', **options)
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(len(self.calls), 3)  # two upstream + one replacement (rejection not counted by fixture).
        self.assertEqual(provider.run_batch_role(self.directory, self.registry, auth,
            'release_reviewer', 'replacement-release', **options), result)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(recovery.claim_successor(self.registry, auth, cp), path)
        self.assertEqual(before, {name: (self.directory / name).read_bytes() for name in before})
        self.assertEqual(source_events, (source.journal_path / 'events.jsonl').read_bytes())
        self.assertEqual(source.status()['requests']['rejected-release']['status'], 'unresolved')

    def test_single_claim_exact_role_attempt_and_no_budget_reset(self):
        self.reject()
        auth, cp = self.prepare()
        path = recovery.claim_successor(self.registry, auth, cp)
        other_auth, other_cp = self.prepare('second-release')
        with self.assertRaisesRegex(ValueError, 'already claimed'):
            recovery.claim_successor(self.registry, other_auth, other_cp)
        for key in ('max_cost_microusd', 'max_calls'):
            changed = copy.deepcopy(auth); changed[key] += 1
            with self.assertRaises(ValueError): recovery.claim_successor(self.registry, changed, cp)
        engine = recovery.ReleaseRecoveryExecution(self.registry, auth, path, clock=lambda: fixtures.NOW)
        for role, attempt, retry in [('primary', 'new-primary', None), ('verifier', 'new-verifier', None),
                ('release_reviewer', 'wrong-release', None), ('release_reviewer', 'replacement-release', 'rejected-release')]:
            with self.assertRaises(ValueError):
                engine.run(role, attempt, lambda _: self.fail('must not dispatch'), input_sha256='a'*64, retry_of=retry)

    def test_unsupported_http_failure_and_generation_are_not_recoverable(self):
        self.reject(status=503)
        with self.assertRaisesRegex(ValueError, 'HTTP 400'): self.prepare()

    def test_http400_with_generation_metadata_is_not_recoverable(self):
        self.reject(response={'id': 'generation-ambiguous', 'error': {'message': 'controlled'}})
        with self.assertRaisesRegex(ValueError, 'HTTP 400'): self.prepare()

    def test_checkpoint_upstream_and_preview_tampering_rejected(self):
        self.reject()
        auth, cp = self.prepare()
        path = recovery.claim_successor(self.registry, auth, cp)
        for field, value in [('replacement_attempt_id', 'changed'), ('retained_unknown_microusd', 0),
                             ('release_preview_sha256', '0'*64), ('upstream_submission_hashes', {}),
                             ('workflow_path', '/changed'), ('input_root', '/changed')]:
            changed = copy.deepcopy(cp); changed[field] = value
            path.write_text(json.dumps(changed))
            with self.assertRaises((ValueError, OSError)):
                recovery.ReleaseRecoveryExecution(self.registry, auth, path)
        path.write_text(json.dumps(cp))
        preview_path = self.directory / 'release-preview.json'
        preview = json.loads(preview_path.read_text()); preview['preview_sha256'] = '0'*64
        preview_path.write_text(json.dumps(preview))
        with self.assertRaises(ValueError): recovery.ReleaseRecoveryExecution(self.registry, auth, path)

    def test_self_consistent_replacement_preview_is_not_original_attempt(self):
        self.reject()
        from turbo.universe import batch_closure
        from turbo.pipeline_paths import ROOT
        stage = provider.workflow.verified_stage(self.directory, input_root=self.input_root)
        config = copy.deepcopy(stage['release_preview']['preview']['config'])
        config['recorded_at_utc'] = '2026-11-09T17:00:01Z'
        changed = batch_closure._compile(stage, config, root=ROOT, input_root=self.input_root)
        wrapper = copy.deepcopy(stage['release_preview'])
        wrapper['preview'] = changed
        wrapper['preview_sha256'] = provider._hash(changed)
        (self.directory / 'release-preview.json').write_text(json.dumps(wrapper))
        provider._replay_preview(self.directory, input_root=self.input_root)
        with self.assertRaisesRegex(ValueError, 'differ from rejected predecessor'):
            self.prepare()

    def test_missing_or_unsupported_predecessor_is_read_only(self):
        before = sorted(str(p.relative_to(self.registry)) for p in self.registry.rglob('*'))
        with self.assertRaises(ValueError): self.prepare()
        self.assertEqual(before, sorted(str(p.relative_to(self.registry)) for p in self.registry.rglob('*')))
        changed = copy.deepcopy(self.authorization)
        changed['execution_contract_hashes'] = {'unknown': '0'*64}
        with self.assertRaisesRegex(ValueError, 'unsupported predecessor'):
            recovery.prepare_successor(self.registry, changed, workflow_dir=self.directory,
                input_root=self.input_root, replacement_attempt_id='new', authorized_by='operator',
                valid_from_utc='2026-11-09T16:00:00Z', expires_at_utc='2026-11-09T18:00:00Z')

    def test_upstream_provider_artifact_mutation_rejected(self):
        self.reject()
        auth, cp = self.prepare()
        path = recovery.claim_successor(self.registry, auth, cp)
        source = ledger.BatchExecutionV2(self.registry, self.authorization)
        primary = source.status()['requests']['primary-1']
        artifact_path = source.journal_path / primary['response']['output']['artifact']
        artifact = json.loads(artifact_path.read_text()); artifact['document']['payload']['contract_version'] = 'tampered'
        artifact_path.write_text(json.dumps(artifact))
        with self.assertRaisesRegex(ValueError, 'artifact hash mismatch'):
            recovery.ReleaseRecoveryExecution(self.registry, auth, path)

    def test_legacy_ledger_and_http402_recovery_unchanged(self):
        from pathlib import Path
        from turbo.agents import batch_recovery
        self.assertEqual(hashlib.sha256(Path(ledger.__file__).read_bytes()).hexdigest(),
            '0a9c19bde71e5d55843581ca406e6b28ad5dad4e8c234c957dbf195b8804f56a')
        self.assertEqual(hashlib.sha256(Path(batch_recovery.__file__).read_bytes()).hexdigest(),
            'b66af6d6d1cc57f2c8d543c6f244f83c69a4167b0c1cc30ede5d7e6b7543ed2b')


if __name__ == '__main__': unittest.main()
