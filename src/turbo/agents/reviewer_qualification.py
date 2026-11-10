"""Isolated reviewer qualification: four cells, no research publication or retries."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from jsonschema import Draft202012Validator
from turbo.agents import batch_execution_v2 as ledger, batch_provider as provider
from turbo.agents import readable_request_candidate as readable
from turbo.agents.batch_authorization import utc_now, utc_datetime
from turbo.agents.batch_output import _strict_json
from turbo.agents.openrouter_attempt import bounded_request_body, invoke_openrouter_once, openrouter_role_schema
from turbo.pipeline_paths import ROOT

KIND = 'isolated-reviewer-qualification-v1'
CELLS = {'positive-plain': 'primary', 'positive-references': 'verifier',
         'negative-plain': 'escalation_a', 'negative-references': 'escalation_b'}
CONTRACT_KEY = 'qualification/' + KIND
REGISTRY_KEY = 'qualification/registry-path-v1'
CODE_FILES = ('src/turbo/agents/reviewer_qualification.py',
              'src/turbo/agents/reviewer_qualification_builder.py',
              'scripts/run-reviewer-qualification.py', 'scripts/build-reviewer-qualification.py')
SETTINGS = ('model', 'reasoning_effort', 'max_output_tokens', 'timeout_seconds',
            'allow_fallbacks', 'routing', 'input_microusd_per_token',
            'output_microusd_per_token', 'max_input_tokens')


def sha(value): return hashlib.sha256(provider._bytes(value)).hexdigest()


def file_sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def path_at(root, name):
    relative = Path(name)
    if relative.is_absolute() or not relative.parts or '..' in relative.parts:
        raise ValueError('invalid qualification artifact path')
    path = root / relative
    for parent in (path, *path.parents):
        if parent.is_symlink(): raise ValueError('qualification symlink path')
    return path


def read(path):
    ledger._regular(path)
    if path.stat().st_size > 16_000_000: raise ValueError('qualification artifact too large')
    return _strict_json(path.read_bytes())


def contracts():
    result = provider.execution_contract_hashes(reviewer_view=readable.FORMAT)
    result.update({name: file_sha(ROOT / name) for name in CODE_FILES})
    result[CONTRACT_KEY] = sha({'kind': KIND, 'cells': CELLS, 'max_calls': 4, 'retries': False})
    return result


def request_for(task, representation, config, schema, *, cell):
    mode = readable.FORMAT if representation == 'references' else None
    # Prompt text is frozen by the builder; this helper never reads prior answers.
    runtime = task['prompt'] + '\n# Frozen assignment\n' + provider._bytes(
        readable.encode(task['assignment']) if mode else task['assignment']).decode()
    invocation = 'invocation:' + sha([KIND, cell, sha(task['assignment'])])[:24]
    options = dict(invocation_id=invocation, role='release_reviewer', model=config['model'],
        reasoning_effort=config['reasoning_effort'], runtime_prompt_text=runtime, schema=schema,
        max_completion_tokens=config['max_output_tokens'], timeout=config['timeout_seconds'],
        allow_fallbacks=False, routing=config['routing'])
    wire = bounded_request_body(invocation_id=invocation, role_id='release_reviewer',
        model=config['model'], reasoning_effort=config['reasoning_effort'], runtime_prompt_text=runtime,
        schema=openrouter_role_schema(schema, role_id='release_reviewer', model=config['model']),
        max_completion_tokens=config['max_output_tokens'], allow_fallbacks=False,
        routing=config['routing'], schema_name='turbo_workflow_role')
    return wire, options


def load_bundle(directory):
    directory = Path(directory).resolve(strict=True)
    manifest = read(directory / 'manifest.json')
    if (set(manifest) != {'kind', 'cells', 'files', 'config', 'schema', 'rubric', 'source', 'code'}
            or manifest['kind'] != KIND or set(manifest['cells']) != set(CELLS)
            or manifest['code'] != contracts()):
        raise ValueError('qualification manifest or implementation changed')
    for name, digest in manifest['files'].items():
        path = path_at(directory, name)
        if file_sha(path) != digest: raise ValueError('qualification artifact hash changed')
    def artifact(name):
        if name not in manifest['files']: raise ValueError('unbound qualification artifact')
        return read(path_at(directory, name))
    config = manifest['config']
    if set(config) != set(SETTINGS) or config['allow_fallbacks'] is not False:
        raise ValueError('qualification settings changed')
    schema = artifact(manifest['schema']); Draft202012Validator.check_schema(schema)
    if schema != provider.role_schema('release_reviewer', input_root=ROOT):
        raise ValueError('qualification requires canonical reviewer schema')
    rubric = artifact(manifest['rubric'])
    if rubric.get('kind') != KIND or rubric.get('version') != 1:
        raise ValueError('qualification rubric changed')
    loaded = {}
    for cell, slot in CELLS.items():
        entry = manifest['cells'][cell]
        if set(entry) != {'ledger_slot', 'task', 'request'} or entry['ledger_slot'] != slot:
            raise ValueError('qualification cell accounting mapping changed')
        task = artifact(entry['task'])
        if set(task) != {'assignment', 'prompt'} or set(task['assignment']['inputs']) != {'primary', 'verifier'}:
            raise ValueError('qualification fixture dependencies changed')
        assignment = task['assignment']
        if assignment['role'] != 'release_reviewer': raise ValueError('qualification is reviewer only')
        wire, options = request_for(task, cell.split('-')[1], config, schema, cell=cell)
        if artifact(entry['request']) != wire: raise ValueError('qualification request differs from fixture')
        if len(provider._bytes(wire)) + 4096 > config['max_input_tokens']:
            raise ValueError('qualification conservative input bound exceeds fixed cap')
        loaded[cell] = dict(slot=slot, task=task, wire=wire, options=options)
    for fixture in ('positive', 'negative'):
        plain_prompt = loaded[fixture+'-plain']['task']['prompt']
        if loaded[fixture+'-references']['task']['prompt'] != plain_prompt + '\n# Reviewer readable references\n' + readable.INSTRUCTIONS:
            raise ValueError('representation prompt policy changed')
        if loaded[fixture+'-plain']['task']['assignment'] != loaded[fixture+'-references']['task']['assignment']:
            raise ValueError('plain and referenced fixtures differ')
    if loaded['positive-plain']['task']['prompt'] != loaded['negative-plain']['task']['prompt']:
        raise ValueError('fixture prompt settings differ')
    return directory, manifest, schema, rubric, loaded


def role_bindings(manifest, schema, loaded):
    # Slots are accounting labels only, never primary/verifier research judgments.
    config = dict(manifest['config'], max_attempts=1)
    fallback = next(iter(loaded.values()))
    return {slot: dict(config, prompt_sha256=hashlib.sha256(next((v for v in loaded.values() if v['slot'] == slot), fallback)['options']['runtime_prompt_text'].encode()).hexdigest(),
                       schema_sha256=sha(schema)) for slot in ledger.ROLES}


def preflight(bundle, authority=None, *, registry=None):
    directory, manifest, schema, rubric, loaded = load_bundle(bundle)
    roles = role_bindings(manifest, schema, loaded)
    expected_contracts = contracts()
    if registry is not None:
        expected_contracts[REGISTRY_KEY] = sha(str(Path(registry).resolve()))
    elif authority is not None:
        raise ValueError('authority validation requires its dedicated registry path')
    reservation = ledger._reservation({'roles': roles}, 'primary')
    report = {'kind': KIND, 'packet_sha256': sha(manifest), 'authority_supplied': authority is not None,
        'required_execution_contract_hashes': expected_contracts, 'required_role_bindings': roles,
        'registry_binding_required': registry is None,
        'max_calls': 4, 'reservation_per_cell_microusd': reservation,
        'aggregate_reservation_microusd': 4*reservation,
        'cells': {cell: {'ledger_slot': row['slot'], 'request_sha256': sha(row['wire']),
                        'wire_bytes': len(provider._bytes(row['wire'])),
                        'conservative_input_bound': len(provider._bytes(row['wire']))+4096}
                  for cell, row in loaded.items()}, 'execution_performed': False}
    if authority is not None:
        ledger._validate_auth(authority)
        if (authority['workflow_plan_sha256'] != sha(manifest) or authority['execution_contract_hashes'] != expected_contracts
                or authority['roles'] != roles or authority['max_calls'] != 4
                or authority['max_cost_microusd'] != 4*reservation):
            raise ValueError('authority does not bind exact qualification packet and limits')
        report['authorization_sha256'] = ledger._hash(authority)
        if registry is not None and Path(registry).exists():
            reg = Path(registry).resolve(strict=True); ledger._registry(reg)
            claim_names = {p.name for p in (reg/'claims').iterdir()}
            if claim_names - {ledger._hash(authority)+'.json'}:
                raise ValueError('qualification registry contains another authority')
            owner = reg/'qualification.json'
            if not owner.exists() or ledger._read(owner) != {'kind': KIND, 'packet_sha256': sha(manifest), 'authorization_sha256': ledger._hash(authority)}:
                raise ValueError('registry is not owned by this qualification')
    return report


def validate_output(document, schema, assignment):
    if not Draft202012Validator(schema).is_valid(document): raise ValueError('response_schema')
    if document['input_hashes'] != {key: value['submission_sha256'] for key, value in assignment['inputs'].items()}:
        raise ValueError('response_upstream_hashes')
    if document['approved_plan_sha256'] != assignment['release_preview']['preview_sha256']:
        raise ValueError('response_preview_hash')
    findings = document['findings']
    if len({item['finding_id'] for item in findings}) != len(findings): raise ValueError('response_duplicate_findings')
    if document['verdict'] == 'approve' and (any(v != 'pass' for v in document['checks'].values()) or any(f['status'] != 'resolved' for f in findings)):
        raise ValueError('response_approval_with_failed_checks')
    known = {item['evidence_id'] for family in assignment['context']['families'] for item in family['evidence_catalog']}
    cited = set(re.findall(r'evidence:[A-Za-z0-9_-]+', json.dumps(document)))
    if cited - known: raise ValueError('response_unknown_evidence_reference')


def _immutable(path, value):
    if path.exists() or path.is_symlink():
        if read(path) != value: raise ValueError('immutable qualification record changed')
    else: ledger._write(path, value)


def run_cell(bundle, authority, registry, cell, *, execute=False, api_key=None, transport=None, clock=utc_now):
    if authority is None: raise ValueError('externally supplied qualification authority required')
    if cell not in CELLS: raise ValueError('unknown qualification cell')
    report = preflight(bundle, authority, registry=registry)
    if not execute: return report
    if not api_key: raise ValueError('credential required before qualification admission')
    if not utc_datetime(authority['valid_from_utc']) <= utc_datetime(clock()) < utc_datetime(authority['expires_at_utc']):
        raise ValueError('qualification authority is not currently valid')
    directory, manifest, schema, rubric, loaded = load_bundle(bundle)
    row = loaded[cell]; registry = Path(registry).absolute()
    if not registry.exists():
        ledger.initialize_registry(registry)
        ledger._write(registry/'qualification.json', {'kind': KIND, 'packet_sha256': sha(manifest), 'authorization_sha256': ledger._hash(authority)})
    registry = registry.resolve(strict=True)
    engine = ledger.BatchExecutionV2(registry, authority, clock=clock)
    attempt_id = 'qualification:' + cell
    def invoke(envelope):
        # Recheck immutable inputs immediately before the single transport attempt.
        preflight(bundle, authority, registry=registry)
        _immutable(engine.journal_path/(cell+'-request.json'), {'cell': cell, 'ledger_slot': row['slot'], 'request': row['wire']})
        result = invoke_openrouter_once(**row['options'], api_key=api_key,
                                       **({'transport': transport} if transport is not None else {}))
        body = result.pop('body', None); document = None; error = None
        try:
            if result['request_sha256'] != sha(row['wire']): raise ValueError('request_hash')
            if result['status'] != 'valid' or result['served_model'] != manifest['config']['model']:
                raise ValueError('provider_invalid')
            document = _strict_json(body)
            validate_output(document, schema, row['task']['assignment'])
        except (ValueError, TypeError, KeyError):
            document = None; error = 'invalid_provider_or_canonical_response'
        artifact = {'cell': cell, 'ledger_slot': row['slot'], 'packet_sha256': sha(manifest),
                    'provider': result, 'document': document, 'validation_error': error,
                    'body_base64': base64.b64encode(body).decode() if body is not None else None}
        output = engine.journal_path/(cell+'-response.json'); _immutable(output, artifact)
        return {'outcome': 'succeeded' if document is not None else 'failed', 'usage': result['usage'],
                'provider_cost_microusd': result['provider_cost_microusd'],
                'output': {'artifact': output.name, 'artifact_sha256': file_sha(output)}}
    with ledger._lock(registry/'.lock'):
        preflight(bundle, authority, registry=registry)
        state = engine.status(); _check_attempts(state, loaded)
        existing = state['requests'].get(attempt_id)
        if existing and 'response' in existing:
            _verified_response(engine.journal_path, cell, row, existing, manifest, schema)
        result = engine.run(row['slot'], attempt_id, invoke, input_sha256=sha(row['wire']))
    return {'kind': KIND, 'cell': cell, 'ledger_slot': row['slot'], 'attempt': result,
            'independent_semantic_assessment_required': True}


def _check_attempts(state, loaded):
    expected = {'qualification:'+cell: cell for cell in CELLS}
    for attempt_id, attempt in state['requests'].items():
        if attempt_id not in expected: raise ValueError('foreign qualification attempt')
        row = loaded[expected[attempt_id]]
        if (attempt['role'] != row['slot'] or attempt['input_sha256'] != sha(row['wire'])
                or attempt['retry_of'] is not None):
            raise ValueError('qualification attempt binding changed')


def _verified_response(journal, cell, row, attempt, manifest, schema):
    stored_request = read(journal/(cell+'-request.json'))
    if stored_request != {'cell': cell, 'ledger_slot': row['slot'], 'request': row['wire']}:
        raise ValueError('qualification stored request changed')
    refs = attempt['response']['output']; artifact_path = path_at(journal, refs['artifact'])
    if file_sha(artifact_path) != refs['artifact_sha256']: raise ValueError('qualification response artifact changed')
    artifact = read(artifact_path); metadata = artifact['provider']
    if (artifact['cell'] != cell or artifact['ledger_slot'] != row['slot']
            or artifact['packet_sha256'] != sha(manifest)
            or metadata['request_sha256'] != sha(row['wire'])
            or metadata['usage'] != attempt['response']['usage']
            or metadata['provider_cost_microusd'] != attempt['response']['provider_cost_microusd']):
        raise ValueError('qualification response provenance changed')
    try:
        body = base64.b64decode(artifact['body_base64'], validate=True) if artifact['body_base64'] is not None else None
    except (ValueError, TypeError) as error:
        raise ValueError('qualification body encoding changed') from error
    if body is not None and hashlib.sha256(body).hexdigest() != metadata['body_sha256']:
        raise ValueError('qualification response body changed')
    document = None
    if metadata['status'] == 'valid' and metadata['served_model'] == manifest['config']['model']:
        try:
            document = _strict_json(body)
            validate_output(document, schema, row['task']['assignment'])
        except (ValueError, TypeError, KeyError): document = None
    expected_error = None if document is not None else 'invalid_provider_or_canonical_response'
    if (artifact['document'] != document or artifact['validation_error'] != expected_error
            or attempt['status'] != ('succeeded' if document is not None else 'failed')):
        raise ValueError('qualification response document or classification changed')
    return artifact


def comparison(bundle, authority, registry):
    preflight(bundle, authority, registry=registry)
    _, manifest, schema, _, loaded = load_bundle(bundle)
    registry = Path(registry).resolve(strict=True)
    digest = ledger._hash(authority); journal = registry/'journals'/digest
    metadata = ledger._registry(registry)
    expected = {'authorization_sha256': digest, 'registry_id': metadata['registry_id']}
    ledger._regular(journal, True)
    if (ledger._read(registry/'claims'/(digest+'.json')) != expected
            or ledger._read(journal/'ready.json') != expected
            or ledger._read(journal/'authorization.json') != authority):
        raise ValueError('qualification journal ownership changed')
    ledger._regular(journal/'events.jsonl')
    events = (journal/'events.jsonl').read_bytes()
    if not events.endswith(b'\n'): raise ValueError('partial qualification journal')
    state = ledger.replay_events([_strict_json(line) for line in events.splitlines()], authority,
                                registry_id=metadata['registry_id'])
    _check_attempts(state, loaded)
    cells = {}
    for cell, slot in CELLS.items():
        attempt = state['requests'].get('qualification:'+cell)
        row = {'cell': cell, 'ledger_slot': slot, 'status': attempt['status'] if attempt else 'not_attempted'}
        if attempt and 'response' in attempt:
            artifact = _verified_response(journal, cell, loaded[cell], attempt, manifest, schema)
            row['document'] = artifact['document']; row['validation_error'] = artifact['validation_error']
        cells[cell] = row
    return {'kind': KIND, 'cells': cells, 'calls_reserved': state['calls_reserved'],
            'committed_microusd': state['committed_microusd'], 'outstanding_microusd': state['outstanding_microusd'],
            'independent_semantic_assessment_required': True, 'production_enablement': False}
