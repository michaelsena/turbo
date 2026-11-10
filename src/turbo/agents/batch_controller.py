"""Explicit serial role controller. Approval is not publication; no automatic retry."""
from __future__ import annotations
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
from turbo.agents import batch_execution_v2 as ledger, batch_provider as provider, batch_workflow as workflow
from turbo.agents.batch_authorization import utc_now, utc_datetime
from turbo.pipeline_paths import ROOT


def _code():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _git(path, ref):
    return subprocess.check_output(['git','--no-optional-locks','-C',str(path),'rev-parse',ref],text=True,stderr=subprocess.PIPE).strip()


def _paths(path):
    path=Path(path).absolute()
    # The operating system's /tmp alias is resolved by callers; reject other aliases.
    if path != path.resolve(): raise ValueError('controller requires resolved paths')
    for parent in (path,*path.parents):
        if parent.is_symlink(): raise ValueError('controller symlink path')
    return path


def _base(root):
    return ledger._hash(ledger._read(root/'data/generated/latest-graph.json'))


def _journal(registry, auth):
    """Read existing accounting without implicitly claiming a new authority."""
    meta=ledger._registry(registry); digest=ledger._hash(auth)
    claim=registry/'claims'/(digest+'.json'); directory=registry/'journals'/digest
    if not claim.exists() and not claim.is_symlink():
        if directory.exists() or directory.is_symlink(): raise ValueError('unclaimed controller journal')
        return {'requests':{},'calls_reserved':0,'committed_microusd':0,'outstanding_microusd':0}
    expected={'authorization_sha256':digest,'registry_id':meta['registry_id']}
    if ledger._read(claim)!=expected or ledger._read(directory/'ready.json')!=expected or ledger._read(directory/'authorization.json')!=auth:
        raise ValueError('controller journal identity mismatch')
    with ledger._lock(directory/'.lock'):
        ledger._regular(directory/'events.jsonl'); raw=(directory/'events.jsonl').read_bytes()
        if not raw.endswith(b'\n'): raise ValueError('partial controller journal')
        return ledger.replay_events([json.loads(line) for line in raw.splitlines()],auth,registry_id=meta['registry_id'])


def initialize(directory, *, workflow_dir, registry_dir, authorization, input_root, preparation_dirs=None, root=ROOT):
    """Explicitly persist a fresh controller; does not create spend authority or dispatch."""
    directory=_paths(directory); wd=_paths(workflow_dir); registry=_paths(registry_dir); inp=_paths(input_root); root=_paths(root)
    ledger._validate_auth(authorization)
    status=workflow.inspect_workflow(wd,input_root=inp,preparation_dirs=preparation_dirs)
    if status['status']!='primary_pending' or status['completed_roles']:
        raise ValueError('controller initialization requires fresh workflow')
    plan=ledger._read(wd/'plan.json')
    if authorization['workflow_plan_sha256']!=plan['plan_sha256'] or _git(inp,'HEAD^{tree}')!=plan['input_tree']:
        raise ValueError('controller input/authority mismatch')
    if _journal(registry,authorization)['requests']: raise ValueError('controller requires unused authority')
    if any(k.startswith('recovery/') for k in authorization['execution_contract_hashes']):raise ValueError('controller cannot create recovery authority')
    if _base(root)!=_base(inp):raise ValueError('frozen canonical base differs from publication root')
    digest=ledger._hash(authorization)
    manifest={'schema_version':1,'kind':'serial_batch_controller','controller_dir':str(directory),'workflow_dir':str(wd),
        'registry_dir':str(registry),'input_root':str(inp),'input_tree':plan['input_tree'],
        'preparation_dirs':[str(_paths(p)) for p in preparation_dirs] if preparation_dirs is not None else None,
        'root':str(root),'base_pointer_sha256':_base(root),'workflow_plan_sha256':plan['plan_sha256'],
        'authorization':copy.deepcopy(authorization),'authorization_sha256':digest,'controller_code_sha256':_code(),
        'attempt_ids':{role:'controller-'+ledger._hash([digest,role])[:24] for role in workflow.ROLES}}
    manifest['manifest_sha256']=ledger._hash(manifest)
    owner=registry/('controller-'+digest+'.json')
    workflow_owner=registry/('controller-workflow-'+ledger._hash([str(wd),plan['plan_sha256']])+'.json')
    with ledger._lock(registry/'.lock'):
        if owner.exists() or owner.is_symlink():raise ValueError('authority already has controller')
        if workflow_owner.exists() or workflow_owner.is_symlink():raise ValueError('workflow already has controller')
        if directory.exists() or directory.is_symlink():raise ValueError('controller directory already exists')
        directory.mkdir(mode=0o700);(directory/'.lock').touch(mode=0o600)
        ledger._write(directory/'manifest.json',manifest)
        identity={'controller_dir':str(directory),'manifest_sha256':manifest['manifest_sha256']}
        ledger._write(owner,identity)
        ledger._write(workflow_owner,identity)
    return manifest


