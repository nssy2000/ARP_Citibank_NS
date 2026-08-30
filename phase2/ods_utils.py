"""Shared helper for reading Master_Data_NEW.ods, which is malformed OOXML -
pandas/odfpy raise `duplicate attribute`/ExpatError on it. Read the raw
content.xml with a recovering lxml parser instead (documented in CLAUDE.md's
Live sheet section)."""
from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

NS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}
TABLE_NAME_ATTR = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}name"
COLS_REPEATED_ATTR = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}number-columns-repeated"
ROWS_REPEATED_ATTR = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}number-rows-repeated"


def load_ods_root(ods_path: Path):
    with zipfile.ZipFile(ods_path) as z:
        content = z.read("content.xml")
    return etree.fromstring(content, parser=etree.XMLParser(recover=True, huge_tree=True))


def _cell_text(cell) -> str:
    texts = cell.findall(".//text:p", NS)
    return " ".join((t.text or "") + "".join(c.text or "" for c in t) for t in texts).strip()


def load_table_rows(root, name: str, max_cols: int = 21) -> list[list[str]]:
    """Rows for table `name` (header included), each row truncated to
    max_cols cells. Raises ValueError if the table isn't found."""
    for t in root.findall(".//table:table", NS):
        if t.get(TABLE_NAME_ATTR) != name:
            continue
        rows: list[list[str]] = []
        for r in t.findall("table:table-row", NS):
            row: list[str] = []
            col_count = 0
            for c in r.findall("table:table-cell", NS):
                rep = int(c.get(COLS_REPEATED_ATTR, "1"))
                val = _cell_text(c)
                for _ in range(rep):
                    if col_count < max_cols:
                        row.append(val)
                    col_count += 1
            # Note: a trailing "fill the rest of the sheet" row can carry a
            # huge number-rows-repeated (observed up to ~1,048,576, Excel's
            # max row count) - this expands to that many list entries. Kept
            # as-is: harmless today since callers filter on non-empty cells,
            # but don't assume `rows` here is bounded by real sheet content.
            row_rep = int(r.get(ROWS_REPEATED_ATTR, "1"))
            rows.extend([row] * row_rep)
        return rows
    raise ValueError(f"table {name!r} not found")
