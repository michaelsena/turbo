from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass

from turbo.pipeline_paths import ROOT
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

    @property
    def name(self) -> str:
        return self.raw_label


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
    excluded_terms: set[str] = set()
    for match in re.finditer(r"\b(?:except|excluding)\b\s+(.+?)(?=\b(?:and|or)\b|$)", normalized):
        excluded_terms.update(
            part
            for part in match.group(1).split()
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
            if "nonhazardous" in words
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
                record_id=f"napcs:{code}",
                source="napcs_collection_codes_2022",
                source_code=code,
                raw_label=label,
                record_kind=record_kind,
                locator=f"first_sheet:row:{row_number}",
            )
        )
    return result


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
                record_id=f"prior:{digest}{duplicate_suffix}",
                source="prior_model_2026_11_05",
                source_code="",
                raw_label=name,
                record_kind="market_hypothesis",
                locator=f"markets[{index - 1}]",
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
    return {
        **asdict(record),
        "normalized_label": normalize_name(record.raw_label),
        "semantic_flags": semantic_flags(record.raw_label),
    }


def reconcile() -> dict[str, object]:
    naics = [
        NamedRecord(
            record_id=f"naics:{node.source_code}",
            source="naics_2022",
            source_code=node.source_code,
            raw_label=node.raw_title,
            record_kind="industry",
            locator=f"2022_NAICS_Structure:{node.source_code}",
        )
        for node in parse_naics(NAICS)
        if node.level == 6
    ]
    napcs = parse_napcs()
    seeds = parse_prior()
    seed_tokens = {item.record_id: retrieval_tokens(item.name) for item in seeds}
    seed_by_id = {item.record_id: item for item in seeds}
    inverted: dict[str, set[str]] = defaultdict(set)
    exact: dict[str, list[str]] = defaultdict(list)
    for item in seeds:
        exact[normalize_name(item.name)].append(item.record_id)
        for token in seed_tokens[item.record_id]:
            inverted[token].add(item.record_id)
    for ids in exact.values():
        ids.sort()

    def candidate(record: NamedRecord, candidate_id: str, score: float) -> dict[str, object]:
        proposed = seed_by_id[candidate_id]
        return {
            "candidate_market_id": candidate_id,
            "candidate_market_name": proposed.name,
            "similarity": round(score, 4),
            "relationship_type": "equivalent_label_candidate",
            "semantic_conflicts": semantic_conflicts(record.name, proposed.name),
        }

    def match(record: NamedRecord) -> dict[str, object]:
        normalized = normalize_name(record.name)
        exact_ids = exact.get(normalized, [])
        if exact_ids:
            candidates = [candidate(record, candidate_id, 1.0) for candidate_id in exact_ids[:TOP_K]]
            return {
                "source_record_id": record.record_id,
                "status": "exact_label_candidate",
                "reason": "identical_normalized_label_still_requires_operating_identity_review",
                "top_similarity": 1.0,
                "top_two_margin": 0.0 if len(candidates) > 1 else 1.0,
                "ambiguous": len(candidates) > 1,
                "candidates": candidates,
            }
        record_tokens = retrieval_tokens(record.name)
        candidate_ids: set[str] = set()
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
        if top_score >= MIN_PROPOSAL_SIMILARITY:
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

    source_records = [*naics, *napcs, *seeds]
    mappings = [match(record) for record in [*naics, *napcs]]
    exact_duplicate_groups = [ids for ids in exact.values() if len(ids) > 1]
    counts: dict[str, int] = defaultdict(int)
    for item in mappings:
        counts[str(item["status"])] += 1
    return {
        "schema_version": 2,
        "artifact_type": "multisource_universe_reconciliation_worklist",
        "warning": "All mappings are top-k review proposals until operating-identity review; label similarity never establishes a canonical market decision.",
        "source_counts": {
            "naics_six_digit": len(naics),
            "napcs_products": len(napcs),
            "prior_seed_markets": len(seeds),
        },
        "source_records": [_source_record(item) for item in source_records],
        "candidate_markets": [
            {
                "candidate_market_id": item.record_id,
                "name": item.name,
                "status": "unvalidated_prior_model_seed",
                "source_record_id": item.record_id,
            }
            for item in seeds
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
