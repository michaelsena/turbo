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
    "parent_market_id",
    "aliases",
    "explicit_exclusions",
    "source_record_ids",
    "mapping_event_ids",
    "candidate_market_ids",
    "evidence_by_dimension",
    "confidence_by_dimension",
}


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


def market_id_from_creation(event_id: str, ordinal: int = 0) -> str:
    digest = hashlib.sha256(f"{event_id}:{ordinal}".encode("utf-8")).hexdigest()[:24]
    return f"market:{digest}"


def market_version_id(event_id: str, market_id: str) -> str:
    digest = hashlib.sha256(f"{event_id}:{market_id}".encode("utf-8")).hexdigest()[:24]
    return f"market-version:{digest}"


def _validate_market_version(
    version: object,
    *,
    event_id: str,
    expected_market_id: str,
) -> list[str]:
    if not isinstance(version, dict):
        return ["market version must be an object"]
    errors: list[str] = []
    missing = sorted(MARKET_VERSION_FIELDS - set(version))
    if missing:
        errors.append("market version missing fields: " + ", ".join(missing))
        return errors
    if version["market_id"] != expected_market_id:
        errors.append("market version market_id does not match event output")
    expected_version_id = market_version_id(event_id, expected_market_id)
    if version["market_version_id"] != expected_version_id:
        errors.append(f"market_version_id must equal {expected_version_id}")
    for field in (
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
    ):
        if not isinstance(version[field], str) or not version[field].strip():
            errors.append(f"market version {field} must be a non-empty string")
    confidence = version["confidence_by_dimension"]
    if not isinstance(confidence, dict) or set(confidence) != IDENTITY_DIMENSIONS:
        errors.append("confidence_by_dimension must contain exactly the seven identity dimensions")
    elif any(
        not isinstance(value, (int, float)) or not 0 <= value <= 1
        for value in confidence.values()
    ):
        errors.append("confidence_by_dimension values must be between 0 and 1")
    evidence = version["evidence_by_dimension"]
    if not isinstance(evidence, dict) or set(evidence) != IDENTITY_DIMENSIONS:
        errors.append("evidence_by_dimension must contain exactly the seven identity dimensions")
    elif any(
        label not in {"fact", "inference", "assumption", "unknown"}
        for label in evidence.values()
    ):
        errors.append("evidence_by_dimension contains an invalid evidence label")
    if version["parent_market_id"] is not None and not isinstance(
        version["parent_market_id"], str
    ):
        errors.append("parent_market_id must be a string or null")
    for field in (
        "aliases",
        "explicit_exclusions",
        "source_record_ids",
        "mapping_event_ids",
        "candidate_market_ids",
    ):
        if not isinstance(version[field], list) or any(
            not isinstance(item, str) for item in version[field]
        ):
            errors.append(f"market version {field} must be an array of strings")
    return errors


