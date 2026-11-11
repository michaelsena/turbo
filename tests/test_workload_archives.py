"""Adversarial in-memory publication archive bindings; no extraction."""
import copy
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from turbo.universe import workload_envelope as workload


class ArchivePublicationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def manifest(self, entries=None):
        entries = entries or [('workflow/plan.json', b'{"safe":true}')]
        path = self.root / 'replay.zip'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for name, content in entries: archive.writestr(name, content)
        return {'schema_version': 2, 'files': {'replay.zip': hashlib.sha256(path.read_bytes()).hexdigest()},
                'archived_files': {'virtual/plan.json': {'archive_path': 'replay.zip',
                    'member': 'workflow/plan.json', 'sha256': hashlib.sha256(b'{"safe":true}').hexdigest()}}}

    def test_reads_strict_json_without_extraction_or_restoration(self):
        manifest = self.manifest([('workflow/plan.json', b'{"safe":true}'),
                                  ('preparations/family-preparation:abc/config.json', b'{}')])
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(workload._publication_reader(self.root, manifest)('virtual/plan.json'), {'safe': True})
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertFalse((self.root / 'virtual').exists())

    def test_archive_member_and_unbound_hashes_reject(self):
        original = self.manifest()
        for kind in ('archive', 'member', 'unbound', 'missing'):
            manifest = copy.deepcopy(original)
            if kind == 'archive': manifest['files']['replay.zip'] = '0' * 64
            elif kind == 'member': manifest['archived_files']['virtual/plan.json']['sha256'] = '0' * 64
            elif kind == 'unbound': manifest['files'] = {}
            else: manifest['archived_files']['virtual/plan.json']['member'] = 'workflow/missing.json'
            with self.subTest(kind=kind), self.assertRaises(ValueError): workload._publication_reader(self.root, manifest)

    def test_unsafe_duplicate_and_symlink_entries_reject_even_when_unused(self):
        symlink = zipfile.ZipInfo('unused-link'); symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        for extra in ('../escape', '/absolute', 'folder/./entry', 'folder//entry', 'back\\slash', 'workflow/plan.json', symlink):
            manifest = self.manifest([('workflow/plan.json', b'{"safe":true}'), (extra, b'{}')])
            with self.subTest(extra=str(extra)), self.assertRaises(ValueError): workload._publication_reader(self.root, manifest)

    def test_ambiguous_bindings_physical_files_and_archive_symlink_reject(self):
        manifest = self.manifest(); manifest['archived_files']['other.json'] = manifest['archived_files']['virtual/plan.json']
        with self.assertRaisesRegex(ValueError, 'duplicate archive member binding'): workload._publication_reader(self.root, manifest)
        manifest = self.manifest(); (self.root / 'virtual').mkdir(); (self.root / 'virtual/plan.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'ambiguous'): workload._publication_reader(self.root, manifest)
        (self.root / 'virtual/plan.json').unlink()
        (self.root / 'replay.zip').rename(self.root / 'real.zip'); (self.root / 'replay.zip').symlink_to(self.root / 'real.zip')
        with self.assertRaisesRegex(ValueError, 'symlink'): workload._publication_reader(self.root, manifest)

    def test_bound_member_still_requires_strict_json(self):
        raw = b'{"duplicate":1,"duplicate":2}'
        manifest = self.manifest([('workflow/plan.json', raw)])
        manifest['archived_files']['virtual/plan.json']['sha256'] = hashlib.sha256(raw).hexdigest()
        bound = workload._publication_reader(self.root, manifest)
        with self.assertRaises(ValueError): bound('virtual/plan.json')

    def test_entry_member_archive_and_aggregate_limits(self):
        manifest = self.manifest([('workflow/plan.json', b'{"safe":true}'), ('other.json', b'{}')])
        for key, value in [('ARCHIVE_MAX_BYTES', 1), ('ARCHIVE_MEMBER_MAX_BYTES', 2),
                           ('ARCHIVE_EXPANDED_MAX_BYTES', 3), ('ARCHIVE_MAX_ENTRIES', 1)]:
            with self.subTest(limit=key), patch.object(workload, key, value), self.assertRaises(ValueError):
                workload._publication_reader(self.root, manifest)
        manifest = self.manifest([('workflow/plan.json', b'{"safe":true}'), ('bomb', b'x'*100000)])
        with self.assertRaisesRegex(ValueError, 'expansion'): workload._publication_reader(self.root, manifest)

    def test_aggregate_expansion_and_embedded_nul_entry_reject(self):
        payload = bytes(range(256)) * 20
        manifest = self.manifest([('workflow/plan.json', b'{"safe":true}'),
                                  ('first', payload), ('second', payload)])
        self.assertLess((self.root / 'replay.zip').stat().st_size, 6000)
        with patch.object(workload, 'ARCHIVE_EXPANDED_MAX_BYTES', 6000), self.assertRaisesRegex(ValueError, 'expansion'):
            workload._publication_reader(self.root, manifest)
        manifest = self.manifest([('workflow/plan.json', b'{"safe":true}'), ('unusedXname', b'{}')])
        path = self.root / 'replay.zip'
        raw = path.read_bytes().replace(b'unusedXname', b'unused\x00name')
        path.write_bytes(raw); manifest['files']['replay.zip'] = hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError, 'unsafe archive artifact name'):
            workload._publication_reader(self.root, manifest)

    def test_schema_one_no_archive_extension_and_unsafe_reference_reject(self):
        manifest = self.manifest(); manifest['schema_version'] = 1
        with self.assertRaisesRegex(ValueError, 'require publication manifest v2'): workload._publication_reader(self.root, manifest)
        for name in ('../bad', 'a\\b', 'a\x00b', '/absolute'):
            manifest = self.manifest(); manifest['archived_files'][name] = manifest['archived_files'].pop('virtual/plan.json')
            with self.subTest(name=name), self.assertRaises(ValueError): workload._publication_reader(self.root, manifest)


if __name__ == '__main__': unittest.main()
