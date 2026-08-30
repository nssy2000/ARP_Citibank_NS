"""Diff Master_Data_NEW.ods's Human_Data_Entry against LLM_Data_Entry to find
gap combos (human has, LLM doesn't) and write phase2/gap_combos.json, the
resumability checkpoint the rest of the gap-onboarding pipeline reads/writes.

Safe to rerun any time: re-diffs from the ODS, but never overwrites an
existing gap_combos.json entry's progress fields - only adds combos that are
genuinely new to the tracker.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "phase2"))

from ods_utils import load_ods_root, load_table_rows  # noqa: E402

ODS_PATH = BASE_DIR / "Master_Data_NEW.ods"
OUT_PATH = BASE_DIR / "phase2" / "gap_combos.json"


HEADER_ROW = ("Company", "Ticker", "Year", "Quarter")


def parse_events(rows: list[list[str]]) -> dict[tuple[str, str, str], str]:
    """Returns {(ticker, year, quarter): company} for non-empty rows.

    Skips the header row by matching its exact text (case-sensitive) rather
    than a fixed row index - Master_Data_NEW.ods's Human_Data_Entry/
    LLM_Data_Entry tabs have a title-banner row above the real header row
    ("data rows start at row 3", per CLAUDE.md), and any banner-style
    preamble row is skipped anyway by the existing empty-cell check below.
    """
    events: dict[tuple[str, str, str], str] = {}
    for r in rows:
        if len(r) < 4:
            continue
        company, ticker, year, quarter = r[0].strip(), r[1].strip(), r[2].strip(), r[3].strip()
        if (company, ticker, year, quarter) == HEADER_ROW:
            continue
        if not ticker or not year or not quarter:
            continue
        events[(ticker.upper(), year, quarter)] = company
    return events


def compute_gap(
    human_events: dict[tuple[str, str, str], str],
    llm_events: dict[tuple[str, str, str], str],
) -> dict[tuple[str, str, str], str]:
    """Combos the human sheet has that the LLM sheet doesn't."""
    return {k: v for k, v in human_events.items() if k not in llm_events}


def main() -> None:
    root = load_ods_root(ODS_PATH)
    human_events = parse_events(load_table_rows(root, "Human_Data_Entry", max_cols=4))
    llm_events = parse_events(load_table_rows(root, "LLM_Data_Entry", max_cols=4))
    gap = compute_gap(human_events, llm_events)

    existing: dict[str, dict] = {}
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))

    out: dict[str, dict] = dict(existing)
    added = 0
    for (ticker, year, quarter), company in gap.items():
        key = f"{ticker}_{year}_{quarter}"
        if key in out:
            continue
        out[key] = {
            "ticker": ticker,
            "company": company,
            "year": year,
            "quarter": quarter,
            "status": "not_started",
            "slug": None,
            "sector": None,
            "is_sec_registrant": None,
            "cik": None,
            "report_date": None,
            "report_date_confidence": None,
            "documents": [],
            "news_document_written": False,
            "appended": False,
            "notes": "",
        }
        added += 1

    OUT_PATH.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Human combos: {len(human_events)}, LLM combos: {len(llm_events)}, gap: {len(gap)}")
    print(f"gap_combos.json: {len(out)} total tracked combos ({added} newly added this run)")
    statuses: dict[str, int] = {}
    for v in out.values():
        statuses[v["status"]] = statuses.get(v["status"], 0) + 1
    print(f"Status breakdown: {statuses}")


if __name__ == "__main__":
    main()
