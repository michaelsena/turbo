from __future__ import annotations

import hashlib
import gzip
import json
import re
from datetime import datetime, timedelta
from importlib.metadata import version
from pathlib import Path

from turbo.models import to_dict
from turbo.pipeline_paths import ROOT
from turbo.universe.identity_sources import identity_source_artifacts
from turbo.universe.multisource import NAPCS, PRIOR, reconcile
from turbo.universe.naics import parse_naics
from turbo.universe.naics_identity_sources import naics_identity_source_artifacts
from turbo.universe.napcs_hierarchy import napcs_hierarchy_artifacts

SOURCE = ROOT / "data/source_snapshots/2022-naics-structure.xlsx"
SOURCE_SNAPSHOT_DIR = ROOT / "data/source_snapshots"
SOURCE_MANIFEST = ROOT / "data/source_snapshots/census-naics-2022.snapshot.json"
NAPCS_MANIFEST = ROOT / "data/source_snapshots/census-napcs-2022.snapshot.json"
PRIOR_MANIFEST = ROOT / "data/source_snapshots/prior-model-normalized-markets-2026-11-05.snapshot.json"
NAPCS_HIERARCHY_CAPTURE = (
    ROOT
    / "data/source_snapshots/2022-napcs-trilateral-hierarchy-browser-capture.json"
)
NAPCS_HIERARCHY_MANIFEST = (
    ROOT
    / "data/source_snapshots/census-napcs-2022-trilateral-hierarchy.snapshot.json"
)
STRATEGY_CONFIG = ROOT / "config/strategy.json"
PROJECT_CONFIG = ROOT / "pyproject.toml"
GENERATED = ROOT / "data/generated"
RUNS = ROOT / "data/runs"
SOURCE_URL = "https://www.census.gov/naics/2022NAICS/2022_NAICS_Structure.xlsx"
METHOD_VERSION = "identity-source-semantic-reconciliation-v9"

UNIVERSE_CODE_PATHS = (
    "src/turbo/models.py",
    "src/turbo/pipeline.py",
    "src/turbo/pipeline_paths.py",
    "src/turbo/universe/identity_sources.py",
    "src/turbo/universe/multisource.py",
    "src/turbo/universe/naics.py",
    "src/turbo/universe/naics_identity_sources.py",
    "src/turbo/universe/napcs_hierarchy.py",
)
UNIVERSE_SCHEMA_PATHS = ("schemas/source-record.schema.json",)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_manifest_metadata(manifest: dict[str, object], name: str) -> list[str]:
    errors: list[str] = []
    required = {
        "acquired_at",
        "dataset_id",
        "file",
        "publisher",
        "reuse",
        "role",
        "sha256",
        "source_url",
    }
    missing = sorted(required - set(manifest))
    if missing:
        return [f"source manifest {name} missing: {', '.join(missing)}"]
    for field in required:
        if not isinstance(manifest[field], str) or not str(manifest[field]).strip():
            errors.append(f"source manifest {name} has empty or non-string {field}")
    try:
        acquired_at = datetime.fromisoformat(
            str(manifest["acquired_at"]).replace("Z", "+00:00")
        )
        if acquired_at.utcoffset() != timedelta(0):
            errors.append(f"source manifest {name} acquired_at must be UTC")
    except ValueError:
        errors.append(f"source manifest {name} has invalid acquired_at")
    if not str(manifest["source_url"]).startswith("https://"):
        errors.append(f"source manifest {name} source_url must use https")
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest["sha256"])):
        errors.append(f"source manifest {name} has invalid sha256")
    return errors


