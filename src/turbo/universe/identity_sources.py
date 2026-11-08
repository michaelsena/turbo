from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

from turbo.pipeline_paths import ROOT
from turbo.universe.naics import read_sheet

SNAPSHOTS = ROOT / "data/source_snapshots"
COLLECTION_TO_TRILATERAL = SNAPSHOTS / "2022-napcs-collection-to-trilateral.xlsx"
TRILATERAL_TO_COLLECTION = SNAPSHOTS / "2022-napcs-trilateral-to-collection.xlsx"
INDUSTRY_BY_PRODUCTS = SNAPSHOTS / "2022-ecn-industry-by-products.zip"
PRODUCTS_BY_INDUSTRY = SNAPSHOTS / "2022-ecn-products-by-industry.zip"


@dataclass(frozen=True)
class NapcsConcordanceRecord:
    collection_code: str
    collection_description: str
    trilateral_code: str
    trilateral_description: str
    part_indicator: str


def parse_collection_to_trilateral() -> list[NapcsConcordanceRecord]:
    records: list[NapcsConcordanceRecord] = []
    for row in read_sheet(COLLECTION_TO_TRILATERAL, 2)[1:]:
        if not row or not row[0].strip():
            continue
        row = [*row, *([""] * (6 - len(row)))]
        records.append(
            NapcsConcordanceRecord(
                collection_code=row[0].strip(),
                collection_description=" ".join(row[2].split()),
                trilateral_code=row[3].strip(),
                part_indicator=row[4].strip(),
                trilateral_description=" ".join(row[5].split()),
            )
        )
    return records


def parse_trilateral_to_collection() -> list[NapcsConcordanceRecord]:
    records: list[NapcsConcordanceRecord] = []
    for row in read_sheet(TRILATERAL_TO_COLLECTION, 2)[1:]:
        if not row or not row[0].strip():
            continue
        row = [*row, *([""] * (5 - len(row)))]
        records.append(
            NapcsConcordanceRecord(
                collection_code=row[3].strip(),
                collection_description=" ".join(row[4].split()),
                trilateral_code=row[0].strip(),
                part_indicator=row[1].strip(),
                trilateral_description=" ".join(row[2].split()),
            )
        )
    return records


