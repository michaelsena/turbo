from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from turbo.pipeline_paths import ROOT
from turbo.universe.naics import parse_naics, read_first_sheet

NAICS = ROOT / "data/source_snapshots/2022-naics-structure.xlsx"
NAPCS = ROOT / "data/source_snapshots/2022-economic-census-napcs-codes.xlsx"
PRIOR = ROOT / "data/source_snapshots/prior-model-normalized-markets-2026-11-05.json"

GENERIC = {
    "and", "for", "of", "the", "to", "other", "all", "except", "services",
    "service", "business", "commercial", "operation", "operations",
}


@dataclass(frozen=True)
class NamedRecord:
    record_id: str
    name: str


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def tokens(value: str) -> frozenset[str]:
    return frozenset(part for part in normalize_name(value).split() if part not in GENERIC)


def parse_napcs() -> list[NamedRecord]:
    result: list[NamedRecord] = []
    for row in read_first_sheet(NAPCS):
        if len(row) < 2 or not row[0].strip().isdigit():
            continue
        result.append(NamedRecord(f"napcs:{row[0].strip()}", " ".join(row[1].split())))
    return result


def parse_prior() -> list[NamedRecord]:
    payload = json.loads(PRIOR.read_text(encoding="utf-8"))
    return [
        NamedRecord(f"prior:{index:04d}", name)
        for index, name in enumerate(payload["markets"], 1)
    ]


def _similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def reconcile() -> dict[str, object]:
    naics = [
        NamedRecord(f"naics:{node.source_code}", node.title)
        for node in parse_naics(NAICS)
        if node.level == 6
    ]
    napcs = parse_napcs()
    seeds = parse_prior()
    seed_tokens = {item.record_id: tokens(item.name) for item in seeds}
    seed_by_id = {item.record_id: item for item in seeds}
    inverted: dict[str, set[str]] = defaultdict(set)
    exact: dict[str, list[str]] = defaultdict(list)
    for item in seeds:
        exact[normalize_name(item.name)].append(item.record_id)
        for token in seed_tokens[item.record_id]:
            inverted[token].add(item.record_id)

    def match(record: NamedRecord, source: str) -> dict[str, object]:
        normalized = normalize_name(record.name)
        exact_ids = exact.get(normalized, [])
        if exact_ids:
            return {
                "source": source,
                "source_record_id": record.record_id,
                "source_name": record.name,
                "candidate_market_id": exact_ids[0],
                "candidate_market_name": seed_by_id[exact_ids[0]].name,
                "similarity": 1.0,
                "status": "accepted_exact_label",
                "reason": "identical_normalized_label",
            }
        record_tokens = tokens(record.name)
        candidate_ids: set[str] = set()
        for token in record_tokens:
            candidate_ids.update(inverted[token])
        best_id = None
        best_score = 0.0
        for candidate_id in candidate_ids:
            score = _similarity(record_tokens, seed_tokens[candidate_id])
            if score > best_score or (score == best_score and candidate_id < (best_id or "~")):
                best_id, best_score = candidate_id, score
        if best_id is not None and best_score >= 0.55:
            return {
                "source": source,
                "source_record_id": record.record_id,
                "source_name": record.name,
                "candidate_market_id": best_id,
                "candidate_market_name": seed_by_id[best_id].name,
                "similarity": round(best_score, 4),
                "status": "proposed_mapping",
                "reason": "token_similarity_requires_review",
            }
        return {
            "source": source,
            "source_record_id": record.record_id,
            "source_name": record.name,
            "candidate_market_id": None,
            "candidate_market_name": None,
            "similarity": round(best_score, 4),
            "status": "unmatched_requires_add_split_or_exclusion_review",
            "reason": "no_sufficient_candidate_match",
        }

    mappings = [match(record, "naics") for record in naics]
    mappings.extend(match(record, "napcs") for record in napcs)
    exact_duplicate_groups = [ids for ids in exact.values() if len(ids) > 1]
    counts: dict[str, int] = defaultdict(int)
    for item in mappings:
        counts[str(item["status"])] += 1
    return {
        "schema_version": 1,
        "artifact_type": "multisource_universe_reconciliation_worklist",
        "warning": "Mappings other than accepted exact labels are proposals, not canonical market decisions.",
        "source_counts": {"naics_six_digit": len(naics), "napcs_products": len(napcs), "prior_seed_markets": len(seeds)},
        "candidate_markets": [
            {
                "candidate_market_id": item.record_id,
                "name": item.name,
                "status": "unvalidated_prior_model_seed",
                "source": "prior-model-normalized-markets-2026-11-05",
            }
            for item in seeds
        ],
        "mapping_counts": dict(sorted(counts.items())),
        "mappings": mappings,
        "exact_duplicate_seed_groups": exact_duplicate_groups,
        "required_next_actions": [
            "Review proposed mappings using buyer/job/delivery/workforce/economics/acquisition/AI identity tests.",
            "Resolve every unmatched NAICS row as add, split input, merge input, or explicit exclusion.",
            "Use NAPCS product rows to identify hidden submarkets and cross-industry service products.",
            "Publish append-only canonical market decisions with lineage.",
        ],
    }

