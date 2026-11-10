"""Narrow Google review grammar adaptation retains canonical acceptance rules."""
import copy
import hashlib
import json
import unittest

from jsonschema import Draft202012Validator

from turbo.agents.batch_provider import role_schema
from turbo.agents.openrouter_attempt import bounded_request_body, invoke_openrouter_once
from turbo.agents.openrouter_runner import openrouter_role_schema, openrouter_schema
from turbo.pipeline_paths import ROOT


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode()


class GoogleReleaseSchemaTest(unittest.TestCase):
    def setUp(self):
        self.schema = role_schema('release_reviewer', input_root=ROOT)
        self.model = 'google/gemini-4-argon'
        self.document = {
            'input_hashes': {'primary': 'a'*64, 'verifier': 'b'*64},
            'approved_plan_sha256': 'c'*64, 'verdict': 'approve', 'findings': [],
            'checks': {k: 'pass' for k in ('coverage', 'operating_identity', 'evidence',
                                         'cross_family_conflicts', 'closure_outcomes')},
        }

    def test_only_google_review_findings_bound_changes_without_source_mutation(self):
        before = copy.deepcopy(self.schema)
        adapted = openrouter_role_schema(self.schema, role_id='release_reviewer', model=self.model)
        expected = openrouter_schema(self.schema)
        self.assertEqual(expected['properties']['findings'].pop('maxItems'), 20000)
        self.assertEqual(adapted, expected)
        self.assertEqual(self.schema, before)
        self.assertEqual(role_schema('release_reviewer', input_root=ROOT), before)
        # Other bounds, nested object shapes and exact-hash requirements remain.
        self.assertEqual(adapted['properties']['findings']['items']['properties']['rationale']['maxLength'], 12000)
        self.assertEqual(adapted['properties']['input_hashes'], before['properties']['input_hashes'])

    def test_other_models_and_roles_keep_existing_provider_schema(self):
        expected = openrouter_schema(self.schema)
        for role, model in [('release_reviewer', 'openai/reviewer'),
                            ('release_reviewer', 'meta/reviewer'),
                            ('primary', self.model), ('verifier', self.model),
                            ('adjudicator', self.model)]:
            with self.subTest(role=role, model=model):
                self.assertEqual(openrouter_role_schema(self.schema, role_id=role, model=model), expected)

    def test_admission_and_wire_share_adaptation_and_record_actual_schema_hash(self):
        invocation = 'invocation:'+'a'*24
        options = dict(role_id='release_reviewer', model=self.model, reasoning_effort='high',
                       runtime_prompt_text='Controlled schema compatibility fixture.',
                       invocation_id=invocation, max_completion_tokens=16000,
                       allow_fallbacks=False, schema_name='turbo_workflow_role')
        admission = bounded_request_body(schema=openrouter_role_schema(self.schema,
            role_id='release_reviewer', model=self.model), **options)
        calls = []
        def transport(url, headers, body, timeout):
            calls.append(body)
            return 200, {}, json.dumps({'model': self.model,
                'choices': [{'message': {'content': json.dumps(self.document)}}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'cost': '0.00001'}}).encode()
        result = invoke_openrouter_once(invocation_id=invocation, role='release_reviewer',
            model=self.model, reasoning_effort='high', runtime_prompt_text=options['runtime_prompt_text'],
            schema=self.schema, max_completion_tokens=16000, timeout=30,
            api_key='controlled-secret', transport=transport)
        self.assertEqual(result['status'], 'valid')
        self.assertEqual(calls, [encoded(admission)])
        sent_schema = admission['response_format']['json_schema']['schema']
        self.assertEqual(result['provider_schema_sha256'], hashlib.sha256(encoded(sent_schema)).hexdigest())
        self.assertEqual(result['schema_sha256'], hashlib.sha256(encoded(self.schema)).hexdigest())
        self.assertNotEqual(result['schema_sha256'], result['provider_schema_sha256'])

    def test_canonical_findings_limit_still_rejects_overflow(self):
        document = copy.deepcopy(self.document)
        document['findings'] = [{'finding_id': 'f', 'status': 'resolved', 'rationale': 'r'}]*20001
        self.assertFalse(Draft202012Validator(self.schema).is_valid(document))
        # A smaller controlled bound makes the actual adapter rejection observable
        # without exceeding its independent response-body size limit first.
        schema = {'type': 'object', 'required': ['findings'], 'additionalProperties': False,
                  'properties': {'findings': {'type': 'array', 'maxItems': 1,
                                             'items': {'type': 'integer'}}}}
        calls = []
        def transport(url, headers, body, timeout):
            calls.append(json.loads(body))
            return 200, {}, json.dumps({'model': self.model,
                'choices': [{'message': {'content': '{"findings":[1,2]}'}}],
                'usage': {'prompt_tokens': 1, 'completion_tokens': 2, 'cost': '0.00001'}}).encode()
        result = invoke_openrouter_once(invocation_id='fixture', role='release_reviewer',
            model=self.model, reasoning_effort='high', runtime_prompt_text='Controlled fixture.',
            schema=schema, max_completion_tokens=100, timeout=30,
            api_key='controlled-secret', transport=transport)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('maxItems', calls[0]['response_format']['json_schema']['schema']['properties']['findings'])
        self.assertEqual(result['status'], 'invalid')
        self.assertEqual(result['error_stage'], 'content_schema')
        self.assertEqual(result['usage_status'], 'known')
        self.assertEqual(result['provider_cost_microusd'], 10)


if __name__ == '__main__':
    unittest.main()
