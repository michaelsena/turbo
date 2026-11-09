"""Explicit one-call corrected review after the pinned HTTP400/diagnostic chain.

No old journal is edited. All observed charges and held exposure remain carried.
This is a separately approved aggregate budget amendment, never an automatic retry.
"""
from __future__ import annotations
import copy
import hashlib
from pathlib import Path
from turbo.agents import batch_execution_v2 as ledger
from turbo.agents import batch_release_recovery as prior
from turbo.agents.batch_authorization import utc_now

CONTRACT_KEY = 'recovery/corrected-release-v1'
DIAGNOSTIC_CLAIMS = ('issue57-diagnostic-single-claim.json', 'issue57-adapted-single-claim.json')
PINNED_PROVIDER_CONTRACT = {'src/turbo/agents/batch_release_recovery.py': '6445e9c54fcaa07bf1e619413570b1f5f4c7fe789f155c206e1cbabdd7085554', 'src/turbo/agents/model_view.py': '47e777c62f7e5e2b1a7971ccf38dca69d334993fc6655823031bed49603c4567', 'src/turbo/agents/batch_recovery.py': 'b66af6d6d1cc57f2c8d543c6f244f83c69a4167b0c1cc30ede5d7e6b7543ed2b', 'src/turbo/agents/batch_provider.py': '713fe78b182f27018e2164d400c2cbe2aa772eccb140c5e0aa1c87f89cb2cb82', 'src/turbo/agents/openrouter_attempt.py': 'a3bdcefa8ecece48d998891f128038301e096953bf76552c8cf0366de3bd33b8', 'src/turbo/agents/openrouter_runner.py': '1e25d49ef2cd0d1927909d4e36138c00a88255f821139c759abf193f621afc31', 'src/turbo/agents/batch_output.py': '7b8447ecef2b94a81fc83d3045acf295cbe2e82c952db02dcf4b19968ee19433', 'src/turbo/agents/batch_authorization.py': '4165a4aae65e3c225149a363050cf4bd48daf4551aadca80630462868d08de9c', 'src/turbo/agents/runtime.py': 'ecad21221a50d6b00f69357510f20b8cd8877382475e2c8046a14038a699980f', 'src/turbo/agents/boundary_harness.py': 'e138491ec7038e4e0a3e14b00e136149a972d61782e5702726dd0171ecb14c1e', 'src/turbo/universe/batch_closure.py': 'f20e549ba55e591b2a6f02e008162d9c8557913ee0e278078903b8e815f3940c', 'src/turbo/universe/graph_release.py': '542aa4929b342cdb0f340d44ba8cf4ddb5b53c6083a4f80a1eab6e0656aa4ff3', 'schemas/graph-release-config.schema.json': '7b06fc7565bc52ad639a3148c1a175e5512b51ba789ef311d74b47630fc0ecc3'}


def checkpoint_binding(value):
    return ledger._hash({k:v for k,v in value.items() if k != 'successor_authorization_sha256'})


def _journal(registry, digest):
    ledger._digest(digest)
    ledger._regular(registry / 'claims' / (digest + '.json'))
    path = registry / 'journals' / digest
    for name in ('authorization.json','ready.json','events.jsonl','.lock'):
        ledger._regular(path / name)
    auth = ledger._read(path / 'authorization.json')
    if ledger._hash(auth) != digest: raise ValueError('source authority identity mismatch')
    engine = ledger.BatchExecutionV2(registry, auth)
    return auth, engine, engine.status()


def _tip(engine):
    return hashlib.sha256((engine.journal_path / 'events.jsonl').read_bytes()).hexdigest()


def _totals(states):
    return (sum(s['committed_microusd'] for s in states),
            sum(s['outstanding_microusd'] for s in states),
            sum(s['calls_reserved'] for s in states))


