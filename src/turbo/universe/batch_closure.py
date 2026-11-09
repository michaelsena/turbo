"""Reviewed batch release previews, explicit event translation and closure proofs.

Preparation is not activation. Persisted batch events become an activated family
closure only after the ordinary cumulative graph release independently replays.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from turbo.agents import batch_workflow as workflow
from turbo.agents.batch_authorization import canonical_bytes, utc_datetime
from turbo.agents.batch_output import _strict_json
from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT
from turbo.universe.family_pack_v2 import _verified_graph
from turbo.universe.graph import (RELATIONSHIP_TYPES, market_id_from_creation,
                                 market_version_id, project_graph, validate_event)

DIMENSIONS = {'buyer': 'buyer', 'job': 'job_to_be_done', 'delivery': 'delivery_model',
              'workforce': 'workforce_model', 'economics_risk': 'economics_risk',
              'acquisition_universe': 'acquisition_universe', 'ambient_ai_workflow': 'ambient_ai_workflow'}
OUTCOMES = {'activate', 'reviewed_no_graph_movement', 'retry_required'}
STATUSES = {'provisional', 'accepted_with_gaps'}


def _read(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ValueError('missing or symlink closure file')
    return _strict_json(path.read_bytes())


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contract(root: Path) -> dict[str, str]:
    return {name: _file_hash(root / name) for name in (
        'src/turbo/universe/batch_closure.py', 'src/turbo/universe/graph_release.py',
        'schemas/graph-release-config.schema.json')}


def _fields(value: Any, keys: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError('release configuration fields mismatch')


def _unique(rows: list[dict], key: str) -> dict[str, dict]:
    if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get(key), str) for row in rows):
        raise ValueError('invalid release ' + key)
    result = {row[key]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError('duplicate release ' + key)
    return result


def _source_data(input_root: Path, run_id: str) -> tuple[set[str], set[str], dict]:
    directory = input_root / 'data/runs' / run_id
    receipt = _read(directory / 'run-receipt.json')
    path = directory / 'multisource-reconciliation.json.gz'
    if receipt['run_id'] != run_id or _file_hash(path) != receipt['output_hashes']['multisource-reconciliation.json.gz']:
        raise ValueError('release source reconciliation mismatch')
    data = _strict_json(gzip.decompress(path.read_bytes()))
    return ({row['record_id'] for row in data['source_records']},
            {row['candidate_market_id'] for row in data['candidate_markets']}, receipt['output_hashes'])


def _base(stage: dict, *, input_root: Path | None = None) -> tuple[dict, dict, list[dict]]:
    input_root = Path(input_root) if input_root is not None else Path(stage['plan']['input_root'])
    pointer, receipt, projection = _verified_graph(root=input_root)
    for family in stage['context']['families']:
        if family['pack_metadata']['graph_projection_sha256'] != pointer['projection_sha256']:
            raise ValueError('family context does not bind release base graph')
    events = []
    for binding in receipt['activation_bindings']:
        path = input_root / binding['activation_dir'] / 'events.json'
        rows = _read(path)
        if canonical_sha256(rows) != binding['events_sha256']:
            raise ValueError('base activation events mismatch')
        events.extend(rows)
    if len({e['event_id'] for e in events}) != len(events):
        raise ValueError('duplicate base graph event')
    return pointer, projection, events


def _sources(family: dict, evidence_ids: list[str], subjects: list[str]) -> list[str]:
    refs = set(evidence_ids)
    subject_set = set(subjects)
    sources: set[str] = set()
    for row in family['evidence_catalog']:
        value = row['value']
        if not isinstance(value, dict):
            continue
        if row['evidence_id'] in refs or subject_set.intersection(row['subject_ids']):
            sources.update(value.get('source_record_ids', []))
            if row['json_pointer'].startswith('/source_record_cards/'):
                sources.add(value['record_id'])
    return sorted(sources)


def _compile(stage: dict, config: dict, *, root: Path, input_root: Path | None = None) -> dict:
    _fields(config, {'schema_version', 'recorded_at_utc', 'execution_commit', 'graph_base_sha256', 'families'})
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('invalid release schema version')
    utc_datetime(config['recorded_at_utc'])
    if not isinstance(config['execution_commit'], str) or not re.fullmatch('[0-9a-f]{40}', config['execution_commit']):
        raise ValueError('release requires a full execution commit')
    pointer, base, base_events = _base(stage, input_root=input_root)
    if config['graph_base_sha256'] != pointer['projection_sha256']:
        raise ValueError('release graph base hash mismatch')
    if utc_datetime(config['recorded_at_utc']) < utc_datetime(base['as_of']):
        raise ValueError('release predates its base graph')
    payload = stage['final_payload']
    expected = {f['family_id']: f for f in stage['context']['families']}
    decisions = _unique(config['families'], 'family_id')
    if set(decisions) != set(expected):
        raise ValueError('release must cover every family exactly once')
    adjudication_hash = stage['final_submission_sha256']
    seed = {'config': config, 'final_submission_sha256': adjudication_hash,
            'workflow_plan_sha256': stage['plan']['plan_sha256'], 'compiler_hashes': _contract(root)}
    activation_id = 'batch-activation-' + canonical_sha256(seed)[:20]
    existing_names = {m['canonical_name'].casefold().strip() for m in base['markets']}
    existing_identities = {m.get('identity_id') for m in base['mappings']}
    all_names: set[str] = set()
    seen_subjects: set[str] = set()
    events: list[dict] = []
    outcomes = []
    actors = stage['plan']['actors']
    for family in payload['families']:
        fid = family['family_id']; frozen = expected[fid]; decision = decisions[fid]
        _fields(decision, {'family_id', 'outcome', 'reason', 'proposals', 'mappings'})
        if decision['outcome'] not in OUTCOMES or not isinstance(decision['reason'], str) or not decision['reason'].strip():
            raise ValueError('invalid family closure decision')
        required = set(frozen['required_identity_ids']) | set(frozen['required_candidate_ids'])
        if seen_subjects & required:
            raise ValueError('cross-family duplicate required subject')
        seen_subjects.update(required)
        proposals = _unique(family['proposed_markets'], 'proposal_id')
        selected = _unique(decision['proposals'], 'proposal_id')
        mappings = {(r['identity_id'], r['proposal_id']): r for r in decision['mappings']}
        if len(mappings) != len(decision['mappings']):
            raise ValueError('duplicate requested identity mapping')
        identity_rows = {r['identity_id']: r for r in family['identity_dispositions']}
        expected_maps = {(r['identity_id'], p) for r in identity_rows.values() for p in r['proposal_ids']}
        if decision['outcome'] != 'activate':
            if selected or mappings:
                raise ValueError('nonactivation closure cannot contain events')
            if decision['outcome'] == 'reviewed_no_graph_movement' and (proposals or expected_maps):
                raise ValueError('proposed markets require activation or retry, not no-movement closure')
            outcomes.append({'family_id': fid, 'requested_outcome': decision['outcome'],
                             'proposal_ids': [], 'event_ids': [], 'reason': decision['reason']})
            continue
        if not proposals or set(selected) != set(proposals) or set(mappings) != expected_maps:
            raise ValueError('activation requires exact nonempty adjudicated proposals and mappings')
        gaps = {g['gap_id']: g for g in family['research_gaps']}
        family_events = []
        for pid, proposal in proposals.items():
            setting = selected[pid]
            _fields(setting, {'proposal_id', 'activation_status'})
            status = setting['activation_status']
            if status not in STATUSES:
                raise ValueError('proposal status must explicitly preserve provisional or accepted_with_gaps')
            linked = [r for r in family['identity_dispositions'] + family['candidate_dispositions'] if pid in r['proposal_ids']]
            if status != 'provisional' and any(r['disposition'].startswith('provisional_') for r in linked):
                raise ValueError('cannot silently promote a provisional adjudicated mapping')
            name = proposal['canonical_name'].casefold().strip()
            if name in existing_names or name in all_names or proposal['related_graph_market_ids']:
                raise ValueError('cross-family or existing-market conflict requires reconciliation before creation')
            all_names.add(name)
            event_id = f'{activation_id}:{len(events)+1:05d}:create'
            market_id = market_id_from_creation(event_id)
            gap_ids = sorted({r['gap_id'] for r in linked if r['gap_id'] is not None})
            source_ids = _sources(frozen, proposal['supporting_evidence_ids'] + proposal['counterevidence_ids'],
                                  [r.get('identity_id', r.get('candidate_market_id')) for r in linked])
            candidates = sorted(r['candidate_market_id'] for r in family['candidate_dispositions'] if pid in r['proposal_ids'])
            common = {'decision': 'accepted', 'recorded_at': config['recorded_at_utc'],
                      'input_source_record_ids': source_ids, 'input_market_ids': [],
                      'input_candidate_market_ids': candidates,
                      'operating_identity': {k: {'result': v['statement'], 'confidence': v['confidence']} for k,v in proposal['dimensions'].items()},
                      'supporting_record_ids': proposal['supporting_evidence_ids'], 'counterevidence_record_ids': proposal['counterevidence_ids'],
                      'alternatives_considered': ['Verified selective workflow; full evidence and findings retained in source workflow'],
                      'review': {'proposer': actors[stage['final_role']], 'independent_reviewer': actors['release_reviewer'], 'result': 'accepted'},
                      'supersedes': [], 'supersedes_market_version_ids': [],
                      'activation_status': status, 'research_gap_ids': gap_ids, 'research_gaps': [gaps[g] for g in gap_ids],
                      'family_id': fid, 'proposal_id': pid, 'workflow_plan_sha256': stage['plan']['plan_sha256'],
                      'source_final_submission_sha256': adjudication_hash, 'source_b3_proposal': copy.deepcopy(proposal)}
            version = {'market_id': market_id, 'market_version_id': market_version_id(event_id, market_id),
                       **{k: proposal[k] for k in ('canonical_name','definition','boundary','explicit_exclusions')},
                       **{target: proposal['dimensions'][key]['statement'] for key,target in DIMENSIONS.items()},
                       'parent_market_id': None, 'aliases': [], 'source_record_ids': source_ids, 'mapping_event_ids': [],
                       'candidate_market_ids': candidates,
                       'evidence_by_dimension': {k:v['evidence_label'] for k,v in proposal['dimensions'].items()},
                       'confidence_by_dimension': {k:v['confidence'] for k,v in proposal['dimensions'].items()},
                       'activation_status': status, 'research_gap_ids': gap_ids,
                       'source_b3_proposal': copy.deepcopy(proposal)}
            event = {**common, 'event_id': event_id, 'event_type':'create_market','output_market_ids':[market_id],
                     'relationship_type':None,'market_version':version}
            events.append(event); family_events.append(event_id)
            for identity_id, mapped_pid in sorted(mappings):
                if mapped_pid != pid: continue
                mapping = mappings[(identity_id,pid)]; disposition = identity_rows[identity_id]
                _fields(mapping, {'identity_id','proposal_id','relationship_type'})
                if mapping['relationship_type'] not in RELATIONSHIP_TYPES:
                    raise ValueError('explicit valid mapping relationship required')
                if identity_id in existing_identities:
                    raise ValueError('existing identity mapping conflicts; explicit reconciliation required')
                mapping_id = f'{activation_id}:{len(events)+1:05d}:map'
                event = {**copy.deepcopy(common), 'event_id': mapping_id,'event_type':'map','output_market_ids':[market_id],
                         'relationship_type':mapping['relationship_type'],'identity_id':identity_id,
                         'input_candidate_market_ids':[],
                         'input_source_record_ids':_sources(frozen,disposition['supporting_evidence_ids']+disposition['counterevidence_ids'],[identity_id]),
                         'supporting_record_ids':disposition['supporting_evidence_ids'],'counterevidence_record_ids':disposition['counterevidence_ids'],
                         'source_b3_disposition':copy.deepcopy(disposition)}
                events.append(event); family_events.append(mapping_id)
        outcomes.append({'family_id':fid,'requested_outcome':'activate','proposal_ids':list(proposals),
                         'event_ids':family_events,'reason':decision['reason']})
    for event in events:
        errors = validate_event(event)
        if errors: raise ValueError('invalid compiled batch event: '+ '; '.join(errors))
    source_ids, candidate_ids, hashes = _source_data(Path(input_root) if input_root is not None else Path(stage['plan']['input_root']),pointer['source_universe_run_id'])
    projection = project_graph(events,as_of=config['recorded_at_utc'],known_source_record_ids=source_ids,
                               known_candidate_market_ids=candidate_ids,source_hashes=hashes,
                               config_hash=canonical_sha256(config),code_hash=config['execution_commit'])
    cumulative = project_graph(base_events + events,as_of=config['recorded_at_utc'],
                               known_source_record_ids=source_ids,known_candidate_market_ids=candidate_ids,
                               source_hashes=hashes,config_hash=canonical_sha256(config),code_hash=config['execution_commit'])
    return {'schema_version':1,'kind':'batch_release_preview_v1',**seed,
            'graph_base_sha256':pointer['projection_sha256'],'source_universe_run_id':pointer['source_universe_run_id'],
            'activation_id':activation_id,'movements':events,'projection':projection,'cumulative_projection':cumulative,
            'base_event_ids':sorted(e['event_id'] for e in base_events),
            'base_events_sha256':canonical_sha256(sorted(base_events,key=lambda e:e['event_id'])),
            'family_lineage':copy.deepcopy(payload['families']),
            'closure_outcomes':outcomes,'candidate_policy':'family_local_nonmappings_remain_global_candidates',
            'model_invoked':False,'status':'planned_not_activated'}


def prepare_batch_release(directory: Path, release_config: dict, *, root: Path = ROOT,
                           input_root: Path | None = None, preparation_dirs=None) -> dict:
    stage = workflow.verified_stage(directory, input_root=input_root, preparation_dirs=preparation_dirs)
    preview = _compile(stage, copy.deepcopy(release_config), root=root, input_root=input_root)
    return workflow.bind_release_preview(directory, preview, input_root=input_root, preparation_dirs=preparation_dirs)


def _approved(directory: Path, *, root: Path, input_root: Path | None = None, preparation_dirs=None) -> tuple[dict, dict, dict]:
    stage = workflow.verified_stage(directory, input_root=input_root, preparation_dirs=preparation_dirs)
    wrapper = _read(Path(directory) / 'release-preview.json')
    preview = _compile(stage, wrapper['preview']['config'], root=root, input_root=input_root)
    if wrapper['preview'] != preview or wrapper['preview_sha256'] != workflow._hash(preview):
        raise ValueError('release preview cannot replay')
    if wrapper['plan_sha256'] != stage['plan']['plan_sha256'] or wrapper['final_submission_sha256'] != stage['final_submission_sha256']:
        raise ValueError('release preview workflow binding mismatch')
    reviewer = stage['submissions'].get('release_reviewer')
    if (reviewer is None or reviewer['document']['verdict'] != 'approve'
            or reviewer['document']['approved_plan_sha256'] != wrapper['preview_sha256']):
        raise ValueError('exact independent release preview approval required')
    return stage, wrapper, reviewer


def _activation(directory: Path, *, root: Path, input_root: Path | None = None, preparation_dirs=None) -> dict:
    stage, wrapper, reviewer = _approved(directory,root=root,input_root=input_root,preparation_dirs=preparation_dirs)
    preview = wrapper['preview']
    if not preview['movements']: raise ValueError('no graph movement: use reviewed closure, not activation')
    receipt = {'schema_version':1,'activation_kind':'batch','activation_id':preview['activation_id'],
               'activation_config_sha256':canonical_sha256({'workflow_dir':str(Path(directory).resolve())}),
               'events_sha256':canonical_sha256(preview['movements']),
               'projection_sha256':canonical_sha256(preview['projection']),
               'source_universe_run_id':preview['source_universe_run_id'],
               'required_base_event_ids':preview['base_event_ids'],'required_base_events_sha256':preview['base_events_sha256'],
               'preview_sha256':wrapper['preview_sha256'],'release_review_sha256':reviewer['submission_sha256'],
               'workflow_plan_sha256':stage['plan']['plan_sha256'],'model_invoked':False,
               'status':'persisted_approved_batch_events'}
    return {'receipt':receipt,'events':preview['movements'],'projection':preview['projection']}


def _publish(destination: Path, files: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists() or destination.is_symlink(): raise FileExistsError(destination)
    with tempfile.TemporaryDirectory(prefix='.batch-closure-',dir=destination.parent) as tmp:
        temp = Path(tmp)
        for name,value in files.items():
            with (temp/name).open('xb') as handle:
                handle.write(canonical_bytes(value));handle.flush();os.fsync(handle.fileno())
        fd=os.open(temp,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
        temp.rename(destination)
        fd=os.open(destination.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)


def persist_batch_activation(directory: Path, *, output_root: Path, root: Path = ROOT,
                           input_root: Path | None = None, preparation_dirs=None) -> dict:
    """Explicit publication of approved events, not a cumulative graph activation."""
    from turbo.universe.graph_release import _git_commit_exists, _git_head, _git_worktree_clean
    stage, wrapper, _ = _approved(directory,root=root,input_root=input_root,preparation_dirs=preparation_dirs)
    commit=wrapper['preview']['config']['execution_commit']
    if not _git_worktree_clean(root) or _git_head(root)!=commit or not _git_commit_exists(root,commit):
        raise ValueError('event persistence requires the exact clean reviewed execution commit')
    value=_activation(directory,root=root,input_root=input_root,preparation_dirs=preparation_dirs);receipt=value['receipt']
    destination=Path(output_root)/receipt['activation_id']
    _publish(destination,{'events.json':value['events'],'projection.json':value['projection'],
                          'activation-receipt.json':receipt,'activation-config.json':{'workflow_dir':str(Path(directory).resolve())}})
    return {'activation_dir':str(destination),**receipt}


def validate_batch_activation(activation_dir: Path, activation_config_path: Path, *, root: Path = ROOT,
                           input_root: Path | None = None, preparation_dirs=None) -> dict:
    try:
        config=_read(activation_config_path);_fields(config,{'workflow_dir'})
        value=_activation(Path(config['workflow_dir']),root=root,input_root=input_root,preparation_dirs=preparation_dirs)
        if Path(activation_dir).name!=value['receipt']['activation_id']:raise ValueError('activation directory identity mismatch')
        for name,key in [('events.json','events'),('projection.json','projection'),('activation-receipt.json','receipt')]:
            if _read(Path(activation_dir)/name)!=value[key]:raise ValueError('batch activation '+name+' mismatch')
        return {'valid':True,'errors':[],**value['receipt']}
    except (OSError,ValueError,KeyError,TypeError) as error:
        return {'valid':False,'errors':[str(error)]}


def _closure_proof(directory: Path, *, graph_release_dir: Path | None = None,
                           graph_release_config: Path | None = None, root: Path = ROOT,
                           input_root: Path | None = None, preparation_dirs=None) -> dict:
    """Issue closure only after exact approved events appear in a replayed release."""
    _,wrapper,reviewer=_approved(directory,root=root,input_root=input_root,preparation_dirs=preparation_dirs);preview=wrapper['preview']
    graph_binding=None
    if preview['movements']:
        if graph_release_dir is None or graph_release_config is None:raise ValueError('persisted cumulative graph release required')
        from turbo.universe.graph_release import validate_graph_release
        checked=validate_graph_release(graph_release_dir,graph_release_config,root=root,input_root=input_root,preparation_dirs=preparation_dirs)
        if not checked['valid']:raise ValueError('cumulative graph release cannot replay')
        receipt=_read(Path(graph_release_dir)/'graph-receipt.json')
        bindings=[b for b in receipt['activation_bindings'] if b['activation_id']==preview['activation_id']]
        if len(bindings)!=1 or bindings[0]['events_sha256']!=canonical_sha256(preview['movements']):
            raise ValueError('release does not contain exact approved batch events')
        projection=_read(Path(graph_release_dir)/'projection.json')
        if not set(e['event_id'] for e in preview['movements'])<=set(projection['active_event_ids']):
            raise ValueError('approved batch events are not active in persisted release')
        graph_binding={'release_id':receipt['release_id'],'receipt_sha256':canonical_sha256(receipt),
                       'projection_sha256':receipt['projection_sha256']}
    outcomes=[{**row,'status':'activated_events' if row['requested_outcome']=='activate' else row['requested_outcome']}
              for row in preview['closure_outcomes']]
    proof={'schema_version':1,'preview_sha256':wrapper['preview_sha256'],
           'release_review_sha256':reviewer['submission_sha256'],'graph_release':graph_binding,
           'families':outcomes,'family_lineage':preview['family_lineage'],'model_invoked':False}
    return proof


def finalize_batch_closure(directory: Path, *, output_root: Path, graph_release_dir: Path | None = None,
                           graph_release_config: Path | None = None, root: Path = ROOT,
                           input_root: Path | None = None, preparation_dirs=None) -> dict:
    proof = _closure_proof(directory, graph_release_dir=graph_release_dir,
                           graph_release_config=graph_release_config, root=root,
                               input_root=input_root, preparation_dirs=preparation_dirs)
    closure_id = 'batch-closure-' + canonical_sha256(proof)[:20]
    destination = Path(output_root) / closure_id
    _publish(destination, {'closure.json': proof})
    return {'closure_id': closure_id, 'closure_dir': str(destination), **proof}


def validate_batch_closure(closure_dir: Path, directory: Path, *,
                           graph_release_dir: Path | None = None,
                           graph_release_config: Path | None = None, root: Path = ROOT,
                           input_root: Path | None = None, preparation_dirs=None) -> dict:
    try:
        proof = _closure_proof(directory, graph_release_dir=graph_release_dir,
                               graph_release_config=graph_release_config, root=root,
                               input_root=input_root, preparation_dirs=preparation_dirs)
        if (Path(closure_dir).name != 'batch-closure-' + canonical_sha256(proof)[:20]
                or _read(Path(closure_dir) / 'closure.json') != proof):
            raise ValueError('batch closure cannot replay')
        return {'valid': True, 'errors': []}
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {'valid': False, 'errors': [str(error)]}
