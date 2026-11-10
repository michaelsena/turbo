"""Governed evaluation admission and request planning (Issue 86a).

Production admission is deliberately closed until a governed eligibility validator
exists. Internal planning helpers do not confer eligibility or accept score events.
Universe workflow semantics and V2 accounting remain unchanged.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from turbo.agents import batch_execution_v2 as ledger
from turbo.agents.batch_output import _strict_json
from turbo.agents.openrouter_attempt import bounded_request_body, openrouter_role_schema

KIND = 'governed-submodel-work-unit-v1'
TASK_SLOTS = {'evaluator_a': 'primary', 'evaluator_b': 'verifier',
              'adjudicator': 'adjudicator', 'comparator': 'release_reviewer'}
BLOCKED = 'BLOCKED_ELIGIBILITY_IMPLEMENTATION'
CODE = ('src/turbo/agents/evaluation_workflow.py',
        'scripts/run-evaluation-work-unit.py',
        'src/turbo/agents/batch_execution_v2.py',
        'src/turbo/agents/batch_authorization.py',
        'src/turbo/agents/batch_output.py',
        'src/turbo/agents/openrouter_attempt.py',
        'src/turbo/agents/openrouter_runner.py',
        'schemas/batch-authorization-v2.schema.json')
ROOT = Path(__file__).resolve().parents[3]


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode()


def _sha(value: Any) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path(directory: Path, name: str) -> Path:
    if not isinstance(name, str):
        raise ValueError('artifact path must be a string')
    relative = Path(name)
    if relative.is_absolute() or not relative.parts or '..' in relative.parts:
        raise ValueError('artifact path escapes work unit')
    path = directory / relative
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise ValueError('symlink artifact path')
    return path


def _read(path: Path) -> dict:
    ledger._regular(path)
    if path.stat().st_size > 16_000_000:
        raise ValueError('artifact too large')
    result = _strict_json(path.read_bytes())
    if not isinstance(result, dict):
        raise ValueError('artifact must be an object')
    return result


def contracts() -> dict[str, str]:
    """Exact code dependencies for this closed-admission implementation."""
    return {name: _file_sha(ROOT / name) for name in CODE}


def load_plan(directory: Path) -> dict:
    """Check immutable packaging only; this never establishes eligibility."""
    directory = Path(directory).absolute()
    plan = _read(_path(directory, 'plan.json'))
    required = {'kind', 'submodel_version_id', 'market_version_ids', 'graph',
                'eligibility', 'strategy', 'factors', 'evidence', 'evidence_cutoff',
                'task_slots', 'tasks', 'files', 'code', 'registry_path'}
    if set(plan) != required or plan['kind'] != KIND:
        raise ValueError('unsupported work-unit plan')
    if plan['code'] != contracts() or plan['task_slots'] != TASK_SLOTS:
        raise ValueError('work-unit implementation or task mapping changed')
    markets = plan['market_version_ids']
    if (not isinstance(markets, list) or not markets or len(markets) != len(set(markets))
            or any(not isinstance(m, str) or not m.startswith('market-version:') for m in markets)):
        raise ValueError('exact canonical market version identifiers required')
    if not isinstance(plan['submodel_version_id'], str) or not plan['submodel_version_id']:
        raise ValueError('one submodel version required')
    if not isinstance(plan['registry_path'], str) or not Path(plan['registry_path']).is_absolute():
        raise ValueError('absolute dedicated registry path required')
    if str(Path(plan['registry_path']).resolve()) != plan['registry_path']:
        raise ValueError('registry path must be canonical')
    ledger.utc_datetime(plan['evidence_cutoff'])
    if not isinstance(plan['files'], dict) or not plan['files']:
        raise ValueError('frozen artifacts required')
    for name, digest in plan['files'].items():
        ledger._digest(digest)
        path = _path(directory, name)
        ledger._regular(path)
        if path.stat().st_size > 16_000_000 or _file_sha(path) != digest:
            raise ValueError('frozen artifact changed')
    def artifact(name):
        if name not in plan['files']:
            raise ValueError('unbound artifact')
        return _read(_path(directory, name))
    for key in ('graph', 'eligibility', 'strategy', 'factors', 'evidence'):
        artifact(plan[key])
    if set(plan['tasks']) != set(TASK_SLOTS):
        raise ValueError('exactly four semantic tasks required')
    for task, spec in plan['tasks'].items():
        if set(spec) != {'prompt', 'schema', 'config'}:
            raise ValueError('task configuration fields changed')
        prompt = artifact(spec['prompt'])
        if set(prompt) != {'text'} or not isinstance(prompt['text'], str) or not prompt['text'].strip():
            raise ValueError('frozen prompt text required')
        Draft202012Validator.check_schema(artifact(spec['schema']))
        if spec['config'].get('max_attempts') != 1 or spec['config'].get('allow_fallbacks') is not False:
            raise ValueError('one attempt without fallbacks required')
    return plan


def _role_bindings(directory: Path, plan: dict) -> dict:
    bindings = {}
    for task, slot in TASK_SLOTS.items():
        spec = plan['tasks'][task]
        prompt = _read(_path(directory, spec['prompt']))['text']
        schema = _read(_path(directory, spec['schema']))
        bindings[slot] = dict(spec['config'],
                              prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                              schema_sha256=_sha(schema))
    # Required by V2 schema, but never reachable through TASK_SLOTS.
    for slot in set(ledger.ROLES) - set(TASK_SLOTS.values()):
        bindings[slot] = dict(bindings['primary'])
    return bindings


def _authority_bindings(directory: Path, plan: dict, authority: dict) -> dict:
    ledger._validate_auth(authority)
    expected = dict(contracts(), **{'evaluation/registry-path': _sha(plan['registry_path']),
                                   'evaluation/task-slots': _sha(TASK_SLOTS)})
    if (authority['workflow_plan_sha256'] != _sha(plan)
            or authority['execution_contract_hashes'] != expected
            or authority['roles'] != _role_bindings(directory, plan)
            or authority['max_calls'] != 4):
        raise ValueError('authority does not bind this single work unit')
    digest = ledger._hash(authority)
    return {'kind': KIND, 'plan_sha256': _sha(plan), 'authorization_sha256': digest,
            'attempt_ids': {task: 'evaluation:' + _sha([digest, task])[:40] for task in TASK_SLOTS}}


def preflight(directory: Path, *, authority: dict | None = None) -> dict:
    """Read-only report: even valid packaging cannot bypass absent eligibility."""
    directory = Path(directory).absolute()
    plan = load_plan(directory)
    if authority is not None:
        _authority_bindings(directory, plan, authority)
    return {'kind': KIND, 'status': BLOCKED, 'execution_enabled': False,
            'reason': 'No governed eligibility projection compiler/validator is installed.',
            'plan_sha256': _sha(plan), 'submodel_version_id': plan['submodel_version_id'],
            'market_version_ids': plan['market_version_ids'], 'task_slots': dict(TASK_SLOTS),
            'graph_provenance_validated': False, 'eligibility_provenance_validated': False,
            'scope': 'single_submodel_work_unit', 'global_ranking': False}


def run_task(directory: Path, task: str, *, authority: dict | None = None,
             execute: bool = False) -> dict:
    """No public admission bypass, credential parameter, or network dispatch."""
    if task not in TASK_SLOTS:
        raise ValueError('disabled or unknown semantic task')
    report = preflight(directory, authority=authority)
    if execute:
        raise ValueError(BLOCKED + ': governed eligibility replay must be implemented and reviewed')
    return report


def _assignment(plan: dict, task: str, *, verified_upstream: dict) -> dict:
    """Pure dependency-view builder; caller must separately verify provenance.

    Internal testable mechanics only. This function accepts no scores as events,
    publishes nothing, and is not a production eligibility/acceptance interface.
    """
    if task not in TASK_SLOTS:
        raise ValueError('disabled or unknown semantic task')
    common = {key: plan[key] for key in ('submodel_version_id', 'market_version_ids',
              'graph', 'eligibility', 'strategy', 'factors', 'evidence', 'evidence_cutoff')}
    if task in ('evaluator_a', 'evaluator_b'):
        return {'frozen_input': common, 'upstream': {}}
    required = {'evaluator_a', 'evaluator_b'} if task == 'adjudicator' else {'resolved_submodel'}
    if set(verified_upstream) != required:
        raise ValueError('exact semantic dependencies required')
    return {'frozen_input': common, 'upstream': verified_upstream}


def _request(directory: Path, plan: dict, task: str, *, attempt_id: str,
             verified_upstream: dict) -> dict:
    """Build a bounded request without dispatch; not an admission decision."""
    assignment = _assignment(plan, task, verified_upstream=verified_upstream)
    # Include frozen artifact content, not just paths that a model cannot read.
    assignment['artifacts'] = {key: _read(_path(directory, plan[key]))
                               for key in ('graph', 'eligibility', 'strategy', 'factors', 'evidence')}
    spec = plan['tasks'][task]; config = spec['config']
    schema = _read(_path(directory, spec['schema']))
    prompt = _read(_path(directory, spec['prompt']))['text']
    runtime = prompt + '\n# Frozen assignment\n' + _bytes(assignment).decode()
    wire = bounded_request_body(invocation_id=attempt_id, role_id=task,
        model=config['model'], reasoning_effort=config['reasoning_effort'],
        runtime_prompt_text=runtime,
        schema=openrouter_role_schema(schema, role_id=task, model=config['model']),
        max_completion_tokens=config['max_output_tokens'], allow_fallbacks=False,
        routing=config.get('routing'), schema_name='turbo_evaluation_task')
    if len(_bytes(wire)) + 4096 > config['max_input_tokens']:
        raise ValueError('request exceeds conservative input bound')
    return wire
