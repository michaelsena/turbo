from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass

from turbo.pipeline_paths import ROOT
from turbo.universe.identity_sources import (
    parse_collection_to_trilateral,
    parse_trilateral_to_collection,
    relationship_product_records,
)
from turbo.universe.naics import parse_naics, read_first_sheet

NAICS = ROOT / "data/source_snapshots/2022-naics-structure.xlsx"
NAPCS = ROOT / "data/source_snapshots/2022-economic-census-napcs-codes.xlsx"
PRIOR = ROOT / "data/source_snapshots/prior-model-normalized-markets-2026-11-05.json"

# Retrieval may ignore only grammatical glue. Scope words such as "other", "except",
# "commercial", and "service" remain authoritative semantic inputs.
RETRIEVAL_STOPWORDS = {"and", "for", "of", "the", "to"}
TOP_K = 5
MIN_PROPOSAL_SIMILARITY = 0.55
AMBIGUITY_MARGIN = 0.05


@dataclass(frozen=True)
class NamedRecord:
    record_id: str
    source: str
    source_code: str
    raw_label: str
    record_kind: str
    locator: str
    snapshot_id: str
    normalized_identity_ids: tuple[str, ...]
    raw_definition: str = ""
    hierarchy_path: tuple[str, ...] = ()
    parent_ids: tuple[str, ...] = ()
    source_relationships: tuple[dict[str, str], ...] = ()

    @property
    def name(self) -> str:
        return self.raw_label

    @property
    def candidate_market_id(self) -> str:
        digest = hashlib.sha256(normalize_name(self.raw_label).encode("utf-8")).hexdigest()[:24]
        return f"candidate-market:{digest}"


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def retrieval_tokens(value: str) -> frozenset[str]:
    parts = []
    for part in normalize_name(value).split():
        if part in RETRIEVAL_STOPWORDS:
            continue
        parts.append("service" if part == "services" else part)
    return frozenset(parts)


def semantic_flags(value: str) -> dict[str, object]:
    normalized = normalize_name(value)
    words = frozenset(normalized.split())
    semantic_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    excluded_terms: set[str] = set()
    for match in re.finditer(r"\b(?:except|excluding)\b\s+([^)]+?)(?=\)|;|$)", semantic_text):
        excluded_terms.update(
            part
            for part in normalize_name(match.group(1)).split()
            if part not in RETRIEVAL_STOPWORDS and part not in {"service", "services"}
        )
    return {
        "residual": normalized.startswith("other ")
        or normalized.startswith("all other ")
        or " all other " in f" {normalized} ",
        "has_except_scope": "except" in words or "excluding" in words,
        "excluded_terms": sorted(excluded_terms),
        "hazard_scope": (
            "nonhazardous"
            if re.search(r"\bnon[\s-]*hazardous\b", semantic_text)
            else "hazardous"
            if "hazardous" in words
            else None
        ),
        "customer_scope": sorted(words & {"commercial", "consumer", "industrial", "residential"}),
    }


def semantic_conflicts(left: str, right: str) -> list[str]:
    left_flags = semantic_flags(left)
    right_flags = semantic_flags(right)
    conflicts: list[str] = []
    hazard_pair = {left_flags["hazard_scope"], right_flags["hazard_scope"]}
    if hazard_pair == {"hazardous", "nonhazardous"}:
        conflicts.append("hazard_scope_conflict")
    right_tokens = retrieval_tokens(right)
    left_excluded = set(left_flags["excluded_terms"])
    if left_excluded & right_tokens and not right_flags["has_except_scope"]:
        conflicts.append("candidate_contains_source_excluded_scope")
    left_tokens = retrieval_tokens(left)
    right_excluded = set(right_flags["excluded_terms"])
    if right_excluded & left_tokens and not left_flags["has_except_scope"]:
        conflicts.append("source_contains_candidate_excluded_scope")
    if bool(left_flags["residual"]) != bool(right_flags["residual"]):
        conflicts.append("residual_scope_mismatch")
    return sorted(set(conflicts))


