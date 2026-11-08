from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from turbo.pipeline_paths import ROOT


SNAPSHOT_ID = "census-napcs-2022-trilateral-hierarchy"
EXPECTED_PUBLISHER = "United States Census Bureau"
EXPECTED_DATASET = "2022 NAPCS six-level hierarchy"
EXPECTED_CAPTURE_METHOD = (
    "same-origin browser fetch; response entity bytes after normal HTTP "
    "content decoding"
)
CAPTURE = (
    ROOT
    / "data/source_snapshots/2022-napcs-trilateral-hierarchy-browser-capture.json"
)
EXPECTED_SECTIONS = (
    "11",
    "14",
    "17",
    "21",
    "24",
    "27",
    "31",
    "34",
    "37",
    "41",
    "44",
    "47",
    "51",
    "54",
    "57",
    "61",
    "64",
    "67",
    "71",
    "74",
    "77",
    "81",
    "84",
    "87",
)
LEVEL_BY_LENGTH = {
    2: (1, "section"),
    3: (2, "subsection"),
    5: (3, "division"),
    7: (4, "group"),
    9: (5, "subgroup"),
    11: (6, "trilateral_product"),
}
PARENT_LENGTH = {3: 2, 5: 3, 7: 5, 9: 7, 11: 9}
EXPECTED_LEVEL_COUNTS = {
    "section": 24,
    "subsection": 60,
    "division": 169,
    "group": 274,
    "subgroup": 496,
    "trilateral_product": 1_159,
}


@dataclass(frozen=True)
class NapcsHierarchyPage:
    section: str
    requested_url: str
    final_url: str
    retrieved_at_utc: str
    status: int
    content_type: str
    headers: dict[str, str]
    byte_length: int
    sha256: str
    body: bytes


@dataclass(frozen=True)
class NapcsHierarchyNode:
    code: str
    raw_title: str
    level: int
    level_name: str
    section: str
    source_row_number: int
    locator: str
    snapshot_id: str
    parent_code: str | None
    expected_parent_code: str | None
    parent_status: str


class _HierarchyTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.table_depth = 0
        self.in_data_table = False
        self.in_row = False
        self.in_cell = False
        self.cells: list[list[str]] = []
        self.rows: list[tuple[int, str, str]] = []
        self.row_number = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        if tag == "table":
            classes = set((attributes.get("class") or "").split())
            if self.in_data_table:
                self.table_depth += 1
            elif "data" in classes:
                self.in_data_table = True
                self.table_depth = 1
        elif self.in_data_table and tag == "tr":
            self.in_row = True
            self.cells = []
            self.row_number += 1
        elif self.in_row and tag in {"td", "th"}:
            self.in_cell = True
            self.cells.append([])

    def handle_endtag(self, tag: str) -> None:
        if self.in_cell and tag in {"td", "th"}:
            self.in_cell = False
        elif self.in_row and tag == "tr":
            values = [" ".join("".join(cell).split()) for cell in self.cells]
            if len(values) >= 2 and values[0].isdigit() and values[1]:
                self.rows.append((self.row_number, values[0], values[1]))
            self.in_row = False
            self.cells = []
        elif self.in_data_table and tag == "table":
            self.table_depth -= 1
            if self.table_depth == 0:
                self.in_data_table = False

    def handle_data(self, data: str) -> None:
        if self.in_cell and self.cells:
            self.cells[-1].append(data)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_utc(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"NAPCS hierarchy capture {field} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            f"NAPCS hierarchy capture {field} must be a UTC timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"NAPCS hierarchy capture {field} must be a UTC timestamp")
    return value


