from __future__ import annotations

import json
import os
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from turbo.agents.boundary_harness import (
    canonical_sha256,
    load_adjudication_schema,
    load_specialist_schema,
    validate_boundary_output,
)
from turbo.agents.runtime import InvocationResult, runtime_prompt, sha256_text, utc_now
from turbo.pipeline_paths import ROOT


OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
Transport = Callable[
    [str, dict[str, str], bytes, float], tuple[int, dict[str, str], bytes]
]

# Providers differ in which optional JSON-Schema validation keywords they accept.
# Keep the model-facing schema portable and enforce the complete canonical schema
# again with Turbo's local validator before accepting an output.
PROVIDER_UNSAFE_SCHEMA_KEYWORDS = {
    "exclusiveMaximum",
    "exclusiveMinimum",
    "maximum",
    "minimum",
    "multipleOf",
    "uniqueItems",
}


def openrouter_schema(value: object) -> object:
    if isinstance(value, dict):
        adapted = {
            key: openrouter_schema(child)
            for key, child in value.items()
            if key not in PROVIDER_UNSAFE_SCHEMA_KEYWORDS
        }
        if "type" not in adapted:
            if "const" in adapted:
                adapted["type"] = _json_schema_type(adapted["const"])
            elif isinstance(adapted.get("enum"), list):
                inferred = []
                for item in adapted["enum"]:
                    item_type = _json_schema_type(item)
                    if item_type not in inferred:
                        inferred.append(item_type)
                adapted["type"] = inferred[0] if len(inferred) == 1 else inferred
        return adapted
    if isinstance(value, list):
        return [openrouter_schema(child) for child in value]
    return value



def openrouter_role_schema(value: object, *, role_id: str, model: str) -> object:
    """Provider-facing compatibility only; callers still validate the original.

    Gemini compiles array bounds into its output grammar. The release schema's
    large findings bound can exceed that compiler's state budget. Omit only this
    bound for Google release reviewers; the canonical schema remains authoritative.
    """
    adapted = openrouter_schema(value)
    if role_id == "release_reviewer" and model.startswith("google/") and isinstance(adapted, dict):
        properties = adapted.get("properties")
        findings = properties.get("findings") if isinstance(properties, dict) else None
        if isinstance(findings, dict) and findings.get("type") == "array":
            findings.pop("maxItems", None)
    return adapted


def _json_schema_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise TypeError(f"unsupported JSON Schema constant type: {type(value).__name__}")


