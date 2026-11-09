from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

from turbo.agents.boundary_harness import canonical_sha256
from turbo.agents.boundary_review import validate_independent_review_run
from turbo.agents.boundary_runner import _git_head, validate_boundary_run
from turbo.agents.runtime import sha256_text
from turbo.pipeline_paths import ROOT
from turbo.universe.boundary_pack import build_boundary_pack
from turbo.universe.graph import (
    market_id_from_creation,
    market_version_id,
    project_graph,
    validate_event,
)


DIMENSION_FIELDS = {
    "buyer": "buyer",
    "job": "job_to_be_done",
    "delivery": "delivery_model",
    "workforce": "workforce_model",
    "economics_risk": "economics_risk",
    "acquisition_universe": "acquisition_universe",
    "ambient_ai_workflow": "ambient_ai_workflow",
}
FULL_GIT_COMMIT = re.compile(r"[0-9a-f]{40}")


def _git_worktree_clean(root: Path) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0 and not completed.stdout.strip()


def _git_commit_exists(root: Path, commit: str) -> bool:
    if FULL_GIT_COMMIT.fullmatch(commit) is None:
        return False
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _load_array(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{path} must contain an array of JSON objects")
    return value


def _path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _assert_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} mismatch: {actual!r} != {expected!r}")


def _prepare_inputs(
    activation_config_path: Path,
    *,
    root: Path,
) -> dict[str, Any]:
    config = _load_object(activation_config_path)
    if config.get("schema_version") != 1:
        raise ValueError("activation config schema_version must equal 1")
    if config.get("candidate_disposition_policy") != {
        "family_local_non_mappings_remain_global_candidates": True,
        "emit_reject_candidate_events": False,
    }:
        raise ValueError(
            "activation must preserve family-local candidate non-mappings globally"
        )
    prohibited = set(config.get("prohibited_actions", []))
    required_prohibitions = {
        "target-universe filtering",
        "market attractiveness scoring",
        "company discovery or evaluation",
        "global deletion or rejection of family-local candidate non-mappings",
        "model invocation",
    }
    if not required_prohibitions.issubset(prohibited):
        raise ValueError("activation config is missing a required prohibited action")

    boundary_config_path = _path(root, config["source_family_config"])
    review_config_path = _path(root, config["source_review_config"])
    run_dir = _path(root, config["source_run_dir"])
    review_dir = _path(root, config["source_review_dir"])
    _assert_equal(
        sha256_text(boundary_config_path.read_text(encoding="utf-8")),
        config["source_family_config_sha256"],
        "source family config hash",
    )
    _assert_equal(
        sha256_text(review_config_path.read_text(encoding="utf-8")),
        config["source_review_config_sha256"],
        "source review config hash",
    )

    run_replay = validate_boundary_run(run_dir, boundary_config_path, root=root)
    if not run_replay["valid"]:
        raise ValueError(f"source boundary run failed replay: {run_replay['errors']}")
    review_replay = validate_independent_review_run(
        review_dir, review_config_path, boundary_config_path, root=root
    )
    if not review_replay["valid"]:
        raise ValueError(f"source independent review failed replay: {review_replay['errors']}")

    run_receipt = _load_object(run_dir / "run-receipt.json")
    adjudication = _load_object(run_dir / "adjudicator.json")
    review = _load_object(review_dir / "review.json")
    review_receipt = _load_object(review_dir / "review.receipt.json")
    exact = {
        "source_run_id": run_receipt["boundary_run_id"],
        "source_run_execution_commit": run_receipt["git_commit"],
        "source_pack_sha256": run_receipt["input_pack_sha256"],
        "source_adjudication_sha256": canonical_sha256(adjudication),
        "source_review_id": review["review_id"],
        "source_review_output_sha256": canonical_sha256(review),
        "required_review_verdict": review["verdict"],
    }
    for field, expected in exact.items():
        _assert_equal(config.get(field), expected, field)
    _assert_equal(
        review_receipt.get("output_sha256"),
        config["source_review_output_sha256"],
        "review receipt output hash",
    )
    finding_counts = {
        severity: sum(
            1 for item in review["findings"] if item.get("severity") == severity
        )
        for severity in ("P0", "P1", "P2")
    }
    _assert_equal(
        finding_counts, config["required_review_findings"], "review finding counts"
    )
    if review["verdict"] != "approve_activation":
        raise ValueError("activation requires an approve_activation review verdict")
    if review["findings"] or any(check["status"] != "pass" for check in review["checks"]):
        raise ValueError("activation requires zero findings and every review check passing")

    pack = build_boundary_pack(boundary_config_path, root=root)
    proposals = {item["proposal_id"]: item for item in adjudication["proposed_markets"]}
    configured_proposals = {
        item["proposal_id"]: item for item in config["activate_proposals"]
    }
    if set(configured_proposals) != set(proposals):
        raise ValueError("activation must cover the exact adjudicated proposal set")
    if len(configured_proposals) != len(config["activate_proposals"]):
        raise ValueError("activate_proposals contains duplicate proposal IDs")

    gaps = {item["gap_id"]: item for item in adjudication["research_gaps"]}
    for item in config["activate_proposals"]:
        unknown = set(item["research_gap_ids"]) - set(gaps)
        if unknown:
            raise ValueError(f"proposal activation references unknown gaps: {sorted(unknown)}")
    mapping_dispositions = {
        (item["identity_id"], item["proposal_id"]): item
        for item in adjudication["identity_dispositions"]
        if item["proposal_id"] is not None
    }
    configured_mappings = {
        (item["identity_id"], item["proposal_id"]): item
        for item in config["activate_identity_mappings"]
    }
    if set(configured_mappings) != set(mapping_dispositions):
        raise ValueError("activation must cover the exact proposal-mapping disposition set")
    if len(configured_mappings) != len(config["activate_identity_mappings"]):
        raise ValueError("activate_identity_mappings contains duplicates")
    for key, item in configured_mappings.items():
        disposition = mapping_dispositions[key]
        _assert_equal(item["relationship_type"], disposition["relationship_type"], "mapping relationship")
        _assert_equal(item["research_gap_ids"], [disposition["gap_id"]], "mapping gap")

    return {
        "config": config,
        "config_sha256": sha256_text(
            activation_config_path.read_text(encoding="utf-8")
        ),
        "activation_id": "boundary-activation-"
        + canonical_sha256(config)[:20],
        "adjudication": adjudication,
        "review": review,
        "pack": pack,
        "proposals": proposals,
        "configured_proposals": configured_proposals,
        "gaps": gaps,
        "mapping_dispositions": mapping_dispositions,
    }


