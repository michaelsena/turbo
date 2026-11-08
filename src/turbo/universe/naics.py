from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from turbo.models import MarketNode

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _clean_title(value: str) -> tuple[str, str | None]:
    title = " ".join(value.split())
    if title.endswith("T"):
        return title[:-1].strip(), "trilateral"
    return title, None


def _column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference)
    if letters is None:
        raise ValueError(f"invalid cell reference: {reference}")
    result = 0
    for character in letters.group(0):
        result = result * 26 + ord(character) - ord("A") + 1
    return result - 1


def read_sheet(path: Path, sheet_number: int = 1) -> list[list[str]]:
    if sheet_number < 1:
        raise ValueError("sheet_number must be at least 1")
    with zipfile.ZipFile(path) as book:
        shared_root = ET.fromstring(book.read("xl/sharedStrings.xml"))
        shared = [
            "".join(text.text or "" for text in item.iter(NS + "t"))
            for item in shared_root.findall(NS + "si")
        ]
        sheet = ET.fromstring(book.read(f"xl/worksheets/sheet{sheet_number}.xml"))
    rows: list[list[str]] = []
    for row in sheet.iter(NS + "row"):
        indexed: dict[int, str] = {}
        for cell in row.findall(NS + "c"):
            raw = cell.find(NS + "v")
            value = "" if raw is None or raw.text is None else raw.text
            if cell.get("t") == "s" and value:
                value = shared[int(value)]
            indexed[_column_index(cell.get("r", ""))] = value
        width = max(indexed, default=-1) + 1
        values = [indexed.get(index, "") for index in range(width)]
        rows.append(values)
    return rows


def read_first_sheet(path: Path) -> list[list[str]]:
    return read_sheet(path, 1)


def _sector_parent(code: str, sectors: list[str]) -> str | None:
    prefix = int(code[:2])
    for sector in sectors:
        if "-" in sector:
            low, high = (int(part) for part in sector.split("-", 1))
            if low <= prefix <= high:
                return sector
        elif sector == code[:2]:
            return sector
    return None


def parse_naics(path: Path) -> list[MarketNode]:
    records: list[tuple[str, str, str, str | None]] = []
    for row in read_first_sheet(path):
        if len(row) < 3:
            continue
        code = row[1].strip()
        if not re.fullmatch(r"\d{2}(?:-\d{2})?|\d{3,6}", code):
            continue
        raw_title = " ".join(row[2].split())
        title, indicator = _clean_title(row[2])
        records.append((code, title, raw_title, indicator))

    codes = {code for code, *_ in records}
    sectors = [code for code, *_ in records if len(code) == 2 or "-" in code]
    nodes: list[MarketNode] = []
    for code, title, raw_title, indicator in records:
        level = 2 if "-" in code else len(code)
        parent_code: str | None = None
        if level > 2:
            for length in range(level - 1, 2, -1):
                candidate = code[:length]
                if candidate in codes:
                    parent_code = candidate
                    break
            if parent_code is None:
                parent_code = _sector_parent(code, sectors)
        lineage = ("census-naics-2022", f"naics:{code}")
        nodes.append(
            MarketNode(
                node_id=f"naics-{code}",
                source_code=code,
                title=title,
                raw_title=raw_title,
                source_indicator=indicator,
                level=level,
                parent_id=f"naics-{parent_code}" if parent_code else None,
                node_type="source_category",
                lineage=lineage,
            )
        )
    return nodes

