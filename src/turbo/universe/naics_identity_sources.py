from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader

from turbo.pipeline_paths import ROOT
from turbo.universe.naics import parse_naics, read_first_sheet


SNAPSHOTS = ROOT / "data/source_snapshots"
STRUCTURE = SNAPSHOTS / "2022-naics-structure.xlsx"
MANUAL = SNAPSHOTS / "2022-naics-manual.pdf"
FORWARD_CONCORDANCE = SNAPSHOTS / "2017-to-2022-naics-concordance.xlsx"
REVERSE_CONCORDANCE = SNAPSHOTS / "2022-to-2017-naics-concordance.xlsx"
FORWARD_BRIDGE = SNAPSHOTS / "2022-ecn-naics-bridge-2017-to-2022.zip"
REVERSE_BRIDGE = SNAPSHOTS / "2022-ecn-naics-bridge-2022-to-2017.zip"


@dataclass(frozen=True)
class NaicsConcordanceRecord:
    direction: str
    row_number: int
    naics_2017_code: str
    naics_2017_title: str
    naics_2022_code: str
    naics_2022_title: str
    snapshot_id: str


@dataclass(frozen=True)
class NaicsIndexEntry:
    ordinal: int
    naics_2022_code: str
    page: int
    column: int
    y: float
    raw_fragments: tuple[str, ...]
    normalized_label: str

    @property
    def locator(self) -> str:
        return (
            f"pdf:page:{self.page}:column:{self.column}:y:{self.y}:"
            f"entry:{self.ordinal}"
        )


@dataclass(frozen=True)
class NaicsIndexCrossReference:
    ordinal: int
    page: int
    column: int
    y: float
    raw_fragments: tuple[str, ...]
    normalized_label: str

    @property
    def locator(self) -> str:
        return (
            f"pdf:page:{self.page}:column:{self.column}:y:{self.y}:"
            f"cross-reference:{self.ordinal}"
        )


def _clean(value: str) -> str:
    return " ".join(value.split())


def parse_naics_concordance(
    path: Path,
    direction: str,
    snapshot_id: str,
) -> list[NaicsConcordanceRecord]:
    if direction not in {"2017_to_2022", "2022_to_2017"}:
        raise ValueError(f"unsupported NAICS concordance direction: {direction}")
    records: list[NaicsConcordanceRecord] = []
    for row_number, row in enumerate(read_first_sheet(path), start=1):
        row = [*row, *("" for _ in range(max(0, 4 - len(row))))]
        if direction == "2017_to_2022":
            code_2017, title_2017, code_2022, title_2022 = row[:4]
        else:
            code_2022, title_2022, code_2017, title_2017 = row[:4]
        code_2017 = code_2017.strip()
        code_2022 = code_2022.strip()
        if not (
            len(code_2017) == 6
            and code_2017.isdigit()
            and len(code_2022) == 6
            and code_2022.isdigit()
        ):
            continue
        records.append(
            NaicsConcordanceRecord(
                direction=direction,
                row_number=row_number,
                naics_2017_code=code_2017,
                naics_2017_title=_clean(title_2017),
                naics_2022_code=code_2022,
                naics_2022_title=_clean(title_2022),
                snapshot_id=snapshot_id,
            )
        )
    return records


def _valid_six_digit_codes() -> set[str]:
    return {
        node.source_code
        for node in parse_naics(STRUCTURE)
        if node.level == 6
    }