def validate_event(event: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "event_id",
        "event_type",
        "decision",
        "recorded_at",
        "input_source_record_ids",
        "input_market_ids",
        "input_candidate_market_ids",
        "output_market_ids",
        "operating_identity",
        "supporting_record_ids",
        "counterevidence_record_ids",
        "alternatives_considered",
        "review",
        "supersedes",
        "supersedes_market_version_ids",
    }
    missing = sorted(required - set(event))
    if missing:
        return ["missing fields: " + ", ".join(missing)]
    event_id = str(event["event_id"])
    event_type = event["event_type"]
    if event_type not in EVENT_TYPES:
        errors.append(f"unknown event_type: {event_type}")
    if event["decision"] not in {"accepted", "rejected", "deferred"}:
        errors.append(f"unknown decision: {event['decision']}")
    try:
        _parse_timestamp(str(event["recorded_at"]))
    except ValueError as error:
        errors.append(f"recorded_at must be timezone-aware ISO-8601: {error}")
    list_fields = (
        "input_source_record_ids",
        "input_market_ids",
        "input_candidate_market_ids",
        "output_market_ids",
        "supporting_record_ids",
        "counterevidence_record_ids",
        "alternatives_considered",
        "supersedes",
        "supersedes_market_version_ids",
    )
    for field in list_fields:
        if not isinstance(event[field], list):
            errors.append(f"{field} must be an array")
    if errors and any(not isinstance(event[field], list) for field in list_fields):
        return errors
    if event_id in event["supersedes"]:
        errors.append("event cannot supersede itself")
    for field in (
        "input_source_record_ids",
        "input_market_ids",
        "input_candidate_market_ids",
        "output_market_ids",
        "supporting_record_ids",
        "counterevidence_record_ids",
        "supersedes",
        "supersedes_market_version_ids",
    ):
        values = event[field]
        if len(values) != len(set(values)):
            errors.append(f"{field} contains duplicates")
        if any(not isinstance(value, str) or not value for value in values):
            errors.append(f"{field} must contain non-empty strings")
    relationship = event.get("relationship_type")
    if relationship is not None and relationship not in RELATIONSHIP_TYPES:
        errors.append(f"unknown relationship_type: {relationship}")
    identity = event["operating_identity"]
    if not isinstance(identity, dict):
        errors.append("operating_identity must be an object")
    else:
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
    if not isinstance(review, dict):
        errors.append("review must be an object")
    else:
        proposer = review.get("proposer")
        independent = review.get("independent_reviewer")
        if not isinstance(proposer, str) or not proposer:
            errors.append("review.proposer must be a non-empty string")
        if not isinstance(independent, str) or not independent:
            errors.append("review.independent_reviewer must be a non-empty string")
        elif proposer == independent:
            errors.append("proposer and independent_reviewer must differ")
        if review.get("result") not in {"accepted", "rejected", "changes_requested"}:
            errors.append("review.result is invalid")
        if event["decision"] == "accepted" and review.get("result") != "accepted":
            errors.append("accepted event review.result must be accepted")

    source_ids = event["input_source_record_ids"]
    input_ids = event["input_market_ids"]
    candidate_ids = event["input_candidate_market_ids"]
    output_ids = event["output_market_ids"]
    if event_type not in {"rename", "reparent"} and event[
        "supersedes_market_version_ids"
    ]:
        errors.append(
            "only rename or reparent may supersede a market version"
        )
    if event_type == "map":
        if not source_ids:
            errors.append("map requires at least one input source record")
        if len(output_ids) != 1:
            errors.append("map requires exactly one output market")
        if input_ids:
            errors.append("map does not accept input markets")
        if relationship is None:
            errors.append("map requires relationship_type")
    elif event_type == "create_market":
        if event["supersedes"]:
            errors.append("create_market cannot supersede another event")
        if input_ids or len(output_ids) != 1:
            errors.append("create_market requires no input markets and exactly one output market")
        elif output_ids[0] != market_id_from_creation(event_id):
            errors.append("create_market output must use the opaque event-derived market ID")
        else:
            errors.extend(
                _validate_market_version(
                    event.get("market_version"),
                    event_id=event_id,
                    expected_market_id=output_ids[0],
                )
            )
    elif event_type == "split":
        if len(input_ids) != 1 or len(output_ids) < 2:
            errors.append("split requires exactly one input market and at least two outputs")
        expected = [market_id_from_creation(event_id, index) for index in range(len(output_ids))]
        if output_ids != expected:
            errors.append("split outputs must use ordered opaque event-derived market IDs")
        versions = event.get("market_versions")
        if not isinstance(versions, list) or len(versions) != len(output_ids):
            errors.append("split requires one market version per output")
        else:
            for version, market_id in zip(versions, output_ids):
                errors.extend(
                    _validate_market_version(version, event_id=event_id, expected_market_id=market_id)
                )
    elif event_type == "merge":
        if len(input_ids) < 2 or len(output_ids) != 1:
            errors.append("merge requires at least two input markets and exactly one output")
        elif output_ids[0] != market_id_from_creation(event_id):
            errors.append("merge output must use the opaque event-derived market ID")
        else:
            errors.extend(
                _validate_market_version(
                    event.get("market_version"),
                    event_id=event_id,
                    expected_market_id=output_ids[0],
                )
            )
    elif event_type in {"rename", "reparent"}:
        if len(input_ids) != 1 or output_ids != input_ids:
            errors.append(f"{event_type} must preserve exactly one market ID")
        elif len(event["supersedes_market_version_ids"]) != 1:
            errors.append(f"{event_type} must supersede exactly one market version")
        else:
            errors.extend(
                _validate_market_version(
                    event.get("market_version"),
                    event_id=event_id,
                    expected_market_id=output_ids[0],
                )
            )
    elif event_type == "exclude_source_record":
        if not source_ids:
            errors.append("exclude_source_record requires at least one source record")
        if output_ids:
            errors.append("exclude_source_record cannot create market outputs")
    elif event_type == "reject_candidate":
        if not candidate_ids:
            errors.append("reject_candidate requires at least one candidate-market input")
        if output_ids:
            errors.append("reject_candidate cannot create market outputs")
    elif event_type == "supersede_decision":
        if not event["supersedes"]:
            errors.append("supersede_decision requires at least one superseded event")
        if output_ids:
            errors.append("supersede_decision cannot create market outputs")
    return errors


