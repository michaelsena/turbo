"""Exact, simulation-only authorization for a manifest-ordered family batch.

These documents exercise execution controls. They do not authorize paid model calls.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT
from turbo.universe.family_pack_v2 import _verified_schedule, validate_family_preparation_v2


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def utc_datetime(value: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value):
        raise ValueError("time must be an explicit UTC timestamp ending Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("invalid UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("timestamp must be timezone-aware UTC")
    return parsed


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_schema(value: Any, filename: str, root: Path) -> None:
    schema = json.loads((root / "schemas" / filename).read_text())
    errors = sorted(error.message for error in Draft202012Validator(schema).iter_errors(value))
    if errors:
        raise ValueError("schema validation failed: " + "; ".join(errors))
    # JSON Schema's integer permits 1.0. Durable arithmetic accepts actual ints only.
    def strict_numbers(item: Any) -> None:
        if isinstance(item, float):
            raise ValueError("floating-point values are not permitted")
        if isinstance(item, dict):
            for child in item.values(): strict_numbers(child)
        elif isinstance(item, list):
            for child in item: strict_numbers(child)
    strict_numbers(value)


def validate_authorization_document(auth: dict[str, Any], *, root: Path = ROOT) -> None:
    validate_schema(auth, "batch-authorization.schema.json", root)
    expected_schemas = {name: hashlib.sha256((root / "schemas" / name).read_bytes()).hexdigest()
                        for name in ("batch-authorization.schema.json", "batch-execution-event.schema.json")}
    if auth["execution_schema_hashes"] != expected_schemas:
        raise ValueError("execution schema hashes mismatch")
    if utc_datetime(auth["valid_from_utc"]) >= utc_datetime(auth["expires_at_utc"]):
        raise ValueError("authorization validity interval is empty")
    if auth["pricing_sha256"] != canonical_sha256(auth["pricing"]):
        raise ValueError("pricing hash mismatch")
    if len({row["family_id"] for row in auth["families"]}) != len(auth["families"]):
        raise ValueError("duplicate family scope")
    if len({row["preparation_id"] for row in auth["families"]}) != len(auth["families"]):
        raise ValueError("duplicate preparation scope")
    if auth["max_retries"] >= auth["max_calls"]:
        raise ValueError("retry allowance must be below total call allowance")


def _scope(preparation_dirs: Iterable[Path], root: Path) -> tuple[list[dict[str, str]], str]:
    paths = [Path(path) for path in preparation_dirs]
    if not 1 <= len(paths) <= 8:
        raise ValueError("a batch requires one to eight distinct preparations")
    scope = []
    for path in paths:
        replay = validate_family_preparation_v2(path, root=root)
        if not replay["valid"]:
            raise ValueError("preparation cannot replay: " + "; ".join(replay["errors"]))
        scope.append({
            "family_id": replay["family_id"], "preparation_id": replay["preparation_id"],
            "config_sha256": hashlib.sha256((path / "family-config-v2.json").read_bytes()).hexdigest(),
            "pack_file_sha256": hashlib.sha256((path / "family-evidence-pack-v2.json").read_bytes()).hexdigest(),
            "receipt_sha256": hashlib.sha256((path / "preparation-receipt.json").read_bytes()).hexdigest(),
        })
    ids = [row["family_id"] for row in scope]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate family scope")
    _, _, artifacts = _verified_schedule(root=root)
    matches = [batch for batch in artifacts["batch-manifest.json"]["batches"]
               if all(fid in batch["family_ids"] for fid in ids)]
    if len(matches) != 1:
        raise ValueError("families must belong to exactly one schedule batch")
    batch = matches[0]
    if [fid for fid in batch["family_ids"] if fid in ids] != ids:
        raise ValueError("families must retain manifest order")
    return scope, batch["batch_id"]


def max_reservation_microusd(auth: dict[str, Any]) -> int:
    return (auth["max_input_tokens"] * auth["pricing"]["input_microusd_per_token"]
            + auth["max_output_tokens"] * auth["pricing"]["output_microusd_per_token"])


def build_authorization(
    preparation_dirs: Iterable[Path], *, root: Path = ROOT, authorized_by: str,
    valid_from_utc: str, expires_at_utc: str, prompt_sha256: str,
    pricing: dict[str, int], max_cost_microusd: int, max_calls: int,
    model: str = "simulation", max_input_tokens: int = 1000,
    max_output_tokens: int = 1000, max_retries: int = 0,
    max_concurrency: int = 1, lease_seconds: int = 60,
) -> dict[str, Any]:
    families, batch_id = _scope(preparation_dirs, root)
    auth = dict(schema_version=1, mode="simulation_only", provider="simulation",
                budget_scope="single_journal_simulation",
                role="batch_primary", authorized_by=authorized_by,
                valid_from_utc=valid_from_utc, expires_at_utc=expires_at_utc,
                model=model, prompt_sha256=prompt_sha256, pricing=dict(pricing),
                pricing_sha256=canonical_sha256(pricing), max_cost_microusd=max_cost_microusd,
                max_calls=max_calls, max_retries=max_retries, max_concurrency=max_concurrency,
                lease_seconds=lease_seconds, max_input_tokens=max_input_tokens,
                max_output_tokens=max_output_tokens, batch_id=batch_id, families=families, execution_schema_hashes={
                    name: hashlib.sha256((root / "schemas" / name).read_bytes()).hexdigest()
                    for name in ("batch-authorization.schema.json", "batch-execution-event.schema.json")})
    validate_authorization_document(auth, root=root)
    return auth


def validate_authorization(
    auth: dict[str, Any], preparation_dirs: Iterable[Path], *, root: Path = ROOT,
    now: str | None = None, enforce_time: bool = True,
) -> dict[str, Any]:
    validate_authorization_document(auth, root=root)
    if enforce_time:
        stamp = utc_datetime(now or utc_now())
        if not utc_datetime(auth["valid_from_utc"]) <= stamp < utc_datetime(auth["expires_at_utc"]):
            raise ValueError("authorization is not currently valid")
    scope, batch_id = _scope(preparation_dirs, root)
    if scope != auth["families"] or batch_id != auth["batch_id"]:
        raise ValueError("authorization preparation scope or batch mismatch")
    return {"families": scope, "batch_id": batch_id,
            "authorization_sha256": canonical_sha256(auth),
            "max_reservation_microusd": max_reservation_microusd(auth),
            "mode": "simulation_only", "budget_scope": "single_journal_simulation", "model_invoked": False}