def validate_identity_references(
    reconciliation: dict[str, object],
    relationships: dict[str, object],
    governed_snapshot_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    source_records = reconciliation["source_records"]
    identities = reconciliation["source_identities"]
    source_ids = [record["record_id"] for record in source_records]
    identity_ids = [identity["identity_id"] for identity in identities]
    known_sources = set(source_ids)
    known_identities = set(identity_ids)
    if len(source_ids) != len(known_sources):
        errors.append("duplicate source record IDs")
    if len(identity_ids) != len(known_identities):
        errors.append("duplicate normalized source identity IDs")
    source_locator_keys: list[tuple[str, str]] = []
    for record in source_records:
        if record["snapshot_id"] not in governed_snapshot_ids:
            errors.append(
                f"source record {record['record_id']} references unknown snapshot "
                f"{record['snapshot_id']}"
            )
        locator = record.get("locator")
        if not isinstance(locator, str) or not locator.strip():
            errors.append(f"source record {record['record_id']} has an empty locator")
        else:
            source_locator_keys.append((record["snapshot_id"], locator))
        for identity_id in record["normalized_identity_ids"]:
            if identity_id not in known_identities:
                errors.append(
                    f"source record {record['record_id']} references unknown identity {identity_id}"
                )
        for edge in record["source_relationships"]:
            if edge["target_identity_id"] not in known_identities:
                errors.append(
                    f"source relationship references unknown identity "
                    f"{edge['target_identity_id']}"
                )
    if len(source_locator_keys) != len(set(source_locator_keys)):
        errors.append("duplicate source record locators within a governed snapshot")
    for identity in identities:
        missing = set(identity["source_record_ids"]) - known_sources
        if missing:
            errors.append(
                f"identity {identity['identity_id']} references unknown source records: "
                f"{sorted(missing)}"
            )
    identity_sources = {
        identity["identity_id"]: set(identity["source_record_ids"])
        for identity in identities
    }
    mappings = reconciliation["mappings"]
    mapping_identity_ids = [mapping["normalized_identity_id"] for mapping in mappings]
    if len(mapping_identity_ids) != len(set(mapping_identity_ids)):
        errors.append("duplicate normalized identity mappings")
    missing_mappings = known_identities - set(mapping_identity_ids)
    extra_mappings = set(mapping_identity_ids) - known_identities
    if missing_mappings:
        errors.append(
            f"normalized identities missing reconciliation mappings: {sorted(missing_mappings)}"
        )
    if extra_mappings:
        errors.append(
            f"reconciliation mappings reference unknown identities: {sorted(extra_mappings)}"
        )
    for mapping in mappings:
        identity_id = mapping["normalized_identity_id"]
        supporting_sources = set(mapping["supporting_source_record_ids"])
        missing_sources = supporting_sources - known_sources
        if missing_sources:
            errors.append(
                f"mapping {identity_id} references unknown source records: "
                f"{sorted(missing_sources)}"
            )
        if (
            identity_id in identity_sources
            and supporting_sources != identity_sources[identity_id]
        ):
            errors.append(
                f"mapping {identity_id} does not preserve its complete source-record set"
            )
    endpoint_fields = {
        "napcs_concordance_relationships": (
            "collection_identity_id",
            "trilateral_identity_id",
        ),
        "napcs_concordance_non_mappings": ("collection_identity_id",),
        "industry_product_relationships": (
            "industry_identity_id",
            "product_identity_id",
        ),
    }
    for collection, fields in endpoint_fields.items():
        observation_keys: list[tuple[str, str]] = []
        for edge in relationships[collection]:
            for field in fields:
                if edge[field] not in known_identities:
                    errors.append(
                        f"{collection} references unknown identity {edge[field]}"
                    )
            for observation in edge["source_observations"]:
                if observation["snapshot_id"] not in governed_snapshot_ids:
                    errors.append(
                        f"{collection} references unknown snapshot "
                        f"{observation['snapshot_id']}"
                    )
                locator = observation.get("locator")
                if not isinstance(locator, str) or not locator.strip():
                    errors.append(f"{collection} contains an empty source locator")
                else:
                    observation_keys.append((observation["snapshot_id"], locator))
        if len(observation_keys) != len(set(observation_keys)):
            errors.append(f"{collection} contains duplicate source observation locators")
    return errors


def validate_naics_identity_evidence(
    evidence: dict[str, object],
    known_identity_ids: set[str],
    governed_snapshot_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    locator_keys: list[tuple[str, str]] = []

    def observe_snapshot_and_locator(observation: dict[str, object], context: str) -> None:
        snapshot_id = observation.get("snapshot_id")
        locator = observation.get("locator")
        if snapshot_id not in governed_snapshot_ids:
            errors.append(f"{context} references unknown snapshot {snapshot_id}")
        if not isinstance(locator, str) or not locator.strip():
            errors.append(f"{context} has an empty locator")
        elif isinstance(snapshot_id, str):
            locator_keys.append((snapshot_id, locator))

    for entry in evidence["manual_index_entries"]:  # type: ignore[index]
        if entry["identity_id"] not in known_identity_ids:
            errors.append(
                f"manual index entry references unknown identity {entry['identity_id']}"
            )
        observe_snapshot_and_locator(entry, "manual index entry")
    for entry in evidence["manual_index_cross_references"]:  # type: ignore[index]
        observe_snapshot_and_locator(entry, "manual index cross-reference")
    for definition in evidence["manual_definitions"]:  # type: ignore[index]
        if definition["identity_id"] not in known_identity_ids:
            errors.append(
                f"manual definition references unknown identity {definition['identity_id']}"
            )
        delegated_to = definition["delegated_to_identity_id"]
        if delegated_to and delegated_to not in known_identity_ids:
            errors.append(
                f"manual definition delegates to unknown identity {delegated_to}"
            )
        observe_snapshot_and_locator(definition, "manual definition")
    for relationship in evidence["vintage_lineage_relationships"]:  # type: ignore[index]
        if relationship["naics_2022_identity_id"] not in known_identity_ids:
            errors.append(
                "vintage lineage references unknown identity "
                f"{relationship['naics_2022_identity_id']}"
            )
        for observation in relationship["source_observations"]:
            observe_snapshot_and_locator(observation, "vintage lineage observation")
    for observation in evidence["economic_census_bridge_observations"]:  # type: ignore[index]
        observe_snapshot_and_locator(observation, "NAICS bridge observation")
    if len(locator_keys) != len(set(locator_keys)):
        errors.append("NAICS identity evidence contains duplicate snapshot locators")
    return errors


def validate_napcs_hierarchy_evidence(
    evidence: dict[str, object],
    known_identity_ids: set[str],
    governed_snapshot_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    locator_keys: list[tuple[str, str]] = []
    for node in evidence["nodes"]:  # type: ignore[index]
        identity_id = f"identity:napcs-trilateral:{node['code']}"
        if identity_id not in known_identity_ids:
            errors.append(
                f"NAPCS hierarchy node references unknown identity {identity_id}"
            )
        snapshot_id = node.get("snapshot_id")
        locator = node.get("locator")
        if snapshot_id not in governed_snapshot_ids:
            errors.append(
                f"NAPCS hierarchy node references unknown snapshot {snapshot_id}"
            )
        if not isinstance(locator, str) or not locator.strip():
            errors.append(f"NAPCS hierarchy node {node['code']} has an empty locator")
        elif isinstance(snapshot_id, str):
            locator_keys.append((snapshot_id, locator))
        parent_code = node.get("parent_code")
        if parent_code:
            parent_identity_id = f"identity:napcs-trilateral:{parent_code}"
            if parent_identity_id not in known_identity_ids:
                errors.append(
                    "NAPCS hierarchy node references unknown parent identity "
                    f"{parent_identity_id}"
                )
    if len(locator_keys) != len(set(locator_keys)):
        errors.append("NAPCS hierarchy evidence contains duplicate snapshot locators")
    for code in evidence["hierarchy_only_product_codes"]:  # type: ignore[index]
        identity_id = f"identity:napcs-trilateral:{code}"
        if identity_id not in known_identity_ids:
            errors.append(
                "NAPCS hierarchy-only product references unknown identity "
                f"{identity_id}"
            )
    return errors


def source_registry() -> list[dict[str, object]]:
    registry: list[dict[str, object]] = []
    for manifest_path in sorted(SOURCE_SNAPSHOT_DIR.glob("*.snapshot.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        registry.append(
            {
                "dataset_id": manifest["dataset_id"],
                "file": manifest["file"],
                "manifest_file": manifest_path.name,
                "manifest_sha256": sha256(manifest_path),
                "sha256": manifest["sha256"],
            }
        )
    return registry


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _code_fingerprint() -> str:
    digest = hashlib.sha256()
    for relative_path in UNIVERSE_CODE_PATHS:
        path = ROOT / relative_path
        digest.update(relative_path.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _schema_fingerprint() -> str:
    digest = hashlib.sha256()
    for relative_path in UNIVERSE_SCHEMA_PATHS:
        path = ROOT / relative_path
        digest.update(relative_path.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_immutable(path: Path, value: object) -> None:
    rendered = _canonical_bytes(value)
    if path.exists():
        if path.read_bytes() != rendered:
            raise ValueError(f"immutable artifact mismatch: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rendered)


def _canonical_gzip(value: object) -> bytes:
    rendered = bytearray(
        gzip.compress(_canonical_bytes(value), compresslevel=9, mtime=0)
    )
    # RFC 1952 byte 9 is the originating OS. Force the portable unknown value so
    # identical content hashes across supported operating systems and Python builds.
    rendered[9] = 255
    return bytes(rendered)


def _write_immutable_gzip(path: Path, value: object) -> None:
    rendered = _canonical_gzip(value)
    if path.exists():
        if path.read_bytes() != rendered:
            raise ValueError(f"immutable artifact mismatch: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rendered)


def run() -> dict[str, object]:
    errors = validate()
    if errors:
        raise ValueError("source validation failed: " + "; ".join(errors))
    GENERATED.mkdir(parents=True, exist_ok=True)
    nodes = parse_naics(SOURCE)
    reconciliation = reconcile()
    identity_summary, identity_relationships = identity_source_artifacts()
    naics_identity_summary, naics_identity_evidence = naics_identity_source_artifacts()
    napcs_hierarchy_summary, napcs_hierarchy_evidence = napcs_hierarchy_artifacts()
    registry = source_registry()
    identity_errors = validate_identity_references(
        reconciliation,
        identity_relationships,
        {str(item["dataset_id"]) for item in registry},
    )
    identity_errors.extend(
        validate_naics_identity_evidence(
            naics_identity_evidence,
            {
                str(item["identity_id"])
                for item in reconciliation["source_identities"]
            },
            {str(item["dataset_id"]) for item in registry},
        )
    )
    identity_errors.extend(
        validate_napcs_hierarchy_evidence(
            napcs_hierarchy_evidence,
            {
                str(item["identity_id"])
                for item in reconciliation["source_identities"]
            },
            {str(item["dataset_id"]) for item in registry},
        )
    )
    if identity_errors:
        raise ValueError("identity reference validation failed: " + "; ".join(identity_errors))
    leaf_nodes = [node for node in nodes if node.level == 6]
    source_hash = sha256(SOURCE)
    source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    if source_hash != source_manifest["sha256"]:
        raise ValueError("source snapshot hash does not match pinned manifest")
    code_fingerprint = _code_fingerprint()
    run_config = {
        "code_fingerprint": code_fingerprint,
        "dependency_versions": {"pypdf": version("pypdf")},
        "method_version": METHOD_VERSION,
        "project_config_sha256": sha256(PROJECT_CONFIG),
        "schema_version": 1,
        "schema_fingerprint": _schema_fingerprint(),
        "source_sha256": source_hash,
        "napcs_sha256": sha256(NAPCS),
        "prior_seed_sha256": sha256(PRIOR),
        "source_manifest_sha256": sha256(SOURCE_MANIFEST),
        "napcs_manifest_sha256": sha256(NAPCS_MANIFEST),
        "napcs_hierarchy_capture_sha256": sha256(NAPCS_HIERARCHY_CAPTURE),
        "napcs_hierarchy_manifest_sha256": sha256(NAPCS_HIERARCHY_MANIFEST),
        "prior_seed_manifest_sha256": sha256(PRIOR_MANIFEST),
        "strategy_config_sha256": sha256(STRATEGY_CONFIG),
        "source_registry_sha256": hashlib.sha256(_canonical_bytes(registry)).hexdigest(),
    }
    run_id = "run-" + hashlib.sha256(_canonical_bytes(run_config)).hexdigest()[:20]
    run_dir = RUNS / run_id
    universe = {
        "schema_version": 1,
        "run_id": run_id,
        "artifact_type": "raw_official_source_hierarchy",
        "warning": "NAICS source categories are not canonical operating markets.",
        "source_snapshot": source_manifest,
        "nodes": [to_dict(node) for node in nodes],
    }
    receipt = {
        "schema_version": 1,
        "run_id": run_id,
        "run_config": run_config,
        "source_sha256": source_hash,
        "source_nodes": len(nodes),
        "governed_source_snapshots": len(registry),
        "multisource_counts": reconciliation["source_counts"],
        "reconciliation_mapping_counts": reconciliation["mapping_counts"],
        "identity_source_counts": {
            "collection_to_trilateral_rows": identity_summary["collection_to_trilateral"]["rows"],
            "trilateral_to_collection_rows": identity_summary["trilateral_to_collection"]["rows"],
            "industry_by_products_rows": identity_summary["industry_by_products"]["rows"],
            "industry_by_products_national_six_digit_observations": identity_summary["industry_by_products"]["national_six_digit_rows"],
            "products_by_industry_rows": identity_summary["products_by_industry"]["rows"],
            "products_by_industry_national_six_digit_observations": identity_summary["products_by_industry"]["national_six_digit_rows"],
            "industry_product_source_observations": (
                identity_summary["industry_by_products"]["national_six_digit_rows"]
                + identity_summary["products_by_industry"]["national_six_digit_rows"]
            ),
            "products_by_industry_unique_national_six_digit_pairs": identity_summary["products_by_industry"]["unique_national_six_digit_naics_napcs_pairs"],
            "napcs_concordance_relationships": identity_summary["relationship_artifact_counts"]["napcs_concordance_relationships"],
            "napcs_concordance_non_mappings": identity_summary["relationship_artifact_counts"]["napcs_concordance_non_mappings"],
            "industry_product_relationships": identity_summary["relationship_artifact_counts"]["industry_product_relationships"],
            "naics_manual_index_coded_entries": naics_identity_summary["manual_index"]["coded_entries"],
            "naics_manual_index_cross_references": naics_identity_summary["manual_index"]["uncoded_cross_reference_rows"],
            "naics_manual_index_codes": naics_identity_summary["manual_index"]["represented_six_digit_codes"],
            "naics_manual_definitions": naics_identity_summary["manual_definitions"]["definitions"],
            "naics_manual_illustrative_example_blocks": naics_identity_summary["manual_definitions"]["illustrative_example_blocks"],
            "naics_manual_cross_reference_blocks": naics_identity_summary["manual_definitions"]["cross_reference_blocks"],
            "naics_manual_delegated_definition_links": naics_identity_summary["manual_definitions"]["delegated_definition_links"],
            "naics_vintage_lineage_pairs": naics_identity_summary["full_concordance"]["unique_pairs"],
            "naics_bridge_observations": (
                naics_identity_summary["economic_census_bridges"]["2017_to_2022_observations"]
                + naics_identity_summary["economic_census_bridges"]["2022_to_2017_observations"]
            ),
            "napcs_hierarchy_pages": napcs_hierarchy_summary["pages"],
            "napcs_hierarchy_response_entity_bytes": napcs_hierarchy_summary["response_entity_bytes"],
            "napcs_hierarchy_nodes": napcs_hierarchy_summary["nodes"],
            "napcs_hierarchy_sections": napcs_hierarchy_summary["level_counts"]["section"],
            "napcs_hierarchy_subsections": napcs_hierarchy_summary["level_counts"]["subsection"],
            "napcs_hierarchy_divisions": napcs_hierarchy_summary["level_counts"]["division"],
            "napcs_hierarchy_groups": napcs_hierarchy_summary["level_counts"]["group"],
            "napcs_hierarchy_subgroups": napcs_hierarchy_summary["level_counts"]["subgroup"],
            "napcs_hierarchy_products": napcs_hierarchy_summary["level_counts"]["trilateral_product"],
            "napcs_hierarchy_only_products": napcs_hierarchy_summary["hierarchy_only_products"],
            "napcs_hierarchy_published_parent_anomalies": napcs_hierarchy_summary["published_parent_anomalies"],
        },
        "six_digit_source_categories": len(leaf_nodes),
        "canonical_markets": 0,
        "target_markets": 0,
        "research_scores": 0,
        "current_stage": "source_reconciliation_before_canonical_market_decisions",
    }
    output_hashes = {
        "raw-source-hierarchy.json.gz": hashlib.sha256(_canonical_gzip(universe)).hexdigest(),
        "multisource-reconciliation.json.gz": hashlib.sha256(
            _canonical_gzip(reconciliation)
        ).hexdigest(),
        "identity-source-summary.json.gz": hashlib.sha256(
            _canonical_gzip(identity_summary)
        ).hexdigest(),
        "identity-relationships.json.gz": hashlib.sha256(
            _canonical_gzip(identity_relationships)
        ).hexdigest(),
        "naics-identity-source-summary.json.gz": hashlib.sha256(
            _canonical_gzip(naics_identity_summary)
        ).hexdigest(),
        "naics-identity-evidence.json.gz": hashlib.sha256(
            _canonical_gzip(naics_identity_evidence)
        ).hexdigest(),
        "napcs-hierarchy-source-summary.json.gz": hashlib.sha256(
            _canonical_gzip(napcs_hierarchy_summary)
        ).hexdigest(),
        "napcs-hierarchy-evidence.json.gz": hashlib.sha256(
            _canonical_gzip(napcs_hierarchy_evidence)
        ).hexdigest(),
    }
    receipt["output_hashes"] = output_hashes
    _write_immutable_gzip(run_dir / "raw-source-hierarchy.json.gz", universe)
    _write_immutable_gzip(
        run_dir / "multisource-reconciliation.json.gz",
        reconciliation,
    )
    _write_immutable_gzip(run_dir / "identity-source-summary.json.gz", identity_summary)
    _write_immutable_gzip(
        run_dir / "identity-relationships.json.gz",
        identity_relationships,
    )
    _write_immutable_gzip(
        run_dir / "naics-identity-source-summary.json.gz",
        naics_identity_summary,
    )
    _write_immutable_gzip(
        run_dir / "naics-identity-evidence.json.gz",
        naics_identity_evidence,
    )
    _write_immutable_gzip(
        run_dir / "napcs-hierarchy-source-summary.json.gz",
        napcs_hierarchy_summary,
    )
    _write_immutable_gzip(
        run_dir / "napcs-hierarchy-evidence.json.gz",
        napcs_hierarchy_evidence,
    )
    _write_immutable(run_dir / "run-receipt.json", receipt)
    latest = {
        **receipt,
        "immutable_run_path": str(run_dir.relative_to(ROOT)),
    }
    _write_json(GENERATED / "latest-run.json", latest)
    return latest


def validate() -> list[str]:
    errors: list[str] = []
    manifests = sorted(SOURCE_SNAPSHOT_DIR.glob("*.snapshot.json"))
    if not manifests:
        errors.append("no source snapshot manifests")
    dataset_ids: set[str] = set()
    governed_files: set[str] = set()
    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            errors.append(f"invalid source manifest {manifest_path.name}: {error}")
            continue
        metadata_errors = validate_manifest_metadata(manifest, manifest_path.name)
        if metadata_errors:
            errors.extend(metadata_errors)
            continue
        dataset_id = str(manifest["dataset_id"])
        file_name = str(manifest["file"])
        if dataset_id in dataset_ids:
            errors.append(f"duplicate source dataset_id: {dataset_id}")
        dataset_ids.add(dataset_id)
        if file_name in governed_files:
            errors.append(f"duplicate governed source file: {file_name}")
        governed_files.add(file_name)
        if Path(file_name).name != file_name:
            errors.append(f"source manifest file must be a basename: {manifest_path.name}")
            continue
        snapshot = SOURCE_SNAPSHOT_DIR / file_name
        if not snapshot.exists():
            errors.append(f"missing source snapshot: {snapshot}")
            continue
        if manifest.get("sha256") != sha256(snapshot):
            errors.append(f"source snapshot hash does not match manifest: {snapshot.name}")
    if not SOURCE.exists():
        return errors
    nodes = parse_naics(SOURCE)
    ids = [node.node_id for node in nodes]
    if len(ids) != len(set(ids)):
        errors.append("duplicate market node IDs")
    known = set(ids)
    for node in nodes:
        if node.parent_id is not None and node.parent_id not in known:
            errors.append(f"missing parent {node.parent_id} for {node.node_id}")
    if not any(node.level == 6 for node in nodes):
        errors.append("no six-digit source categories")
    if not errors:
        try:
            reconciliation = reconcile()
            _, relationships = identity_source_artifacts()
            _, naics_identity_evidence = naics_identity_source_artifacts()
            _, napcs_hierarchy_evidence = napcs_hierarchy_artifacts()
            errors.extend(
                validate_identity_references(
                    reconciliation,
                    relationships,
                    dataset_ids,
                )
            )
            errors.extend(
                validate_naics_identity_evidence(
                    naics_identity_evidence,
                    {
                        str(item["identity_id"])
                        for item in reconciliation["source_identities"]
                    },
                    dataset_ids,
                )
            )
            errors.extend(
                validate_napcs_hierarchy_evidence(
                    napcs_hierarchy_evidence,
                    {
                        str(item["identity_id"])
                        for item in reconciliation["source_identities"]
                    },
                    dataset_ids,
                )
            )
        except Exception as error:
            errors.append(f"identity/reference validation failed: {error}")
    if not errors:
        try:
            from jsonschema import Draft202012Validator

            from turbo.agents.boundary_harness import (
                load_adjudication_schema,
                load_specialist_schema,
            )
            from turbo.universe.boundary_pack import (
                build_boundary_pack,
                validate_boundary_pack,
            )

            Draft202012Validator.check_schema(load_specialist_schema())
            Draft202012Validator.check_schema(load_adjudication_schema())
            family_configs = sorted((ROOT / "config/universe/families").glob("*.json"))
            if not family_configs:
                errors.append("no boundary family configurations")
            for config_path in family_configs:
                pack = build_boundary_pack(config_path)
                errors.extend(
                    f"boundary family {config_path.name}: {error}"
                    for error in validate_boundary_pack(pack)
                )
        except Exception as error:
            errors.append(f"boundary harness validation failed: {error}")
    return errors

