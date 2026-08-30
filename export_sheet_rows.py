"""
export_sheet_rows.py
Generates a TSV of 131 LLM-scored quarters for pasting into the group Google Sheet.

Outputs:
  outputs/global/summary/sheet_export.tsv        -- paste-ready (131 rows + header)
  outputs/global/summary/sheet_discrepancy_report.txt -- price check vs human rows

Paste instructions:
  1. Open sheet_export.tsv
  2. In Google Sheet, click the cell below the last existing row in column A
  3. Paste-special -> Values only (Ctrl+Shift+V on Windows)
  4. Columns L / M / N are blank -- extend the formulas from the row above down to
     cover all 131 new rows (select last formula row in L:N, drag handle down)
  5. Review sheet_discrepancy_report.txt for any price mismatches vs human rows

Blend score formula (replicates blend.py with DEFAULT_WEIGHTS = (0.8, 0.0, 0.2, 0.0)):
  - No news:   blend = micro_score            (macro/quant weight = 0, total_weight = 0.8)
  - With news: blend = 0.8 * micro + 0.2 * news   (total_weight = 1.0)
  Macro and quant always contribute zero (their weights are 0.0).

Decision: blend_predicted_signal_default from global_outcome_calibration.csv
  (pre-computed at +/-0.25 thresholds, identical for default and tuned since every
  LOOCV fold converges to the same weights).

Price methodology (timing-aware, 2026-08-11):
  Entry-date resolution depends on the manifest's release_timing.value:

  after_hours / intraday:
    prior_close   = Close on report_date (first trading day on/after)
    next_day_open = Open on the next trading session

  pre_market:
    prior_close   = Close on the session BEFORE report_date
    next_day_open = Open on report_date itself

  Cached to data/quantitative/sheet_export_cache/{TICKER}_{report_date}.csv.
  Release timing is per-issuer in the manifest (release_timing.value field).
  The old PRE_MARKET_ISSUERS constant is deprecated and unread.
"""

from __future__ import annotations

import csv
import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
OUTPUTS_DIR = BASE_DIR / "outputs"
CALIBRATION_CSV = OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration.csv"
EXPORT_TSV = OUTPUTS_DIR / "global" / "summary" / "sheet_export.tsv"
DISCREPANCY_REPORT = OUTPUTS_DIR / "global" / "summary" / "sheet_discrepancy_report.txt"
PRICE_CACHE_DIR = BASE_DIR / "data" / "quantitative" / "sheet_export_cache"

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
COMPANY_NAMES: dict[str, str] = {
    "boeing": "Boeing",
    "jpm": "JPMorgan Chase",
    "netflix": "Netflix",
    "bank_of_america": "Bank of America",
    "disney": "Disney",
    "target": "Target",
}

# DEPRECATED — was unread prose, never consumed by backtest.py or eval.
# Release timing is now per-issuer in the manifest (release_timing.value).
# Kept only as a comment for the git-blame trail; do not use.
# PRE_MARKET_ISSUERS = {"jpm", "bank_of_america", "target"}  # DEPRECATED 2026-08-11

# Human-entered prices from the Google Sheet screenshot.
# Key: (ticker, year, quarter); Value: (prior_close, next_day_open)
HUMAN_PRICES: dict[tuple[str, str, str], tuple[float, float]] = {
    ("NFLX", "2026", "Q1"): (107.79,  96.37),
    ("NFLX", "2025", "Q2"): (127.42, 129.92),
    ("NFLX", "2025", "Q3"): (124.14, 114.29),
    ("NFLX", "2025", "Q4"): ( 87.26,  82.52),
    ("NFLX", "2024", "Q4"): ( 86.97,  99.80),
    ("TGT",  "2026", "Q1"): ( 98.12,  91.50),
    ("TGT",  "2025", "Q3"): ( 86.08,  86.16),
    ("TGT",  "2025", "Q2"): ( 98.69,  98.49),
    ("TGT",  "2025", "Q1"): ( 93.01,  92.17),
    ("BA",   "2025", "Q1"): (162.52, 172.37),
    ("BA",   "2025", "Q2"): (236.41, 226.08),
    ("BA",   "2025", "Q3"): (223.33, 213.58),
    ("BA",   "2025", "Q4"): (248.43, 244.56),
    ("DIS",  "2025", "Q1"): (110.54, 115.70),
    ("DIS",  "2025", "Q3"): (118.32, 115.78),
    ("DIS",  "2025", "Q4"): (116.65, 108.89),
}

