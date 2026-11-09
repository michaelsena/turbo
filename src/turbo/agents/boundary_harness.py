from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from turbo.pipeline_paths import ROOT


def canonical_sha256(value: object) -> str:
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def load_specialist_schema(*, root: Path = ROOT) -> dict[str, Any]:
    return json.loads(
        (root / "schemas/boundary-specialist-output.schema.json").read_text(
            encoding="utf-8"
        )
    )


def load_adjudication_schema(*, root: Path = ROOT) -> dict[str, Any]:
    """Return a self-contained adjudication schema for validators and model CLIs."""

    specialist = load_specialist_schema(root=root)
    adjudication = json.loads(
        (root / "schemas/boundary-adjudication-output.schema.json").read_text(
            encoding="utf-8"
        )
    )
    adjudication["$defs"] = specialist["$defs"]
    for field, definition in (
        ("proposed_markets", "proposedMarket"),
        ("identity_dispositions", "identityDisposition"),
        ("candidate_dispositions", "candidateDisposition"),
        ("research_gaps", "researchGap"),
    ):
        adjudication["properties"][field]["items"] = {"$ref": f"#/$defs/{definition}"}
    return adjudication


def _schema_errors(output: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema)
    return sorted(
        f"schema:{'/'.join(str(part) for part in error.absolute_path) or '<root>'}:"
        f"{error.message}"
        for error in validator.iter_errors(output)
    )