def _source_indexes(pack: dict[str, Any]) -> dict[str, Any]:
    evidence_by_id = {
        item["evidence_id"]: item for item in pack["evidence_catalog"]
    }
    subject_sources: dict[str, set[str]] = {}
    known_sources: set[str] = set()
    for item in pack["evidence_catalog"]:
        sources = set(item["source_record_ids"])
        known_sources.update(sources)
        for subject_id in item["subject_ids"]:
            subject_sources.setdefault(subject_id, set()).update(sources)
    candidate_sources: dict[str, set[str]] = {
        item["candidate_market_id"]: set()
        for item in pack["prior_candidate_catalog"]
    }
    for item in pack["retrieved_prior_candidate_details"]:
        sources = set(item["source_record_ids"])
        candidate_sources[item["candidate_market_id"]] = sources
        subject_sources.setdefault(item["candidate_market_id"], set()).update(sources)
        known_sources.update(sources)
    return {
        "evidence_by_id": evidence_by_id,
        "subject_sources": subject_sources,
        "candidate_sources": candidate_sources,
        "known_source_record_ids": known_sources,
        "known_candidate_market_ids": set(candidate_sources),
    }


def _source_records(
    evidence_ids: Iterable[str],
    subject_ids: Iterable[str],
    indexes: dict[str, Any],
) -> list[str]:
    sources: set[str] = set()
    all_subjects = set(subject_ids)
    for evidence_id in evidence_ids:
        evidence = indexes["evidence_by_id"][evidence_id]
        sources.update(evidence["source_record_ids"])
        all_subjects.update(evidence["subject_ids"])
    for subject_id in all_subjects:
        sources.update(indexes["subject_sources"].get(subject_id, set()))
    return sorted(sources)


