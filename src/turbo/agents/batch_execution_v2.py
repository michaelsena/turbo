"""Explicit live V2 accounting: one trusted registry, one shared role budget.

V1 simulation contracts are untouched. Workflow eligibility and output acceptance
belong to the caller; this primitive enforces physical-attempt accounting only.
Local authorization documents are trusted operator records, not signed credentials.
"""
from __future__ import annotations
from contextlib import contextmanager
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable
import uuid
from jsonschema import Draft202012Validator
from turbo.agents.batch_authorization import canonical_bytes, utc_datetime, utc_now
from turbo.agents.batch_output import _strict_json

SCHEMA = Path(__file__).resolve().parents[3] / 'schemas/batch-authorization-v2.schema.json'
ROLES = ('primary', 'verifier', 'escalation_a', 'escalation_b', 'adjudicator', 'release_reviewer')
ZERO = '0' * 64


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _contract() -> dict:
    return {'schema_sha256': hashlib.sha256(SCHEMA.read_bytes()).hexdigest(),
            'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def _identifier(value: Any) -> None:
    if not isinstance(value, str) or not value or len(value) > 256 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-' for c in value):
        raise ValueError('invalid attempt identifier')


def _digest(value: Any) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('invalid SHA256')


def _validate_auth(auth: dict) -> None:
    errors = list(Draft202012Validator(json.loads(SCHEMA.read_text())).iter_errors(auth))
    if errors: raise ValueError('invalid V2 authorization: ' + errors[0].message)
    # JSON Schema numeric equality admits 1.0 for integer: accounting demands actual ints.
    for name in ('schema_version', 'max_calls', 'max_cost_microusd', 'max_concurrency'):
        if type(auth[name]) is not int: raise ValueError('authorization requires integer counters')
    for role in auth['roles'].values():
        if role['allow_fallbacks'] is not False: raise ValueError('provider fallbacks must be disabled')
        for name in ('max_input_tokens', 'max_output_tokens', 'input_microusd_per_token', 'output_microusd_per_token', 'max_attempts', 'timeout_seconds'):
            if type(role[name]) is not int: raise ValueError('role budgets require actual integers')
    if utc_datetime(auth['valid_from_utc']) >= utc_datetime(auth['expires_at_utc']): raise ValueError('invalid authorization interval')
    if auth['execution_contract'] != _contract(): raise ValueError('V2 execution contract changed')


def build_authorization(*, workflow_plan_sha256: str, roles: dict, authorized_by: str,
                        valid_from_utc: str, expires_at_utc: str, max_calls: int,
                        max_cost_microusd: int, execution_contract_hashes: dict[str, str]) -> dict:
    auth = dict(schema_version=2, mode='authorized_live_v2', provider='openrouter',
                budget_scope='single_trusted_registry_exact_authorization', workflow_plan_sha256=workflow_plan_sha256,
                roles=copy.deepcopy(roles), execution_contract_hashes=copy.deepcopy(execution_contract_hashes), authorized_by=authorized_by, valid_from_utc=valid_from_utc,
                expires_at_utc=expires_at_utc, max_calls=max_calls, max_cost_microusd=max_cost_microusd,
                max_concurrency=1, pricing_unit='microusd_per_token_ceiling', execution_contract=_contract())
    _validate_auth(auth)
    return auth


def _regular(path: Path, directory: bool = False) -> None:
    if path.is_symlink() or not (path.is_dir() if directory else path.is_file()):
        raise ValueError('missing or symlink V2 path: ' + path.name)


def _read(path: Path) -> dict:
    _regular(path)
    if path.stat().st_size > 8_000_000: raise ValueError('V2 document too large')
    return _strict_json(path.read_bytes())


def _sync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def _write(path: Path, value: dict) -> None:
    temp = path.with_name(path.name + '.pending')
    with temp.open('xb') as stream:
        stream.write(canonical_bytes(value)); stream.flush(); os.fsync(stream.fileno())
    os.link(temp, path); temp.unlink(); _sync(path.parent)


@contextmanager
def _lock(path: Path):
    _regular(path)
    with path.open('rb') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def initialize_registry(directory: Path) -> dict:
    path = Path(directory).absolute()
    if path.exists() or path.is_symlink(): raise ValueError('registry initialization requires a new directory')
    path = path.parent.resolve(strict=True) / path.name
    path.mkdir(mode=0o700); _sync(path.parent)
    (path / '.lock').touch(mode=0o600)
    (path / 'claims').mkdir(); (path / 'journals').mkdir()
    metadata = {'kind': 'live_batch_registry_v2', 'registry_id': 'registry-v2:' + uuid.uuid4().hex,
                'registry_path': str(path), 'execution_contract': _contract()}
    _write(path / 'registry.json', metadata)
    return metadata


def _registry(path: Path) -> dict:
    _regular(path, True)
    for name in ('claims', 'journals'): _regular(path / name, True)
    _regular(path / '.lock')
    metadata = _read(path / 'registry.json')
    if (set(metadata) != {'kind', 'registry_id', 'registry_path', 'execution_contract'} or
        metadata['kind'] != 'live_batch_registry_v2' or metadata['registry_path'] != str(path) or
        metadata['execution_contract'] != _contract()): raise ValueError('V2 registry identity or contract mismatch')
    return metadata


def _reservation(auth: dict, role: str) -> int:
    config = auth['roles'][role]
    return sum(config['max_' + k + '_tokens'] * config[k + '_microusd_per_token'] for k in ('input', 'output'))


def _known_response(response: Any, auth: dict, role: str) -> int:
    if not isinstance(response, dict) or set(response) != {'outcome', 'usage', 'output', 'provider_cost_microusd'}:
        raise ValueError('response requires outcome usage output and provider cost')
    if response['outcome'] not in ('succeeded', 'failed'): raise ValueError('invalid response outcome')
    if not isinstance(response['output'], dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in response['output'].items()):
        raise ValueError('output must contain string artifact references only')
    usage = response['usage']; config = auth['roles'][role]
    if not isinstance(usage, dict) or set(usage) != {'input_tokens', 'output_tokens'}: raise ValueError('unknown usage')
    for kind in ('input', 'output'):
        value = usage[kind + '_tokens']
        if type(value) is not int or not 0 <= value <= config['max_' + kind + '_tokens']: raise ValueError('unknown or excessive token usage')
    reported = response['provider_cost_microusd']
    if type(reported) is not int or reported < 0: raise ValueError('known integer provider cost required')
    cost = max(reported, sum(usage[k + '_tokens'] * config[k + '_microusd_per_token'] for k in ('input', 'output')))
    if cost > _reservation(auth, role): raise ValueError('provider cost exceeds reserved exposure')
    if len(canonical_bytes(response)) > 100_000: raise ValueError('response references too large')
    return cost


def _observed(response: Any) -> dict:
    evidence = {}
    if isinstance(response, dict):
        cost = response.get('provider_cost_microusd')
        if type(cost) is int and cost >= 0: evidence['provider_cost_microusd'] = cost
        usage = response.get('usage')
        if isinstance(usage, dict):
            evidence['usage'] = {k: v for k, v in usage.items() if k in ('input_tokens', 'output_tokens') and type(v) is int and v >= 0}
    return evidence


def replay_events(events: list[dict], auth: dict, *, registry_id: str) -> dict:
    """Hash and semantic replay. No clocks, dispatch, refunds or automatic recovery."""
    _validate_auth(auth); digest = _hash(auth); attempts = {}; committed = 0; previous = ZERO; last_time = None
    if not events: raise ValueError('missing opened event')
    for index, event in enumerate(events):
        if set(event) != {'sequence', 'previous_sha256', 'event_sha256', 'at_utc', 'kind', 'data'}: raise ValueError('invalid event envelope')
        when = utc_datetime(event['at_utc'])
        if type(event['sequence']) is not int or event['sequence'] != index or event['previous_sha256'] != previous or (last_time and when < last_time):
            raise ValueError('event sequence or clock regression')
        if event['event_sha256'] != _hash({k: v for k, v in event.items() if k != 'event_sha256'}): raise ValueError('event hash mismatch')
        kind, data = event['kind'], event['data']
        if index == 0:
            if kind != 'opened' or data != {'authorization_sha256': digest, 'registry_id': registry_id}: raise ValueError('invalid journal opening')
        elif kind == 'reserved':
            if set(data) != {'attempt_id', 'role', 'input_sha256', 'retry_of', 'reserved_microusd'}: raise ValueError('invalid reservation fields')
            aid, role = data['attempt_id'], data['role']; _identifier(aid); _digest(data['input_sha256'])
            if role not in ROLES or aid in attempts: raise ValueError('duplicate attempt or unknown role')
            if not utc_datetime(auth['valid_from_utc']) <= when < utc_datetime(auth['expires_at_utc']): raise ValueError('outside authorization interval')
            if any(a['status'] in ('reserved', 'dispatched', 'unresolved') for a in attempts.values()): raise ValueError('outstanding attempt blocks admission')
            same = [a for a in attempts.values() if a['role'] == role]
            predecessor = data['retry_of']
            if predecessor is not None: _identifier(predecessor)
            if same:
                if predecessor not in attempts or attempts[predecessor]['role'] != role or attempts[predecessor]['status'] != 'failed': raise ValueError('same-role failed predecessor required')
                if any(a['retry_of'] == predecessor for a in attempts.values()): raise ValueError('retry cannot fork')
            elif predecessor is not None: raise ValueError('initial role attempt cannot have predecessor')
            if len(same) >= auth['roles'][role]['max_attempts'] or len(attempts) >= auth['max_calls']: raise ValueError('call or role allowance exhausted')
            amount = _reservation(auth, role)
            if type(data['reserved_microusd']) is not int or data['reserved_microusd'] != amount or committed + amount > auth['max_cost_microusd']: raise ValueError('shared cost allowance exhausted')
            attempts[aid] = {**copy.deepcopy(data), 'status': 'reserved'}
        elif kind in ('dispatched', 'settled', 'unresolved'):
            fields = {'attempt_id'} | ({'response', 'charged_microusd'} if kind == 'settled' else {'reason', 'observed'} if kind == 'unresolved' else set())
            if set(data) != fields or data['attempt_id'] not in attempts: raise ValueError('invalid attempt transition')
            attempt = attempts[data['attempt_id']]
            if kind == 'dispatched':
                if attempt['status'] != 'reserved' or not utc_datetime(auth['valid_from_utc']) <= when < utc_datetime(auth['expires_at_utc']): raise ValueError('invalid dispatch')
                attempt['status'] = 'dispatched'
            elif kind == 'settled':
                if attempt['status'] != 'dispatched': raise ValueError('settlement requires dispatch')
                cost = _known_response(data['response'], auth, attempt['role'])
                if type(data['charged_microusd']) is not int or cost != data['charged_microusd']: raise ValueError('settlement cost mismatch')
                attempt.update(status=data['response']['outcome'], response=copy.deepcopy(data['response']), charged_microusd=cost); committed += cost
            else:
                if attempt['status'] != 'dispatched' or data['reason'] not in ('transport_exception', 'invalid_response') or _observed(data['observed']) != data['observed']:
                    raise ValueError('invalid unresolved event')
                attempt.update(status='unresolved', reason=data['reason'], observed=copy.deepcopy(data['observed']))
        else: raise ValueError('unknown event transition')
        previous = event['event_sha256']; last_time = when
    return {'authorization_sha256': digest, 'registry_id': registry_id, 'requests': attempts,
            'calls_reserved': len(attempts), 'committed_microusd': committed,
            'outstanding_microusd': sum(a['reserved_microusd'] for a in attempts.values() if a['status'] in ('reserved', 'dispatched', 'unresolved'))}


class BatchExecutionV2:
    def __init__(self, registry_dir: Path, authorization: dict, *, clock: Callable[[], str] = utc_now):
        _validate_auth(authorization)
        self._auth = copy.deepcopy(authorization); self._digest = _hash(self._auth)
        self._registry = Path(registry_dir).resolve(strict=True); self._clock = clock
        metadata = _registry(self._registry); self._registry_id = metadata['registry_id']
        self._journal = self._registry / 'journals' / self._digest
        claim = self._registry / 'claims' / (self._digest + '.json')
        with _lock(self._registry / '.lock'):
            _registry(self._registry)
            if claim.exists() or claim.is_symlink():
                self._check()
            else:
                if self._journal.exists() or self._journal.is_symlink(): raise ValueError('unclaimed journal exists')
                _write(claim, {'authorization_sha256': self._digest, 'registry_id': self._registry_id})
                self._journal.mkdir(); _sync(self._journal.parent)
                (self._journal / '.lock').touch(mode=0o600)
                _write(self._journal / 'authorization.json', self._auth)
                self._append([], 'opened', {'authorization_sha256': self._digest, 'registry_id': self._registry_id})
                _write(self._journal / 'ready.json', {'authorization_sha256': self._digest, 'registry_id': self._registry_id})
        self.status()

    @property
    def authorization_sha256(self) -> str: return self._digest

    @property
    def journal_path(self) -> Path: return self._journal

    def _check(self) -> None:
        metadata = _registry(self._registry)
        if metadata['registry_id'] != self._registry_id: raise ValueError('registry identity changed')
        _regular(self._journal, True)
        expected = {'authorization_sha256': self._digest, 'registry_id': self._registry_id}
        if _read(self._registry / 'claims' / (self._digest + '.json')) != expected or _read(self._journal / 'ready.json') != expected:
            raise ValueError('missing or changed claim/ready binding')
        _regular(self._journal / '.lock'); _regular(self._journal / 'events.jsonl')
        if _read(self._journal / 'authorization.json') != self._auth: raise ValueError('stored authorization changed')
        _validate_auth(self._auth)

    def _events(self) -> list[dict]:
        raw = (self._journal / 'events.jsonl').read_bytes()
        if not raw.endswith(b'\n'): raise ValueError('partial journal append')
        return [_strict_json(line) for line in raw.splitlines()]

    def _append(self, events: list[dict], kind: str, data: dict) -> dict:
        event = {'sequence': len(events), 'previous_sha256': events[-1]['event_sha256'] if events else ZERO,
                 'at_utc': self._clock(), 'kind': kind, 'data': data}
        event['event_sha256'] = _hash(event)
        result = replay_events([*events, event], self._auth, registry_id=self._registry_id)
        with (self._journal / 'events.jsonl').open('ab') as stream:
            stream.write(canonical_bytes(event)); stream.flush(); os.fsync(stream.fileno())
        _sync(self._journal); events.append(event)
        return result

    def status(self) -> dict:
        self._check()
        with _lock(self._journal / '.lock'):
            self._check()
            return replay_events(self._events(), self._auth, registry_id=self._registry_id)

    def run(self, role: str, attempt_id: str, transport: Callable[[dict], dict], *, input_sha256: str, retry_of: str | None = None) -> dict:
        self._check(); _identifier(attempt_id); _digest(input_sha256)
        if retry_of is not None: _identifier(retry_of)
        if role not in ROLES: raise ValueError('unknown role')
        with _lock(self._journal / '.lock'):
            self._check(); events = self._events(); state = replay_events(events, self._auth, registry_id=self._registry_id)
            if attempt_id in state['requests']:
                existing = state['requests'][attempt_id]
                if (existing['role'], existing['input_sha256'], existing['retry_of']) != (role, input_sha256, retry_of): raise ValueError('attempt input or lineage changed')
                return copy.deepcopy(existing)  # Never resend even a reserved crash boundary.
            self._append(events, 'reserved', {'attempt_id': attempt_id, 'role': role, 'input_sha256': input_sha256,
                         'retry_of': retry_of, 'reserved_microusd': _reservation(self._auth, role)})
            self._append(events, 'dispatched', {'attempt_id': attempt_id})
        envelope = {'authorization_sha256': self._digest, 'workflow_plan_sha256': self._auth['workflow_plan_sha256'],
                    'registry_id': self._registry_id, 'attempt_id': attempt_id, 'role': role, 'input_sha256': input_sha256,
                    'provider': 'openrouter', 'mode': 'authorized_live_v2', 'role_config': copy.deepcopy(self._auth['roles'][role])}
        response = None; returned = False
        try:
            response = copy.deepcopy(transport(envelope)); returned = True
            cost = _known_response(response, self._auth, role)
        except Exception:
            kind = 'unresolved'; data = {'attempt_id': attempt_id, 'reason': 'invalid_response' if returned else 'transport_exception', 'observed': _observed(response)}
        else:
            kind = 'settled'; data = {'attempt_id': attempt_id, 'response': response, 'charged_microusd': cost}
        with _lock(self._journal / '.lock'):
            self._check(); events = self._events()
            return self._append(events, kind, data)['requests'][attempt_id]
