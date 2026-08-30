"""Re-resolve phase2 report_date using the humans' own typed prices as ground
truth, instead of trusting resolve_report_dates.py's nearest-real-earnings-date
guess blind.

Bug this fixes: resolve_report_dates.py picks report_date from a fiscal-quarter
ESTIMATE matched to the nearest cached real earnings event - no cross-check
against what quarter that date's price action actually belongs to. Comparing
the resulting data_entry_rows.tsv against the group sheet's human-typed rows
(same ticker+quarter) showed 58/97 overlapping combos with a DIFFERENT
Actual %Change between the LLM row and the human row - i.e. the LLM's
Prior Close/Next Day Open often comes from the wrong trading day entirely
(see e.g. NKE_2025_Q2: human $77.10->$75.96, LLM $60.87->$67.93 - unrelated
price pair). That means most of the LLM's phase2 P&L was scored against noise,
not its actual prediction's real outcome.

Method: humans already hand-typed (Prior Close, Next Day Open) into the group
sheet for the same combos (captured in phase2/human_prices.json). For each
combo with human price data, pull the ticker's full daily price history and
find the trading day D where Close[D] matches the human Prior Close AND
Open[D+1] matches the human Next Day Open (both to the cent). Matching two
independent price points (not one) makes a coincidental match across a
multi-year history vanishingly unlikely - this is what the earlier
Close-only-match attempt (documented as a prior failure in
resolve_report_dates.py's docstring) was missing.

Combos with no human price data (~10) are left untouched - out of scope for
this fix, already flagged low/medium confidence in report_dates.json.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

REPORT_DATES_PATH = BASE_DIR / "phase2" / "report_dates.json"
HUMAN_PRICES_PATH = BASE_DIR / "phase2" / "human_prices.json"
CACHE_DIR = BASE_DIR / "data" / "quantitative" / "phase2_date_validation_cache"

TOLERANCE = 0.02  # dollars, matches human rows' 2dp typing precision

# auto_adjust=False is load-bearing: yfinance's default (True) returns
# dividend/split-adjusted prices, which drift below the actual quoted price
# the more dividends have been paid since the data was pulled. Humans typed
# the real same-day quote, so matching against adjusted history silently
# fails for every dividend payer (confirmed: TGT_2025_Q1 raw Close on the
# real report date is $93.01, exact match; adjusted Close for that same day
# reads $89.11 - a false non-match).


def _safe_ticker(ticker: str) -> str:
    return ticker.replace("^", "").replace("/", "_")


def _full_history(ticker: str) -> pd.DataFrame:
    """Entire available daily history, cached indefinitely (historical prices
    don't change)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{_safe_ticker(ticker)}.csv"
    if cache_path.exists():
        return pd.read_csv(cache_path, index_col=0, parse_dates=True)
    raw = yf.Ticker(ticker).history(period="max", auto_adjust=False)
    if raw.empty:
        return raw
    raw = raw.copy()
    raw.index = pd.to_datetime(raw.index).tz_localize(None)
    raw.to_csv(cache_path)
    return raw


def consensus_price(entries: list[dict]) -> tuple[float, float, bool]:
    """Majority (prior_close, next_day_open) pair across raters for one combo.
    Returns (prior_close, next_day_open, was_unanimous)."""
    pairs = [(round(e["prior_close"], 2), round(e["next_day_open"], 2)) for e in entries]
    counts = Counter(pairs)
    winner, n = counts.most_common(1)[0]
    return winner[0], winner[1], (n == len(pairs))


def find_report_date(ticker: str, prior_close: float, next_day_open: float) -> list[str]:
    """Trading days D where Close[D]~=prior_close and Open[D+1]~=next_day_open.
    Returns ISO date strings of D (should normally be exactly one match)."""
    hist = _full_history(ticker)
    if hist.empty:
        return []
    closes = hist["Close"].to_numpy()
    opens = hist["Open"].to_numpy()
    dates = hist.index
    matches = []
    for i in range(len(hist) - 1):
        if abs(closes[i] - prior_close) <= TOLERANCE and abs(opens[i + 1] - next_day_open) <= TOLERANCE:
            matches.append(dates[i].date().isoformat())
    return matches


def main() -> None:
    report_dates = json.loads(REPORT_DATES_PATH.read_text(encoding="utf-8"))
    human_prices = json.loads(HUMAN_PRICES_PATH.read_text(encoding="utf-8"))

    updated = 0
    unchanged_confirmed = 0
    unresolved: list[str] = []
    ambiguous: list[str] = []
    no_human_data: list[str] = []
    disagreements: list[str] = []

    for key in sorted(report_dates.keys()):
        if key not in human_prices:
            no_human_data.append(key)
            continue

        entries = human_prices[key]
        prior_close, next_day_open, unanimous = consensus_price(entries)
        ticker = key.split("_")[0]
        old_date = report_dates[key]["report_date"]

        if unanimous:
            matches = find_report_date(ticker, prior_close, next_day_open)
        else:
            # Raters disagree - don't just trust majority-vote (a 1-1 tie is a
            # coinflip and majority-count can equally pick a typo). Instead try
            # every distinct pair any rater typed and keep whichever one
            # actually validates against real market data.
            distinct_pairs = sorted({(round(e["prior_close"], 2), round(e["next_day_open"], 2)) for e in entries})
            pair_matches = {pair: find_report_date(ticker, pair[0], pair[1]) for pair in distinct_pairs}
            validating = {pair: m for pair, m in pair_matches.items() if m}
            if len(validating) == 1:
                (prior_close, next_day_open), matches = next(iter(validating.items()))
                disagreements.append(
                    f"{key}: raters disagreed {distinct_pairs}, only {(prior_close, next_day_open)} validates against real prices - using it"
                )
            else:
                disagreements.append(f"{key}: raters disagree on price {distinct_pairs}, using majority {prior_close}/{next_day_open}")
                matches = find_report_date(ticker, prior_close, next_day_open)

        if len(matches) == 0:
            unresolved.append(f"{key}: no trading day matches human price ${prior_close}->${next_day_open}, kept old date {old_date}")
            continue

        if len(matches) > 1:
            # Two independent price points collide by coincidence only across
            # very long histories (e.g. a stock revisiting the same level 15+
            # years apart) - pick whichever candidate is nearest the existing
            # earnings-date-anchored estimate, which is always in the right
            # ballpark, and flag it for a human to eyeball.
            new_date = min(matches, key=lambda d: abs((pd.Timestamp(d) - pd.Timestamp(old_date)).days))
            ambiguous.append(f"{key}: {len(matches)} candidate dates matched human price {matches}, picked nearest-to-estimate {new_date}")
        else:
            new_date = matches[0]

        if new_date != old_date:
            report_dates[key] = {
                "report_date": new_date,
                "confidence": "high",
                "source": "validated_against_human_price",
            }
            updated += 1
        else:
            report_dates[key]["confidence"] = "high"
            report_dates[key]["source"] = "validated_against_human_price(unchanged)"
            unchanged_confirmed += 1

    REPORT_DATES_PATH.write_text(json.dumps(report_dates, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Combos with human price data: {len(human_prices)}")
    print(f"  Updated (date changed):        {updated}")
    print(f"  Confirmed (date already right): {unchanged_confirmed}")
    print(f"  Unresolved (no match):          {len(unresolved)}")
    print(f"  Ambiguous (multiple matches):   {len(ambiguous)}")
    print(f"Combos with no human price data (untouched): {len(no_human_data)}")

    if disagreements:
        print(f"\n{len(disagreements)} rater price disagreements (used majority):")
        for d in disagreements:
            print(" ", d)
    if unresolved:
        print(f"\n{len(unresolved)} unresolved:")
        for u in unresolved:
            print(" ", u)
    if ambiguous:
        print(f"\n{len(ambiguous)} ambiguous:")
        for a in ambiguous:
            print(" ", a)


if __name__ == "__main__":
    main()
