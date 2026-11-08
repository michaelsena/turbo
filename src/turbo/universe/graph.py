from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Iterable

EVENT_TYPES = {
    "create_market",
    "map",
    "split",
    "merge",
    "rename",
    "reparent",
    "exclude_source_record",
    "reject_candidate",
    "supersede_decision",
}

RELATIONSHIP_TYPES = {
    "equivalent_label_candidate",
    "broader_than_market",
    "narrower_than_market",
    "product_sold_by_market",
    "industry_containing_market",
    "task_performed_by_market",
    "partial_overlap",
    "residual_bucket",
    "duplicate_source_record",
    "non_market_product",
    "out_of_scope_for_canonicalization",
    "unresolved",
}

IDENTITY_DIMENSIONS = {
    "buyer",
    "job",
    "delivery",
    "workforce",
    "economics_risk",
    "acquisition_universe",
    "ambient_ai_workflow",
}

MARKET_VERSION_FIELDS = {
    "market_version_id",
    "market_id",
    "canonical_name",
    "definition",
    "boundary",
    "buyer",
    "job_to_be_done",
    "delivery_model",
    "workforce_model",
    "economics_risk",
    "acquisition_universe",
    "ambient_ai_workflow",
    "confidence_by_dimension",
}


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_event(event: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "event_id",
        "event_type",
        "decision",
        "recorded_at",
        "input_source_record_ids",
        "input_market_ids",
        "output_market_ids",
        "operating_identity",
        "supporting_record_ids",
        "counterevidence_record_ids",
        "alternatives_considered",
        "review",
        "supersedes",
    }
    missing = sorted(required - set(event))
    if missing:
        errors.append("missing fields: " + ", ".join(missing))
        return errors
    if event["event_type"] not in EVENT_TYPES:
        errors.append(f"unknown event_type: {event['event_type']}")
    if event["decision"] not in {"accepted", "rejected", "deferred"}:
        errors.append(f"unknown decision: {event['decision']}")
    try:
        _parse_timestamp(str(event["recorded_at"]))
    except ValueError:
        errors.append("recorded_at must be an ISO-8601 timestamp")
    relationship = event.get("relationship_type")
    if relationship is not None and relationship not in RELATIONSHIP_TYPES:
        errors.append(f"unknown relationship_type: {relationship}")
    identity = event["operating_identity"]
    missing_dimensions = sorted(IDENTITY_DIMENSIONS - set(identity))
    if missing_dimensions:
        errors.append("missing operating-identity dimensions: " + ", ".join(missing_dimensions))
    for dimension, result in identity.items():
        if dimension not in IDENTITY_DIMENSIONS:
            errors.append(f"unknown operating-identity dimension: {dimension}")
            continue
        confidence = result.get("confidence") if isinstance(result, dict) else None
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append(f"invalid confidence for {dimension}")
    review = event["review"]
    if event["decision"] == "accepted":
        proposer = review.get("proposer")
        independent = review.get("independent_reviewer")
        if not proposer or not independent:
            errors.append("accepted events require proposer and independent_reviewer")
        elif proposer == independent:
            errors.append("proposer and independent_reviewer must differ")
        if review.get("result") != "accepted":
            errors.append("accepted event review.result must be accepted")
    if event["event_type"] == "create_market":
        market_version = event.get("market_version")
        if not isinstance(market_version, dict):
            errors.append("create_market requires market_version")
        else:
            missing_market_fields = sorted(MARKET_VERSION_FIELDS - set(market_version))
            if missing_market_fields:
                errors.append("market_version missing fields: " + ", ".join(missing_market_fields))
            output_ids = event["output_market_ids"]
            if market_version.get("market_id") not in output_ids:
                errors.append("market_version market_id must appear in output_market_ids")
    return errors


def project_graph(
    events: Iterable[dict[str, Any]],
    *,
    as_of: str,
    source_hashes: dict[str, str] | None = None,
    config_hash: str = "",
    code_hash: str = "",
) -> dict[str, Any]:
    cutoff = _parse_timestamp(as_of)
    ordered = sorted(events, key=lambda event: (event["recorded_at"], event["event_id"]))
    event_ids = [event["event_id"] for event in ordered]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("duplicate reconciliation event IDs")
    for event in ordered:
        errors = validate_event(event)
        if errors:
            raise ValueError(f"invalid event {event['event_id']}: {'; '.join(errors)}")
    accepted = [
        event
        for event in ordered
        if event["decision"] == "accepted" and _parse_timestamp(event["recorded_at"]) <= cutoff
    ]
    superseded = {
        superseded_id
        for event in accepted
        for superseded_id in event.get("supersedes", [])
    }
    active = [event for event in accepted if event["event_id"] not in superseded]
    markets: dict[str, dict[str, Any]] = {}
    mappings: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    for event in active:
        if event["event_type"] in {"create_market", "rename", "reparent"}:
            market_version = event.get("market_version")
            if market_version:
                markets[market_version["market_id"]] = market_version
        elif event["event_type"] == "map":
            mappings.append(event)
        elif event["event_type"] == "exclude_source_record":
            exclusions.append(event)
        elif event["event_type"] in {"split", "merge"}:
            lineage.append(event)
    version_inputs = {
        "accepted_events": accepted,
        "as_of": as_of,
        "code_hash": code_hash,
        "config_hash": config_hash,
        "source_hashes": dict(sorted((source_hashes or {}).items())),
    }
    graph_version_id = "graph-" + hashlib.sha256(_canonical_bytes(version_inputs)).hexdigest()[:24]
    return {
        "schema_version": 1,
        "graph_version_id": graph_version_id,
        "as_of": as_of,
        "active_event_ids": [event["event_id"] for event in active],
        "superseded_event_ids": sorted(superseded),
        "markets": [markets[market_id] for market_id in sorted(markets)],
        "mappings": mappings,
        "exclusions": exclusions,
        "lineage": lineage,
    }
