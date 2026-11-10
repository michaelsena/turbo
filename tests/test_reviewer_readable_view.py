"""Controlled reviewer-only representation; transports are synthetic, never paid."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_batch_provider as fixtures
from turbo.agents import batch_provider as provider, batch_workflow, model_view
from turbo.agents import readable_request_candidate as readable
from turbo.agents.openrouter_attempt import bounded_request_body


class ReviewerReadableViewTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.BatchProviderTest.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.BatchProviderTest.tearDownClass.__func__)
    setUp = fixtures.BatchProviderTest.setUp
    payload = fixtures.BatchProviderTest.payload
    transport_for = fixtures.BatchProviderTest.transport_for
    run_role = fixtures.BatchProviderTest.run_role
    verifier_document = fixtures.BatchProviderTest.verifier_document
    compiled_preview = fixtures.BatchProviderTest.compiled_preview
    review_document = fixtures.BatchProviderTest.review_document

    def enable(self):
        self.authorization['execution_contract_hashes'] = provider.execution_contract_hashes(reviewer_view=readable.FORMAT)
        for role, bindings in provider.contract_bindings(input_root=self.input_root, reviewer_view=readable.FORMAT).items():
            self.authorization['roles'][role].update(bindings)

    def prepare(self):
        self.enable()
        self.assertEqual(self.run_role('primary', {'payload': self.payload()})['status'], 'succeeded')
        self.assertEqual(self.run_role('verifier', self.verifier_document())['status'], 'succeeded')
        return self.compiled_preview()

    def test_reviewer_bound_wire_roundtrip_canonical_submission_and_replay(self):
        preview = self.prepare()
        for wire in self.calls:
            content = wire['messages'][0]['content']
            self.assertNotIn(readable.INSTRUCTIONS, content)
            task = json.loads(content.split('\n# Frozen assignment\n', 1)[1])
            self.assertIn(task['role'], ('primary', 'verifier'))
            self.assertEqual(task['context'], self.context)
        task = batch_workflow.assignment(self.directory, 'release_reviewer', input_root=self.input_root)
        document = self.review_document(preview)
        bounds = []
        def capture(**kwargs):
            bound = bounded_request_body(**kwargs); bounds.append(bound); return bound
        with patch.object(provider, 'bounded_request_body', side_effect=capture):
            self.assertEqual(self.run_role('release_reviewer', document)['status'], 'succeeded')
        bound = bounds[0]; wire = self.calls[-1]
        self.assertEqual(len(provider._bytes(bound)), len(provider._bytes(wire)))
        bound['session_id'] = wire['session_id']; self.assertEqual(bound, wire)
        content = wire['messages'][0]['content']
        self.assertIn(readable.INSTRUCTIONS, content)
        self.assertEqual(readable.decode(json.loads(content.split('\n# Frozen assignment\n', 1)[1])), task)
        self.assertEqual(json.loads((self.directory / 'release_reviewer.json').read_text())['document'], document)
        self.assertEqual(self.run_role('release_reviewer', document)['status'], 'succeeded')
        self.assertEqual(len(self.calls), 3)

    def test_wrong_preview_still_charged_failed_and_never_published(self):
        document = self.review_document(self.prepare())
        document['approved_plan_sha256'] = '0' * 64
        result = self.run_role('release_reviewer', document)
        self.assertEqual(result['status'], 'failed')
        self.assertFalse((self.directory / 'release_reviewer.json').exists())
        self.assertEqual(provider.BatchExecutionV2(self.registry, self.authorization).status()['committed_microusd'], 60)
        self.assertEqual(len(self.calls), 3)

    def test_canonical_reject_remains_settled_and_blocks_closure(self):
        document = self.review_document(self.prepare(), verdict='reject')
        self.assertEqual(self.run_role('release_reviewer', document)['status'], 'succeeded')
        self.assertEqual(batch_workflow.inspect_workflow(self.directory)['status'], 'rejected')
        with self.assertRaises(ValueError): batch_workflow.closure_payload(self.directory)
        self.assertEqual(json.loads((self.directory / 'release_reviewer.json').read_text())['document'], document)

    def test_authority_policy_source_prompt_and_incompatible_modes_fail_closed(self):
        self.enable(); original = copy.deepcopy(self.authorization)
        cases = []
        for key in (readable.CONTRACT_KEY, readable.SOURCE_PATH):
            bad = copy.deepcopy(original); bad['execution_contract_hashes'][key] = '0' * 64; cases.append(bad)
        bad = copy.deepcopy(original); bad['roles']['release_reviewer']['prompt_sha256'] = '0' * 64; cases.append(bad)
        bad = copy.deepcopy(original); bad['execution_contract_hashes'][model_view.CONTRACT_KEY] = model_view.POLICY_SHA256; cases.append(bad)
        for bad in cases:
            self.authorization = bad
            with self.assertRaises(ValueError): self.run_role('primary', {'payload': self.payload()})
        self.authorization = original
        with self.assertRaisesRegex(ValueError, 'fresh workflow'):
            provider.run_batch_role(self.directory, self.registry, self.authorization, 'primary', 'primary-1',
                input_root=self.input_root, recovery_checkpoint=Path('/nonexistent-checkpoint'))
        self.assertEqual(self.calls, [])

    def test_reviewer_encoded_admission_cap_blocks_without_new_transport(self):
        preview = self.prepare()
        # New authority would ordinarily be built before execution. This mutation
        # is solely a pre-admission refusal test; no new registry claim is allowed.
        self.authorization['roles']['release_reviewer']['max_input_tokens'] = 100
        with self.assertRaisesRegex(ValueError, 'token bound'):
            self.run_role('release_reviewer', self.review_document(preview))
        self.assertEqual(len(self.calls), 2)

    def test_plain_defaults_and_other_role_bindings_unchanged(self):
        plain = provider.contract_bindings(input_root=self.input_root)
        enabled = provider.contract_bindings(input_root=self.input_root, reviewer_view=readable.FORMAT)
        self.assertEqual(plain, provider.contract_bindings(input_root=self.input_root, reviewer_view=None))
        for role in batch_workflow.ROLES:
            self.assertEqual(plain[role]['schema_sha256'], enabled[role]['schema_sha256'])
            if role != 'release_reviewer': self.assertEqual(plain[role], enabled[role])
        self.assertNotEqual(plain['release_reviewer']['prompt_sha256'], enabled['release_reviewer']['prompt_sha256'])
        self.assertNotIn(readable.CONTRACT_KEY, provider.execution_contract_hashes())
        self.assertNotIn(readable.INSTRUCTIONS, provider.role_prompt(input_root=self.input_root))
        for options in ({'reviewer_view': 'unknown'}, {'reviewer_view': readable.FORMAT, 'model_view': model_view.VERSION}):
            with self.assertRaises(ValueError): provider.execution_contract_hashes(**options)
            with self.assertRaises(ValueError): provider.contract_bindings(input_root=self.input_root, **options)


if __name__ == '__main__': unittest.main()