TSV_HEADERS = [
    "Company",
    "Ticker",
    "Year",
    "Quarter",
    "Rater",
    "Type (Human/LM)",
    "Sentiment Score (-1 to +1)",
    "Decision (BUY/HOLD/SELL)",
    "Time (mins)",
    "Prior Close ($)",
    "Next Day Open ($)",
    "Actual % Change",       # L -- leave blank; sheet formula computes from J+K
    "Actual Direction",      # M -- leave blank; sheet formula computes from L
    "Prediction Correct?",   # N -- leave blank; sheet formula computes from H+M
    "Notes / Risks Flagged",
]


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _safe_ticker(ticker: str) -> str:
    return ticker.replace("^", "").replace("/", "_")


def _load_release_timing_map() -> dict[str, str]:
    """Build {issuer_slug: timing_value} from all phase2 manifests.

    Returns e.g. {"p2_airbnb": "after_hours", "p2_target": "pre_market", ...}.
    Entries whose manifest has release_timing.value == null are included as None.
    """
    import json as _json, glob as _glob
    timing_map: dict[str, str | None] = {}
    for path in _glob.glob(str(BASE_DIR / "manifests" / "p2_*_reports.json")):
        with open(path) as fh:
            data = _json.load(fh)
        issuer = data.get("issuer", "")
        rt = data.get("release_timing", {})
        timing_map[issuer] = rt.get("value")  # None if not yet populated
    return timing_map


# Module-level cache (populated lazily)
_RELEASE_TIMING_MAP: dict[str, str] | None = None


def get_release_timing(issuer: str) -> str:
    """Return the release_timing value for an issuer.

    Raises ValueError if the value is None (not yet populated) — callers
    must not silently default to after_hours.
    """
    global _RELEASE_TIMING_MAP
    if _RELEASE_TIMING_MAP is None:
        _RELEASE_TIMING_MAP = _load_release_timing_map()
    val = _RELEASE_TIMING_MAP.get(issuer)
    if val is None:
        raise ValueError(
            f"release_timing is null for issuer '{issuer}'. "
            f"Populate the manifest's release_timing.value field before running. "
            f"Allowed values: pre_market, after_hours, intraday, unknown."
        )
    if val not in ("pre_market", "after_hours", "intraday", "unknown"):
        raise ValueError(
            f"Invalid release_timing value '{val}' for issuer '{issuer}'. "
            f"Allowed: pre_market, after_hours, intraday, unknown."
        )
    if val == "intraday":
        raise ValueError(
            f"release_timing is 'intraday' for issuer '{issuer}'. "
            f"Neither convention isolates the earnings reaction for a "
            f"mid-session release. Events for this issuer must be excluded."
        )
    if val == "unknown":
        raise ValueError(
            f"release_timing is 'unknown' for issuer '{issuer}'. "
            f"Timing cannot be sourced from a documented public timestamp. "
            f"Events for this issuer must be excluded."
        )
    return val


def _fetch_price_df(ticker: str, report_date: str, pre_days: int = 5) -> pd.DataFrame:
    """Fetch and cache yfinance price history around report_date.

    Returns a DataFrame with at least (pre_days + 14) calendar days of
    coverage, indexed by trading date (tz-naive).
    """
    PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = PRICE_CACHE_DIR / f"{_safe_ticker(ticker)}_{report_date}.csv"

    if cache_path.exists():
        df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
    else:
        report_dt = datetime.strptime(report_date, "%Y-%m-%d")
        start = (report_dt - timedelta(days=pre_days * 2 + 5)).strftime("%Y-%m-%d")
        end = (report_dt + timedelta(days=14)).strftime("%Y-%m-%d")
        raw = yf.Ticker(ticker).history(start=start, end=end)
        if raw.empty or len(raw) < 2:
            raise ValueError(
                f"Insufficient price data for {ticker} around {report_date}: "
                f"got {len(raw)} rows"
            )
        raw = raw.copy()
        raw.index = pd.to_datetime(raw.index).tz_localize(None)
        raw.to_csv(cache_path)
        df = raw

    if len(df) < 2:
        raise ValueError(
            f"Cache too short for {ticker} {report_date}: {len(df)} rows (need >=2)"
        )
    return df