def _operating_identity(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        dimension: {
            "result": proposal[field],
            "confidence": proposal["confidence_by_dimension"][dimension],
        }
        for dimension, field in DIMENSION_FIELDS.items()
    }


def _review_record(inputs: dict[str, Any]) -> dict[str, str]:
    return {
        "proposer": f"adjudicator:{inputs['config']['source_run_id']}",
        "independent_reviewer": f"independent-review:{inputs['review']['review_id']}",
        "result": "accepted",
    }


def _event_common(
    inputs: dict[str, Any],
    proposal: dict[str, Any],
    *,
    event_id: str,
    activation_status: str,
    research_gap_ids: list[str],
    source_record_ids: list[str],
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "decision": "accepted",
        "recorded_at": inputs["config"]["recorded_at_utc"],
        "input_source_record_ids": source_record_ids,
        "input_market_ids": [],
        "input_candidate_market_ids": proposal["candidate_market_ids"],
        "operating_identity": _operating_identity(proposal),
        "supporting_record_ids": proposal["supporting_evidence_ids"],
        "counterevidence_record_ids": proposal["counterevidence_ids"],
        "alternatives_considered": inputs["adjudication"]["alternatives_considered"],
        "review": _review_record(inputs),
        "supersedes": [],
        "supersedes_market_version_ids": [],
        "proposal_id": proposal["proposal_id"],
        "activation_status": activation_status,
        "research_gap_ids": research_gap_ids,
        "research_gaps": [inputs["gaps"][gap_id] for gap_id in research_gap_ids],
        "source_boundary_run_id": inputs["config"]["source_run_id"],
        "source_adjudication_sha256": inputs["config"]["source_adjudication_sha256"],
        "source_review_id": inputs["config"]["source_review_id"],
        "source_review_output_sha256": inputs["config"]["source_review_output_sha256"],
    }


