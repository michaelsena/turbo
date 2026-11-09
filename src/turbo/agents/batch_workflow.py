"""Offline Issue15 primary/selective-verification workflow; no dispatch or spend claims.

A trusted coordinator supplies genuinely independent actors. Hashes prove local
artifact consistency, not cryptographic actor identity or filesystem isolation.
"""
from __future__ import annotations
from contextlib import contextmanager
import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from typing import Any
from jsonschema import Draft202012Validator
from turbo.agents.batch_output import build_batch_context, _strict_json, _validate_against_context
from turbo.pipeline_paths import ROOT

ROLES = ('primary', 'verifier', 'escalation_a', 'escalation_b', 'adjudicator', 'release_reviewer')
CANARY_POLICY = {'version': 'issue15-canary-v1', 'weak_confidence_threshold': 0.7,
                 'qa_fraction': 0.1, 'qa_minimum_per_family': 1,
                 'all_proposals': True, 'all_linked_dispositions': True,
                 'all_unresolved_provisional': True, 'all_counterevidence': True,
                 'explicit_conflicts_and_competing_mappings': True}
SCHEMA = 'schemas/batch-workflow-submission.schema.json'
PROMPT = 'prompts/universe/batch-workflow-v1.md'
MAX_DOCUMENT_BYTES = 4_000_000


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def _hash(value: Any) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _read(path: Path, limit: int = MAX_DOCUMENT_BYTES) -> Any:
    if path.is_symlink() or not path.is_file(): raise ValueError('missing or symlink workflow file: ' + path.name)
    with path.open('rb') as stream: raw = stream.read(limit + 1)
    if len(raw) > limit: raise ValueError('workflow file exceeds bound')
    return _strict_json(raw)


def _sync(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def _write(path: Path, value: Any) -> None:
    temp = path.with_name(path.name + '.pending')
    with temp.open('xb') as stream:
        stream.write(_bytes(value) + b'\n'); stream.flush(); os.fsync(stream.fileno())
    os.link(temp, path); temp.unlink(); _sync(path.parent)


def _contract() -> dict:
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (SCHEMA, PROMPT, 'src/turbo/agents/batch_workflow.py')}


def _git(root: Path, ref: str) -> str:
    return subprocess.run(['git', '-C', str(root), 'rev-parse', ref], check=True,
                          text=True, capture_output=True).stdout.strip()


@contextmanager
def _locked(directory: Path):
    directory = Path(directory).absolute()
    if directory.resolve() != directory or not directory.is_dir(): raise ValueError('invalid workflow directory')
    lock = directory / '.lock'
    if lock.is_symlink() or not lock.is_file(): raise ValueError('missing workflow lock')
    with lock.open('rb') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield directory


def _subjects(context: dict) -> list[tuple[str, str, str]]:
    return [(f['family_id'], kind, subject) for f in context['families']
            for kind, key in (('identity', 'required_identity_ids'), ('candidate', 'required_candidate_ids'))
            for subject in f[key]]


def _qa(context: dict) -> list[list[str]]:
    result = []
    for family in context['families']:
        candidates = [s for s in _subjects(context) if s[0] == family['family_id']]
        count = min(len(candidates), max(1, math.ceil(len(candidates) / 10)))
        result.extend(sorted(candidates, key=lambda s: _hash([context['context_sha256'], *s]))[:count])
    return [list(s) for s in result]


def initialize_workflow(directory: Path, preparation_dirs, *, input_root: Path, request_id: str,
                        invocation_id: str, actors: dict[str, str], policy: dict | None = None) -> dict:
    if set(actors) != set(ROLES) or any(not isinstance(v, str) or not v.strip() for v in actors.values()):
        raise ValueError('exactly six nonempty role actors required')
    if len(set(actors.values())) != len(ROLES): raise ValueError('each role requires a distinct actor')
    if policy is not None and _bytes(policy) != _bytes(CANARY_POLICY): raise ValueError('unsupported selection policy')
    root = Path(input_root).resolve(); paths = [str(Path(p).resolve()) for p in preparation_dirs]
    context = build_batch_context(paths, request_id=request_id, invocation_id=invocation_id, root=root)
    plan = {'schema_version': 1, 'workflow_kind': 'issue15-primary-selective-v1',
            'input_root': str(root), 'input_commit': _git(root, 'HEAD'), 'input_tree': _git(root, 'HEAD^{tree}'),
            'preparation_dirs': paths, 'request_id': request_id, 'invocation_id': invocation_id,
            'actors': copy.deepcopy(actors), 'context_sha256': context['context_sha256'],
            'policy': copy.deepcopy(CANARY_POLICY), 'qa_targets': _qa(context), 'contract_hashes': _contract(),
            'execution_channel': 'offline_role_submission', 'spend_telemetry': 'not_available_not_claimed'}
    plan['plan_sha256'] = _hash(plan)
    directory = Path(directory).absolute()
    if directory.resolve() != directory: raise ValueError('symlink workflow path')
    directory.mkdir(mode=0o700); _sync(directory.parent)
    (directory / '.lock').touch(mode=0o600)
    _write(directory / 'context.json', context); _write(directory / 'plan.json', plan)
    return copy.deepcopy(plan)


