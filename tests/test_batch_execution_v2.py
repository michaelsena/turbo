"""Physical-call accounting under one explicit V2 authorization; no network."""
import copy
import json
import multiprocessing
from pathlib import Path
import shutil
import tempfile
import unittest
from turbo.agents.batch_execution_v2 import (BatchExecutionV2, ROLES, build_authorization,
    initialize_registry, replay_events, _hash)

NOW = '2026-11-09T12:00:00Z'

def clock(): return NOW

def response(outcome='succeeded', cost=20):
    return {'outcome': outcome, 'usage': {'input_tokens': 5, 'output_tokens': 5},
            'output': {'artifact_sha256': 'a' * 64}, 'provider_cost_microusd': cost}

def compete(registry, auth, role, barrier, queue):
    try:
        execution = BatchExecutionV2(Path(registry), auth, clock=clock)
        barrier.wait()
        result = execution.run(role, role, lambda envelope: (queue.put('http'), response())[1], input_sha256='b'*64)
        queue.put(result['status'])
    except ValueError:
        queue.put('denied')


class ExecutionV2Test(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.registry = Path(self.temp.name) / 'registry'; initialize_registry(self.registry)
        self.roles = {role: {'model': 'test/' + role, 'prompt_sha256': 'a'*64, 'schema_sha256': 'b'*64,
            'max_input_tokens': 100, 'max_output_tokens': 100, 'input_microusd_per_token': 1,
            'output_microusd_per_token': 2, 'max_attempts': 3, 'reasoning_effort': 'high',
            'timeout_seconds': 30, 'allow_fallbacks': False} for role in ROLES}

    def auth(self, **overrides):
        values = dict(workflow_plan_sha256='c'*64, roles=self.roles, authorized_by='test operator',
                      valid_from_utc='2026-11-09T00:00:00Z', expires_at_utc='2026-11-10T00:00:00Z',
                      max_calls=6, max_cost_microusd=1000, execution_contract_hashes={})
        values.update(overrides); return build_authorization(**values)

    def execution(self, **overrides):
        return BatchExecutionV2(self.registry, self.auth(**overrides), clock=clock)

    def run_attempt(self, execution, role='primary', aid='p', result=None, **kwargs):
        return execution.run(role, aid, lambda envelope: response() if result is None else result,
                             input_sha256='d'*64, **kwargs)

    def test_constructor_restart_and_primary_verifier_share_budget(self):
        auth = self.auth(max_cost_microusd=320)
        first = BatchExecutionV2(self.registry, auth, clock=clock)
        self.assertEqual(first.status()['calls_reserved'], 0)
        self.assertEqual(self.run_attempt(first)['status'], 'succeeded')
        resumed = BatchExecutionV2(self.registry, auth, clock=clock)
        self.run_attempt(resumed, 'verifier', 'v')
        self.assertEqual(resumed.status()['committed_microusd'], 40)
        self.assertEqual(resumed.status()['calls_reserved'], 2)
        self.assertEqual(first.journal_path, resumed.journal_path)

    def test_shared_last_budget_blocks_verifier_before_transport(self):
        execution = self.execution(max_cost_microusd=300)
        self.run_attempt(execution)
        calls=[]
        with self.assertRaises(ValueError):
            execution.run('verifier', 'v', lambda e: calls.append(e), input_sha256='d'*64)
        self.assertEqual(calls, [])
        self.assertEqual(execution.status()['calls_reserved'], 1)

    def test_idempotent_resume_binds_exact_input_and_role(self):
        execution = self.execution(); calls=[]
        def transport(e): calls.append(e); return response()
        first=execution.run('primary','p',transport,input_sha256='d'*64)
        self.assertEqual(execution.run('primary','p',transport,input_sha256='d'*64), first)
        self.assertEqual(len(calls),1)
        for role, digest in [('primary','e'*64),('verifier','d'*64)]:
            with self.assertRaises(ValueError): execution.run(role,'p',transport,input_sha256=digest)

    def test_failed_retry_is_same_role_nonforking_and_charged(self):
        execution=self.execution()
        self.run_attempt(execution,result=response('failed'))
        with self.assertRaises(ValueError): self.run_attempt(execution,'verifier','v',retry_of='p')
        self.run_attempt(execution,aid='repair',result=response('failed'),retry_of='p')
        with self.assertRaises(ValueError): self.run_attempt(execution,aid='fork',retry_of='p')
        self.run_attempt(execution,aid='repair2',retry_of='repair')
        self.assertEqual(execution.status()['calls_reserved'],3)
        self.assertEqual(execution.status()['committed_microusd'],60)

    def test_success_cannot_be_retried_and_role_attempt_cap_applies(self):
        execution=self.execution();self.run_attempt(execution)
        with self.assertRaises(ValueError):self.run_attempt(execution,aid='again',retry_of='p')
        self.roles['verifier']['max_attempts']=1
        other=self.execution();self.run_attempt(other,'verifier','v',response('failed'))
        with self.assertRaises(ValueError):self.run_attempt(other,'verifier','v2',retry_of='v')

    def test_timeout_unknown_cost_and_overage_remain_outstanding(self):
        for index, kind in enumerate(('timeout','missing_cost','overage','bool_usage')):
            with self.subTest(kind=kind):
                auth=self.auth(authorized_by='operator'+str(index));execution=BatchExecutionV2(self.registry,auth,clock=clock)
                observed=response()
                if kind=='missing_cost':observed['provider_cost_microusd']=None
                if kind=='overage':observed['provider_cost_microusd']=301
                if kind=='bool_usage':observed['usage']['input_tokens']=True
                def transport(e):
                    if kind=='timeout':raise TimeoutError('secret omitted')
                    return observed
                result=execution.run('primary','p',transport,input_sha256='d'*64)
                self.assertEqual(result['status'],'unresolved')
                self.assertEqual(execution.status()['outstanding_microusd'],300)
                self.assertEqual(execution.status()['committed_microusd'],0)
                execution.run('primary','p',lambda e:self.fail('resent'),input_sha256='d'*64)
                with self.assertRaises(ValueError):self.run_attempt(execution,'verifier','v')
                if kind=='overage':self.assertEqual(result['observed']['provider_cost_microusd'],301)

    def test_hard_crash_dispatch_never_resends_after_restart(self):
        auth=self.auth();execution=BatchExecutionV2(self.registry,auth,clock=clock)
        with self.assertRaises(KeyboardInterrupt):
            execution.run('primary','p',lambda e:(_ for _ in ()).throw(KeyboardInterrupt()),input_sha256='d'*64)
        reopened=BatchExecutionV2(self.registry,auth,clock=clock)
        result=reopened.run('primary','p',lambda e:self.fail('resent'),input_sha256='d'*64)
        self.assertEqual(result['status'],'dispatched')
        self.assertEqual(reopened.status()['outstanding_microusd'],300)

    def test_unknown_registry_and_missing_claimed_journal_fail_closed(self):
        with self.assertRaises((ValueError,FileNotFoundError)):BatchExecutionV2(self.registry/'missing',self.auth())
        execution=self.execution();shutil.rmtree(execution.journal_path)
        with self.assertRaises(ValueError):BatchExecutionV2(self.registry,self.auth(),clock=clock)
        self.assertFalse(execution.journal_path.exists())

    def test_rehashed_semantic_tamper_rejected(self):
        execution=self.execution();self.run_attempt(execution)
        events=[json.loads(line) for line in (execution.journal_path/'events.jsonl').read_text().splitlines()]
        events[1]['data']['reserved_microusd']=1
        previous='0'*64
        for event in events:
            event['previous_sha256']=previous
            event['event_sha256']=_hash({k:v for k,v in event.items() if k!='event_sha256'})
            previous=event['event_sha256']
        with self.assertRaises(ValueError):replay_events(events,self.auth(),registry_id=execution.status()['registry_id'])

    def test_status_callback_has_no_registry_or_journal_deadlock(self):
        execution=self.execution()
        def transport(e):
            self.assertEqual(execution.status()['requests']['p']['status'],'dispatched')
            return response()
        self.assertEqual(execution.run('primary','p',transport,input_sha256='d'*64)['status'],'succeeded')

    def test_two_processes_compete_for_shared_final_slot(self):
        auth=self.auth(max_calls=1);BatchExecutionV2(self.registry,auth,clock=clock)
        ctx=multiprocessing.get_context('fork');barrier=ctx.Barrier(2);queue=ctx.Queue()
        children=[ctx.Process(target=compete,args=(str(self.registry),auth,r,barrier,queue)) for r in ('primary','verifier')]
        for p in children:p.start()
        for p in children:p.join(10);self.assertFalse(p.is_alive());self.assertEqual(p.exitcode,0)
        results=[queue.get(timeout=2) for _ in range(3)]
        self.assertEqual(results.count('http'),1);self.assertIn('denied',results)

    def test_expired_authority_and_fractional_prices_refused(self):
        execution=self.execution(expires_at_utc='2026-11-09T10:00:00Z')
        with self.assertRaises(ValueError):self.run_attempt(execution)
        self.roles['primary']['input_microusd_per_token']=1.0
        with self.assertRaises(ValueError):self.auth()
