"""Synthetic publication continuations; only disposable canonical pointers change."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from turbo.agents import batch_controller as controller, batch_publication as publication
from turbo.agents import batch_execution_v2 as ledger, batch_workflow as workflow
from turbo.pipeline_paths import ROOT
from turbo.universe import batch_closure as closure
from turbo.universe.family_pack_v2 import prepare_family_v2
from turbo.agents.batch_output import build_batch_context
import test_batch_provider as fixtures
import test_batch_workflow as workflow_fixtures
from test_batch_output import FAMILIES, proposal

NOW = '2026-11-10T19:00:00Z'


class PublicationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='turbo-publication-inputs-')
        cls.input_root = ROOT.resolve()
        cls.preparations = [Path(prepare_family_v2(family, root=cls.input_root,
            output_root=Path(cls.fixture.name))['preparation_path']).resolve() for family in FAMILIES]
        cls.historical_contexts = {}
        cls.context = build_batch_context(cls.preparations, root=cls.input_root,
            request_id=workflow_fixtures.REQUEST, invocation_id=workflow_fixtures.INVOCATION)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    payload = fixtures.BatchProviderTest.payload
    transport_for = fixtures.BatchProviderTest.transport_for
    review_document = fixtures.BatchProviderTest.review_document

    def setUp(self):
        fixtures.BatchProviderTest.setUp(self)
        def context_for(*args, **kwargs):
            if kwargs.get('request_id') == workflow_fixtures.REQUEST:
                return copy.deepcopy(self.context)
            # Historical source packs are not mutated by these controller tests.
            # Verify once, then isolate each consumer with a deep copy; artifact,
            # journal, preview and closure checks themselves remain uncached.
            key = (str(args), str(sorted(kwargs.items())))
            if key not in self.historical_contexts:
                self.historical_contexts[key] = build_batch_context(*args, **kwargs)
            return copy.deepcopy(self.historical_contexts[key])
        isolated = patch.object(workflow, 'build_batch_context', side_effect=context_for)
        isolated.start(); self.addCleanup(isolated.stop)
        self.authorization['valid_from_utc'] = '2026-11-10T18:00:00Z'
        self.authorization['expires_at_utc'] = '2026-11-10T20:00:00Z'
        historical_boundary = publication.graph.validate_boundary_activation
        historical_cache = {}
        def verified_historical_boundary(*args, **kwargs):
            # This suite never mutates the historical pilot's evidence. Perform
            # its full validator once per disposable root; the cumulative compiler
            # still reads/hashes its persisted receipt and events on every replay.
            key = (str(args), str(sorted(kwargs.items())))
            if key not in historical_cache:
                historical_cache[key] = historical_boundary(*args, **kwargs)
            return copy.deepcopy(historical_cache[key])
        boundary_fixture = patch.object(publication.graph, 'validate_boundary_activation', side_effect=verified_historical_boundary)
        boundary_fixture.start(); self.addCleanup(boundary_fixture.stop)
        source_data = closure._source_data; source_cache = {}
        def immutable_source_data(*args, **kwargs):
            # Frozen source inputs never change in this suite. The source replay
            # is real once per binding; all mutable publication checks stay real.
            key = (str(args), str(sorted(kwargs.items())))
            if key not in source_cache:
                source_cache[key] = source_data(*args, **kwargs)
            return copy.deepcopy(source_cache[key])
        source_fixture = patch.object(closure, '_source_data', side_effect=immutable_source_data)
        source_fixture.start(); self.addCleanup(source_fixture.stop)
        self.root = self.base / 'publication-root'
        subprocess.run(['git', 'clone', '--local', '--quiet', str(ROOT), str(self.root)], check=True)
        self.control = self.base / 'controller'
        self.manifest = controller.initialize(self.control, workflow_dir=self.directory, registry_dir=self.registry,
            authorization=self.authorization, input_root=self.input_root,
            preparation_dirs=self.preparations, root=self.root)
        self.publication_config = {'schema_version': 1, 'output_root': 'data/controller-publication-test',
            'base_graph_config': 'config/universe/graph-releases/canonical-universe-lease-v1.json',
            'release_name': 'controlled-publication-test'}
        self.config_path = self.base / 'publication-config.json'
        ledger._write(self.config_path, self.publication_config)

    def approve(self, movement=False):
        payload = self.payload()
        market = None
        if movement:
            family = payload['families'][0]; identity = family['identity_dispositions'][0]
            market = proposal(self.context['families'][0], identity['identity_id'], 'controller-publication-test')
            family['proposed_markets'] = [market]
            identity.update(disposition='provisional_map_to_proposals', proposal_ids=[market['proposal_id']],
                            evidence_label='inference', confidence=0.5)
        def transport(url, headers, raw, timeout):
            role = json.loads(raw)['model'].split('/')[-1]
            if role == 'primary':
                document = {'payload': payload}
            elif role == 'verifier':
                task = workflow.assignment(self.directory, 'verifier')
                families = {row['family_id']: row for row in self.context['families']}
                document = {'input_hashes': {'primary': task['inputs']['primary']['submission_sha256']},
                    'assessments': [{**{key: row[key] for key in ('family_id', 'target_kind', 'target_id')},
                        'verdict': 'agree', 'rationale': 'Controlled synthetic evidence check.',
                        'supporting_evidence_ids': market['supporting_evidence_ids'] if row['target_kind'] == 'proposal' else
                            [next(e['evidence_id'] for e in families[row['family_id']]['evidence_catalog'] if row['target_id'] in e['subject_ids'])]}
                        for row in task['targets']]}
            else:
                document = self.review_document(ledger._read(self.directory / 'release-preview.json'))
            return self.transport_for(document)(url, headers, raw, timeout)
        options = dict(api_key='synthetic-only', clock=lambda: NOW, transport=transport)
        self.assertEqual(controller.execute(self.control, **options)['state'], 'WAITING_RELEASE_CONFIG')
        config = {'schema_version': 1, 'recorded_at_utc': NOW, 'execution_commit': publication.graph._git_head(self.root),
            'graph_base_sha256': self.context['families'][0]['pack_metadata']['graph_projection_sha256'],
            'families': [{'family_id': family['family_id'], 'outcome': 'reviewed_no_graph_movement',
                'reason': 'Synthetic publication fixture retains research gaps.', 'proposals': [], 'mappings': []}
                for family in self.context['families']]}
        if movement:
            config['families'][0].update(outcome='activate',
                proposals=[{'proposal_id': market['proposal_id'], 'activation_status': 'provisional'}],
                mappings=[{'identity_id': identity['identity_id'], 'proposal_id': market['proposal_id'], 'relationship_type': 'partial_overlap'}])
        release_config = self.base / 'release-config.json'; ledger._write(release_config, config)
        self.assertEqual(controller.execute(self.control, release_config=release_config, **options)['state'], 'APPROVED_PENDING_PUBLICATION')

    def publish(self):
        return publication.publish(self.control, config_path=self.config_path)

    def commit_source(self):
        subprocess.run(['git', '-C', str(self.root), 'add', 'data/controller-publication-test'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Controlled Test', '-c',
            'user.email=controlled@example.invalid', 'commit', '-qm', 'Controlled publication source'], check=True)

    def test_no_movement_closure_preserves_six_market_pointer_and_repeats(self):
        self.approve()
        pointer = (self.root / 'data/generated/latest-graph.json').read_bytes()
        result = self.publish()
        self.assertEqual(result['state'], 'COMPLETE', result)
        self.assertFalse(result['receipt']['graph_moved'])
        self.assertTrue(result['receipt']['closure_validated'])
        self.assertEqual(self.publish(), result)
        self.assertEqual(controller.status(self.control, clock=lambda: NOW)['state'], 'COMPLETE')
        self.assertEqual((self.root / 'data/generated/latest-graph.json').read_bytes(), pointer)
        current = json.loads(pointer)
        projection = ledger._read(self.root / current['release_path'] / 'projection.json')
        self.assertEqual(len(projection['markets']), 6)
        self.assertEqual(len(self.calls), 3)
        # Completion is always revalidated; neither mutable pointers nor files
        # can be hidden behind a previously written success receipt.
        canonical = self.root / 'data/generated/latest-graph.json'
        changed = json.loads(pointer); changed['release_id'] = 'changed'
        canonical.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'base changed'):
            self.publish()
        canonical.write_bytes(pointer)
        changed_config = dict(self.publication_config, release_name='changed')
        self.config_path.write_text(json.dumps(changed_config))
        with self.assertRaisesRegex(ValueError, 'already bound'):
            self.publish()
        self.config_path.write_text(json.dumps(self.publication_config))
        proof_path = Path(result['receipt']['closure_dir']) / 'closure.json'
        proof = proof_path.read_bytes(); proof_path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'closure replay failed'):
            self.publish()
        proof_path.write_bytes(proof)
        envelope_path = self.directory / 'release_reviewer.json'
        accepted_envelope = envelope_path.read_bytes()
        envelope = ledger._read(envelope_path)
        envelope['document']['verdict'] = 'reject'
        envelope['document']['findings'] = [{'finding_id':'rejected','status':'unresolved','rationale':'Synthetic rejection.'}]
        envelope['submission_sha256'] = workflow._hash({k:v for k,v in envelope.items() if k!='submission_sha256'})
        envelope_path.write_text(json.dumps(envelope))
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.publish()
        self.assertEqual(canonical.read_bytes(), pointer)
        envelope_path.write_bytes(accepted_envelope)
        readme = self.root / 'README.md'; readme.write_bytes(readme.read_bytes() + b'\nControlled unrelated source commit.\n')
        subprocess.run(['git', '-C', str(self.root), 'add', 'README.md', 'data/controller-publication-test'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Controlled Test', '-c',
            'user.email=controlled@example.invalid', 'commit', '-qm', 'Controlled unrelated source commit'], check=True)
        with self.assertRaisesRegex(ValueError, 'original reviewed execution commit'):
            self.publish()
        self.assertEqual(canonical.read_bytes(), pointer)

    def test_movement_waits_for_exact_source_commit_and_stages_before_pointer(self):
        self.approve(movement=True)
        pointer = (self.root / 'data/generated/latest-graph.json').read_bytes()
        persist = closure.persist_batch_activation
        def interrupted(*args, **kwargs):
            persist(*args, **kwargs)
            raise RuntimeError('controlled interruption after atomic activation')
        with patch.object(closure, 'persist_batch_activation', side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError, 'controlled interruption'):
                self.publish()
        self.assertEqual(publication.inspect(self.manifest)['state'], 'PUBLICATION_ACTIVATION_STAGED')
        result = self.publish()
        self.assertEqual(result['state'], 'WAITING_PUBLICATION_SOURCE_COMMIT')
        self.assertEqual(self.publish(), result)
        self.commit_source()
        with patch.object(publication.graph, 'run_graph_release', side_effect=RuntimeError('before graph stage')):
            with self.assertRaisesRegex(RuntimeError, 'before graph stage'):
                self.publish()
        compiler = self.root / 'src/turbo/universe/graph.py'
        code = compiler.read_bytes(); compiler.write_bytes(code + b'\n# unrelated tracked change\n')
        with self.assertRaisesRegex(ValueError, 'tracked files changed'):
            self.publish()
        compiler.write_bytes(code)
        unrelated = self.root / 'src/untracked-executable.py'; unrelated.write_text('raise RuntimeError()')
        with self.assertRaisesRegex(ValueError, 'undeclared untracked'):
            self.publish()
        unrelated.unlink()
        stage = publication.graph.run_graph_release
        def graph_interrupted(*args, **kwargs):
            stage(*args, **kwargs)
            raise RuntimeError('controlled interruption after graph staging')
        with patch.object(publication.graph, 'run_graph_release', side_effect=graph_interrupted):
            with self.assertRaisesRegex(RuntimeError, 'controlled interruption'):
                self.publish()
        self.assertEqual(publication.inspect(self.manifest)['state'], 'PUBLICATION_GRAPH_STAGED')
        finalize = closure.finalize_batch_closure
        def closure_interrupted(*args, **kwargs):
            finalize(*args, **kwargs)
            raise RuntimeError('controlled interruption after closure staging')
        with patch.object(closure, 'finalize_batch_closure', side_effect=closure_interrupted):
            with self.assertRaisesRegex(RuntimeError, 'controlled interruption'):
                self.publish()
        self.assertEqual((self.root / 'data/generated/latest-graph.json').read_bytes(), pointer)
        self.assertEqual(publication.inspect(self.manifest)['state'], 'PUBLICATION_READY_TO_PROMOTE')
        from turbo.universe import graph_publication
        promote = graph_publication.promote_pointer
        def pointer_interrupted(**kwargs):
            promote(**kwargs)
            raise RuntimeError('controlled interruption after canonical pointer')
        with patch.object(graph_publication, 'promote_pointer', side_effect=pointer_interrupted):
            with self.assertRaisesRegex(RuntimeError, 'controlled interruption'):
                self.publish()
        self.assertEqual(publication.inspect(self.manifest)['state'], 'PUBLICATION_VALIDATED_PENDING_RECEIPT')
        result = self.publish()
        self.assertEqual(result['state'], 'COMPLETE')
        self.assertTrue(result['receipt']['graph_moved'])
        self.assertEqual(self.publish(), result)
        old_pointer = json.loads(pointer)
        old_projection = ledger._read(self.root / old_pointer['release_path'] / 'projection.json')
        new_projection = ledger._read(self.root / result['receipt']['pointer']['release_path'] / 'projection.json')
        self.assertEqual(len(old_projection['markets']), 6)
        self.assertEqual(len(new_projection['markets']), 7)
        new_by_id = {row['market_id']: row for row in new_projection['markets']}
        for old in old_projection['markets']:
            self.assertEqual(new_by_id[old['market_id']], old)
        self.assertTrue(set(old_projection['active_event_ids']) < set(new_projection['active_event_ids']))
        self.assertTrue(all(row in new_projection['mappings'] for row in old_projection['mappings']))
        self.assertEqual(len(self.calls), 3)
        config_path = self.root / self.publication_config['output_root'] / 'graph-config.json'
        original_config = config_path.read_bytes(); config_path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'graph configuration changed'):
            self.publish()
        config_path.write_bytes(original_config)
        intent = publication._binding(self.manifest, 'publication-intent')
        events = publication._activation_dir(self.manifest, intent) / 'events.json'
        events.write_text('[]')
        with self.assertRaisesRegex(ValueError, 'activation replay failed'):
            self.publish()
        self.assertEqual(ledger._read(self.root / 'data/generated/latest-graph.json'), result['receipt']['pointer'])



class SourceBoundaryTest(unittest.TestCase):
    def test_source_commit_rejects_unrelated_changes_before_binding(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve(); activation = root / 'activation'; activation.mkdir()
            (activation / 'events.json').write_text('[]')
            config = root / 'graph-config.json'; config.write_text('{}')
            with patch.object(publication.graph, '_git_worktree_clean', return_value=True), \
                 patch.object(publication.graph, '_git_head', return_value='b' * 40), \
                 patch.object(publication, '_activation_dir', return_value=activation), \
                 patch.object(publication.subprocess, 'check_output', return_value='activation/events.json\ngraph-config.json\nsrc/changed.py\n'), \
                 patch.object(publication, '_binding') as binding:
                with self.assertRaisesRegex(ValueError, 'only exact activation'):
                    publication._source({'root': str(root)}, {'reviewed_execution_commit': 'a' * 40}, config)
                binding.assert_not_called()

    def test_controller_intent_rejects_subdirectory_before_binding_or_staging(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            subprocess.run(['git', 'init', '--quiet', str(root)], check=True)
            nested = root / 'nested'; nested.mkdir()
            with patch.object(publication, '_approved') as approval, patch.object(publication, '_binding') as binding:
                with self.assertRaisesRegex(ValueError, 'Git top-level'):
                    publication._intent({'root': str(nested)}, {})
                approval.assert_not_called(); binding.assert_not_called()
            self.assertEqual(list(nested.iterdir()), [])

    def test_no_movement_new_clean_commit_refuses_before_replay(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            subprocess.run(['git', 'init', '--quiet', str(root)], check=True)
            path = root / 'source.txt'
            def commit(value):
                path.write_text(value)
                subprocess.run(['git', '-C', str(root), 'add', 'source.txt'], check=True)
                subprocess.run(['git', '-C', str(root), '-c', 'user.name=Controlled Test', '-c',
                    'user.email=controlled@example.invalid', 'commit', '-qm', value], check=True)
            commit('original')
            original = publication.graph._git_head(root)
            commit('unrelated new source')
            self.assertTrue(publication.graph._git_worktree_clean(root))
            with patch.object(publication, '_approved') as approval:
                with self.assertRaisesRegex(ValueError, 'original reviewed execution commit'):
                    publication._verify_intent({'root': str(root)}, {'movement': False, 'reviewed_execution_commit': original})
                approval.assert_not_called()
