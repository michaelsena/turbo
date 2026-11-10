"""Offline workload accounting and publication binding regressions."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from turbo.pipeline_paths import ROOT
from turbo.universe.family_pack_v2 import _verified_graph, _verified_schedule
from turbo.universe.workload_envelope import (
    _overlay, _published_closure, _validate_obligations, build_report, scenario_envelope,
)

MANIFEST = 'data/research_pilots/small-qualification-20261109/publication-manifest.json'


class WorkloadEnvelopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schedule, _, artifacts = _verified_schedule(root=ROOT)
        cls.families = {f['family_id']: f for f in artifacts['family-manifest.json.gz']['families']}
        cls.batches = artifacts['batch-manifest.json']['batches']
        _, cls.receipt, cls.projection = _verified_graph(root=ROOT)
        cls.closure, _ = _published_closure(ROOT, MANIFEST, cls.schedule, cls.families, cls.receipt, cls.projection)

    def test_real_published_counts_and_retained_gaps(self):
        report = build_report(root=ROOT, publication_manifests=[MANIFEST])
        self.assertEqual(report['scheduled'], {'families': 1018, 'required_identities': 8182, 'required_candidates': 976, 'batches': 129})
        self.assertEqual(report['completed_batch_closure_work'], {'families': 2, 'required_identities': 8, 'required_candidates': 1})
        self.assertEqual(report['remaining'], {'families': 1016, 'required_identities': 8174, 'required_candidates': 975, 'batches_with_remaining_work': 129})
        self.assertEqual(len(report['retained_gaps']['all_distinct_ids']), 5)
        self.assertFalse(report['retained_gaps']['resolved_by_completion'])
        self.assertIsNone(report['scenario'])
        self.assertEqual(sum(report['batch_required_identity_histogram'].values()), 129)

    def test_duplicate_manifest_is_idempotent(self):
        self.assertEqual(build_report(root=ROOT, publication_manifests=[MANIFEST]),
                         build_report(root=ROOT, publication_manifests=[MANIFEST, MANIFEST]))

    def test_missing_current_activation_manifest_fails(self):
        with self.assertRaisesRegex(ValueError, 'do not cover'):
            build_report(root=ROOT)

    def test_wrong_schedule_subjects_or_receipt_fail(self):
        families = copy.deepcopy(self.families)
        fid = self.closure['families'][0]['family_id']
        families[fid]['required_disposition_identity_ids'][0] = 'identity:wrong'
        with self.assertRaisesRegex(ValueError, 'selected schedule'):
            _published_closure(ROOT, MANIFEST, self.schedule, families, self.receipt, self.projection)
        schedule = {**self.schedule, 'receipt_sha256': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'selected schedule'):
            _published_closure(ROOT, MANIFEST, schedule, self.families, self.receipt, self.projection)

    def test_current_graph_must_retain_activated_events(self):
        projection = {**self.projection, 'active_event_ids': []}
        with self.assertRaisesRegex(ValueError, 'event binding'):
            _published_closure(ROOT, MANIFEST, self.schedule, self.families, self.receipt, projection)

    def test_modified_publication_artifact_fails(self):
        manifest = json.loads((ROOT / MANIFEST).read_text())
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            for name in [MANIFEST, *manifest['files']]:
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, destination)
            path = root / manifest['workflow_dir'] / 'release_reviewer.json'
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'artifact hash mismatch'):
                _published_closure(root, MANIFEST, self.schedule, self.families, self.receipt, self.projection)

    def test_overlay_rejects_conflict_and_keeps_retry_uncompleted(self):
        completed, _, _ = _overlay(self.families, [self.closure, self.closure])
        self.assertEqual(len(completed), 2)
        changed = copy.deepcopy(self.closure)
        changed['families'][0]['status'] = 'retry_required'
        with self.assertRaisesRegex(ValueError, 'conflicting closures'):
            _overlay(self.families, [self.closure, changed])
        completed, retry, gaps = _overlay(self.families, [changed])
        self.assertEqual(len(completed), 1)
        self.assertEqual(retry, {changed['families'][0]['family_id']})
        self.assertEqual(len(gaps), 3)

    def test_schedule_count_inconsistency_and_duplicates_fail(self):
        queued = {fid: copy.deepcopy(f) for fid, f in self.families.items() if f['schedulable']}
        family = next(f for f in queued.values() if f['required_disposition_identity_ids'])
        family['required_disposition_identity_ids'].append(family['required_disposition_identity_ids'][0])
        family['counts']['required_identities'] += 1
        with self.assertRaisesRegex(ValueError, 'schedule subject count'):
            _validate_obligations(queued, self.batches)
        batches = copy.deepcopy(self.batches)
        batches[0]['required_candidates'] += 1
        with self.assertRaisesRegex(ValueError, 'batch subject count'):
            _validate_obligations(self.families, batches)

    def test_scenarios_are_explicit_and_assumed(self):
        values = dict(escalation_fraction='0.5', seconds_per_call=10, concurrency=2,
                      cost_units_per_call=2, cost_unit='hypothetical units')
        result = scenario_envelope(4, values)
        self.assertEqual(result['expected_calls'], '18.0')
        self.assertEqual(result['idealized_seconds'], '90.0')
        self.assertEqual(result['expected_cost_units'], '36.0')
        self.assertEqual(result['classification'], 'assumption_scenario_not_measured_forecast')
        for bad in ({}, {**values, 'escalation_fraction': 2}, {**values, 'seconds_per_call': 'NaN'},
                    {**values, 'concurrency': True}):
            with self.assertRaises(ValueError):
                scenario_envelope(4, bad)


if __name__ == '__main__':
    unittest.main()
