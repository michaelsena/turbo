"""Fresh cohort planning uses real child admission and synthetic eligibility only."""
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from turbo.agents import evaluation_cohort as cohort, evaluation_execution as runtime
from turbo.agents import batch_execution_v2 as ledger
import test_evaluation_execution as fixtures


class CohortTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ExecutionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        source = self.fixture.evaluation()
        self.base = self.fixture.base
        original = runtime.load_plan(source)
        catalog = runtime._read(runtime.ROOT / cohort.CATALOG)
        self.manifest = {'schema_version': 1, 'kind': cohort.KIND,
            'calibration_manifest_sha256': runtime.packaging._file_sha(runtime.ROOT / cohort.CATALOG),
            'max_cost_microusd': 18000000, 'units': []}
        for index, item in enumerate(catalog['submodel_artifacts']):
            directory = self.base / ('fresh-' + str(index)); directory.mkdir()
            plan = copy.deepcopy(original)
            for name in plan['files']:
                (directory / name).write_bytes((source / name).read_bytes())
            factor = (runtime.ROOT / item['path']).read_bytes()
            (directory / plan['factors']).write_bytes(factor)
            plan['files'][plan['factors']] = item['sha256']
            plan['submodel_version_id'] = item['submodel_version_id']
            plan['registry_path'] = str(self.base / ('fresh-registry-' + str(index)))
            for task, spec in plan['tasks'].items():
                spec['config'].update(catalog['task_model_policy']['tasks'][task])
            self.write_plan(directory, plan)
            authority = self.authority(directory, plan)
            auth_path = self.base / ('authority-' + str(index) + '.json')
            auth_path.write_bytes(runtime._bytes(authority))
            self.manifest['units'].append({'submodel_version_id': plan['submodel_version_id'],
                'work_unit_dir': str(directory), 'plan_sha256': runtime._sha(plan),
                'authority_path': str(auth_path), 'authority_sha256': ledger._hash(authority)})

    def write_plan(self, directory, plan):
        (directory / 'plan.json').write_bytes(runtime._bytes(plan))

    def authority(self, directory, plan):
        return ledger.build_authorization(workflow_plan_sha256=runtime._sha(plan),
            roles=runtime.role_bindings(directory, plan), authorized_by='synthetic fixture only',
            valid_from_utc='2026-11-10T00:00:00Z', expires_at_utc='2026-11-11T00:00:00Z',
            max_calls=4, max_cost_microusd=3000000, execution_contract_hashes=runtime.authority_contracts(plan))

    def change(self, key, value):
        item = self.manifest['units'][0]; directory = Path(item['work_unit_dir'])
        plan = runtime._read(directory / 'plan.json'); plan[key] = value
        self.write_plan(directory, plan); item['plan_sha256'] = runtime._sha(plan)
        auth = self.authority(directory, plan)
        Path(item['authority_path']).write_bytes(runtime._bytes(auth)); item['authority_sha256'] = ledger._hash(auth)

    def test_valid_exact_six_is_read_only_and_not_authority(self):
        before = {str(p): p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        with patch.object(runtime, 'initialize', side_effect=AssertionError('write')), patch.object(runtime, 'run_task', side_effect=AssertionError('dispatch')):
            result = cohort.preflight(self.manifest)
        after = {str(p): p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(result['allocated_microusd'], 18000000)
        self.assertEqual(result['maximum_calls'], 24)
        self.assertFalse(result['execution_enabled']); self.assertFalse(result['global_ranking'])

    def test_budget_types_and_overallocation_rejected(self):
        for cap in (True, -1, 1.5, 17999999):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                cohort.preflight(dict(self.manifest, max_cost_microusd=cap))

    def test_missing_duplicate_submodel_and_authority_rejected(self):
        missing = copy.deepcopy(self.manifest); missing['units'].pop()
        duplicate = copy.deepcopy(self.manifest); duplicate['units'][1] = duplicate['units'][0]
        auth = copy.deepcopy(self.manifest)
        for k in ('authority_path', 'authority_sha256'): auth['units'][1][k] = auth['units'][0][k]
        for value in (missing, duplicate, auth):
            with self.subTest(value=value['units'][-1]['submodel_version_id']), self.assertRaises(ValueError):
                cohort.preflight(value)

    def test_empty_initialized_registry_allowed_prior_exposure_rejected(self):
        directory = Path(self.manifest['units'][0]['work_unit_dir'])
        registry = Path(runtime.load_plan(directory)['registry_path']); ledger.initialize_registry(registry)
        cohort.preflight(self.manifest)
        for folder in ('claims', 'journals'):
            marker = registry / folder / 'prior'; marker.write_text('prior unresolved or settled exposure')
            with self.assertRaisesRegex(ValueError, 'prior claims or journal'): cohort.preflight(self.manifest)
            marker.unlink()
        (directory / 'execution-owner.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'initialized child'): cohort.preflight(self.manifest)

    def test_source_mutation_and_alias_rejected(self):
        directory = Path(self.manifest['units'][0]['work_unit_dir'])
        (directory / 'source.txt').write_text('mutated')
        with self.assertRaisesRegex(ValueError, 'frozen artifact changed'): cohort.preflight(self.manifest)
        link = self.base / 'alias'; link.symlink_to(directory, target_is_directory=True)
        self.manifest['units'][0]['work_unit_dir'] = str(link)
        with self.assertRaisesRegex(ValueError, 'resolved absolute'): cohort.preflight(self.manifest)

    def test_rebound_scope_or_model_change_rejected(self):
        self.change('evidence_cutoff', '2026-11-10T13:00:00Z')
        with self.assertRaises(ValueError): cohort.preflight(self.manifest)
        self.change('evidence_cutoff', '2026-11-10T12:00:00Z')
        directory = Path(self.manifest['units'][0]['work_unit_dir'])
        tasks = runtime.load_plan(directory)['tasks']; tasks['evaluator_a']['config']['model'] = 'test/wrong'
        self.change('tasks', tasks)
        with self.assertRaisesRegex(ValueError, 'factor model policy'): cohort.preflight(self.manifest)

    def test_forged_eligibility_rejected_even_when_rehashed(self):
        item = self.manifest['units'][0]; directory = Path(item['work_unit_dir']); plan = runtime.load_plan(directory)
        path = directory / plan['eligibility']; path.write_bytes(runtime._bytes({'eligible': True}))
        plan['files'][plan['eligibility']] = runtime.packaging._file_sha(path)
        self.change('files', plan['files'])
        with self.assertRaisesRegex(ValueError, 'exact eligibility provider descriptor'): cohort.preflight(self.manifest)

    def test_cli_malformed_top_level_fails_without_traceback(self):
        for value in (None, [], 1, 'x', {}):
            path = self.base / 'bad-cohort.json'; path.write_text(json.dumps(value))
            process = subprocess.run([sys.executable, '-m', 'turbo.agents.evaluation_cohort', str(path)],
                capture_output=True, text=True, env={**os.environ, 'PYTHONPATH': str(runtime.ROOT / 'src')})
            self.assertEqual(process.returncode, 2)
            self.assertFalse(json.loads(process.stdout)['execution_enabled'])
            self.assertEqual(process.stderr, '')

    def test_nonoverlapping_authority_intervals_and_duplicate_registry_rejected(self):
        item = self.manifest['units'][0]; path = Path(item['authority_path']); auth = runtime._read(path)
        auth['valid_from_utc'] = '2026-11-12T00:00:00Z'
        auth['expires_at_utc'] = '2026-11-13T00:00:00Z'
        path.write_bytes(runtime._bytes(auth)); item['authority_sha256'] = ledger._hash(auth)
        with self.assertRaisesRegex(ValueError, 'validity windows'): cohort.preflight(self.manifest)
        other = runtime.load_plan(Path(self.manifest['units'][1]['work_unit_dir']))
        self.change('registry_path', other['registry_path'])
        with self.assertRaisesRegex(ValueError, 'duplicate cohort registry'): cohort.preflight(self.manifest)

    def test_stale_contracts_and_rebound_factor_rejected(self):
        directory = Path(self.manifest['units'][0]['work_unit_dir']); plan = runtime.load_plan(directory)
        self.change('code', {})
        with self.assertRaisesRegex(ValueError, 'execution contract changed'): cohort.preflight(self.manifest)
        self.change('code', plan['code'])
        factor = runtime._artifact(directory, plan, 'factors'); factor['factors'][0]['weight'] = 2
        (directory / plan['factors']).write_bytes(runtime._bytes(factor))
        plan['files'][plan['factors']] = runtime.packaging._file_sha(directory / plan['factors'])
        self.change('files', plan['files'])
        with self.assertRaisesRegex(ValueError, 'registered factor bytes'): cohort.preflight(self.manifest)


if __name__ == '__main__': unittest.main()
