"""Issue #101: bound reviewer replacement, synthetic HTTP only.

Only the historical checkout identity/subprocess boundary is substituted. The
fixture proof replays real provider artifacts, citation traces and compiler output.
The separate pin test exercises the production checkout identity guard directly.
"""
import base64
import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_batch_provider as fixtures
from turbo.agents import batch_provider as provider, batch_release_recovery as recovery
from turbo.agents import batch_execution_v2 as ledger
from turbo.pipeline_paths import ROOT


class BoundReleaseSuccessorTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.BatchProviderTest.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.BatchProviderTest.tearDownClass.__func__)
    transport_for = fixtures.BatchProviderTest.transport_for
    run_role = fixtures.BatchProviderTest.run_role
    verifier_document = fixtures.BatchProviderTest.verifier_document
    compiled_preview = fixtures.BatchProviderTest.compiled_preview
    review_document = fixtures.BatchProviderTest.review_document

    def setUp(self):
        fixtures.BatchProviderTest.setUp(self)
        contracts = provider.execution_contract_hashes(model_view=provider.view.VERSION, citation_sets=True)
        self.authorization['execution_contract_hashes'] = contracts
        for role, binding in provider.contract_bindings(input_root=self.input_root,
                model_view=provider.view.VERSION, citation_sets=True).items():
            self.authorization['roles'][role].update(binding)
        self.replacement = {**self.authorization['roles']['release_reviewer'],
                            'model': 'openai/gpt-5.6-luna'}
        for name, value in (('_source_contracts', lambda _: copy.deepcopy(contracts)),
                            ('_frozen_proof', self.fixture_proof)):
            mock = patch.object(recovery, name, side_effect=value)
            mock.start(); self.addCleanup(mock.stop)

    def payload(self):
        value = fixtures.BatchProviderTest.payload(self)
        for family in value['families']:
            for row in family['identity_dispositions']:
                row['supporting_evidence_ids'] += row['supporting_evidence_ids'][:1]
        return value

    def fixture_proof(self, source_runtime, registry, authorization, directory, input_root, preparations):
        directory, input_root = Path(directory), Path(input_root)
        source = ledger.BatchExecutionV2(registry, authorization)
        previous = provider._snapshot(directory, input_root=input_root, preparation_dirs=preparations)
        hashes = provider._verify_upstream(source, 'release_reviewer', previous, authorization, input_root=input_root)
        provider._replay_preview(directory, input_root=input_root, preparation_dirs=preparations)
        task = provider.workflow.assignment(directory, 'release_reviewer', input_root=input_root,
                                            preparation_dirs=preparations)
        runtime = provider.render_assignment(task, input_root=input_root,
                                            model_view=provider.view.VERSION, citation_sets=True)
        return dict(source_commit=recovery.PINNED_SOURCE_COMMIT, source_tree=recovery.PINNED_SOURCE_TREE,
            contracts=authorization['execution_contract_hashes'],
            input_sha256=provider._hash(dict(assignment=task, runtime_prompt=runtime,
                schema=provider.role_schema('release_reviewer', input_root=input_root, citation_sets=True),
                upstream_submission_hashes=hashes)), upstream_submission_hashes=hashes,
            release_preview_sha256=ledger._hash(ledger._read(directory / 'release-preview.json')),
            source_events_sha256=hashlib.sha256((source.journal_path / 'events.jsonl').read_bytes()).hexdigest())

    def reject(self):
        self.assertEqual(self.run_role('primary', {'payload': self.payload()})['status'], 'succeeded')
        self.assertEqual(self.run_role('verifier', self.verifier_document())['status'], 'succeeded')
        self.preview = self.compiled_preview()
        result = provider.run_batch_role(self.directory, self.registry, self.authorization,
            'release_reviewer', 'rejected-release', input_root=self.input_root,
            api_key='synthetic-only', clock=lambda: fixtures.NOW,
            transport=lambda *args: (400, {}, b'{"error":{"message":"controlled context limit"}}'))
        self.assertEqual(result['status'], 'unresolved')

    def prepare(self, replacement='replacement-release'):
        return recovery.prepare_bound_successor(self.registry, self.authorization,
            source_runtime=ROOT, replacement_reviewer=self.replacement,
            workflow_dir=self.directory, input_root=self.input_root,
            replacement_attempt_id=replacement, authorized_by='controlled explicit successor',
            valid_from_utc='2026-11-09T16:00:00Z', expires_at_utc='2026-11-09T18:00:00Z')

    def primary_artifact(self):
        source = ledger.BatchExecutionV2(self.registry, self.authorization)
        row = source.status()['requests']['primary-1']
        path = source.journal_path / row['response']['output']['artifact']
        return path, json.loads(path.read_text())

    def test_bound_review_closes_without_resetting_original_journal(self):
        from turbo.universe.batch_closure import finalize_batch_closure, validate_batch_closure
        self.reject()
        source = ledger.BatchExecutionV2(self.registry, self.authorization)
        before = (source.journal_path / 'events.jsonl').read_bytes()
        upstream = {name: (self.directory / name).read_bytes()
                    for name in ('primary.json', 'verifier.json', 'release-preview.json')}
        _, artifact = self.primary_artifact()
        self.assertTrue(artifact['citation_normalization']['changes'])
        auth, checkpoint = self.prepare()
        self.assertEqual(checkpoint['kind'], recovery.BOUND_KIND)
        self.assertEqual((checkpoint['carried_physical_calls'], checkpoint['carried_paid_microusd'],
                          checkpoint['retained_unknown_microusd']), (3, 40, 200))
        self.assertEqual((auth['max_calls'], auth['max_cost_microusd']), (1, 960))
        path = recovery.claim_successor(self.registry, auth, checkpoint)
        options = dict(input_root=self.input_root, api_key='synthetic-only', clock=lambda: fixtures.NOW,
            recovery_checkpoint=path, transport=self.transport_for(self.review_document(self.preview)))
        result = provider.run_batch_role(self.directory, self.registry, auth,
            'release_reviewer', 'replacement-release', **options)
        self.assertEqual(result['status'], 'succeeded', result)
        self.assertEqual(self.calls[-1]['model'], 'openai/gpt-5.6-luna')
        self.assertEqual(provider.run_batch_role(self.directory, self.registry, auth,
            'release_reviewer', 'replacement-release', **options), result)
        self.assertEqual(len(self.calls), 3)
        proof = recovery.verify_bound_release_approval(self.registry, auth, path)
        self.assertFalse(proof['canonical_published'])
        self.assertEqual(proof, recovery.verify_bound_release_approval(self.registry, auth, path))
        from turbo.agents import batch_controller as controller
        manifest = dict(controller_dir=str(self.base / 'old-controller'), registry_dir=str(self.registry),
            authorization_sha256=ledger._hash(self.authorization), authorization=self.authorization,
            root=str(self.input_root), base_pointer_sha256=controller._base(self.input_root),
            attempt_ids={'primary': 'primary-1', 'verifier': 'verifier-1', 'release_reviewer': 'rejected-release'})
        stopped = controller._state(manifest, clock=lambda: fixtures.NOW)
        self.assertEqual((stopped['state'], stopped['reason']), ('STOPPED', 'attempt_unresolved'))
        closure = finalize_batch_closure(self.directory, output_root=self.base / 'closures', root=ROOT)
        self.assertTrue(validate_batch_closure(Path(closure['closure_dir']), self.directory, root=ROOT)['valid'])
        self.assertEqual(before, (source.journal_path / 'events.jsonl').read_bytes())
        self.assertEqual(upstream, {name: (self.directory / name).read_bytes() for name in upstream})
        self.assertEqual(source.status()['requests']['rejected-release']['status'], 'unresolved')
        self.assertEqual(source.status()['outstanding_microusd'], 200)

    def test_missing_predecessor_is_read_only(self):
        before = {str(p): p.read_bytes() for p in self.registry.rglob('*') if p.is_file()}
        with patch.object(recovery, '_frozen_proof') as proof:
            with self.assertRaises((ValueError, OSError)): self.prepare()
            proof.assert_not_called()
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.registry.rglob('*') if p.is_file()})

    def test_one_claim_one_role_and_no_budget_reset(self):
        self.reject()
        auth, cp = self.prepare()
        path = recovery.claim_successor(self.registry, auth, cp)
        other_auth, other_cp = self.prepare('other-release')
        with self.assertRaisesRegex(ValueError, 'already claimed'):
            recovery.claim_successor(self.registry, other_auth, other_cp)
        for key in ('max_calls', 'max_cost_microusd'):
            changed = copy.deepcopy(auth); changed[key] += 1
            with self.assertRaises(ValueError): recovery.claim_successor(self.registry, changed, cp)
        engine = recovery.ReleaseRecoveryExecution(self.registry, auth, path, clock=lambda: fixtures.NOW)
        for role, attempt, retry in [('primary', 'new-primary', None), ('verifier', 'new-verifier', None),
                ('release_reviewer', 'wrong', None), ('release_reviewer', 'replacement-release', 'rejected-release')]:
            with self.assertRaises(ValueError):
                engine.run(role, attempt, lambda _: self.fail('upstream must not redispatch'),
                           input_sha256='a'*64, retry_of=retry)
        self.assertEqual(len(self.calls), 2)

    def test_wrong_model_role_contract_or_reasoning_refused(self):
        self.reject()
        baseline = copy.deepcopy(self.replacement)
        for key, value in [('model', 'test/primary'), ('reasoning_effort', 'low'),
                           ('schema_sha256', '0'*64), ('prompt_sha256', '0'*64)]:
            self.replacement = {**baseline, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError): self.prepare()
        self.assertEqual(len(self.calls), 2)

    def test_reviewer_cannot_reuse_upstream_model(self):
        self.authorization['roles']['primary']['model'] = 'openai/gpt-5.6-luna'
        self.reject()
        with self.assertRaisesRegex(ValueError, 'independent'): self.prepare()
        self.assertEqual(len(self.calls), 2)

    def test_raw_trace_and_upstream_tampering_refused(self):
        self.reject()
        auth, cp = self.prepare(); path = recovery.claim_successor(self.registry, auth, cp)
        artifact_path, artifact = self.primary_artifact()
        original = artifact_path.read_bytes()
        for change in ('raw', 'trace', 'document'):
            changed = copy.deepcopy(artifact)
            if change == 'raw': changed['output_base64'] = base64.b64encode(b'{}').decode()
            elif change == 'trace': changed['citation_normalization']['changes'] = []
            else: changed['document']['payload']['contract_version'] = 'invented'
            self.assertFalse(provider.verify_artifact_document(changed, self.authorization, input_root=self.input_root))
            artifact_path.write_text(json.dumps(changed))
            with self.subTest(change=change), self.assertRaises(ValueError):
                recovery.ReleaseRecoveryExecution(self.registry, auth, path)
            artifact_path.write_bytes(original)

    def test_preview_and_bound_proof_tampering_refused(self):
        self.reject()
        auth, cp = self.prepare(); path = recovery.claim_successor(self.registry, auth, cp)
        changed = copy.deepcopy(cp); changed['frozen_source_proof']['source_tree'] = '0'*40
        path.write_text(json.dumps(changed))
        with self.assertRaises(ValueError): recovery.ReleaseRecoveryExecution(self.registry, auth, path)
        path.write_text(json.dumps(cp))
        preview_path = self.directory / 'release-preview.json'
        preview = ledger._read(preview_path); preview['preview_sha256'] = '0'*64
        preview_path.write_text(json.dumps(preview))
        with self.assertRaises(ValueError): recovery.ReleaseRecoveryExecution(self.registry, auth, path)


class FrozenSourcePinTest(unittest.TestCase):
    def test_current_or_modified_checkout_is_not_the_frozen_source(self):
        # No subprocess/proof mocking: production rejects this distinct checkout.
        with self.assertRaisesRegex(ValueError, 'exact clean pinned'):
            recovery._source_contracts(ROOT)


if __name__ == '__main__': unittest.main()
