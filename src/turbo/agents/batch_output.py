"""Standalone structural output validation over regenerated, immutable V2 inputs.

No model transport, ledger settlement, graph activation, or research acceptance is
performed. A caller-supplied context is never an authority for the public validator.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from turbo.agents.batch_authorization import _scope, canonical_bytes
from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT

SCHEMA_PATH = "schemas/batch-primary-output.schema.json"
PROMPT_PATH = "prompts/universe/batch-primary-v1.md"
DEFAULT_MAX_OUTPUT_BYTES = 1_000_000
DEFAULT_MAX_CONTEXT_BYTES = 100_000_000
DIMENSIONS = ("buyer", "job", "delivery", "workforce", "economics_risk", "acquisition_universe", "ambient_ai_workflow")
SECTIONS = ("manual_definitions", "manual_index_entries", "manual_index_missing_identity_ids",
            "identity_cards", "source_record_cards", "mapping_cards", "required_candidate_cards",
            "context_candidate_cards", "context_edges", "graph_context/mappings", "graph_context/markets")


def _json_values(value: Any) -> None:
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        for child in value.values(): _json_values(child)
    elif isinstance(value, list):
        for child in value: _json_values(child)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
    elif value is not None and type(value) not in (str, int, bool):
        raise ValueError("value is not a JSON value")


def _limit(value: int, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(name + " must be a positive integer")


def _bindings(request_id: str, invocation_id: str) -> None:
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", request_id):
        raise ValueError("invalid expected request ID")
    if not isinstance(invocation_id, str) or not re.fullmatch(r"invocation:[0-9a-f]{24}", invocation_id):
        raise ValueError("invalid expected invocation ID")


def _strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return set().union(*(_strings(child) for child in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_strings(child) for child in value)) if value else set()
    return set()


def _unique(values: list[str], name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError("duplicate " + name + " in verified input")


def _family_view(pack: dict[str, Any], binding: dict[str, str]) -> dict[str, Any]:
    family_id = binding["family_id"]
    scope = pack["scope"]
    required_ids = scope["required_disposition_identity_ids"]
    context_ids = scope["context_only_identity_ids"]
    candidate_ids = scope["required_prior_candidate_ids"]
    context_candidates = [item["candidate_market_id"] for item in pack["context_candidate_cards"]]
    for name, values in (("required identities", required_ids), ("context identities", context_ids),
                         ("required candidates", candidate_ids), ("context candidates", context_candidates)):
        _unique(values, name)
    if set(required_ids) & set(context_ids) or set(candidate_ids) & set(context_candidates):
        raise ValueError("required/context scope overlap in verified input")
    known_subjects = set(required_ids + context_ids + candidate_ids + context_candidates)
    record_owners: dict[str, set[str]] = {}
    for card in pack["identity_cards"] + pack["required_candidate_cards"] + pack["context_candidate_cards"]:
        subject = card.get("identity_id", card.get("candidate_market_id"))
        for record in card["source_record_ids"]:
            record_owners.setdefault(record, set()).add(subject)
    catalog = []
    sections = SECTIONS + tuple(s for s in ("supplemental_sources", "supplemental_claims", "supplemental_gaps") if s in pack)
    for section in sections:
        values: Any = pack
        for component in section.split("/"):
            values = values[component]
        for index, value in enumerate(values):
            pointer = "/" + section + "/" + str(index)
            item_hash = canonical_sha256(value)
            subjects = (set(value["subject_ids"]) if section.startswith("supplemental_")
                        else known_subjects & _strings(value))
            if section == "source_record_cards":
                subjects |= record_owners.get(value["record_id"], set())
            reference = {"family_id": family_id, "pack_sha256": pack["metadata"]["pack_sha256"],
                         "json_pointer": pointer, "item_sha256": item_hash}
            catalog.append({"evidence_id": "evidence:" + canonical_sha256(reference),
                "json_pointer": pointer, "item_sha256": item_hash,
                "subject_ids": sorted(subjects), "value": value})
    evidence_ids = [item["evidence_id"] for item in catalog]
    _unique(evidence_ids, "evidence references")
    namespace = hashlib.sha256(family_id.encode()).hexdigest()[:16]
    graph_ids = [item["market_id"] for item in pack["graph_context"]["markets"]]
    _unique(graph_ids, "graph market IDs")
    return {"family_id": family_id, "preparation_id": binding["preparation_id"],
        "input_pack_sha256": pack["metadata"]["pack_sha256"],
        "required_identity_ids": required_ids, "context_identity_ids": context_ids,
        "required_candidate_ids": candidate_ids, "context_candidate_ids": context_candidates,
        "proposal_id_prefix": "proposal:" + namespace + ":", "gap_id_prefix": "gap:" + namespace + ":",
        "graph_market_ids": graph_ids, "pack_metadata": pack["metadata"],
        "scope": scope, "counts": pack["counts"], "evidence_catalog": catalog}


def build_batch_context(
    preparation_dirs: Iterable[Path], *, request_id: str, invocation_id: str,
    root: Path = ROOT, max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    max_context_bytes: int = DEFAULT_MAX_CONTEXT_BYTES,
) -> dict[str, Any]:
    """Regenerate every preparation before exposing a deterministic evidence view."""
    _bindings(request_id, invocation_id)
    _limit(max_output_bytes, "max_output_bytes"); _limit(max_context_bytes, "max_context_bytes")
    paths = [Path(path) for path in preparation_dirs]
    bindings, batch_id = _scope(paths, root)
    families = []
    for path, binding in zip(paths, bindings):
        raw = (path / "family-evidence-pack-v2.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != binding["pack_file_sha256"]:
            raise ValueError("preparation changed while deriving batch context")
        pack = json.loads(raw)
        _json_values(pack)
        families.append(_family_view(pack, binding))
    context = {"schema_version": 1, "contract_version": "batch-primary-v1", "role_id": "batch_primary",
        "request_id": request_id, "invocation_id": invocation_id, "batch_id": batch_id,
        "output_schema_sha256": hashlib.sha256((root / SCHEMA_PATH).read_bytes()).hexdigest(),
        "prompt_sha256": hashlib.sha256((root / PROMPT_PATH).read_bytes()).hexdigest(),
        "input_bindings": bindings, "limits": {"max_output_bytes": max_output_bytes, "max_context_bytes": max_context_bytes},
        "families": families, "model_invoked": False}
    context["context_sha256"] = canonical_sha256(context)
    if len(canonical_bytes(context)) > max_context_bytes:
        raise ValueError("batch context exceeds max_context_bytes")
    return context


def _validate_against_context(output: Any, context: dict[str, Any], *, root: Path = ROOT) -> list[str]:
    """Internal pure checks. Public acceptance always regenerates this context."""
    errors: list[str] = []
    try:
        _json_values(output)
        if len(canonical_bytes(output)) > context["limits"]["max_output_bytes"]:
            return ["output exceeds max_output_bytes"]
        schema = json.loads((root / SCHEMA_PATH).read_text())
        errors = sorted(f"schema:{'/'.join(map(str, error.absolute_path)) or '<root>'}:{error.message}"
                        for error in Draft202012Validator(schema).iter_errors(output))
        if errors:
            return errors
        if type(output["schema_version"]) is not int:
            return ["schema_version must be an integer"]
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as error:
        return ["output cannot be validated: " + str(error)]
    for key in ("contract_version", "role_id", "request_id", "invocation_id", "context_sha256",
                "output_schema_sha256", "prompt_sha256"):
        if output[key] != context[key]:
            errors.append(key + " does not match the expected request context")
    expected_families = context["families"]
    if [item["family_id"] for item in output["families"]] != [item["family_id"] for item in expected_families]:
        errors.append("families must match exact manifest-ordered request scope")
        return errors
    for family, expected in zip(output["families"], expected_families):
        owner = family["family_id"]
        for key in ("preparation_id", "input_pack_sha256"):
            if family[key] != expected[key]:
                errors.append(owner + ": " + key + " mismatch")
        evidence = {row["evidence_id"]: row for row in expected["evidence_catalog"]}
        required_ids = set(expected["required_identity_ids"])
        required_candidates = set(expected["required_candidate_ids"])
        proposals = {row["proposal_id"]: row for row in family["proposed_markets"]}
        gaps = {row["gap_id"]: row for row in family["research_gaps"]}
        if len(proposals) != len(family["proposed_markets"]):
            errors.append(owner + ": duplicate proposal IDs")
        if len(gaps) != len(family["research_gaps"]):
            errors.append(owner + ": duplicate gap IDs")

        def citations(item: dict[str, Any], location: str, subject: str | None = None) -> None:
            for field in ("supporting_evidence_ids", "counterevidence_ids"):
                if set(item[field]) - evidence.keys():
                    errors.append(owner + ": " + location + " cites unknown or other-family evidence")
            if set(item["supporting_evidence_ids"]) & set(item["counterevidence_ids"]):
                errors.append(owner + ": " + location + " uses the same supporting and counter evidence")
            if subject is not None and not any(subject in evidence[ref]["subject_ids"]
                    for ref in item["supporting_evidence_ids"] if ref in evidence):
                errors.append(owner + ": " + location + " lacks supporting evidence for its own subject")

        for proposal_id, proposal in proposals.items():
            if not proposal_id.startswith(expected["proposal_id_prefix"]):
                errors.append(owner + ": proposal ID is outside its family namespace")
            if set(proposal["related_graph_market_ids"]) - set(expected["graph_market_ids"]):
                errors.append(owner + ": proposal references unknown graph markets")
            citations(proposal, proposal_id)
            for dimension in DIMENSIONS:
                citations(proposal["dimensions"][dimension], proposal_id + "/" + dimension)
        for gap_id, gap in gaps.items():
            if not gap_id.startswith(expected["gap_id_prefix"]):
                errors.append(owner + ": gap ID is outside its family namespace")
            if (set(gap["affected_identity_ids"]) - required_ids
                    or set(gap["affected_candidate_ids"]) - required_candidates):
                errors.append(owner + ": gap names a subject outside the required family scope")
            if not gap["affected_identity_ids"] and not gap["affected_candidate_ids"]:
                errors.append(owner + ": gap must name an affected required subject")
            citations(gap, gap_id)
            for subject in gap["affected_identity_ids"] + gap["affected_candidate_ids"]:
                citations(gap, gap_id, subject)

        used_proposals: set[str] = set()
        for list_key, id_key, required in (("identity_dispositions", "identity_id", required_ids),
                                         ("candidate_dispositions", "candidate_market_id", required_candidates)):
            rows = family[list_key]
            actual = [row[id_key] for row in rows]
            if len(actual) != len(set(actual)) or set(actual) != required:
                errors.append(owner + ": " + list_key + " must cover every required subject exactly once")
            for row in rows:
                subject, outcome, references = row[id_key], row["disposition"], row["proposal_ids"]
                citations(row, subject, subject)
                if set(references) - proposals.keys():
                    errors.append(owner + ": disposition references unknown or other-family proposals")
                used_proposals.update(references)
                if outcome in {"adopt", "change", "merge_input"}:
                    valid_count = len(references) == 1
                elif outcome == "split_input":
                    valid_count = len(references) >= 2
                elif outcome in {"map_to_proposals", "provisional_map_to_proposals"}:
                    valid_count = bool(references)
                else:
                    valid_count = not references
                if not valid_count:
                    errors.append(owner + ": disposition/proposal cardinality mismatch for " + subject)
                unknown_dimension = any(
                    any(d["evidence_label"] == "unknown" for d in proposals[ref]["dimensions"].values())
                    for ref in references if ref in proposals)
                needs_gap = outcome in {"unresolved", "provisional_map_to_proposals"} or row["evidence_label"] == "unknown" or unknown_dimension
                gap = gaps.get(row["gap_id"])
                if needs_gap and gap is None:
                    errors.append(owner + ": unresolved/provisional/unknown judgment requires an applicable gap")
                if row["gap_id"] is not None:
                    affected_key = "affected_identity_ids" if id_key == "identity_id" else "affected_candidate_ids"
                    if gap is None or subject not in gap[affected_key]:
                        errors.append(owner + ": disposition gap does not apply to its subject")
        if proposals.keys() - used_proposals:
            errors.append(owner + ": unreferenced proposal is outside required dispositions")
    return errors


def validate_batch_output(
    output: Any, preparation_dirs: Iterable[Path], *, expected_request_id: str,
    expected_invocation_id: str, root: Path = ROOT,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    max_context_bytes: int = DEFAULT_MAX_CONTEXT_BYTES,
) -> dict[str, Any]:
    """Validate against independent request parameters and freshly verified inputs."""
    try:
        context = build_batch_context(preparation_dirs, request_id=expected_request_id,
            invocation_id=expected_invocation_id, root=root, max_output_bytes=max_output_bytes,
            max_context_bytes=max_context_bytes)
        errors = _validate_against_context(output, context, root=root)
        return {"valid": not errors, "errors": errors, "context_sha256": context["context_sha256"],
                "structural_validation_only": True, "model_invoked": False}
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        return {"valid": False, "errors": ["batch context cannot be verified: " + str(error)],
                "structural_validation_only": True, "model_invoked": False}


def _strict_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON object key: " + key)
            result[key] = value
        return result
    def constant(value: str) -> None:
        raise ValueError("nonfinite JSON constant: " + value)
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    _json_values(value)
    return value


def validate_batch_output_file(
    output_path: Path, preparation_dirs: Iterable[Path], *, expected_request_id: str,
    expected_invocation_id: str, root: Path = ROOT,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    max_context_bytes: int = DEFAULT_MAX_CONTEXT_BYTES,
) -> dict[str, Any]:
    try:
        _limit(max_output_bytes, "max_output_bytes")
        with Path(output_path).open("rb") as handle:
            raw = handle.read(max_output_bytes + 1)
        if len(raw) > max_output_bytes:
            raise ValueError("raw output exceeds max_output_bytes")
        output = _strict_json(raw)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as error:
        return {"valid": False, "errors": ["output file cannot be parsed: " + str(error)],
                "structural_validation_only": True, "model_invoked": False}
    return validate_batch_output(output, preparation_dirs, expected_request_id=expected_request_id,
        expected_invocation_id=expected_invocation_id, root=root, max_output_bytes=max_output_bytes,
        max_context_bytes=max_context_bytes)