def iter_pipe_rows(path: Path, member: str) -> Iterator[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        with archive.open(member) as raw:
            with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
                yield from csv.DictReader(text, delimiter="|")


def _relationship_file_data(
    path: Path,
    member: str,
) -> tuple[dict[str, object], set[tuple[str, str]], dict[str, str]]:
    rows = 0
    national_rows = 0
    national_six_digit_rows = 0
    unique_national_six_digit_pairs: set[tuple[str, str]] = set()
    product_labels: dict[str, str] = {}
    for row in iter_pipe_rows(path, member):
        rows += 1
        if row.get("GEO_ID") != "0100000US":
            continue
        national_rows += 1
        naics = row.get("NAICS2022", "")
        napcs = row.get("NAPCS2022", "")
        if len(naics) == 6 and naics.isdigit() and napcs != "0000000000":
            national_six_digit_rows += 1
            unique_national_six_digit_pairs.add((naics, napcs))
            product_labels.setdefault(
                napcs,
                " ".join(row.get("NAPCS2022_LABEL", "").split()),
            )
    return {
        "rows": rows,
        "national_rows": national_rows,
        "national_six_digit_rows": national_six_digit_rows,
        "unique_national_six_digit_naics_napcs_pairs": len(unique_national_six_digit_pairs),
    }, unique_national_six_digit_pairs, product_labels


def relationship_product_records() -> dict[str, str]:
    _, _, labels = _relationship_file_data(
        PRODUCTS_BY_INDUSTRY,
        "EC2200NAPCSPRDIND.dat",
    )
    return labels


def identity_source_artifacts() -> tuple[dict[str, object], dict[str, object]]:
    forward = parse_collection_to_trilateral()
    reverse = parse_trilateral_to_collection()
    forward_pairs = {(row.collection_code, row.trilateral_code) for row in forward}
    reverse_pairs = {(row.collection_code, row.trilateral_code) for row in reverse}
    industry_summary, industry_pairs, _ = _relationship_file_data(
        INDUSTRY_BY_PRODUCTS,
        "EC2200NAPCSINDPRD.dat",
    )
    product_summary, product_pairs, _ = _relationship_file_data(
        PRODUCTS_BY_INDUSTRY,
        "EC2200NAPCSPRDIND.dat",
    )
    summary = {
        "schema_version": 1,
        "artifact_type": "official_identity_source_summary",
        "warning": "Counts and observed relationships are identity evidence, not accepted canonical market mappings.",
        "collection_to_trilateral": {
            "rows": len(forward),
            "unique_pairs": len(forward_pairs),
            "part_rows": sum(row.part_indicator == "PT" for row in forward),
            "not_applicable_rows": sum(row.trilateral_code == "NA" for row in forward),
        },
        "trilateral_to_collection": {
            "rows": len(reverse),
            "unique_pairs": len(reverse_pairs),
            "part_rows": sum(row.part_indicator == "PT" for row in reverse),
        },
        "concordance_pair_difference": {
            "forward_only": len(forward_pairs - reverse_pairs),
            "reverse_only": len(reverse_pairs - forward_pairs),
        },
        "industry_by_products": industry_summary,
        "products_by_industry": product_summary,
        "sample_forward_records": [asdict(row) for row in forward[:5]],
    }
    concordance: dict[tuple[str, str], dict[str, set[str]]] = {}
    non_mappings: dict[str, set[str]] = {}
    for observed_in, rows in (
        ("collection_to_trilateral", forward),
        ("trilateral_to_collection", reverse),
    ):
        for row in rows:
            if row.trilateral_code in {"", "NA"}:
                non_mappings.setdefault(row.collection_code, set()).add(observed_in)
                continue
            key = (row.collection_code, row.trilateral_code)
            value = concordance.setdefault(
                key,
                {"part_indicators": set(), "observed_in": set()},
            )
            if row.part_indicator:
                value["part_indicators"].add(row.part_indicator)
            value["observed_in"].add(observed_in)
    all_pairs = industry_pairs | product_pairs
    relationships = {
        "schema_version": 1,
        "artifact_type": "official_identity_relationships",
        "warning": "These are observed source relationships, not accepted canonical market mappings.",
        "napcs_concordance_relationships": [
            {
                "collection_identity_id": f"identity:napcs-collection:{collection_code}",
                "trilateral_identity_id": f"identity:napcs-trilateral:{trilateral_code}",
                "part_indicators": sorted(value["part_indicators"]),
                "observed_in": sorted(value["observed_in"]),
                "source_observations": [
                    {
                        "snapshot_id": (
                            "census-napcs-2022-collection-to-trilateral"
                            if direction == "collection_to_trilateral"
                            else "census-napcs-2022-trilateral-to-collection"
                        ),
                        "locator": (
                            f"data_sheet:collection={collection_code}:"
                            f"trilateral={trilateral_code}"
                        ),
                    }
                    for direction in sorted(value["observed_in"])
                ],
            }
            for (collection_code, trilateral_code), value in sorted(concordance.items())
        ],
        "napcs_concordance_non_mappings": [
            {
                "collection_identity_id": f"identity:napcs-collection:{collection_code}",
                "disposition": "no_trilateral_mapping",
                "observed_in": sorted(observed_in),
                "source_observations": [
                    {
                        "snapshot_id": (
                            "census-napcs-2022-collection-to-trilateral"
                            if direction == "collection_to_trilateral"
                            else "census-napcs-2022-trilateral-to-collection"
                        ),
                        "locator": f"data_sheet:collection={collection_code}:trilateral=NA",
                    }
                    for direction in sorted(observed_in)
                ],
            }
            for collection_code, observed_in in sorted(non_mappings.items())
        ],
        "industry_product_relationships": [
            {
                "industry_identity_id": f"identity:naics:{naics}",
                "product_identity_id": f"identity:napcs-collection:{napcs}",
                "observed_in": sorted(
                    source
                    for source, pairs in (
                        ("industry_by_products", industry_pairs),
                        ("products_by_industry", product_pairs),
                    )
                    if (naics, napcs) in pairs
                ),
                "source_observations": [
                    {
                        "snapshot_id": (
                            "census-economic-census-2022-industry-by-products"
                            if source == "industry_by_products"
                            else "census-economic-census-2022-products-by-industry"
                        ),
                        "locator": (
                            "GEO_ID=0100000US:"
                            f"NAICS2022={naics}:NAPCS2022={napcs}"
                        ),
                    }
                    for source, pairs in (
                        ("industry_by_products", industry_pairs),
                        ("products_by_industry", product_pairs),
                    )
                    if (naics, napcs) in pairs
                ],
            }
            for naics, napcs in sorted(all_pairs)
        ],
    }
    summary["relationship_artifact_counts"] = {
        "napcs_concordance_relationships": len(
            relationships["napcs_concordance_relationships"]
        ),
        "napcs_concordance_non_mappings": len(
            relationships["napcs_concordance_non_mappings"]
        ),
        "industry_product_relationships": len(
            relationships["industry_product_relationships"]
        ),
    }
    return summary, relationships


def identity_source_summary() -> dict[str, object]:
    return identity_source_artifacts()[0]
