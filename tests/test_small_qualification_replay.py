"""Publication transport guards, without invoking model or compiler work."""
import importlib.util
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/replay-small-qualification.py'
spec = importlib.util.spec_from_file_location('pilot_replay', SCRIPT)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class PublicationTransportTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.source = self.base / 'source'
        self.source.mkdir()
        (self.source / 'plan.json').write_text('{"immutable":true}\n')
        self.target = self.base / 'runtime' / 'workflow'

    def test_default_requires_restore_and_does_not_write(self):
        with self.assertRaisesRegex(ValueError, 'explicit --restore'):
            replay.restore_plan(self.source, self.target, restore=False)
        self.assertFalse(self.target.exists())

    def test_restore_preserves_bytes_and_matching_existing_files(self):
        plan = replay.restore_plan(self.source, self.target, restore=True)
        replay.copy_missing(plan)
        (self.target / '.lock').touch()
        before = (self.target / 'plan.json').stat().st_mtime_ns
        self.assertEqual(replay.restore_plan(self.source, self.target, restore=False), [])
        self.assertEqual((self.source / 'plan.json').read_bytes(), (self.target / 'plan.json').read_bytes())
        self.assertEqual((self.target / 'plan.json').stat().st_mtime_ns, before)

    def test_mismatch_is_detected_before_any_copy(self):
        self.target.mkdir(parents=True)
        (self.source / 'new.json').write_text('{}')
        (self.target / 'plan.json').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'differs'):
            replay.restore_plan(self.source, self.target, restore=True)
        self.assertFalse((self.target / 'new.json').exists())
        self.assertEqual((self.target / 'plan.json').read_text(), 'changed')

    def test_symlink_and_extra_file_are_rejected(self):
        self.target.mkdir(parents=True)
        (self.target / 'plan.json').symlink_to(self.source / 'plan.json')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            replay.restore_plan(self.source, self.target, restore=True)
        (self.target / 'plan.json').unlink()
        (self.target / 'extra.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'differs'):
            replay.restore_plan(self.source, self.target, restore=True)

    def test_manifest_hash_and_relative_paths_fail_closed(self):
        manifest = self.base / 'manifest.json'
        manifest.write_text(json.dumps({'schema_version': 1, 'input_commit': replay.INPUT_COMMIT,
                                        'files': {'source/plan.json': '0' * 64}}))
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            replay.load_manifest(self.base, manifest)
        for name in ('../escape', '/absolute'):
            with self.assertRaisesRegex(ValueError, 'repository-relative'):
                replay.relative_path(self.base, name)

    def test_input_checkout_requires_pin_and_clean_tree_without_clone(self):
        missing = self.base / 'missing-input'
        with patch.object(replay.subprocess, 'run') as clone:
            with self.assertRaisesRegex(ValueError, 'explicit --restore'):
                replay.frozen_input(self.base, missing, {}, restore=False)
            clone.assert_not_called()
        for replies in ([str(self.source), 'wrong-commit'],
                        [str(self.source), replay.INPUT_COMMIT, ' M data.json']):
            with patch.object(replay, 'git', side_effect=replies):
                with self.assertRaisesRegex(ValueError, 'unchanged checkout'):
                    replay.frozen_input(self.base, self.source, {}, restore=False)

    def test_capsule_validates_every_object_before_clone(self):
        raw = b'controlled object'
        object_id = hashlib.sha1(b'commit 17\0' + raw).hexdigest()
        capsule = {'schema_version': 1, 'input_commit': object_id, 'input_tree': 'tree',
                   'objects': [{'sha1': object_id, 'type': 'commit',
                                'base64': base64.b64encode(raw).decode()}]}
        path = self.base / 'objects.json'
        manifest = {'input_objects': 'objects.json', 'input_tree': 'tree', 'files': {}}
        def save():
            path.write_text(json.dumps(capsule))
            manifest['files']['objects.json'] = replay.digest(path)
        save()
        with patch.object(replay, 'INPUT_COMMIT', object_id):
            self.assertEqual(replay.input_objects(self.base, manifest), [('commit', object_id, raw)])
            for field, value in [('sha1', '0' * 40), ('type', 'tag')]:
                original = capsule['objects'][0][field]
                capsule['objects'][0][field] = value
                save()
                with patch.object(replay.subprocess, 'run') as clone:
                    with self.assertRaises(ValueError):
                        replay.frozen_input(self.base, self.base / 'new-input', manifest, restore=True)
                    clone.assert_not_called()
                capsule['objects'][0][field] = original
            save()
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'hash bound'):
                replay.input_objects(self.base, manifest)

    def test_input_and_runtime_aliases_cannot_hide_symlinks(self):
        alias = self.base / 'alias'
        alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            replay.external_path(alias)
        self.assertEqual(replay.external_path(self.source), self.source)


if __name__ == '__main__':
    unittest.main()