def compile_boundary_activation(
    activation_config_path: Path,
    *,
    execution_commit: str,
    root: Path = ROOT,
) -> dict[str, Any]:
    if FULL_GIT_COMMIT.fullmatch(execution_commit) is None:
        raise ValueError("execution_commit must be a complete lowercase hexadecimal Git commit")
    inputs = _prepare_inputs(activation_config_path, root=root)
    indexes = _source_indexes(inputs["pack"])
    activation_id = inputs["activation_id"]
    events: list[dict[str, Any]] = []
    proposal_markets: dict[str, str] = {}

    for ordinal, activation in enumerate(inputs["config"]["activate_proposals"], 1):
        proposal = inputs["proposals"][activation["proposal_id"]]
        event_id = (
            f"{activation_id}:{ordinal:02d}:create-market:"
            + proposal["proposal_id"].removeprefix("proposal:")
        )
        market_id = market_id_from_creation(event_id)
        proposal_markets[proposal["proposal_id"]] = market_id
        evidence_ids = [
            *proposal["supporting_evidence_ids"],
            *proposal["counterevidence_ids"],
        ]
        source_record_ids = _source_records(
            evidence_ids, proposal["candidate_market_ids"], indexes
        )
        event = _event_common(
            inputs,
            proposal,
            event_id=event_id,
            activation_status=activation["activation_status"],
            research_gap_ids=activation["research_gap_ids"],
            source_record_ids=source_record_ids,
        )
        event.update(
            {
                "event_type": "create_market",
                "output_market_ids": [market_id],
                "relationship_type": None,
                "market_version": {
                    "market_version_id": market_version_id(event_id, market_id),
                    "market_id": market_id,
                    "canonical_name": proposal["canonical_name"],
                    "definition": proposal["definition"],
                    "boundary": proposal["boundary"],
                    "buyer": proposal["buyer"],
                    "job_to_be_done": proposal["job_to_be_done"],
                    "delivery_model": proposal["delivery_model"],
                    "workforce_model": proposal["workforce_model"],
                    "economics_risk": proposal["economics_risk"],
                    "acquisition_universe": proposal["acquisition_universe"],
                    "ambient_ai_workflow": proposal["ambient_ai_workflow"],
                    "parent_market_id": None,
                    "aliases": proposal["aliases"],
                    "explicit_exclusions": proposal["explicit_exclusions"],
                    "source_record_ids": source_record_ids,
                    "mapping_event_ids": [],
                    "candidate_market_ids": proposal["candidate_market_ids"],
                    "evidence_by_dimension": proposal["evidence_by_dimension"],
                    "confidence_by_dimension": proposal["confidence_by_dimension"],
                    "proposal_id": proposal["proposal_id"],
                    "activation_status": activation["activation_status"],
                    "research_gap_ids": activation["research_gap_ids"],
                    "supporting_evidence_ids": proposal["supporting_evidence_ids"],
                    "counterevidence_ids": proposal["counterevidence_ids"],
                    "source_boundary_run_id": inputs["config"]["source_run_id"],
                    "source_review_id": inputs["config"]["source_review_id"],
                },
            }
        )
        errors = validate_event(event)
        if errors:
            raise ValueError(f"compiled invalid create event {event_id}: {errors}")
        events.append(event)

    offset = len(events)
    for ordinal, activation in enumerate(
        inputs["config"]["activate_identity_mappings"], offset + 1
    ):
        key = (activation["identity_id"], activation["proposal_id"])
        disposition = inputs["mapping_dispositions"][key]
        proposal = inputs["proposals"][activation["proposal_id"]]
        event_id = (
            f"{activation_id}:{ordinal:02d}:map:"
            + activation["identity_id"].replace(":", "-")
        )
        evidence_ids = [
            *disposition["supporting_evidence_ids"],
            *disposition["counterevidence_ids"],
        ]
        source_record_ids = _source_records(
            evidence_ids, [activation["identity_id"]], indexes
        )
        event = _event_common(
            inputs,
            proposal,
            event_id=event_id,
            activation_status=activation["activation_status"],
            research_gap_ids=activation["research_gap_ids"],
            source_record_ids=source_record_ids,
        )
        event.update(
            {
                "event_type": "map",
                "input_candidate_market_ids": [],
                "output_market_ids": [proposal_markets[activation["proposal_id"]]],
                "relationship_type": disposition["relationship_type"],
                "supporting_record_ids": disposition["supporting_evidence_ids"],
                "counterevidence_record_ids": disposition["counterevidence_ids"],
                "identity_id": activation["identity_id"],
                "identity_disposition": disposition["disposition"],
                "identity_evidence_label": disposition["evidence_label"],
                "identity_confidence": disposition["confidence"],
                "identity_rationale": disposition["rationale"],
            }
        )
        errors = validate_event(event)
        if errors:
            raise ValueError(f"compiled invalid mapping event {event_id}: {errors}")
        events.append(event)

    if any(event["event_type"] == "reject_candidate" for event in events):
        raise ValueError("family-local non-mappings cannot emit reject_candidate events")
    projection = project_graph(
        events,
        as_of=inputs["config"]["recorded_at_utc"],
        known_source_record_ids=indexes["known_source_record_ids"],
        known_candidate_market_ids=indexes["known_candidate_market_ids"],
        source_hashes=inputs["pack"]["metadata"]["source_artifact_hashes"],
        config_hash=inputs["config_sha256"],
        code_hash=execution_commit,
    )
    return {
        "activation_id": activation_id,
        "activation_config_sha256": inputs["config_sha256"],
        "events": events,
        "projection": projection,
        "source_boundary_run_id": inputs["config"]["source_run_id"],
        "source_review_id": inputs["config"]["source_review_id"],
        "proposal_market_ids": dict(sorted(proposal_markets.items())),
    }