def _invocation(plan: dict, role: str) -> str:
    return 'workflow-role:' + _hash([plan['plan_sha256'], role])[:24]


def _material(previous: dict) -> bool:
    return any(a['verdict'] == 'material_disagreement'
               for a in previous.get('verifier', {}).get('document', {}).get('assessments', []))


def _final_role(previous: dict) -> str:
    if 'verifier' not in previous: raise ValueError('selective verification required')
    if _material(previous):
        if 'adjudicator' not in previous: raise ValueError('material disagreement requires blind escalation and adjudication')
        return 'adjudicator'
    return 'primary'


def _dependencies(role: str, previous: dict) -> tuple[str, ...]:
    if role == 'primary': return ()
    if role == 'verifier': return ('primary',)
    if role in ('escalation_a', 'escalation_b', 'adjudicator'):
        if 'verifier' not in previous or not _material(previous): raise ValueError('escalation requires material disagreement')
        return ROLES[:4] if role == 'adjudicator' else ('primary', 'verifier')
    _final_role(previous)
    return ROLES[:5] if _material(previous) else ROLES[:2]


def _targets(context: dict, primary: dict, plan: dict) -> list[dict]:
    reasons: dict[tuple[str, str, str], set[str]] = {}
    def add(key, reason): reasons.setdefault(tuple(key), set()).add(reason)
    for target in plan['qa_targets']: add(target, 'preregistered_qa')
    for family in context['families']:
        mappings: dict[str, set[str]] = {}
        for item in family['evidence_catalog']:
            value = item['value']
            if not isinstance(value, dict): continue
            flagged = any(value.get(k) is True for k in ('ambiguous', 'conflict', 'contradiction', 'contradictory'))
            flagged = flagged or value.get('status') in ('conflict', 'contradiction', 'ambiguous', 'contested')
            for f, kind, subject in _subjects(context):
                if f != family['family_id'] or subject not in item['subject_ids']: continue
                if flagged: add((f, kind, subject), 'explicit_frozen_conflict')
                if item['json_pointer'].startswith('/graph_context/mappings/'):
                    markets = value.get('output_market_ids', [])
                    market = value.get('market_id', value.get('canonical_market_id'))
                    if isinstance(market, str): markets = [*markets, market]
                    if isinstance(markets, list):
                        mappings.setdefault(subject, set()).update(m for m in markets if isinstance(m, str))
        for f, kind, subject in _subjects(context):
            if f == family['family_id'] and len(mappings.get(subject, set())) > 1:
                add((f, kind, subject), 'competing_canonical_mappings')
    names: dict[str, set[str]] = {}
    for family in primary['families']:
        for proposal in family['proposed_markets']:
            name = ' '.join(proposal['canonical_name'].casefold().split())
            names.setdefault(name, set()).add(family['family_id'])
    for family in primary['families']:
        fid = family['family_id']
        for proposal in family['proposed_markets']:
            key = (fid, 'proposal', proposal['proposal_id']); add(key, 'all_proposals')
            if len(names[' '.join(proposal['canonical_name'].casefold().split())]) > 1: add(key, 'cross_family_name_conflict')
            if any(d['confidence'] < 0.7 for d in proposal['dimensions'].values()): add(key, 'weak_confidence')
            if proposal['counterevidence_ids'] or proposal['related_graph_market_ids']: add(key, 'conflict_risk')
        for kind, field, idfield in (('identity', 'identity_dispositions', 'identity_id'),
                                     ('candidate', 'candidate_dispositions', 'candidate_market_id')):
            for item in family[field]:
                key = (fid, kind, item[idfield])
                if item['proposal_ids']: add(key, 'graph_movement_candidate')
                if len(item['proposal_ids']) > 1: add(key, 'multiple_proposal_boundary')
                if item['confidence'] < 0.7: add(key, 'weak_confidence')
                if item['disposition'] == 'unresolved' or item['disposition'].startswith('provisional_'): add(key, 'unresolved_or_provisional')
                if item['counterevidence_ids']: add(key, 'counterevidence_conflict')
    return [{'family_id': f, 'target_kind': k, 'target_id': s, 'reasons': sorted(why)}
            for (f, k, s), why in sorted(reasons.items())]


