"""Literal upstream hash navigation never changes output acceptance."""
import copy
import json
import unittest

from turbo.agents import batch_provider as provider, batch_workflow as workflow, model_view
from turbo.pipeline_paths import ROOT


class AssignmentNavigationHashesTest(unittest.TestCase):
    def task(self, role='verifier', inputs=None):
        return {'role': role, 'plan_sha256': '9' * 64,
                'context': {'schema_version': 1, 'contract_version': 'batch-primary-v1',
                    'role_id': 'batch_primary', 'request_id': 'request:literal',
                    'invocation_id': 'invocation:' + 'a' * 24,
                    'context_sha256': 'b' * 64, 'output_schema_sha256': 'c' * 64,
                    'prompt_sha256': 'd' * 64, 'families': []},
                'inputs': inputs or {}}

    def test_dependent_role_maps_use_submission_not_plan_hashes_losslessly(self):
        for role, dependencies in [('verifier', ['primary']),
                ('adjudicator', ['primary', 'verifier', 'escalation_a', 'escalation_b']),
                ('release_reviewer', ['primary', 'verifier', 'escalation_a', 'escalation_b', 'adjudicator'])]:
            with self.subTest(role=role):
                inputs = {r: {'submission_sha256': str(i + 1) * 64,
                    'plan_sha256': '9' * 64, 'document': {'untouched': r}}
                    for i, r in enumerate(dependencies)}
                task = self.task(role, inputs)
                if role == 'release_reviewer':
                    task['release_preview'] = {'preview_sha256': 'e' * 64}
                before = copy.deepcopy(task)
                rendered = provider.render_assignment(task, input_root=ROOT, model_view=model_view.VERSION)
                literal, encoded = rendered.split('\n# Literal assignment navigation\n')[1].split('\n# Frozen assignment\n')
                expected = {r: e['submission_sha256'] for r, e in inputs.items()}
                self.assertEqual(json.loads(literal)['role_input_hashes'], expected)
                self.assertEqual(model_view.decode(json.loads(encoded)), before)
                self.assertEqual(task, before)
                self.assertNotIn('9' * 64, json.dumps(expected))

    def test_blind_roles_have_no_upstream_hashes(self):
        for role in ('primary', 'escalation_a', 'escalation_b'):
            task = self.task(role)
            self.assertEqual(provider.assignment_navigation(task)['role_input_hashes'], {})
            self.assertEqual(task['inputs'], {})

    def test_missing_submission_hash_is_not_replaced_with_plan_hash(self):
        task = self.task(inputs={'primary': {'plan_sha256': '9' * 64}})
        with self.assertRaises(KeyError):
            provider.assignment_navigation(task)

    def test_wrong_model_authored_hash_still_rejected_without_repair(self):
        plan = {'plan_sha256': '9' * 64, 'actors': {'verifier': 'actor:verifier'}}
        document = {'input_hashes': {'primary': plan['plan_sha256']}, 'assessments': []}
        envelope = {'role': 'verifier', 'actor_id': 'actor:verifier',
                    'role_invocation_id': workflow._invocation(plan, 'verifier'),
                    'plan_sha256': plan['plan_sha256'], 'document': document}
        envelope['submission_sha256'] = workflow._hash(envelope)
        before = copy.deepcopy(envelope)
        with self.assertRaisesRegex(ValueError, 'upstream submission hashes mismatch'):
            workflow._validate(envelope, 'verifier', plan, {},
                               {'primary': {'submission_sha256': '1' * 64}})
        self.assertEqual(envelope, before)


if __name__ == '__main__':
    unittest.main()