def run_boundary_activation(
    activation_config_path: Path,
    *,
    output_root: Path | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    if not _git_worktree_clean(root):
        raise RuntimeError(
            "boundary activation requires a clean Git worktree so its exact commit "
            "contains the executed compiler and configuration"
        )
    execution_commit = _git_head(root)
    if execution_commit is None:
        raise RuntimeError("cannot determine exact Git commit for activation")
    compiled = compile_boundary_activation(
        activation_config_path, execution_commit=execution_commit, root=root
    )
    destination = output_root or root / "data/market_graph/activations"
    activation_dir = destination / compiled["activation_id"]
    activation_dir.mkdir(parents=True, exist_ok=False)
    events_path = activation_dir / "events.json"
    projection_path = activation_dir / "projection.json"
    events_path.write_text(
        json.dumps(compiled["events"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    projection_path.write_text(
        json.dumps(compiled["projection"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt = {
        "schema_version": 1,
        "activation_id": compiled["activation_id"],
        "activation_config_sha256": compiled["activation_config_sha256"],
        "activation_execution_commit": execution_commit,
        "recorded_at_utc": compiled["projection"]["as_of"],
        "source_boundary_run_id": compiled["source_boundary_run_id"],
        "source_review_id": compiled["source_review_id"],
        "events_sha256": canonical_sha256(compiled["events"]),
        "projection_sha256": canonical_sha256(compiled["projection"]),
        "graph_version_id": compiled["projection"]["graph_version_id"],
        "event_ids": [event["event_id"] for event in compiled["events"]],
        "proposal_market_ids": compiled["proposal_market_ids"],
        "event_counts": {
            event_type: sum(
                1 for event in compiled["events"] if event["event_type"] == event_type
            )
            for event_type in ("create_market", "map", "reject_candidate")
        },
        "open_research_gap_ids": sorted(
            {
                gap_id
                for event in compiled["events"]
                for gap_id in event["research_gap_ids"]
            }
        ),
        "model_invoked": False,
        "status": "activated_approved_boundary",
    }
    (activation_dir / "activation-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"activation_dir": str(activation_dir), **receipt}


def validate_boundary_activation(
    activation_dir: Path,
    activation_config_path: Path,
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        receipt = _load_object(activation_dir / "activation-receipt.json")
        events = _load_array(activation_dir / "events.json")
        projection = _load_object(activation_dir / "projection.json")
        execution_commit = receipt["activation_execution_commit"]
        if not _git_commit_exists(root, execution_commit):
            raise ValueError(
                "activation_execution_commit is not a resolvable full Git commit"
            )
        compiled = compile_boundary_activation(
            activation_config_path,
            execution_commit=execution_commit,
            root=root,
        )
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "valid": False,
            "errors": [f"activation cannot replay: {error}"],
            "activation_id": activation_dir.name,
        }
    if events != compiled["events"]:
        errors.append("persisted events do not match deterministic compilation")
    if projection != compiled["projection"]:
        errors.append("persisted projection does not match deterministic compilation")
    expected = {
        "activation_id": compiled["activation_id"],
        "activation_config_sha256": compiled["activation_config_sha256"],
        "activation_execution_commit": execution_commit,
        "recorded_at_utc": projection["as_of"],
        "source_boundary_run_id": compiled["source_boundary_run_id"],
        "source_review_id": compiled["source_review_id"],
        "events_sha256": canonical_sha256(events),
        "projection_sha256": canonical_sha256(projection),
        "graph_version_id": projection["graph_version_id"],
        "event_ids": [event["event_id"] for event in events],
        "proposal_market_ids": compiled["proposal_market_ids"],
        "event_counts": {
            event_type: sum(1 for event in events if event["event_type"] == event_type)
            for event_type in ("create_market", "map", "reject_candidate")
        },
        "model_invoked": False,
        "status": "activated_approved_boundary",
    }
    for field, expected_value in expected.items():
        if receipt.get(field) != expected_value:
            errors.append(f"activation receipt {field} mismatch")
    expected_gaps = sorted(
        {gap_id for event in events for gap_id in event.get("research_gap_ids", [])}
    )
    if receipt.get("open_research_gap_ids") != expected_gaps:
        errors.append("activation receipt open_research_gap_ids mismatch")
    if activation_dir.name != compiled["activation_id"]:
        errors.append("activation directory name does not match activation_id")
    return {
        "valid": not errors,
        "errors": sorted(set(errors)),
        "activation_id": compiled["activation_id"],
        "graph_version_id": projection.get("graph_version_id"),
        "event_counts": expected["event_counts"],
        "market_count": len(projection.get("markets", [])),
        "open_research_gap_ids": expected_gaps,
    }
