"""Explicit one-shot release-review HTTP-400 continuation; unknown spend stays held.

Imports exactly one settled primary and verifier plus their immutable compiler
preview. It cannot retry research, fork successors, or refresh the parent budget.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from turbo.agents import batch_execution_v2 as ledger
from turbo.agents.batch_authorization import utc_now

CONTRACT_KEY = 'recovery/release-http400-v1'
BOUND_KIND = 'explicit_bound_release_http400_successor'
PINNED_SOURCE_COMMIT = 'f5fcbbd82c0fd5b847b26be96ac2a65522ef308a'
PINNED_SOURCE_TREE = 'c3e3db157f4b9e0c04b38527c4d2f24005fb5ce8'
# Released plain-contract implementation used by the initial small qualification.
PREDECESSOR_CONTRACT = {'schemas/graph-release-config.schema.json': '7b06fc7565bc52ad639a3148c1a175e5512b51ba789ef311d74b47630fc0ecc3', 'src/turbo/agents/batch_authorization.py': '4165a4aae65e3c225149a363050cf4bd48daf4551aadca80630462868d08de9c', 'src/turbo/agents/batch_output.py': '7b8447ecef2b94a81fc83d3045acf295cbe2e82c952db02dcf4b19968ee19433', 'src/turbo/agents/batch_provider.py': '1b42ff6c73f9294aa353ffd27523d5c831233d4917cff0048677a1ffe8da2202', 'src/turbo/agents/batch_recovery.py': 'b66af6d6d1cc57f2c8d543c6f244f83c69a4167b0c1cc30ede5d7e6b7543ed2b', 'src/turbo/agents/boundary_harness.py': 'e138491ec7038e4e0a3e14b00e136149a972d61782e5702726dd0171ecb14c1e', 'src/turbo/agents/model_view.py': '47e777c62f7e5e2b1a7971ccf38dca69d334993fc6655823031bed49603c4567', 'src/turbo/agents/openrouter_attempt.py': '6da33cf46918ff3c4c4b818268f9c4b09e851796a1f8a087bbdc9165574156f1', 'src/turbo/agents/openrouter_runner.py': '1e25d49ef2cd0d1927909d4e36138c00a88255f821139c759abf193f621afc31', 'src/turbo/agents/runtime.py': 'ecad21221a50d6b00f69357510f20b8cd8877382475e2c8046a14038a699980f', 'src/turbo/universe/batch_closure.py': 'f20e549ba55e591b2a6f02e008162d9c8557913ee0e278078903b8e815f3940c', 'src/turbo/universe/graph_release.py': '542aa4929b342cdb0f340d44ba8cf4ddb5b53c6083a4f80a1eab6e0656aa4ff3'}


def checkpoint_binding(checkpoint):
    return ledger._hash({k: v for k, v in checkpoint.items() if k != 'successor_authorization_sha256'})


def _source_contracts(source_runtime):
    """One explicit original source identity, never a hash wildcard."""
    from turbo.agents import batch_provider as provider
    root = Path(source_runtime).resolve(strict=True)
    def git(*args):
        return subprocess.check_output(['git','--no-optional-locks','-C',str(root),*args], text=True, stderr=subprocess.PIPE).strip()
    if (git('rev-parse','HEAD') != PINNED_SOURCE_COMMIT or git('rev-parse','HEAD^{tree}') != PINNED_SOURCE_TREE
            or git('status','--porcelain','--untracked-files=all')):
        raise ValueError('original runtime must be exact clean pinned f5fc source')
    expected = provider.execution_contract_hashes(model_view=provider.view.VERSION, citation_sets=True)
    for name in expected:
        if name.startswith(('src/','schemas/')):
            path = root/name
            if path.is_symlink() or not path.is_file(): raise ValueError('unsafe frozen source file')
            expected[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return expected


def _frozen_proof(source_runtime, registry_dir, authorization, workflow_dir, input_root, preparation_dirs):
    contracts = _source_contracts(source_runtime)
    if contracts != authorization['execution_contract_hashes']:
        raise ValueError('frozen authorization/source mismatch')
    root = Path(source_runtime).resolve()
    if Path(input_root).resolve() != root:
        raise ValueError('bound recovery requires original frozen input runtime')
    # Import only the verified predecessor in a fresh interpreter. No credential,
    # transport, registry initialization or mutable current-provider import occurs.
    code = r"""
