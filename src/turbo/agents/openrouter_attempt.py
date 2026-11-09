"""One bounded provider attempt after a caller has durably recorded dispatch.

This adapter has no retry, repair, reservation, or spend authority. Telemetry may
remain unknown even when final content is usable; callers must reconcile it.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_CEILING, localcontext
import hashlib
import json
import math
import os
import re
from typing import Any
import urllib.error
import urllib.request

from jsonschema import Draft202012Validator

from turbo.agents.batch_output import _strict_json
from turbo.agents.openrouter_runner import (
    OPENROUTER_CHAT_COMPLETIONS_URL, Transport,
    _message_content, openrouter_request_body, openrouter_schema,
)

MAX_RESPONSE_BYTES = 4_000_000
MAX_BODY_BYTES = 1_000_000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        # A redirect is another physical request and could forward Authorization.
        return None


def _no_redirect_transport(url: str, headers: dict[str, str], body: bytes,
                           timeout_seconds: float) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method='POST')
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            return response.status, dict(response.headers.items()), response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        with error:
            return error.code, dict(error.headers.items()), error.read(MAX_RESPONSE_BYTES + 1)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def _local_references(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ('$ref', '$dynamicRef') and (not isinstance(child, str) or not child.startswith('#')):
                raise ValueError('external schema references are not supported')
            _local_references(child)
    elif isinstance(value, list):
        for child in value:
            _local_references(child)


def _contains_secret(value: Any, secret: str) -> bool:
    if isinstance(value, str):
        return secret in value
    if isinstance(value, dict):
        return any(_contains_secret(key, secret) or _contains_secret(child, secret)
                   for key, child in value.items())
    if isinstance(value, list):
        return any(_contains_secret(child, secret) for child in value)
    return False


def _number(value: str) -> Decimal:
    if len(value) > 128:
        raise ValueError('numeric resource bound')
    number = Decimal(value)
    if not number.is_finite() or abs(number.adjusted()) > 1000:
        raise ValueError('numeric resource bound')
    return number


def _integer(value: str) -> int:
    if len(value) > 128:
        raise ValueError('numeric resource bound')
    return int(value)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('nonfinite JSON')


def _response_json(raw: bytes) -> dict:
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                       parse_float=_number, parse_int=_integer, parse_constant=_constant)
    if not isinstance(value, dict):
        raise ValueError('response must be an object')
    return value


def _metadata(value: Any, secret: str) -> str | None:
    # Only bounded identifiers, never provider error messages or arbitrary metadata.
    if (not isinstance(value, str) or not 1 <= len(value) <= 256
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ._:/@+()\-]*', value)
            or secret in value):
        return None
    return value


def _telemetry(value: Any) -> tuple[dict | None, int | None, str]:
    if not isinstance(value, dict):
        return None, None, 'unknown'
    prompt, completion = value.get('prompt_tokens'), value.get('completion_tokens')
    usage = ({'input_tokens': prompt, 'output_tokens': completion}
             if type(prompt) is int and type(completion) is int
             and prompt >= 0 and completion >= 0 else None)
    cost, cost_status = None, 'unknown'
    if 'cost' in value:
        raw = value['cost']
        try:
            if isinstance(raw, bool) or not isinstance(raw, (int, Decimal, str)):
                raise ValueError('invalid cost')
            amount = _number(str(raw))
            if amount < 0:
                raise ValueError('negative cost')
            with localcontext() as context:
                context.prec = len(amount.as_tuple().digits) + max(amount.adjusted(), 0) + 12
                cost = int((amount * Decimal(1_000_000)).to_integral_value(rounding=ROUND_CEILING))
            cost_status = 'known'
        except (ValueError, InvalidOperation, OverflowError):
            cost_status = 'invalid'
    return usage, cost, cost_status


def routing_request_fields(routing: dict) -> dict:
    """Validate the narrow V1 policy; convert decimal strings only at the wire edge."""
    if (not isinstance(routing, dict) or set(routing) - {'schema_version', 'provider', 'prompt_cache_options'}
            or type(routing.get('schema_version')) is not int or routing['schema_version'] != 1):
        raise ValueError('invalid routing policy version or keys')
    provider = routing.get('provider')
    if not isinstance(provider, dict) or set(provider) != {'only', 'ignore', 'max_price'}:
        raise ValueError('invalid provider routing keys')
    result = {'require_parameters': True, 'allow_fallbacks': False}
    for name in ('only', 'ignore'):
        slugs = provider[name]
        if (not isinstance(slugs, list) or len(slugs) > 32 or (name == 'only' and not slugs)
                or any(not isinstance(s, str) or len(s) > 128
                       or not re.fullmatch(r'[a-z0-9][a-z0-9._/-]*', s) for s in slugs)
                or len(set(slugs)) != len(slugs)):
            raise ValueError('invalid provider restrictions')
        result[name] = list(slugs)
    prices = provider['max_price']
    if not isinstance(prices, dict) or set(prices) != {'prompt', 'completion'}:
        raise ValueError('both price caps are required')
    result['max_price'] = {}
    for name, raw in prices.items():
        if (not isinstance(raw, str) or len(raw) > 32
                or not re.fullmatch(r'(0|[1-9][0-9]*)(\.[0-9]+)?', raw)):
            raise ValueError('price caps require nonnegative decimal strings')
        amount = Decimal(raw)
        number = int(amount) if amount == amount.to_integral_value() else float(amount)
        # Reject conversion that would change the JSON numeric value or exceed safe integers.
        if amount > 2**53 - 1 or Decimal(json.dumps(number, allow_nan=False)) != amount:
            raise ValueError('price cap is not exactly representable on the JSON wire')
        result['max_price'][name] = number
    fields = {'provider': result}
    if 'prompt_cache_options' in routing:
        if routing['prompt_cache_options'] != {'mode': 'explicit'}:
            raise ValueError('unsupported prompt cache options')
        fields['prompt_cache_options'] = {'mode': 'explicit'}
    return fields


def bounded_request_body(*, routing: dict | None = None, **options) -> dict:
    """Single request construction path for managed admission and dispatch."""
    request = openrouter_request_body(**options)
    if routing is not None:
        if options.get('allow_fallbacks') is not False:
            raise ValueError('routing policy forbids fallbacks')
        fields = routing_request_fields(routing)
        if 'prompt_cache_options' in fields and not options['model'].startswith('openai/'):
            raise ValueError('explicit cache mode requires an OpenAI model')
        request.update(fields)
    return request


def invoke_openrouter_once(
    *, invocation_id: str, role: str, model: str, reasoning_effort: str,
    runtime_prompt_text: str, schema: dict[str, Any], max_completion_tokens: int,
    timeout: float, allow_fallbacks: bool = False, routing: dict | None = None, api_key: str | None = None,
    transport: Transport = _no_redirect_transport,
    max_response_bytes: int = MAX_RESPONSE_BYTES, max_body_bytes: int = MAX_BODY_BYTES,
) -> dict[str, Any]:
    """Return sanitized evidence of exactly one call, with no automatic retry.

    ``status=valid`` concerns canonical-schema content only, never spend settlement.
    Missing/invalid token or cost telemetry is explicit, never replaced by zero.
    The default transport never follows redirects and bounds the HTTP body read.
    Response and final-content parsing are also bounded.
    """
    secret = api_key if api_key is not None else os.environ.get('OPENROUTER_API_KEY')
    secret = secret if isinstance(secret, str) else ''
    result = dict(status='not_dispatched', body=None, usage=None, usage_status='unknown',
                  provider_cost_microusd=None, cost_status='unknown',
                  invocation_id=None, role=None, requested_model=None,
                  served_model=None, served_provider=None, generation_id=None,
                  request_sha256=None, schema_sha256=None, provider_schema_sha256=None,
                  response_sha256=None, body_sha256=None, http_status=None,
                  error_stage='preflight', transport_attempted=False)
    try:
        if (not secret or not all(isinstance(x, str) and x.strip() for x in
                (invocation_id, role, model, reasoning_effort, runtime_prompt_text))
                or type(max_completion_tokens) is not int or max_completion_tokens <= 0
                or isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout) or timeout <= 0
                or type(allow_fallbacks) is not bool
                or any(type(n) is not int or n <= 0 for n in (max_response_bytes, max_body_bytes))
                or max_response_bytes > MAX_RESPONSE_BYTES or max_body_bytes > MAX_BODY_BYTES
                or not isinstance(schema, dict)):
            return result
        _local_references(schema)
        Draft202012Validator.check_schema(schema)
        schema_bytes = _canonical(schema)
        provider_schema = openrouter_schema(schema)
        request = bounded_request_body(routing=routing, role_id=role, model=model, reasoning_effort=reasoning_effort,
            runtime_prompt_text=runtime_prompt_text, schema=provider_schema,
            invocation_id=invocation_id, max_completion_tokens=max_completion_tokens,
            allow_fallbacks=allow_fallbacks, schema_name='turbo_workflow_role')
        request_bytes = _canonical(request)
        result.update(invocation_id=_metadata(invocation_id, secret), role=_metadata(role, secret),
                      requested_model=_metadata(model, secret), request_sha256=_sha(request_bytes),
                      schema_sha256=_sha(schema_bytes), provider_schema_sha256=_sha(_canonical(provider_schema)))
    except Exception:
        # Validation exceptions may contain input/schema text; never echo them.
        return result
    headers = {'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json',
               'HTTP-Referer': 'https://github.com/michaelsena/turbo', 'X-Title': 'Turbo'}
    result.update(transport_attempted=True, status='unknown', error_stage='transport')
    try:
        returned = transport(OPENROUTER_CHAT_COMPLETIONS_URL, headers, request_bytes, float(timeout))
    except Exception:
        return result
    try:
        result['error_stage'] = 'transport_contract'
        status, _, raw = returned
        if type(status) is not int or not 100 <= status <= 599 or type(raw) is not bytes:
            result['error_stage'] = 'transport_contract'
            return result
        result.update(http_status=status, response_sha256=_sha(raw))
        if len(raw) > max_response_bytes:
            result['error_stage'] = 'response_size'
            return result
        result['error_stage'] = 'response_json'
        response = _response_json(raw)
    except Exception:
        return result
    usage, cost, cost_status = _telemetry(response.get('usage'))
    result.update(usage=usage, usage_status='known' if usage is not None else 'unknown',
                  provider_cost_microusd=cost, cost_status=cost_status,
                  served_model=_metadata(response.get('model'), secret),
                  served_provider=_metadata(response.get('provider'), secret),
                  generation_id=_metadata(response.get('id'), secret))
    if status != 200:
        result.update(status='invalid', error_stage='http')
        return result
    if response.get('error') is not None:
        result.update(status='invalid', error_stage='provider_error')
        return result
    try:
        result['error_stage'] = 'content'
        content = _message_content(response)
        body = content.encode('utf-8')
        result['body_sha256'] = _sha(body)
        if len(body) > max_body_bytes:
            result.update(status='invalid', error_stage='body_size')
            return result
        if secret in content:
            result.update(status='invalid', error_stage='credential_echo')
            return result
        result['body'] = body
        result['error_stage'] = 'content_json'
        parsed = _strict_json(body)
        if _contains_secret(parsed, secret):
            result.update(status='invalid', error_stage='credential_echo', body=None)
            return result
        result['error_stage'] = 'content_schema'
        if not Draft202012Validator(schema).is_valid(parsed):
            result['status'] = 'invalid'
            return result
    except Exception:
        result['status'] = 'invalid'
        return result
    result.update(status='valid', error_stage=None)
    return result
