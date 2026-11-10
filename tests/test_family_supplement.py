"""Frozen supplemental evidence admission; no model, network, or accepted market."""
import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from turbo.pipeline_paths import ROOT
from turbo.universe.family_supplement import binding_for, load_supplement
from turbo.universe.family_pack_v2 import (generate_family_config_v2,
    compile_family_evidence_pack_v2, prepare_family_v2, validate_family_preparation_v2,
    validate_family_evidence_pack_v2, _pack_hash)
from turbo.agents.batch_output import _family_view

FAMILY = 'family:coverage:napcs-collection:10:001'


def manifest(root, relative='evidence', family='family:test', run='run:test', subject='identity:test'):
    directory = root / relative
    directory.mkdir(parents=True, exist_ok=True)
    raw = b'Frozen excerpt: the service includes recurring administration.\n'
    (directory / 'source.txt').write_bytes(raw)
    value = {'schema_version': 1, 'family_id': family, 'source_run_id': run,
        'sources': [{'source_id': 'source:test', 'path': relative + '/source.txt',
            'url': 'https://example.org/research', 'retrieved_at_utc': '2026-11-10T12:00:00Z',
            'sha256': hashlib.sha256(raw).hexdigest(), 'representation': 'excerpt',
            'subject_ids': [subject]}],
        'claims': [{'claim_id': 'claim:test', 'kind': 'inference',
            'text': 'Recurring administrative delivery is a research hypothesis.',
            'subject_ids': [subject], 'source_ids': ['source:test'], 'gap_ids': ['gap:test']}],
        'gaps': [{'gap_id': 'gap:test', 'question': 'Is this a distinct operating boundary?',
                  'subject_ids': [subject]}]}
    path = directory / 'manifest.json'
    path.write_text(json.dumps(value))
    return path, value


class SupplementValidationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'schemas').mkdir()
        shutil.copyfile(ROOT / 'schemas/family-supplement-v1.schema.json',
                        self.root / 'schemas/family-supplement-v1.schema.json')
        self.path, self.value = manifest(self.root)

    def load(self, value=None):
        if value is not None:
            self.path.write_text(json.dumps(value))
        return load_supplement(self.root, binding_for(self.root, self.path),
            family_id='family:test', source_run_id='run:test', subject_ids={'identity:test'})

    def test_separate_exact_source_claim_and_gap(self):
        result = self.load()
        self.assertEqual(result['supplemental_sources'][0]['text'],
                         (self.path.parent / 'source.txt').read_text())
        for key, value in self.value['claims'][0].items():
            self.assertEqual(result['supplemental_claims'][0][key], value)
        self.assertIn('not compiler-certified truth',
                      result['supplemental_claims'][0]['interpretation_boundary'])
        self.assertEqual(result['supplemental_gaps'], self.value['gaps'])
        self.assertIn('not an accepted market', result['supplemental_sources'][0]['interpretation_boundary'])

    def test_hash_tamper_paths_and_symlinks_fail(self):
        binding = binding_for(self.root, self.path)
        self.path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'manifest hash'):
            load_supplement(self.root, binding, family_id='family:test',
                            source_run_id='run:test', subject_ids={'identity:test'})
        self.path.write_text(json.dumps(self.value))
        (self.path.parent / 'source.txt').write_text('Changed source')
        with self.assertRaisesRegex(ValueError, 'source bytes hash'):
            self.load()
        for path in ('../source.txt', '/etc/passwd', 'missing.txt'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                binding_for(self.root, Path(path))
        (self.root / 'alias').symlink_to(self.path.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            binding_for(self.root, Path('alias/manifest.json'))

    def test_scope_reference_and_provenance_fail_closed(self):
        variants = []
        def mutation(fn):
            item = copy.deepcopy(self.value); fn(item); variants.append(item)
        mutation(lambda x: x.update(family_id='family:other'))
        mutation(lambda x: x.update(source_run_id='run:other'))
        mutation(lambda x: x['sources'][0].update(subject_ids=['identity:other']))
        mutation(lambda x: x['claims'][0].update(subject_ids=['identity:other']))
        mutation(lambda x: x['claims'][0].update(source_ids=['source:missing']))
        mutation(lambda x: x['claims'][0].update(gap_ids=['gap:missing']))
        mutation(lambda x: x['claims'][0].update(kind='fact', source_ids=[]))
        mutation(lambda x: x['claims'][0].update(kind='inference', source_ids=[], gap_ids=[]))
        mutation(lambda x: x['claims'][0].update(kind='unknown', gap_ids=[]))
        mutation(lambda x: x['sources'][0].update(url='https://user:secret@example.org'))
        mutation(lambda x: x['sources'][0].update(retrieved_at_utc='2026-11-10T12:00:00'))
        mutation(lambda x: x['sources'].append(copy.deepcopy(x['sources'][0])))
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.load(value)

    def test_duplicate_keys_nonfinite_and_integer_version_fail(self):
        for raw in ('{"schema_version":1,"schema_version":1}', '{"schema_version":NaN}',
                    json.dumps({**self.value, 'schema_version': 1.0}),
                    json.dumps({**self.value, 'schema_version': True})):
            self.path.write_text(raw)
            with self.subTest(raw=raw[:50]), self.assertRaises(ValueError):
                self.load()


class SupplementPreparationTest(unittest.TestCase):
    def test_complete_preparation_replays_preserves_base_and_catalogs_explicit_subjects(self):
        base_config = generate_family_config_v2(FAMILY)
        base = compile_family_evidence_pack_v2(base_config)
        subject = base['scope']['required_disposition_identity_ids'][0]
        with tempfile.TemporaryDirectory(prefix='.supplement-test-', dir=ROOT) as raw:
            relative = str(Path(raw).relative_to(ROOT))
            path, value = manifest(ROOT, relative, FAMILY,
                base_config['schedule_binding']['source_run_id'], subject)
            config = generate_family_config_v2(FAMILY, supplemental_manifest=path)
            pack = compile_family_evidence_pack_v2(config)
            self.assertNotIn('supplemental_evidence', base_config)
            self.assertFalse(any(k.startswith('supplemental_') for k in base))
            for key in base:
                if key not in ('metadata', 'counts'):
                    self.assertEqual(pack[key], base[key], key)
            self.assertEqual(pack['counts']['evidence_items'], base['counts']['evidence_items'] + 3)
            for key in base['counts']:
                if key != 'evidence_items':
                    self.assertEqual(pack['counts'][key], base['counts'][key], key)
            self.assertEqual(validate_family_evidence_pack_v2(pack, config), [])
            binding = {'family_id': FAMILY, 'preparation_id': 'synthetic:catalog-only'}
            view = _family_view(pack, binding)
            extras = [row for row in view['evidence_catalog'] if row['json_pointer'].startswith('/supplemental_')]
            self.assertEqual(len(extras), 3)
            self.assertTrue(all(row['subject_ids'] == [subject] for row in extras))
            self.assertEqual(view['required_identity_ids'], base['scope']['required_disposition_identity_ids'])
            altered = copy.deepcopy(pack)
            altered['supplemental_claims'][0]['text'] = 'Tampered claim'
            altered['metadata']['pack_sha256'] = _pack_hash(altered)
            self.assertTrue(validate_family_evidence_pack_v2(altered, config))
            result = prepare_family_v2(FAMILY, output_root=Path(raw) / 'preparations',
                                       supplemental_manifest=path)
            prepared = Path(result['preparation_path'])
            self.assertTrue(validate_family_preparation_v2(prepared)['valid'])
            (path.parent / 'source.txt').write_text('Edited after preparation')
            self.assertFalse(validate_family_preparation_v2(prepared)['valid'])


if __name__ == '__main__':
    unittest.main()