import hashlib,json,sys
from pathlib import Path
v=json.loads(sys.stdin.read());sys.path.insert(0,v['source']+'/src')
from turbo.agents import batch_provider as p,batch_controller as c,batch_execution_v2 as l
from turbo.agents import model_view
r=Path(v['registry']);a=v['authorization'];w=Path(v['workflow']);i=Path(v['input'])
state=c._journal(r,a)
previous=p._snapshot(w,input_root=i,preparation_dirs=v['preparations'])
source=l.BatchExecutionV2(r,a)
hashes=p._verify_upstream(source,'release_reviewer',previous,a,input_root=i)
p._replay_preview(w,input_root=i,preparation_dirs=v['preparations'])
request_bindings={}
for attempt in state['requests'].values():
 role=attempt['role'];cfg=a['roles'][role];aid=attempt['attempt_id']
 name='provider-'+hashlib.sha256(aid.encode()).hexdigest()+'.json'
 path=source.journal_path/name
 artifact=p._load_artifact(source.journal_path,{'artifact':name,'artifact_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 receipt=artifact['provider']
 assignment=p.workflow.assignment(w,role,input_root=i,preparation_dirs=v['preparations'])
 rendered=p.render_assignment(assignment,input_root=i,model_view=model_view.VERSION,citation_sets=True)
 canonical=p.role_schema(role,input_root=i,citation_sets=True)
 wire=p.openrouter_role_schema(canonical,role_id=role,model=cfg['model'])
 invocation='invocation:'+p._hash([l._hash(a),aid])[:24]
 request=p.bounded_request_body(routing=cfg.get('routing'),role_id=role,model=cfg['model'],reasoning_effort=cfg['reasoning_effort'],runtime_prompt_text=rendered,schema=wire,invocation_id=invocation,max_completion_tokens=cfg['max_output_tokens'],allow_fallbacks=cfg['allow_fallbacks'],schema_name='turbo_workflow_role')
 expected={'role':role,'invocation_id':invocation,'requested_model':cfg['model'],'request_sha256':p._hash(request),'schema_sha256':p._hash(canonical),'provider_schema_sha256':p._hash(wire)}
 if any(receipt.get(k)!=val for k,val in expected.items()):raise ValueError('original request receipt metadata changed')
 if p._hash({'assignment':assignment,'runtime_prompt':rendered,'schema':canonical,'upstream_submission_hashes':p._upstream_hashes(role,previous)})!=attempt['input_sha256']:raise ValueError('original request input changed')
 request_bindings[role]=expected
task=p.workflow.assignment(w,'release_reviewer',input_root=i,preparation_dirs=v['preparations'])
runtime=p.render_assignment(task,input_root=i,model_view=model_view.VERSION,citation_sets=True)
schema=p.role_schema('release_reviewer',input_root=i,citation_sets=True)
print(json.dumps({'source_commit':v['commit'],'source_tree':v['tree'],
 'contracts':p.execution_contract_hashes(model_view=model_view.VERSION,citation_sets=True),'request_bindings':request_bindings,
 'input_sha256':p._hash({'assignment':task,'runtime_prompt':runtime,'schema':schema,'upstream_submission_hashes':hashes}),
 'upstream_submission_hashes':hashes,'release_preview_sha256':l._hash(l._read(w/'release-preview.json')),
 'source_events_sha256':hashlib.sha256((r/'journals'/l._hash(a)/'events.jsonl').read_bytes()).hexdigest()}))
"""
    value = dict(source=str(root), registry=str(Path(registry_dir).resolve()), authorization=authorization,
                 workflow=str(Path(workflow_dir).resolve()), input=str(root),
                 preparations=[str(Path(p).resolve()) for p in preparation_dirs] if preparation_dirs is not None else None,
                 commit=PINNED_SOURCE_COMMIT, tree=PINNED_SOURCE_TREE)
    result = subprocess.run([sys.executable,'-I','-B','-c',code], input=json.dumps(value), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, cwd=root, check=False,
        env={'PATH':os.defpath,'LANG':'C','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    if result.returncode: raise ValueError('frozen predecessor proof failed')
    proof = json.loads(result.stdout)
    if proof['contracts'] != contracts: raise ValueError('frozen proof contract mismatch')
    return proof


def prepare_bound_successor(registry_dir, source_authorization, *, source_runtime, replacement_reviewer, **kwargs):
    """Prepare one explicit Luna review with unchanged original views and research."""
    return _prepare(registry_dir, source_authorization, source_runtime=source_runtime,
                    replacement_reviewer=replacement_reviewer, **kwargs)


def _source(registry, authorization, *, source_runtime=None):
    from turbo.agents import batch_provider as provider
    if source_runtime is not None:
        if authorization['execution_contract_hashes'] != _source_contracts(source_runtime):
            raise ValueError('frozen predecessor execution contract changed')
    elif authorization['execution_contract_hashes'] not in (PREDECESSOR_CONTRACT, provider.execution_contract_hashes()):
        raise ValueError('unsupported predecessor execution contract')
    registry = Path(registry).resolve(strict=True)
    ledger._registry(registry)
    digest = ledger._hash(authorization)
    ledger._regular(registry / 'claims' / (digest + '.json'))
    for name in ('authorization.json', 'ready.json', 'events.jsonl', '.lock'):
        ledger._regular(registry / 'journals' / digest / name)
    source = ledger.BatchExecutionV2(registry, authorization)
    state = source.status()
    upstream = {role: [a for a in state['requests'].values()
                      if a['role'] == role and a['status'] == 'succeeded']
                for role in ('primary', 'verifier')}
    rejected = [a for a in state['requests'].values()
                if a['role'] == 'release_reviewer' and a['status'] == 'unresolved']
    if len(state['requests']) != 3 or any(len(rows) != 1 for rows in upstream.values()) or len(rejected) != 1:
        raise ValueError('recovery requires settled primary/verifier and one unresolved release reviewer')
    attempt = rejected[0]
    name = 'provider-' + hashlib.sha256(attempt['attempt_id'].encode()).hexdigest() + '.json'
    path = source.journal_path / name
    ledger._regular(path)
    raw = path.read_bytes()
    artifact = provider._load_artifact(source.journal_path, {'artifact': name, 'artifact_sha256': hashlib.sha256(raw).hexdigest()})
    result = artifact['provider']
    if (artifact['authorization_sha256'] != source.authorization_sha256
            or artifact['attempt_id'] != attempt['attempt_id'] or artifact['role'] != 'release_reviewer'
            or artifact['input_sha256'] != attempt['input_sha256'] or artifact['valid'] is not False
            or artifact['document'] is not None or artifact['output_base64'] is not None
            or result['http_status'] != 400 or result['status'] != 'invalid'
            or result['error_stage'] != 'http' or result['transport_attempted'] is not True
            or any(result.get(k) is not None for k in ('generation_id', 'served_model', 'served_provider', 'usage', 'provider_cost_microusd'))):
        raise ValueError('only a recorded HTTP 400 without generation or usage metadata is eligible')
    ledger._digest(result['response_sha256'])
    tip = hashlib.sha256((source.journal_path / 'events.jsonl').read_bytes()).hexdigest()
    return source, state, {role: rows[0] for role, rows in upstream.items()}, attempt, tip, hashlib.sha256(raw).hexdigest(), artifact


def _prepare(registry_dir, source_authorization, *, workflow_dir, input_root,
             replacement_attempt_id, authorized_by, valid_from_utc, expires_at_utc,
             preparation_dirs=None, allow_completed=False, source_runtime=None, replacement_reviewer=None):
    from turbo.agents import batch_provider as provider
    source, state, upstream, rejected, tip, rejected_hash, artifact = _source(registry_dir, source_authorization, source_runtime=source_runtime)
    frozen = _frozen_proof(source_runtime, registry_dir, source_authorization, workflow_dir, input_root, preparation_dirs) if source_runtime is not None else None
    ledger._identifier(replacement_attempt_id)
    if replacement_attempt_id in state['requests'] or not authorized_by.strip():
        raise ValueError('new exact replacement and explicit operator required')
    directory, input_root = Path(workflow_dir).resolve(), Path(input_root).resolve()
    previous = provider._snapshot(directory, input_root=input_root, preparation_dirs=preparation_dirs)
    expected = {'primary', 'verifier'}
    if set(previous) != expected and not (allow_completed and set(previous) == expected | {'release_reviewer'}):
        raise ValueError('recovery requires exact accepted primary/verifier workflow')
    hashes = provider._verify_upstream(source, 'release_reviewer', previous, source_authorization,
        **({'input_root':input_root} if frozen is not None else {}))
    if set(hashes) != expected or artifact['upstream_submission_hashes'] != hashes:
        raise ValueError('rejected release attempt does not bind exact upstream submissions')
    provider._replay_preview(directory, input_root=input_root, preparation_dirs=preparation_dirs)
    preview = ledger._read(directory / 'release-preview.json')
    task = provider.workflow.assignment(directory, 'release_reviewer', input_root=input_root, preparation_dirs=preparation_dirs)
    runtime = (provider.render_assignment(task, input_root=input_root, model_view=provider.view.VERSION, citation_sets=True)
               if frozen is not None else provider.role_prompt(input_root=input_root) + '\n# Frozen assignment\n' + provider._bytes(task).decode())
    original_input = provider._hash({'assignment': task, 'runtime_prompt': runtime,
        'schema': provider.role_schema('release_reviewer', input_root=input_root, citation_sets=frozen is not None),
        'upstream_submission_hashes': hashes})
    if original_input != rejected['input_sha256']:
        raise ValueError('release preview or inputs differ from rejected predecessor request')
    if task['plan_sha256'] != source_authorization['workflow_plan_sha256']:
        raise ValueError('predecessor authorization does not bind workflow')
    checkpoint = dict(schema_version=1, kind='explicit_release_http400_successor',
        registry_path=str(Path(registry_dir).resolve()), source_authorization=copy.deepcopy(source_authorization),
        source_events_sha256=tip, source_rejection_artifact_sha256=rejected_hash,
        imported_upstream=copy.deepcopy(upstream), upstream_submission_hashes=hashes,
        release_preview_sha256=ledger._hash(preview),
        rejected_attempt_id=rejected['attempt_id'], replacement_attempt_id=replacement_attempt_id,
        carried_paid_microusd=state['committed_microusd'], retained_unknown_microusd=state['outstanding_microusd'],
        carried_physical_calls=state['calls_reserved'], authorized_by=authorized_by,
        workflow_path=str(directory), input_root=str(input_root))
    roles = copy.deepcopy(source_authorization['roles'])
    if frozen is not None:
        if (frozen['input_sha256'] != original_input or frozen['upstream_submission_hashes'] != hashes
                or frozen['release_preview_sha256'] != ledger._hash(preview) or frozen['source_events_sha256'] != tip):
            raise ValueError('frozen source proof differs from current replay')
        if not isinstance(replacement_reviewer, dict): raise ValueError('explicit replacement reviewer required')
        if (replacement_reviewer.get('model') != 'openai/gpt-5.6-luna' or replacement_reviewer.get('reasoning_effort') != 'high'
                or any(replacement_reviewer.get(k) != roles['release_reviewer'][k] for k in ('prompt_sha256','schema_sha256','max_attempts','allow_fallbacks'))):
            raise ValueError('replacement must be independent Luna high with unchanged role contract')
        if any(v['model'] == replacement_reviewer['model'] for k,v in roles.items() if k != 'release_reviewer'):
            raise ValueError('replacement reviewer must remain independent')
        roles['release_reviewer'] = copy.deepcopy(replacement_reviewer)
        checkpoint.update(kind=BOUND_KIND, source_runtime=str(Path(source_runtime).resolve()),
                          frozen_source_proof=frozen, replacement_reviewer=copy.deepcopy(replacement_reviewer))
    contracts = provider.execution_contract_hashes(model_view=provider.view.VERSION, citation_sets=True) if frozen is not None else provider.execution_contract_hashes()
    contracts[CONTRACT_KEY] = checkpoint_binding(checkpoint)
    remaining_calls = source_authorization['max_calls'] - state['calls_reserved']
    if remaining_calls < 1:
        raise ValueError('no predecessor call allowance remains')
    authorization = ledger.build_authorization(
        workflow_plan_sha256=source_authorization['workflow_plan_sha256'],
        roles=roles, authorized_by=authorized_by,
        valid_from_utc=valid_from_utc, expires_at_utc=expires_at_utc,
        max_calls=1,
        max_cost_microusd=source_authorization['max_cost_microusd'] - state['committed_microusd'] - state['outstanding_microusd'],
        execution_contract_hashes=contracts)
    checkpoint['successor_authorization_sha256'] = ledger._hash(authorization)
    return authorization, checkpoint


def prepare_successor(registry_dir: Path, source_authorization: dict, *, workflow_dir: Path,
                      input_root: Path, replacement_attempt_id: str, authorized_by: str,
                      valid_from_utc: str, expires_at_utc: str, preparation_dirs=None) -> tuple[dict, dict]:
    """Prepare concrete authority/checkpoint without claim, journal or dispatch."""
    return _prepare(registry_dir, source_authorization, workflow_dir=workflow_dir, input_root=input_root,
        replacement_attempt_id=replacement_attempt_id, authorized_by=authorized_by,
        valid_from_utc=valid_from_utc, expires_at_utc=expires_at_utc, preparation_dirs=preparation_dirs)


def _expected(registry_dir, authorization, checkpoint, *, preparation_dirs=None, allow_completed=False):
    return _prepare(registry_dir, checkpoint['source_authorization'],
        workflow_dir=checkpoint['workflow_path'], input_root=checkpoint['input_root'],
        replacement_attempt_id=checkpoint['replacement_attempt_id'], authorized_by=checkpoint['authorized_by'],
        valid_from_utc=authorization['valid_from_utc'], expires_at_utc=authorization['expires_at_utc'],
        preparation_dirs=preparation_dirs, allow_completed=allow_completed,
        source_runtime=checkpoint.get('source_runtime'), replacement_reviewer=checkpoint.get('replacement_reviewer'))


def claim_successor(registry_dir: Path, authorization: dict, checkpoint: dict, *, preparation_dirs=None) -> Path:
    expected_auth, expected = _expected(registry_dir, authorization, checkpoint,
        preparation_dirs=preparation_dirs, allow_completed=True)
    if expected_auth != authorization or expected != checkpoint:
        raise ValueError('release recovery checkpoint or successor authorization changed')
    registry = Path(registry_dir).resolve()
    path = registry / ('release-http400-successor-' + ledger._hash(checkpoint['source_authorization']) + '.json')
    with ledger._lock(registry / '.lock'):
        source = registry / 'journals' / ledger._hash(checkpoint['source_authorization'])
        if hashlib.sha256((source / 'events.jsonl').read_bytes()).hexdigest() != checkpoint['source_events_sha256']:
            raise ValueError('predecessor journal changed')
        if path.exists() or path.is_symlink():
            if ledger._read(path) != checkpoint:
                raise ValueError('predecessor already claimed by another successor')
        else:
            ledger._write(path, checkpoint)
    return path


class ReleaseRecoveryExecution:
    """One exact release attempt with imported upstream and retained exposure."""
    def __init__(self, registry_dir, authorization, checkpoint_path, *, clock=utc_now, preparation_dirs=None):
        self.checkpoint = ledger._read(Path(checkpoint_path))
        cp = self.checkpoint
        if (cp.get('successor_authorization_sha256') != ledger._hash(authorization)
                or authorization['execution_contract_hashes'].get(CONTRACT_KEY) != checkpoint_binding(cp)):
            raise ValueError('release recovery checkpoint is not bound to successor authority')
        registry = Path(registry_dir).resolve()
        expected_path = registry / ('release-http400-successor-' + ledger._hash(cp['source_authorization']) + '.json')
        if Path(checkpoint_path).resolve() != expected_path or cp['registry_path'] != str(registry):
            raise ValueError('checkpoint is not the unique predecessor claim')
        expected_auth, expected = _expected(registry, authorization, cp,
            preparation_dirs=preparation_dirs, allow_completed=True)
        if expected_auth != authorization or expected != cp:
            raise ValueError('invalid release recovery provenance or carried accounting')
        self.source = ledger.BatchExecutionV2(registry, cp['source_authorization'])
        self.authorization = copy.deepcopy(authorization)
        self.successor = ledger.BatchExecutionV2(registry, authorization, clock=clock)

    @property
    def authorization_sha256(self): return self.successor.authorization_sha256

    @property
    def journal_path(self): return self.successor.journal_path

    def upstream_origin(self, role):
        if role not in ('primary', 'verifier'):
            raise ValueError('unsupported imported role')
        return self.source, self.checkpoint['source_authorization']

    def status(self): return self.successor.status()

    def run(self, role, attempt_id, transport, *, input_sha256, retry_of=None):
        if (role != 'release_reviewer' or attempt_id != self.checkpoint['replacement_attempt_id']
                or retry_of is not None):
            raise ValueError('only the exact authorized replacement release review is permitted')
        return self.successor.run(role, attempt_id, transport, input_sha256=input_sha256)


def verify_bound_release_approval(registry_dir, authorization, checkpoint_path, *, preparation_dirs=None):
    """Read-only approval proof; original stopped controller is never relabeled."""
    from turbo.agents import batch_provider as provider
    from turbo.universe import batch_closure
    cp = ledger._read(Path(checkpoint_path))
    if cp.get('kind') != BOUND_KIND:
        raise ValueError('bound release successor required')
    # Require an existing successor journal before its validating constructor.
    registry = Path(registry_dir).resolve()
    digest = ledger._hash(authorization)
    for name in ('authorization.json','ready.json','events.jsonl','.lock'):
        ledger._regular(registry/'journals'/digest/name)
    engine = ReleaseRecoveryExecution(registry, authorization, checkpoint_path, preparation_dirs=preparation_dirs)
    state = engine.status(); aid = cp['replacement_attempt_id']
    if set(state['requests']) != {aid} or state['requests'][aid]['status'] != 'succeeded':
        raise ValueError('one settled successful replacement review required')
    attempt = state['requests'][aid]
    artifact = provider._load_artifact(engine.journal_path, attempt['response']['output'])
    directory = Path(cp['workflow_path']); inp = Path(cp['input_root'])
    previous = provider._snapshot(directory,input_root=inp,preparation_dirs=preparation_dirs)
    hashes = provider._verify_upstream(engine,'release_reviewer',previous,authorization,input_root=inp)
    role = 'release_reviewer'; config = authorization['roles'][role]
    task = provider.workflow.assignment(directory,role,input_root=inp,preparation_dirs=preparation_dirs)
    schema = provider.role_schema(role,input_root=inp,citation_sets=True)
    runtime = provider.render_assignment(task,input_root=inp,model_view=provider.view.VERSION,citation_sets=True)
    expected_input = provider._hash({'assignment':task,'runtime_prompt':runtime,'schema':schema,'upstream_submission_hashes':hashes})
    receipt = artifact['provider']
    if (attempt['role'] != role or attempt['input_sha256'] != expected_input
            or artifact['authorization_sha256'] != digest or artifact['attempt_id'] != aid
            or artifact['role'] != role or artifact['input_sha256'] != expected_input
            or artifact['upstream_submission_hashes'] != hashes or artifact['valid'] is not True
            or artifact['document'] != previous[role]['document']
            or receipt['role'] != role or receipt['invocation_id'] != 'invocation:'+provider._hash([digest,aid])[:24]
            or receipt['status'] != 'valid' or receipt['requested_model'] != config['model'] or receipt['served_model'] != config['model']
            or receipt['usage'] != attempt['response']['usage'] or receipt['provider_cost_microusd'] != attempt['response']['provider_cost_microusd']
            or not provider.verify_artifact_document(artifact,authorization,input_root=inp)):
        raise ValueError('replacement provider provenance does not substantiate approval')
    _,wrapper,reviewer = batch_closure._approved(directory,root=Path(cp['source_runtime']),input_root=inp,preparation_dirs=preparation_dirs)
    if ledger._hash(wrapper) != cp['release_preview_sha256']:
        raise ValueError('replacement approval preview changed')
    return {'kind':'verified_bound_release_approval','successor_authorization_sha256':digest,
            'predecessor_authorization_sha256':ledger._hash(cp['source_authorization']),
            'review_submission_sha256':reviewer['submission_sha256'],
            'preview_sha256':wrapper['preview_sha256'],'replacement_attempt_id':aid,
            'retained_unknown_microusd':cp['retained_unknown_microusd'],
            'canonical_published':False}
