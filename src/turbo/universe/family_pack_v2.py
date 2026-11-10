from __future__ import annotations

import gzip
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT
from turbo.system_context import _source_context
from turbo.universe.family_supplement import binding_for, load_supplement


DEFAULT_LIMITS = {
    "max_required_identities": 96,
    "max_context_identities": 1_000,
    "max_required_candidates": 256,
    "max_context_edges": 10_000,
    "max_evidence_items": 20_000,
    "max_pack_bytes": 12_000_000,
}
PROHIBITED_ACTIONS = [
    "model invocation",
    "market graph mutation",
    "target-universe filtering",
    "market evaluation or scoring",
    "company discovery or evaluation",
    "silent evidence truncation",
]


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _gzip_object(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema(name: str, root: Path) -> dict[str, Any]:
    return _object(root / "schemas" / name)


def _schema_errors(value: dict[str, Any], name: str, root: Path) -> list[str]:
    validator = Draft202012Validator(_schema(name, root))
    return sorted(
        f"schema:{'/'.join(map(str, error.absolute_path)) or '<root>'}:{error.message}"
        for error in validator.iter_errors(value)
    )


def _verified_schedule(
    *, root: Path, pointer_path: Path | None = None
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    pointer = _object(pointer_path or root / "data/generated/latest-family-schedule.json")
    if pointer.get("status") != "complete_deterministic_family_plan":
        raise ValueError("schedule pointer is not complete")
    schedule_dir = root / pointer["schedule_path"]
    if schedule_dir.name != pointer["partition_id"]:
        raise ValueError("schedule pointer path does not match partition_id")
    receipt = _object(schedule_dir / "schedule-receipt.json")
    if canonical_sha256(receipt) != pointer["receipt_sha256"]:
        raise ValueError("schedule pointer receipt hash mismatch")
    for field in ("partition_id", "source_run_id"):
        if receipt.get(field) != pointer.get(field):
            raise ValueError(f"schedule pointer/receipt {field} mismatch")
    if receipt.get("model_invoked") is not False:
        raise ValueError("schedule receipt must state model_invoked=false")
    if receipt.get("status") != "complete_deterministic_family_plan":
        raise ValueError("schedule receipt is not complete")
    if receipt.get("counts") != pointer.get("counts"):
        raise ValueError("schedule pointer/receipt counts mismatch")
    expected_artifacts = {
        "coverage-ledger.json.gz",
        "context-edge-ledger.json.gz",
        "candidate-collision-ledger.json.gz",
        "family-manifest.json.gz",
        "batch-manifest.json",
    }
    if set(receipt.get("output_hashes", {})) != expected_artifacts:
        raise ValueError("schedule receipt artifact set mismatch")
    artifacts: dict[str, dict[str, Any]] = {}
    for name, expected in sorted(receipt["output_hashes"].items()):
        path = schedule_dir / name
        if _sha256_path(path) != expected:
            raise ValueError(f"schedule artifact hash mismatch: {name}")
        artifacts[name] = _gzip_object(path) if name.endswith(".gz") else _object(path)
        for field in ("partition_id", "source_run_id"):
            if artifacts[name].get(field) != receipt[field]:
                raise ValueError(f"schedule artifact {name} {field} mismatch")
    return pointer, receipt, artifacts


def _verified_graph(
    *, root: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    pointer = _object(root / "data/generated/latest-graph.json")
    release_dir = root / pointer["release_path"]
    if release_dir.name != pointer.get("release_id"):
        raise ValueError("graph pointer release path does not match release_id")
    receipt = _object(release_dir / "graph-receipt.json")
    projection = _object(release_dir / "projection.json")
    if canonical_sha256(receipt) != pointer["receipt_sha256"]:
        raise ValueError("graph receipt hash mismatch")
    if canonical_sha256(projection) != pointer["projection_sha256"]:
        raise ValueError("graph projection hash mismatch")
    for field in ("release_id", "graph_version_id", "source_universe_run_id"):
        if receipt.get(field) != pointer.get(field):
            raise ValueError(f"graph pointer/receipt {field} mismatch")
    if receipt.get("projection_sha256") != pointer["projection_sha256"]:
        raise ValueError("graph receipt does not bind pointer projection hash")
    if projection.get("graph_version_id") != receipt["graph_version_id"]:
        raise ValueError("graph receipt/projection graph_version_id mismatch")
    if receipt.get("status") != "published_cumulative_canonical_graph":
        raise ValueError("graph receipt is not a published cumulative graph")
    if receipt.get("model_invoked") is not False:
        raise ValueError("graph receipt must state model_invoked=false")
    projection_counts = {
        "activations": len(receipt.get("activation_bindings", [])),
        "active_events": len(projection.get("active_event_ids", [])),
        "canonical_markets": len(projection.get("markets", [])),
        "mappings": len(projection.get("mappings", [])),
        "retired_markets": len(projection.get("retired_market_ids", [])),
    }
    if receipt.get("counts") != projection_counts:
        raise ValueError("graph receipt counts do not match projection")
    return pointer, receipt, projection


def _load_run_artifact(
    root: Path,
    run_id: str,
    receipt: dict[str, Any],
    schedule_source_hashes: dict[str, str],
    name: str,
) -> dict[str, Any]:
    path = root / "data/runs" / run_id / name
    expected = receipt.get("output_hashes", {}).get(name)
    schedule_expected = schedule_source_hashes.get(name)
    if not isinstance(schedule_expected, str):
        raise ValueError(f"schedule receipt does not govern source artifact: {name}")
    if expected != schedule_expected:
        raise ValueError(f"source run/schedule hash disagreement: {name}")
    if not isinstance(expected, str) or _sha256_path(path) != expected:
        raise ValueError(f"source run artifact hash mismatch: {name}")
    return _gzip_object(path)


def _family_edges(
    ledger: dict[str, Any], family_id: str, selected_ids: set[str]
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    def observations(edge: dict[str, Any]) -> list[dict[str, str]]:
        return sorted(
            {
                (item["snapshot_id"], item["locator"])
                for item in edge["source_observations"]
            }
        )

    def observation_cards(edge: dict[str, Any]) -> list[dict[str, str]]:
        return [
            {"snapshot_id": snapshot_id, "locator": locator}
            for snapshot_id, locator in observations(edge)
        ]

    for edge in ledger["industry_product_relationships"]:
        endpoints = {edge["industry_identity_id"], edge["product_identity_id"]}
        if endpoints & selected_ids and (
            family_id in edge["product_appearance_family_ids"]
            or edge["industry_identity_id"] in selected_ids
        ):
            edges.append({
                "relationship_id": edge["relationship_id"],
                "relationship_type": edge["relationship_type"],
                "industry_identity_id": edge["industry_identity_id"],
                "product_identity_id": edge["product_identity_id"],
                "observed_in": edge["observed_in"],
                "source_observations": observation_cards(edge),
            })
    for edge in ledger["napcs_concordance_relationships"]:
        endpoints = {edge["collection_identity_id"], edge["trilateral_identity_id"]}
        if endpoints & selected_ids and (
            family_id in edge["collection_appearance_family_ids"]
            or family_id in edge["trilateral_appearance_family_ids"]
        ):
            edges.append({
                "relationship_id": edge["relationship_id"],
                "relationship_type": edge["relationship_type"],
                "collection_identity_id": edge["collection_identity_id"],
                "trilateral_identity_id": edge["trilateral_identity_id"],
                "observed_in": edge["observed_in"],
                "part_indicators": edge["part_indicators"],
                "source_observations": observation_cards(edge),
            })
    for edge in ledger["napcs_concordance_non_mappings"]:
        if edge["collection_identity_id"] in selected_ids and family_id in edge["appearance_family_ids"]:
            edges.append({
                "relationship_id": edge["relationship_id"],
                "relationship_type": edge["relationship_type"],
                "collection_identity_id": edge["collection_identity_id"],
                "disposition": edge["disposition"],
                "observed_in": edge["observed_in"],
                "source_observations": observation_cards(edge),
            })
    return sorted(edges, key=lambda item: item["relationship_id"])


def _source_binding(root: Path, run_id: str) -> dict[str, Any]:
    source = _source_context(root)
    if source["run_id"] != run_id:
        raise ValueError("family schedule and verified source run disagree")
    receipt = _object(root / source["immutable_run_path"] / "run-receipt.json")
    return {"run_id": run_id, "receipt_sha256": canonical_sha256(receipt),
            "artifact_hashes": source["output_hashes"]}


def _implementation_hashes(root: Path) -> dict[str, str]:
    paths = sorted((root / "src/turbo").rglob("*.py")) + [
        root / "schemas/family-config-v2.schema.json",
        root / "schemas/family-evidence-pack-v2.schema.json",
    ]
    return {str(path.relative_to(root)): _sha256_path(path) for path in paths}


def generate_family_config_v2(
    family_id: str,
    *,
    root: Path = ROOT,
    pointer_path: Path | None = None,
    limits: dict[str, int] | None = None,
    supplemental_manifest: Path | None = None,
) -> dict[str, Any]:
    pointer, receipt, artifacts = _verified_schedule(root=root, pointer_path=pointer_path)
    graph, _, _ = _verified_graph(root=root)
    if graph["source_universe_run_id"] != pointer["source_run_id"]:
        raise ValueError("schedule and cumulative graph source runs disagree")
    families = {
        item["family_id"]: item
        for item in artifacts["family-manifest.json.gz"]["families"]
    }
    family = families.get(family_id)
    if family is None:
        raise ValueError(f"family is absent from corrected schedule: {family_id}")
    if not family["schedulable"] or family["status"] != "ready_for_boundary_review":
        raise ValueError(f"family is not schedulable: {family_id}")
    selected_ids = set(family["required_disposition_identity_ids"]) | set(
        family["context_only_identity_ids"]
    )
    edges = _family_edges(
        artifacts["context-edge-ledger.json.gz"], family_id, selected_ids
    )
    resolved_limits = {**DEFAULT_LIMITS, **(limits or {})}
    config = {
        "schema_version": 2,
        "method_version": "schedule-driven-family-v2",
        "source_binding": _source_binding(root, pointer["source_run_id"]),
        "implementation_hashes": _implementation_hashes(root),
        "family_id": family_id,
        "family_kind": family["family_kind"],
        "status": "prepared_no_model_call",
        "schedule_binding": {
            "partition_id": pointer["partition_id"],
            "source_run_id": pointer["source_run_id"],
            "receipt_sha256": pointer["receipt_sha256"],
            "artifact_hashes": receipt["output_hashes"],
        },
        "graph_binding": {
            "release_id": graph["release_id"],
            "graph_version_id": graph["graph_version_id"],
            "source_universe_run_id": graph["source_universe_run_id"],
            "receipt_sha256": graph["receipt_sha256"],
            "projection_sha256": graph["projection_sha256"],
        },
        "scope": {
            "required_disposition_identity_ids": family["required_disposition_identity_ids"],
            "context_shards": family["context_shards"],
            "required_prior_candidate_ids": family["required_prior_candidate_ids"],
        },
        "expected_counts": {
            **family["counts"],
            "context_edges": len(edges),
        },
        "limits": resolved_limits,
        "prohibited_actions": PROHIBITED_ACTIONS,
        "model_invoked": False,
    }
    if supplemental_manifest is not None:
        config["supplemental_evidence"] = binding_for(root, supplemental_manifest)
        load_supplement(root, config["supplemental_evidence"], family_id=family_id,
                        source_run_id=pointer["source_run_id"],
                        subject_ids=selected_ids | set(family["required_prior_candidate_ids"]))
        config["implementation_hashes"]["schemas/family-supplement-v1.schema.json"] = _sha256_path(
            root / "schemas/family-supplement-v1.schema.json")
    errors = _schema_errors(config, "family-config-v2.schema.json", root)
    if errors:
        raise ValueError("invalid generated family config V2: " + "; ".join(errors))
    _enforce_count_limits(config)
    return config


def _enforce_count_limits(config: dict[str, Any]) -> None:
    counts, limits = config["expected_counts"], config["limits"]
    pairs = (
        ("required_identities", "max_required_identities"),
        ("context_identities", "max_context_identities"),
        ("required_candidates", "max_required_candidates"),
        ("context_edges", "max_context_edges"),
    )
    for count_key, limit_key in pairs:
        if counts[count_key] > limits[limit_key]:
            raise ValueError(
                f"family preparation count limit exceeded: {count_key}="
                f"{counts[count_key]} > {limits[limit_key]}"
            )


def compile_family_evidence_pack_v2(
    config: dict[str, Any], *, root: Path = ROOT
) -> dict[str, Any]:
    pack = _assemble_family_evidence_pack_v2(config, root=root)
    validation_errors = _validate_family_evidence_pack_v2(
        pack, config, root=root, expected_pack=pack
    )
    if validation_errors:
        raise ValueError("invalid family evidence pack V2: " + "; ".join(validation_errors))
    return pack


def _assemble_family_evidence_pack_v2(
    config: dict[str, Any], *, root: Path = ROOT
) -> dict[str, Any]:
    errors = _schema_errors(config, "family-config-v2.schema.json", root)
    if errors:
        raise ValueError("invalid family config V2: " + "; ".join(errors))
    _enforce_count_limits(config)
    pointer, receipt, artifacts = _verified_schedule(root=root)
    graph_pointer, _, graph_projection = _verified_graph(root=root)
    if config["schedule_binding"] != {
        "partition_id": pointer["partition_id"],
        "source_run_id": pointer["source_run_id"],
        "receipt_sha256": pointer["receipt_sha256"],
        "artifact_hashes": receipt["output_hashes"],
    }:
        raise ValueError("family config schedule binding is stale or tampered")
    if config["graph_binding"] != {
        "release_id": graph_pointer["release_id"],
        "graph_version_id": graph_pointer["graph_version_id"],
        "source_universe_run_id": graph_pointer["source_universe_run_id"],
        "receipt_sha256": graph_pointer["receipt_sha256"],
        "projection_sha256": graph_pointer["projection_sha256"],
    }:
        raise ValueError("family config graph binding is stale or tampered")

    regenerated = generate_family_config_v2(
        config["family_id"], root=root, limits=config["limits"],
        supplemental_manifest=(Path(config["supplemental_evidence"]["manifest_path"])
                               if "supplemental_evidence" in config else None)
    )
    if regenerated != config:
        raise ValueError("family config does not match its exact schedule entry")
    run_id = pointer["source_run_id"]
    run_receipt = _object(root / "data/runs" / run_id / "run-receipt.json")
    if run_receipt.get("run_id") != run_id:
        raise ValueError("source run receipt run_id mismatch")
    reconciliation = _load_run_artifact(
        root,
        run_id,
        run_receipt,
        receipt["source_hashes"],
        "multisource-reconciliation.json.gz",
    )
    naics_evidence = _load_run_artifact(
        root, run_id, run_receipt, config["source_binding"]["artifact_hashes"],
        "naics-identity-evidence.json.gz",
    )
    identities = {item["identity_id"]: item for item in reconciliation["source_identities"]}
    records = {item["record_id"]: item for item in reconciliation["source_records"]}
    mappings = {item["normalized_identity_id"]: item for item in reconciliation["mappings"]}
    candidates = {item["candidate_market_id"]: item for item in reconciliation["candidate_markets"]}
    assignments = {
        item["identity_id"]: item
        for item in artifacts["coverage-ledger.json.gz"]["assignments"]
    }
    candidate_ledger = {
        item["candidate_market_id"]: item
        for item in artifacts["candidate-collision-ledger.json.gz"]["candidates"]
    }
    required_ids = config["scope"]["required_disposition_identity_ids"]
    context_ids = [
        identity_id
        for shard in config["scope"]["context_shards"]
        for identity_id in shard["identity_ids"]
    ]
    required_naics = {identity_id for identity_id in required_ids
                      if identity_id.startswith("identity:naics:")}
    manual_definitions = [item for item in naics_evidence["manual_definitions"]
                          if item["identity_id"] in required_naics]
    if {item["identity_id"] for item in manual_definitions} != required_naics:
        raise ValueError("required NAICS identity missing official Manual definition")
    manual_index_entries = [item for item in naics_evidence["manual_index_entries"]
                            if item["identity_id"] in required_naics]
    # Two official codes have no index entry; absence remains an explicit source fact.
    manual_index_missing_identity_ids = sorted(required_naics - {
        item["identity_id"] for item in manual_index_entries})
    selected_ids = required_ids + context_ids
    required_candidate_ids = config["scope"]["required_prior_candidate_ids"]
    context_candidate_ids = sorted({
        candidate["candidate_market_id"]
        for identity_id in required_ids
        for candidate in mappings[identity_id]["candidates"]
    } - set(required_candidate_ids))
    all_candidate_ids = required_candidate_ids + context_candidate_ids
    # Context is orientation, not a second primary research obligation. Keep its
    # labels and exact relationship edges, but include full source/mapping cards
    # only for required identities.
    record_ids = sorted({
        record_id
        for identity_id in required_ids
        for record_id in identities[identity_id]["source_record_ids"]
    } | {
        record_id
        for candidate_id in all_candidate_ids
        for record_id in candidates[candidate_id]["source_record_ids"]
    })
    identity_cards = [
        {
            "identity_id": identity_id,
            "identity_type": identities[identity_id]["identity_type"],
            "source_code": identities[identity_id]["source_code"],
            "labels": identities[identity_id]["labels"],
            "analysis_labels": identities[identity_id]["analysis_labels"],
            "source_record_ids": identities[identity_id]["source_record_ids"],
            "assignment_role": assignments[identity_id]["assignment_role"],
            "owner_family_id": assignments[identity_id]["owner_family_id"],
            "reason_code": assignments[identity_id]["reason_code"],
        }
        for identity_id in selected_ids
    ]
    source_record_cards = [
        {key: records[record_id][key] for key in (
            "record_id", "snapshot_id", "locator", "record_kind", "raw_label",
            "raw_definition", "source_indicator", "parent_ids", "hierarchy_path"
        )}
        for record_id in record_ids
    ]
    mapping_cards = [
        {
            "identity_id": identity_id,
            "status": mappings[identity_id]["status"],
            "reason": mappings[identity_id]["reason"],
            "ambiguous": mappings[identity_id]["ambiguous"],
            "top_similarity": mappings[identity_id]["top_similarity"],
            "retrieved_candidate_ids": [
                candidate["candidate_market_id"] for candidate in mappings[identity_id]["candidates"]
            ],
        }
        for identity_id in required_ids
    ]
    required_candidate_cards = []
    context_candidate_cards = []
    for candidate_id in all_candidate_ids:
        catalog = candidates[candidate_id]
        ledger = candidate_ledger[candidate_id]
        target = (required_candidate_cards if candidate_id in required_candidate_ids
                  else context_candidate_cards)
        target.append({
            "candidate_market_id": candidate_id,
            "name": catalog["name"],
            "status": catalog["status"],
            "source_record_ids": catalog["source_record_ids"],
            "coverage_status": ledger["coverage_status"],
            "primary_family_id": ledger["primary_family_id"],
            "relevant_retrieval_occurrences": [
                item for item in ledger["retrieval_occurrences"] if item["identity_id"] in set(selected_ids)
            ],
        })
    context_edges = _family_edges(
        artifacts["context-edge-ledger.json.gz"], config["family_id"], set(selected_ids)
    )
    graph_mappings = [
        item for item in graph_projection["mappings"] if item.get("identity_id") in set(selected_ids)
    ]
    graph_market_ids = {market_id for item in graph_mappings for market_id in item.get("output_market_ids", [])}
    graph_markets = [
        item for item in graph_projection["markets"] if item["market_id"] in graph_market_ids
    ]
    counts = {
        "required_identities": len(required_ids),
        "context_identities": len(context_ids),
        "context_shards": len(config["scope"]["context_shards"]),
        "required_candidates": len(required_candidate_cards),
        "context_candidates": len(context_candidate_cards),
        "context_edges": len(context_edges),
        "identity_cards": len(identity_cards),
        "source_record_cards": len(source_record_cards),
        "mapping_cards": len(mapping_cards),
        "manual_definitions": len(manual_definitions),
        "manual_index_entries": len(manual_index_entries),
        "graph_mappings": len(graph_mappings),
        "graph_markets": len(graph_markets),
    }
    expected = config["expected_counts"]
    for key in ("required_identities", "context_identities", "context_shards", "required_candidates", "context_edges"):
        if counts[key] != expected[key]:
            raise ValueError(f"family pack count gate {key}: {counts[key]} != {expected[key]}")
    evidence_items = sum(counts[key] for key in (
        "identity_cards", "source_record_cards", "mapping_cards", "required_candidates",
        "context_edges", "graph_mappings", "graph_markets",
        "manual_definitions", "manual_index_entries", "context_candidates"
    ))
    if evidence_items > config["limits"]["max_evidence_items"]:
        raise ValueError("family pack evidence-item limit exceeded")
    pack: dict[str, Any] = {
        "schema_version": 2,
        "metadata": {
            "family_id": config["family_id"],
            "family_kind": config["family_kind"],
            "partition_id": pointer["partition_id"],
            "source_run_id": run_id,
            "graph_release_id": graph_pointer["release_id"],
            "schedule_receipt_sha256": pointer["receipt_sha256"],
            "graph_receipt_sha256": graph_pointer["receipt_sha256"],
            "graph_projection_sha256": graph_pointer["projection_sha256"],
            "source_artifact_hashes": config["source_binding"]["artifact_hashes"],
            "source_receipt_sha256": config["source_binding"]["receipt_sha256"],
            "implementation_hashes": config["implementation_hashes"],
            "config_sha256": canonical_sha256(config),
            "pack_sha256": "",
            "model_invoked": False,
        },
        "scope": {
            **config["scope"],
            "context_only_identity_ids": context_ids,
            "purpose": "operating-market boundary construction only",
            "prohibited_actions": config["prohibited_actions"],
        },
        "counts": {**counts, "evidence_items": evidence_items},
        "manual_definitions": manual_definitions,
        "manual_index_entries": manual_index_entries,
        "manual_index_missing_identity_ids": manual_index_missing_identity_ids,
        "identity_cards": identity_cards,
        "source_record_cards": source_record_cards,
        "mapping_cards": mapping_cards,
        "required_candidate_cards": required_candidate_cards,
        "context_candidate_cards": context_candidate_cards,
        "context_edges": context_edges,
        "graph_context": {
            "graph_version_id": graph_pointer["graph_version_id"],
            "mappings": graph_mappings,
            "markets": graph_markets,
            "interpretation_boundary": "Existing canonical graph context only; it does not decide this family.",
        },
    }
    if "supplemental_evidence" in config:
        extra = load_supplement(root, config["supplemental_evidence"],
            family_id=config["family_id"], source_run_id=run_id,
            subject_ids=set(required_ids + context_ids + required_candidate_ids))
        pack.update(extra)
        pack["counts"]["evidence_items"] += sum(len(rows) for rows in extra.values())
        if pack["counts"]["evidence_items"] > config["limits"]["max_evidence_items"]:
            raise ValueError("family pack evidence-item limit exceeded")
    pack["metadata"]["pack_sha256"] = _pack_hash(pack)
    return pack


def _pack_hash(pack: dict[str, Any]) -> str:
    copy = json.loads(json.dumps(pack))
    copy["metadata"]["pack_sha256"] = ""
    return canonical_sha256(copy)


def validate_family_evidence_pack_v2(
    pack: dict[str, Any], config: dict[str, Any], *, root: Path = ROOT
) -> list[str]:
    try:
        expected_pack = _assemble_family_evidence_pack_v2(config, root=root)
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
        return [f"pack cannot be regenerated from exact inputs: {error}"]
    return _validate_family_evidence_pack_v2(
        pack, config, root=root, expected_pack=expected_pack
    )


def _validate_family_evidence_pack_v2(
    pack: dict[str, Any],
    config: dict[str, Any],
    *,
    root: Path,
    expected_pack: dict[str, Any],
) -> list[str]:
    errors = _schema_errors(pack, "family-evidence-pack-v2.schema.json", root)
    if errors:
        return errors
    try:
        if pack.get("metadata", {}).get("pack_sha256") != _pack_hash(pack):
            errors.append("pack_sha256 does not match canonical pack content")
    except (KeyError, TypeError, ValueError):
        errors.append("pack content cannot be canonically hashed")
    if pack.get("metadata", {}).get("config_sha256") != canonical_sha256(config):
        errors.append("pack config hash does not match config")
    scope = pack.get("scope", {})
    required = scope.get("required_disposition_identity_ids", [])
    context = scope.get("context_only_identity_ids", [])
    if set(required) & set(context):
        errors.append("required and context-only identity sets overlap")
    if required != config.get("scope", {}).get("required_disposition_identity_ids"):
        errors.append("pack required identities do not match config")
    if scope.get("required_prior_candidate_ids") != config.get("scope", {}).get("required_prior_candidate_ids"):
        errors.append("pack required candidates do not match config")
    if len(_canonical_bytes(pack)) > config["limits"]["max_pack_bytes"]:
        errors.append("pack canonical byte-size limit exceeded")
    for field in (
        "metadata",
        "scope",
        "counts",
        "identity_cards",
        "manual_definitions",
        "manual_index_entries",
        "manual_index_missing_identity_ids",
        "source_record_cards",
        "mapping_cards",
        "required_candidate_cards",
        "context_candidate_cards",
        "context_edges",
        "graph_context",
    ):
        if pack.get(field) != expected_pack[field]:
            errors.append(f"pack {field} does not match exact regenerated content")
    for field in ("supplemental_sources", "supplemental_claims", "supplemental_gaps"):
        if (field in pack) != (field in expected_pack) or pack.get(field) != expected_pack.get(field):
            errors.append(f"pack {field} does not match exact regenerated content")
    return sorted(errors)


def dry_run_family_preparation_v2(
    family_id: str, *, root: Path = ROOT, limits: dict[str, int] | None = None,
    supplemental_manifest: Path | None = None
) -> dict[str, Any]:
    config = generate_family_config_v2(family_id, root=root, limits=limits,
                                       supplemental_manifest=supplemental_manifest)
    pack = compile_family_evidence_pack_v2(config, root=root)
    return {
        "valid": True,
        "family_id": family_id,
        "family_kind": config["family_kind"],
        "config_sha256": canonical_sha256(config),
        "pack_sha256": pack["metadata"]["pack_sha256"],
        "pack_bytes": len(_canonical_bytes(pack)),
        "counts": pack["counts"],
        "model_invoked": False,
        "persisted": False,
    }


def prepare_family_v2(
    family_id: str,
    *,
    root: Path = ROOT,
    output_root: Path | None = None,
    limits: dict[str, int] | None = None,
    supplemental_manifest: Path | None = None,
) -> dict[str, Any]:
    config = generate_family_config_v2(family_id, root=root, limits=limits,
                                       supplemental_manifest=supplemental_manifest)
    pack = compile_family_evidence_pack_v2(config, root=root)
    preparation_id = "family-preparation:" + canonical_sha256({
        "config_sha256": canonical_sha256(config),
        "pack_sha256": pack["metadata"]["pack_sha256"],
    })[:24]
    destination = (output_root or root / "data/family_preparations") / preparation_id
    if destination.exists():
        raise FileExistsError(f"family preparation already exists: {destination}")
    receipt = _preparation_receipt(preparation_id, config, pack)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".family-preparation-", dir=destination.parent) as raw:
        temporary = Path(raw)
        (temporary / "family-config-v2.json").write_bytes(_canonical_bytes(config))
        (temporary / "family-evidence-pack-v2.json").write_bytes(_canonical_bytes(pack))
        (temporary / "preparation-receipt.json").write_bytes(_canonical_bytes(receipt))
        temporary.replace(destination)
    return {"preparation_path": str(destination), **receipt}


def _preparation_receipt(
    preparation_id: str, config: dict[str, Any], pack: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "preparation_id": preparation_id,
        "family_id": config["family_id"],
        "partition_id": config["schedule_binding"]["partition_id"],
        "graph_release_id": config["graph_binding"]["release_id"],
        "config_sha256": canonical_sha256(config),
        "pack_sha256": pack["metadata"]["pack_sha256"],
        "pack_bytes": len(_canonical_bytes(pack)),
        "counts": pack["counts"],
        "model_invoked": False,
        "status": "prepared_no_model_call",
    }


def validate_family_preparation_v2(
    preparation_dir: Path, *, root: Path = ROOT
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        config_path = preparation_dir / "family-config-v2.json"
        pack_path = preparation_dir / "family-evidence-pack-v2.json"
        receipt_path = preparation_dir / "preparation-receipt.json"
        config = _object(config_path)
        pack = _object(pack_path)
        receipt = _object(receipt_path)
        for name, path, value in (
            ("config", config_path, config),
            ("pack", pack_path, pack),
            ("receipt", receipt_path, receipt),
        ):
            if path.read_bytes() != _canonical_bytes(value):
                errors.append(f"persisted {name} bytes are not canonical")
        schema_errors = (
            _schema_errors(config, "family-config-v2.schema.json", root)
            + _schema_errors(pack, "family-evidence-pack-v2.schema.json", root)
        )
        if schema_errors:
            raise ValueError("persisted schema validation failed: " + "; ".join(schema_errors))
        regenerated_config = generate_family_config_v2(
            config["family_id"], root=root, limits=config["limits"],
            supplemental_manifest=(Path(config["supplemental_evidence"]["manifest_path"])
                                   if "supplemental_evidence" in config else None)
        )
        regenerated_pack = compile_family_evidence_pack_v2(regenerated_config, root=root)
        if config != regenerated_config:
            errors.append("persisted config does not match deterministic regeneration")
        if pack != regenerated_pack:
            errors.append("persisted pack does not match deterministic regeneration")
        expected_id = "family-preparation:" + canonical_sha256({
            "config_sha256": canonical_sha256(config),
            "pack_sha256": pack["metadata"]["pack_sha256"],
        })[:24]
        if preparation_dir.name != expected_id or receipt.get("preparation_id") != expected_id:
            errors.append("preparation ID does not match content")
        if receipt != _preparation_receipt(expected_id, config, pack):
            errors.append("preparation receipt does not match exact config and pack")
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"family preparation cannot replay: {error}")
        receipt = {}
    return {
        "valid": not errors,
        "errors": errors,
        "preparation_id": receipt.get("preparation_id", preparation_dir.name),
        "family_id": receipt.get("family_id"),
    }