def validate_boundary_output(
    output: dict[str, Any],
    pack: dict[str, Any],
    *,
    expected_role: str,
    specialist_outputs: list[dict[str, Any]] | None = None,
    root: Path = ROOT,
) -> list[str]:
    """Validate schema plus the closed-world invariants schemas cannot express."""

    is_adjudication = expected_role == "adjudicator"
    schema = (
        load_adjudication_schema(root=root)
        if is_adjudication
        else load_specialist_schema(root=root)
    )
    errors = _schema_errors(output, schema)
    if errors:
        return errors

    metadata = pack["metadata"]
    scope = pack["scope"]
    if output["family_id"] != metadata["family_id"]:
        errors.append("family_id does not match the frozen pack")
    if output["input_pack_sha256"] != metadata["pack_sha256"]:
        errors.append("input_pack_sha256 does not match the frozen pack")
    if output["role_id"] != expected_role:
        errors.append(f"role_id must equal {expected_role}")

    evidence_ids = {item["evidence_id"] for item in pack["evidence_catalog"]}
    required_identity_ids = set(scope["required_disposition_identity_ids"])
    context_identity_ids = set(scope["context_only_identity_ids"])
    known_identity_ids = required_identity_ids | context_identity_ids | set(
        scope["linked_trilateral_product_identity_ids"]
    )
    known_candidate_ids = {
        item["candidate_market_id"]
        for item in pack["retrieved_prior_candidate_details"]
    }

    proposal_ids = [item["proposal_id"] for item in output["proposed_markets"]]
    proposal_id_set = set(proposal_ids)
    if len(proposal_ids) != len(proposal_id_set):
        errors.append("proposed_markets contains duplicate proposal IDs")

    gap_ids = [item["gap_id"] for item in output["research_gaps"]]
    gap_id_set = set(gap_ids)
    if len(gap_ids) != len(gap_id_set):
        errors.append("research_gaps contains duplicate gap IDs")

    dispositions = output["identity_dispositions"]
    disposition_ids = [item["identity_id"] for item in dispositions]
    if len(disposition_ids) != len(set(disposition_ids)):
        errors.append("identity_dispositions contains duplicate identity IDs")
    missing_identities = required_identity_ids - set(disposition_ids)
    extra_identities = set(disposition_ids) - required_identity_ids
    if missing_identities:
        errors.append(f"missing required identity dispositions: {sorted(missing_identities)}")
    if extra_identities:
        errors.append(f"unexpected identity dispositions: {sorted(extra_identities)}")

    candidate_dispositions = output["candidate_dispositions"]
    disposed_candidate_ids = [item["candidate_market_id"] for item in candidate_dispositions]
    if len(disposed_candidate_ids) != len(set(disposed_candidate_ids)):
        errors.append("candidate_dispositions contains duplicate candidate IDs")
    missing_candidates = known_candidate_ids - set(disposed_candidate_ids)
    extra_candidates = set(disposed_candidate_ids) - known_candidate_ids
    if missing_candidates:
        errors.append(f"missing candidate dispositions: {sorted(missing_candidates)}")
    if extra_candidates:
        errors.append(f"unexpected candidate dispositions: {sorted(extra_candidates)}")

    def check_evidence(owner: str, item: dict[str, Any]) -> None:
        for field in ("supporting_evidence_ids", "counterevidence_ids"):
            unknown = set(item[field]) - evidence_ids
            if unknown:
                errors.append(f"{owner} cites unknown {field}: {sorted(unknown)}")

    for proposal in output["proposed_markets"]:
        check_evidence(f"proposal {proposal['proposal_id']}", proposal)
        unknown_candidates = set(proposal["candidate_market_ids"]) - known_candidate_ids
        if unknown_candidates:
            errors.append(
                f"proposal {proposal['proposal_id']} cites unknown candidates: "
                f"{sorted(unknown_candidates)}"
            )

    for disposition in dispositions:
        identity_id = disposition["identity_id"]
        check_evidence(f"identity disposition {identity_id}", disposition)
        proposal_id = disposition["proposal_id"]
        disposition_name = disposition["disposition"]
        is_map = disposition_name in {"map_to_proposal", "provisional_map_to_proposal"}
        if is_map:
            if proposal_id not in proposal_id_set:
                errors.append(
                    f"identity disposition {identity_id} must reference a known proposal"
                )
            if disposition["relationship_type"] is None:
                errors.append(
                    f"identity disposition {identity_id} requires relationship_type"
                )
        elif proposal_id is not None:
            errors.append(
                f"non-mapping identity disposition {identity_id} must use null proposal_id"
            )
        is_provisional = disposition_name.startswith("provisional_")
        if is_provisional and disposition["gap_id"] not in gap_id_set:
            errors.append(
                f"provisional identity disposition {identity_id} must reference a known gap"
            )
        if not is_provisional and disposition["gap_id"] is not None:
            errors.append(
                f"non-provisional identity disposition {identity_id} must use null gap_id"
            )

    for candidate in candidate_dispositions:
        check_evidence(
            f"candidate disposition {candidate['candidate_market_id']}", candidate
        )
        unknown_proposals = set(candidate["proposal_ids"]) - proposal_id_set
        if unknown_proposals:
            errors.append(
                f"candidate disposition {candidate['candidate_market_id']} cites unknown "
                f"proposals: {sorted(unknown_proposals)}"
            )

    for gap in output["research_gaps"]:
        check_evidence(f"research gap {gap['gap_id']}", gap)
        unknown_identities = set(gap["affected_identity_ids"]) - known_identity_ids
        if unknown_identities:
            errors.append(
                f"research gap {gap['gap_id']} cites unknown identities: "
                f"{sorted(unknown_identities)}"
            )

    if is_adjudication:
        if specialist_outputs is None or len(specialist_outputs) != 2:
            errors.append("adjudication validation requires exactly two specialist outputs")
        else:
            specialist_roles = [item["role_id"] for item in specialist_outputs]
            if set(specialist_roles) != {"specialist-a", "specialist-b"}:
                errors.append("adjudication inputs must be specialist-a and specialist-b")
            if len({item["invocation_id"] for item in specialist_outputs}) != 2:
                errors.append("specialists must have distinct invocation IDs")
            expected_hashes = {canonical_sha256(item) for item in specialist_outputs}
            if set(output["specialist_output_sha256"]) != expected_hashes:
                errors.append("specialist_output_sha256 does not match specialist inputs")
            resolution_roles = [item["role_id"] for item in output["specialist_resolution"]]
            if len(resolution_roles) != 2 or set(resolution_roles) != {
                "specialist-a",
                "specialist-b",
            }:
                errors.append(
                    "specialist_resolution must resolve specialist-a and specialist-b exactly once"
                )

    return sorted(set(errors))