def _validate(envelope: dict, role: str, plan: dict, context: dict, previous: dict, *, input_root: Path | None = None) -> None:
    if set(envelope) != {'role', 'actor_id', 'role_invocation_id', 'plan_sha256', 'document', 'submission_sha256'}:
        raise ValueError('invalid role envelope')
    if (envelope['role'] != role or envelope['actor_id'] != plan['actors'][role]
        or envelope['plan_sha256'] != plan['plan_sha256'] or envelope['role_invocation_id'] != _invocation(plan, role)):
        raise ValueError('role actor invocation or plan mismatch')
    if envelope['submission_sha256'] != _hash({k: v for k, v in envelope.items() if k != 'submission_sha256'}):
        raise ValueError('submission hash mismatch')
    document = envelope['document']; dependencies = _dependencies(role, previous)
    if any(r not in previous for r in dependencies): raise ValueError('mandatory prior stage missing')
    schema = json.loads((ROOT / SCHEMA).read_text())['$defs']
    definition = schema['research' if role in ('primary', 'escalation_a', 'escalation_b') else role]
    errors = list(Draft202012Validator(definition).iter_errors(document))
    if errors: raise ValueError('invalid role document: ' + errors[0].message)
    if role in ('verifier', 'adjudicator', 'release_reviewer'):
        if document['input_hashes'] != {r: previous[r]['submission_sha256'] for r in dependencies}:
            raise ValueError('upstream submission hashes mismatch')
    if 'payload' in document:
        errors = _validate_against_context(document['payload'], context, root=Path(input_root) if input_root is not None else Path(plan['input_root']))
        if errors: raise ValueError('invalid B3 payload: ' + '; '.join(errors))
    if role == 'verifier':
        targets = _targets(context, previous['primary']['document']['payload'], plan)
        expected = {(t['family_id'], t['target_kind'], t['target_id']) for t in targets}
        actual = [(a['family_id'], a['target_kind'], a['target_id']) for a in document['assessments']]
        if len(actual) != len(set(actual)) or set(actual) != expected: raise ValueError('exact selected-target verification required')
        families = {f['family_id']: f for f in context['families']}
        proposals = {(f['family_id'], p['proposal_id']): p for f in previous['primary']['document']['payload']['families'] for p in f['proposed_markets']}
        for a in document['assessments']:
            catalog = {e['evidence_id']: e for e in families[a['family_id']]['evidence_catalog']}
            refs = set(a['supporting_evidence_ids'])
            if not refs <= catalog.keys(): raise ValueError('unknown or cross-family verification evidence')
            if a['target_kind'] == 'proposal':
                anchors = set(proposals[(a['family_id'], a['target_id'])]['supporting_evidence_ids'])
            else: anchors = {eid for eid, e in catalog.items() if a['target_id'] in e['subject_ids']}
            if not refs & anchors: raise ValueError('verification needs target-owned evidence anchor')
    if role == 'adjudicator':
        actual = [(c['family_id'], c['subject_kind'], c['subject_id']) for c in document['comparisons']]
        if len(actual) != len(set(actual)) or set(actual) != set(_subjects(context)): raise ValueError('compare every required subject once')
        payloads = [document['payload']] + [previous[r]['document']['payload'] for r in ('primary', 'escalation_a', 'escalation_b')]
        expected = {(f['family_id'], p['proposal_id']) for payload in payloads for f in payload['families'] for p in f['proposed_markets']}
        actual = [(p['family_id'], p['proposal_id']) for p in document['proposal_comparisons']]
        if len(actual) != len(set(actual)) or set(actual) != expected: raise ValueError('compare all original and final proposals once')
    if role == 'release_reviewer':
        findings = document['findings']
        if len({f['finding_id'] for f in findings}) != len(findings): raise ValueError('duplicate review finding')
        if document['verdict'] == 'approve' and (any(v != 'pass' for v in document['checks'].values()) or any(f['status'] != 'resolved' for f in findings)):
            raise ValueError('approval requires all checks pass and zero unresolved review findings')


