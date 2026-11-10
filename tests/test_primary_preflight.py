import copy
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest

from turbo.agents.openrouter_attempt import bounded_request_body
from turbo.agents.primary_preflight import assess_primary


SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'scripts/preflight-medium-primary.py'
SPEC = importlib.util.spec_from_file_location('medium_preflight_script', SCRIPT_PATH)
SCRIPT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCRIPT)


class PrimaryPreflightTest(unittest.TestCase):
    def setUp(self):
        self.config = dict(model='test/model', max_input_tokens=2000, max_output_tokens=100,
                           reasoning_effort='high', allow_fallbacks=False,
                           input_microusd_per_token=2, output_microusd_per_token=3,
                           routing={'schema_version': 1, 'provider': {'only': ['test'], 'ignore': [],
                                    'max_price': {'prompt': '1', 'completion': '2'}}})
        request = bounded_request_body(routing=self.config['routing'], role_id='primary', model='test/model',
            reasoning_effort='high', runtime_prompt_text='complete frozen evidence',
            schema={'type': 'object'}, invocation_id='invocation:' + '0' * 24,
            max_completion_tokens=100, allow_fallbacks=False, schema_name='turbo_workflow_role')
        self.capture = dict(role='primary', representation='plain', request=request, role_config=self.config,
                            bindings={'context_sha256': 'a' * 64}, subjects={'required_identities': 38})
        self.metadata = [dict(id='test/model', context_length=4000,
                              top_provider=dict(context_length=4000, max_completion_tokens=128))]

    def test_admission_context_output_are_independent(self):
        result = assess_primary(self.capture, self.metadata)
        self.assertFalse(result['admission']['fits_supplied_ceiling'])
        self.assertTrue(result['output']['fits_reported_maximum'])
        self.assertFalse(result['context']['fits_reported_context_by_conservative_bound'])
        self.assertFalse(result['context']['actual_context_overflow_established'])
        self.assertFalse(result['dispatch_authorized'])
        self.assertNotIn('private_reservation_arithmetic', result)

    def test_even_fitting_snapshots_do_not_create_authority_or_provenance(self):
        self.config['max_input_tokens'] = 10000
        self.metadata[0]['context_length'] = 12000
        self.metadata[0]['top_provider']['context_length'] = 12000
        result = assess_primary(self.capture, self.metadata, metadata_observed_at='2026-11-10T07:15:12Z')
        self.assertTrue(result['admission']['fits_supplied_ceiling'])
        self.assertTrue(result['context']['fits_reported_context_by_conservative_bound'])
        self.assertEqual(result['recommendation'], 'blocked')
        self.assertEqual(result['metadata']['provenance'], 'supplied_snapshot_unverified')
        self.assertIsNone(result['metadata']['retrieved_at'])
        self.assertIsNone(result['actual_usage']['input_tokens'])

    def test_missing_limits_are_unknown_and_output_failure_is_independent(self):
        self.metadata[0]['top_provider'] = {'max_completion_tokens': 99}
        result = assess_primary(self.capture, self.metadata)
        self.assertIsNone(result['context']['fits_reported_context_by_conservative_bound'])
        self.assertFalse(result['output']['fits_reported_maximum'])
        self.assertIsNone(result['tokenizer_estimate'])

    def test_bad_binding_or_metadata_is_rejected(self):
        for field, value in [('model', 'other'), ('max_completion_tokens', 99)]:
            capture = copy.deepcopy(self.capture)
            capture['request'][field] = value
            with self.assertRaisesRegex(ValueError, 'configuration'):
                assess_primary(capture, self.metadata)
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            assess_primary(self.capture, self.metadata * 2)
        self.metadata[0]['context_length'] = True
        with self.assertRaisesRegex(ValueError, 'positive integer'):
            assess_primary(self.capture, self.metadata)

    def test_reservation_must_cover_routing_price_caps(self):
        self.config['input_microusd_per_token'] = 0
        with self.assertRaisesRegex(ValueError, 'routing max_price'):
            assess_primary(self.capture, self.metadata, include_private_budget=True)

    def test_git_status_rejects_dirty_frozen_checkout(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            (root / 'plan.json').write_text(json.dumps({'input_tree': 'a' * 40}))
            answers = [str(root), 'a' * 40, ' M src/provider.py']
            results = [subprocess.CompletedProcess([], 0, stdout=value) for value in answers]
            with patch.object(SCRIPT.subprocess, 'run', side_effect=results):
                with self.assertRaisesRegex(ValueError, 'tracked or untracked changes'):
                    SCRIPT._verify_frozen_input(root, root)

    def test_dirty_frozen_input_stops_before_child_import(self):
        with patch.object(SCRIPT, '_verify_frozen_input', side_effect=ValueError('dirty checkout')):
            with patch.object(SCRIPT.subprocess, 'run') as child:
                with self.assertRaisesRegex(ValueError, 'dirty checkout'):
                    SCRIPT.capture_primary(Path('/tmp/input'), Path('/tmp/workflow'), Path('/tmp/roles'))
                child.assert_not_called()

    def test_private_ceiling_math_never_mutates_supplied_configuration(self):
        before = copy.deepcopy(self.capture)
        result = assess_primary(self.capture, self.metadata, include_private_budget=True)
        budget = result['private_reservation_arithmetic']
        self.assertEqual(budget['supplied_primary_reservation_microusd'], 4300)
        self.assertEqual(budget['minimum_admitting_primary_reservation_microusd'],
                         result['admission']['conservative_input_bound'] * 2 + 300)
        self.assertIsNone(budget['whole_workflow_reservation'])
        self.assertEqual(self.capture, before)
        self.assertEqual(result['staged_options']['one_call_diagnostic']['recommendation'],
                         'not_recommended_as_coverage_path')


if __name__ == '__main__':
    unittest.main()