def fetch_prices(ticker: str, report_date: str,
                 release_timing: str) -> tuple[float, float]:
    """Return (prior_close, next_day_open).

    Entry-date resolution depends on release_timing (REQUIRED, never None):

      after_hours:
        prior_close   = Close on report_date (first trading day on/after)
        next_day_open = Open on the next trading session

      pre_market:
        prior_close   = Close on the session BEFORE report_date
        next_day_open = Open on report_date itself
        (The reaction happens at report_date's open, so entry must be the
        prior session's close to capture it.)

      intraday:
        Raises ValueError — neither convention isolates the reaction for a
        mid-session release. The event must be excluded from grading.

      unknown:
        Raises ValueError — timing cannot be sourced from a documented public
        timestamp. The event must be excluded from grading.

    Raises ValueError if release_timing is None — callers must always pass
    an explicit value from the manifest.
    """
    if release_timing is None:
        raise ValueError(
            f"release_timing is None for {ticker} {report_date}. "
            f"Populate the manifest's release_timing.value field. "
            f"The pipeline must not run with unclassified timing."
        )
    if release_timing == "intraday":
        raise ValueError(
            f"release_timing is 'intraday' for {ticker} {report_date}. "
            f"Neither the pre_market nor after_hours convention isolates the "
            f"earnings reaction for a mid-session release. This event must be "
            f"excluded from grading."
        )
    if release_timing == "unknown":
        raise ValueError(
            f"release_timing is 'unknown' for {ticker} {report_date}. "
            f"Timing cannot be sourced from a documented public timestamp. "
            f"This event must be excluded from grading."
        )
    if release_timing not in ("pre_market", "after_hours"):
        raise ValueError(
            f"Invalid release_timing '{release_timing}' for {ticker} {report_date}. "
            f"Allowed: pre_market, after_hours, intraday, unknown."
        )

    df = _fetch_price_df(ticker, report_date)
    report_dt = pd.Timestamp(report_date)

    if release_timing == "pre_market":
        # Find the last trading day strictly BEFORE report_date
        prior_mask = df.index < report_dt
        if not prior_mask.any():
            raise ValueError(
                f"No trading day before {report_date} for {ticker}"
            )
        prior_idx = int(np.nonzero(prior_mask)[0][-1])
        # report_date itself (first trading day on/after)
        rdate_mask = df.index >= report_dt
        if not rdate_mask.any():
            raise ValueError(
                f"No trading day on/after {report_date} for {ticker}"
            )
        rdate_idx = int(np.nonzero(rdate_mask)[0][0])

        prior_close = round(float(df.iloc[prior_idx]["Close"]), 2)
        next_day_open = round(float(df.iloc[rdate_idx]["Open"]), 2)
    else:
        # after_hours
        rdate_mask = df.index >= report_dt
        if not rdate_mask.any():
            raise ValueError(
                f"No trading day on/after {report_date} for {ticker}"
            )
        rdate_idx = int(np.nonzero(rdate_mask)[0][0])
        if rdate_idx + 1 >= len(df):
            raise ValueError(
                f"No next trading session after {report_date} for {ticker}"
            )
        prior_close = round(float(df.iloc[rdate_idx]["Close"]), 2)
        next_day_open = round(float(df.iloc[rdate_idx + 1]["Open"]), 2)

    return prior_close, next_day_open


def compute_blend_score(micro: float, news: float | None) -> float:
    """Replicates blend.py blend_scores() with DEFAULT_WEIGHTS = (0.8, 0.0, 0.2, 0.0).

    Macro weight = 0.0, quant weight = 0.0 => they contribute nothing even if present.

    No news:   components = [(micro, 0.8)]; total_weight = 0.8; result = micro.
    With news: components = [(micro, 0.8), (news, 0.2)]; total_weight = 1.0;
               result = 0.8*micro + 0.2*news.
    """
    if news is not None and not math.isnan(news):
        return round(0.8 * micro + 0.2 * news, 4)
    return round(float(micro), 4)


def parse_document_id(doc_id: str) -> tuple[str, str]:
    """'BA_FQ1_2025' -> ('Q1', '2025')."""
    m = re.search(r"_FQ(\d+)_(\d{4})$", doc_id)
    if not m:
        raise ValueError(f"Cannot parse document_id: {doc_id!r}")
    return f"Q{m.group(1)}", m.group(2)