def _preview(directory: Path, plan: dict, previous: dict) -> dict:
    bound = _read(directory / 'release-preview.json', 10_000_000); final = _final_role(previous)
    if set(bound) != {'plan_sha256', 'final_submission_sha256', 'preview', 'preview_sha256'}:
        raise ValueError('invalid preview envelope')
    if (bound['plan_sha256'] != plan['plan_sha256'] or bound['final_submission_sha256'] != previous[final]['submission_sha256']
        or bound['preview_sha256'] != _hash(bound['preview'])): raise ValueError('release preview binding mismatch')
    return bound


def _load(directory: Path, *, input_root: Path | None = None, preparation_dirs=None) -> tuple[dict, dict, dict]:
    plan = _read(directory / 'plan.json')
    if plan.get('plan_sha256') != _hash({k: v for k, v in plan.items() if k != 'plan_sha256'}): raise ValueError('plan hash mismatch')
    if plan['contract_hashes'] != _contract() or _bytes(plan['policy']) != _bytes(CANARY_POLICY): raise ValueError('workflow contract or policy changed')
    if set(plan['actors']) != set(ROLES) or len(set(plan['actors'].values())) != len(ROLES): raise ValueError('actor separation invalid')
    root = Path(input_root).resolve() if input_root is not None else Path(plan['input_root'])
    if _git(root, 'HEAD^{tree}') != plan['input_tree']: raise ValueError('frozen input tree moved')
    paths = list(preparation_dirs) if preparation_dirs is not None else plan['preparation_dirs']
    context = build_batch_context(paths, request_id=plan['request_id'], invocation_id=plan['invocation_id'], root=root)
    if (context['context_sha256'] != plan['context_sha256'] or _read(directory / 'context.json', 100_000_000) != context
        or plan['qa_targets'] != _qa(context)): raise ValueError('frozen context or QA sample changed')
    previous = {}
    for role in ROLES:
        path = directory / (role + '.json')
        if path.exists() or path.is_symlink():
            envelope = _read(path); _validate(envelope, role, plan, context, previous, input_root=root); previous[role] = envelope
    if (directory / 'release-preview.json').exists() or (directory / 'release-preview.json').is_symlink():
        preview = _preview(directory, plan, previous)
        if 'release_reviewer' in previous and previous['release_reviewer']['document']['approved_plan_sha256'] != preview['preview_sha256']:
            raise ValueError('review does not bind exact preview')
    elif 'release_reviewer' in previous: raise ValueError('review lacks immutable preview')
    return plan, context, previous


def assignment(directory: Path, role: str, *, input_root: Path | None = None, preparation_dirs=None) -> dict:
    if role not in ROLES: raise ValueError('unknown role')
    with _locked(directory) as directory:
        plan, context, previous = _load(directory, input_root=input_root, preparation_dirs=preparation_dirs); dependencies = _dependencies(role, previous)
        if any(r not in previous for r in dependencies): raise ValueError('mandatory prior stage missing')
        blind = role in ('primary', 'escalation_a', 'escalation_b')
        return {'role': role, 'actor_id': plan['actors'][role], 'role_invocation_id': _invocation(plan, role),
                'plan_sha256': plan['plan_sha256'], 'context': context, 'policy': plan['policy'],
                'instructions': (ROOT / PROMPT).read_text(),
                'inputs': {} if blind else {r: copy.deepcopy(previous[r]) for r in dependencies},
                'targets': _targets(context, previous['primary']['document']['payload'], plan) if role == 'verifier' else [],
                'release_preview': _preview(directory, plan, previous) if role == 'release_reviewer' else None}