def _rejection(engine, state, expected_input, expected_upstream):
    from turbo.agents import batch_provider as provider
    rows=list(state['requests'].values())
    if len(rows)!=1 or rows[0]['role']!='release_reviewer' or rows[0]['status']!='unresolved':
        raise ValueError('prior successor must contain only one unresolved review')
    attempt=rows[0]
    path=engine.journal_path / ('provider-'+hashlib.sha256(attempt['attempt_id'].encode()).hexdigest()+'.json')
    ledger._regular(path); raw=path.read_bytes()
    artifact=provider._load_artifact(engine.journal_path,{'artifact':path.name,'artifact_sha256':hashlib.sha256(raw).hexdigest()})
    result=artifact['provider']
    if (attempt['input_sha256']!=expected_input or artifact['input_sha256']!=expected_input
        or artifact['authorization_sha256']!=engine.authorization_sha256
        or artifact['attempt_id']!=attempt['attempt_id'] or artifact['role']!='release_reviewer'
        or artifact['upstream_submission_hashes']!=expected_upstream
        or artifact['valid'] is not False or artifact['document'] is not None or artifact['output_base64'] is not None
        or result['http_status']!=400 or result['status']!='invalid' or result['error_stage']!='http'
        or result['transport_attempted'] is not True
        or any(result.get(k) is not None for k in ('generation_id','served_model','served_provider','usage','provider_cost_microusd'))):
        raise ValueError('prior successor is not the same rejected request')
    ledger._digest(result['response_sha256'])
    return hashlib.sha256(raw).hexdigest()


def _sources(registry, source_authorization, workflow_dir, input_root, preparation_dirs=None):
    from turbo.agents import batch_provider as provider
    if source_authorization['execution_contract_hashes'] != prior.PREDECESSOR_CONTRACT:
        raise ValueError('unsupported original execution contract')
    registry=Path(registry).resolve(strict=True)
    source,state,upstream,rejected,tip,artifact_hash,artifact=prior._source(registry,source_authorization)
    old_path=registry / ('release-http400-successor-'+ledger._hash(source_authorization)+'.json')
    old=ledger._read(old_path)
    if old['source_authorization']!=source_authorization or old['workflow_path']!=str(Path(workflow_dir).resolve()) or old['input_root']!=str(Path(input_root).resolve()):
        raise ValueError('prior claim input paths or authority differ')
    next_auth,next_engine,next_state=_journal(registry,old['successor_authorization_sha256'])
    expected_auth,expected=prior._prepare(registry,source_authorization,workflow_dir=workflow_dir,input_root=input_root,
        replacement_attempt_id=old['replacement_attempt_id'],authorized_by=old['authorized_by'],
        valid_from_utc=next_auth['valid_from_utc'],expires_at_utc=next_auth['expires_at_utc'],
        preparation_dirs=preparation_dirs,allow_completed=True)
    expected_auth['execution_contract_hashes']={**PINNED_PROVIDER_CONTRACT,prior.CONTRACT_KEY:prior.checkpoint_binding(expected)}
    expected['successor_authorization_sha256']=ledger._hash(expected_auth)
    if expected_auth!=next_auth or expected!=old: raise ValueError('prior successor claim does not replay')
    rejection_hash=_rejection(next_engine,next_state,rejected['input_sha256'],old['upstream_submission_hashes'])
    auths=[source_authorization,next_auth];engines=[source,next_engine];states=[state,next_state]
    claim_hashes={old_path.name:ledger._hash(old)}
    for ordinal,name in enumerate(DIAGNOSTIC_CLAIMS):
        claim=ledger._read(registry/name); plan=claim['plan']
        paid,held,calls=_totals(states)
        if (plan['purpose']!='diagnostic_only_never_release'
            or plan.get('adaptation')!=(None if ordinal==0 else 'omit_only_findings_maxItems_google_probe')
            or plan['source_authorizations']!=[ledger._hash(a) for a in auths]
            or plan['source_event_hashes']!=[_tip(e) for e in engines]
            or plan['carried_exposure_microusd']!=paid+held or plan['carried_calls']!=calls):
            raise ValueError('diagnostic claim omits or changes preceding exposure')
        auth,engine,diag_state=_journal(registry,claim['authorization_sha256'])
        rows=list(diag_state['requests'].values())
        if (auth['execution_contract_hashes']!=PINNED_PROVIDER_CONTRACT
            or auth['workflow_plan_sha256']!=ledger._hash(plan) or auth['max_calls']!=1
            or auth['max_cost_microusd']!=plan['max_probe_cost_microusd']
            or paid+held+auth['max_cost_microusd']>source_authorization['max_cost_microusd']
            or calls+1>source_authorization['max_calls']
            or len(rows)!=1 or rows[0]['role']!='release_reviewer' or rows[0]['status']!='unresolved'
            or rows[0]['input_sha256']!=ledger._hash(plan)):
            raise ValueError('invalid diagnostic authority or journal')
        auths.append(auth);engines.append(engine);states.append(diag_state);claim_hashes[name]=ledger._hash(claim)
    return registry,auths,engines,states,old,claim_hashes,artifact_hash,rejection_hash


