"""A one-shot adapter must never hide another paid attempt or uncertain billing."""
import json
import io
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request

from turbo.agents.openrouter_attempt import (
    MAX_RESPONSE_BYTES, _NoRedirect, _no_redirect_transport, invoke_openrouter_once,
)

SECRET = 'test-key-do-not-persist-123'
SCHEMA = {'type':'object', 'additionalProperties':False, 'required':['answer'],
          'properties':{'answer':{'type':'string'}}}


class OpenRouterAttemptTest(unittest.TestCase):
    def call(self, response=None, *, status=200, raw=None, failure=None, **changes):
        calls = []
        def transport(url, headers, body, timeout):
            calls.append((url, headers, body, timeout))
            if failure is not None:
                raise failure
            return status, {'discarded-header':SECRET}, raw if raw is not None else json.dumps(response).encode()
        args = dict(invocation_id='invocation:'+'a'*24, role='primary', model='vendor/test-model',
                    reasoning_effort='high', runtime_prompt_text='Frozen evidence only.', schema=SCHEMA,
                    max_completion_tokens=100, timeout=30, api_key=SECRET, transport=transport)
        args.update(changes)
        result = invoke_openrouter_once(**args)
        return result, calls

    def response(self, content='{"answer":"ok"}', usage=None):
        return {'id':'gen-test-1', 'model':'vendor/served-model', 'provider':'Test Provider',
                'choices':[{'message':{'content':content,'reasoning':SECRET+' reasoning'}}],
                'usage':usage if usage is not None else {'prompt_tokens':7,'completion_tokens':5,'cost':'0.0000011'}}

    def safe(self, result):
        text=repr(result)
        self.assertNotIn(SECRET,text)
        self.assertNotIn('reasoning',text)

    def test_one_success_preserves_final_bytes_and_decimal_cost(self):
        result,calls=self.call(self.response())
        self.assertEqual(len(calls),1)
        self.assertEqual(result['status'],'valid')
        self.assertEqual(result['body'],b'{"answer":"ok"}')
        self.assertEqual(result['usage'],{'input_tokens':7,'output_tokens':5})
        self.assertEqual(result['provider_cost_microusd'],2)
        request=json.loads(calls[0][2])
        self.assertFalse(request['provider']['allow_fallbacks'])
        self.assertEqual(request['session_id'],'invocation:'+'a'*24)
        for key in ('request_sha256','schema_sha256','provider_schema_sha256','response_sha256','body_sha256'):
            self.assertEqual(len(result[key]),64)
        self.safe(result)

    def test_429_and_500_never_retry_and_keep_known_billing(self):
        for status in (429,500):
            with self.subTest(status=status):
                response=self.response();response['error']={'message':SECRET+' provider details'}
                result,calls=self.call(response,status=status)
                self.assertEqual(len(calls),1)
                self.assertEqual(result['error_stage'],'http')
                self.assertEqual(result['usage_status'],'known')
                self.assertEqual(result['provider_cost_microusd'],2)
                self.assertIsNone(result['body']);self.safe(result)

    def test_empty_malformed_and_schema_invalid_content_keep_usage(self):
        for content,stage in [('', 'content_json'),('not JSON','content_json'),
                              ('{"answer":true}','content_schema'),
                              ('{"answer":"a","answer":"b"}','content_json'),
                              ('{"answer":NaN}','content_json')]:
            with self.subTest(content=content):
                result,calls=self.call(self.response(content))
                self.assertEqual(len(calls),1);self.assertEqual(result['status'],'invalid')
                self.assertEqual(result['error_stage'],stage)
                self.assertEqual(result['usage_status'],'known')
                self.assertEqual(result['provider_cost_microusd'],2)
        response=self.response();response['choices']=[]
        result,calls=self.call(response)
        self.assertEqual(len(calls),1);self.assertEqual(result['error_stage'],'content')
        self.assertEqual(result['usage_status'],'known');self.assertIsNone(result['body'])

    def test_transport_ambiguity_never_invents_zero_usage(self):
        result,calls=self.call(failure=TimeoutError(SECRET+' ambiguous request'))
        self.assertEqual(len(calls),1);self.assertEqual(result['status'],'unknown')
        self.assertTrue(result['transport_attempted']);self.assertIsNone(result['usage'])
        self.assertIsNone(result['provider_cost_microusd']);self.safe(result)

    def test_malformed_outer_response_remains_unknown_and_single_attempt(self):
        for raw in (b'not JSON',b'[]',b'{"usage":{},"usage":{}}',b'{"value":NaN}',b'{"value":1e999999999}'):
            with self.subTest(raw=raw):
                result,calls=self.call(raw=raw)
                self.assertEqual(len(calls),1);self.assertEqual(result['status'],'unknown')
                self.assertEqual(result['error_stage'],'response_json')
                self.assertIsNone(result['usage']);self.assertIsNone(result['provider_cost_microusd'])
                self.safe(result)

    def test_numeric_cost_rounding_is_exact_at_integer_boundary(self):
        raw=b'{"choices":[{"message":{"content":"{\\"answer\\":\\"ok\\"}"}}],"usage":{"prompt_tokens":1,"completion_tokens":2,"cost":0.00000100000000000000000000000000001}}'
        result,calls=self.call(raw=raw)
        self.assertEqual(result['provider_cost_microusd'],2)
        self.assertEqual(len(calls),1)

    def test_invalid_cost_does_not_discard_known_tokens(self):
        for cost in (-1,True,'Infinity','NaN','not-cost'):
            with self.subTest(cost=cost):
                result,_=self.call(self.response(usage={'prompt_tokens':1,'completion_tokens':2,'cost':cost}))
                self.assertEqual(result['usage_status'],'known')
                self.assertEqual(result['cost_status'],'invalid')
                self.assertIsNone(result['provider_cost_microusd'])
        result,_=self.call(self.response(usage={'prompt_tokens':0,'completion_tokens':0,'cost':0}))
        self.assertEqual(result['provider_cost_microusd'],0)
        self.assertEqual(result['usage'],{'input_tokens':0,'output_tokens':0})

    def test_unknown_tokens_never_invented_even_when_cost_is_known(self):
        for usage in ({},{'prompt_tokens':True,'completion_tokens':2,'cost':1},
                      {'prompt_tokens':1.0,'completion_tokens':2,'cost':1},
                      {'prompt_tokens':-1,'completion_tokens':2,'cost':1}):
            with self.subTest(usage=usage):
                result,_=self.call(self.response(usage=usage))
                self.assertEqual(result['status'],'valid')
                self.assertIsNone(result['usage']);self.assertEqual(result['usage_status'],'unknown')

    def test_bounds_fail_closed_and_content_bound_keeps_telemetry(self):
        result,calls=self.call(self.response(),max_response_bytes=2)
        self.assertEqual(len(calls),1);self.assertEqual(result['error_stage'],'response_size')
        self.assertIsNone(result['usage'])
        result,calls=self.call(self.response(),max_body_bytes=2)
        self.assertEqual(len(calls),1);self.assertEqual(result['error_stage'],'body_size')
        self.assertEqual(result['usage_status'],'known');self.assertIsNone(result['body'])

    def test_credential_echo_and_arbitrary_provider_metadata_are_not_returned(self):
        response=self.response('{"answer":"'+SECRET+'"}')
        response.update(id=SECRET,model=SECRET,provider=SECRET)
        result,_=self.call(response)
        self.assertEqual(result['error_stage'],'credential_echo')
        self.assertIsNone(result['body']);self.assertIsNone(result['served_model'])
        self.assertIsNone(result['served_provider']);self.assertIsNone(result['generation_id'])
        self.assertEqual(result['usage_status'],'known');self.safe(result)

    def test_text_parts_exclude_reasoning_parts(self):
        response=self.response([{'type':'reasoning','text':SECRET},
                                {'type':'text','text':'{"answer":"ok"}'}])
        result,_=self.call(response)
        self.assertEqual(result['body'],b'{"answer":"ok"}');self.safe(result)

    def test_preflight_failure_makes_no_http_call(self):
        for change in ({'api_key':''},{'timeout':0},{'max_completion_tokens':True},
                       {'schema':{'type':'invalid-type'}},{'allow_fallbacks':'yes'}):
            with self.subTest(change=change):
                result,calls=self.call(self.response(),**change)
                self.assertEqual(calls,[]);self.assertEqual(result['status'],'not_dispatched')
                self.assertFalse(result['transport_attempted']);self.assertIsNone(result['usage'])

    def test_provider_error_on_200_retains_usage_without_error_text(self):
        response=self.response();response['error']={'message':SECRET}
        result,calls=self.call(response)
        self.assertEqual(len(calls),1);self.assertEqual(result['error_stage'],'provider_error')
        self.assertEqual(result['usage_status'],'known');self.assertIsNone(result['body']);self.safe(result)

    def test_error_diagnostics_keep_only_allowlisted_provider_hints(self):
        prompt = 'PRIVATE research evidence and secret candidate names'
        nested = {'error': {'code': 400, 'status': 'INVALID_ARGUMENT',
            'message': 'Invalid JSON schema: ' + prompt + ' ' + SECRET,
            'details': [{'prompt': prompt, 'credential': SECRET}]}}
        response = {'error': {'code': 'invalid_request_error',
            'param': 'response_format.json_schema.schema', 'message': 'Provider returned error',
            'metadata': {'raw': json.dumps(nested), 'prompt': prompt, 'key': SECRET}}}
        result, calls = self.call(response, status=400, runtime_prompt_text=prompt)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['error_stage'], 'http')
        self.assertEqual(result['error_diagnostics'], {
            'version': 1, 'provider_codes': ['invalid_argument', 'invalid_request_error'],
            'provider_parameters': ['response_format.json_schema.schema'],
            'provider_schema_keywords': [], 'provider_reported_hints': ['schema_rejected']})
        self.assertIsNone(result['usage'])
        self.assertIsNone(result['provider_cost_microusd'])
        self.assertEqual(result['cost_status'], 'unknown')
        self.assertNotIn(prompt, repr(result)); self.safe(result)

    def test_error_diagnostics_never_copy_arbitrary_fields_or_nested_payloads(self):
        for error in (None, SECRET, [SECRET],
                {'type': SECRET, 'code': SECRET, 'param': SECRET,
                 'message': SECRET, 'metadata': {'raw': SECRET}},
                {'message': 'x' * 4097 + ' invalid schema',
                 'metadata': {'raw': 'x' * 8193 + ' invalid schema'}},
                {'metadata': {'raw': '{"error":{"code":"invalid_argument","code":"' + SECRET + '"}}'}},
                {'metadata': {'raw': json.dumps({'error': {'metadata': {'raw': json.dumps({
                    'error': {'code': 'invalid_argument'}})}}})}}):
            with self.subTest(error_type=type(error).__name__):
                result, calls = self.call({'error': error}, status=400)
                self.assertEqual(len(calls), 1)
                self.assertEqual(result['error_diagnostics'], {'version': 1,
                    'provider_codes': [], 'provider_parameters': [], 'provider_schema_keywords': [],
                    'provider_reported_hints': []})
                self.assertIsNone(result['body']); self.safe(result)

    def test_schema_keyword_diagnostics_require_explicit_rejection(self):
        prompt = 'PRIVATE_SOURCE_TEXT'
        for phrase, keyword in (
                ('Unknown name "maxItems" at request.schema.private_path', 'maxItems'),
                ("Unsupported keyword: 'additionalProperties'", 'additionalProperties'),
                ('Unrecognized schema field `$ref`', '$ref'),
                ('Unsupported schema keyword anyOf', 'anyOf'),
                ('unknown field "$defs"', '$defs')):
            with self.subTest(keyword=keyword):
                nested = {'error': {'message': phrase + ' ' + SECRET + ' ' + prompt}}
                result, calls = self.call({'error': {'metadata': {'raw': json.dumps(nested)}}}, status=400)
                self.assertEqual(len(calls), 1)
                self.assertEqual(result['error_diagnostics']['provider_schema_keywords'], [keyword])
                self.assertIn('schema_keyword_rejected', result['error_diagnostics']['provider_reported_hints'])
                self.assertNotIn('private_path', repr(result)); self.assertNotIn(prompt, repr(result))
                self.assertIsNone(result['provider_cost_microusd']); self.safe(result)
        for message in ('Schema contains maxItems and anyOf', 'Unknown name "maxItemsPrivate"',
                        'Unsupported keyword "privateField"', 'Unknown name "response.maxItems"',
                        'x' * 4097 + ' Unknown name "maxItems"'):
            result, _ = self.call({'error': {'message': message}}, status=400)
            self.assertEqual(result['error_diagnostics']['provider_schema_keywords'], [])
            self.assertNotIn('schema_keyword_rejected', result['error_diagnostics']['provider_reported_hints'])

    def test_diagnostic_hints_do_not_change_known_billing_or_success_shape(self):
        for message, hint in (
                ('Unsupported parameter supplied', 'parameter_rejected'),
                ('Maximum context length exceeded', 'context_limit_reported'),
                ('No endpoints found for request', 'route_unavailable_reported')):
            response = self.response()
            response['error'] = {'message': message, 'code': 'unsupported_parameter'}
            result, calls = self.call(response)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result['error_stage'], 'provider_error')
            self.assertEqual(result['error_diagnostics']['provider_reported_hints'], [hint])
            self.assertEqual(result['usage_status'], 'known')
            self.assertEqual(result['provider_cost_microusd'], 2)
        result, _ = self.call(self.response())
        self.assertNotIn('error_diagnostics', result)

    def test_external_schema_reference_cannot_add_hidden_network_io(self):
        result,calls=self.call(self.response(),schema={'$ref':'https://example.invalid/schema'})
        self.assertEqual(calls,[])
        self.assertEqual(result['status'],'not_dispatched')
        self.assertEqual(result['error_stage'],'preflight')

    def test_default_transport_disables_redirects_and_bounds_success_read(self):
        response=MagicMock()
        response.__enter__.return_value=response
        response.status=200;response.headers={};response.read.return_value=b'{}'
        opener=MagicMock();opener.open.return_value=response
        with patch('turbo.agents.openrouter_attempt.urllib.request.build_opener',return_value=opener) as build:
            self.assertEqual(_no_redirect_transport('https://openrouter.ai/api/v1/chat/completions',
                {'Authorization':'Bearer '+SECRET},b'{}',30),(200,{},b'{}'))
        opener.open.assert_called_once()
        response.read.assert_called_once_with(MAX_RESPONSE_BYTES+1)
        handler=build.call_args.args[0]
        self.assertIsInstance(handler,_NoRedirect)
        handler.parent=MagicMock()
        request=urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',
            data=b'{}',headers={'Authorization':'Bearer '+SECRET})
        for status in (301,302,303,307,308):
            stream=MagicMock()
            method=getattr(handler,'http_error_'+str(status))
            self.assertIsNone(method(request,stream,status,'redirect',{'location':'https://other.invalid/receive'}))
            stream.read.assert_not_called()
        handler.parent.open.assert_not_called()

    def test_http_redirect_error_body_is_bounded_without_followup(self):
        class RecordedStream(io.BytesIO):
            def __init__(self):
                super().__init__(b'redirect body');self.read_sizes=[]
            def read(self,size=-1):
                self.read_sizes.append(size)
                return super().read(size)
        stream=RecordedStream()
        error=urllib.error.HTTPError('https://openrouter.ai/api/v1/chat/completions',302,
            'omitted',{'Location':'https://other.invalid/'+SECRET},stream)
        opener=MagicMock();opener.open.side_effect=error
        with patch('turbo.agents.openrouter_attempt.urllib.request.build_opener',return_value=opener):
            status,headers,body=_no_redirect_transport('https://openrouter.ai/api/v1/chat/completions',
                {'Authorization':'Bearer '+SECRET},b'{}',30)
        self.assertEqual(status,302);self.assertEqual(body,b'redirect body')
        opener.open.assert_called_once();self.assertEqual(stream.read_sizes,[MAX_RESPONSE_BYTES+1])

    def test_unicode_escaped_credential_in_value_or_key_is_suppressed(self):
        escaped=''.join('\\u%04x'%ord(character) for character in SECRET)
        for content in ('{"answer":"'+escaped+'"}', '{"'+escaped+'":"value"}'):
            with self.subTest(content=content):
                result,calls=self.call(self.response(content))
                self.assertEqual(len(calls),1)
                self.assertEqual(result['error_stage'],'credential_echo')
                self.assertIsNone(result['body'])
                self.assertEqual(result['usage_status'],'known');self.safe(result)


if __name__=='__main__':
    unittest.main()
