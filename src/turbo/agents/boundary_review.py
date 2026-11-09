from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from turbo.agents.boundary_harness import canonical_sha256
from turbo.agents.boundary_runner import _git_head, validate_boundary_run
from turbo.agents.openrouter_runner import (
    OPENROUTER_CHAT_COMPLETIONS_URL,
    RETRYABLE_STATUS_CODES,
    _default_transport,
    _message_content,
    _safe_error_summary,
    _usage_receipt,
    openrouter_request_body,
    openrouter_schema,
)
from turbo.agents.runtime import sha256_text, utc_now
from turbo.pipeline_paths import ROOT
from turbo.universe.boundary_pack import build_boundary_pack


REQUIRED_CHECK_IDS = {
    "check:activation-safety",
    "check:boundary-evidence",
    "check:candidate-scope",
    "check:gap-calibration",
    "check:identity-dispositions",
}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write_receipt(review_dir: Path, receipt: dict[str, Any]) -> None:
    (review_dir / "review.receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def build_review_envelope(
    review_config_path: Path,
    boundary_config_path: Path,
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    config = _load_json(review_config_path)
    run_dir = root / config["target_run_dir"]
    replay = validate_boundary_run(run_dir, boundary_config_path, root=root)
    if not replay["valid"]:
        raise RuntimeError(f"target boundary run failed replay: {replay['errors']}")
    run_receipt = _load_json(run_dir / "run-receipt.json")
    if replay["boundary_run_id"] != config["target_run_id"]:
        raise RuntimeError("review target_run_id does not match the replayed run")
    if replay["input_pack_sha256"] != config["target_pack_sha256"]:
        raise RuntimeError("review target_pack_sha256 does not match the replayed run")
    if run_receipt["adjudication_output_sha256"] != config[
        "target_adjudication_sha256"
    ]:
        raise RuntimeError("review target_adjudication_sha256 does not match the run")
    pack = build_boundary_pack(boundary_config_path, root=root)
    envelope = {
        "review_config": config,
        "required_check_ids": sorted(REQUIRED_CHECK_IDS),
        "frozen_evidence_pack": pack,
        "target_outputs": {
            role: _load_json(run_dir / f"{role}.json")
            for role in ("specialist-a", "specialist-b", "adjudicator")
        },
        "target_run_receipt": run_receipt,
    }
    envelope["review_input_sha256"] = canonical_sha256(envelope)
    return envelope


def validate_review_output(
    output: dict[str, Any],
    envelope: dict[str, Any],
    *,
    root: Path = ROOT,
) -> list[str]:
    schema = _load_json(root / "schemas/boundary-independent-review.schema.json")
    errors = sorted(
        f"schema:{'/'.join(str(part) for part in error.absolute_path) or '<root>'}:"
        f"{error.message}"
        for error in Draft202012Validator(schema).iter_errors(output)
    )
    if errors:
        return errors
    config = envelope["review_config"]
    exact = {
        "review_id": config["review_id"],
        "target_run_id": config["target_run_id"],
        "target_pack_sha256": config["target_pack_sha256"],
        "target_adjudication_sha256": config["target_adjudication_sha256"],
    }
    for field, expected in exact.items():
        if output[field] != expected:
            errors.append(f"{field} does not match the preregistered review")
    check_ids = [item["check_id"] for item in output["checks"]]
    if len(check_ids) != len(set(check_ids)):
        errors.append("checks contain duplicate IDs")
    if set(check_ids) != REQUIRED_CHECK_IDS:
        errors.append("checks do not cover the exact registered check IDs")
    finding_ids = [item["finding_id"] for item in output["findings"]]
    if len(finding_ids) != len(set(finding_ids)):
        errors.append("findings contain duplicate IDs")
    evidence_ids = {
        item["evidence_id"] for item in envelope["frozen_evidence_pack"]["evidence_catalog"]
    }
    for owner in [*output["checks"], *output["findings"]]:
        unknown = set(owner["evidence_ids"]) - evidence_ids
        if unknown:
            errors.append(f"review cites unknown evidence IDs: {sorted(unknown)}")
    all_checks_pass = all(item["status"] == "pass" for item in output["checks"])
    if output["verdict"] == "approve_activation" and (
        output["findings"] or not all_checks_pass
    ):
        errors.append("approval requires zero findings and every check passing")
    if output["verdict"] != "approve_activation" and not output["activation_conditions"]:
        errors.append("non-approval requires at least one activation condition")
    return sorted(set(errors))


def run_independent_review(
    review_config_path: Path,
    boundary_config_path: Path,
    *,
    output_root: Path | None = None,
    timeout_seconds: int = 1800,
    root: Path = ROOT,
) -> dict[str, Any]:
    secret = os.environ.get("OPENROUTER_API_KEY")
    if not secret:
        raise RuntimeError("OPENROUTER_API_KEY is required")
    config = _load_json(review_config_path)
    envelope = build_review_envelope(review_config_path, boundary_config_path, root=root)
    schema = _load_json(root / "schemas/boundary-independent-review.schema.json")
    provider_schema = openrouter_schema(schema)
    if not isinstance(provider_schema, dict):
        raise RuntimeError("provider review schema must be an object")
    prompt_path = root / "prompts/universe/boundary-independent-review-v1.md"
    prompt = prompt_path.read_text(encoding="utf-8").rstrip()
    prompt += "\n\n# Frozen review envelope\n\n" + json.dumps(
        envelope, sort_keys=True, separators=(",", ":")
    )
    invocation_id = f"review-invocation:{secrets.token_hex(12)}"
    payload = openrouter_request_body(
        role_id="independent-review",
        model=config["review_model"],
        reasoning_effort=config["reasoning_effort"],
        runtime_prompt_text=prompt,
        schema=provider_schema,
        invocation_id=invocation_id,
        max_completion_tokens=config["max_completion_tokens"],
        allow_fallbacks=True,
        schema_name="turbo_boundary_independent_review",
    )
    request_text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    request_bytes = request_text.encode("utf-8")
    headers = {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/michaelsena/turbo",
        "X-Title": "Turbo",
    }
    started_at = utc_now()
    started_monotonic = time.monotonic()
    invocation_digest = canonical_sha256({"invocation_id": invocation_id})[:20]
    review_run_id = f"independent-review-{invocation_digest}"
    destination = output_root or root / "data/agent_reviews"
    review_dir = destination / review_run_id
    review_dir.mkdir(parents=True, exist_ok=False)
    status_code = 0
    response_bytes = b""
    attempts = 0
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "review_id": config["review_id"],
        "provider": "openrouter",
        "requested_model": config["review_model"],
        "reasoning_effort": config["reasoning_effort"],
        "invocation_id": invocation_id,
        "started_at_utc": started_at,
        "completed_at_utc": None,
        "elapsed_ms": None,
        "attempts": attempts,
        "http_status": status_code,
        "git_commit": _git_head(root),
        "review_config_sha256": sha256_text(review_config_path.read_text(encoding="utf-8")),
        "review_input_sha256": envelope["review_input_sha256"],
        "prompt_sha256": sha256_text(prompt_path.read_text(encoding="utf-8")),
        "runtime_prompt_sha256": sha256_text(prompt),
        "schema_sha256": canonical_sha256(schema),
        "provider_schema_sha256": canonical_sha256(provider_schema),
        "request_sha256": sha256_text(request_text),
        "response_sha256": None,
        "raw_reasoning_persisted": False,
        "credential_persisted": False,
        "status": "in_progress",
    }
    _write_receipt(review_dir, receipt)
    try:
        for attempts in range(1, config["max_attempts"] + 1):
            receipt["attempts"] = attempts
            _write_receipt(review_dir, receipt)
            status_code, _, response_bytes = _default_transport(
                OPENROUTER_CHAT_COMPLETIONS_URL,
                headers,
                request_bytes,
                float(timeout_seconds),
            )
            receipt["http_status"] = status_code
            receipt["response_sha256"] = sha256_text(
                response_bytes.decode("utf-8", errors="replace")
            )
            _write_receipt(review_dir, receipt)
            if status_code == 200:
                break
            if (
                status_code not in RETRYABLE_STATUS_CODES
                or attempts == config["max_attempts"]
            ):
                break
            time.sleep(min(2 ** (attempts - 1), 8))
    except Exception as error:
        receipt.update(
            {
                "completed_at_utc": utc_now(),
                "elapsed_ms": round((time.monotonic() - started_monotonic) * 1000),
                "failure_stage": "transport",
                "failure_type": type(error).__name__,
                "status": "failed",
            }
        )
        _write_receipt(review_dir, receipt)
        raise RuntimeError(
            f"independent review transport failed; receipt={review_dir / 'review.receipt.json'}"
        ) from error
    receipt.update(
        {
            "completed_at_utc": utc_now(),
            "elapsed_ms": round((time.monotonic() - started_monotonic) * 1000),
            "attempts": attempts,
            "http_status": status_code,
        }
    )
    if status_code != 200:
        receipt.update({"failure_stage": "provider", "status": "failed"})
        _write_receipt(review_dir, receipt)
        raise RuntimeError(
            f"independent review failed with HTTP {status_code}; "
            f"error={_safe_error_summary(response_bytes)}; "
            f"receipt={review_dir / 'review.receipt.json'}"
        )
    try:
        response = json.loads(response_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        receipt.update(
            {
                "failure_stage": "provider_response_parse",
                "failure_type": type(error).__name__,
                "status": "failed",
            }
        )
        _write_receipt(review_dir, receipt)
        raise RuntimeError(
            f"independent review response was not valid JSON; "
            f"receipt={review_dir / 'review.receipt.json'}"
        ) from error
    receipt.update(
        {
            "generation_id": response.get("id"),
            "served_model": response.get("model"),
            "served_provider": response.get("provider"),
            "usage": _usage_receipt(response.get("usage")),
        }
    )
    try:
        output = json.loads(_message_content(response))
    except (json.JSONDecodeError, ValueError, RuntimeError) as error:
        receipt.update(
            {
                "failure_stage": "structured_output_parse",
                "failure_type": type(error).__name__,
                "status": "failed",
            }
        )
        _write_receipt(review_dir, receipt)
        raise RuntimeError(
            f"independent review structured output was invalid; "
            f"receipt={review_dir / 'review.receipt.json'}"
        ) from error
    errors = validate_review_output(output, envelope, root=root)
    receipt["output_sha256"] = canonical_sha256(output)
    receipt["validation_errors"] = errors
    receipt["status"] = "valid" if not errors else "invalid"
    if errors:
        receipt["failure_stage"] = "local_validation"
        _write_receipt(review_dir, receipt)
        raise RuntimeError(
            f"independent review output invalid; "
            f"receipt={review_dir / 'review.receipt.json'}"
        )
    (review_dir / "review.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_receipt(review_dir, receipt)
    return {
        "review_run_id": review_run_id,
        "review_dir": str(review_dir),
        "verdict": output["verdict"],
        "finding_counts": {
            severity: sum(1 for item in output["findings"] if item["severity"] == severity)
            for severity in ("P0", "P1", "P2")
        },
        "output_sha256": receipt["output_sha256"],
        "status": "validated_review_not_activated",
    }
