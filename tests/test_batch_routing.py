"""Authorization-bound routing with controlled transports only; no live calls."""
import copy
from decimal import Decimal
import json
import unittest
from unittest.mock import patch

from turbo.agents import batch_provider, batch_execution_v2 as execution
from turbo.agents.openrouter_attempt import bounded_request_body, routing_request_fields
from test_batch_execution_v2 import ExecutionV2Test, clock
from test_batch_provider import BatchProviderTest
from test_openrouter_attempt import OpenRouterAttemptTest


def policy(cache=True):
    value = {'schema_version': 1, 'provider': {'only': ['openai'],
        'ignore': ['openai/fast', 'openai/flex'],
        'max_price': {'prompt': '0.4', 'completion': '1.8'}}}
    if cache:
        value['prompt_cache_options'] = {'mode': 'explicit'}
    return value


class RoutingAuthorizationTest(unittest.TestCase):
    setUp = ExecutionV2Test.setUp
    auth = ExecutionV2Test.auth

    def configure(self):
        self.roles['primary'].update(model='openai/test', routing=policy())

    def test_decimal_units_and_policy_hash_binding(self):
        self.configure()
        auth = self.auth()
        ledger = execution.BatchExecutionV2(self.registry, auth, clock=clock)
        digest = ledger.authorization_sha256
        changed = copy.deepcopy(auth)
        changed['roles']['primary']['routing']['provider']['max_price']['prompt'] = '0.5'
        self.assertNotEqual(execution._hash(changed), digest)
        stored = ledger.journal_path / 'authorization.json'
        stored.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'stored authorization changed'):
            ledger.status()

    def test_caps_must_fit_integer_local_rates(self):
        self.configure()
        for field, amount in [('prompt', '1.000000000000001'), ('completion', '2.1')]:
            self.roles['primary']['routing'] = policy()
            self.roles['primary']['routing']['provider']['max_price'][field] = amount
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.auth()

    def test_strict_schema_and_adapter_reject_unknown_or_lossy_policy(self):
        self.configure()
        baseline = policy()
        invalid = []
        for field, value in [('schema_version', True), ('schema_version', 1.0), ('url', 'https://example.com')]:
            item = copy.deepcopy(baseline); item[field] = value; invalid.append(item)
        for value in (0.4, True, '-1', 'NaN', 'Infinity', '1e-1', '9007199254740992', '0.1234567890123456789'):
            item = copy.deepcopy(baseline); item['provider']['max_price']['prompt'] = value; invalid.append(item)
        for key, value in [('only', []), ('only', ['openai', 'openai']), ('only', ['https://x']),
                           ('allow_fallbacks', True), ('require_parameters', False), ('headers', {})]:
            item = copy.deepcopy(baseline); item['provider'][key] = value; invalid.append(item)
        for value in ({'mode': 'automatic'}, {'mode': 'explicit', 'ttl': '12h'}):
            item = copy.deepcopy(baseline); item['prompt_cache_options'] = value; invalid.append(item)
        for value in invalid:
            with self.subTest(policy=value):
                self.roles['primary']['routing'] = value
                with self.assertRaises(ValueError): self.auth()
                with self.assertRaises(ValueError): routing_request_fields(value)
        self.roles['primary'].update(routing=policy(), model='google/test')
        with self.assertRaises(ValueError): self.auth()


