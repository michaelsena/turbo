from __future__ import annotations

import hashlib
import json
from pathlib import Path

from turbo.models import to_dict
from turbo.pipeline_paths import ROOT
from turbo.universe.multisource import NAPCS, PRIOR, reconcile
from turbo.universe.naics import parse_naics

SOURCE = ROOT / "data/source_snapshots/2022-naics-structure.xlsx"
SOURCE_MANIFEST = ROOT / "data/source_snapshots/census-naics-2022.snapshot.json"
NAPCS_MANIFEST = ROOT / "data/source_snapshots/census-napcs-2022.snapshot.json"
PRIOR_MANIFEST = ROOT / "data/source_snapshots/prior-model-normalized-markets-2026-11-05.snapshot.json"
STRATEGY_CONFIG = ROOT / "config/strategy.json"
GENERATED = ROOT / "data/generated"
RUNS = ROOT / "data/runs"
SOURCE_URL = "https://www.census.gov/naics/2022NAICS/2022_NAICS_Structure.xlsx"
METHOD_VERSION = "multisource-universe-bootstrap-v2"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _code_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted((ROOT / "src/turbo").rglob("*.py")):
        digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
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


def run() -> dict[str, object]:
    errors = validate()
    if errors:
        raise ValueError("source validation failed: " + "; ".join(errors))
    GENERATED.mkdir(parents=True, exist_ok=True)
    nodes = parse_naics(SOURCE)
    reconciliation = reconcile()
    leaf_nodes = [node for node in nodes if node.level == 6]
    source_hash = sha256(SOURCE)
    source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    if source_hash != source_manifest["sha256"]:
        raise ValueError("source snapshot hash does not match pinned manifest")
    code_fingerprint = _code_fingerprint()
    run_config = {
        "code_fingerprint": code_fingerprint,
        "method_version": METHOD_VERSION,
        "schema_version": 1,
        "source_sha256": source_hash,
        "napcs_sha256": sha256(NAPCS),
        "prior_seed_sha256": sha256(PRIOR),
        "source_manifest_sha256": sha256(SOURCE_MANIFEST),
        "napcs_manifest_sha256": sha256(NAPCS_MANIFEST),
        "prior_seed_manifest_sha256": sha256(PRIOR_MANIFEST),
        "strategy_config_sha256": sha256(STRATEGY_CONFIG),
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
        "multisource_counts": reconciliation["source_counts"],
        "reconciliation_mapping_counts": reconciliation["mapping_counts"],
        "six_digit_source_categories": len(leaf_nodes),
        "canonical_markets": 0,
        "target_markets": 0,
        "research_scores": 0,
        "current_stage": "source_reconciliation_before_canonical_market_decisions",
    }
    output_hashes = {
        "raw-source-hierarchy.json": hashlib.sha256(_canonical_bytes(universe)).hexdigest(),
        "multisource-reconciliation.json": hashlib.sha256(_canonical_bytes(reconciliation)).hexdigest(),
    }
    receipt["output_hashes"] = output_hashes
    _write_immutable(run_dir / "raw-source-hierarchy.json", universe)
    _write_immutable(run_dir / "multisource-reconciliation.json", reconciliation)
    _write_immutable(run_dir / "run-receipt.json", receipt)
    latest = {
        **receipt,
        "immutable_run_path": str(run_dir.relative_to(ROOT)),
    }
    _write_json(GENERATED / "latest-run.json", latest)
    return latest


def validate() -> list[str]:
    errors: list[str] = []
    for snapshot, manifest_path in (
        (SOURCE, SOURCE_MANIFEST),
        (NAPCS, NAPCS_MANIFEST),
        (PRIOR, PRIOR_MANIFEST),
    ):
        if not snapshot.exists():
            errors.append(f"missing source snapshot: {snapshot}")
            continue
        if not manifest_path.exists():
            errors.append(f"missing source manifest: {manifest_path}")
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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
    return errors

