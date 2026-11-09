from __future__ import annotations

import gzip
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from turbo.pipeline_paths import ROOT


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_gzip_json(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def _load_verified_run_artifact(
    run_dir: Path,
    receipt: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    expected = receipt["output_hashes"].get(name)
    if not isinstance(expected, str):
        raise ValueError(f"run receipt does not govern {name}")
    path = run_dir / name
    actual = _sha256_path(path)
    if actual != expected:
        raise ValueError(
            f"immutable run artifact hash mismatch for {name}: {actual} != {expected}"
        )
    return _load_gzip_json(path)


def _evidence_item(
    kind: str,
    content: dict[str, Any],
    *,
    subject_ids: Iterable[str] = (),
    source_record_ids: Iterable[str] = (),
    source_observations: Iterable[dict[str, Any]] = (),
    context_only: bool = False,
) -> dict[str, Any]:
    subjects = sorted(set(subject_ids))
    record_ids = sorted(set(source_record_ids))
    observations = sorted(
        (
            {
                "snapshot_id": observation["snapshot_id"],
                "locator": observation["locator"],
            }
            for observation in source_observations
        ),
        key=lambda item: (item["snapshot_id"], item["locator"]),
    )
    fingerprint = {
        "evidence_kind": kind,
        "subject_ids": subjects,
        "source_record_ids": record_ids,
        "source_observations": observations,
        "context_only": context_only,
        "content": content,
    }
    evidence_id = f"evidence:{kind}:{_sha256_bytes(_canonical_bytes(fingerprint))[:24]}"
    return {"evidence_id": evidence_id, **fingerprint}


def _identity_card(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "identity_id": identity["identity_id"],
        "identity_type": identity["identity_type"],
        "source_code": identity["source_code"],
        "labels": identity["labels"],
        "analysis_labels": identity["analysis_labels"],
        "label_conflict": identity["label_conflict"],
        "analysis_label_conflict": identity["analysis_label_conflict"],
        "source_record_count": len(identity["source_record_ids"]),
    }


def _source_record_card(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": record["record_id"],
        "snapshot_id": record["snapshot_id"],
        "locator": record["locator"],
        "record_kind": record["record_kind"],
        "raw_label": record["raw_label"],
        "normalized_label": record["normalized_label"],
        "raw_definition": record["raw_definition"],
        "source_indicator": record["source_indicator"],
        "normalized_identity_ids": record["normalized_identity_ids"],
        "parent_ids": record["parent_ids"],
        "hierarchy_path": record["hierarchy_path"],
    }


def _industry_edge_card(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "industry_identity_id": edge["industry_identity_id"],
        "product_identity_id": edge["product_identity_id"],
        "observed_in": edge["observed_in"],
        "source_observation_count": len(edge["source_observations"]),
        "source_snapshots": sorted(
            {item["snapshot_id"] for item in edge["source_observations"]}
        ),
    }


def _concordance_edge_card(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "collection_identity_id": edge["collection_identity_id"],
        "trilateral_identity_id": edge["trilateral_identity_id"],
        "observed_in": edge["observed_in"],
        "part_indicators": edge["part_indicators"],
        "source_observation_count": len(edge["source_observations"]),
    }


def _manual_definition_card(definition: dict[str, Any]) -> dict[str, Any]:
    return {
        key: definition[key]
        for key in (
            "identity_id",
            "naics_2022_code",
            "level",
            "disposition",
            "narrative_text",
            "illustrative_examples_text",
            "cross_references_text",
            "delegated_to_identity_id",
            "snapshot_id",
            "locator",
            "start_page",
            "start_y",
            "end_page",
            "end_y",
        )
    }


def _mapping_card(mapping: dict[str, Any]) -> dict[str, Any]:
    return {
        "normalized_identity_id": mapping["normalized_identity_id"],
        "status": mapping["status"],
        "reason": mapping["reason"],
        "ambiguous": mapping["ambiguous"],
        "top_similarity": mapping["top_similarity"],
        "candidates": [
            {
                "candidate_market_id": candidate["candidate_market_id"],
                "candidate_market_name": candidate["candidate_market_name"],
                "relationship_type": candidate["relationship_type"],
                "similarity": candidate["similarity"],
                "semantic_conflicts": candidate["semantic_conflicts"],
            }
            for candidate in mapping["candidates"]
        ],
        "interpretation_boundary": (
            "Deterministic label-retrieval worklist only; not an accepted mapping or "
            "operating-market conclusion."
        ),
    }


def _pack_hash(pack: dict[str, Any]) -> str:
    copy = json.loads(json.dumps(pack))
    copy["metadata"].pop("pack_sha256", None)
    return _sha256_bytes(_canonical_bytes(copy))


def build_boundary_pack(
    config_path: Path,
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Compile one frozen, bounded family pack from hash-verified run artifacts.

    This function never reparses source files and never makes market decisions. It
    selects an exact evidence surface from an immutable universe run so independent
    model calls can be compared against identical inputs.
    """

    config = _load_json(config_path)
    run_id = config["source_run_id"]
    run_dir = root / "data" / "runs" / run_id
    receipt_path = run_dir / "run-receipt.json"
    receipt = _load_json(receipt_path)
    if receipt.get("run_id") != run_id:
        raise ValueError("family config source_run_id does not match run receipt")

    reconciliation = _load_verified_run_artifact(
        run_dir, receipt, "multisource-reconciliation.json.gz"
    )
    relationships = _load_verified_run_artifact(
        run_dir, receipt, "identity-relationships.json.gz"
    )
    naics_evidence = _load_verified_run_artifact(
        run_dir, receipt, "naics-identity-evidence.json.gz"
    )
    hierarchy = _load_verified_run_artifact(
        run_dir, receipt, "napcs-hierarchy-evidence.json.gz"
    )

    identities = {
        item["identity_id"]: item for item in reconciliation["source_identities"]
    }
    records = {item["record_id"]: item for item in reconciliation["source_records"]}
    mappings = {
        item["normalized_identity_id"]: item for item in reconciliation["mappings"]
    }
    candidates = {
        item["candidate_market_id"]: item
        for item in reconciliation["candidate_markets"]
    }

    seed_ids = set(config["required_seed_identity_ids"])
    if len(seed_ids) != 1:
        raise ValueError("V1 boundary family requires exactly one seed identity")
    seed_id = next(iter(seed_ids))
    if seed_id not in identities:
        raise ValueError(f"unknown seed identity: {seed_id}")

    industry_edges = [
        edge
        for edge in relationships["industry_product_relationships"]
        if edge["industry_identity_id"] == seed_id
    ]
    product_ids = {edge["product_identity_id"] for edge in industry_edges}
    required_ids = sorted(seed_ids | product_ids)

    seed_record = records[identities[seed_id]["source_record_ids"][0]]
    naics_path = seed_record["hierarchy_path"]
    ancestor_ids = [identity_id for identity_id in naics_path if identity_id != seed_id]
    boundary_neighbor_ids = sorted(
        set(config["context_only_boundary_neighbor_identity_ids"])
    )
    context_identity_ids = sorted(set(ancestor_ids) | set(boundary_neighbor_ids))
    missing_context = set(context_identity_ids) - set(identities)
    if missing_context:
        raise ValueError(f"unknown context identities: {sorted(missing_context)}")

    collection_records = [
        record
        for record in records.values()
        if set(record["normalized_identity_ids"]) & product_ids
        and record["source"] == "napcs_collection_codes_2022"
        and record["record_kind"] in {"napcs_broad_line", "napcs_detail_line"}
    ]
    collection_record_identity_ids = {
        identity_id
        for record in collection_records
        for identity_id in record["normalized_identity_ids"]
        if identity_id in product_ids
    }
    relationship_only_ids = product_ids - collection_record_identity_ids

    concordance_edges = [
        edge
        for edge in relationships["napcs_concordance_relationships"]
        if edge["collection_identity_id"] in product_ids
    ]
    no_mapping_edges = [
        edge
        for edge in relationships["napcs_concordance_non_mappings"]
        if edge["collection_identity_id"] in product_ids
    ]
    concordance_collection_ids = {
        edge["collection_identity_id"] for edge in concordance_edges
    }
    no_mapping_collection_ids = {
        edge["collection_identity_id"] for edge in no_mapping_edges
    }
    absent_from_concordance_ids = sorted(
        product_ids - concordance_collection_ids - no_mapping_collection_ids
    )
    linked_trilateral_ids = {
        edge["trilateral_identity_id"] for edge in concordance_edges
    }

    hierarchy_nodes = {node["code"]: node for node in hierarchy["nodes"]}
    hierarchy_context_codes: set[str] = set()
    for identity_id in linked_trilateral_ids:
        code = identity_id.rsplit(":", 1)[-1]
        while code:
            node = hierarchy_nodes.get(code)
            if node is None:
                raise ValueError(f"missing hierarchy node for linked product {code}")
            hierarchy_context_codes.add(code)
            code = node["parent_code"] or ""
    hierarchy_context_nodes = [
        hierarchy_nodes[code] for code in sorted(hierarchy_context_codes)
    ]

    manual_definitions = [
        item for item in naics_evidence["manual_definitions"] if item["identity_id"] == seed_id
    ]
    manual_index_entries = [
        item for item in naics_evidence["manual_index_entries"] if item["identity_id"] == seed_id
    ]
    vintage_relationships = [
        item
        for item in naics_evidence["vintage_lineage_relationships"]
        if item["naics_2022_identity_id"] == seed_id
    ]

    selected_mappings = [mappings[identity_id] for identity_id in required_ids]
    retrieved_candidate_ids = sorted(
        {
            candidate["candidate_market_id"]
            for mapping in selected_mappings
            for candidate in mapping["candidates"]
        }
    )

    prevalence = Counter(
        edge["product_identity_id"]
        for edge in relationships["industry_product_relationships"]
        if edge["product_identity_id"] in product_ids
    )
    prevalence_values = sorted(prevalence.values())
    prevalence_rows = [
        {
            "product_identity_id": identity_id,
            "observed_industry_count": prevalence[identity_id],
            "interpretation_boundary": (
                "Count of distinct published industry-product relationships only; "
                "not revenue share, economic importance, exclusivity, or core-workflow proof."
            ),
        }
        for identity_id in sorted(product_ids)
    ]

    selected_record_ids = {seed_record["record_id"]}
    selected_record_ids.update(record["record_id"] for record in collection_records)
    for identity_id in context_identity_ids:
        selected_record_ids.update(identities[identity_id]["source_record_ids"])
    selected_record_ids_by_identity: dict[str, list[str]] = {}
    for record_id in selected_record_ids:
        for identity_id in records[record_id]["normalized_identity_ids"]:
            selected_record_ids_by_identity.setdefault(identity_id, []).append(record_id)

    evidence: list[dict[str, Any]] = []
    for identity_id in required_ids + context_identity_ids:
        identity = identities[identity_id]
        evidence.append(
            _evidence_item(
                "source-identity",
                _identity_card(identity),
                subject_ids=[identity_id],
                source_record_ids=selected_record_ids_by_identity.get(identity_id, []),
                context_only=identity_id in context_identity_ids,
            )
        )

    for record_id in sorted(selected_record_ids):
        record = records[record_id]
        evidence.append(
            _evidence_item(
                "source-record",
                _source_record_card(record),
                subject_ids=record["normalized_identity_ids"],
                source_record_ids=[record_id],
                source_observations=[record],
                context_only=not bool(set(record["normalized_identity_ids"]) & set(required_ids)),
            )
        )

    for edge in industry_edges:
        evidence.append(
            _evidence_item(
                "industry-product-relationship",
                _industry_edge_card(edge),
                subject_ids=[edge["industry_identity_id"], edge["product_identity_id"]],
                source_observations=edge["source_observations"],
            )
        )
    for edge in concordance_edges:
        evidence.append(
            _evidence_item(
                "collection-trilateral-relationship",
                _concordance_edge_card(edge),
                subject_ids=[edge["collection_identity_id"], edge["trilateral_identity_id"]],
                source_observations=edge["source_observations"],
            )
        )
    for edge in no_mapping_edges:
        evidence.append(
            _evidence_item(
                "collection-trilateral-no-mapping",
                {
                    "collection_identity_id": edge["collection_identity_id"],
                    "disposition": edge["disposition"],
                    "observed_in": edge["observed_in"],
                    "source_observation_count": len(edge["source_observations"]),
                },
                subject_ids=[edge["collection_identity_id"]],
                source_observations=edge["source_observations"],
            )
        )
    for node in hierarchy_context_nodes:
        identity_id = f"identity:napcs-trilateral:{node['code']}"
        evidence.append(
            _evidence_item(
                "trilateral-hierarchy-node",
                node,
                subject_ids=[identity_id],
                source_observations=[node],
                context_only=identity_id not in linked_trilateral_ids,
            )
        )
    for definition in manual_definitions:
        evidence.append(
            _evidence_item(
                "manual-definition",
                _manual_definition_card(definition),
                subject_ids=[definition["identity_id"]],
                source_observations=[definition],
            )
        )
    for entry in manual_index_entries:
        evidence.append(
            _evidence_item(
                "manual-index-entry",
                entry,
                subject_ids=[entry["identity_id"]],
                source_observations=[entry],
            )
        )
    for relationship in vintage_relationships:
        evidence.append(
            _evidence_item(
                "vintage-lineage-relationship",
                relationship,
                subject_ids=[relationship["naics_2022_identity_id"]],
                source_observations=relationship["source_observations"],
            )
        )
    for row in prevalence_rows:
        evidence.append(
            _evidence_item(
                "cross-industry-prevalence",
                row,
                subject_ids=[row["product_identity_id"]],
            )
        )
    for mapping in selected_mappings:
        evidence.append(
            _evidence_item(
                "reconciliation-candidate-retrieval",
                _mapping_card(mapping),
                subject_ids=[mapping["normalized_identity_id"]],
                source_record_ids=mapping["supporting_source_record_ids"],
            )
        )

    evidence.sort(key=lambda item: item["evidence_id"])
    evidence_ids = [item["evidence_id"] for item in evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("evidence catalog contains duplicate IDs")

    actual_counts = {
        "required_disposition_identities": len(required_ids),
        "industry_product_relationships": len(industry_edges),
        "industry_product_source_observations": sum(
            len(edge["source_observations"]) for edge in industry_edges
        ),
        "collection_workbook_rows": len(collection_records),
        "relationship_only_collection_identities": len(relationship_only_ids),
        "collection_trilateral_relationships": len(concordance_edges),
        "collection_trilateral_source_observations": sum(
            len(edge["source_observations"]) for edge in concordance_edges
        ),
        "linked_trilateral_products": len(linked_trilateral_ids),
        "linked_trilateral_context_nodes": len(hierarchy_context_nodes),
        "explicit_no_mapping_records": len(no_mapping_edges),
        "selected_products_absent_from_concordance": len(absent_from_concordance_ids),
        "manual_definition_records": len(manual_definitions),
        "manual_index_entries": len(manual_index_entries),
        "vintage_lineage_relationships": len(vintage_relationships),
        "existing_reconciliation_mappings": len(selected_mappings),
        "retrieved_prior_candidates": len(retrieved_candidate_ids),
        "prior_candidate_catalog": len(candidates),
    }
    if actual_counts != config["expected_counts"]:
        raise ValueError(
            "family pack count gate failed: "
            + json.dumps(
                {"expected": config["expected_counts"], "actual": actual_counts},
                sort_keys=True,
            )
        )

    pack: dict[str, Any] = {
        "schema_version": 1,
        "metadata": {
            "family_id": config["family_id"],
            "source_run_id": run_id,
            "as_of_utc": config["as_of_utc"],
            "run_receipt_sha256": _sha256_path(receipt_path),
            "source_artifact_hashes": receipt["output_hashes"],
            "pack_sha256": "",
        },
        "scope": {
            "purpose": "operating-market boundary construction only",
            "prohibited_uses": [
                "market attractiveness scoring",
                "Target Market filtering",
                "company discovery or evaluation",
                "external research or browsing",
            ],
            "required_disposition_identity_ids": required_ids,
            "context_only_identity_ids": context_identity_ids,
            "relationship_only_collection_identity_ids": sorted(relationship_only_ids),
            "selected_products_absent_from_concordance": absent_from_concordance_ids,
            "linked_trilateral_product_identity_ids": sorted(linked_trilateral_ids),
        },
        "summary": {
            "counts": actual_counts,
            "cross_industry_prevalence": {
                "minimum": min(prevalence_values),
                "median": statistics.median(prevalence_values),
                "maximum": max(prevalence_values),
                "interpretation_boundary": (
                    "Counts are relationship prevalence only, not revenue share, "
                    "importance, exclusivity, or core-workflow proof."
                ),
            },
        },
        "evidence_catalog": evidence,
        "retrieved_prior_candidate_details": [
            candidates[candidate_id] for candidate_id in retrieved_candidate_ids
        ],
        "prior_candidate_catalog": [
            {
                "candidate_market_id": candidate["candidate_market_id"],
                "name": candidate["name"],
                "status": candidate["status"],
            }
            for candidate in sorted(
                candidates.values(), key=lambda item: item["candidate_market_id"]
            )
        ],
    }
    pack["metadata"]["pack_sha256"] = _pack_hash(pack)
    return pack


def validate_boundary_pack(pack: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_hash = pack.get("metadata", {}).get("pack_sha256")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        errors.append("pack metadata has no valid pack_sha256")
    elif _pack_hash(pack) != expected_hash:
        errors.append("pack_sha256 does not match canonical pack content")

    evidence = pack.get("evidence_catalog")
    if not isinstance(evidence, list):
        return errors + ["evidence_catalog must be an array"]
    evidence_ids = [item.get("evidence_id") for item in evidence if isinstance(item, dict)]
    if len(evidence_ids) != len(evidence):
        errors.append("evidence_catalog entries must be objects with evidence IDs")
    elif len(evidence_ids) != len(set(evidence_ids)):
        errors.append("evidence_catalog contains duplicate evidence IDs")

    scope = pack.get("scope", {})
    required_ids = scope.get("required_disposition_identity_ids", [])
    context_ids = scope.get("context_only_identity_ids", [])
    if set(required_ids) & set(context_ids):
        errors.append("required and context-only identity sets overlap")
    if len(required_ids) != len(set(required_ids)):
        errors.append("required disposition identity IDs contain duplicates")
    return errors


def write_boundary_pack(pack: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(pack))
