from __future__ import annotations

import gzip
import hashlib
import json
import re
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT
from turbo.universe.boundary_pack import build_boundary_pack, _load_verified_run_artifact


FULL_GIT_COMMIT = re.compile(r"[0-9a-f]{40}")


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _canonical_gzip(value: object) -> bytes:
    return gzip.compress(_canonical_bytes(value), compresslevel=9, mtime=0)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_worktree_clean(root: Path) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0 and not completed.stdout.strip()


def _git_head(root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and FULL_GIT_COMMIT.fullmatch(value) else None


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


def _rendezvous_owner(subject_id: str, family_ids: Iterable[str]) -> str:
    choices = sorted(set(family_ids))
    if not choices:
        raise ValueError(f"cannot assign {subject_id} without a family appearance")
    return max(
        choices,
        key=lambda family_id: hashlib.sha256(
            f"turbo-family-owner-v1\0{subject_id}\0{family_id}".encode("utf-8")
        ).digest(),
    )


def _chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _family_id(code: str) -> str:
    return f"family:naics-2022:{code}"


def _coverage_family_id(kind: str, prefix: str, ordinal: int) -> str:
    return f"family:coverage:{kind}:{prefix}:{ordinal:03d}"


def _assignment(
    *,
    identity: dict[str, Any],
    role: str,
    owner: str,
    appearances: Iterable[str],
    reason: str,
    supporting_relationship_ids: Iterable[str] = (),
) -> dict[str, Any]:
    appearance_ids = sorted(set(appearances))
    if owner not in appearance_ids:
        appearance_ids.append(owner)
        appearance_ids.sort()
    fingerprint = {
        "identity_id": identity["identity_id"],
        "assignment_role": role,
        "owner_family_id": owner,
        "appearance_family_ids": appearance_ids,
    }
    return {
        "assignment_id": "assignment:" + canonical_sha256(fingerprint)[:24],
        "identity_id": identity["identity_id"],
        "identity_type": identity["identity_type"],
        "source_code": identity["source_code"],
        "assignment_role": role,
        "owner_family_id": owner,
        "appearance_family_ids": appearance_ids,
        "reason_code": reason,
        "supporting_relationship_ids": sorted(set(supporting_relationship_ids)),
        "interpretation_boundary": (
            "Administrative review ownership only; not evidence of market equivalence, "
            "market membership, eligibility, attractiveness, or economic primacy."
        ),
    }


def _relationship_id(kind: str, *parts: str) -> str:
    return f"relationship:{kind}:" + canonical_sha256(parts)[:24]


def _sorted_observations(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(values, key=canonical_sha256)


def _validate_config(config: dict[str, Any]) -> None:
    schema = _object(ROOT / "schemas" / "family-partition-config.schema.json")
    schema_errors = sorted(
        error.message for error in Draft202012Validator(schema).iter_errors(config)
    )
    if schema_errors:
        raise ValueError("invalid family partition config: " + "; ".join(schema_errors))
    if config.get("schema_version") != 1:
        raise ValueError("family partition config schema_version must equal 1")
    if config.get("method_version") != "naics-leaf-rendezvous-v1":
        raise ValueError("unsupported family partition method_version")
    required_prohibitions = {
        "target-universe filtering",
        "market evaluation or scoring",
        "company discovery or evaluation",
        "investment-attractiveness scheduling",
        "model invocation",
    }
    if set(config.get("prohibited_actions", [])) != required_prohibitions:
        raise ValueError("family partition prohibited_actions mismatch")
    limits = config.get("limits", {})
    for field in (
        "max_required_identities_per_family",
        "max_context_identities_per_shard",
        "max_families_per_batch",
        "max_required_identities_per_batch",
        "max_required_candidates_per_batch",
    ):
        if not isinstance(limits.get(field), int) or limits[field] <= 0:
            raise ValueError(f"family partition limit {field} must be positive")


def compile_family_plan(
    config_path: Path,
    *,
    execution_commit: str,
    root: Path = ROOT,
) -> dict[str, Any]:
    if FULL_GIT_COMMIT.fullmatch(execution_commit) is None:
        raise ValueError("execution_commit must be a complete lowercase hexadecimal Git commit")
    config = _object(config_path)
    _validate_config(config)
    run_id = config["source_run_id"]
    run_dir = root / "data" / "runs" / run_id
    receipt = _object(run_dir / "run-receipt.json")
    if receipt.get("run_id") != run_id:
        raise ValueError("family plan source run does not match run receipt")
    reconciliation = _load_verified_run_artifact(
        run_dir, receipt, "multisource-reconciliation.json.gz"
    )
    relationships = _load_verified_run_artifact(
        run_dir, receipt, "identity-relationships.json.gz"
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
    if set(identities) != set(mappings):
        raise ValueError("source identities and reconciliation mappings disagree")

    naics_ids = {
        identity_id for identity_id, item in identities.items() if item["identity_type"] == "naics"
    }
    leaf_ids = {
        identity_id
        for identity_id in naics_ids
        if len(identities[identity_id]["source_code"]) == 6
    }
    aggregate_naics_ids = naics_ids - leaf_ids
    leaf_family = {
        identity_id: _family_id(identities[identity_id]["source_code"])
        for identity_id in leaf_ids
    }

    appearances: dict[str, set[str]] = defaultdict(set)
    relationship_ids: dict[str, set[str]] = defaultdict(set)
    for edge in relationships["industry_product_relationships"]:
        industry_id = edge["industry_identity_id"]
        product_id = edge["product_identity_id"]
        if industry_id not in leaf_family:
            raise ValueError(f"industry-product edge has non-leaf industry {industry_id}")
        family_id = leaf_family[industry_id]
        appearances[product_id].add(family_id)
        relationship_ids[product_id].add(
            _relationship_id("industry-product", industry_id, product_id)
        )

    collection_ids = {
        identity_id
        for identity_id, item in identities.items()
        if item["identity_type"] == "napcs-collection"
    }
    linked_collection_ids = set(appearances) & collection_ids
    unlinked_collection_ids = collection_ids - linked_collection_ids
    limits = config["limits"]
    unlinked_by_prefix: dict[str, list[str]] = defaultdict(list)
    for identity_id in sorted(unlinked_collection_ids):
        unlinked_by_prefix[identities[identity_id]["source_code"][:2]].append(identity_id)
    unlinked_owner: dict[str, str] = {}
    for prefix, values in sorted(unlinked_by_prefix.items()):
        for ordinal, shard in enumerate(
            _chunked(values, limits["max_required_identities_per_family"]), 1
        ):
            family_id = _coverage_family_id("napcs-collection", prefix, ordinal)
            for identity_id in shard:
                unlinked_owner[identity_id] = family_id

    pilot = config["pilot_regression"]
    pilot_seed_id = pilot["seed_identity_id"]
    pilot_family_id = leaf_family[pilot_seed_id]
    pilot_config_path = root / pilot["source_family_config"]
    pilot_pack = build_boundary_pack(pilot_config_path, root=root)
    if pilot_pack["metadata"]["pack_sha256"] != pilot["source_pack_sha256"]:
        raise ValueError("pilot regression pack hash mismatch")
    pilot_required_ids = set(
        pilot_pack["scope"]["required_disposition_identity_ids"]
    )
    pilot_context_ids = set(pilot_pack["scope"]["context_only_identity_ids"])
    pilot_context_ids.update(
        pilot_pack["scope"]["linked_trilateral_product_identity_ids"]
    )
    pilot_context_ids.update(
        subject_id
        for evidence in pilot_pack["evidence_catalog"]
        if evidence["context_only"]
        for subject_id in evidence["subject_ids"]
        if subject_id in identities and subject_id not in pilot_required_ids
    )
    if pilot_seed_id not in pilot_required_ids:
        raise ValueError("pilot regression pack does not contain its configured seed")
    pilot_products = pilot_required_ids - {pilot_seed_id}
    topology_pilot_products = {
        product_id
        for product_id in appearances
        if pilot_family_id in appearances[product_id]
    }
    if pilot_products != topology_pilot_products:
        raise ValueError("pilot regression required identity set drifted from frozen pack")
    if len(pilot_required_ids) != pilot["expected_required_identities"]:
        raise ValueError("pilot regression required-identity count mismatch")

    for edge in relationships["napcs_concordance_non_mappings"]:
        collection_id = edge["collection_identity_id"]
        relationship_ids[collection_id].add(
            _relationship_id("napcs-non-mapping", collection_id, edge["disposition"])
        )

    assignments: dict[str, dict[str, Any]] = {}
    for identity_id in sorted(leaf_ids):
        assignments[identity_id] = _assignment(
            identity=identities[identity_id],
            role="required_review",
            owner=leaf_family[identity_id],
            appearances=[leaf_family[identity_id]],
            reason="six_digit_naics_anchor",
        )
    for identity_id in sorted(linked_collection_ids):
        owner = (
            pilot_family_id
            if identity_id in pilot_products
            else _rendezvous_owner(identity_id, appearances[identity_id])
        )
        assignments[identity_id] = _assignment(
            identity=identities[identity_id],
            role="required_review",
            owner=owner,
            appearances=appearances[identity_id],
            reason=(
                "pinned_completed_pilot_surface"
                if identity_id in pilot_products
                else "linked_collection_rendezvous_owner"
            ),
            supporting_relationship_ids=relationship_ids[identity_id],
        )
    for identity_id in sorted(unlinked_collection_ids):
        assignments[identity_id] = _assignment(
            identity=identities[identity_id],
            role="required_review",
            owner=unlinked_owner[identity_id],
            appearances=[unlinked_owner[identity_id]],
            reason="unlinked_collection_coverage_challenge",
            supporting_relationship_ids=relationship_ids[identity_id],
        )

    descendant_families: dict[str, set[str]] = defaultdict(set)
    for leaf_id in sorted(leaf_ids):
        identity = identities[leaf_id]
        for record_id in identity["source_record_ids"]:
            for ancestor_id in records[record_id]["hierarchy_path"]:
                if ancestor_id in aggregate_naics_ids:
                    descendant_families[ancestor_id].add(leaf_family[leaf_id])
    for identity_id in sorted(aggregate_naics_ids):
        family_ids = descendant_families[identity_id]
        assignments[identity_id] = _assignment(
            identity=identities[identity_id],
            role="context_only",
            owner=_rendezvous_owner(identity_id, family_ids),
            appearances=family_ids,
            reason="naics_hierarchy_context",
        )

    trilateral_to_collection: dict[str, set[str]] = defaultdict(set)
    for edge in relationships["napcs_concordance_relationships"]:
        collection_id = edge["collection_identity_id"]
        trilateral_id = edge["trilateral_identity_id"]
        trilateral_to_collection[trilateral_id].add(collection_id)
        relationship_ids[trilateral_id].add(
            _relationship_id("napcs-concordance", collection_id, trilateral_id)
        )
    hierarchy_nodes = {node["code"]: node for node in hierarchy["nodes"]}
    children: dict[str, set[str]] = defaultdict(set)
    for code, node in hierarchy_nodes.items():
        if node["parent_code"]:
            children[node["parent_code"]].add(code)
    direct_trilateral_appearances: dict[str, set[str]] = defaultdict(set)
    for trilateral_id, collection_set in trilateral_to_collection.items():
        for collection_id in collection_set:
            direct_trilateral_appearances[trilateral_id].update(
                assignments[collection_id]["appearance_family_ids"]
            )

    inherited_cache: dict[str, set[str]] = {}

    def inherited_appearances(code: str, active: set[str] | None = None) -> set[str]:
        if code in inherited_cache:
            return inherited_cache[code]
        path = set() if active is None else set(active)
        if code in path:
            raise ValueError(f"NAPCS hierarchy cycle at {code}")
        path.add(code)
        identity_id = f"identity:napcs-trilateral:{code}"
        result = set(direct_trilateral_appearances.get(identity_id, set()))
        for child_code in sorted(children.get(code, set())):
            result.update(inherited_appearances(child_code, path))
        inherited_cache[code] = result
        return result

    trilateral_ids = {
        identity_id
        for identity_id, item in identities.items()
        if item["identity_type"] == "napcs-trilateral"
    }
    for identity_id in sorted(trilateral_ids):
        code = identities[identity_id]["source_code"]
        family_ids = inherited_appearances(code)
        if not family_ids:
            section = hierarchy_nodes[code]["section"]
            family_ids = {f"family:context:napcs-trilateral:section-{section}"}
        assignments[identity_id] = _assignment(
            identity=identities[identity_id],
            role="context_only",
            owner=_rendezvous_owner(identity_id, family_ids),
            appearances=family_ids,
            reason=(
                "napcs_hierarchy_context_inherited_from_collection"
                if any(family_id.startswith("family:naics-2022:") for family_id in family_ids)
                else "napcs_hierarchy_only_context_bucket"
            ),
            supporting_relationship_ids=relationship_ids[identity_id],
        )

    for identity_id in sorted(pilot_context_ids):
        if identity_id not in assignments:
            raise ValueError(f"pilot context identity is absent from coverage: {identity_id}")
        assignment = assignments[identity_id]
        assignments[identity_id] = _assignment(
            identity=identities[identity_id],
            role=assignment["assignment_role"],
            owner=assignment["owner_family_id"],
            appearances=[*assignment["appearance_family_ids"], pilot_family_id],
            reason=assignment["reason_code"],
            supporting_relationship_ids=assignment["supporting_relationship_ids"],
        )

    if set(assignments) != set(identities):
        missing = sorted(set(identities) - set(assignments))
        extra = sorted(set(assignments) - set(identities))
        raise ValueError(f"identity coverage mismatch: missing={missing} extra={extra}")

    family_records: dict[str, dict[str, Any]] = {}
    family_ids = {
        assignment["owner_family_id"] for assignment in assignments.values()
    } | {
        family_id
        for assignment in assignments.values()
        for family_id in assignment["appearance_family_ids"]
    }
    for family_id in sorted(family_ids):
        required_ids = sorted(
            identity_id
            for identity_id, assignment in assignments.items()
            if assignment["owner_family_id"] == family_id
            and assignment["assignment_role"] == "required_review"
        )
        context_ids = sorted(
            identity_id
            for identity_id, assignment in assignments.items()
            if family_id in assignment["appearance_family_ids"]
            and not (
                assignment["owner_family_id"] == family_id
                and assignment["assignment_role"] == "required_review"
            )
        )
        schedulable = bool(required_ids) and family_id != pilot_family_id
        status = (
            "completed_regression_fixture"
            if family_id == pilot_family_id
            else "ready_for_boundary_review"
            if schedulable
            else "administrative_context_only"
        )
        if len(required_ids) > limits["max_required_identities_per_family"]:
            raise ValueError(f"family {family_id} exceeds required-identity limit")
        family_records[family_id] = {
            "family_id": family_id,
            "family_kind": (
                "naics_leaf_anchor"
                if family_id.startswith("family:naics-2022:")
                else "unlinked_collection_coverage_challenge"
                if family_id.startswith("family:coverage:napcs-collection:")
                else "administrative_context_bucket"
            ),
            "status": status,
            "schedulable": schedulable,
            "required_disposition_identity_ids": required_ids,
            "context_only_identity_ids": context_ids,
            "context_shards": [
                {
                    "shard_id": "context-shard:"
                    + canonical_sha256({"family_id": family_id, "identity_ids": shard})[:24],
                    "identity_ids": shard,
                }
                for shard in _chunked(
                    context_ids, limits["max_context_identities_per_shard"]
                )
            ],
            "required_prior_candidate_ids": [],
            "counts": {
                "required_identities": len(required_ids),
                "context_identities": len(context_ids),
                "context_shards": (
                    (len(context_ids) + limits["max_context_identities_per_shard"] - 1)
                    // limits["max_context_identities_per_shard"]
                ),
                "required_candidates": 0,
            },
        }

    if set(
        family_records[pilot_family_id]["required_disposition_identity_ids"]
    ) != pilot_required_ids:
        raise ValueError("pilot family required identities do not match frozen pack")
    if (
        set(family_records[pilot_family_id]["context_only_identity_ids"])
        != pilot_context_ids
    ):
        raise ValueError("pilot family context identities do not match frozen pack")

    candidate_occurrences: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for identity_id, mapping in sorted(mappings.items()):
        assignment = assignments[identity_id]
        for rank, candidate in enumerate(mapping["candidates"], 1):
            candidate_occurrences[candidate["candidate_market_id"]].append(
                {
                    "identity_id": identity_id,
                    "rank": rank,
                    "similarity": candidate["similarity"],
                    "relationship_type": candidate["relationship_type"],
                    "semantic_conflicts": candidate["semantic_conflicts"],
                    "exact_normalized_label": candidate["component_signals"][
                        "exact_normalized_label"
                    ],
                    "owner_family_id": assignment["owner_family_id"],
                    "appearance_family_ids": assignment["appearance_family_ids"],
                }
            )
    candidate_catalog = {
        item["candidate_market_id"]: item
        for item in reconciliation["candidate_markets"]
    }
    unretrieved_ids = sorted(set(candidate_catalog) - set(candidate_occurrences))
    review_capable_family_ids = {
        family_id
        for family_id, family in family_records.items()
        if family["schedulable"] or family["status"] == "completed_regression_fixture"
    }
    context_only_collision_ids = sorted(
        candidate_id
        for candidate_id, occurrences in candidate_occurrences.items()
        if not {
            family_id
            for occurrence in occurrences
            for family_id in occurrence["appearance_family_ids"]
        }
        & review_capable_family_ids
    )
    global_challenger_ids = sorted(
        set(unretrieved_ids) | set(context_only_collision_ids)
    )
    challenger_family_ids: list[str] = []
    for ordinal, shard in enumerate(
        _chunked(global_challenger_ids, limits["max_required_identities_per_family"]), 1
    ):
        family_id = _coverage_family_id("prior-candidate", "global-challenger", ordinal)
        challenger_family_ids.append(family_id)
        family_records[family_id] = {
            "family_id": family_id,
            "family_kind": "global_prior_candidate_challenge",
            "status": "ready_for_boundary_review",
            "schedulable": True,
            "required_disposition_identity_ids": [],
            "context_only_identity_ids": [],
            "context_shards": [],
            "required_prior_candidate_ids": [],
            "counts": {
                "required_identities": 0,
                "context_identities": 0,
                "context_shards": 0,
                "required_candidates": 0,
            },
        }
    candidate_ledger: list[dict[str, Any]] = []
    for candidate_id, candidate in sorted(candidate_catalog.items()):
        occurrences = sorted(
            candidate_occurrences.get(candidate_id, []),
            key=lambda item: (item["identity_id"], item["rank"]),
        )
        if occurrences:
            exact = [item for item in occurrences if item["exact_normalized_label"]]
            collision_families = sorted(
                {
                    family_id
                    for item in occurrences
                    for family_id in item["appearance_family_ids"]
                }
            )
            eligible_families = set(collision_families) & review_capable_family_ids
            exact_eligible_families = {
                family_id
                for item in exact
                for family_id in item["appearance_family_ids"]
                if family_id in review_capable_family_ids
            }
            if eligible_families:
                primary_family = _rendezvous_owner(
                    candidate_id, exact_eligible_families or eligible_families
                )
                status = "exact_collision" if exact else "retrieved_collision"
            else:
                primary_family = challenger_family_ids[
                    int(hashlib.sha256(candidate_id.encode()).hexdigest(), 16)
                    % len(challenger_family_ids)
                ]
                status = "context_only_collision_challenger"
        else:
            primary_family = challenger_family_ids[
                int(hashlib.sha256(candidate_id.encode()).hexdigest(), 16)
                % len(challenger_family_ids)
            ]
            collision_families = [primary_family]
            status = "unretrieved_global_challenger"
        family_records[primary_family]["required_prior_candidate_ids"].append(
            candidate_id
        )
        candidate_ledger.append(
            {
                "candidate_market_id": candidate_id,
                "name": candidate["name"],
                "coverage_status": status,
                "primary_family_id": primary_family,
                "collision_family_ids": collision_families,
                "retrieval_occurrences": occurrences,
                "interpretation_boundary": (
                    "Retrieval and administrative challenge ownership only. A family-local "
                    "disposition cannot globally reject this candidate."
                ),
            }
        )

    for family in family_records.values():
        candidates = sorted(set(family["required_prior_candidate_ids"]))
        family["required_prior_candidate_ids"] = candidates
        family["counts"]["required_candidates"] = len(candidates)
        unresolved = sum(
            1
            for identity_id in family["required_disposition_identity_ids"]
            if mappings[identity_id]["status"]
            in {
                "ambiguous_or_semantically_conflicted_review",
                "unmatched_requires_add_split_or_exclusion_review",
            }
        )
        shared = sum(
            1
            for identity_id in family["required_disposition_identity_ids"]
            if len(assignments[identity_id]["appearance_family_ids"]) > 1
        )
        tier = (
            0
            if family["family_kind"]
            in {
                "unlinked_collection_coverage_challenge",
                "global_prior_candidate_challenge",
            }
            else 1
            if unresolved or shared
            else 2
        )
        required_work = (
            family["counts"]["required_identities"]
            + family["counts"]["required_candidates"]
        )
        family["neutral_priority"] = {
            "tier": tier,
            "unresolved_or_unmatched_required_identities": unresolved,
            "shared_required_identities": shared,
            "required_work_items": required_work,
            "ordering_key": [
                tier,
                -unresolved,
                -shared,
                -required_work,
                family["family_id"],
            ],
            "prohibited_signals": [
                "strategy fit",
                "market attractiveness",
                "Target eligibility",
                "AI value",
                "company evidence",
            ],
        }

    ordered_families = sorted(
        (family for family in family_records.values() if family["schedulable"]),
        key=lambda family: tuple(family["neutral_priority"]["ordering_key"]),
    )
    batches: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        ordinal = len(batches) + 1
        family_ids_in_batch = [family["family_id"] for family in current]
        payload = {
            "ordinal": ordinal,
            "family_ids": family_ids_in_batch,
            "required_identities": sum(
                family["counts"]["required_identities"] for family in current
            ),
            "required_candidates": sum(
                family["counts"]["required_candidates"] for family in current
            ),
        }
        batches.append(
            {
                "batch_id": "family-batch:" + canonical_sha256(payload)[:24],
                **payload,
                "status": (
                    "completed_regression_fixture"
                    if all(
                        family["status"] == "completed_regression_fixture"
                        for family in current
                    )
                    else "ready"
                ),
            }
        )
        current = []

    for family in ordered_families:
        next_required = sum(
            item["counts"]["required_identities"] for item in current
        ) + family["counts"]["required_identities"]
        next_candidates = sum(
            item["counts"]["required_candidates"] for item in current
        ) + family["counts"]["required_candidates"]
        if current and (
            len(current) >= limits["max_families_per_batch"]
            or next_required > limits["max_required_identities_per_batch"]
            or next_candidates > limits["max_required_candidates_per_batch"]
        ):
            flush()
        current.append(family)
    flush()

    assignment_list = [assignments[key] for key in sorted(assignments)]
    required_count = sum(
        item["assignment_role"] == "required_review" for item in assignment_list
    )
    context_count = len(assignment_list) - required_count
    retrieved_candidates = sum(
        item["coverage_status"] != "unretrieved_global_challenger"
        for item in candidate_ledger
    )
    context_only_collision_candidates = sum(
        item["coverage_status"] == "context_only_collision_challenger"
        for item in candidate_ledger
    )
    count_gates = {
        "normalized_identities": len(assignment_list),
        "naics_leaves": len(leaf_ids),
        "aggregate_naics": len(aggregate_naics_ids),
        "linked_collection_identities": len(linked_collection_ids),
        "unlinked_collection_identities": len(unlinked_collection_ids),
        "trilateral_identities": len(trilateral_ids),
        "required_review_identities": required_count,
        "context_only_identities": context_count,
        "industry_product_relationships": len(
            relationships["industry_product_relationships"]
        ),
        "napcs_concordance_relationships": len(
            relationships["napcs_concordance_relationships"]
        ),
        "napcs_concordance_non_mappings": len(
            relationships["napcs_concordance_non_mappings"]
        ),
        "prior_candidates": len(candidate_ledger),
        "retrieved_candidates": retrieved_candidates,
        "unretrieved_candidates": len(candidate_ledger) - retrieved_candidates,
        "context_only_collision_candidates": context_only_collision_candidates,
        "families": len(family_records),
        "schedulable_families": len(ordered_families),
        "batches": len(batches),
        "pilot_required_identities": len(
            family_records[pilot_family_id]["required_disposition_identity_ids"]
        ),
        "pilot_context_identities": len(
            family_records[pilot_family_id]["context_only_identity_ids"]
        ),
    }
    for field, expected in config["expected_counts"].items():
        if count_gates.get(field) != expected:
            raise ValueError(
                f"family partition count gate {field}: {count_gates.get(field)} != {expected}"
            )
    if required_count + context_count != len(assignment_list):
        raise ValueError("required/context identity roles do not cover the ledger")
    if any(
        assignment["owner_family_id"] not in assignment["appearance_family_ids"]
        for assignment in assignment_list
    ):
        raise ValueError("identity owner is absent from its family appearances")
    if any(
        family_records[item["primary_family_id"]]["status"]
        not in {"ready_for_boundary_review", "completed_regression_fixture"}
        for item in candidate_ledger
    ):
        raise ValueError("candidate work is owned by a non-reviewable family")

    industry_edge_ledger = sorted(
        (
            {
                "relationship_id": _relationship_id(
                    "industry-product",
                    edge["industry_identity_id"],
                    edge["product_identity_id"],
                ),
                "relationship_type": "industry_product",
                "industry_identity_id": edge["industry_identity_id"],
                "product_identity_id": edge["product_identity_id"],
                "product_owner_family_id": assignments[edge["product_identity_id"]][
                    "owner_family_id"
                ],
                "product_appearance_family_ids": assignments[
                    edge["product_identity_id"]
                ]["appearance_family_ids"],
                "observed_in": sorted(edge["observed_in"]),
                "source_observations": _sorted_observations(
                    edge["source_observations"]
                ),
            }
            for edge in relationships["industry_product_relationships"]
        ),
        key=lambda item: item["relationship_id"],
    )
    concordance_edge_ledger = sorted(
        (
            {
                "relationship_id": _relationship_id(
                    "napcs-concordance",
                    edge["collection_identity_id"],
                    edge["trilateral_identity_id"],
                ),
                "relationship_type": "napcs_collection_to_trilateral",
                "collection_identity_id": edge["collection_identity_id"],
                "trilateral_identity_id": edge["trilateral_identity_id"],
                "collection_owner_family_id": assignments[
                    edge["collection_identity_id"]
                ]["owner_family_id"],
                "collection_appearance_family_ids": assignments[
                    edge["collection_identity_id"]
                ]["appearance_family_ids"],
                "trilateral_owner_family_id": assignments[
                    edge["trilateral_identity_id"]
                ]["owner_family_id"],
                "trilateral_appearance_family_ids": assignments[
                    edge["trilateral_identity_id"]
                ]["appearance_family_ids"],
                "observed_in": sorted(edge["observed_in"]),
                "part_indicators": sorted(edge["part_indicators"]),
                "source_observations": _sorted_observations(
                    edge["source_observations"]
                ),
            }
            for edge in relationships["napcs_concordance_relationships"]
        ),
        key=lambda item: item["relationship_id"],
    )
    non_mapping_ledger = sorted(
        (
            {
                "relationship_id": _relationship_id(
                    "napcs-non-mapping",
                    edge["collection_identity_id"],
                    edge["disposition"],
                ),
                "relationship_type": "napcs_explicit_non_mapping",
                "collection_identity_id": edge["collection_identity_id"],
                "owner_family_id": assignments[edge["collection_identity_id"]][
                    "owner_family_id"
                ],
                "appearance_family_ids": assignments[
                    edge["collection_identity_id"]
                ]["appearance_family_ids"],
                "disposition": edge["disposition"],
                "observed_in": sorted(edge["observed_in"]),
                "source_observations": _sorted_observations(
                    edge["source_observations"]
                ),
            }
            for edge in relationships["napcs_concordance_non_mappings"]
        ),
        key=lambda item: item["relationship_id"],
    )

    config_sha256 = canonical_sha256(config)
    source_hashes = {
        name: receipt["output_hashes"][name]
        for name in (
            "multisource-reconciliation.json.gz",
            "identity-relationships.json.gz",
            "napcs-hierarchy-evidence.json.gz",
        )
    }
    partition_id = "family-partition:" + canonical_sha256(
        {
            "source_run_id": run_id,
            "source_hashes": source_hashes,
            "config_sha256": config_sha256,
            "execution_commit": execution_commit,
        }
    )[:24]
    coverage = {
        "schema_version": 1,
        "partition_id": partition_id,
        "source_run_id": run_id,
        "method_version": config["method_version"],
        "assignments": assignment_list,
        "counts": count_gates,
    }
    candidates_artifact = {
        "schema_version": 1,
        "partition_id": partition_id,
        "source_run_id": run_id,
        "candidates": candidate_ledger,
        "counts": {
            "prior_candidates": len(candidate_ledger),
            "retrieved_candidates": retrieved_candidates,
            "unretrieved_candidates": len(candidate_ledger) - retrieved_candidates,
            "context_only_collision_candidates": context_only_collision_candidates,
            "retrieval_occurrences": sum(
                len(item["retrieval_occurrences"]) for item in candidate_ledger
            ),
        },
    }
    families_artifact = {
        "schema_version": 1,
        "partition_id": partition_id,
        "source_run_id": run_id,
        "families": [family_records[key] for key in sorted(family_records)],
        "counts": {
            "families": len(family_records),
            "schedulable_families": len(ordered_families),
            "context_only_families": sum(
                not family["schedulable"] for family in family_records.values()
            ),
        },
    }
    batches_artifact = {
        "schema_version": 1,
        "partition_id": partition_id,
        "source_run_id": run_id,
        "limits": limits,
        "neutral_priority_policy": config["neutral_priority_policy"],
        "batches": batches,
        "counts": {
            "batches": len(batches),
            "scheduled_families": sum(len(batch["family_ids"]) for batch in batches),
        },
    }
    relationship_artifact = {
        "schema_version": 1,
        "partition_id": partition_id,
        "source_run_id": run_id,
        "industry_product_relationships": industry_edge_ledger,
        "napcs_concordance_relationships": concordance_edge_ledger,
        "napcs_concordance_non_mappings": non_mapping_ledger,
        "counts": {
            "industry_product_relationships": len(industry_edge_ledger),
            "napcs_concordance_relationships": len(concordance_edge_ledger),
            "napcs_concordance_non_mappings": len(non_mapping_ledger),
        },
        "interpretation_boundary": (
            "Official source relationship topology and administrative family routing only; "
            "not accepted canonical market mappings."
        ),
    }
    artifacts = {
        "coverage-ledger.json.gz": coverage,
        "context-edge-ledger.json.gz": relationship_artifact,
        "candidate-collision-ledger.json.gz": candidates_artifact,
        "family-manifest.json.gz": families_artifact,
        "batch-manifest.json": batches_artifact,
    }
    output_hashes = {
        name: _sha256_bytes(
            _canonical_gzip(value) if name.endswith(".gz") else _canonical_bytes(value)
        )
        for name, value in artifacts.items()
    }
    receipt_payload = {
        "schema_version": 1,
        "partition_id": partition_id,
        "source_run_id": run_id,
        "as_of_utc": config["as_of_utc"],
        "method_version": config["method_version"],
        "config_sha256": config_sha256,
        "execution_commit": execution_commit,
        "source_hashes": source_hashes,
        "output_hashes": output_hashes,
        "counts": count_gates,
        "pilot_regression": {
            "family_id": pilot_family_id,
            "source_family_config": pilot["source_family_config"],
            "source_pack_sha256": pilot["source_pack_sha256"],
            "required_identities": count_gates["pilot_required_identities"],
            "context_identities": count_gates["pilot_context_identities"],
            "required_identity_set_sha256": canonical_sha256(
                sorted(pilot_required_ids)
            ),
            "context_identity_set_sha256": canonical_sha256(
                sorted(pilot_context_ids)
            ),
            "status": "completed_regression_fixture",
        },
        "model_invoked": False,
        "status": "complete_deterministic_family_plan",
    }
    return {
        "partition_id": partition_id,
        "artifacts": artifacts,
        "receipt": receipt_payload,
    }


def run_family_plan(
    config_path: Path,
    *,
    output_root: Path | None = None,
    pointer_path: Path | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    if not _git_worktree_clean(root):
        raise RuntimeError(
            "family plan requires a clean Git worktree so its exact commit contains "
            "the executed compiler and configuration"
        )
    execution_commit = _git_head(root)
    if execution_commit is None:
        raise RuntimeError("cannot determine exact Git commit for family plan")
    compiled = compile_family_plan(
        config_path, execution_commit=execution_commit, root=root
    )
    destination = output_root or root / "data" / "family_schedules"
    schedule_dir = destination / compiled["partition_id"]
    destination.mkdir(parents=True, exist_ok=True)
    if schedule_dir.exists():
        raise FileExistsError(f"family plan already exists: {schedule_dir}")
    with tempfile.TemporaryDirectory(prefix=".family-plan-", dir=destination) as raw_temp:
        temporary_dir = Path(raw_temp)
        for name, value in compiled["artifacts"].items():
            path = temporary_dir / name
            if name.endswith(".gz"):
                path.write_bytes(_canonical_gzip(value))
            else:
                path.write_bytes(_canonical_bytes(value))
        (temporary_dir / "schedule-receipt.json").write_bytes(
            _canonical_bytes(compiled["receipt"])
        )
        temporary_dir.replace(schedule_dir)
    pointer = {
        "schema_version": 1,
        "status": "complete_deterministic_family_plan",
        "partition_id": compiled["partition_id"],
        "source_run_id": compiled["receipt"]["source_run_id"],
        "schedule_path": str(schedule_dir.relative_to(root)),
        "receipt_sha256": canonical_sha256(compiled["receipt"]),
        "counts": compiled["receipt"]["counts"],
    }
    resolved_pointer = (
        pointer_path
        or root / "data" / "generated" / "latest-family-schedule.json"
    )
    temporary = resolved_pointer.with_suffix(resolved_pointer.suffix + ".tmp")
    temporary.write_bytes(_canonical_bytes(pointer))
    temporary.replace(resolved_pointer)
    return {"schedule_dir": str(schedule_dir), **compiled["receipt"]}


def validate_family_plan(
    schedule_dir: Path,
    config_path: Path,
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        receipt = _object(schedule_dir / "schedule-receipt.json")
        execution_commit = receipt["execution_commit"]
        if not _git_commit_exists(root, execution_commit):
            raise ValueError("execution_commit is not a resolvable full Git commit")
        compiled = compile_family_plan(
            config_path, execution_commit=execution_commit, root=root
        )
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "valid": False,
            "errors": [f"family plan cannot replay: {error}"],
            "partition_id": schedule_dir.name,
        }
    if receipt != compiled["receipt"]:
        errors.append("persisted schedule receipt does not match deterministic compilation")
    for name, expected_hash in compiled["receipt"]["output_hashes"].items():
        path = schedule_dir / name
        if not path.exists() or _sha256_path(path) != expected_hash:
            errors.append(f"persisted family-plan artifact hash mismatch: {name}")
    if schedule_dir.name != compiled["partition_id"]:
        errors.append("family-plan directory name does not match partition_id")
    return {
        "valid": not errors,
        "errors": errors,
        "partition_id": compiled["partition_id"],
        "counts": compiled["receipt"]["counts"],
    }
