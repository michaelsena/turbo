"""Managed six-role batch integration; no automatic research or activation.

V2 authorization is supplied by the trusted coordinator. Constructing a document is
not evidence of human spend approval. The workflow determines role eligibility;
provider settlement never bypasses independent review or activates the graph.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from turbo.agents import batch_workflow as workflow
from turbo.agents import model_view as view
from turbo.agents.batch_output import PROMPT_PATH, SCHEMA_PATH, _strict_json
from turbo.agents.batch_execution_v2 import BatchExecutionV2
from turbo.agents.openrouter_attempt import bounded_request_body, invoke_openrouter_once
from turbo.agents.openrouter_runner import openrouter_schema
from turbo.pipeline_paths import ROOT

SUPPORTED_ROLES = workflow.ROLES
EXECUTION_FILES = ('src/turbo/agents/model_view.py', 'src/turbo/agents/batch_recovery.py', 'src/turbo/agents/batch_provider.py', 'src/turbo/agents/openrouter_attempt.py',
                   'src/turbo/agents/openrouter_runner.py', 'src/turbo/agents/batch_output.py',
                   'src/turbo/agents/batch_authorization.py', 'src/turbo/agents/runtime.py',
                   'src/turbo/agents/boundary_harness.py', 'src/turbo/universe/batch_closure.py',
                   'src/turbo/universe/graph_release.py', 'schemas/graph-release-config.schema.json')


def execution_contract_hashes(*, model_view: str | None = None) -> dict:
    if model_view not in (None, view.VERSION): raise ValueError('unknown model view')
    result = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in EXECUTION_FILES}
    if model_view is not None: result[view.CONTRACT_KEY] = view.POLICY_SHA256
    return result


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode()


def _hash(value: Any) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def role_schema(role: str, *, input_root: Path) -> dict:
    if role not in workflow.ROLES:
        raise ValueError('unknown workflow role')
    definitions = json.loads((ROOT / workflow.SCHEMA).read_text())['$defs']
    schema = copy.deepcopy(definitions['research' if role in
        ('primary', 'escalation_a', 'escalation_b') else role])
    if role == 'release_reviewer':
        # The exact 2-role/5-role hash objects are disjoint (closed properties),
        # so anyOf is equivalent and fits the pilot's provider-facing subset.
        hashes = schema['properties']['input_hashes']
        hashes['anyOf'] = hashes.pop('oneOf')
    if 'payload' in schema['properties']:
        payload = json.loads((Path(input_root) / SCHEMA_PATH).read_text())
        schema['$defs'] = payload.pop('$defs')
        payload.pop('$id', None)
        payload.pop('$schema', None)
        schema['properties']['payload'] = payload
    return schema


def role_prompt(*, input_root: Path, model_view: str | None = None) -> str:
    if model_view not in (None, view.VERSION): raise ValueError('unknown model view')
    return ((ROOT / workflow.PROMPT).read_text() + '\n\n# B3 payload instructions\n\n'
            + (Path(input_root) / PROMPT_PATH).read_text()
            + '\n\nReturn the assigned role document, not the coordinator envelope. '
              'For research roles put the complete B3 object inside payload. '
              'For verifier return input_hashes and assessments only.\n'
            + (view.INSTRUCTIONS if model_view is not None else ''))


def contract_bindings(*, input_root: Path, model_view: str | None = None) -> dict:
    """Bindings to include in each preregistered V2 role configuration."""
    prompt = role_prompt(input_root=input_root, model_view=model_view)
    return {role: {'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                   'schema_sha256': _hash(role_schema(role, input_root=input_root))}
            for role in workflow.ROLES}


def _validate_document(directory: Path, role: str, document: dict, *, input_root: Path,
                       preparation_dirs=None) -> dict:
    # Validate without publishing: paid settlement and artifacts precede submission.
    with workflow._locked(directory) as locked:
        plan, context, previous = workflow._load(locked, input_root=input_root,
                                                preparation_dirs=preparation_dirs)
        envelope = {'role': role, 'actor_id': plan['actors'][role],
                    'role_invocation_id': workflow._invocation(plan, role),
                    'plan_sha256': plan['plan_sha256'], 'document': document}
        envelope['submission_sha256'] = workflow._hash(envelope)
        if len(workflow._bytes(envelope)) + 1 > workflow.MAX_DOCUMENT_BYTES:
            raise ValueError('role output exceeds workflow bound')
        workflow._validate(envelope, role, plan, context, previous, input_root=input_root)
        if role == 'release_reviewer':
            preview = workflow._preview(locked, plan, previous)
            if document['approved_plan_sha256'] != preview['preview_sha256']:
                raise ValueError('release review does not bind exact compiler preview')
        return envelope


def _save_artifact(journal: Path, attempt_id: str, artifact: dict) -> dict:
    name = 'provider-' + hashlib.sha256(attempt_id.encode()).hexdigest() + '.json'
    path = journal / name
    raw = _bytes(artifact)
    if len(raw) > 8_000_000:
        raise ValueError('provider artifact exceeds bound')
    # Exclusive write: interrupted/partial artifacts are never silently overwritten.
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    descriptor = os.open(journal, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return {'artifact': name, 'artifact_sha256': hashlib.sha256(raw).hexdigest()}


def _load_artifact(journal: Path, reference: dict) -> dict:
    name = reference.get('artifact', '')
    if not isinstance(name, str) or Path(name).name != name or not name.startswith('provider-'):
        raise ValueError('invalid provider artifact reference')
    path = journal / name
    if path.is_symlink() or not path.is_file():
        raise ValueError('missing provider artifact')
    with path.open('rb') as stream:
        raw = stream.read(8_000_001)
    if len(raw) > 8_000_000 or hashlib.sha256(raw).hexdigest() != reference.get('artifact_sha256'):
        raise ValueError('provider artifact hash mismatch')
    return _strict_json(raw)



def _upstream_hashes(role: str, previous: dict) -> dict:
    return {name: previous[name]['submission_sha256']
            for name in workflow._dependencies(role, previous)}


def _snapshot(directory: Path, *, input_root: Path, preparation_dirs=None) -> dict:
    with workflow._locked(directory) as locked:
        _, _, previous = workflow._load(locked, input_root=input_root,
                                        preparation_dirs=preparation_dirs)
        return previous


def _verify_upstream(execution: BatchExecutionV2, role: str, previous: dict,
                     authorization: dict) -> dict:
    """Coordinator-only provenance. Never add these conclusions to blind prompts."""
    required = _upstream_hashes(role, previous)
    for name in required:
        origin, origin_authorization = execution.upstream_origin(name) if hasattr(execution, 'upstream_origin') else (execution, authorization)
        requests = origin.status()['requests']
        matches = [row for row in requests.values()
                   if row['role'] == name and row['status'] == 'succeeded']
        if len(matches) != 1:
            raise ValueError('upstream submission lacks one settled provider attempt')
        attempt = matches[0]
        artifact = _load_artifact(origin.journal_path, attempt['response']['output'])
        provider = artifact['provider']
        if (artifact['authorization_sha256'] != origin.authorization_sha256
                or artifact['attempt_id'] != attempt['attempt_id']
                or artifact['role'] != name or artifact['input_sha256'] != attempt['input_sha256']
                or artifact['upstream_submission_hashes'] != _upstream_hashes(name, previous)
                or artifact['valid'] is not True
                or artifact['document'] != previous[name]['document']
                or provider['status'] != 'valid'
                or provider['requested_model'] != origin_authorization['roles'][name]['model']
                or provider['served_model'] != origin_authorization['roles'][name]['model']
                or provider['usage'] != attempt['response']['usage']
                or provider['provider_cost_microusd'] != attempt['response']['provider_cost_microusd']):
            raise ValueError('upstream provider artifact does not substantiate submission')
        raw = base64.b64decode(artifact['output_base64'], validate=True)
        if (_strict_json(raw) != artifact['document']
                or hashlib.sha256(raw).hexdigest() != provider['body_sha256']):
            raise ValueError('upstream provider output differs from validated document')
    return required


def _replay_preview(directory: Path, *, input_root: Path, preparation_dirs=None) -> None:
    from turbo.universe import batch_closure
    stage = workflow.verified_stage(directory, input_root=input_root,
                                    preparation_dirs=preparation_dirs)
    wrapper = stage['release_preview']
    if wrapper is None:
        raise ValueError('compiler release preview required')
    actual = batch_closure._compile(stage, wrapper['preview']['config'], root=ROOT,
                                    input_root=input_root)
    if (actual != wrapper['preview']
            or workflow._hash(actual) != wrapper['preview_sha256']):
        raise ValueError('release compiler preview cannot replay')

def run_batch_role(directory: Path, registry_dir: Path, authorization: dict, role: str,
                   attempt_id: str, *, input_root: Path, preparation_dirs=None,
                   retry_of: str | None = None, api_key: str | None = None,
                   transport=None, clock=None, recovery_checkpoint: Path | None = None) -> dict:
    """Execute at most one managed attempt; repeat calls replay without HTTP.

    Eligibility comes from frozen workflow dependencies. This function never chooses
    a model, creates spend authority, automatically repairs, or activates the graph.
    """
    authorization = copy.deepcopy(authorization)
    if role not in SUPPORTED_ROLES:
        raise ValueError('unknown provider workflow role')
    directory = Path(directory).resolve()
    input_root = Path(input_root).resolve()
    task = workflow.assignment(directory, role, input_root=input_root,
                               preparation_dirs=preparation_dirs)
    enabled_view = view.VERSION if view.CONTRACT_KEY in authorization['execution_contract_hashes'] else None
    if enabled_view is not None and recovery_checkpoint is not None:
        raise ValueError('model view requires a fresh workflow authorization, not recovery')
    expected_contracts = execution_contract_hashes(model_view=enabled_view)
    if recovery_checkpoint is not None:
        from turbo.agents.batch_recovery import checkpoint_binding
        from turbo.agents.batch_execution_v2 import _read
        expected_contracts['recovery/checkpoint-v1'] = checkpoint_binding(_read(Path(recovery_checkpoint)))
    if authorization['execution_contract_hashes'] != expected_contracts:
        raise ValueError('execution implementation changed')
    if authorization['workflow_plan_sha256'] != task['plan_sha256']:
        raise ValueError('authorization does not bind workflow plan')
    bindings = contract_bindings(input_root=input_root, model_view=enabled_view)
    for name, binding in bindings.items():
        if any(authorization['roles'][name].get(k) != v for k, v in binding.items()):
            raise ValueError('role prompt/schema authorization mismatch')
    if authorization['roles']['primary']['model'] == authorization['roles']['verifier']['model']:
        raise ValueError('primary and verifier require distinct configured models')
    reviewer = authorization['roles']['release_reviewer']['model']
    if any(authorization['roles'][name]['model'] == reviewer
           for name in workflow.ROLES if name != 'release_reviewer'):
        raise ValueError('release reviewer requires an independent configured model')
    if role == 'release_reviewer':
        _replay_preview(directory, input_root=input_root, preparation_dirs=preparation_dirs)
    config = authorization['roles'][role]
    prompt = role_prompt(input_root=input_root, model_view=enabled_view)
    rendered_task = view.encode(task) if enabled_view is not None else task
    runtime = prompt + '\n# Frozen assignment\n' + _bytes(rendered_task).decode()
    schema = role_schema(role, input_root=input_root)
    # Conservative admission: UTF-8 request bytes plus an explicit wrapper allowance.
    # This deliberately overestimates normal tokenization, not a provider dollar cap.
    request_bound = bounded_request_body(routing=config.get('routing'), role_id=role, model=config['model'],
        reasoning_effort=config['reasoning_effort'], runtime_prompt_text=runtime,
        schema=openrouter_schema(schema), invocation_id='invocation:' + '0' * 24,
        max_completion_tokens=config['max_output_tokens'], allow_fallbacks=False,
        schema_name='turbo_workflow_role')
    if len(_bytes(request_bound)) + 4096 > config['max_input_tokens']:
        raise ValueError('conservative request token bound exceeds authorization')
    if not (api_key or os.environ.get('OPENROUTER_API_KEY')):
        raise ValueError('OpenRouter credential required before managed admission')
    if recovery_checkpoint is None:
        execution = BatchExecutionV2(registry_dir, authorization, **({'clock': clock} if clock else {}))
    else:
        from turbo.agents.batch_recovery import RecoveryExecution
        execution = RecoveryExecution(registry_dir, authorization, recovery_checkpoint, **({'clock': clock} if clock else {}))
        if (execution.checkpoint['workflow_path'] != str(directory)
                or execution.checkpoint['input_root'] != str(input_root)):
            raise ValueError('recovery workflow or input root changed')
    previous = _snapshot(directory, input_root=input_root, preparation_dirs=preparation_dirs)
    upstream = _verify_upstream(execution, role, previous, authorization)
    input_digest = _hash({'assignment': task, 'runtime_prompt': runtime, 'schema': schema,
                          'upstream_submission_hashes': upstream})
    status = workflow.inspect_workflow(directory, input_root=input_root,
                                       preparation_dirs=preparation_dirs)
    # Offline submissions cannot masquerade as results of this governed execution.
    if role in status['completed_roles']:
        existing = execution.status()['requests'].get(attempt_id)
        if existing is None or existing['status'] != 'succeeded':
            raise ValueError('existing workflow submission lacks this settled provider attempt')

    def invoke(envelope: dict) -> dict:
        fresh = workflow.assignment(directory, role, input_root=input_root,
                                    preparation_dirs=preparation_dirs)
        if fresh != task:
            raise ValueError('workflow inputs changed before dispatch')
        current = _snapshot(directory, input_root=input_root, preparation_dirs=preparation_dirs)
        if _verify_upstream(execution, role, current, authorization) != upstream:
            raise ValueError('upstream provenance changed before dispatch')
        if role == 'release_reviewer':
            _replay_preview(directory, input_root=input_root, preparation_dirs=preparation_dirs)
        options = dict(invocation_id='invocation:' + _hash([
                           execution.authorization_sha256, attempt_id])[:24],
                       role=role, model=config['model'], reasoning_effort=config['reasoning_effort'],
                       runtime_prompt_text=runtime, schema=schema,
                       max_completion_tokens=config['max_output_tokens'],
                       timeout=config['timeout_seconds'], allow_fallbacks=config['allow_fallbacks'],
                       routing=config.get('routing'), api_key=api_key)
        if transport is not None:
            options['transport'] = transport
        result = invoke_openrouter_once(**options)
        raw = result.pop('body', None)
        document = None
        valid = False
        if (raw is not None and result['status'] == 'valid'
                and result['served_model'] == config['model']):
            try:
                if len(raw) > workflow.MAX_DOCUMENT_BYTES:
                    raise ValueError('role output exceeds bound')
                document = _strict_json(raw)
                observed = workflow.assignment(directory, role, input_root=input_root,
                                               preparation_dirs=preparation_dirs)
                if observed != task:
                    raise ValueError('workflow assignment changed during provider execution')
                current = _snapshot(directory, input_root=input_root, preparation_dirs=preparation_dirs)
                if _verify_upstream(execution, role, current, authorization) != upstream:
                    raise ValueError('upstream provenance changed during provider execution')
                if role == 'release_reviewer':
                    _replay_preview(directory, input_root=input_root, preparation_dirs=preparation_dirs)
                _validate_document(directory, role, document, input_root=input_root,
                                   preparation_dirs=preparation_dirs)
                valid = True
            except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
                document = None
        artifact = {'authorization_sha256': execution.authorization_sha256,
                    'attempt_id': attempt_id, 'role': role, 'input_sha256': input_digest,
                    'upstream_submission_hashes': upstream, 'provider': result, 'document': document, 'valid': valid,
                    'output_base64': base64.b64encode(raw).decode() if raw is not None else None}
        reference = _save_artifact(execution.journal_path, attempt_id, artifact)
        return {'outcome': 'succeeded' if valid else 'failed',
                'usage': result.get('usage'), 'provider_cost_microusd': result.get('provider_cost_microusd'),
                'output': reference}

    result = execution.run(role, attempt_id, invoke, retry_of=retry_of,
                           input_sha256=input_digest)
    if result['status'] in {'succeeded', 'failed'}:
        artifact = _load_artifact(execution.journal_path, result['response']['output'])
        if (artifact['authorization_sha256'] != execution.authorization_sha256
                or artifact['attempt_id'] != attempt_id or artifact['role'] != role
                or artifact['input_sha256'] != input_digest
                or artifact['upstream_submission_hashes'] != upstream):
            raise ValueError('provider artifact binding mismatch')
        if artifact['valid'] != (result['status'] == 'succeeded'):
            raise ValueError('provider artifact verdict mismatch')
        if result['status'] == 'failed':
            return result
        raw = base64.b64decode(artifact['output_base64'], validate=True)
        if _strict_json(raw) != artifact['document']:
            raise ValueError('provider output differs from validated document')
        if role == 'release_reviewer':
            _replay_preview(directory, input_root=input_root, preparation_dirs=preparation_dirs)
        _validate_document(directory, role, artifact['document'], input_root=input_root,
                           preparation_dirs=preparation_dirs)
        workflow.submit(directory, role, task['actor_id'], artifact['document'],
                        input_root=input_root, preparation_dirs=preparation_dirs)
    return result
