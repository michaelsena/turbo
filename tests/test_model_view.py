"""Optional model-view tests; synthetic transports only."""
import copy
import json
import unittest
from unittest.mock import patch
from turbo.agents import model_view as view, batch_provider as provider, batch_workflow
from turbo.agents.openrouter_attempt import bounded_request_body
from test_batch_provider import BatchProviderTest


class ModelViewTest(unittest.TestCase):
    def test_roundtrip_markers_empty_values_and_order(self):
        repeated = 'identity:napcs-collection:1234567890'
        value = {'o': [0, {'s': 7}], 's': {'o': []}, 'empty': [{}, [], None, False, 1, 1.25],
                 'repeated': [repeated] * 20, 'literal': '{"s":0}',
                 'evidence_id': 'evidence:' + 'a' * 64, 'hashes': ['b' * 64] * 20}
        encoded = view.encode(value)
        self.assertEqual(view.decode(encoded), value)
        self.assertEqual(view.encode(dict(reversed(list(value.items())))), encoded)
        self.assertNotIn(value['evidence_id'], encoded['strings'])
        self.assertNotIn('b' * 64, encoded['strings'])
        self.assertIn(repeated, encoded['strings'])

    def test_invalid_markers_and_non_json_rejected(self):
        for value in [{'schema_version': True}, {'schema_version': 1, 'schemas': [], 'strings': [], 'context': {'s': -1}},
                      {'schema_version': 1, 'schemas': [['x']], 'strings': [], 'context': {'o': [0]}},
                      {'schema_version': 1, 'schemas': [], 'strings': [], 'context': {'unknown': 1}}]:
            with self.subTest(value=value), self.assertRaises(ValueError): view.decode(value)
        for value in [{1: 'x'}, {'tuple': (1, 2)}, float('nan')]:
            with self.subTest(value=value), self.assertRaises(ValueError): view.encode(value)


class ModelViewProviderTest(unittest.TestCase):
    setUpClass = classmethod(BatchProviderTest.setUpClass.__func__)
    tearDownClass = classmethod(BatchProviderTest.tearDownClass.__func__)
    setUp = BatchProviderTest.setUp
    payload = BatchProviderTest.payload
    transport_for = BatchProviderTest.transport_for
    run_role = BatchProviderTest.run_role
    verifier_document = BatchProviderTest.verifier_document

    def enable(self):
        self.authorization['execution_contract_hashes'] = provider.execution_contract_hashes(model_view=view.VERSION)
        for name, binding in provider.contract_bindings(input_root=self.input_root, model_view=view.VERSION).items():
            self.authorization['roles'][name].update(binding)

    def test_full_context_roundtrip_and_plain_default_wire(self):
        self.assertEqual(view.decode(view.encode(self.context)), self.context)
        task = batch_workflow.assignment(self.directory, 'primary', input_root=self.input_root)
        self.assertEqual(self.run_role('primary', {'payload':self.payload()})['status'], 'succeeded')
        content = self.calls[0]['messages'][0]['content']
        self.assertEqual(content, provider.role_prompt(input_root=self.input_root) + '\n# Frozen assignment\n' + provider._bytes(task).decode())
        self.assertNotIn(view.INSTRUCTIONS, content)
        plain = provider.contract_bindings(input_root=self.input_root)
        explicit = provider.contract_bindings(input_root=self.input_root, model_view=None)
        self.assertEqual(plain, explicit)

    def test_encoded_admission_dispatch_canonical_outputs_and_replay(self):
        self.enable(); bounds=[]
        def capture(**kwargs):
            result=bounded_request_body(**kwargs); bounds.append(result); return result
        with patch.object(provider, 'bounded_request_body', side_effect=capture):
            primary={'payload':self.payload()}
            self.assertEqual(self.run_role('primary', primary)['status'], 'succeeded')
        wire=copy.deepcopy(self.calls[0]); bound=bounds[0]
        self.assertEqual(len(provider._bytes(bound)),len(provider._bytes(wire)))
        bound['session_id']=wire['session_id']; self.assertEqual(bound,wire)
        content=wire['messages'][0]['content']; self.assertIn(view.INSTRUCTIONS,content)
        decoded=view.decode(json.loads(content.split('\n# Frozen assignment\n',1)[1]))
        self.assertEqual(decoded['context'],self.context)
        self.assertEqual(decoded['inputs'],{})
        self.assertEqual(self.run_role('primary',primary)['status'],'succeeded')
        self.assertEqual(len(self.calls),1)
        verifier=self.verifier_document()
        self.assertEqual(self.run_role('verifier',verifier)['status'],'succeeded')
        self.assertEqual(self.run_role('verifier',verifier)['status'],'succeeded')
        self.assertEqual(len(self.calls),2)
        self.authorization['execution_contract_hashes'][view.CONTRACT_KEY]='0'*64
        with self.assertRaisesRegex(ValueError,'implementation changed'):
            self.run_role('primary',primary)
        self.assertEqual(len(self.calls),2)

    def test_unknown_policy_or_missing_prompt_binding_rejects_before_dispatch(self):
        original=copy.deepcopy(self.authorization)
        for contracts in [dict(original['execution_contract_hashes'], **{'model-view/unknown':'0'*64}),
                          provider.execution_contract_hashes(model_view=view.VERSION)]:
            self.authorization=copy.deepcopy(original)
            self.authorization['execution_contract_hashes']=contracts
            with self.assertRaises(ValueError): self.run_role('primary',{'payload':self.payload()})
        self.assertEqual(self.calls,[])
        with self.assertRaises(ValueError): provider.contract_bindings(input_root=self.input_root,model_view='v99')
        with self.assertRaises(ValueError): provider.execution_contract_hashes(model_view='v99')

    def test_encoded_byte_gate_cannot_dispatch_over_limit(self):
        self.enable(); self.authorization['roles']['primary']['max_input_tokens']=100
        with self.assertRaisesRegex(ValueError,'token bound'): self.run_role('primary',{'payload':self.payload()})
        self.assertEqual(self.calls,[])

    def test_encoding_cannot_be_enabled_on_recovery(self):
        self.enable()
        with self.assertRaisesRegex(ValueError,'fresh workflow'):
            provider.run_batch_role(self.directory,self.registry,self.authorization,'primary','p',
                input_root=self.input_root,preparation_dirs=self.preparations,
                recovery_checkpoint=self.base/'missing',api_key='synthetic')
        self.assertEqual(self.calls,[])


del BatchProviderTest
if __name__ == '__main__': unittest.main()
