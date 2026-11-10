"""Explicit synthetic mechanics only; no fixture confers live eligibility."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from turbo.agents import evaluation_workflow as workflow
from turbo.agents import batch_execution_v2 as ledger


class EvaluationWorkUnitTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        self.registry = self.directory / 'registry'
        self.plan = {'kind': workflow.KIND, 'submodel_version_id': 'synthetic-submodel:v1',
            'market_version_ids': ['market-version:synthetic-only'],
            'evidence_cutoff': '2026-11-10T12:00:00Z',
            'registry_path': str(self.registry), 'task_slots': dict(workflow.TASK_SLOTS),
            'tasks': {}, 'files': {}, 'code': workflow.contracts()}
        for key in ('graph', 'eligibility', 'strategy', 'factors', 'evidence'):
            name = key + '.json'; self.plan[key] = name
            self.save(name, {'origin': 'synthetic test only', 'status': 'passed'})
        for task in workflow.TASK_SLOTS:
            prompt = task + '-prompt.json'; schema = task + '-schema.json'
            self.save(prompt, {'text': 'Synthetic evaluation prompt.'})
            self.save(schema, {'type': 'object', 'additionalProperties': False,
                               'properties': {'score': {'type': 'number'}}, 'required': ['score']})
            self.plan['tasks'][task] = {'prompt': prompt, 'schema': schema, 'config': {
                'model': 'test/model', 'reasoning_effort': 'high',
                'max_output_tokens': 1000, 'max_input_tokens': 100000,
                'max_attempts': 1, 'allow_fallbacks': False, 'timeout_seconds': 30,
                'input_microusd_per_token': 1, 'output_microusd_per_token': 1}}
        self.persist()

    def save(self, name, value):
        path = self.directory / name; path.write_bytes(workflow._bytes(value))
        self.plan['files'][name] = workflow._file_sha(path)

    def persist(self):
        (self.directory / 'plan.json').write_bytes(workflow._bytes(self.plan))

    def authority(self):
        return ledger.build_authorization(workflow_plan_sha256=workflow._sha(self.plan),
            roles=workflow._role_bindings(self.directory, self.plan),
            authorized_by='synthetic test only', valid_from_utc='2026-11-10T11:00:00Z',
            expires_at_utc='2026-11-10T13:00:00Z', max_calls=4, max_cost_microusd=404000,
            execution_contract_hashes=dict(workflow.contracts(), **{
                'evaluation/registry-path': workflow._sha(str(self.registry)),
                'evaluation/task-slots': workflow._sha(workflow.TASK_SLOTS)}))

    def test_passed_json_never_grants_eligibility_or_creates_registry(self):
        report = workflow.preflight(self.directory, authority=self.authority())
        self.assertEqual(report['status'], workflow.BLOCKED)
        self.assertFalse(report['eligibility_provenance_validated'])
        self.assertFalse(report['graph_provenance_validated'])
        self.assertFalse(report['execution_enabled'])
        self.assertFalse(self.registry.exists())
        with self.assertRaisesRegex(ValueError, workflow.BLOCKED):
            workflow.run_task(self.directory, 'evaluator_a', authority=self.authority(), execute=True)
        self.assertFalse(self.registry.exists())
        self.plan['synthetic_bypass'] = True; self.persist()
        with self.assertRaises(ValueError): workflow.preflight(self.directory)

    def test_no_manual_pilot_identity_or_mapping_relabel(self):
        self.plan['market_version_ids'] = ['pilot-market:manual']; self.persist()
        with self.assertRaises(ValueError): workflow.preflight(self.directory)
        self.plan['market_version_ids'] = ['market-version:synthetic-only']
        self.plan['task_slots']['evaluator_b'] = 'primary'; self.persist()
        with self.assertRaises(ValueError): workflow.preflight(self.directory)
        for task in ('primary', 'escalation_a', 'escalation_b', 'generalist'):
            with self.assertRaises(ValueError): workflow.run_task(self.directory, task)

    def test_frozen_file_code_and_path_changes_refused(self):
        (self.directory / 'evidence.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'changed'): workflow.preflight(self.directory)
        self.save('evidence.json', {'origin': 'synthetic test only'}); self.persist()
        self.plan['code']['src/turbo/agents/evaluation_workflow.py'] = '0' * 64; self.persist()
        with self.assertRaisesRegex(ValueError, 'changed'): workflow.preflight(self.directory)
        with self.assertRaises(ValueError): workflow._path(self.directory, '../outside.json')
        (self.directory / 'alias.json').symlink_to(self.directory / 'graph.json')
        with self.assertRaisesRegex(ValueError, 'symlink'): workflow._path(self.directory, 'alias.json')

    def test_authority_exact_unit_and_stable_attempt_ids(self):
        auth = self.authority()
        owner = workflow._authority_bindings(self.directory, self.plan, auth)
        self.assertEqual(owner, workflow._authority_bindings(self.directory, self.plan, auth))
        self.assertEqual(len(set(owner['attempt_ids'].values())), 4)
        for field, value in [('max_calls', 24), ('workflow_plan_sha256', '0' * 64)]:
            bad = copy.deepcopy(auth); bad[field] = value
            with self.assertRaises(ValueError): workflow._authority_bindings(self.directory, self.plan, bad)
        bad = copy.deepcopy(auth); bad['roles']['verifier']['prompt_sha256'] = '0' * 64
        with self.assertRaises(ValueError): workflow._authority_bindings(self.directory, self.plan, bad)
        self.assertFalse(self.registry.exists())

    def test_blind_assignments_exclude_other_answers_and_have_distinct_invocations(self):
        upstream = {'evaluator_a': {'private_answer': 'NEVER_SHARE'}}
        a = workflow._assignment(self.plan, 'evaluator_a', verified_upstream=upstream)
        b = workflow._assignment(self.plan, 'evaluator_b', verified_upstream=upstream)
        self.assertEqual(a, b); self.assertNotIn('NEVER_SHARE', json.dumps(a))
        requests = [workflow._request(self.directory, self.plan, task, attempt_id=task,
                                     verified_upstream=upstream)
                    for task in ('evaluator_a', 'evaluator_b')]
        self.assertEqual(requests[0]['messages'], requests[1]['messages'])
        self.assertNotEqual(requests[0]['session_id'], requests[1]['session_id'])
        self.assertNotIn('NEVER_SHARE', json.dumps(requests))
        self.plan['tasks']['evaluator_a']['config']['max_input_tokens'] = 1
        with self.assertRaisesRegex(ValueError, 'input bound'):
            workflow._request(self.directory, self.plan, 'evaluator_a', attempt_id='a', verified_upstream={})

    def test_dependency_views_do_not_accept_generalist_or_partial_inputs(self):
        with self.assertRaises(ValueError):
            workflow._assignment(self.plan, 'adjudicator', verified_upstream={'evaluator_a': {}})
        with self.assertRaises(ValueError):
            workflow._assignment(self.plan, 'comparator', verified_upstream={'global_ranking': {}})
        value = workflow._assignment(self.plan, 'comparator', verified_upstream={'resolved_submodel': {}})
        self.assertEqual(set(value['upstream']), {'resolved_submodel'})

    def test_cli_blocked_exit_is_not_success(self):
        result = subprocess.run([sys.executable, str(workflow.ROOT / 'scripts/run-evaluation-work-unit.py'),
                                 '--input', str(self.directory)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['status'], workflow.BLOCKED)
        self.assertFalse(self.registry.exists())


if __name__ == '__main__': unittest.main()