@lru_cache(maxsize=1)
def _parse_naics_manual_index_rows() -> tuple[
    tuple[NaicsIndexEntry, ...],
    tuple[NaicsIndexCrossReference, ...],
]:
    valid_codes = _valid_six_digit_codes()
    reader = PdfReader(str(MANUAL))
    frames: list[tuple[int, int, float, list[list[object]]]] = []

    # The manual's alphabetic index occupies physical PDF pages 637 through 958.
    # Coordinates are measured against the immutable pinned PDF. Parsing columns
    # separately prevents right-column text from being joined to left-column rows.
    for page_number in range(637, 959):
        spans: list[dict[str, object]] = []

        def visit(
            text: str,
            _cm: list[float],
            tm: list[float],
            _font: object,
            _size: float,
        ) -> None:
            raw = text.replace("\n", "")
            if raw.strip():
                spans.append({"x": float(tm[4]), "y": float(tm[5]), "text": raw})

        reader.pages[page_number - 1].extract_text(visitor_text=visit)
        for column, (xmin, xmax, code_band_max) in enumerate(
            ((60.0, 306.0, 110.0), (306.0, 550.0, 362.0)),
            start=1,
        ):
            selected = [
                span
                for span in spans
                if xmin <= float(span["x"]) < xmax
                and 60.0 <= float(span["y"]) <= 720.0
            ]
            lines: list[list[object]] = []
            for span in sorted(
                selected,
                key=lambda item: (-float(item["y"]), float(item["x"])),
            ):
                if not lines or abs(float(lines[-1][0]) - float(span["y"])) > 0.35:
                    lines.append([float(span["y"]), [span]])
                else:
                    lines[-1][1].append(span)  # type: ignore[union-attr]
            frames.append((page_number, column, code_band_max, lines))

    raw_rows: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for page_number, column, code_band_max, lines in frames:
        for y, untyped_spans in lines:
            line_spans = sorted(
                untyped_spans,  # type: ignore[arg-type]
                key=lambda item: float(item["x"]),
            )
            code_band = "".join(
                str(span["text"])
                for span in line_spans
                if float(span["x"]) < code_band_max
            )
            code_band = "".join(code_band.split())
            same_line_text = "".join(
                str(span["text"])
                for span in line_spans
                if float(span["x"]) >= code_band_max
            ).strip()
            if code_band in valid_codes or code_band == "******":
                if current is not None:
                    raw_rows.append(current)
                current = {
                    "row_kind": (
                        "coded_entry" if code_band in valid_codes else "cross_reference"
                    ),
                    "code": code_band if code_band in valid_codes else "",
                    "page": page_number,
                    "column": column,
                    "y": round(float(y), 2),
                    "fragments": [same_line_text] if same_line_text else [],
                }
            elif current is not None and same_line_text:
                current["fragments"].append(same_line_text)  # type: ignore[union-attr]
    if current is not None:
        raw_rows.append(current)

    coded_rows = [value for value in raw_rows if value["row_kind"] == "coded_entry"]
    cross_reference_rows = [
        value for value in raw_rows if value["row_kind"] == "cross_reference"
    ]
    entries = tuple(
        NaicsIndexEntry(
            ordinal=ordinal,
            naics_2022_code=str(value["code"]),
            page=int(value["page"]),
            column=int(value["column"]),
            y=float(value["y"]),
            raw_fragments=tuple(str(fragment) for fragment in value["fragments"]),
            normalized_label=_clean(" ".join(value["fragments"])),  # type: ignore[arg-type]
        )
        for ordinal, value in enumerate(coded_rows, start=1)
    )
    cross_references = tuple(
        NaicsIndexCrossReference(
            ordinal=ordinal,
            page=int(value["page"]),
            column=int(value["column"]),
            y=float(value["y"]),
            raw_fragments=tuple(str(fragment) for fragment in value["fragments"]),
            normalized_label=_clean(" ".join(value["fragments"])),  # type: ignore[arg-type]
        )
        for ordinal, value in enumerate(cross_reference_rows, start=1)
    )
    if any(not entry.normalized_label for entry in entries):
        raise ValueError("NAICS manual index contains an empty reconstructed entry")
    if any(not entry.normalized_label for entry in cross_references):
        raise ValueError("NAICS manual index contains an empty cross-reference row")
    return entries, cross_references


def parse_naics_manual_index() -> tuple[NaicsIndexEntry, ...]:
    return _parse_naics_manual_index_rows()[0]


def parse_naics_manual_index_cross_references() -> tuple[
    NaicsIndexCrossReference, ...
]:
    return _parse_naics_manual_index_rows()[1]