def _safe_error_summary(response_bytes: bytes) -> str:
    try:
        payload = json.loads(response_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "unparseable provider error response omitted"
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return "provider error response omitted"
    summary: dict[str, Any] = {
        key: error.get(key) for key in ("code", "message") if error.get(key) is not None
    }
    metadata = error.get("metadata")
    if isinstance(metadata, dict):
        summary["metadata"] = {
            key: metadata.get(key)
            for key in ("provider_error_code", "provider_name")
            if metadata.get(key) is not None
        }
    return json.dumps(summary, sort_keys=True)


def _default_transport(
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout_seconds: float,
) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read()


def openrouter_request_body(
    *,
    role_id: str,
    model: str,
    reasoning_effort: str,
    runtime_prompt_text: str,
    schema: dict[str, Any],
    invocation_id: str,
    max_completion_tokens: int,
    allow_fallbacks: bool,
    schema_name: str | None = None,
) -> dict[str, Any]:
    schema_name = schema_name or (
        "turbo_boundary_adjudication"
        if role_id == "adjudicator"
        else "turbo_boundary_specialist"
    )
    return {
        "model": model,
        "messages": [{"role": "user", "content": runtime_prompt_text}],
        "reasoning": {"effort": reasoning_effort, "exclude": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        },
        "provider": {
            "require_parameters": True,
            "allow_fallbacks": allow_fallbacks,
        },
        "max_completion_tokens": max_completion_tokens,
        "stream": False,
        "usage": {"include": True},
        "session_id": invocation_id,
    }


def _message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise RuntimeError("OpenRouter response must contain exactly one choice")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("OpenRouter response choice has no message")
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        if text_parts:
            return "".join(text_parts)
    raise RuntimeError("OpenRouter response message has no text content")


def _usage_receipt(usage: object) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {}

    def safe_value(value: object) -> object | None:
        if value is None or isinstance(value, (int, float, bool)):
            return value
        if isinstance(value, dict):
            return {
                key: safe
                for key, child in value.items()
                if (safe := safe_value(child)) is not None
            }
        return None

    return {
        key: safe
        for key, value in usage.items()
        if (safe := safe_value(value)) is not None
    }


def invoke_openrouter_role(
    *,
    role_id: str,
    model: str,
    reasoning_effort: str,
    prompt_path: Path,
    pack: dict[str, Any],
    specialist_outputs: list[dict[str, Any]] | None = None,
    timeout_seconds: int = 1800,
    max_completion_tokens: int = 128_000,
    allow_fallbacks: bool = True,
    max_attempts: int = 3,
    max_validation_repairs: int = 2,
    api_url: str = OPENROUTER_CHAT_COMPLETIONS_URL,
    api_key: str | None = None,
    transport: Transport = _default_transport,
    sleeper: Callable[[float], None] = time.sleep,
    root: Path = ROOT,
) -> InvocationResult:
    if role_id not in {"specialist-a", "specialist-b", "adjudicator"}:
        raise ValueError(f"unsupported boundary role: {role_id}")
    if role_id == "adjudicator" and (
        specialist_outputs is None or len(specialist_outputs) != 2
    ):
        raise ValueError("adjudicator requires exactly two validated specialist outputs")
    if role_id != "adjudicator" and specialist_outputs is not None:
        raise ValueError("blind specialists cannot receive specialist outputs")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")
    if max_validation_repairs < 0:
        raise ValueError("max_validation_repairs cannot be negative")

    secret = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not secret:
        raise RuntimeError(
            "OPENROUTER_API_KEY is required; store it outside Git and export it locally"
        )

    invocation_id = f"invocation:{secrets.token_hex(12)}"
    base_prompt = prompt_path.read_text(encoding="utf-8")
    initial_prompt = runtime_prompt(
        base_prompt,
        role_id=role_id,
        invocation_id=invocation_id,
        pack=pack,
        specialist_outputs=specialist_outputs,
    )
    schema = (
        load_adjudication_schema(root=root)
        if role_id == "adjudicator"
        else load_specialist_schema(root=root)
    )
    provider_schema = openrouter_schema(schema)
    if not isinstance(provider_schema, dict):
        raise RuntimeError("OpenRouter schema adapter did not return an object")
    headers = {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/michaelsena/turbo",
        "X-Title": "Turbo",
        "X-OpenRouter-Metadata": "enabled",
    }
    model_calls: list[dict[str, Any]] = []
    prior_errors: list[str] = []
    prior_output_sha256: str | None = None
    for validation_round in range(max_validation_repairs + 1):
        prompt = initial_prompt
        if validation_round:
            correction = {
                "instruction": (
                    "Regenerate the complete JSON output from the frozen pack. "
                    "Correct every listed validator error; do not return a patch."
                ),
                "prior_output_sha256": prior_output_sha256,
                "prior_validation_errors": prior_errors,
                "validation_round": validation_round,
            }
            prompt += "\n\n# Required correction round\n\n" + json.dumps(
                correction, sort_keys=True, separators=(",", ":")
            )
        request_payload = openrouter_request_body(
            role_id=role_id,
            model=model,
            reasoning_effort=reasoning_effort,
            runtime_prompt_text=prompt,
            schema=provider_schema,
            invocation_id=invocation_id,
            max_completion_tokens=max_completion_tokens,
            allow_fallbacks=allow_fallbacks,
        )
        request_text = json.dumps(
            request_payload, sort_keys=True, separators=(",", ":")
        )
        request_bytes = request_text.encode("utf-8")
        started_at = utc_now()
        started_monotonic = time.monotonic()
        status_code = 0
        response_bytes = b""
        attempts = 0
        for attempts in range(1, max_attempts + 1):
            status_code, _, response_bytes = transport(
                api_url, headers, request_bytes, float(timeout_seconds)
            )
            if status_code == 200:
                break
            if status_code not in RETRYABLE_STATUS_CODES or attempts == max_attempts:
                break
            sleeper(min(2 ** (attempts - 1), 8))

        receipt: dict[str, Any] = {
            "schema_version": 1,
            "provider": "openrouter",
            "api_surface": "chat_completions",
            "invocation_id": invocation_id,
            "role_id": role_id,
            "family_id": pack["metadata"]["family_id"],
            "requested_model": model,
            "reasoning_effort": reasoning_effort,
            "validation_round": validation_round,
            "started_at_utc": started_at,
            "completed_at_utc": utc_now(),
            "elapsed_ms": round((time.monotonic() - started_monotonic) * 1000),
            "attempts": attempts,
            "http_status": status_code,
            "prompt_sha256": sha256_text(base_prompt),
            "runtime_prompt_sha256": sha256_text(prompt),
            "schema_sha256": canonical_sha256(schema),
            "provider_schema_sha256": canonical_sha256(provider_schema),
            "request_sha256": sha256_text(request_text),
            "response_sha256": sha256_text(
                response_bytes.decode("utf-8", errors="replace")
            ),
            "input_pack_sha256": pack["metadata"]["pack_sha256"],
            "raw_reasoning_persisted": False,
            "credential_persisted": False,
            "status": "failed",
        }
        if status_code != 200:
            error_summary = _safe_error_summary(response_bytes)
            raise RuntimeError(
                f"{role_id} OpenRouter invocation failed with HTTP {status_code}; "
                f"error={error_summary}; receipt={json.dumps(receipt, sort_keys=True)}"
            )
        try:
            response = json.loads(response_bytes)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"{role_id} OpenRouter response was not JSON: {error}"
            ) from error

        receipt.update(
            {
                "generation_id": response.get("id"),
                "served_model": response.get("model"),
                "served_provider": response.get("provider"),
                "service_tier": response.get("service_tier"),
                "system_fingerprint": response.get("system_fingerprint"),
                "usage": _usage_receipt(response.get("usage")),
            }
        )
        try:
            output = json.loads(_message_content(response))
        except json.JSONDecodeError as error:
            raise RuntimeError(f"{role_id} final output was not JSON: {error}") from error
        errors = validate_boundary_output(
            output,
            pack,
            expected_role=role_id,
            specialist_outputs=specialist_outputs,
            root=root,
        )
        receipt["output_sha256"] = canonical_sha256(output)
        receipt["validation_errors"] = errors
        receipt["status"] = "valid" if not errors else "invalid"
        model_calls.append(receipt)
        if not errors:
            final_receipt = dict(receipt)
            final_receipt["model_calls"] = [dict(item) for item in model_calls]
            final_receipt["validation_repairs_used"] = validation_round
            return InvocationResult(output=output, receipt=final_receipt)
        prior_errors = errors
        prior_output_sha256 = receipt["output_sha256"]

    raise RuntimeError(
        f"{role_id} output failed closed-world validation after "
        f"{max_validation_repairs + 1} model calls: {json.dumps(prior_errors)}"
    )