def _load(directory):
    directory=_paths(directory); manifest=ledger._read(directory/'manifest.json'); digest=manifest.get('manifest_sha256')
    if digest!=ledger._hash({k:v for k,v in manifest.items() if k!='manifest_sha256'}):raise ValueError('controller manifest changed')
    if manifest['controller_dir']!=str(directory) or manifest['controller_code_sha256']!=_code():raise ValueError('controller implementation/path changed')
    auth=manifest['authorization'];ledger._validate_auth(auth)
    if ledger._hash(auth)!=manifest['authorization_sha256']:raise ValueError('controller authorization changed')
    for field in ('workflow_dir','registry_dir','input_root','root'):_paths(manifest[field])
    owner=Path(manifest['registry_dir'])/('controller-'+manifest['authorization_sha256']+'.json')
    if ledger._read(owner)!={'controller_dir':str(directory),'manifest_sha256':digest}:raise ValueError('controller claim changed')
    workflow_owner=Path(manifest['registry_dir'])/('controller-workflow-'+ledger._hash([manifest['workflow_dir'],manifest['workflow_plan_sha256']])+'.json')
    if ledger._read(workflow_owner)!={'controller_dir':str(directory),'manifest_sha256':digest}:raise ValueError('workflow controller claim changed')
    if manifest['attempt_ids']!={r:'controller-'+ledger._hash([manifest['authorization_sha256'],r])[:24] for r in workflow.ROLES}:raise ValueError('controller attempt IDs changed')
    plan=ledger._read(Path(manifest['workflow_dir'])/'plan.json')
    if plan['plan_sha256']!=manifest['workflow_plan_sha256'] or _git(Path(manifest['input_root']),'HEAD^{tree}')!=manifest['input_tree']:
        raise ValueError('controller frozen input changed')
    for path in manifest['preparation_dirs'] or []:_paths(path)
    _release_binding(manifest)
    return manifest


def _release_binding(m):
    local=Path(m['controller_dir'])/'release-config.json'
    external=Path(m['registry_dir'])/('controller-release-'+m['authorization_sha256']+'.json')
    if not local.exists() and not external.exists():return None
    value=ledger._read(local)
    digest=ledger._hash(value['config'])
    if value['config_sha256']!=digest or ledger._read(external)!={'manifest_sha256':m['manifest_sha256'],'config_sha256':digest}:
        raise ValueError('release config binding changed')
    return value


def _verify_submissions(m, records):
    previous=provider._snapshot(Path(m['workflow_dir']),**_options(m))
    journal=Path(m['registry_dir'])/'journals'/m['authorization_sha256']
    for role,envelope in previous.items():
        aid=m['attempt_ids'][role]; attempt=records[aid]
        artifact=provider._load_artifact(journal,attempt['response']['output']); receipt=artifact['provider']
        raw=base64.b64decode(artifact['output_base64'],validate=True)
        if (artifact['authorization_sha256']!=m['authorization_sha256'] or artifact['attempt_id']!=aid
            or artifact['role']!=role or artifact['input_sha256']!=attempt['input_sha256']
            or artifact['upstream_submission_hashes']!=provider._upstream_hashes(role,previous)
            or artifact['valid'] is not True or artifact['document']!=envelope['document']
            or provider._strict_json(raw)!=artifact['document'] or hashlib.sha256(raw).hexdigest()!=receipt['body_sha256']
            or receipt['status']!='valid' or receipt['requested_model']!=m['authorization']['roles'][role]['model']
            or receipt['served_model']!=m['authorization']['roles'][role]['model']
            or receipt['usage']!=attempt['response']['usage']
            or receipt['provider_cost_microusd']!=attempt['response']['provider_cost_microusd']):
            raise ValueError('controller submission lacks exact provider provenance')


def _options(m):
    return {'input_root':Path(m['input_root']),'preparation_dirs':m['preparation_dirs']}


