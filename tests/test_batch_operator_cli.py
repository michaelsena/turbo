"""Operator commands exercise the real managed harness with controlled HTTP only."""
import contextlib
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from turbo import cli
from turbo.agents import batch_provider, batch_workflow
from turbo.agents import batch_execution_v2 as execution
import test_batch_provider as provider_tests


class BatchOperatorCliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        provider_tests.BatchProviderTest.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        provider_tests.BatchProviderTest.setUp(self)
        self.auth_file = self.base / 'authorization.json'
        self.auth_file.write_text(json.dumps(self.authorization))

    payload = provider_tests.BatchProviderTest.payload
    transport_for = provider_tests.BatchProviderTest.transport_for
    verifier_document = provider_tests.BatchProviderTest.verifier_document
    review_document = provider_tests.BatchProviderTest.review_document
    compiled_preview = provider_tests.BatchProviderTest.compiled_preview
    ledger = provider_tests.BatchProviderTest.ledger

    def invoke(self, *args):
        output = io.StringIO()
        with patch('sys.argv', ['turbo', *map(str, args)]), contextlib.redirect_stdout(output):
            code = cli.main()
        return code, json.loads(output.getvalue())

    def role(self, name, document, **transport_options):
        def run(*args, **kwargs):
            return batch_provider.run_batch_role(*args, **kwargs,
                api_key='synthetic-cli-credential', clock=lambda: provider_tests.NOW,
                transport=self.transport_for(document, **transport_options))
        with patch.object(cli, 'run_batch_role', side_effect=run):
            return self.invoke('batch-provider-run', self.directory, self.registry, self.auth_file,
                               name, name + '-1', '--input-root', self.input_root,
                               '--preparation-dirs', *self.preparations)

    def files(self):
        return {str(p.relative_to(self.base)): p.read_bytes()
                for p in self.base.rglob('*') if p.is_file()}

    def test_status_never_creates_missing_registry_or_unclaimed_journal(self):
        before = self.files()
        for path in (self.base / 'absent', self.registry):
            code, result = self.invoke('batch-provider-status', path, self.auth_file)
            self.assertEqual(code, 1)
            self.assertFalse(result['model_invoked'])
            self.assertEqual(self.files(), before)
        self.assertFalse((self.base / 'absent').exists())
        self.assertEqual(list((self.registry / 'claims').iterdir()), [])

    def test_status_replays_existing_journal_without_constructor_or_writes(self):
        self.assertEqual(self.role('primary', {'payload': self.payload()})[0], 0)
        before = self.files()
        with patch.object(execution.BatchExecutionV2, '__init__', side_effect=AssertionError('constructor forbidden')):
            code, status = self.invoke('batch-provider-status', self.registry, self.auth_file)
        self.assertEqual(code, 0)
        self.assertEqual(status['calls_reserved'], 1)
        self.assertEqual(status['committed_microusd'], 20)
        self.assertFalse(status['model_invoked'])
        self.assertNotIn('response', status['requests']['primary-1'])
        self.assertEqual(self.files(), before)
        claim = next((self.registry / 'claims').glob('*.json'))
        claim.unlink()
        missing = self.files()
        self.assertEqual(self.invoke('batch-provider-status', self.registry, self.auth_file)[0], 1)
        self.assertEqual(self.files(), missing)

    def test_malformed_auth_is_bounded_redacted_and_has_no_side_effects(self):
        for content in ('{"secret":"do-not-echo","secret":true}', '{"unexpected":"do-not-echo"}'):
            self.auth_file.write_text(content)
            before = self.files()
            code, result = self.invoke('batch-provider-run', self.directory, self.registry,
                self.auth_file, 'primary', 'primary-1', '--input-root', self.input_root)
            self.assertEqual(code, 1)
            self.assertNotIn('do-not-echo', json.dumps(result))
            self.assertEqual(self.files(), before)
            self.assertEqual(self.calls, [])

    def test_cli_run_resume_preview_review_close_and_replay(self):
        document = {'payload': self.payload()}
        self.assertEqual(self.role('primary', document)[0], 0)
        self.assertEqual(self.role('primary', document)[0], 0)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.role('verifier', self.verifier_document())[0], 0)
        preview = self.compiled_preview()
        config_file = self.base / 'release-config.json'
        config_file.write_text(json.dumps(preview['preview']['config']))
        code, summary = self.invoke('batch-release-preview', self.directory, config_file,
            '--input-root', self.input_root, '--preparation-dirs', *self.preparations)
        self.assertEqual(code, 0)
        self.assertEqual(summary['preview_sha256'], preview['preview_sha256'])
        self.assertEqual(summary['movements_count'], 0)
        self.assertNotIn('projection', summary)
        self.assertEqual(self.role('release_reviewer', self.review_document(preview))[0], 0)
        self.assertEqual(len(self.calls), 3)
        code, closed = self.invoke('batch-close', self.directory, '--output-root', self.base / 'closures',
                                  '--input-root', self.input_root)
        self.assertEqual(code, 0, closed)
        self.assertIsNone(closed['graph_release'])
        before = self.files()
        code, result = self.invoke('batch-validate-closure', closed['closure_dir'], self.directory,
                                   '--input-root', self.input_root)
        self.assertEqual(code, 0, result)
        self.assertTrue(result['valid'])
        self.assertEqual(self.files(), before)
        self.assertEqual(self.invoke('batch-provider-status', self.registry, self.auth_file)[1]['committed_microusd'], 60)

    def test_unapproved_closure_and_partial_graph_binding_create_no_output(self):
        for extra in ([], ['--graph-release-dir', str(self.base / 'graph')]):
            before = self.files()
            code, result = self.invoke('batch-close', self.directory, '--output-root', self.base / 'closures',
                                      '--input-root', self.input_root, *extra)
            self.assertEqual(code, 1)
            self.assertFalse((self.base / 'closures').exists())
            self.assertEqual(self.files(), before)

    def test_registry_init_and_graph_relocation_forwarding(self):
        fresh = self.base / 'fresh-registry'
        code, metadata = self.invoke('batch-provider-registry-init', fresh)
        self.assertEqual(code, 0)
        self.assertFalse(metadata['model_invoked'])
        before = self.files()
        self.assertEqual(self.invoke('batch-provider-registry-init', fresh)[0], 1)
        self.assertEqual(self.files(), before)
        with patch.object(cli, 'run_graph_release', return_value={'valid': True}) as operation:
            self.assertEqual(self.invoke('graph-release', self.base / 'graph-config', '--input-root',
                self.input_root, '--preparation-dirs', *self.preparations)[0], 0)
        self.assertEqual(operation.call_args.kwargs['input_root'], self.input_root)
        self.assertEqual(operation.call_args.kwargs['preparation_dirs'], self.preparations)

    def test_unknown_usage_is_reported_unresolved_not_success_and_resume_never_calls(self):
        document = {'payload': self.payload()}
        code, result = self.role('primary', document, cost=None)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'unresolved')
        self.assertEqual(self.role('primary', document, cost=None)[0], 1)
        self.assertEqual(len(self.calls), 1)
        self.assertFalse((self.directory / 'primary.json').exists())

    def test_graph_errors_are_bounded_and_do_not_echo_source(self):
        for command, operation, args in (
            ('graph-release', 'run_graph_release', [self.base / 'config']),
            ('graph-validate-release', 'validate_graph_release', [self.base / 'release', self.base / 'config']),
        ):
            with patch.object(cli, operation, side_effect=ValueError('do-not-echo-provider-secret')):
                code, result = self.invoke(command, *args)
            self.assertEqual(code, 1)
            self.assertEqual(result['errors'], ['batch_operator_failed'])
            self.assertNotIn('do-not-echo', json.dumps(result))
            with patch.object(cli, operation, return_value={'valid': False, 'errors': ['do-not-echo']}):
                code, result = self.invoke(command, *args)
            self.assertEqual(code, 1)
            self.assertEqual(result['errors'], ['artifact_validation_failed'])