def prepare_successor(registry_dir, source_authorization, *, workflow_dir, input_root,
                      replacement_attempt_id, authorized_by, valid_from_utc, expires_at_utc,
                      aggregate_max_cost_microusd, aggregate_max_calls, preparation_dirs=None):
    """Read-only proposed amendment. Caller must obtain explicit new aggregate approval."""
    from turbo.agents import batch_provider as provider
    registry,auths,engines,states,old,claims,first_error,next_error=_sources(registry_dir,source_authorization,workflow_dir,input_root,preparation_dirs)
    ledger._identifier(replacement_attempt_id)
    if not isinstance(authorized_by,str) or not authorized_by.strip(): raise ValueError('explicit operator approval required')
    if any(replacement_attempt_id in s['requests'] for s in states): raise ValueError('replacement attempt already used')
    paid,held,calls=_totals(states)
    if (type(aggregate_max_calls) is not int or aggregate_max_calls!=calls+1
        or type(aggregate_max_cost_microusd) is not int or aggregate_max_cost_microusd<=paid+held):
        raise ValueError('explicit aggregate allowance must cover exactly one further call')
    known={ledger._hash(a) for a in auths}
    existing={p.stem for p in (registry/'claims').glob('*.json')}
    repair_path=registry/('corrected-release-successor-'+ledger._hash(source_authorization)+'.json')
    if repair_path.exists() or repair_path.is_symlink():
        known.add(ledger._read(repair_path)['successor_authorization_sha256'])
    if existing-known: raise ValueError('unaccounted authority in source registry')
    checkpoint=dict(schema_version=1,kind='explicit_corrected_release_successor',registry_path=str(registry),
        source_authorization=copy.deepcopy(source_authorization),source_authorization_hashes=[ledger._hash(a) for a in auths],
        source_events_sha256=[_tip(e) for e in engines],source_claim_hashes=claims,
        source_rejection_artifact_hashes=[first_error,next_error],release_preview_sha256=old['release_preview_sha256'],
        upstream_submission_hashes=old['upstream_submission_hashes'],workflow_path=str(Path(workflow_dir).resolve()),
        input_root=str(Path(input_root).resolve()),replacement_attempt_id=replacement_attempt_id,authorized_by=authorized_by,
        carried_paid_microusd=paid,retained_unknown_microusd=held,carried_physical_calls=calls,
        aggregate_max_cost_microusd=aggregate_max_cost_microusd,aggregate_max_calls=aggregate_max_calls)
    contracts=provider.execution_contract_hashes();contracts[CONTRACT_KEY]=checkpoint_binding(checkpoint)
    auth=ledger.build_authorization(workflow_plan_sha256=source_authorization['workflow_plan_sha256'],roles=source_authorization['roles'],
        authorized_by=authorized_by,valid_from_utc=valid_from_utc,expires_at_utc=expires_at_utc,max_calls=1,
        max_cost_microusd=aggregate_max_cost_microusd-paid-held,execution_contract_hashes=contracts)
    if ledger._reservation(auth,'release_reviewer')>auth['max_cost_microusd']:
        raise ValueError('amended aggregate budget cannot reserve corrected review')
    checkpoint['successor_authorization_sha256']=ledger._hash(auth)
    return auth,checkpoint


def _expected(registry,auth,cp,preparation_dirs=None):
    return prepare_successor(registry,cp['source_authorization'],workflow_dir=cp['workflow_path'],input_root=cp['input_root'],
        replacement_attempt_id=cp['replacement_attempt_id'],authorized_by=cp['authorized_by'],valid_from_utc=auth['valid_from_utc'],
        expires_at_utc=auth['expires_at_utc'],aggregate_max_cost_microusd=cp['aggregate_max_cost_microusd'],
        aggregate_max_calls=cp['aggregate_max_calls'],preparation_dirs=preparation_dirs)



