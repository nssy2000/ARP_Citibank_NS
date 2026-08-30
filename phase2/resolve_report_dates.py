"""Resolve a real report_date (exact earnings-release calendar date) for each of
the 104 target combos.

Method: yfinance's real historical earnings-date list is SPARSE (~4 events/year,
~91 days apart) and each entry is a genuine reported event - unlike a continuous
price series, there's no risk of a coincidental price match landing on the wrong
day. So: build a fiscal-year-aware naive estimate per combo (calendar-year FYE
for most tickers; hardcoded quarter-end-month overrides for the handful with a
shifted FYE - Apple, Walmart, Lowe's, Target, Nvidia), then pick whichever real
cached earnings date is closest to that estimate. Because real events are ~91
days apart, an estimate within ~45 days of the truth always resolves to the
correct event, and a fiscal-year-aware estimate only needs to be roughly right,
not exact.

Literal filename dates (extracted from filenames that already carry an exact
release date, e.g. Target/Lowe's transcripts named by date) override this
entirely where available - highest confidence, no estimation needed.

Prior attempts (positional "last N" alignment; open-window Close-price
matching) both produced silently wrong dates - documented in the phase2/
build notes so the mistake isn't repeated.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from quant_layer import _fetch_earnings_dates  # noqa: E402
import pandas as pd  # noqa: E402

from triage_docs import TARGET_COMBOS  # noqa: E402

# Fiscal-year-end month for tickers whose fiscal year isn't calendar-year.
# Value = the calendar month in which fiscal Q1 STARTS (i.e. month after FYE).
FYE_Q1_START_MONTH = {
    "AAPL": 10,   # FYE end-Sept: Q1=Oct-Dec, Q2=Jan-Mar, Q3=Apr-Jun, Q4=Jul-Sep
    "WMT": 2,     # FYE Jan 31: Q1=Feb-Apr, Q2=May-Jul, Q3=Aug-Oct, Q4=Nov-Jan
    "LOW": 2,     # FYE ~Jan/early Feb, same pattern as Walmart
    "TGT": 2,     # FYE ~late Jan/early Feb, same pattern
    "NVDA": 2,    # FYE last Sunday of January, same pattern
    "FDX": 6,     # FYE May 31: Q1=Jun-Aug, Q2=Sep-Nov, Q3=Dec-Feb, Q4=Mar-May
}

# naive_estimate()'s generic "base_year = year - 1 if q1_start_month >= 7 else
# year" rule mis-years any ticker whose Q1 starts in the first half of the
# year but whose Q1 still falls in the PRIOR calendar year (FedEx: Q1 starts
# June, fails the >=7 cutoff, would wrongly keep base_year=year and place
# "FDX FY2026 Q1" in Jun-Aug 2026 instead of the correct Jun-Aug 2025). An
# explicit override avoids touching the shared >=7 cutoff, which is already
# correct for AAPL/WMT/LOW/TGT/NVDA.
FYE_BASE_YEAR_OFFSET = {
    "FDX": -1,
}

# Literal exact dates recovered directly from filenames (ground truth, no
# estimation needed) - see phase2/coverage_report.json date_inferred_notes
# for Target/Lowe's transcripts named by their real release date.
LITERAL_DATES = {
    "TGT_2025_Q1": "2025-05-21", "TGT_2025_Q2": "2025-08-20",
    "TGT_2025_Q3": "2025-11-19", "TGT_2026_Q1": "2026-05-20",
    "LOW_2025_Q2": "2025-08-20", "LOW_2025_Q3": "2025-11-19",
    "LOW_2025_Q4": "2026-02-25", "LOW_2026_Q1": "2026-05-20",
}

QUARTER_START_OFFSET = {"Q1": 0, "Q2": 3, "Q3": 6, "Q4": 9}


def add_months(year: int, month: int, n: int) -> tuple[int, int]:
    total = (year * 12 + (month - 1)) + n
    return total // 12, total % 12 + 1


def naive_estimate(ticker: str, year: int, quarter: str) -> date:
    """Fiscal-year-aware guess at the report date: quarter END month (fiscal),
    plus a ~30-day reporting lag. `year` is the fiscal year label as used in
    the target combos (the calendar year the fiscal year is named after -
    Apple's FY2025 Q1 = Oct-Dec 2024, standard "fiscal year ends in the named
    year" convention)."""
    q1_start_month = FYE_Q1_START_MONTH.get(ticker, 1)  # default: calendar year, Q1 starts January
    # Non-calendar FYE tickers with Q1 starting late in the year (Apple: Oct)
    # have that Q1 falling in the PRIOR calendar year relative to the fiscal
    # year label; tickers with Q1 starting early (Feb) keep the same year.
    if ticker in FYE_BASE_YEAR_OFFSET:
        base_year = year + FYE_BASE_YEAR_OFFSET[ticker]
    else:
        base_year = year - 1 if q1_start_month >= 7 else year
    start_year, start_month = add_months(base_year, q1_start_month, QUARTER_START_OFFSET[quarter])
    end_year, end_month = add_months(start_year, start_month, 3)
    q_end = date(end_year, end_month, 1) - timedelta(days=1)
    return q_end + timedelta(days=30)


def main() -> None:
    resolved: dict[str, dict] = {}
    issues: list[str] = []

    for company, ticker, year, quarter in TARGET_COMBOS:
        key = f"{ticker}_{year}_{quarter}"
        if key in LITERAL_DATES:
            resolved[key] = {"report_date": LITERAL_DATES[key], "confidence": "high", "source": "filename_literal_date"}
            continue

        est = naive_estimate(ticker, year, quarter)
        try:
            earnings = _fetch_earnings_dates(ticker, limit=40)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"{key}: earnings-date fetch failed: {exc}; using naive estimate {est}")
            resolved[key] = {"report_date": est.isoformat(), "confidence": "low", "source": "naive_estimate_fallback"}
            continue

        if earnings is None or earnings.empty:
            issues.append(f"{key}: no earnings-date data; using naive estimate {est}")
            resolved[key] = {"report_date": est.isoformat(), "confidence": "low", "source": "naive_estimate_fallback"}
            continue

        idx = earnings.index
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_localize(None)
        cached_dates = sorted(d.date() for d in idx)
        nearest = min(cached_dates, key=lambda d: abs((d - est).days))
        gap = abs((nearest - est).days)
        confidence = "high" if gap <= 20 else ("medium" if gap <= 45 else "low")
        if gap > 45:
            issues.append(f"{key}: nearest real earnings date {nearest} is {gap}d from naive estimate {est} (low confidence, spot-check)")
        resolved[key] = {"report_date": nearest.isoformat(), "confidence": confidence, "source": f"nearest_real_earnings_date(gap={gap}d)"}

    out_path = BASE_DIR / "phase2" / "report_dates.json"
    out_path.write_text(json.dumps(resolved, indent=2, sort_keys=True), encoding="utf-8")

    counts = {}
    for v in resolved.values():
        counts[v["confidence"]] = counts.get(v["confidence"], 0) + 1
    print(f"Resolved {len(resolved)}/{len(TARGET_COMBOS)} -> {out_path}")
    print(f"Confidence breakdown: {counts}")
    if issues:
        print(f"\n{len(issues)} issues/notes:")
        for i in issues:
            print(f"  {i}")


if __name__ == "__main__":
    main()