def capture_pages(path: Path = CAPTURE) -> list[NapcsHierarchyPage]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("NAPCS hierarchy capture has unexpected schema_version")
    if payload.get("publisher") != EXPECTED_PUBLISHER:
        raise ValueError("NAPCS hierarchy capture has unexpected publisher")
    if payload.get("dataset") != EXPECTED_DATASET:
        raise ValueError("NAPCS hierarchy capture has unexpected dataset")
    if payload.get("capture_method") != EXPECTED_CAPTURE_METHOD:
        raise ValueError("NAPCS hierarchy capture has unexpected capture method")
    _require_utc(payload.get("generated_at_utc"), "generated_at_utc")
    if payload.get("page_count") != len(EXPECTED_SECTIONS):
        raise ValueError("NAPCS hierarchy capture must declare exactly 24 pages")
    raw_pages = payload.get("pages")
    if not isinstance(raw_pages, list) or len(raw_pages) != len(EXPECTED_SECTIONS):
        raise ValueError("NAPCS hierarchy capture must contain exactly 24 pages")

    pages: list[NapcsHierarchyPage] = []
    for raw_page in raw_pages:
        section = str(raw_page.get("section", ""))
        expected_url = (
            "https://www.census.gov/naics/napcs/sections/"
            f"section{section}.html"
        )
        try:
            body = base64.b64decode(raw_page["body_base64"], validate=True)
        except (KeyError, ValueError) as error:
            raise ValueError(
                f"NAPCS hierarchy section {section} has invalid base64 body"
            ) from error
        if raw_page.get("status") != 200:
            raise ValueError(
                f"NAPCS hierarchy section {section} is not an HTTP 200 response"
            )
        if raw_page.get("requested_url") != expected_url:
            raise ValueError(
                f"NAPCS hierarchy section {section} has unexpected requested URL"
            )
        if raw_page.get("final_url") != expected_url:
            raise ValueError(
                f"NAPCS hierarchy section {section} has unexpected final URL"
            )
        if raw_page.get("byte_length") != len(body):
            raise ValueError(
                f"NAPCS hierarchy section {section} byte length does not match"
            )
        if raw_page.get("sha256") != _sha256(body):
            raise ValueError(
                f"NAPCS hierarchy section {section} SHA-256 does not match"
            )
        content_type = str(raw_page.get("content_type", ""))
        if "text/html" not in content_type.lower():
            raise ValueError(
                f"NAPCS hierarchy section {section} is not an HTML response"
            )
        headers = raw_page.get("headers")
        if not isinstance(headers, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in headers.items()
        ):
            raise ValueError(
                f"NAPCS hierarchy section {section} has invalid response headers"
            )
        retrieved_at_utc = _require_utc(
            raw_page.get("retrieved_at_utc"),
            f"section {section} retrieved_at_utc",
        )
        text = body.decode("utf-8", errors="strict")
        if "2022 North American Product Classification System" not in text:
            raise ValueError(
                f"NAPCS hierarchy section {section} lacks the official title"
            )
        if "2022 NAPCS Code" not in text:
            raise ValueError(
                f"NAPCS hierarchy section {section} lacks the hierarchy table"
            )
        if "Bad Gateway" in text or "cf-error" in text.lower():
            raise ValueError(
                f"NAPCS hierarchy section {section} contains a gateway response"
            )
        pages.append(
            NapcsHierarchyPage(
                section=section,
                requested_url=expected_url,
                final_url=expected_url,
                retrieved_at_utc=retrieved_at_utc,
                status=200,
                content_type=content_type,
                headers=dict(sorted(headers.items())),
                byte_length=len(body),
                sha256=_sha256(body),
                body=body,
            )
        )

    sections = tuple(page.section for page in pages)
    if sections != EXPECTED_SECTIONS:
        raise ValueError(
            "NAPCS hierarchy capture sections are missing, duplicated, or out of order"
        )
    return pages


def parse_napcs_hierarchy(path: Path = CAPTURE) -> list[NapcsHierarchyNode]:
    pages = capture_pages(path)
    located_rows: list[tuple[NapcsHierarchyPage, int, str, str]] = []
    for page in pages:
        parser = _HierarchyTableParser()
        parser.feed(page.body.decode("utf-8"))
        parser.close()
        if not parser.rows:
            raise ValueError(
                f"NAPCS hierarchy section {page.section} has no parsed rows"
            )
        for row_number, code, title in parser.rows:
            if not code.startswith(page.section):
                raise ValueError(
                    f"NAPCS code {code} appears on unexpected section {page.section}"
                )
            if len(code) not in LEVEL_BY_LENGTH:
                raise ValueError(f"NAPCS code {code} has an unexpected length")
            located_rows.append((page, row_number, code, title))

    codes = [code for _, _, code, _ in located_rows]
    if len(codes) != len(set(codes)):
        raise ValueError("NAPCS hierarchy contains duplicate published codes")
    known_codes = set(codes)
    nodes: list[NapcsHierarchyNode] = []
    for page, row_number, code, title in located_rows:
        level, level_name = LEVEL_BY_LENGTH[len(code)]
        parent_length = PARENT_LENGTH.get(len(code))
        expected_parent_code = code[:parent_length] if parent_length else None
        if expected_parent_code is None:
            parent_code = None
            parent_status = "root"
        elif expected_parent_code in known_codes:
            parent_code = expected_parent_code
            parent_status = "published_parent"
        else:
            parent_code = None
            parent_status = "missing_published_parent"
        nodes.append(
            NapcsHierarchyNode(
                code=code,
                raw_title=title,
                level=level,
                level_name=level_name,
                section=page.section,
                source_row_number=row_number,
                locator=(
                    f"section{page.section}.html:table.data:row:{row_number}:"
                    f"code:{code}"
                ),
                snapshot_id=SNAPSHOT_ID,
                parent_code=parent_code,
                expected_parent_code=expected_parent_code,
                parent_status=parent_status,
            )
        )

    level_counts = {
        level_name: sum(node.level_name == level_name for node in nodes)
        for level_name in EXPECTED_LEVEL_COUNTS
    }
    if level_counts != EXPECTED_LEVEL_COUNTS:
        raise ValueError(
            f"NAPCS hierarchy level counts changed: {level_counts}"
        )
    anomalies = [node for node in nodes if node.parent_status == "missing_published_parent"]
    if [
        (node.code, node.expected_parent_code)
        for node in anomalies
    ] != [("1110201", "11102")]:
        raise ValueError(
            "NAPCS hierarchy published-parent anomaly set changed"
        )
    return nodes