def submit(directory: Path, role: str, actor_id: str, document: dict, *, input_root: Path | None = None, preparation_dirs=None) -> dict:
    if role not in ROLES: raise ValueError('unknown role')
    if len(_bytes(document)) > MAX_DOCUMENT_BYTES: raise ValueError('submission exceeds bound')
    with _locked(directory) as directory:
        plan, context, previous = _load(directory, input_root=input_root, preparation_dirs=preparation_dirs)
        envelope = {'role': role, 'actor_id': actor_id, 'role_invocation_id': _invocation(plan, role),
                    'plan_sha256': plan['plan_sha256'], 'document': copy.deepcopy(document)}
        envelope['submission_sha256'] = _hash(envelope)
        if len(_bytes(envelope)) + 1 > MAX_DOCUMENT_BYTES: raise ValueError('submission envelope exceeds bound')
        _validate(envelope, role, plan, context, previous, input_root=input_root)
        if role == 'release_reviewer' and document['approved_plan_sha256'] != _preview(directory, plan, previous)['preview_sha256']:
            raise ValueError('review does not bind exact preview')
        if role in previous:
            if previous[role] != envelope: raise ValueError('immutable role submission already exists')
            return copy.deepcopy(previous[role])
        _write(directory / (role + '.json'), envelope)
        return envelope


def verified_stage(directory: Path, *, input_root: Path | None = None, preparation_dirs=None) -> dict:
    with _locked(directory) as directory:
        plan, context, previous = _load(directory, input_root=input_root, preparation_dirs=preparation_dirs); final = _final_role(previous)
        return {'plan': plan, 'context': context, 'submissions': previous, 'final_role': final,
                'final_submission_sha256': previous[final]['submission_sha256'],
                'final_payload': copy.deepcopy(previous[final]['document']['payload']),
                'release_preview': _preview(directory, plan, previous) if (directory / 'release-preview.json').exists() else None}


def bind_release_preview(directory: Path, preview: dict, *, input_root: Path | None = None, preparation_dirs=None) -> dict:
    if not isinstance(preview, dict) or len(_bytes(preview)) > 9_000_000: raise ValueError('invalid release preview')
    with _locked(directory) as directory:
        plan, _, previous = _load(directory, input_root=input_root, preparation_dirs=preparation_dirs); final = _final_role(previous)
        required = {'graph_base_sha256', 'movements', 'closure_outcomes', 'workflow_plan_sha256', 'final_submission_sha256'}
        if (not required <= set(preview) or preview['workflow_plan_sha256'] != plan['plan_sha256']
            or preview['final_submission_sha256'] != previous[final]['submission_sha256']): raise ValueError('invalid compiler preview bindings')
        if (not isinstance(preview['graph_base_sha256'], str) or len(preview['graph_base_sha256']) != 64
            or any(c not in '0123456789abcdef' for c in preview['graph_base_sha256'])
            or not isinstance(preview['movements'], list) or not isinstance(preview['closure_outcomes'], list)):
            raise ValueError('invalid compiler preview shape')
        bound = {'plan_sha256': plan['plan_sha256'], 'final_submission_sha256': previous[final]['submission_sha256'],
                 'preview': copy.deepcopy(preview), 'preview_sha256': _hash(preview)}
        if (directory / 'release-preview.json').exists():
            if _preview(directory, plan, previous) != bound: raise ValueError('immutable preview already exists')
        else: _write(directory / 'release-preview.json', bound)
        return bound


def inspect_workflow(directory: Path, *, input_root: Path | None = None, preparation_dirs=None) -> dict:
    with _locked(directory) as directory:
        plan, context, previous = _load(directory, input_root=input_root, preparation_dirs=preparation_dirs); status = 'primary_pending'
        if 'primary' in previous: status = 'verification_pending'
        if 'verifier' in previous: status = 'escalation_pending' if _material(previous) else 'release_pending'
        if all(r in previous for r in ('escalation_a', 'escalation_b')): status = 'adjudication_pending'
        if 'adjudicator' in previous: status = 'release_pending'
        if 'release_reviewer' in previous: status = 'approved' if previous['release_reviewer']['document']['verdict'] == 'approve' else 'rejected'
        return {'plan_sha256': plan['plan_sha256'], 'status': status, 'completed_roles': list(previous),
                'submission_hashes': {r: e['submission_sha256'] for r, e in previous.items()},
                'escalation_required': _material(previous), 'qa_targets': plan['qa_targets'],
                'targets': _targets(context, previous['primary']['document']['payload'], plan) if 'primary' in previous else [],
                'canonical_activation_approved': False, 'model_invoked': False}


def closure_payload(directory: Path, *, input_root: Path | None = None, preparation_dirs=None) -> dict:
    stage = verified_stage(directory, input_root=input_root, preparation_dirs=preparation_dirs)
    if stage['submissions'].get('release_reviewer', {}).get('document', {}).get('verdict') != 'approve':
        raise ValueError('independent release approval required')
    return stage['final_payload']