def parse_napcs() -> list[NamedRecord]:
    forward_rows = parse_collection_to_trilateral()
    reverse_rows = parse_trilateral_to_collection()
    concordance: dict[str, dict[tuple[str, str], set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    collection_labels: dict[str, str] = {}
    for direction, rows in (
        ("collection_to_trilateral", forward_rows),
        ("trilateral_to_collection", reverse_rows),
    ):
        for row in rows:
            if row.collection_code and row.collection_description:
                collection_labels.setdefault(row.collection_code, row.collection_description)
            if row.collection_code and row.trilateral_code not in {"", "NA"}:
                concordance[row.collection_code][
                    (row.trilateral_code, row.part_indicator)
                ].add(direction)
    def relationships(code: str) -> tuple[dict[str, str], ...]:
        return tuple(
            {
                "relationship_type": "collection_to_trilateral",
                "target_identity_id": f"identity:napcs-trilateral:{trilateral_code}",
                "part_indicator": part_indicator,
                "observed_in": ",".join(sorted(directions)),
            }
            for (trilateral_code, part_indicator), directions in sorted(
                concordance.get(code, {}).items()
            )
        )

    result: list[NamedRecord] = []
    for row_number, row in enumerate(read_first_sheet(NAPCS), 1):
        if len(row) < 2 or not row[0].strip().isdigit():
            continue
        code = row[0].strip()
        label = " ".join(row[1].split())
        if label.lower().startswith("add #"):
            record_kind = "survey_control"
        elif code.endswith("0"):
            record_kind = "napcs_broad_line"
        else:
            record_kind = "napcs_detail_line"
        result.append(
            NamedRecord(
                record_id=(
                    "source-row:census-napcs-2022-economic-census-codes:"
                    f"{code}"
                ),
                source="napcs_collection_codes_2022",
                source_code=code,
                raw_label=label,
                record_kind=record_kind,
                locator=f"first_sheet:row:{row_number}",
                snapshot_id="census-napcs-2022-economic-census-codes",
                normalized_identity_ids=(f"identity:napcs-collection:{code}",),
                source_relationships=relationships(code),
            )
        )
    known_codes = {record.source_code for record in result}
    for code, label in sorted(relationship_product_records().items()):
        if code in known_codes:
            continue
        result.append(
            NamedRecord(
                record_id=(
                    "source-observation:census-economic-census-2022-products-by-industry:"
                    f"napcs:{code}"
                ),
                source="economic_census_products_by_industry_2022",
                source_code=code,
                raw_label=label,
                record_kind="relationship_product",
                locator=(
                    "EC2200NAPCSPRDIND.dat:GEO_ID=0100000US:"
                    f"NAPCS2022={code}"
                ),
                snapshot_id="census-economic-census-2022-products-by-industry",
                normalized_identity_ids=(f"identity:napcs-collection:{code}",),
            )
        )
        known_codes.add(code)
    for code, label in sorted(collection_labels.items()):
        if code in known_codes:
            continue
        result.append(
            NamedRecord(
                record_id=(
                    "source-observation:census-napcs-2022-collection-to-trilateral:"
                    f"collection:{code}"
                ),
                source="napcs_collection_to_trilateral_2022",
                source_code=code,
                raw_label=label,
                record_kind="concordance_product",
                locator=f"data_sheet:collection_code={code}",
                snapshot_id="census-napcs-2022-collection-to-trilateral",
                normalized_identity_ids=(f"identity:napcs-collection:{code}",),
                source_relationships=relationships(code),
            )
        )
    return result


def parse_trilateral_products() -> list[NamedRecord]:
    grouped: dict[str, dict[str, object]] = {}
    for direction, rows in (
        ("collection_to_trilateral", parse_collection_to_trilateral()),
        ("trilateral_to_collection", parse_trilateral_to_collection()),
    ):
        for row in rows:
            code = row.trilateral_code
            if code in {"", "NA"}:
                continue
            value = grouped.setdefault(
                code,
                {"labels": set(), "collections": defaultdict(set)},
            )
            if row.trilateral_description:
                value["labels"].add(row.trilateral_description)
            value["collections"][(row.collection_code, row.part_indicator)].add(direction)
    records: list[NamedRecord] = []
    for code, value in sorted(grouped.items()):
        labels = sorted(value["labels"])
        records.append(
            NamedRecord(
                record_id=(
                    "source-observation:census-napcs-2022-trilateral-to-collection:"
                    f"trilateral:{code}"
                ),
                source="napcs_trilateral_concordance_2022",
                source_code=code,
                raw_label=labels[0],
                record_kind="trilateral_product",
                locator=f"data_sheet:trilateral_code={code}",
                snapshot_id="census-napcs-2022-trilateral-to-collection",
                normalized_identity_ids=(f"identity:napcs-trilateral:{code}",),
                source_relationships=tuple(
                    {
                        "relationship_type": "trilateral_to_collection",
                        "target_identity_id": f"identity:napcs-collection:{collection_code}",
                        "part_indicator": part_indicator,
                        "observed_in": ",".join(sorted(directions)),
                    }
                    for (collection_code, part_indicator), directions in sorted(
                        value["collections"].items()
                    )
                ),
            )
        )
    return records


def prior_records(names: list[str]) -> list[NamedRecord]:
    totals = Counter(names)
    seen: Counter[str] = Counter()
    records: list[NamedRecord] = []
    for index, name in enumerate(names, 1):
        seen[name] += 1
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:20]
        duplicate_suffix = f":dup:{seen[name]}" if totals[name] > 1 else ""
        records.append(
            NamedRecord(
                record_id=f"source-row:prior-model-2026-11-05:{digest}{duplicate_suffix}",
                source="prior_model_2026_11_05",
                source_code="",
                raw_label=name,
                record_kind="market_hypothesis",
                locator=f"markets[{index - 1}]",
                snapshot_id="prior-model-normalized-markets-2026-11-05",
                normalized_identity_ids=(),
            )
        )
    return records


def parse_prior() -> list[NamedRecord]:
    payload = json.loads(PRIOR.read_text(encoding="utf-8"))
    return prior_records(payload["markets"])


def _similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _source_record(record: NamedRecord) -> dict[str, object]:
    json_compatible = json.loads(json.dumps(asdict(record)))
    return {
        **json_compatible,
        "normalized_label": normalize_name(record.raw_label),
        "semantic_flags": semantic_flags(record.raw_label),
    }


def reconcile() -> dict[str, object]:
    naics_nodes = parse_naics(NAICS)
    node_by_id = {node.node_id: node for node in naics_nodes}

    def hierarchy_path(node_id: str) -> tuple[str, ...]:
        path: list[str] = []
        current = node_by_id[node_id]
        while True:
            path.append(f"identity:naics:{current.source_code}")
            if current.parent_id is None:
                break
            current = node_by_id[current.parent_id]
        return tuple(reversed(path))

    naics = []
    for node in naics_nodes:
        parent_ids = (
            (f"identity:naics:{node_by_id[node.parent_id].source_code}",)
            if node.parent_id is not None
            else ()
        )
        relationships = (
            (
                {
                    "relationship_type": "source_parent",
                    "target_identity_id": f"identity:naics:{node_by_id[node.parent_id].source_code}",
                },
            )
            if parent_ids
            else ()
        )
        naics.append(
            NamedRecord(
                record_id=f"source-row:census-naics-2022:{node.source_code}",
                source="naics_2022",
                source_code=node.source_code,
                raw_label=node.raw_title,
                record_kind="industry" if node.level == 6 else "industry_aggregate",
                locator=f"2022_NAICS_Structure:{node.source_code}",
                snapshot_id="census-naics-2022",
                normalized_identity_ids=(f"identity:naics:{node.source_code}",),
                hierarchy_path=hierarchy_path(node.node_id),
                parent_ids=parent_ids,
                source_relationships=relationships,
            )
        )
    napcs = parse_napcs()
    trilateral = parse_trilateral_products()
    seeds = parse_prior()
    seed_by_id: dict[str, NamedRecord] = {}
    duplicate_seed_rows: dict[str, list[str]] = defaultdict(list)
    for item in seeds:
        seed_by_id.setdefault(item.candidate_market_id, item)
        duplicate_seed_rows[item.candidate_market_id].append(item.record_id)
    seed_tokens = {
        candidate_id: retrieval_tokens(item.name)
        for candidate_id, item in seed_by_id.items()
    }
    inverted: dict[str, set[str]] = defaultdict(set)
    exact: dict[str, list[str]] = defaultdict(list)
    for candidate_id, item in seed_by_id.items():
        exact[normalize_name(item.name)].append(candidate_id)
        for token in seed_tokens[candidate_id]:
            inverted[token].add(candidate_id)
    for ids in exact.values():
        ids.sort()

    def candidate(record: NamedRecord, candidate_id: str, score: float) -> dict[str, object]:
        proposed = seed_by_id[candidate_id]
        source_tokens = retrieval_tokens(record.name)
        candidate_tokens = seed_tokens[candidate_id]
        return {
            "candidate_market_id": candidate_id,
            "candidate_market_name": proposed.name,
            "similarity": round(score, 4),
            "component_signals": {
                "exact_normalized_label": normalize_name(record.name)
                == normalize_name(proposed.name),
                "matched_tokens": sorted(source_tokens & candidate_tokens),
                "source_only_tokens": sorted(source_tokens - candidate_tokens),
                "candidate_only_tokens": sorted(candidate_tokens - source_tokens),
                "intersection_count": len(source_tokens & candidate_tokens),
                "union_count": len(source_tokens | candidate_tokens),
                "source_semantic_flags": semantic_flags(record.name),
                "candidate_semantic_flags": semantic_flags(proposed.name),
            },
            "relationship_type": "equivalent_label_candidate",
            "semantic_conflicts": semantic_conflicts(record.name, proposed.name),
        }

    def match(record: NamedRecord) -> dict[str, object]:
        normalized = normalize_name(record.name)
        exact_ids = exact.get(normalized, [])
        record_tokens = retrieval_tokens(record.name)
        candidate_ids: set[str] = set(exact_ids)
        for token in record_tokens:
            candidate_ids.update(inverted[token])
        scored = sorted(
            (
                (_similarity(record_tokens, seed_tokens[candidate_id]), candidate_id)
                for candidate_id in candidate_ids
            ),
            key=lambda item: (-item[0], item[1]),
        )
        candidates = [candidate(record, candidate_id, score) for score, candidate_id in scored[:TOP_K]]
        top_score = scored[0][0] if scored else 0.0
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        margin = top_score - second_score
        has_conflict = bool(candidates and candidates[0]["semantic_conflicts"])
        ambiguous = top_score >= MIN_PROPOSAL_SIMILARITY and margin <= AMBIGUITY_MARGIN
        if exact_ids:
            status = "exact_label_candidate"
            reason = "identical_normalized_label_still_requires_operating_identity_review"
        elif top_score >= MIN_PROPOSAL_SIMILARITY:
            status = (
                "ambiguous_or_semantically_conflicted_review"
                if ambiguous or has_conflict
                else "proposed_mapping_review"
            )
            reason = "top_k_similarity_requires_operating_identity_review"
        else:
            status = "unmatched_requires_add_split_or_exclusion_review"
            reason = "no_sufficient_candidate_match"
        return {
            "source_record_id": record.record_id,
            "status": status,
            "reason": reason,
            "top_similarity": round(top_score, 4),
            "top_two_margin": round(margin, 4),
            "ambiguous": ambiguous,
            "candidates": candidates,
        }

    source_records = [*naics, *napcs, *trilateral, *seeds]
    mappings = [match(record) for record in [*naics, *napcs, *trilateral]]
    identities: dict[str, dict[str, object]] = {}
    for record in source_records:
        for identity_id in record.normalized_identity_ids:
            value = identities.setdefault(
                identity_id,
                {
                    "identity_id": identity_id,
                    "identity_type": identity_id.split(":", 2)[1],
                    "source_code": record.source_code,
                    "labels": set(),
                    "source_record_ids": [],
                },
            )
            value["labels"].add(record.raw_label)
            value["source_record_ids"].append(record.record_id)
    exact_duplicate_groups = [
        source_ids
        for source_ids in duplicate_seed_rows.values()
        if len(source_ids) > 1
    ]
    counts: dict[str, int] = defaultdict(int)
    for item in mappings:
        counts[str(item["status"])] += 1
    return {
        "schema_version": 2,
        "artifact_type": "multisource_universe_reconciliation_worklist",
        "warning": "All mappings are top-k review proposals until operating-identity review; label similarity never establishes a canonical market decision.",
        "source_counts": {
            "naics_nodes": len(naics),
            "naics_six_digit": sum(item.record_kind == "industry" for item in naics),
            "napcs_products": len(napcs),
            "napcs_collection_records": sum(
                item.source == "napcs_collection_codes_2022" for item in napcs
            ),
            "napcs_relationship_only_products": sum(
                item.record_kind == "relationship_product" for item in napcs
            ),
            "napcs_concordance_only_products": sum(
                item.record_kind == "concordance_product" for item in napcs
            ),
            "napcs_trilateral_products": len(trilateral),
            "prior_seed_records": len(seeds),
            "prior_candidate_markets": len(seed_by_id),
            "normalized_source_identities": len(identities),
        },
        "source_records": [_source_record(item) for item in source_records],
        "source_identities": [
            {
                **value,
                "labels": sorted(value["labels"]),
                "source_record_ids": sorted(set(value["source_record_ids"])),
            }
            for _, value in sorted(identities.items())
        ],
        "candidate_markets": [
            {
                "candidate_market_id": candidate_id,
                "name": item.name,
                "status": "unvalidated_prior_model_seed",
                "source_record_ids": duplicate_seed_rows[candidate_id],
            }
            for candidate_id, item in sorted(seed_by_id.items())
        ],
        "mapping_counts": dict(sorted(counts.items())),
        "mappings": mappings,
        "exact_duplicate_seed_groups": exact_duplicate_groups,
        "required_next_actions": [
            "Ingest official NAICS definitions, full NAPCS hierarchy/concordance, and industry-product relationships.",
            "Review exact-label and top-k candidates; label similarity does not prove operating-market identity.",
            "Resolve every source row with a typed relationship or explicit non-market disposition.",
            "Apply buyer/job/delivery/workforce/economics/acquisition/AI identity tests.",
            "Publish append-only canonical market decisions with lineage and independent review.",
        ],
    }
