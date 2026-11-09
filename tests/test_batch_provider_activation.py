"""Synthetic transport acceptance test; no factual research or production writes."""
import copy
import json
import subprocess
import unittest
from pathlib import Path

import test_batch_provider as provider_tests
from test_batch_output import proposal
from turbo.agents import batch_workflow
from turbo.pipeline_paths import ROOT
from turbo.universe import batch_closure as closure, graph_release


class BatchProviderActivationTest(unittest.TestCase):
    # Reuse transport/verified preparation fixtures without inheriting their tests.
    setUpClass = classmethod(provider_tests.BatchProviderTest.setUpClass.__func__)
    tearDownClass = classmethod(provider_tests.BatchProviderTest.tearDownClass.__func__)
    setUp = provider_tests.BatchProviderTest.setUp
    payload = provider_tests.BatchProviderTest.payload
    transport_for = provider_tests.BatchProviderTest.transport_for
    run_role = provider_tests.BatchProviderTest.run_role
    review_document = provider_tests.BatchProviderTest.review_document
    ledger = provider_tests.BatchProviderTest.ledger

    def test_synthetic_provider_movement_preserves_pilot_and_replays_closure(self):
        payload = self.payload()
        family = payload['families'][0]
        identity = family['identity_dispositions'][0]
        market = proposal(self.context['families'][0], identity['identity_id'], 'activation-smoke')
        family['proposed_markets'] = [market]
        family['analysis_summary'] = 'Synthetic plumbing test only; no factual research.'
        identity.update(disposition='provisional_map_to_proposals', proposal_ids=[market['proposal_id']],
                        evidence_label='inference', confidence=0.5)
        documents = {'primary': {'payload': payload}}
        primary = self.run_role('primary', documents['primary'])
        self.assertEqual(primary['status'], 'succeeded', primary)
        task = batch_workflow.assignment(self.directory, 'verifier')
        families = {f['family_id']: f for f in self.context['families']}
        self.assertIn(market['proposal_id'], [t['target_id'] for t in task['targets']])
        documents['verifier'] = {
            'input_hashes': {'primary': task['inputs']['primary']['submission_sha256']},
            'assessments': [{**{k: t[k] for k in ('family_id', 'target_kind', 'target_id')},
                'verdict': 'agree', 'rationale': 'Synthetic agreement for controlled plumbing test.',
                'supporting_evidence_ids': market['supporting_evidence_ids'] if t['target_kind'] == 'proposal'
                else [next(e['evidence_id'] for e in families[t['family_id']]['evidence_catalog']
                           if t['target_id'] in e['subject_ids'])]} for t in task['targets']]}
        self.assertEqual(self.run_role('verifier', documents['verifier'])['status'], 'succeeded')

        # Actual clean-commit gates run against a disposable clone, even when the
        # developer's checkout has uncommitted work. All publication is ignored
        # test output inside that clone; its canonical pointer is never changed.
        publication_root = self.base / 'publication'
        subprocess.run(['git', 'clone', '--local', '--quiet', str(ROOT), str(publication_root)], check=True)
        artifacts = publication_root / 'test-results'
        artifacts.mkdir()
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=publication_root, text=True).strip()
        config = {'schema_version': 1, 'recorded_at_utc': provider_tests.NOW,
                  'execution_commit': commit,
                  'graph_base_sha256': self.context['families'][0]['pack_metadata']['graph_projection_sha256'],
                  'families': [{'family_id': f['family_id'], 'outcome': 'reviewed_no_graph_movement',
                      'reason': 'Synthetic controlled test; retain unresolved research gaps.',
                      'proposals': [], 'mappings': []} for f in self.context['families']]}
        config['families'][0].update(outcome='activate',
            proposals=[{'proposal_id': market['proposal_id'], 'activation_status': 'provisional'}],
            mappings=[{'identity_id': identity['identity_id'], 'proposal_id': market['proposal_id'],
                       'relationship_type': 'partial_overlap'}])
        options = {'root': publication_root, 'input_root': self.input_root, 'preparation_dirs': self.preparations}
        preview = closure.prepare_batch_release(self.directory, config, **options)
        self.assertEqual([e['event_type'] for e in preview['preview']['movements']], ['create_market', 'map'])
        with self.assertRaises(ValueError):
            closure.persist_batch_activation(self.directory, output_root=artifacts / 'activations', **options)
        documents['release_reviewer'] = self.review_document(preview)
        review = self.run_role('release_reviewer', documents['release_reviewer'])
        self.assertEqual(review['status'], 'succeeded', review)
        activation = closure.persist_batch_activation(self.directory, output_root=artifacts / 'activations', **options)
        activation_dir = Path(activation['activation_dir'])
        self.assertTrue(closure.validate_batch_activation(activation_dir, activation_dir / 'activation-config.json', **options)['valid'])
        with self.assertRaisesRegex(ValueError, 'persisted cumulative'):
            closure.finalize_batch_closure(self.directory, output_root=artifacts / 'closures', **options)

        release_config = json.loads((publication_root / 'config/universe/graph-releases/canonical-universe-v1.json').read_text())
        original = graph_release.compile_graph_release(
            publication_root / 'config/universe/graph-releases/canonical-universe-v1.json',
            execution_commit=commit, root=publication_root)['projection']
        self.assertEqual(len(original['markets']), 3)
        self.assertEqual(len({gap for m in original['markets'] for gap in m['research_gap_ids']}), 2)
        release_config.update(release_name='synthetic-provider-activation-test', as_of_utc=provider_tests.NOW)
        release_config['activations'].append({'kind': 'batch',
            **{key: activation[key] for key in ('activation_id', 'events_sha256', 'projection_sha256', 'activation_config_sha256')},
            'activation_dir': str(activation_dir.relative_to(publication_root)),
            'activation_config': str((activation_dir / 'activation-config.json').relative_to(publication_root))})
        path = artifacts / 'release.json'
        bad = copy.deepcopy(release_config)
        bad['activations'] = bad['activations'][1:]
        path.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError, 'exact reviewed cumulative base'):
            graph_release.compile_graph_release(path, execution_commit=commit, **options)
        path.write_text(json.dumps(release_config))
        release = graph_release.run_graph_release(path, output_root=artifacts / 'versions',
            pointer_path=artifacts / 'latest-graph.json', **options)
        release_dir = Path(release['release_dir'])
        projection = json.loads((release_dir / 'projection.json').read_text())
        self.assertEqual(len(projection['markets']), 4)
        by_id = {m['market_id']: m for m in projection['markets']}
        for old in original['markets']:
            self.assertEqual(by_id[old['market_id']], old)
        added = [m for m in projection['markets'] if m['market_id'] not in {old['market_id'] for old in original['markets']}]
        self.assertEqual(added[0]['activation_status'], 'provisional')
        self.assertIn(identity['gap_id'], added[0]['research_gap_ids'])
        self.assertTrue(set(original['active_event_ids']) < set(projection['active_event_ids']))
        self.assertTrue(all(m in projection['mappings'] for m in original['mappings']))
        proof_options = {**options, 'graph_release_dir': release_dir, 'graph_release_config': path}
        result = closure.finalize_batch_closure(self.directory, output_root=artifacts / 'closures', **proof_options)
        self.assertEqual(result['families'][0]['status'], 'activated_events')
        self.assertTrue(closure.validate_batch_closure(Path(result['closure_dir']), self.directory, **proof_options)['valid'])
        for role, document in documents.items():
            self.assertEqual(self.run_role(role, document)['status'], 'succeeded')
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.ledger().status()['committed_microusd'], 60)
        self.assertEqual(self.ledger().status()['outstanding_microusd'], 0)
        self.assertTrue(graph_release._git_worktree_clean(publication_root))


if __name__ == '__main__':
    unittest.main()
