"""Read-only schedule coverage from canonically published batch closure bindings.

This is artifact/binding verification, not a replacement for research/closure replay.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
from turbo.agents.batch_workflow import _hash as workflow_hash
from turbo.agents.batch_output import _strict_json
from turbo.agents.boundary_harness import canonical_sha256
from turbo.agents.batch_provider import role_schema
from turbo.system_context import _source_context
from turbo.universe.family_pack_v2 import _verified_graph, _verified_schedule


def _path(root, name):
    value = Path(name)
    if value.is_absolute() or '..' in value.parts or not value.parts:
        raise ValueError('artifact path must be repository relative')
    result = root / value
    if any(p.is_symlink() for p in (result, *result.parents)):
        raise ValueError('symlink artifact path')
    return result


def _read(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('missing or symlink artifact')
    return _strict_json(path.read_bytes())


def _unique(rows, key):
    result = {row[key]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError('duplicate ' + key)
    return result


def _subject_set(rows, key):
    return set(_unique(rows, key))


def _published_closure(root, manifest_path, schedule, families, current_receipt, current_projection):
    manifest = _read(_path(root, manifest_path))
    if manifest.get('schema_version') != 1:
        raise ValueError('unsupported publication manifest')
    hashes = manifest['files']
    # A historical manifest may bind the then-current mutable locator. Verify the
    # current locator independently, and verify this manifest's immutable release.
    for name, expected in hashes.items():
        if name == 'data/generated/latest-graph.json':
            continue
        path = _path(root, name)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('manifest artifact hash mismatch: ' + name)

    def bound(name):
        if name not in hashes:
            raise ValueError('required artifact is absent from manifest: ' + name)
        return _read(_path(root, name))

    workflow = manifest['workflow_dir']
    plan = bound(workflow + '/plan.json')
    context = bound(workflow + '/context.json')
    wrapper = bound(workflow + '/release-preview.json')
    reviewer = bound(workflow + '/release_reviewer.json')
    if workflow_hash({k: v for k, v in plan.items() if k != 'plan_sha256'}) != plan['plan_sha256']:
        raise ValueError('workflow plan hash mismatch')
    if workflow_hash({k: v for k, v in reviewer.items() if k != 'submission_sha256'}) != reviewer['submission_sha256']:
        raise ValueError('review envelope hash mismatch')
    try:
        Draft202012Validator(role_schema('release_reviewer', input_root=root)).validate(reviewer['document'])
    except ValidationError as error:
        raise ValueError('invalid review schema') from error
    review = reviewer['document']; preview = wrapper['preview']
    if (reviewer['role'] != 'release_reviewer' or reviewer['plan_sha256'] != plan['plan_sha256']
            or reviewer['actor_id'] != plan['actors']['release_reviewer']
            or review['verdict'] != 'approve' or any(v != 'pass' for v in review['checks'].values())
            or any(f['status'] != 'resolved' for f in review['findings'])
            or review['approved_plan_sha256'] != wrapper['preview_sha256']
            or workflow_hash(preview) != wrapper['preview_sha256']
            or wrapper['plan_sha256'] != plan['plan_sha256']
            or preview['workflow_plan_sha256'] != plan['plan_sha256']
            or preview['source_universe_run_id'] != schedule['source_run_id']):
        raise ValueError('exact approved preview binding mismatch')
    final_submissions = []
    for role, expected in review['input_hashes'].items():
        submission = bound(workflow + '/' + role + '.json')
        if (workflow_hash({k: v for k, v in submission.items() if k != 'submission_sha256'}) != expected
                or submission['submission_sha256'] != expected or submission['plan_sha256'] != plan['plan_sha256']):
            raise ValueError('upstream submission binding mismatch')
        if expected == wrapper['final_submission_sha256'] and role in ('primary', 'adjudicator'):
            final_submissions.append(submission)
    if (len(final_submissions) != 1 or preview['final_submission_sha256'] != wrapper['final_submission_sha256']
            or preview['family_lineage'] != final_submissions[0]['document']['payload']['families']):
        raise ValueError('preview lineage does not bind final research submission')
    if (context['context_sha256'] != plan['context_sha256']
            or canonical_sha256({k: v for k, v in context.items() if k != 'context_sha256'}) != context['context_sha256']):
        raise ValueError('workflow context hash mismatch')
    _unique(context['families'], 'family_id')
    for family in context['families']:
        scheduled = families[family['family_id']]; meta = family['pack_metadata']
        if (meta['partition_id'] != schedule['partition_id'] or meta['source_run_id'] != schedule['source_run_id']
                or meta['schedule_receipt_sha256'] != schedule['receipt_sha256']
                or len(family['required_identity_ids']) != len(set(family['required_identity_ids']))
                or len(family['required_candidate_ids']) != len(set(family['required_candidate_ids']))
                or set(family['required_identity_ids']) != set(scheduled['required_disposition_identity_ids'])
                or set(family['required_candidate_ids']) != set(scheduled['required_prior_candidate_ids'])):
            raise ValueError('closure context does not match selected schedule')
    closure = bound(manifest['closure_dir'] + '/closure.json')
    if (Path(manifest['closure_dir']).name != 'batch-closure-' + canonical_sha256(closure)[:20]
            or closure['preview_sha256'] != wrapper['preview_sha256']
            or closure['release_review_sha256'] != reviewer['submission_sha256']
            or closure['model_invoked'] is not False
            or closure['family_lineage'] != preview['family_lineage']):
        raise ValueError('closure binding mismatch')
    expected = [{**f, 'status': 'activated_events' if f['requested_outcome'] == 'activate' else f['requested_outcome']}
                for f in preview['closure_outcomes']]
    if closure['families'] != expected:
        raise ValueError('closure outcome differs from reviewed preview')
    if closure['graph_release'] is None or not preview['movements']:
        raise ValueError('unanchored no-movement closure requires full replay; unsupported by binding-only report')
    receipt = bound(manifest['release_dir'] + '/graph-receipt.json')
    projection = bound(manifest['release_dir'] + '/projection.json')
    config = bound(manifest['graph_config'])
    if (receipt['source_universe_run_id'] != schedule['source_run_id']
            or canonical_sha256(config) != receipt['config_sha256']
            or canonical_sha256(projection) != receipt['projection_sha256']
            or closure['graph_release'] != {'release_id': receipt['release_id'],
                'receipt_sha256': canonical_sha256(receipt), 'projection_sha256': receipt['projection_sha256']}):
        raise ValueError('closure cumulative release binding mismatch')
    aid = preview['activation_id']
    old = _unique(receipt['activation_bindings'], 'activation_id')[aid]
    current = _unique(current_receipt['activation_bindings'], 'activation_id').get(aid)
    if old != current:
        raise ValueError('reviewed activation is absent or changed in current graph')
    activation = bound(old['activation_dir'] + '/activation-receipt.json')
    events = bound(old['activation_dir'] + '/events.json')
    activated = bound(old['activation_dir'] + '/projection.json')
    if (events != preview['movements'] or activated != preview['projection']
            or any(e.get('source_final_submission_sha256') != wrapper['final_submission_sha256'] for e in events)
            or canonical_sha256(events) != old['events_sha256']
            or activation['preview_sha256'] != wrapper['preview_sha256']
            or activation['release_review_sha256'] != reviewer['submission_sha256']
            or activation['workflow_plan_sha256'] != plan['plan_sha256']
            or not set(e['event_id'] for e in events) <= set(current_projection['active_event_ids'])):
        raise ValueError('approved activation/event binding mismatch')
    for field in ('markets', 'mappings'):
        if any(row not in current_projection[field] for row in activated[field]):
            raise ValueError('reviewed row changed in current graph')
    lineage = _unique(closure['family_lineage'], 'family_id')
    outcomes = _unique(closure['families'], 'family_id')
    if set(lineage) != set(outcomes) or set(outcomes) != {f['family_id'] for f in context['families']}:
        raise ValueError('closure family coverage mismatch')
    for fid, row in lineage.items():
        expected = families[fid]
        if (_subject_set(row['identity_dispositions'], 'identity_id') != set(expected['required_disposition_identity_ids'])
                or _subject_set(row['candidate_dispositions'], 'candidate_market_id') != set(expected['required_prior_candidate_ids'])):
            raise ValueError('closure subject coverage mismatch')
    return closure, aid


def _overlay(families, closures):
    outcomes = {}; gaps = {}
    for closure in closures:
        lineage = _unique(closure['family_lineage'], 'family_id')
        for row in closure['families']:
            fid = row['family_id']
            if fid not in families or not families[fid]['schedulable']:
                raise ValueError('closure family is not in scheduled workload')
            value = {'outcome': row, 'lineage': lineage[fid]}
            if fid in outcomes and outcomes[fid] != value:
                raise ValueError('conflicting closures for family ' + fid)
            outcomes[fid] = value
            for gap in lineage[fid]['research_gaps']:
                gid = gap['gap_id']
                if gid in gaps and gaps[gid] != gap:
                    raise ValueError('conflicting research gap')
                gaps[gid] = gap
    completed = {fid for fid, v in outcomes.items() if v['outcome']['status'] in ('activated_events', 'reviewed_no_graph_movement')}
    retry = {fid for fid, v in outcomes.items() if v['outcome']['status'] == 'retry_required'}
    return completed, retry, gaps


def scenario_envelope(batch_count, parameters):
    """Explicit assumption scenario only; never a measured cost forecast."""
    fields = {'escalation_fraction', 'seconds_per_call', 'concurrency', 'cost_units_per_call', 'cost_unit'}
    if set(parameters) != fields or type(parameters['concurrency']) is not int or parameters['concurrency'] not in (1, 2):
        raise ValueError('scenario requires exact assumptions and concurrency 1 or 2')
    values = {}
    for key in ('escalation_fraction', 'seconds_per_call', 'cost_units_per_call'):
        try: value = Decimal(str(parameters[key]))
        except InvalidOperation as e: raise ValueError('invalid scenario decimal') from e
        if not value.is_finite() or value < 0: raise ValueError('invalid scenario decimal')
        values[key] = value
    if values['escalation_fraction'] > 1 or not isinstance(parameters['cost_unit'], str) or not parameters['cost_unit'].strip():
        raise ValueError('invalid scenario fraction or unit')
    calls = Decimal(batch_count) * (3 + 3 * values['escalation_fraction'])
    return {'classification': 'assumption_scenario_not_measured_forecast', 'assumptions': parameters,
            'expected_calls': str(calls), 'idealized_seconds': str(calls * values['seconds_per_call'] / parameters['concurrency']),
            'expected_cost_units': str(calls * values['cost_units_per_call']),
            'excludes': ['preparation/publication time', 'failures and retries', 'variable role sizes and latency', 'representation quality qualification']}


def _validate_obligations(families, batches):
    for family in families.values():
        for count, field in [('required_identities', 'required_disposition_identity_ids'),
                             ('required_candidates', 'required_prior_candidate_ids')]:
            subjects = family[field]
            if len(subjects) != len(set(subjects)) or family['counts'][count] != len(subjects):
                raise ValueError('schedule subject count mismatch')
    _unique(batches, 'batch_id')
    for batch in batches:
        for field in ('required_identities', 'required_candidates'):
            if batch[field] != sum(families[fid]['counts'][field] for fid in batch['family_ids']):
                raise ValueError('batch subject count mismatch')


def build_report(*, root: Path, publication_manifests=(), scenario=None):
    root = root.resolve(); source = _source_context(root)
    schedule, schedule_receipt, artifacts = _verified_schedule(root=root)
    pointer, graph_receipt, projection = _verified_graph(root=root)
    if source['run_id'] != schedule['source_run_id'] or source['run_id'] != pointer['source_universe_run_id']:
        raise ValueError('source/schedule/graph mismatch')
    families = _unique(artifacts['family-manifest.json.gz']['families'], 'family_id')
    batches = artifacts['batch-manifest.json']['batches']
    queued = {fid: f for fid, f in families.items() if f['schedulable']}
    _validate_obligations(queued, batches)
    assigned = [fid for b in batches for fid in b['family_ids']]
    if len(assigned) != len(set(assigned)) or set(assigned) != set(queued):
        raise ValueError('batch assignment coverage mismatch')
    closures = []; seen_activations = set()
    for manifest in publication_manifests:
        closure, activation = _published_closure(root, manifest, schedule, families, graph_receipt, projection)
        closures.append(closure); seen_activations.add(activation)
    if seen_activations != {b['activation_id'] for b in graph_receipt['activation_bindings'] if b.get('kind') == 'batch'}:
        raise ValueError('publication manifests do not cover current batch activations')
    completed, retry, gaps = _overlay(families, closures)
    remaining = {fid: f for fid, f in queued.items() if fid not in completed}
    def totals(rows):
        return {'families': len(rows), 'required_identities': sum(f['counts']['required_identities'] for f in rows.values()),
                'required_candidates': sum(f['counts']['required_candidates'] for f in rows.values())}
    remaining_batches = [b for b in batches if set(b['family_ids']) & set(remaining)]
    market_gaps = {gid for row in projection['markets'] for gid in row.get('research_gap_ids', [])}
    histogram = {label: sum(lo <= sum(queued[f]['counts']['required_identities'] for f in b['family_ids']) <= hi for b in batches)
                 for label, lo, hi in [('0-32', 0, 32), ('33-64', 33, 64), ('65-128', 65, 128), ('129+', 129, 10**9)]}
    result = {'schema_version': 1, 'status': 'offline_no_calls_no_authority',
              'validation_scope': 'published_artifact_binding_verification_not_fresh_research_replay',
              'source_run_id': source['run_id'], 'partition_id': schedule['partition_id'],
              'graph_release_id': pointer['release_id'], 'schedule_receipt_sha256': schedule['receipt_sha256'],
              'graph_projection_sha256': pointer['projection_sha256'],
              'scheduled': {**totals(queued), 'batches': len(batches)},
              'completed_batch_closure_work': totals({fid: queued[fid] for fid in completed}),
              'remaining': {**totals(remaining), 'batches_with_remaining_work': len(remaining_batches)},
              'completed_family_ids': sorted(completed), 'retry_required_family_ids': sorted(retry),
              'scheduled_family_kinds': dict(sorted(Counter(f['family_kind'] for f in queued.values()).items())),
              'batch_required_identity_histogram': histogram,
              'retained_gaps': {'market_linked_ids': sorted(market_gaps), 'batch_closure_gap_ids': sorted(gaps),
                                'all_distinct_ids': sorted(market_gaps | set(gaps)), 'resolved_by_completion': False},
              'unmeasured': ['request bytes/tokens by workload stratum', 'role outputs and review amplification',
                             'escalation/failure rates', 'representative per-role latency', 'full-universe cost and duration'],
              'scenario': None}
    if scenario is not None: result['scenario'] = scenario_envelope(len(remaining_batches), scenario)
    return result
