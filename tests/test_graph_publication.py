"""Guarded writer contention tests use disposable repositories and pointers."""
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from turbo.universe.graph_publication import promote_pointer


class PointerPublicationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='turbo-pointer-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        subprocess.run(['git', 'init', '--quiet', str(self.root)], check=True)
        self.pointer = self.root / 'data/generated/latest-graph.json'
        self.pointer.parent.mkdir(parents=True)
        self.base = {'release_id': 'base'}
        self.pointer.write_text(json.dumps(self.base))

    def promote(self, target, validate=lambda: None):
        return promote_pointer(root=self.root, pointer_path=self.pointer,
            expected_pointer=self.base, new_pointer=target, validate=validate)

    def test_exact_repeat_validates_and_stale_base_refuses(self):
        target = {'release_id': 'target'}; calls = []
        self.assertTrue(self.promote(target, lambda: calls.append(True))['promoted'])
        self.assertFalse(self.promote(target, lambda: calls.append(True))['promoted'])
        self.assertEqual(len(calls), 2)
        with self.assertRaisesRegex(ValueError, 'base changed'):
            self.promote({'release_id': 'other'})
        self.assertEqual(json.loads(self.pointer.read_text()), target)

    def test_validation_failure_and_changed_pointer_do_not_overwrite(self):
        def rejected():
            raise ValueError('controlled failed validation')
        with self.assertRaisesRegex(ValueError, 'failed validation'):
            self.promote({'release_id': 'target'}, rejected)
        self.assertEqual(json.loads(self.pointer.read_text()), self.base)
        changed = {'release_id': 'external'}
        with self.assertRaisesRegex(ValueError, 'changed during validation'):
            self.promote({'release_id': 'target'}, lambda: self.pointer.write_text(json.dumps(changed)))
        self.assertEqual(json.loads(self.pointer.read_text()), changed)

    def test_competing_supported_writers_cannot_both_promote_same_base(self):
        entered = threading.Event(); release = threading.Event(); errors = []
        def validate_first():
            entered.set()
            if not release.wait(5):
                raise RuntimeError('test coordination timed out')
        def first():
            try:
                self.promote({'release_id': 'first'}, validate_first)
            except Exception as error:
                errors.append(error)
        def second():
            try:
                self.promote({'release_id': 'second'})
            except Exception as error:
                errors.append(error)
        a = threading.Thread(target=first); b = threading.Thread(target=second)
        a.start(); self.assertTrue(entered.wait(5)); b.start(); release.set()
        a.join(5); b.join(5)
        self.assertFalse(a.is_alive()); self.assertFalse(b.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIn('base changed', str(errors[0]))
        self.assertEqual(json.loads(self.pointer.read_text()), {'release_id': 'first'})

    def test_subdirectory_root_and_alternate_pointer_are_refused(self):
        nested = self.root / 'nested'; nested.mkdir()
        with self.assertRaisesRegex(ValueError, 'Git top-level'):
            promote_pointer(root=nested, pointer_path=self.pointer,
                expected_pointer=self.base, new_pointer={'release_id':'target'}, validate=lambda: None)
        with self.assertRaisesRegex(ValueError, 'canonical graph pointer'):
            promote_pointer(root=self.root, pointer_path=self.root / 'other.json',
                expected_pointer=None, new_pointer={'release_id':'target'}, validate=lambda: None)
        self.assertEqual(json.loads(self.pointer.read_text()), self.base)
