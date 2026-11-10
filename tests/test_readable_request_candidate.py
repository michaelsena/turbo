"""Offline representation experiments; no production or model dispatch."""
import copy
import json
import unittest
from turbo.agents import readable_request_candidate as candidate


class ReadableCandidateTest(unittest.TestCase):
    def value(self):
        row = {'evidence_id': 'evidence:original', 'source_url': 'https://example.test/source',
               'sha256': 'f' * 64, 'text': 'Complete original evidence. ' * 20}
        return {'a/b~c': row, 'second': copy.deepcopy(row),
                'scalars': [None, True, False, 1, 1.25, -0.0, 'é漢字']}

    def test_readable_exact_roundtrip_and_independent_copies(self):
        value = self.value(); before = copy.deepcopy(value)
        encoded = candidate.encode(value)
        self.assertEqual(value, before)
        self.assertEqual(encoded['document']['a/b~c'], value['a/b~c'])
        self.assertEqual(encoded['document']['second'], {encoded['reference_key']: '/a~1b~0c'})
        restored = candidate.decode(encoded)
        self.assertEqual(candidate.canonical(restored), candidate.canonical(value))
        restored['second']['text'] = 'changed'
        self.assertEqual(restored['a/b~c'], value['a/b~c'])

    def test_sorted_wire_order_and_numeric_pointer_segments(self):
        row = {'text': 'all original facts ' * 100}
        value = {'z': row, 'a': {'0': row}, 'list': [row]}
        encoded = candidate.encode(value)
        self.assertEqual(encoded['document']['z'], {encoded['reference_key']: '/a/0'})
        self.assertEqual(candidate.decode(json.loads(candidate.canonical(encoded))), value)
        reverse = dict(reversed(list(value.items())))
        self.assertEqual(candidate.canonical(candidate.encode(reverse)), candidate.canonical(encoded))

    def test_marker_collision_and_nested_reference_roundtrip(self):
        row = {'$same_as_0': 'literal original', 'nested': ['identity:full'] * 100}
        value = {'first': row, 'second': copy.deepcopy(row), 'third': row['nested']}
        encoded = candidate.encode(value)
        self.assertEqual(encoded['reference_key'], '$same_as_1')
        self.assertEqual(candidate.decode(encoded), value)

    def test_forward_cycle_missing_and_malformed_references_fail(self):
        original = candidate.encode(self.value()); marker = original['reference_key']
        for ref in ('/second', '', '/missing', 0, '/a/b~c'):
            encoded = copy.deepcopy(original); encoded['document']['second'] = {marker: ref}
            with self.subTest(ref=ref), self.assertRaises(ValueError): candidate.decode(encoded)
        encoded = copy.deepcopy(original); encoded['document']['second']['extra'] = True
        with self.assertRaises(ValueError): candidate.decode(encoded)

    def test_integrity_and_expansion_bounds_fail_closed(self):
        encoded = candidate.encode(self.value())
        with self.assertRaisesRegex(ValueError, 'byte limit'): candidate.decode(encoded, max_output_bytes=100)
        encoded['document']['a/b~c']['text'] = 'tampered'
        with self.assertRaisesRegex(ValueError, 'digest'): candidate.decode(encoded)

    def test_json_domain_and_wrapper_are_strict(self):
        for value in ({1: 'key'}, {'tuple': (1, 2)}, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError): candidate.encode(value)
        for value in (None, {}, [], 'literal', 1, False):
            self.assertEqual(candidate.decode(candidate.encode(value)), value)
        encoded = candidate.encode({}); encoded['unexpected'] = 1
        with self.assertRaises(ValueError): candidate.decode(encoded)


if __name__ == '__main__': unittest.main()