def _state(m, *, clock):
    from turbo.agents import batch_publication
    publication = batch_publication.inspect(m)
    if publication is not None:
        return publication
    if _base(Path(m['root']))!=m['base_pointer_sha256']:return {'state':'STOPPED','reason':'canonical_base_changed'}
    journal=_journal(Path(m['registry_dir']),m['authorization'])
    expected=m['attempt_ids']; records=journal['requests']
    for aid,attempt in records.items():
        if attempt['role'] not in expected or expected[attempt['role']]!=aid:return {'state':'STOPPED','reason':'unmanaged_attempt'}
        if attempt['status']!='succeeded':return {'state':'STOPPED','reason':'attempt_'+attempt['status'],'role':attempt['role'],'attempt_id':aid}
    info=workflow.inspect_workflow(Path(m['workflow_dir']),**_options(m))
    for role in info['completed_roles']:
        if expected[role] not in records:return {'state':'STOPPED','reason':'submission_without_managed_attempt','role':role}
    _verify_submissions(m,records)
    missing=[r for r in workflow.ROLES if expected[r] in records and r not in info['completed_roles']]
    if missing:return {'state':'READY','role':missing[0],'replay_only':True}
    if info['status']=='approved':return {'state':'APPROVED_PENDING_PUBLICATION','review_approved':True,'canonical_published':False}
    if info['status']=='rejected':return {'state':'STOPPED','reason':'review_rejected'}
    now=utc_datetime(clock()); auth=m['authorization']
    if not utc_datetime(auth['valid_from_utc'])<=now<utc_datetime(auth['expires_at_utc']):return {'state':'STOPPED','reason':'authorization_outside_interval'}
    roles={'primary_pending':'primary','verification_pending':'verifier','adjudication_pending':'adjudicator','release_pending':'release_reviewer'}
    role=next((r for r in ('escalation_a','escalation_b') if r not in info['completed_roles']),None) if info['status']=='escalation_pending' else roles.get(info['status'])
    if role is None:raise ValueError('unknown controller workflow stage')
    if journal['calls_reserved']>=auth['max_calls'] or journal['committed_microusd']+ledger._reservation(auth,role)>auth['max_cost_microusd']:
        return {'state':'STOPPED','reason':'authorization_exhausted','role':role}
    if role=='release_reviewer' and not (Path(m['controller_dir'])/'release-config.json').exists():
        return {'state':'WAITING_RELEASE_CONFIG','role':role}
    return {'state':'READY','role':role,'replay_only':False}


def status(directory, *, clock=utc_now):
    """Read-only status: does not create provider journals, restore submissions or dispatch."""
    m=_load(directory)
    with ledger._lock(Path(m['controller_dir'])/'.lock'):
        m=_load(directory)
        return {**_state(m,clock=clock),'manifest_sha256':m['manifest_sha256']}


def _record(directory, state):
    # Status is derived, not an authority or a journal replacement.
    target=directory/'status.json';tmp=directory/'status.pending'
    if tmp.exists() or tmp.is_symlink():raise ValueError('partial controller status requires inspection')
    with tmp.open('xb') as h:
        h.write(ledger.canonical_bytes(state));h.flush();os.fsync(h.fileno())
    os.replace(tmp,target);ledger._sync(directory)


def execute(directory, *, api_key=None, release_config=None, clock=utc_now, transport=None):
    """Explicit one-workflow execution. Stops before canonical publication."""
    directory=_paths(directory)
    with ledger._lock(directory/'.lock'):
        m=_load(directory)
        binding=directory/'release-config.json'
        if release_config is not None:
            config=ledger._read(_paths(release_config)); value={'config':config,'config_sha256':ledger._hash(config)}
            if binding.exists() or binding.is_symlink():
                if ledger._read(binding)!=value:raise ValueError('release config already bound')
            else:
                with ledger._lock(Path(m['registry_dir'])/'.lock'):
                    external=Path(m['registry_dir'])/('controller-release-'+m['authorization_sha256']+'.json')
                    if external.exists() or external.is_symlink():raise ValueError('partial release config binding')
                    ledger._write(binding,value)
                    ledger._write(external,{'manifest_sha256':m['manifest_sha256'],'config_sha256':value['config_sha256']})
        for _ in range(len(workflow.ROLES)+2):
            m=_load(directory);state=_state(m,clock=clock);_record(directory,state)
            if state['state']!='READY':return state
            role=state['role']
            try:
                if role=='release_reviewer' and not state['replay_only']:
                    from turbo.universe.batch_closure import prepare_batch_release
                    value=ledger._read(binding)
                    if ledger._hash(value['config'])!=value['config_sha256']:raise ValueError('release config changed')
                    preview=Path(m['workflow_dir'])/'release-preview.json'
                    if preview.exists():
                        if ledger._read(preview)['preview']['config']!=value['config']:raise ValueError('release preview config changed')
                    else:prepare_batch_release(Path(m['workflow_dir']),value['config'],root=Path(m['root']),**_options(m))
                # Provider supplies exact replay/provenance validation; the same ID cannot resend.
                result=provider.run_batch_role(Path(m['workflow_dir']),Path(m['registry_dir']),m['authorization'],role,m['attempt_ids'][role],
                    api_key=api_key,transport=transport,clock=clock,**_options(m))
            except Exception:
                stopped={'state':'STOPPED','reason':'role_preflight_or_execution_error','role':role,'attempt_id':m['attempt_ids'][role]}
                _record(directory,stopped);return stopped
            if result['status']!='succeeded':
                stopped={'state':'STOPPED','reason':'attempt_'+result['status'],'role':role,'attempt_id':m['attempt_ids'][role]}
                _record(directory,stopped);return stopped
        raise ValueError('controller transition bound exceeded')
