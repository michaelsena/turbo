"""Synthetic policy/provenance tests; never publish or admit real markets."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from turbo.agents import governed_eligibility as eligibility


class EligibilityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'canonical'
        (self.root / 'config').mkdir(parents=True)
        self.strategy = json.loads((eligibility.ROOT / 'config/strategy.json').read_text())
        self.mid = 'market-version:synthetic-reviewed'
        self.plan = {'files': {}, 'market_version_ids': [self.mid],
                     'evidence_cutoff': '2026-11-10T12:00:00Z'}
        self.write('strategy', self.strategy)
        (self.root / 'config/strategy.json').write_bytes((self.base / 'strategy.json').read_bytes())
        self.write('graph', {'synthetic': 'private verifier patched only for unit isolation'})
        self.projection = {'as_of': '2026-11-09T00:00:00Z', 'markets': [
            {'market_version_id': self.mid, 'canonical_name': 'Synthetic fixture'}]}
        self.source = self.base / 'source.txt'
        self.source.write_text('Frozen source supports a synthetic operating market.\n')
        self.plan['files']['source.txt'] = eligibility._file_sha(self.source)
        self.evidence = {'schema_version': 1, 'items': [{
            'evidence_id': 'evidence:source', 'market_version_ids': [self.mid],
            'source_path': 'source.txt', 'source_sha256': self.plan['files']['source.txt'],
            'source_url': 'https://example.test/source', 'retrieved_at': '2026-11-09T00:00:00Z',
            'statement': 'Frozen source supports a synthetic operating market.'}],
            'claims': [{'claim_id': 'claim:one', 'market_version_ids': [self.mid],
                        'label': 'inference', 'statement': 'Synthetic inference, not production research.',
                        'evidence_ids': ['evidence:source'], 'gap_ids': ['gap:one']}],
            'gaps': [{'gap_id': 'gap:one', 'market_version_ids': [self.mid],
                      'question': 'What independent evidence would establish this gate?'}]}
        self.write('evidence', self.evidence)
        self.canonical = patch.object(eligibility, '_canonical_graph', return_value=(self.root, self.projection))
        self.canonical.start(); self.addCleanup(self.canonical.stop)

    def write(self, key, document):
        path = self.base / (key + '.json')
        path.write_text(json.dumps(document, sort_keys=True))
        self.plan[key] = path.name
        self.plan['files'][path.name] = eligibility._file_sha(path)

    def inputs(self):
        return eligibility.validate_eligibility_input(self.base, self.plan)

    def document(self, inputs):
        return {'schema_version': 1, **{k: inputs[k] for k in (
            'graph_sha256', 'strategy_sha256', 'evidence_sha256', 'evidence_cutoff')},
            'markets': [{'market_version_id': self.mid, 'gates': {g: {
                'status': 'pass', 'evidence_label': 'inference', 'confidence': .6,
                'rationale': 'Synthetic evidence-backed inference only.',
                'supporting_evidence_ids': ['evidence:source'], 'counterevidence_ids': [],
                'research_gaps': ['Independent corroboration is absent.']} for g in eligibility.GATES}}]}

    def test_pass_hold_exclusion_preserve_original_strategy_and_deal_conditions(self):
        inp = self.inputs(); doc = self.document(inp)
        result = eligibility.compile_eligibility(doc, inp)
        self.assertEqual(result['markets'][0]['status'], 'eligible')
        self.assertEqual(result['deal_conditions']['purchase_multiple']['hard_ceiling_ebitda'], 9)
        self.assertEqual(result['deal_conditions']['target_enterprise_value'], self.strategy['target_enterprise_value'])
        gate = doc['markets'][0]['gates']['unionized_workforces']
        gate.update(status='unknown', evidence_label='unknown')
        self.assertEqual(eligibility.compile_eligibility(doc, inp)['markets'][0]['status'], 'hold')
        gate.update(status='fail', evidence_label='inference')
        self.assertEqual(eligibility.compile_eligibility(doc, inp)['markets'][0]['status'], 'excluded')
        self.assertEqual(inp['markets'], self.projection['markets'])

    def test_mixed_source_cited_once_preserves_unknown_but_overlap_fails_every_gate(self):
        inp = self.inputs()
        for name in eligibility.GATES:
            with self.subTest(gate=name):
                doc = self.document(inp)
                gate = doc['markets'][0]['gates'][name]
                gate.update(status='unknown', evidence_label='unknown',
                    rationale='The source supports service existence but does not establish the required population.',
                    research_gaps=['Obtain representative population evidence.'])
                original = copy.deepcopy(doc)
                result = eligibility.compile_eligibility(doc, inp)
                self.assertEqual(result['markets'][0]['status'], 'hold')
                self.assertEqual(doc, original)
                gate['counterevidence_ids'] = list(gate['supporting_evidence_ids'])
                with self.assertRaisesRegex(ValueError, 'conflicting'):
                    eligibility.compile_eligibility(doc, inp)
                self.assertEqual(gate['counterevidence_ids'], ['evidence:source'])

    def test_source_bytes_excerpt_cutoff_and_claim_reference_are_verified(self):
        self.assertIn('Frozen source', self.inputs()['evidence']['items'][0]['source_text'])
        self.source.write_text('Changed bytes')
        with self.assertRaisesRegex(ValueError, 'source bytes'):
            self.inputs()
        self.source.write_text('Frozen source supports a synthetic operating market.\n')
        bad = copy.deepcopy(self.evidence); bad['items'][0]['statement'] = 'Fabricated excerpt'
        self.write('evidence', bad)
        with self.assertRaisesRegex(ValueError, 'excerpt'):
            self.inputs()
        bad = copy.deepcopy(self.evidence); bad['claims'][0]['evidence_ids'] = ['evidence:absent']
        self.write('evidence', bad)
        with self.assertRaisesRegex(ValueError, 'claim reference'):
            self.inputs()
        bad = copy.deepcopy(self.evidence); bad['items'][0]['retrieved_at'] = '2027-01-01T00:00:00Z'
        self.write('evidence', bad)
        with self.assertRaisesRegex(ValueError, 'cutoff'):
            self.inputs()

    def test_market_scope_policy_and_artifact_tampering_fail_closed(self):
        self.plan['market_version_ids'] = ['market-version:not-canonical']
        with self.assertRaisesRegex(ValueError, 'canonical graph'):
            self.inputs()
        self.plan['market_version_ids'] = [self.mid]
        altered = copy.deepcopy(self.strategy); altered['excluded_exposures'].remove('unionized_workforces')
        self.write('strategy', altered)
        with self.assertRaisesRegex(ValueError, 'canonical policy'):
            self.inputs()
        self.write('strategy', self.strategy)
        (self.base / 'evidence.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'changed eligibility input'):
            self.inputs()

    def test_no_unknown_as_pass_missing_gates_foreign_evidence_or_fake_confidence(self):
        inp = self.inputs(); doc = self.document(inp)
        for mutate in (
            lambda d: d['markets'][0]['gates']['unionized_workforces'].update(evidence_label='unknown'),
            lambda d: d['markets'][0]['gates'].pop('insurance_or_credit_risk'),
            lambda d: d['markets'][0]['gates']['us_market_scope'].update(supporting_evidence_ids=['evidence:foreign']),
            lambda d: d['markets'][0]['gates']['us_market_scope'].update(confidence=float('nan')),
            lambda d: d.update(schema_version=True),
        ):
            bad = copy.deepcopy(doc); mutate(bad)
            with self.assertRaises(ValueError):
                eligibility.compile_eligibility(bad, inp)

    def test_evaluation_requires_replayed_provider_receipt_and_eligible_projection(self):
        inp = self.inputs(); doc = self.document(inp)
        self.write('eligibility', {'synthetic': 'producer descriptor'})
        fake = types.ModuleType('turbo.agents.evaluation_execution')
        fake.validate_eligibility_provider = lambda directory, descriptor: doc
        with patch.dict(sys.modules, {'turbo.agents.evaluation_execution': fake}):
            self.assertEqual(eligibility.validate_for_evaluation(self.base, self.plan)['market_version_ids'], [self.mid])
            doc['markets'][0]['gates']['unionized_workforces'].update(status='unknown', evidence_label='unknown')
            with self.assertRaisesRegex(ValueError, 'held or excluded'):
                eligibility.validate_for_evaluation(self.base, self.plan)
            def reject(directory, descriptor):
                raise ValueError('provider journal cannot replay')
            fake.validate_eligibility_provider = reject
            with self.assertRaisesRegex(ValueError, 'provider journal'):
                eligibility.validate_for_evaluation(self.base, self.plan)

    def test_source_path_escape_and_claim_gap_scope_rejected(self):
        bad = copy.deepcopy(self.evidence); bad['items'][0]['source_path'] = '../outside.txt'
        self.write('evidence', bad)
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.inputs()
        bad = copy.deepcopy(self.evidence); bad['gaps'][0]['market_version_ids'] = ['market-version:other']
        self.write('evidence', bad)
        with self.assertRaisesRegex(ValueError, 'exact market scope'):
            self.inputs()


if __name__ == '__main__':
    unittest.main()
