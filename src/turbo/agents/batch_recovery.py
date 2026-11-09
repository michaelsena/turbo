"""Explicit HTTP-402 successor checkpoint. Never releases unknown exposure.

V2 authorization, implementation and journals remain unchanged. The successor
imports one accepted primary and carries the parent's charges, reservations and
physical calls by reducing its own immutable limits. This is not a retry loop.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from turbo.agents import batch_execution_v2 as ledger
from turbo.agents.batch_authorization import canonical_bytes, utc_now

# Replaced below with the exact previously released provider contract.
LEGACY_CONTRACT = {"schemas/graph-release-config.schema.json": "7b06fc7565bc52ad639a3148c1a175e5512b51ba789ef311d74b47630fc0ecc3", "src/turbo/agents/batch_authorization.py": "4165a4aae65e3c225149a363050cf4bd48daf4551aadca80630462868d08de9c", "src/turbo/agents/batch_output.py": "7b8447ecef2b94a81fc83d3045acf295cbe2e82c952db02dcf4b19968ee19433", "src/turbo/agents/batch_provider.py": "99ce55b76306d40b383942cc16022fc35c20b805165fbaef2c7b3edf0893b712", "src/turbo/agents/boundary_harness.py": "e138491ec7038e4e0a3e14b00e136149a972d61782e5702726dd0171ecb14c1e", "src/turbo/agents/openrouter_attempt.py": "6da33cf46918ff3c4c4b818268f9c4b09e851796a1f8a087bbdc9165574156f1", "src/turbo/agents/openrouter_runner.py": "1e25d49ef2cd0d1927909d4e36138c00a88255f821139c759abf193f621afc31", "src/turbo/agents/runtime.py": "ecad21221a50d6b00f69357510f20b8cd8877382475e2c8046a14038a699980f", "src/turbo/universe/batch_closure.py": "f20e549ba55e591b2a6f02e008162d9c8557913ee0e278078903b8e815f3940c", "src/turbo/universe/graph_release.py": "542aa4929b342cdb0f340d44ba8cf4ddb5b53c6083a4f80a1eab6e0656aa4ff3"}


def checkpoint_binding(checkpoint):
    return ledger._hash({k: v for k, v in checkpoint.items() if k != 'successor_authorization_sha256'})


def _source(registry, authorization):
    from turbo.agents import batch_provider as provider
    if authorization['execution_contract_hashes'] not in (LEGACY_CONTRACT, provider.execution_contract_hashes()):
        raise ValueError('unsupported predecessor execution contract')
    # V2's constructor initializes missing claims. Recovery inspection must never
    # create a predecessor, so require the complete existing binding first.
    registry = Path(registry).resolve(strict=True)
    ledger._registry(registry)
    digest = ledger._hash(authorization)
    ledger._regular(registry / 'claims' / (digest + '.json'))
    for name in ('authorization.json', 'ready.json', 'events.jsonl', '.lock'):
        ledger._regular(registry / 'journals' / digest / name)
    source = ledger.BatchExecutionV2(registry, authorization)
    state = source.status()
    primary = [a for a in state['requests'].values() if a['role'] == 'primary' and a['status'] == 'succeeded']
    rejected = [a for a in state['requests'].values() if a['role'] == 'verifier' and a['status'] == 'unresolved']
    if len(state['requests']) != 2 or len(primary) != 1 or len(rejected) != 1:
        raise ValueError('recovery requires exactly one accepted primary and one unresolved verifier')
    attempt = rejected[0]
    name = 'provider-' + hashlib.sha256(attempt['attempt_id'].encode()).hexdigest() + '.json'
    path = source.journal_path / name
    ledger._regular(path)
    raw = path.read_bytes()
    artifact = provider._load_artifact(source.journal_path, {'artifact': name, 'artifact_sha256': hashlib.sha256(raw).hexdigest()})
    result = artifact['provider']
    if (artifact['authorization_sha256'] != source.authorization_sha256
            or artifact['attempt_id'] != attempt['attempt_id'] or artifact['role'] != 'verifier'
            or artifact['input_sha256'] != attempt['input_sha256'] or artifact['valid'] is not False
            or artifact['document'] is not None or artifact['output_base64'] is not None
            or result['http_status'] != 402 or result['status'] != 'invalid'
            or result['error_stage'] != 'http' or result['transport_attempted'] is not True
            or any(result.get(k) is not None for k in ('generation_id', 'served_model', 'usage', 'provider_cost_microusd'))):
        raise ValueError('only a recorded non-generation HTTP 402 is eligible')
    ledger._digest(result['response_sha256'])
    parent_hash = hashlib.sha256((source.journal_path / 'events.jsonl').read_bytes()).hexdigest()
    return source, state, primary[0], attempt, parent_hash, hashlib.sha256(raw).hexdigest()


def prepare_successor(registry_dir: Path, source_authorization: dict, *, workflow_dir: Path,
                      input_root: Path, replacement_attempt_id: str, authorized_by: str,
                      valid_from_utc: str, expires_at_utc: str, preparation_dirs=None) -> tuple[dict, dict]:
    """Prepare proposed authority/checkpoint; no claim, journal, or provider call."""
    from turbo.agents import batch_provider as provider
    source, state, primary, rejected, tip, rejected_hash = _source(registry_dir, source_authorization)
    ledger._identifier(replacement_attempt_id)
    if replacement_attempt_id in state['requests'] or not authorized_by.strip():
        raise ValueError('new exact replacement and explicit operator required')
    previous = provider._snapshot(Path(workflow_dir).resolve(), input_root=Path(input_root).resolve(), preparation_dirs=preparation_dirs)
    if set(previous) != {'primary'}:
        raise ValueError('recovery only before verifier acceptance')
    provider._verify_upstream(source, 'verifier', previous, source_authorization)
    held = state['outstanding_microusd']
    carried = state['committed_microusd'] + held
    checkpoint = dict(schema_version=1, kind='explicit_http402_successor',
        registry_path=str(Path(registry_dir).resolve()), source_authorization=copy.deepcopy(source_authorization),
        source_events_sha256=tip,
        source_rejection_artifact_sha256=rejected_hash, imported_primary=copy.deepcopy(primary),
        rejected_attempt_id=rejected['attempt_id'], replacement_attempt_id=replacement_attempt_id,
        carried_paid_microusd=state['committed_microusd'], retained_unknown_microusd=held,
        carried_physical_calls=state['calls_reserved'], authorized_by=authorized_by,
        workflow_path=str(Path(workflow_dir).resolve()), input_root=str(Path(input_root).resolve()))
    contracts = provider.execution_contract_hashes()
    contracts['recovery/checkpoint-v1'] = checkpoint_binding(checkpoint)
    authorization = ledger.build_authorization(
        workflow_plan_sha256=source_authorization['workflow_plan_sha256'],
        roles=source_authorization['roles'], authorized_by=authorized_by,
        valid_from_utc=valid_from_utc, expires_at_utc=expires_at_utc,
        max_calls=source_authorization['max_calls'] - state['calls_reserved'],
        max_cost_microusd=source_authorization['max_cost_microusd'] - carried,
        execution_contract_hashes=contracts)
    checkpoint['successor_authorization_sha256'] = ledger._hash(authorization)
    return authorization, checkpoint


def claim_successor(registry_dir: Path, authorization: dict, checkpoint: dict, *, preparation_dirs=None) -> Path:
    """Claim exactly one successor under the parent registry lock, idempotently."""
    expected_auth, expected = prepare_successor(registry_dir, checkpoint['source_authorization'],
        workflow_dir=Path(checkpoint['workflow_path']), input_root=Path(checkpoint['input_root']),
        replacement_attempt_id=checkpoint['replacement_attempt_id'], authorized_by=checkpoint['authorized_by'],
        valid_from_utc=authorization['valid_from_utc'], expires_at_utc=authorization['expires_at_utc'],
        preparation_dirs=preparation_dirs)
    if expected_auth != authorization or expected != checkpoint:
        raise ValueError('recovery checkpoint or successor authorization changed')
    registry = Path(registry_dir).resolve()
    path = registry / ('http402-successor-' + ledger._hash(checkpoint['source_authorization']) + '.json')
    with ledger._lock(registry / '.lock'):
        # Recheck exact tip while claiming. Parent is already blocked unresolved.
        source = registry / 'journals' / ledger._hash(checkpoint['source_authorization'])
        if hashlib.sha256((source / 'events.jsonl').read_bytes()).hexdigest() != checkpoint['source_events_sha256']:
            raise ValueError('predecessor journal changed')
        if path.exists() or path.is_symlink():
            if ledger._read(path) != checkpoint:
                raise ValueError('predecessor already claimed by another successor')
        else:
            ledger._write(path, checkpoint)
    return path


class RecoveryExecution:
    """Validated source provenance plus a separately budgeted V2 successor."""
    def __init__(self, registry_dir, authorization, checkpoint_path, *, clock=utc_now):
        self.checkpoint = ledger._read(Path(checkpoint_path))
        cp = self.checkpoint
        registry = Path(registry_dir).resolve()
        expected = registry / ('http402-successor-' + ledger._hash(cp['source_authorization']) + '.json')
        if Path(checkpoint_path).resolve() != expected or cp['registry_path'] != str(registry):
            raise ValueError('checkpoint is not the unique predecessor claim')
        source, state, primary, rejected, tip, rejected_hash = _source(registry, cp['source_authorization'])
        if (cp['schema_version'] != 1 or cp['kind'] != 'explicit_http402_successor'
                or cp['successor_authorization_sha256'] != ledger._hash(authorization)
                or authorization['execution_contract_hashes'].get('recovery/checkpoint-v1') != checkpoint_binding(cp)
                or authorization['authorized_by'] != cp['authorized_by']
                or cp['source_events_sha256'] != tip or cp['source_rejection_artifact_sha256'] != rejected_hash
                or cp['imported_primary'] != primary or cp['rejected_attempt_id'] != rejected['attempt_id']
                or cp['carried_paid_microusd'] != state['committed_microusd']
                or cp['retained_unknown_microusd'] != state['outstanding_microusd']
                or cp['carried_physical_calls'] != state['calls_reserved']
                or authorization['roles'] != cp['source_authorization']['roles']
                or authorization['workflow_plan_sha256'] != cp['source_authorization']['workflow_plan_sha256']
                or authorization['max_calls'] + state['calls_reserved'] != cp['source_authorization']['max_calls']
                or authorization['max_cost_microusd'] + state['committed_microusd'] + state['outstanding_microusd'] != cp['source_authorization']['max_cost_microusd']):
            raise ValueError('invalid recovery provenance or carried accounting')
        self.source = source
        self.authorization = copy.deepcopy(authorization)
        self.successor = ledger.BatchExecutionV2(registry, authorization, clock=clock)

    @property
    def authorization_sha256(self): return self.successor.authorization_sha256

    @property
    def journal_path(self): return self.successor.journal_path

    def upstream_origin(self, role):
        return (self.source, self.checkpoint['source_authorization']) if role == 'primary' else (self.successor, self.authorization)

    def status(self):
        return self.successor.status()

    def run(self, role, attempt_id, transport, *, input_sha256, retry_of=None):
        if role == 'primary' or attempt_id in self.source.status()['requests']:
            raise ValueError('cannot redispatch imported primary or reuse predecessor attempt IDs')
        if role == 'verifier' and (attempt_id != self.checkpoint['replacement_attempt_id'] or retry_of is not None):
            raise ValueError('only the exact authorized replacement verifier is permitted')
        return self.successor.run(role, attempt_id, transport, input_sha256=input_sha256, retry_of=retry_of)
