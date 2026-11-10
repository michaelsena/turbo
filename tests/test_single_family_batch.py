"""One complete scheduled family follows the existing managed chain, never a shortcut."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from turbo.agents import batch_authorization as auth, batch_output, batch_workflow as workflow
from turbo.agents import batch_execution_v2 as ledger, batch_controller as controller
from turbo.pipeline_paths import ROOT
from turbo.universe.family_pack_v2 import prepare_family_v2
from turbo.universe import batch_closure
import test_batch_controller as controlled
import test_batch_provider as provider_fixture
from test_batch_output import FAMILIES
from test_batch_workflow import REQUEST, INVOCATION


class SingleFamilyScopeTest(unittest.TestCase):
    def test_empty_and_oversize_reject_before_preparation_access(self):
        with patch.object(auth, 'validate_family_preparation_v2') as replay:
            for paths in ([], [Path('unused')] * 9):
                with self.subTest(count=len(paths)), self.assertRaises(ValueError):
                    auth._scope(paths, ROOT)
            replay.assert_not_called()

    def test_duplicate_cross_batch_and_invalid_preparation_still_reject(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = [Path(temp)/name for name in ('first', 'second')]
            for p in paths:
                p.mkdir()
                for name in ('family-config-v2.json', 'family-evidence-pack-v2.json', 'preparation-receipt.json'):
                    (p/name).write_text('{}')
            def receipt(family):
                return {'valid': True, 'family_id': family, 'preparation_id': 'prep:'+family}
            with patch.object(auth, 'validate_family_preparation_v2', return_value=receipt('f1')):
                with self.assertRaisesRegex(ValueError, 'duplicate family'):
                    auth._scope(paths, ROOT)
            batches = {'batch-manifest.json': {'batches': [
                {'batch_id': 'b1', 'family_ids': ['f1']}, {'batch_id': 'b2', 'family_ids': ['f2']}]}}
            with patch.object(auth, 'validate_family_preparation_v2', side_effect=[receipt('f1'),receipt('f2')]), \
                 patch.object(auth, '_verified_schedule', return_value=(None,None,batches)):
                with self.assertRaisesRegex(ValueError, 'exactly one schedule batch'):
                    auth._scope(paths, ROOT)
            for failure in ('partial scope', 'stale fingerprint'):
                with patch.object(auth, 'validate_family_preparation_v2', return_value={'valid':False,'errors':[failure]}):
                    with self.subTest(failure=failure), self.assertRaisesRegex(ValueError, 'cannot replay'):
                        auth._scope(paths[:1], ROOT)


class SingleFamilyManagedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='turbo-single-family-input-')
        cls.input_root = ROOT
        # This fixture uses the current graph, unlike the historical provider fixture.
        # Keep its synthetic clock after that graph rather than pinning a stale date.
        pointer = json.loads((ROOT/'data/generated/latest-graph.json').read_text())
        projection = json.loads((ROOT/pointer['release_path']/'projection.json').read_text())
        cls.now = datetime.fromisoformat(projection['as_of'].replace('Z', '+00:00')) + timedelta(hours=1)
        cls.now_utc = cls.now.isoformat().replace('+00:00', 'Z')
        cls.preparations = [Path(prepare_family_v2(FAMILIES[0], root=ROOT,
            output_root=Path(cls.fixture.name))['preparation_path'])]
        # Real public construction replays the full preparation; no slicing or mocked scope.
        cls.context = batch_output.build_batch_context(cls.preparations, root=ROOT,
            request_id=REQUEST, invocation_id=INVOCATION)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        controlled.ControllerTest.setUp(self)
        self.authorization['valid_from_utc'] = (self.now-timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
        self.authorization['expires_at_utc'] = (self.now+timedelta(hours=1)).isoformat().replace('+00:00', 'Z')

    def execute(self, **kwargs):
        return controller.execute(self.control, api_key='synthetic-only',
            clock=lambda: self.now_utc, transport=self.transport, **kwargs)

    def config(self):
        value = controlled.ControllerTest.config(self)
        value['recorded_at_utc'] = self.now_utc
        return value
    payload = provider_fixture.BatchProviderTest.payload
    transport_for = provider_fixture.BatchProviderTest.transport_for
    verifier_document = provider_fixture.BatchProviderTest.verifier_document
    review_document = provider_fixture.BatchProviderTest.review_document
    initialize = controlled.ControllerTest.initialize
    transport = controlled.ControllerTest.transport

    def test_complete_single_family_provider_review_and_closure_replay(self):
        self.assertEqual(len(self.context['families']), 1)
        pack = json.loads((self.preparations[0]/'family-evidence-pack-v2.json').read_text())
        family = self.context['families'][0]
        self.assertEqual(family['required_identity_ids'], pack['scope']['required_disposition_identity_ids'])
        self.assertEqual(family['context_identity_ids'], pack['scope']['context_only_identity_ids'])
        self.assertEqual(family['required_candidate_ids'], pack['scope']['required_prior_candidate_ids'])
        self.initialize()
        self.assertEqual(self.execute()['state'], 'WAITING_RELEASE_CONFIG')
        self.assertEqual(len(self.calls), 2)
        config = self.base/'release.json'; ledger._write(config, self.config())
        result = self.execute(release_config=config)
        self.assertEqual(result['state'], 'APPROVED_PENDING_PUBLICATION', result)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.execute()['state'], 'APPROVED_PENDING_PUBLICATION')
        self.assertEqual(len(self.calls), 3)
        proof = batch_closure.finalize_batch_closure(self.directory,
            output_root=self.base/'closures', root=self.publication_root, input_root=self.input_root,
            preparation_dirs=self.preparations)
        self.assertEqual(len(proof['families']), 1)
        self.assertEqual(proof['families'][0]['status'], 'reviewed_no_graph_movement')
        self.assertTrue(batch_closure.validate_batch_closure(Path(proof['closure_dir']), self.directory,
            root=self.publication_root, input_root=self.input_root, preparation_dirs=self.preparations)['valid'])
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(workflow.inspect_workflow(self.directory)['status'], 'approved')

    def test_missing_required_subject_and_tampered_pack_still_fail(self):
        payload = self.payload()
        payload['families'][0]['identity_dispositions'].pop()
        self.assertTrue(batch_output._validate_against_context(payload, self.context, root=ROOT))
        pack_path = self.preparations[0]/'family-evidence-pack-v2.json'
        original = pack_path.read_bytes()
        try:
            pack_path.write_bytes(original+b' ')
            with self.assertRaisesRegex(ValueError, 'cannot replay'):
                auth._scope(self.preparations, ROOT)
        finally:
            pack_path.write_bytes(original)
