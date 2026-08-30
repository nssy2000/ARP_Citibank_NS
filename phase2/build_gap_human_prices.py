"""Extend phase2/human_prices.json with consensus (Prior Close, Next Day
Open) pairs from Master_Data_NEW.ods's Human_Data_Entry tab, for gap combos
only. Column layout verified directly against the live sheet (not the plan's
original assumed layout, which was wrong - see git history/commit message
for details): Ticker=1, Year=2, Quarter=3, Rater=6, Prior Close ($)=13,
Next Day Open ($)=15 (0-indexed). Existing combos' entries (sourced from the
old CSV export) are left untouched. For gap combos, a (combo, rater) pair
already on file gets its prior_close/next_day_open overwritten if the sheet's
current value differs (handles a rater retyping a corrected price after a
misclick) - it only stays untouched when the value hasn't changed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "phase2"))

from ods_utils import load_ods_root, load_table_rows  # noqa: E402

ODS_PATH = BASE_DIR / "Master_Data_NEW.ods"
GAP_COMBOS_PATH = BASE_DIR / "phase2" / "gap_combos.json"
HUMAN_PRICES_PATH = BASE_DIR / "phase2" / "human_prices.json"

COL_TICKER, COL_YEAR, COL_QUARTER, COL_RATER = 1, 2, 3, 6
COL_PRIOR_CLOSE, COL_NEXT_DAY_OPEN = 13, 15

HEADER_ROW = ("Ticker", "Year", "Quarter")


def parse_price(s: str) -> float | None:
    s = s.strip().replace("$", "").replace(",", "").replace("−", "-")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main() -> None:
    gap_keys = set(json.loads(GAP_COMBOS_PATH.read_text(encoding="utf-8")).keys())
    human_prices = json.loads(HUMAN_PRICES_PATH.read_text(encoding="utf-8")) if HUMAN_PRICES_PATH.exists() else {}

    root = load_ods_root(ODS_PATH)
    rows = load_table_rows(root, "Human_Data_Entry", max_cols=16)

    added = 0
    updated = 0
    skipped_unparseable = 0
    for row in rows[1:]:
        if len(row) <= COL_NEXT_DAY_OPEN:
            continue
        ticker, year, quarter, rater = row[COL_TICKER].strip(), row[COL_YEAR].strip(), row[COL_QUARTER].strip(), row[COL_RATER].strip()
        if (ticker, year, quarter) == HEADER_ROW:
            continue
        if not ticker or not year or not quarter:
            continue
        key = f"{ticker.upper()}_{year}_{quarter}"
        if key not in gap_keys:
            continue
        prior_close = parse_price(row[COL_PRIOR_CLOSE])
        next_day_open = parse_price(row[COL_NEXT_DAY_OPEN])
        if prior_close is None or next_day_open is None:
            skipped_unparseable += 1
            continue
        entries = human_prices.setdefault(key, [])
        existing = next((e for e in entries if e["rater"] == rater), None)
        if existing is None:
            entries.append({"rater": rater, "prior_close": prior_close, "next_day_open": next_day_open})
            added += 1
        elif existing["prior_close"] != prior_close or existing["next_day_open"] != next_day_open:
            existing["prior_close"] = prior_close
            existing["next_day_open"] = next_day_open
            updated += 1

    HUMAN_PRICES_PATH.write_text(json.dumps(human_prices, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Added {added} rater price rows, updated {updated} stale rows for gap combos -> {HUMAN_PRICES_PATH}")
    print(f"Skipped {skipped_unparseable} gap-combo rows with unparseable/blank price cells")
    print(f"human_prices.json now covers {len(human_prices)} combos total")


if __name__ == "__main__":
    main()
