"""Rebuild phase2/human_prices.json from a fresh Data Entry CSV export - the
consensus-price ground truth fix_report_dates_from_human_prices.py validates
against. Run this whenever a new CSV export adds human rows, before rerunning
the fix script.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

CSV_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    Path.home() / "Downloads" / "Human vs LLM results(Data Entry) (1).csv"
)
OUT_PATH = BASE_DIR / "phase2" / "human_prices.json"


def parse_price(s: str) -> float | None:
    s = s.strip().replace("$", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main() -> None:
    with open(CSV_PATH, encoding="cp1252") as fh:
        rows = list(csv.reader(fh))
    data = rows[2:]  # row0 = banner, row1 = header

    out: dict[str, list[dict]] = {}
    skipped = 0
    for row in data:
        if len(row) < 11:
            continue
        company, ticker, year, quarter, rater, typ = (row[i].strip() for i in range(6))
        if not company or typ.lower() != "human":
            continue
        prior_close = parse_price(row[9])
        next_day_open = parse_price(row[10])
        if prior_close is None or next_day_open is None:
            skipped += 1
            continue
        key = f"{ticker}_{year}_{quarter}"
        out.setdefault(key, []).append({
            "rater": rater,
            "prior_close": prior_close,
            "next_day_open": next_day_open,
        })

    OUT_PATH.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {len(out)} combos ({sum(len(v) for v in out.values())} human price rows) -> {OUT_PATH}")
    print(f"Skipped {skipped} human rows with no price data")


if __name__ == "__main__":
    main()
