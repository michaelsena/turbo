from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_context(root: Path) -> dict[str, Any]:
    pointer_path = root / "data" / "generated" / "latest-run.json"
    pointer = _object(pointer_path)
    receipt_path = root / pointer["immutable_run_path"] / "run-receipt.json"
    receipt = _object(receipt_path)
    comparable = dict(pointer)
    comparable.pop("immutable_run_path", None)
    if comparable != receipt:
        raise ValueError("latest source-run pointer does not match immutable receipt")
    immutable_run_dir = receipt_path.parent
    for name, expected in receipt["output_hashes"].items():
        if _sha256_path(immutable_run_dir / name) != expected:
            raise ValueError(f"source-run artifact hash mismatch: {name}")
    return {
        "status": "source_reconciliation_complete",
        "run_id": receipt["run_id"],
        "immutable_run_path": pointer["immutable_run_path"],
        "source_run_local_stage": receipt["current_stage"],
        "normalized_identities": receipt["multisource_counts"][
            "normalized_source_identities"
        ],
        "source_records": receipt["multisource_counts"]["source_records"],
        "six_digit_naics": receipt["six_digit_source_categories"],
        "prior_candidate_markets": receipt["multisource_counts"][
            "prior_candidate_markets"
        ],
        "output_hashes": receipt["output_hashes"],
    }


def _graph_context(root: Path, source_run_id: str) -> dict[str, Any]:
    pointer_path = root / "data" / "generated" / "latest-graph.json"
    if not pointer_path.exists():
        return {
            "status": "not_started",
            "source_universe_run_id": source_run_id,
            "canonical_markets": 0,
            "mappings": 0,
        }
    pointer = _object(pointer_path)
    release_dir = root / pointer["release_path"]
    receipt = _object(release_dir / "graph-receipt.json")
    projection = _object(release_dir / "projection.json")
    if canonical_sha256(receipt) != pointer["receipt_sha256"]:
        raise ValueError("latest graph pointer receipt hash mismatch")
    if canonical_sha256(projection) != pointer["projection_sha256"]:
        raise ValueError("latest graph pointer projection hash mismatch")
    if receipt["projection_sha256"] != pointer["projection_sha256"]:
        raise ValueError("graph receipt and pointer projection hashes disagree")
    if receipt["release_id"] != pointer["release_id"]:
        raise ValueError("graph receipt and pointer release IDs disagree")
    if receipt["graph_version_id"] != projection["graph_version_id"]:
        raise ValueError("graph receipt and projection version IDs disagree")
    if receipt["source_universe_run_id"] != source_run_id:
        raise ValueError("graph release and source-universe run disagree")
    if receipt["counts"]["canonical_markets"] != len(projection["markets"]):
        raise ValueError("graph receipt canonical-market count mismatch")
    if receipt["counts"]["mappings"] != len(projection["mappings"]):
        raise ValueError("graph receipt mapping count mismatch")
    return {
        "status": "canonical_universe_construction_in_progress",
        "release_id": receipt["release_id"],
        "graph_version_id": receipt["graph_version_id"],
        "source_universe_run_id": receipt["source_universe_run_id"],
        "release_path": pointer["release_path"],
        "as_of_utc": receipt["as_of_utc"],
        **receipt["counts"],
    }


def _schedule_context(root: Path, source_run_id: str) -> dict[str, Any]:
    pointer_path = root / "data" / "generated" / "latest-family-schedule.json"
    if not pointer_path.exists():
        return {"status": "not_started"}
    pointer = _object(pointer_path)
    schedule_dir = root / pointer["schedule_path"]
    receipt = _object(schedule_dir / "schedule-receipt.json")
    if canonical_sha256(receipt) != pointer["receipt_sha256"]:
        raise ValueError("latest family-schedule pointer receipt hash mismatch")
    if receipt["partition_id"] != pointer["partition_id"]:
        raise ValueError("family-schedule receipt and pointer IDs disagree")
    if receipt["source_run_id"] != source_run_id:
        raise ValueError("family schedule and source-universe run disagree")
    if receipt["counts"] != pointer["counts"]:
        raise ValueError("family-schedule receipt and pointer counts disagree")
    for name, expected in receipt["output_hashes"].items():
        if _sha256_path(schedule_dir / name) != expected:
            raise ValueError(f"family-schedule artifact hash mismatch: {name}")
    return {
        "status": receipt["status"],
        "partition_id": receipt["partition_id"],
        "source_run_id": receipt["source_run_id"],
        "schedule_path": pointer["schedule_path"],
        "as_of_utc": receipt["as_of_utc"],
        "counts": receipt["counts"],
        "model_invoked": receipt["model_invoked"],
    }


def compile_system_context(*, root: Path = ROOT) -> dict[str, Any]:
    source = _source_context(root)
    graph = _graph_context(root, source["run_id"])
    schedule = _schedule_context(root, source["run_id"])
    canonical_markets = int(graph.get("canonical_markets", 0))
    return {
        "schema_version": 2,
        "source_universe": source,
        "family_schedule": schedule,
        "canonical_market_graph": graph,
        "target_universe": {"status": "not_started", "count": 0},
        "evaluation": {"status": "not_started", "score_count": 0},
        "current_stage": (
            "canonical_universe_construction_in_progress"
            if canonical_markets or schedule.get("status") != "not_started"
            else "source_reconciliation_complete"
        ),
        "canonical_markets": canonical_markets,
        "target_markets": 0,
        "research_scores": 0,
    }