def project_graph(
    events: Iterable[dict[str, Any]],
    *,
    as_of: str,
    known_source_record_ids: set[str],
    known_candidate_market_ids: set[str] | None = None,
    source_hashes: dict[str, str] | None = None,
    config_hash: str = "",
    code_hash: str = "",
) -> dict[str, Any]:
    cutoff = _parse_timestamp(as_of)
    known_candidates = known_candidate_market_ids or set()
    timestamped: list[tuple[datetime, dict[str, Any]]] = []
    for event in events:
        try:
            recorded_at = _parse_timestamp(str(event["recorded_at"]))
        except (KeyError, ValueError) as error:
            raise ValueError(f"invalid event timestamp: {error}") from error
        if recorded_at <= cutoff:
            timestamped.append((recorded_at, event))
    ordered = [event for _, event in sorted(timestamped, key=lambda item: (item[0], item[1]["event_id"]))]
    event_ids = [event["event_id"] for event in ordered]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("duplicate reconciliation event IDs")
    by_id = {event["event_id"]: event for event in ordered}
    event_times = {event["event_id"]: _parse_timestamp(event["recorded_at"]) for event in ordered}
    for event in ordered:
        errors = validate_event(event)
        if errors:
            raise ValueError(f"invalid event {event['event_id']}: {'; '.join(errors)}")
        for superseded_id in event["supersedes"]:
            if superseded_id not in by_id:
                raise ValueError(f"event {event['event_id']} supersedes missing or future event {superseded_id}")
            if event_times[superseded_id] >= event_times[event["event_id"]]:
                raise ValueError(f"event {event['event_id']} must supersede an earlier event")
            if (
                event["event_type"] != "supersede_decision"
                and by_id[superseded_id]["event_type"] != event["event_type"]
            ):
                raise ValueError(
                    f"event {event['event_id']} may only supersede the same event type "
                    "unless it is supersede_decision"
                )
        missing_sources = set(event["input_source_record_ids"]) - known_source_record_ids
        if missing_sources:
            raise ValueError(
                f"event {event['event_id']} references unknown source records: {sorted(missing_sources)}"
            )
        missing_candidates = set(event["input_candidate_market_ids"]) - known_candidates
        if missing_candidates:
            raise ValueError(
                f"event {event['event_id']} references unknown candidate markets: "
                f"{sorted(missing_candidates)}"
            )
    accepted = [event for event in ordered if event["decision"] == "accepted"]
    active_ids: set[str] = set()
    suppressed_ids: set[str] = set()
    for event in reversed(accepted):
        if event["event_id"] in suppressed_ids:
            continue
        active_ids.add(event["event_id"])
        suppressed_ids.update(event["supersedes"])
    superseded = {event["event_id"] for event in accepted} - active_ids
    active = [event for event in accepted if event["event_id"] in active_ids]

    markets: dict[str, dict[str, Any]] = {}
    definition_events: dict[str, str] = {}
    current_version_ids: dict[str, str] = {}
    version_ids: set[str] = set()
    mappings: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    retired_market_ids: set[str] = set()

    def install(version: dict[str, Any], event: dict[str, Any], *, replace: bool = False) -> None:
        market_id = version["market_id"]
        version_id = version["market_version_id"]
        if version_id in version_ids:
            raise ValueError(f"duplicate market_version_id: {version_id}")
        if market_id in markets and not replace:
            raise ValueError(f"duplicate active market definition: {market_id}")
        if replace and current_version_ids.get(market_id) not in event[
            "supersedes_market_version_ids"
        ]:
            raise ValueError(
                f"event {event['event_id']} must supersede active market version "
                f"{current_version_ids.get(market_id)}"
            )
        version_ids.add(version_id)
        markets[market_id] = version
        definition_events[market_id] = event["event_id"]
        current_version_ids[market_id] = version_id

    for event in active:
        event_type = event["event_type"]
        if event_type == "create_market":
            install(event["market_version"], event)
        elif event_type in {"rename", "reparent"}:
            market_id = event["output_market_ids"][0]
            if market_id not in markets or market_id in retired_market_ids:
                raise ValueError(f"{event_type} references unknown market or retired market: {market_id}")
            install(event["market_version"], event, replace=True)
        elif event_type == "split":
            source_market = event["input_market_ids"][0]
            if source_market not in markets or source_market in retired_market_ids:
                raise ValueError(f"split references unknown market or retired market: {source_market}")
            for version in event["market_versions"]:
                install(version, event)
            retired_market_ids.add(source_market)
            lineage.append(event)
        elif event_type == "merge":
            missing_markets = set(event["input_market_ids"]) - (
                set(markets) - retired_market_ids
            )
            if missing_markets:
                raise ValueError(
                    f"merge references unknown markets or retired markets: {sorted(missing_markets)}"
                )
            install(event["market_version"], event)
            retired_market_ids.update(event["input_market_ids"])
            lineage.append(event)
        elif event_type == "map":
            market_id = event["output_market_ids"][0]
            if market_id not in markets or market_id in retired_market_ids:
                raise ValueError(f"map references unknown market or retired market: {market_id}")
            mappings.append(event)
        elif event_type == "exclude_source_record":
            exclusions.append(event)

    effective_market_ids = set(markets) - retired_market_ids
    effective_mappings = [
        mapping
        for mapping in mappings
        if mapping["output_market_ids"][0] in effective_market_ids
    ]
    retired_mappings = [
        mapping
        for mapping in mappings
        if mapping["output_market_ids"][0] in retired_market_ids
    ]
    for market_id in sorted(effective_market_ids):
        version = markets[market_id]
        missing_sources = set(version["source_record_ids"]) - known_source_record_ids
        if missing_sources:
            raise ValueError(
                f"market {market_id} references unknown source records: {sorted(missing_sources)}"
            )
        missing_candidates = set(version["candidate_market_ids"]) - known_candidates
        if missing_candidates:
            raise ValueError(
                f"market {market_id} references unknown candidate markets: "
                f"{sorted(missing_candidates)}"
            )
        for mapping_id in version["mapping_event_ids"]:
            mapping = by_id.get(mapping_id)
            if (
                mapping is None
                or mapping["event_type"] != "map"
                or mapping_id not in active_ids
                or mapping["decision"] != "accepted"
                or event_times[mapping_id]
                >= event_times[definition_events[market_id]]
                or mapping["output_market_ids"] != [market_id]
                or not set(mapping["input_source_record_ids"]).issubset(
                    set(version["source_record_ids"])
                )
            ):
                raise ValueError(
                    f"market {market_id} references an invalid mapping event: {mapping_id}"
                )
        parent_id = version["parent_market_id"]
        if parent_id is not None and parent_id not in effective_market_ids:
            raise ValueError(f"market {market_id} references unknown or retired parent: {parent_id}")
        if parent_id == market_id:
            raise ValueError(f"market {market_id} cannot be its own parent")

    for market_id in sorted(effective_market_ids):
        visited: set[str] = set()
        current: str | None = market_id
        while current is not None:
            if current in visited:
                raise ValueError(f"market parent cycle detected at {current}")
            visited.add(current)
            current = markets[current]["parent_market_id"]

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
        "active_event_ids": [event["event_id"] for event in accepted if event["event_id"] in active_ids],
        "superseded_event_ids": sorted(superseded),
        "markets": [
            markets[market_id]
            for market_id in sorted(effective_market_ids)
        ],
        "retired_market_ids": sorted(retired_market_ids),
        "mappings": effective_mappings,
        "retired_mappings": retired_mappings,
        "exclusions": exclusions,
        "lineage": lineage,
    }
