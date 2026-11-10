"""Explicit governed eligibility/evaluation tasks over the existing V2 ledger.

This adapter never publishes canonical markets, accepts caller-written scores,
repairs output, creates authority, or retries a physical attempt.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from pathlib import Path

from jsonschema import Draft202012Validator
from turbo.agents import batch_execution_v2 as ledger, evaluation_scores as scores
from turbo.agents import evaluation_workflow as packaging
from turbo.agents.openrouter_attempt import bounded_request_body, invoke_openrouter_once
from turbo.agents.openrouter_runner import openrouter_role_schema

ROOT = Path(__file__).resolve().parents[3]
ELIGIBILITY_KIND = 'governed-eligibility-execution-v1'
EVALUATION_KIND = 'governed-submodel-execution-v1'
EVALUATION_SLOTS = {'evaluator_a': 'primary', 'evaluator_b': 'verifier',
                    'adjudicator': 'adjudicator', 'comparator': 'release_reviewer'}
CODE = (*packaging.CODE, 'src/turbo/agents/evaluation_execution.py',
        'src/turbo/agents/evaluation_scores.py', 'scripts/run-governed-evaluation.py')
_bytes, _sha, _read, _path = packaging._bytes, packaging._sha, packaging._read, packaging._path


def _eligibility():
    from turbo.agents import governed_eligibility
    return governed_eligibility


def contracts():
    paths = set(CODE) | {str(p.relative_to(ROOT)) for p in (ROOT/'src/turbo').rglob('*.py')}
    paths |= {str(p.relative_to(ROOT)) for p in (ROOT/'schemas').glob('*.json')}
    return {**{name: packaging._file_sha(ROOT/name) for name in sorted(paths)}, **_eligibility().contracts()}


def slots(plan):
    return {'eligibility': 'primary'} if plan['kind'] == ELIGIBILITY_KIND else dict(EVALUATION_SLOTS)


def _object(properties):
    return {'type': 'object', 'additionalProperties': False, 'properties': properties, 'required': list(properties)}


def output_schema(task):
    if task == 'eligibility': return _eligibility().eligibility_output_schema()
    text = {'type': 'string', 'minLength': 1}
    strings = {'type': 'array', 'items': text, 'uniqueItems': True}
    number = {'type': 'number'}
    references = {'rationale': text, 'claim_ids': strings, 'counterevidence_ids': strings, 'gap_ids': strings}
    if task == 'comparator':
        return _object({'pairs': {'type': 'array', 'items': _object({'pair_id': text, 'market_version_ids': strings,
            'preferred_market_version_id': {'type': ['string','null']}, 'confidence': number, **references})},
            'adjustments': {'type': 'array', 'items': _object({'market_version_id': text, 'delta': number, 'pair_ids': strings, 'rationale': text})}})
    if task not in ('evaluator_a', 'evaluator_b', 'adjudicator'): raise ValueError('unknown task')
    return _object({'scores': {'type': 'array', 'items': _object({
        'market_version_id': text, 'factor_version_id': text,
        'raw': number, 'confidence': number, 'evidence_quality': number, 'downside': number,
        'label': {'type': 'string', 'enum': ['fact', 'inference', 'assumption']}, **references,
        'alternatives': {'type': 'array', 'items': number}})}})


def _artifact(directory, plan, key):
    name = plan[key]
    if name not in plan['files']: raise ValueError('unbound artifact')
    return _read(_path(directory, name))


def load_plan(directory):
    directory = Path(directory).absolute()
    if directory != directory.resolve(): raise ValueError('resolved work-unit path required')
    plan = _read(_path(directory, 'plan.json'))
    common = {'schema_version', 'kind', 'market_version_ids', 'graph', 'strategy', 'evidence',
              'evidence_cutoff', 'tasks', 'task_slots', 'files', 'code', 'registry_path'}
    if plan.get('kind') == EVALUATION_KIND: common |= {'eligibility', 'factors', 'submodel_version_id'}
    elif plan.get('kind') != ELIGIBILITY_KIND: raise ValueError('unsupported governed execution kind')
    if set(plan) != common or type(plan['schema_version']) is not int or plan['schema_version'] != 1:
        raise ValueError('exact versioned execution plan required')
    if _bytes(plan['code']) != _bytes(contracts()) or plan['task_slots'] != slots(plan):
        raise ValueError('frozen execution contract changed')
    if (not isinstance(plan['market_version_ids'], list) or not plan['market_version_ids']
            or any(not isinstance(m, str) or not m.startswith('market-version:') for m in plan['market_version_ids'])
            or len(plan['market_version_ids']) != len(set(plan['market_version_ids']))):
        raise ValueError('canonical version scope required')
    ledger.utc_datetime(plan['evidence_cutoff'])
    registry = Path(plan['registry_path'])
    if not registry.is_absolute() or registry != registry.resolve(): raise ValueError('resolved registry path required')
    if not isinstance(plan['files'], dict) or not plan['files']: raise ValueError('frozen files required')
    for name, digest in plan['files'].items():
        ledger._digest(digest); path = _path(directory, name); ledger._regular(path)
        if path.stat().st_size > 16_000_000 or packaging._file_sha(path) != digest:
            raise ValueError('frozen artifact changed')
    for key in ('graph', 'strategy', 'evidence'): _artifact(directory, plan, key)
    if plan['kind'] == EVALUATION_KIND:
        _artifact(directory, plan, 'eligibility')
        scores.policy(_artifact(directory, plan, 'factors'), plan['submodel_version_id'])
    if set(plan['tasks']) != set(slots(plan)): raise ValueError('exact semantic task scope required')
    actors = []
    for task, spec in plan['tasks'].items():
        if set(spec) != {'actor_id', 'prompt', 'schema', 'config'}: raise ValueError('task fields')
        if not isinstance(spec['actor_id'], str) or not spec['actor_id'].strip(): raise ValueError('actor identity required')
        actors.append(spec['actor_id'])
        for name in ('prompt', 'schema'):
            if spec[name] not in plan['files']: raise ValueError('unbound task artifact')
        prompt = _read(_path(directory, spec['prompt']))
        if set(prompt) != {'text'} or not isinstance(prompt['text'], str) or not prompt['text'].strip(): raise ValueError('prompt required')
        schema = _read(_path(directory, spec['schema']))
        Draft202012Validator.check_schema(schema)
        if _bytes(schema) != _bytes(output_schema(task)): raise ValueError('canonical task schema required')
        cfg = spec['config']
        if cfg.get('max_attempts') != 1 or cfg.get('allow_fallbacks') is not False: raise ValueError('one physical attempt without fallback required')
    if len(actors) != len(set(actors)): raise ValueError('independent semantic actors required')
    return plan



def freeze_plan(directory, *, kind, market_version_ids, artifacts, evidence_cutoff,
                task_configs, registry_path, submodel_version_id=None):
    """Freeze already prepared local inputs and explicit task configs; no authority.

    artifacts maps graph/strategy/evidence (and eligibility/factors for evaluation)
    to relative files in directory. Evidence source_path files must also be present.
    task_configs maps task to actor_id, prompt text, and explicit provider config.
    Existing files are never overwritten; an interrupted freeze must be inspected.
    """
    directory = Path(directory).absolute()
    if directory != directory.resolve() or not directory.is_dir(): raise ValueError('existing resolved input directory required')
    if (directory / 'plan.json').exists(): raise ValueError('plan already exists')
    fields = {'graph','strategy','evidence'}
    if kind == EVALUATION_KIND: fields |= {'eligibility','factors'}
    elif kind != ELIGIBILITY_KIND: raise ValueError('unsupported execution kind')
    if set(artifacts) != fields: raise ValueError('exact input artifact roles required')
    plan = {'schema_version':1, 'kind':kind, 'market_version_ids':list(market_version_ids),
        **artifacts, 'evidence_cutoff':evidence_cutoff, 'tasks':{}, 'files':{}, 'code':contracts(),
        'registry_path':str(Path(registry_path).absolute())}
    plan['task_slots'] = slots(plan)
    if set(task_configs) != set(slots(plan)): raise ValueError('exact task configuration required')
    if kind == EVALUATION_KIND: plan['submodel_version_id'] = submodel_version_id
    names = set(artifacts.values())
    source = _read(_path(directory, artifacts['evidence']))
    names.update(row['source_path'] for row in source['items'])
    for name in names:
        path = _path(directory,name); ledger._regular(path)
        plan['files'][name] = packaging._file_sha(path)
    for task,cfg in task_configs.items():
        if set(cfg) != {'actor_id','prompt','config'}: raise ValueError('exact explicit actor/prompt/config required')
        prompt = 'task-' + task + '-prompt.json'; schema = 'task-' + task + '-schema.json'
        for name,value in [(prompt,{'text':cfg['prompt']}),(schema,output_schema(task))]:
            ledger._write(_path(directory,name),value)
            plan['files'][name] = packaging._file_sha(directory/name)
        plan['tasks'][task] = {'actor_id':cfg['actor_id'],'prompt':prompt,'schema':schema,'config':copy.deepcopy(cfg['config'])}
    ledger._write(directory/'plan.json',plan)
    checked = load_plan(directory); _validated_input(directory,checked)
    return checked


def _validated_input(directory, plan):
    module = _eligibility()
    value = module.validate_eligibility_input(directory, plan)
    if plan['kind'] == EVALUATION_KIND:
        value['eligibility'] = module.validate_for_evaluation(directory, plan)
        value['factors'] = scores.policy(_artifact(directory, plan, 'factors'), plan['submodel_version_id'])
        model_policy = {'tasks': {task: {k: spec['config'][k] for k in ('model','reasoning_effort')}
                                  for task,spec in plan['tasks'].items()}}
        if any(_bytes(f['model_policy']) != _bytes(model_policy) for f in value['factors']['factors']):
            raise ValueError('factor model policy differs from frozen execution tasks')
    return value


def role_bindings(directory, plan):
    roles = {}
    for task, slot in slots(plan).items():
        spec = plan['tasks'][task]
        roles[slot] = {**spec['config'],
            'prompt_sha256': hashlib.sha256(_read(_path(directory, spec['prompt']))['text'].encode()).hexdigest(),
            'schema_sha256': _sha(_read(_path(directory, spec['schema'])))}
    for slot in set(ledger.ROLES) - set(roles): roles[slot] = copy.deepcopy(roles['primary'])
    return roles


def authority_contracts(plan):
    return {**contracts(), 'evaluation/registry-path': _sha(plan['registry_path']),
            'evaluation/task-slots': _sha(slots(plan))}


def _authority(directory, plan, authority):
    ledger._validate_auth(authority)
    if (authority['workflow_plan_sha256'] != _sha(plan)
            or authority['execution_contract_hashes'] != authority_contracts(plan)
            or authority['roles'] != role_bindings(directory, plan)
            or authority['max_calls'] != len(slots(plan))):
        raise ValueError('authority does not bind this exact governed work unit')
    digest = ledger._hash(authority)
    return {'kind': plan['kind'], 'work_unit_dir': str(Path(directory).resolve()),
        'plan_sha256': _sha(plan), 'authorization_sha256': digest,
        'attempt_ids': {task: 'governed:' + _sha([digest, task])[:40] for task in slots(plan)}}


def _owner(directory, plan, authority):
    expected = _authority(directory, plan, authority)
    if _read(directory / 'execution-owner.json') != expected: raise ValueError('work-unit owner changed')
    registry = Path(plan['registry_path']); ledger._registry(registry)
    if _read(registry / ('governed-owner-' + _sha(str(directory)) + '.json')) != expected:
        raise ValueError('registry ownership changed')
    if _read(directory / 'execution-authority.json') != authority: raise ValueError('stored authority changed')
    ledger._regular(directory / '.execution.lock')
    return expected


def initialize(directory, authority, *, clock=ledger.utc_now):
    """Explicitly bind one work unit to an already initialized registry; no calls."""
    directory = Path(directory).resolve(); plan = load_plan(directory)
    _validated_input(directory, plan)
    owner = _authority(directory, plan, authority); registry = Path(plan['registry_path'])
    ledger._registry(registry)
    with ledger._lock(registry / '.lock'):
        claim = registry / ('governed-owner-' + _sha(str(directory)) + '.json')
        if claim.exists() or claim.is_symlink() or (directory / 'execution-owner.json').exists():
            raise ValueError('work-unit ownership already exists; inspect original state')
        ledger._write(directory / 'execution-authority.json', authority)
        ledger._write(directory / 'execution-owner.json', owner)
        (directory / '.execution.lock').touch(mode=0o600, exist_ok=False)
        ledger._write(claim, owner)
    ledger.BatchExecutionV2(registry, authority, clock=clock)
    return owner


def _state(directory, plan, authority):
    """Read an existing journal without creating a claim or repairing missing state."""
    registry = Path(plan['registry_path']); meta = ledger._registry(registry)
    digest = ledger._hash(authority); journal = registry / 'journals' / digest
    expected = {'authorization_sha256': digest, 'registry_id': meta['registry_id']}
    if (_read(registry / 'claims' / (digest + '.json')) != expected
            or _read(journal / 'ready.json') != expected
            or _read(journal / 'authorization.json') != authority): raise ValueError('journal identity changed')
    with ledger._lock(journal / '.lock'):
        ledger._regular(journal / 'events.jsonl'); raw = (journal / 'events.jsonl').read_bytes()
        if not raw.endswith(b'\n'): raise ValueError('partial journal')
        return ledger.replay_events([packaging._strict_json(line) for line in raw.splitlines()], authority,
                                    registry_id=meta['registry_id']), journal


def _dependencies(task, outputs, inputs):
    if task in ('eligibility', 'evaluator_a', 'evaluator_b'): return {}, {}
    if not {'evaluator_a', 'evaluator_b'} <= set(outputs): raise ValueError('both blind evaluations required')
    a, b = (outputs[t]['document'] for t in ('evaluator_a', 'evaluator_b'))
    material = scores.disagreements(a, b, inputs['factors'])
    hashes = {t: outputs[t]['artifact_sha256'] for t in ('evaluator_a', 'evaluator_b')}
    if task == 'adjudicator':
        if not material: raise ValueError('adjudicator not eligible without material disagreement')
        return {'evaluator_a': a, 'evaluator_b': b, 'disagreements': material}, hashes
    if material and 'adjudicator' not in outputs: raise ValueError('material disagreement requires adjudication')
    adj = outputs.get('adjudicator', {}).get('document')
    if material: hashes['adjudicator'] = outputs['adjudicator']['artifact_sha256']
    return {'resolved_submodel': scores.resolve(inputs['market_version_ids'], inputs['factors'], a, b, adj),
            'comparison_pairs': scores.comparison_pairs(inputs['market_version_ids'], inputs['factors'])}, hashes


def _request(directory, plan, task, owner, inputs, outputs):
    if task not in slots(plan): raise ValueError('disabled task')
    dependencies, hashes = _dependencies(task, outputs, inputs)
    assignment = {'task': task, 'actor_id': plan['tasks'][task]['actor_id'],
        'plan_sha256': _sha(plan), 'frozen_input': inputs, 'dependencies': dependencies}
    spec = plan['tasks'][task]; cfg = spec['config']; schema = _read(_path(directory, spec['schema']))
    runtime = _read(_path(directory, spec['prompt']))['text'] + '\n# Frozen assignment\n' + _bytes(assignment).decode()
    invocation = owner['attempt_ids'][task]
    wire = bounded_request_body(invocation_id=invocation, role_id=task, model=cfg['model'],
        reasoning_effort=cfg['reasoning_effort'], runtime_prompt_text=runtime,
        schema=openrouter_role_schema(schema, role_id=task, model=cfg['model']),
        max_completion_tokens=cfg['max_output_tokens'], allow_fallbacks=False,
        routing=cfg.get('routing'), schema_name='turbo_workflow_role')
    if len(_bytes(wire)) + 4096 > cfg['max_input_tokens']: raise ValueError('conservative request admission exceeded')
    digest = _sha({'plan_sha256': _sha(plan), 'task': task, 'request_sha256': _sha(wire),
                   'upstream_artifact_hashes': hashes})
    return {'wire': wire, 'runtime': runtime, 'schema': schema, 'config': cfg,
            'dependencies': dependencies, 'upstream_artifact_hashes': hashes, 'input_sha256': digest}


def _validate(document, task, request, inputs):
    if not Draft202012Validator(request['schema']).is_valid(document): raise ValueError('invalid governed task schema')
    if task == 'eligibility': _eligibility().validate_eligibility_output(document, inputs)
    else: scores.validate(document, task, inputs['market_version_ids'], inputs['factors'],
                          inputs['evidence'], request['dependencies'])


def _replay(directory, plan, authority, owner, inputs):
    state, journal = _state(directory, plan, authority); outputs = {}
    expected_ids = set(owner['attempt_ids'].values())
    if set(state['requests']) - expected_ids: raise ValueError('journal contains unassigned task')
    for task, slot in slots(plan).items():
        aid = owner['attempt_ids'][task]; attempt = state['requests'].get(aid)
        if attempt is None: continue
        request = _request(directory, plan, task, owner, inputs, outputs)
        if (attempt['role'] != slot or attempt['input_sha256'] != request['input_sha256']
                or attempt['retry_of'] is not None): raise ValueError('task request lineage changed')
        if attempt['status'] not in ('succeeded', 'failed'): continue
        reference = attempt['response']['output']
        if set(reference) != {'artifact', 'artifact_sha256'}: raise ValueError('provider artifact reference required')
        path = _path(journal, reference['artifact']); artifact = _read(path)
        if packaging._file_sha(path) != reference['artifact_sha256']: raise ValueError('provider artifact changed')
        expected = {'plan_sha256': _sha(plan), 'authorization_sha256': ledger._hash(authority),
                    'task': task, 'attempt_id': aid, 'input_sha256': request['input_sha256'],
                    'upstream_artifact_hashes': request['upstream_artifact_hashes']}
        if any(artifact.get(k) != v for k, v in expected.items()): raise ValueError('provider binding mismatch')
        provider = artifact['provider']
        if provider.get('request_sha256') != _sha(request['wire']): raise ValueError('provider request bytes changed')
        if (provider.get('usage') != attempt['response']['usage']
                or provider.get('provider_cost_microusd') != attempt['response']['provider_cost_microusd']):
            raise ValueError('provider telemetry differs from settled journal')
        if type(artifact['valid']) is not bool or artifact['valid'] != (attempt['status'] == 'succeeded'):
            raise ValueError('provider verdict mismatch')
        if not artifact['valid']: continue
        raw = base64.b64decode(artifact['output_base64'], validate=True)
        document = packaging._strict_json(raw)
        if (hashlib.sha256(raw).hexdigest() != provider.get('body_sha256')
                or _bytes(document) != _bytes(artifact['document'])
                or provider.get('status') != 'valid'
                or provider.get('served_model') != request['config']['model']
                or provider.get('schema_sha256') != _sha(request['schema'])
                or provider.get('invocation_id') != aid or provider.get('role') != task
                or provider.get('requested_model') != request['config']['model']
                or provider.get('provider_schema_sha256') != _sha(openrouter_role_schema(request['schema'],role_id=task,model=request['config']['model']))):
            raise ValueError('provider document/model/schema mismatch')
        _validate(document, task, request, inputs)
        outputs[task] = {'document': document, 'artifact_sha256': reference['artifact_sha256'],
                         'output_sha256': _sha(document)}
    return state, journal, outputs


def preflight(directory, *, authority=None):
    directory = Path(directory).resolve(); plan = load_plan(directory); inputs = _validated_input(directory, plan)
    result = {'kind': plan['kind'], 'plan_sha256': _sha(plan), 'status': 'READY_FOR_INITIALIZATION',
              'market_version_ids': plan['market_version_ids'], 'execution_enabled': True,
              'global_ranking': False, 'canonical_publication': False}
    if authority is not None: _authority(directory, plan, authority)
    if (directory / 'execution-owner.json').exists():
        authority = _read(directory / 'execution-authority.json') if authority is None else authority
        owner = _owner(directory, plan, authority)
        state, _, outputs = _replay(directory, plan, authority, owner, inputs)
        result.update(status='INITIALIZED', completed_tasks=list(outputs), accounting=state)
    return result


def run_task(directory, task, *, execute=False, api_key=None, transport=None, clock=ledger.utc_now):
    directory = Path(directory).resolve(); plan = load_plan(directory)
    if task not in slots(plan): raise ValueError('disabled task')
    inputs = _validated_input(directory, plan)
    authority = _read(directory / 'execution-authority.json'); owner = _owner(directory, plan, authority)
    with ledger._lock(directory / '.execution.lock'):
        state, journal, outputs = _replay(directory, plan, authority, owner, inputs)
        request = _request(directory, plan, task, owner, inputs, outputs)
        existing = state['requests'].get(owner['attempt_ids'][task])
        if existing is not None: return {'task': task, 'status': existing['status'], 'dispatch': False}
        if any(a['status'] != 'succeeded' for a in state['requests'].values()):
            raise ValueError('failed or unresolved task blocks further work-unit dispatch')
        if not execute: return {'task': task, 'status': 'READY', 'dispatch': False,
                               'request_sha256': _sha(request['wire']), 'input_bound': len(_bytes(request['wire']))+4096}
        if not (api_key or os.environ.get('OPENROUTER_API_KEY')): raise ValueError('explicit credential required')
        execution = ledger.BatchExecutionV2(Path(plan['registry_path']), authority, clock=clock)
        config = request['config']; aid = owner['attempt_ids'][task]
        def invoke(envelope):
            fresh_plan = load_plan(directory); fresh_inputs = _validated_input(directory, fresh_plan)
            _, _, fresh_outputs = _replay(directory, fresh_plan, authority, owner, fresh_inputs)
            if _bytes(_request(directory, fresh_plan, task, owner, fresh_inputs, fresh_outputs)) != _bytes(request):
                raise ValueError('assignment changed before transport')
            options = dict(invocation_id=aid, role=task, model=config['model'], reasoning_effort=config['reasoning_effort'],
                runtime_prompt_text=request['runtime'], schema=request['schema'], max_completion_tokens=config['max_output_tokens'],
                timeout=config['timeout_seconds'], allow_fallbacks=False, routing=config.get('routing'), api_key=api_key)
            if transport is not None: options['transport'] = transport
            receipt = invoke_openrouter_once(**options); raw = receipt.pop('body', None); document = None; valid = False
            if raw is not None and receipt['status'] == 'valid' and receipt['served_model'] == config['model']:
                try:
                    document = packaging._strict_json(raw)
                    check_plan = load_plan(directory); check_inputs = _validated_input(directory, check_plan)
                    _, _, check_outputs = _replay(directory, check_plan, authority, owner, check_inputs)
                    if _bytes(_request(directory, check_plan, task, owner, check_inputs, check_outputs)) != _bytes(request):
                        raise ValueError('assignment changed during transport')
                    _validate(document, task, request, inputs); valid = True
                except (ValueError, TypeError, KeyError, OSError): document = None
            artifact = {'plan_sha256': _sha(plan), 'authorization_sha256': ledger._hash(authority),
                'task': task, 'attempt_id': aid, 'input_sha256': request['input_sha256'],
                'upstream_artifact_hashes': request['upstream_artifact_hashes'], 'provider': receipt,
                'valid': valid, 'document': document, 'output_base64': base64.b64encode(raw).decode() if raw is not None else None}
            name = 'governed-' + _sha([aid, request['input_sha256']]) + '.json'
            ledger._write(journal / name, artifact)
            return {'outcome': 'succeeded' if valid else 'failed', 'usage': receipt.get('usage'),
                'provider_cost_microusd': receipt.get('provider_cost_microusd'),
                'output': {'artifact': name, 'artifact_sha256': packaging._file_sha(journal/name)}}
        result = execution.run(slots(plan)[task], aid, invoke, input_sha256=request['input_sha256'])
        _replay(directory, plan, authority, owner, inputs)
        return {'task': task, 'status': result['status'], 'dispatch': True}


def validate_eligibility_provider(directory, descriptor):
    if set(descriptor) != {'work_unit_dir','plan_sha256','authorization_sha256','task','output_sha256'}:
        raise ValueError('exact eligibility provider descriptor required')
    path = Path(descriptor['work_unit_dir'])
    if not path.is_absolute() or path != path.resolve(): raise ValueError('resolved eligibility work unit required')
    plan = load_plan(path)
    if plan['kind'] != ELIGIBILITY_KIND or descriptor['task'] != 'eligibility': raise ValueError('wrong eligibility work-unit kind')
    authority = _read(path/'execution-authority.json'); owner = _owner(path, plan, authority)
    if descriptor['plan_sha256'] != _sha(plan) or descriptor['authorization_sha256'] != ledger._hash(authority):
        raise ValueError('eligibility producer identity changed')
    _, _, outputs = _replay(path, plan, authority, owner, _validated_input(path, plan))
    result = outputs.get('eligibility')
    if result is None or result['output_sha256'] != descriptor['output_sha256']: raise ValueError('settled valid eligibility provider output required')
    return result['document']


def projection(directory):
    directory = Path(directory).resolve(); plan = load_plan(directory); inputs = _validated_input(directory, plan)
    authority = _read(directory/'execution-authority.json'); owner = _owner(directory, plan, authority)
    _, _, outputs = _replay(directory, plan, authority, owner, inputs)
    if plan['kind'] == ELIGIBILITY_KIND:
        if 'eligibility' not in outputs: raise ValueError('eligibility judgment incomplete')
        return _eligibility().compile_eligibility(outputs['eligibility']['document'], inputs)
    if 'comparator' not in outputs: raise ValueError('submodel comparison incomplete')
    resolved = _dependencies('comparator', outputs, inputs)[0]['resolved_submodel']
    comparison = outputs['comparator']['document']; deltas = {r['market_version_id']: r['delta'] for r in comparison['adjustments']}
    for row in resolved['submodel_scores']: row['compared_downside_adjusted'] = row['downside_adjusted'] + deltas[row['market_version_id']]
    return {**resolved, 'submodel_version_id': plan['submodel_version_id'], 'comparison': comparison,
        'plan_sha256': _sha(plan), 'provider_outputs': {k: v['output_sha256'] for k,v in outputs.items()},
        'accepted_global_ranking': False}