class RoutingAttemptTest(unittest.TestCase):
    call = OpenRouterAttemptTest.call
    response = OpenRouterAttemptTest.response

    def test_exact_wire_fields_and_no_cache_breakpoints(self):
        for route in (policy(), policy(False)):
            with self.subTest(cache='prompt_cache_options' in route):
                result, calls = self.call(self.response(), model='openai/test', routing=route)
                self.assertEqual(result['status'], 'valid')
                self.assertEqual(len(calls), 1)
                wire = json.loads(calls[0][2], parse_float=Decimal)
                self.assertEqual(wire['provider'], {'only':['openai'], 'ignore':['openai/fast','openai/flex'],
                    'max_price':{'prompt':Decimal('0.4'),'completion':Decimal('1.8')},
                    'require_parameters':True,'allow_fallbacks':False})
                self.assertEqual('prompt_cache_options' in wire, 'prompt_cache_options' in route)
                self.assertIsInstance(wire['messages'][0]['content'], str)
                self.assertNotIn(b'prompt_cache_breakpoint', calls[0][2])

    def test_ineligible_endpoint_is_one_attempt_and_preserves_charge(self):
        result, calls = self.call({'error':{'message':'No eligible endpoints'},
            'usage':{'prompt_tokens':0,'completion_tokens':0,'cost':'0.0000001'}},
            status=404, model='openai/test', routing=policy())
        self.assertEqual(len(calls),1)
        self.assertEqual(result['error_stage'],'http')
        self.assertEqual(result['provider_cost_microusd'],1)
        result, calls = self.call(self.response(), model='openai/test', routing=policy(), allow_fallbacks=True)
        self.assertEqual(calls, [])
        self.assertFalse(result['transport_attempted'])


class RoutingProviderTest(unittest.TestCase):
    setUpClass = classmethod(BatchProviderTest.setUpClass.__func__)
    tearDownClass = classmethod(BatchProviderTest.tearDownClass.__func__)
    setUp = BatchProviderTest.setUp
    payload = BatchProviderTest.payload
    transport_for = BatchProviderTest.transport_for
    run_role = BatchProviderTest.run_role

    def configure(self):
        self.authorization['roles']['primary'].update(model='openai/test', routing=policy(),
                                                       input_microusd_per_token=1)
        self.authorization['max_cost_microusd'] = 20_000_000

    def test_admission_uses_dispatched_policy_and_replay_cannot_mutate(self):
        self.configure()
        bounds=[]
        def capture(**kwargs):
            value = bounded_request_body(**kwargs); bounds.append(value); return value
        with patch.object(batch_provider, 'bounded_request_body', side_effect=capture):
            self.assertEqual(self.run_role('primary', {'payload':self.payload()})['status'], 'succeeded')
        self.assertEqual(len(self.calls),1)
        wire = self.calls[0]
        bound = bounds[0]
        self.assertEqual(len(json.dumps(bound, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()),
                         len(json.dumps(wire, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()))
        bound['session_id'] = wire['session_id']
        self.assertEqual(bound, wire)
        self.authorization['roles']['primary']['routing']['provider']['max_price']['prompt'] = '0.5'
        with self.assertRaises(ValueError): self.run_role('primary', {'payload':self.payload()})
        self.assertEqual(len(self.calls),1)

    def test_routing_bytes_and_price_mismatch_block_before_http(self):
        self.configure()
        bounds=[]
        def capture(**kwargs):
            value = bounded_request_body(**kwargs); bounds.append(value)
            raise RuntimeError('measured without dispatch')
        with patch.object(batch_provider, 'bounded_request_body', side_effect=capture):
            with self.assertRaisesRegex(RuntimeError,'measured'): self.run_role('primary', {'payload':self.payload()})
        bound = bounds[0]
        routed_size = len(batch_provider._bytes(bound))
        bound['provider'] = {'require_parameters':True,'allow_fallbacks':False}
        bound.pop('prompt_cache_options')
        bare_size = len(batch_provider._bytes(bound))
        self.assertGreater(routed_size,bare_size)
        self.authorization['roles']['primary']['max_input_tokens'] = bare_size + 4096
        with self.assertRaisesRegex(ValueError,'request token bound'): self.run_role('primary', {'payload':self.payload()})
        self.authorization['roles']['primary']['max_input_tokens'] = 10_000_000
        self.authorization['roles']['primary']['input_microusd_per_token'] = 0
        with self.assertRaisesRegex(ValueError,'price ceilings'): self.run_role('primary', {'payload':self.payload()})
        self.assertEqual(self.calls,[])


del ExecutionV2Test, BatchProviderTest, OpenRouterAttemptTest

if __name__ == '__main__': unittest.main()