def load_notes(
    issuer: str,
    doc_id: str,
    micro: float,
    blend: float,
    news_active: bool,
) -> str:
    """Build the Notes cell string from the result JSON."""
    result_path = OUTPUTS_DIR / issuer / "results" / f"{doc_id}.json"
    if not result_path.exists():
        return f"[Micro={micro:.2f}; Blend={blend:.2f}]"

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    summary = payload.get("summary", {})
    tone = summary.get("management_tone", {}).get("label", "n/a")
    risks = summary.get("key_risks", [])

    # Truncate individual risks to keep the cell manageable
    risk_parts = [r[:85].rstrip() for r in risks[:2]]
    risk_text = "; ".join(risk_parts) if risk_parts else "n/a"

    scores_tag = f"[Micro={micro:.2f}; Blend={blend:.2f}]"
    news_tag   = " [news]" if news_active else ""

    note = f"Tone: {tone}. Risks: {risk_text}. {scores_tag}{news_tag}"

    # Hard cap so long notes don't break the sheet cell
    if len(note) > 300:
        note = note[:297] + "..."
    return note


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    cal = pd.read_csv(CALIBRATION_CSV)
    print(f"Loaded {len(cal)} rows from {CALIBRATION_CSV.name}")

    tsv_rows: list[list[str]] = []
    discrepancy_rows: list[dict] = []
    price_errors: list[str] = []

    for _, row in cal.iterrows():
        issuer      = str(row["issuer"])
        doc_id      = str(row["document_id"])
        ticker      = str(row["ticker"])
        report_date = str(row["report_date"])
        micro       = float(row["micro_score"])

        news_val = row["news_score"]
        news: float | None = float(news_val) if pd.notna(news_val) else None

        blend    = compute_blend_score(micro, news)
        decision = str(row["blend_predicted_signal_default"])
        quarter, year = parse_document_id(doc_id)
        company  = COMPANY_NAMES.get(issuer, issuer.replace("_", " ").title())

        # --- Price data ---
        try:
            prior_close, next_day_open = fetch_prices(ticker, report_date)
        except Exception as exc:
            print(f"  WARN price fetch failed: {doc_id}: {exc}")
            price_errors.append(f"{doc_id}: {exc}")
            prior_close, next_day_open = 0.0, 0.0

        # --- Notes ---
        notes = load_notes(issuer, doc_id, micro, blend, news is not None)

        # --- Build TSV row (15 cols: A-O) ---
        # L / M / N left blank -- sheet formulas will fill from J + K
        tsv_rows.append([
            company,                       # A
            ticker,                        # B
            year,                          # C
            quarter,                       # D
            "Ben/DeepSeek",               # E
            "LM",                          # F
            f"{blend:.2f}",               # G  Sentiment Score
            decision,                      # H  Decision
            "",                            # I  Time (humans only)
            f"${prior_close:.2f}",        # J  Prior Close
            f"${next_day_open:.2f}",      # K  Next Day Open
            "",                            # L  (sheet formula)
            "",                            # M  (sheet formula)
            "",                            # N  (sheet formula)
            notes,                         # O  Notes / Risks Flagged
        ])

        # --- Discrepancy check ---
        key = (ticker, year, quarter)
        if key in HUMAN_PRICES:
            h_close, h_open = HUMAN_PRICES[key]
            close_diff = abs(prior_close - h_close)
            open_diff  = abs(next_day_open - h_open)
            discrepancy_rows.append({
                "doc_id":     doc_id,
                "ticker":     ticker,
                "year":       year,
                "quarter":    quarter,
                "our_close":  prior_close,
                "h_close":    h_close,
                "close_diff": close_diff,
                "our_open":   next_day_open,
                "h_open":     h_open,
                "open_diff":  open_diff,
                "flag":       (close_diff > 0.50 or open_diff > 0.50),
            })

    # --- Write TSV ---
    EXPORT_TSV.parent.mkdir(parents=True, exist_ok=True)
    with open(EXPORT_TSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(TSV_HEADERS)
        w.writerows(tsv_rows)
    print(f"\nWrote {len(tsv_rows)} rows -> {EXPORT_TSV}")

    # --- Write discrepancy report ---
    sep = "=" * 72
    lines: list[str] = [
        "PRICE DISCREPANCY REPORT",
        "Compares yfinance-fetched prices against human-entered prices from screenshot.",
        "Flag threshold: |diff| > $0.50",
        sep,
        "",
    ]

    flagged = [d for d in discrepancy_rows if d["flag"]]
    ok      = [d for d in discrepancy_rows if not d["flag"]]

    lines.append(
        f"Checked: {len(discrepancy_rows)} quarters  |  "
        f"OK: {len(ok)}  |  FLAGGED: {len(flagged)}"
    )
    lines.append("")

    if flagged:
        lines.append("--- FLAGGED (diff > $0.50) ---")
        for d in flagged:
            lines.append(
                f"  {d['doc_id']:<22s}  "
                f"Prior Close : ours=${d['our_close']:>7.2f}  human=${d['h_close']:>7.2f}  "
                f"diff=${d['close_diff']:.2f}  |  "
                f"Next Open : ours=${d['our_open']:>7.2f}  human=${d['h_open']:>7.2f}  "
                f"diff=${d['open_diff']:.2f}"
            )
        lines.append("")

    lines.append("--- OK (diff <= $0.50) ---")
    for d in ok:
        lines.append(
            f"  {d['doc_id']:<22s}  "
            f"Prior Close : ours=${d['our_close']:>7.2f}  human=${d['h_close']:>7.2f}  |  "
            f"Next Open : ours=${d['our_open']:>7.2f}  human=${d['h_open']:>7.2f}"
        )

    if price_errors:
        lines += ["", "--- PRICE FETCH ERRORS ---"]
        lines += [f"  {e}" for e in price_errors]

    lines += [
        "",
        sep,
        "KNOWN DATA-ENTRY ISSUES IN HUMAN ROWS (from screenshot analysis)",
        sep,
        "",
        "  BA 2025 Q3 (Nigel, row 17):",
        "    Shown: Prior Close $223.33, Next Day Open $213.58 => -4.4%, Direction=FLAT, Correct=YES",
        "    The sheet's direction formula auto-computes from J/K, so -4.4% should",
        "    register as DOWN (not FLAT) unless Settings!$B$3 >= 4.4. With HOLD prediction",
        "    and DOWN direction the formula would give Correct=NO, not YES.",
        "    Likely cause: Nigel entered wrong prices or direction was typed manually.",
        "",
        "  NFLX 2025 Q2 (Meriem, row 8):",
        "    Shown: Prior Close $127.42, Next Day Open $129.92 => +2.0%, Direction=FLAT, Correct=NO",
        "    BUY prediction vs FLAT direction => NO is internally consistent if the",
        "    Settings threshold is >= 2.0% (strict >). But BA Q4 2025 at -1.6% shows",
        "    DOWN, implying threshold < 1.6% -- contradiction. Likely a data-entry error.",
        "",
        sep,
        "PRE-MARKET REPORTERS (methodology note)",
        sep,
        "",
        "  JPM, BAC, TGT report earnings ~7am ET before the market opens.",
        "  This script uses history(start=report_date), so:",
        "    prior_close   = Close on report_date (already reflects intraday post-open reaction)",
        "    next_day_open = Open on report_date + 1 trading day",
        "  True pre-announcement close = Close on (report_date - 1 trading day).",
        "  Consistent with eval/outcomes.py's entry_price; note when comparing to human rows",
        "  who may have used the previous day's close for these issuers.",
    ]

    DISCREPANCY_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote discrepancy report -> {DISCREPANCY_REPORT}")

    print("\n" + sep)
    print("SPOT-CHECK VALUES (verify before pasting):")
    spot_checks = {
        "BA_FQ1_2025":  ("0.22", "HOLD"),   # blend = 0.8*0.2 + 0.2*0.3 = 0.22
        "JPM_FQ1_2025": ("-0.45", "SELL"),  # blend = 0.8*(-0.5) + 0.2*(-0.25) = -0.45
        "NFLX_FQ2_2025": ("0.18", "HOLD"),  # blend = 0.8*0.3 + 0.2*(-0.3) = 0.18
        "BA_FQ1_2021":  ("0.15", "HOLD"),   # no news => blend = micro = 0.15
    }
    for check_id, (exp_score, exp_decision) in spot_checks.items():
        match = [r for r in tsv_rows if r[0] != "Company" and any(check_id in str(c) for c in r)]
        # Find by scanning notes (doc_id is in notes) -- simpler: rebuild lookup from cal
        pass
    # Direct lookup from cal for spot-check
    for check_id, (exp_score, exp_decision) in spot_checks.items():
        cal_row = cal[cal["document_id"] == check_id]
        if cal_row.empty:
            continue
        r = cal_row.iloc[0]
        micro = float(r["micro_score"])
        nv = r["news_score"]
        news = float(nv) if pd.notna(nv) else None
        got_blend = f"{compute_blend_score(micro, news):.2f}"
        got_dec   = str(r["blend_predicted_signal_default"])
        status = "OK" if got_blend == exp_score and got_dec == exp_decision else "MISMATCH"
        print(
            f"  {check_id:<22s}  blend={got_blend} (expect {exp_score})  "
            f"decision={got_dec} (expect {exp_decision})  [{status}]"
        )

    print(sep)
    print("\nPASTE INSTRUCTIONS:")
    print("  1. Open: outputs/global/summary/sheet_export.tsv")
    print("  2. In Google Sheet: click cell below the last row in col A")
    print("  3. Paste-special -> Values only (Ctrl+Shift+V)")
    print("  4. Cols L/M/N will be blank -- select last formula row in those cols,")
    print("     drag the fill handle down to cover all 131 new rows")
    print("  5. Review sheet_discrepancy_report.txt for price mismatches")


if __name__ == "__main__":
    main()