def _bridge_rows(
    path: Path,
    member: str,
    snapshot_id: str,
    direction: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with zipfile.ZipFile(path) as archive:
        with archive.open(member) as raw:
            with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
                for row_number, row in enumerate(
                    csv.DictReader(text, delimiter="|"),
                    start=2,
                ):
                    records.append(
                        {
                            "direction": direction,
                            "snapshot_id": snapshot_id,
                            "locator": f"{member}:row:{row_number}",
                            "row_number": row_number,
                            "observation_kind": (
                                "industry_total"
                                if row.get("NAICS2017BDG") == "00000000"
                                or row.get("NAICS2022BDG") == "00000000"
                                else "bridge_component"
                            ),
                            "raw_fields": dict(row),
                        }
                    )
    return records


@lru_cache(maxsize=1)
def naics_identity_source_artifacts() -> tuple[dict[str, object], dict[str, object]]:
    forward = parse_naics_concordance(
        FORWARD_CONCORDANCE,
        "2017_to_2022",
        "census-naics-2017-to-2022-concordance",
    )
    reverse = parse_naics_concordance(
        REVERSE_CONCORDANCE,
        "2022_to_2017",
        "census-naics-2022-to-2017-concordance",
    )
    forward_pairs = {
        (row.naics_2017_code, row.naics_2022_code) for row in forward
    }
    reverse_pairs = {
        (row.naics_2017_code, row.naics_2022_code) for row in reverse
    }
    if forward_pairs != reverse_pairs:
        raise ValueError("full NAICS concordance directions do not reverse exactly")

    by_pair: dict[tuple[str, str], list[NaicsConcordanceRecord]] = defaultdict(list)
    for row in [*forward, *reverse]:
        by_pair[(row.naics_2017_code, row.naics_2022_code)].append(row)
    index_entries = parse_naics_manual_index()
    index_cross_references = parse_naics_manual_index_cross_references()
    valid_codes = _valid_six_digit_codes()
    represented_index_codes = {entry.naics_2022_code for entry in index_entries}
    if not represented_index_codes <= valid_codes:
        raise ValueError("NAICS index references a code outside the 2022 structure")

    forward_bridge = _bridge_rows(
        FORWARD_BRIDGE,
        "ECNBRIDGE22022.dat",
        "census-economic-census-2022-naics-bridge-2017-to-2022",
        "2017_to_2022",
    )
    reverse_bridge = _bridge_rows(
        REVERSE_BRIDGE,
        "ECNBRIDGE12022.dat",
        "census-economic-census-2022-naics-bridge-2022-to-2017",
        "2022_to_2017",
    )
    if len(index_entries) != 20_373:
        raise ValueError(
            f"expected 20,373 coded NAICS manual index entries, found {len(index_entries)}"
        )
    if len(index_cross_references) != 25:
        raise ValueError(
            "expected 25 uncoded NAICS manual index cross-reference rows, "
            f"found {len(index_cross_references)}"
        )
    if valid_codes - represented_index_codes != {"112130", "541120"}:
        raise ValueError("unexpected six-digit coverage in the NAICS manual index")
    if len(forward) != 1_150 or len(reverse) != 1_150:
        raise ValueError("full NAICS concordance row count changed")
    if len(forward_bridge) != 444 or len(reverse_bridge) != 402:
        raise ValueError("Economic Census NAICS bridge row count changed")
    changed_pairs = {
        pair for pair in forward_pairs if pair[0] != pair[1]
    }
    outgoing = Counter(pair[0] for pair in changed_pairs)
    incoming = Counter(pair[1] for pair in changed_pairs)
    all_outgoing = Counter(pair[0] for pair in forward_pairs)
    all_incoming = Counter(pair[1] for pair in forward_pairs)
    bridge_observations = [*forward_bridge, *reverse_bridge]
    summary = {
        "schema_version": 1,
        "artifact_type": "official_naics_identity_source_summary",
        "warning": (
            "Index terms, vintage concordances, and bridge observations are identity "
            "evidence; they are not canonical operating markets or market scores."
        ),
        "manual_index": {
            "coded_entries": len(index_entries),
            "uncoded_cross_reference_rows": len(index_cross_references),
            "total_rows": len(index_entries) + len(index_cross_references),
            "represented_six_digit_codes": len(represented_index_codes),
            "missing_six_digit_codes": sorted(valid_codes - represented_index_codes),
            "physical_pdf_pages": [637, 958],
        },
        "full_concordance": {
            "forward_rows": len(forward),
            "reverse_rows": len(reverse),
            "unique_pairs": len(forward_pairs),
            "unique_2017_codes": len({pair[0] for pair in forward_pairs}),
            "unique_2022_codes": len({pair[1] for pair in forward_pairs}),
            "same_code_pairs": len(forward_pairs - changed_pairs),
            "changed_pairs": len(changed_pairs),
            "changed_2017_codes": len(outgoing),
            "changed_2022_codes": len(incoming),
            "split_2017_codes": sum(count > 1 for count in all_outgoing.values()),
            "merged_2022_codes": sum(count > 1 for count in all_incoming.values()),
            "directions_exact_reverses": True,
        },
        "economic_census_bridges": {
            "2017_to_2022_observations": len(forward_bridge),
            "2022_to_2017_observations": len(reverse_bridge),
            "industry_total_observations": sum(
                row["observation_kind"] == "industry_total"
                for row in bridge_observations
            ),
            "component_observations": sum(
                row["observation_kind"] == "bridge_component"
                for row in bridge_observations
            ),
        },
    }
    details = {
        "schema_version": 1,
        "artifact_type": "official_naics_identity_evidence",
        "warning": summary["warning"],
        "manual_index_entries": [
            {
                **asdict(entry),
                "identity_id": f"identity:naics:{entry.naics_2022_code}",
                "locator": entry.locator,
                "snapshot_id": "census-naics-2022-manual",
            }
            for entry in index_entries
        ],
        "manual_index_cross_references": [
            {
                **asdict(entry),
                "locator": entry.locator,
                "snapshot_id": "census-naics-2022-manual",
            }
            for entry in index_cross_references
        ],
        "vintage_lineage_relationships": [
            {
                "naics_2017_code": code_2017,
                "naics_2022_identity_id": f"identity:naics:{code_2022}",
                "relationship_type": "official_vintage_concordance",
                "source_observations": [
                    {
                        **asdict(row),
                        "locator": f"first_sheet:row:{row.row_number}",
                    }
                    for row in sorted(
                        rows,
                        key=lambda item: (item.direction, item.row_number),
                    )
                ],
            }
            for (code_2017, code_2022), rows in sorted(by_pair.items())
        ],
        "economic_census_bridge_observations": bridge_observations,
    }
    return summary, details