def _guard_sources(registry, checkpoint):
    allowed=set(checkpoint['source_authorization_hashes']) | {checkpoint['successor_authorization_sha256']}
    if {p.stem for p in (registry/'claims').glob('*.json')} - allowed:
        raise ValueError('unaccounted authority in source registry')
    for digest,tip in zip(checkpoint['source_authorization_hashes'],checkpoint['source_events_sha256']):
        if hashlib.sha256((registry/'journals'/digest/'events.jsonl').read_bytes()).hexdigest()!=tip:
            raise ValueError('source journal changed')
    for name,digest in checkpoint['source_claim_hashes'].items():
        if ledger._hash(ledger._read(registry/name))!=digest:raise ValueError('source sidecar changed')


def claim_successor(registry_dir,authorization,checkpoint,*,preparation_dirs=None):
    if authorization['execution_contract_hashes'].get(CONTRACT_KEY)!=checkpoint_binding(checkpoint) or ledger._hash(authorization)!=checkpoint.get('successor_authorization_sha256'):
        raise ValueError('repair checkpoint is not bound to authority')
    expected_auth,expected=_expected(registry_dir,authorization,checkpoint,preparation_dirs)
    if expected_auth!=authorization or expected!=checkpoint:raise ValueError('repair amendment changed')
    registry=Path(registry_dir).resolve();path=registry/('corrected-release-successor-'+ledger._hash(checkpoint['source_authorization'])+'.json')
    with ledger._lock(registry/'.lock'):
        _guard_sources(registry,checkpoint)
        if path.exists() or path.is_symlink():
            if ledger._read(path)!=checkpoint:raise ValueError('corrected review already claimed')
        else:ledger._write(path,checkpoint)
    return path


class RequestRepairExecution:
    def __init__(self,registry_dir,authorization,checkpoint_path,*,clock=utc_now,preparation_dirs=None):
        cp=ledger._read(Path(checkpoint_path))
        if authorization['execution_contract_hashes'].get(CONTRACT_KEY)!=checkpoint_binding(cp) or ledger._hash(authorization)!=cp.get('successor_authorization_sha256'):
            raise ValueError('repair checkpoint is not bound to authority')
        registry=Path(registry_dir).resolve()
        expected_path=registry/('corrected-release-successor-'+ledger._hash(cp['source_authorization'])+'.json')
        if Path(checkpoint_path).resolve()!=expected_path or cp['registry_path']!=str(registry):raise ValueError('not the unique corrected review claim')
        expected_auth,expected=_expected(registry,authorization,cp,preparation_dirs)
        if expected_auth!=authorization or expected!=cp:raise ValueError('repair provenance changed')
        self.checkpoint=cp;self.authorization=copy.deepcopy(authorization)
        self._registry=registry;self._checkpoint_path=expected_path
        self.source=ledger.BatchExecutionV2(registry,cp['source_authorization'])
        self.successor=ledger.BatchExecutionV2(registry,authorization,clock=clock)
    @property
    def authorization_sha256(self):return self.successor.authorization_sha256
    @property
    def journal_path(self):return self.successor.journal_path
    def status(self):return self.successor.status()
    def upstream_origin(self,role):
        if role not in ('primary','verifier'):raise ValueError('unsupported imported role')
        return self.source,self.checkpoint['source_authorization']
    def run(self,role,attempt_id,transport,*,input_sha256,retry_of=None):
        if role!='release_reviewer' or attempt_id!=self.checkpoint['replacement_attempt_id'] or retry_of is not None:
            raise ValueError('only the exact corrected review is authorized')
        # V2.run uses journal locks only. Keep registry lock through reservation
        # and transport so another authority cannot enter this aggregate scope.
        with ledger._lock(self._registry/'.lock'):
            if ledger._read(self._checkpoint_path)!=self.checkpoint:raise ValueError('repair claim changed')
            _guard_sources(self._registry,self.checkpoint)
            return self.successor.run(role,attempt_id,transport,input_sha256=input_sha256)
