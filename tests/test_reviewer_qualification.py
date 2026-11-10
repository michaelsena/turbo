"""Synthetic transport proofs for the isolated four-cell qualification ledger."""
import copy
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from turbo.agents import reviewer_qualification as q, batch_execution_v2 as ledger, batch_provider as provider
from turbo.agents import readable_request_candidate as readable
from turbo.pipeline_paths import ROOT

NOW = '2026-11-10T12:00:00Z'


class ReviewerQualificationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(); self.bundle = self.base/'bundle'; self.bundle.mkdir()
        self.registry = self.base/'registry'; self.calls = []
        config = dict(model='google/gemini-4-argon', reasoning_effort='high', max_input_tokens=100000,
                      max_output_tokens=1000, timeout_seconds=30, allow_fallbacks=False,
                      input_microusd_per_token=3, output_microusd_per_token=20,
                      routing={'schema_version': 1, 'provider': {'only': ['google-vertex/global'], 'ignore': [], 'max_price': {'prompt': '2', 'completion': '10'}}})
        schema = provider.role_schema('release_reviewer', input_root=ROOT)
        files = {}; cells = {}
        def save(name, value):
            path = self.bundle/name; path.write_bytes(provider._bytes(value)); files[name] = q.file_sha(path)
        save('schema.json', schema); save('rubric.json', {'kind': q.KIND, 'version': 1, 'expected': 'External answer sentinel: NEVER_IN_REQUEST'})
        for cell, slot in q.CELLS.items():
            fixture, form = cell.split('-')
            assignment = {'role': 'release_reviewer', 'context': {'families': [{'evidence_catalog': [{'evidence_id': 'evidence:'+'a'*64}]}]},
                'inputs': {'primary': {'submission_sha256': '1'*64}, 'verifier': {'submission_sha256': '2'*64}},
                'release_preview': {'preview_sha256': ('3' if fixture=='positive' else '4')*64},
                'claim': 'extract sand' if fixture=='positive' else 'construct drainage'}
            task = {'assignment': assignment, 'prompt': 'Review the exact fixture.' + ('\n# Reviewer readable references\n'+readable.INSTRUCTIONS if form=='references' else '')}
            wire, _ = q.request_for(task, form, config, schema, cell=cell)
            save(cell+'-task.json', task); save(cell+'-request.json', wire)
            cells[cell] = {'ledger_slot': slot, 'task': cell+'-task.json', 'request': cell+'-request.json'}
        self.manifest = {'kind': q.KIND, 'cells': cells, 'files': files, 'schema': 'schema.json', 'rubric': 'rubric.json',
                         'config': config, 'source': {'origin': 'synthetic test only'}, 'code': q.contracts()}
        self.save_manifest()
        report = q.preflight(self.bundle, registry=self.registry)
        self.auth = ledger.build_authorization(workflow_plan_sha256=report['packet_sha256'],
            roles=report['required_role_bindings'], execution_contract_hashes=report['required_execution_contract_hashes'],
            authorized_by='synthetic test only', valid_from_utc='2026-11-10T11:00:00Z', expires_at_utc='2026-11-10T13:00:00Z',
            max_calls=4, max_cost_microusd=report['aggregate_reservation_microusd'])

    def save_manifest(self): (self.bundle/'manifest.json').write_bytes(provider._bytes(self.manifest))

    def transport(self, *, fault=None, unknown=False):
        def call(url, headers, body, timeout):
            wire = json.loads(body); self.calls.append(wire)
            text = wire['messages'][0]['content']; self.assertNotIn('NEVER_IN_REQUEST', text)
            task = json.loads(text.split('\n# Frozen assignment\n')[1])
            if 'format' in task: task = readable.decode(task)
            checks = {key: 'pass' for key in provider.role_schema('release_reviewer', input_root=ROOT)['properties']['checks']['required']}
            document = {'input_hashes': {r: x['submission_sha256'] for r, x in task['inputs'].items()},
                        'approved_plan_sha256': task['release_preview']['preview_sha256'], 'verdict': 'approve', 'findings': [], 'checks': checks}
            if fault == 'preview': document['approved_plan_sha256'] = '0'*64
            if fault == 'evidence':
                document['findings'] = [{'finding_id': 'x', 'status': 'resolved', 'rationale': 'evidence:'+'f'*64}]
            if fault == 'schema': document['extra'] = True
            response = {'id': 'synthetic', 'model': self.manifest['config']['model'], 'provider': 'Google',
                        'choices': [{'message': {'content': json.dumps(document)}}]}
            if not unknown: response['usage'] = {'prompt_tokens': 10, 'completion_tokens': 10, 'cost': 0.0001}
            return 200, {}, json.dumps(response).encode()
        return call

    def run_cell(self, cell, **kwargs):
        return q.run_cell(self.bundle, self.auth, self.registry, cell, execute=True, api_key='synthetic-never-used',
                          transport=self.transport(**kwargs), clock=lambda: NOW)

    def test_default_and_missing_authority_never_write_or_call(self):
        report = q.run_cell(self.bundle, self.auth, self.registry, 'positive-plain')
        self.assertFalse(report['execution_performed']); self.assertFalse(self.registry.exists())
        with self.assertRaises(ValueError): q.run_cell(self.bundle, None, self.registry, 'positive-plain', execute=True)
        self.assertFalse(self.registry.exists()); self.assertEqual(self.calls, [])

    def test_four_cells_settle_independently_replay_without_new_calls(self):
        for cell, slot in q.CELLS.items():
            result = self.run_cell(cell); self.assertEqual(result['attempt']['status'], 'succeeded')
            self.assertEqual(result['ledger_slot'], slot)
        self.assertEqual(len(self.calls), 4)
        for cell in q.CELLS: self.run_cell(cell)
        self.assertEqual(len(self.calls), 4)
        result = q.comparison(self.bundle, self.auth, self.registry)
        self.assertEqual(result['calls_reserved'], 4); self.assertEqual(result['outstanding_microusd'], 0)
        self.assertTrue(result['independent_semantic_assessment_required']); self.assertFalse(result['production_enablement'])
        with self.assertRaises(ValueError): self.run_cell('adjudicator')
        for cell, wire in zip(q.CELLS, self.calls):
            expected = q.read(self.bundle/(cell+'-request.json')); self.assertEqual(wire, expected)

    def test_unknown_usage_keeps_exposure_and_blocks_other_cells(self):
        result = self.run_cell('positive-plain', unknown=True)
        self.assertEqual(result['attempt']['status'], 'unresolved')
        self.run_cell('positive-plain')
        with self.assertRaisesRegex(ValueError, 'outstanding'): self.run_cell('positive-references')
        self.assertEqual(len(self.calls), 1)
        report = q.comparison(self.bundle, self.auth, self.registry)
        self.assertEqual(report['outstanding_microusd'], q.preflight(self.bundle)['reservation_per_cell_microusd'])

    def test_invalid_schema_preview_and_evidence_are_charged_failures(self):
        for cell, fault in zip(q.CELLS, ('schema', 'preview', 'evidence')):
            result = self.run_cell(cell, fault=fault)
            self.assertEqual(result['attempt']['status'], 'failed')
            self.assertGreater(result['attempt']['charged_microusd'], 0)
        self.assertEqual(len(self.calls), 3)

    def test_mapping_policy_request_or_production_authority_substitution_refused(self):
        bad = copy.deepcopy(self.auth); bad['execution_contract_hashes'] = provider.execution_contract_hashes()
        with self.assertRaises(ValueError): q.run_cell(self.bundle, bad, self.registry, 'positive-plain', execute=True)
        bad = copy.deepcopy(self.auth); bad['max_calls'] = 5
        with self.assertRaises(ValueError): q.preflight(self.bundle, bad, registry=self.registry)
        self.manifest['cells']['positive-plain']['ledger_slot'] = 'release_reviewer'; self.save_manifest()
        with self.assertRaises(ValueError): q.preflight(self.bundle, self.auth, registry=self.registry)
        self.manifest['cells']['positive-plain']['ledger_slot'] = 'primary'; self.save_manifest()
        (self.bundle/'positive-plain-request.json').write_text('{}')
        with self.assertRaises(ValueError): q.preflight(self.bundle, self.auth, registry=self.registry)
        self.assertFalse(self.registry.exists())

    def test_rubric_and_code_changes_are_refused_before_registry_creation(self):
        original = copy.deepcopy(self.manifest)
        self.manifest['code'][q.CONTRACT_KEY] = '0'*64; self.save_manifest()
        with self.assertRaises(ValueError): q.preflight(self.bundle, self.auth, registry=self.registry)
        self.manifest = original; self.save_manifest()
        (self.bundle/'rubric.json').write_text('{}')
        with self.assertRaises(ValueError): q.preflight(self.bundle, self.auth, registry=self.registry)
        self.assertFalse(self.registry.exists())

    def test_foreign_registry_and_changed_response_artifact_fail_closed(self):
        ledger.initialize_registry(self.registry)
        with self.assertRaisesRegex(ValueError, 'owned'):
            q.preflight(self.bundle, self.auth, registry=self.registry)
        ledger._write(self.registry/'qualification.json', {'kind': q.KIND, 'packet_sha256': q.sha(self.manifest), 'authorization_sha256': ledger._hash(self.auth)})
        self.run_cell('positive-plain')
        path = self.registry/'journals'/ledger._hash(self.auth)/'positive-plain-response.json'
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            q.comparison(self.bundle, self.auth, self.registry)

    def test_authority_cannot_fork_into_another_registry(self):
        other = self.base/'other-registry'
        with self.assertRaisesRegex(ValueError, 'authority does not bind'):
            q.run_cell(self.bundle, self.auth, other, 'positive-plain', execute=True,
                       api_key='synthetic-never-used', transport=self.transport(), clock=lambda: NOW)
        self.assertFalse(other.exists()); self.assertEqual(self.calls, [])

    def test_self_consistent_forged_attempt_or_body_cannot_masquerade_in_report(self):
        self.run_cell('positive-plain')
        journal = self.registry/'journals'/ledger._hash(self.auth)
        event_path = journal/'events.jsonl'; original_events = event_path.read_bytes()
        artifact_path = journal/'positive-plain-response.json'; original_artifact = artifact_path.read_bytes()
        def rewrite(events):
            previous = ledger.ZERO
            for event in events:
                event['previous_sha256'] = previous
                event['event_sha256'] = ledger._hash({k: v for k, v in event.items() if k != 'event_sha256'})
                previous = event['event_sha256']
            event_path.write_bytes(b''.join(provider._bytes(event)+b'\n' for event in events))
        events = [json.loads(line) for line in original_events.splitlines()]
        events[1]['data']['input_sha256'] = '9'*64; rewrite(events)
        with self.assertRaisesRegex(ValueError, 'attempt binding'):
            q.comparison(self.bundle, self.auth, self.registry)
        with self.assertRaisesRegex(ValueError, 'attempt binding'): self.run_cell('positive-plain')
        event_path.write_bytes(original_events)
        artifact = json.loads(original_artifact)
        wrong = copy.deepcopy(artifact['document']); wrong['approved_plan_sha256'] = '0'*64
        body = provider._bytes(wrong)
        artifact['body_base64'] = base64.b64encode(body).decode()
        artifact['provider']['body_sha256'] = hashlib.sha256(body).hexdigest()
        artifact_path.write_bytes(provider._bytes(artifact))
        events = [json.loads(line) for line in original_events.splitlines()]
        events[-1]['data']['response']['output']['artifact_sha256'] = q.file_sha(artifact_path)
        rewrite(events)
        with self.assertRaisesRegex(ValueError, 'document or classification'):
            q.comparison(self.bundle, self.auth, self.registry)
        self.assertEqual(len(self.calls), 1)

    def test_dispatched_crash_boundary_never_redispatches(self):
        ledger.initialize_registry(self.registry)
        ledger._write(self.registry/'qualification.json', {'kind': q.KIND, 'packet_sha256': q.sha(self.manifest), 'authorization_sha256': ledger._hash(self.auth)})
        engine = ledger.BatchExecutionV2(self.registry, self.auth, clock=lambda: NOW)
        wire = q.read(self.bundle/'positive-plain-request.json')
        with ledger._lock(engine.journal_path/'.lock'):
            events = engine._events()
            engine._append(events, 'reserved', {'attempt_id': 'qualification:positive-plain', 'role': 'primary',
                'input_sha256': q.sha(wire), 'retry_of': None, 'reserved_microusd': ledger._reservation(self.auth, 'primary')})
            engine._append(events, 'dispatched', {'attempt_id': 'qualification:positive-plain'})
        self.assertEqual(self.run_cell('positive-plain')['attempt']['status'], 'dispatched')
        self.assertEqual(self.calls, [])


if __name__ == '__main__': unittest.main()