def napcs_hierarchy_artifacts(
    path: Path = CAPTURE,
) -> tuple[dict[str, object], dict[str, object]]:
    pages = capture_pages(path)
    nodes = parse_napcs_hierarchy(path)
    product_codes = {
        node.code for node in nodes if node.level_name == "trilateral_product"
    }

    # Imported lazily to keep the raw hierarchy parser independent of the
    # collection/trilateral concordance parser.
    from turbo.universe.identity_sources import (
        parse_collection_to_trilateral,
        parse_trilateral_to_collection,
    )

    concordance_codes = {
        row.trilateral_code
        for rows in (
            parse_collection_to_trilateral(),
            parse_trilateral_to_collection(),
        )
        for row in rows
        if row.trilateral_code not in {"", "NA"}
    }
    hierarchy_only_products = sorted(product_codes - concordance_codes)
    concordance_only_products = sorted(concordance_codes - product_codes)
    if len(hierarchy_only_products) != 87 or concordance_only_products:
        raise ValueError(
            "NAPCS hierarchy/concordance product coverage changed: "
            f"hierarchy_only={len(hierarchy_only_products)}, "
            f"concordance_only={len(concordance_only_products)}"
        )

    level_counts = {
        level_name: sum(node.level_name == level_name for node in nodes)
        for level_name in EXPECTED_LEVEL_COUNTS
    }
    anomalies = [
        {
            "code": node.code,
            "expected_parent_code": node.expected_parent_code,
            "locator": node.locator,
            "snapshot_id": node.snapshot_id,
        }
        for node in nodes
        if node.parent_status == "missing_published_parent"
    ]
    page_records = [
        {
            "section": page.section,
            "requested_url": page.requested_url,
            "final_url": page.final_url,
            "retrieved_at_utc": page.retrieved_at_utc,
            "status": page.status,
            "content_type": page.content_type,
            "headers": page.headers,
            "byte_length": page.byte_length,
            "sha256": page.sha256,
        }
        for page in pages
    ]
    summary = {
        "schema_version": 1,
        "artifact_type": "napcs_trilateral_hierarchy_source_summary",
        "warning": (
            "Published hierarchy identities are source evidence, not accepted "
            "canonical operating markets."
        ),
        "snapshot_id": SNAPSHOT_ID,
        "pages": len(pages),
        "response_entity_bytes": sum(page.byte_length for page in pages),
        "nodes": len(nodes),
        "level_counts": level_counts,
        "hierarchy_only_products": len(hierarchy_only_products),
        "concordance_products": len(concordance_codes),
        "published_parent_anomalies": len(anomalies),
    }
    evidence = {
        "schema_version": 1,
        "artifact_type": "napcs_trilateral_hierarchy_evidence",
        "warning": (
            "Published hierarchy identities are source evidence, not accepted "
            "canonical operating markets."
        ),
        "snapshot_id": SNAPSHOT_ID,
        "pages": page_records,
        "nodes": [asdict(node) for node in nodes],
        "hierarchy_only_product_codes": hierarchy_only_products,
        "published_parent_anomalies": anomalies,
    }
    return summary, evidence
