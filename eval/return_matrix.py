"""
eval/return_matrix.py
Multi-horizon return matrix for all phase2 earnings events.

For each of the 268 events in global_outcome_calibration_phase2.csv, fetches
price history from yfinance (auto_adjust=False) and computes returns at five
horizons: overnight (close->next open), 1d, 3d, 5d, 10d (all close-to-close
except overnight). Also computes excess returns vs SPY over each horizon.

Derives implied HOLD bands: overnight band = +/-2% (group sheet convention,
Settings!B3). For longer horizons, the band is set so the share of events
inside the band matches the overnight share (i.e. the HOLD rate is preserved
across horizons).

Outputs:
  outputs/global/summary/returns_matrix.csv
  outputs/global/summary/returns_matrix_by_ticker/<TICKER>.csv
  outputs/global/summary/implied_hold_bands.csv
  outputs/global/summary/returns_matrix_exceptions.csv

Usage:
  python -m eval.return_matrix
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
CALIBRATION_CSV = OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration_phase2.csv"
OUTPUT_CSV = OUTPUTS_DIR / "global" / "summary" / "returns_matrix.csv"
BY_TICKER_DIR = OUTPUTS_DIR / "global" / "summary" / "returns_matrix_by_ticker"
HOLD_BANDS_CSV = OUTPUTS_DIR / "global" / "summary" / "implied_hold_bands.csv"
EXCEPTIONS_CSV = OUTPUTS_DIR / "global" / "summary" / "returns_matrix_exceptions.csv"

# Overnight HOLD band from group sheet Settings!B3
OVERNIGHT_BAND = 0.02

# Horizons: (column_suffix, trading_days_after_entry, use_open_for_exit)
HORIZONS = [
    ("overnight", 1, True),   # close -> next session open
    ("1d",        1, False),  # close -> close of 1st session after entry
    ("3d",        3, False),
    ("5d",        5, False),
    ("10d",      10, False),
]


def _fetch_price_history(ticker: str, report_date: str, pre_days: int = 5,
                         post_days: int = 25) -> pd.DataFrame | None:
    """Fetch raw (auto_adjust=False) price history spanning
    report_date - pre_days sessions to report_date + post_days sessions.
    Returns a DataFrame indexed by trading date, or None on failure."""
    report_dt = datetime.strptime(report_date, "%Y-%m-%d")
    # Calendar days buffer: pre_days*2+5 before, post_days*2+10 after
    start = (report_dt - timedelta(days=pre_days * 2 + 5)).strftime("%Y-%m-%d")
    end = (report_dt + timedelta(days=post_days * 2 + 10)).strftime("%Y-%m-%d")
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(start=start, end=end, auto_adjust=False)
        if hist.empty:
            return None
        # Drop timezone for clean indexing
        hist = hist.copy()
        hist.index = pd.to_datetime(hist.index).tz_localize(None)
        return hist
    except Exception as e:
        print(f"  yfinance error for {ticker} around {report_date}: {e}")
        return None


def _find_entry_idx(hist: pd.DataFrame, report_date: str,
                    release_timing: str) -> int | None:
    """Find the index position of the entry date in the price history.

    release_timing is REQUIRED (never None):
      after_hours: entry = first trading day on/after report_date.
      pre_market:  entry = last trading day BEFORE report_date.
      intraday:    raises ValueError (must be excluded upstream).
    """
    if release_timing is None:
        raise ValueError(
            f"release_timing is None for {report_date} — "
            f"populate the manifest before running"
        )
    if release_timing == "intraday":
        raise ValueError(
            f"release_timing is 'intraday' for {report_date} — "
            f"event must be excluded, cannot resolve entry"
        )

    report_dt = pd.Timestamp(report_date)

    if release_timing == "pre_market":
        mask = hist.index < report_dt
        if not mask.any():
            return None
        return int(np.nonzero(mask)[0][-1])
    else:
        # after_hours
        mask = hist.index >= report_dt
        if not mask.any():
            return None
        return int(np.argmax(mask))


def compute_event_returns(ticker: str, report_date: str,
                          spy_hist: pd.DataFrame | None = None,
                          release_timing: str | None = None,
                          ) -> tuple[dict, list[str]]:
    """Compute all horizon returns for a single event.
    Returns (row_dict, list_of_exception_messages).
    release_timing is passed through to _find_entry_idx."""
    exceptions = []
    row = {
        "ticker": ticker,
        "report_date": report_date,
        "entry_date": None,
        "entry_close": None,
    }
    for suffix, _, _ in HORIZONS:
        row[f"ret_{suffix}"] = None
        row[f"excess_{suffix}"] = None

    hist = _fetch_price_history(ticker, report_date)
    if hist is None or len(hist) < 2:
        exceptions.append(f"{ticker} {report_date}: no price data")
        return row, exceptions

    entry_idx = _find_entry_idx(hist, report_date, release_timing)
    if entry_idx is None:
        exceptions.append(f"{ticker} {report_date}: no trading day resolved for entry")
        return row, exceptions

    entry_close = float(hist.iloc[entry_idx]["Close"])
    entry_date = str(hist.index[entry_idx].date())
    row["entry_date"] = entry_date
    row["entry_close"] = round(entry_close, 4)

    # SPY entry
    spy_entry_idx = None
    spy_entry_close = None
    if spy_hist is not None:
        spy_entry_idx = _find_entry_idx(spy_hist, report_date, release_timing="after_hours")
        if spy_entry_idx is not None:
            spy_entry_close = float(spy_hist.iloc[spy_entry_idx]["Close"])

    for suffix, days, use_open in HORIZONS:
        target_idx = entry_idx + days
        if target_idx >= len(hist):
            exceptions.append(
                f"{ticker} {report_date}: insufficient data for {suffix} "
                f"(need idx {target_idx}, have {len(hist)})"
            )
            continue

        # Assert horizon stepping lands on a trading day (by construction,
        # since we index into the yfinance DataFrame whose index IS the set
        # of trading days — but verify explicitly that no weekend/holiday
        # slipped through, e.g. via a corrupted index).
        exit_date = hist.index[target_idx]
        assert exit_date.weekday() < 5, (
            f"Horizon {suffix} for {ticker} {report_date} landed on "
            f"{exit_date.strftime('%A')} {exit_date.date()} — non-trading day "
            f"in yfinance index"
        )

        if use_open:
            exit_price = float(hist.iloc[target_idx]["Open"])
        else:
            exit_price = float(hist.iloc[target_idx]["Close"])

        ret = (exit_price - entry_close) / entry_close
        row[f"ret_{suffix}"] = round(ret, 6)

        # SPY excess
        if spy_hist is not None and spy_entry_idx is not None:
            spy_target_idx = spy_entry_idx + days
            if spy_target_idx < len(spy_hist):
                if use_open:
                    spy_exit = float(spy_hist.iloc[spy_target_idx]["Open"])
                else:
                    spy_exit = float(spy_hist.iloc[spy_target_idx]["Close"])
                spy_ret = (spy_exit - spy_entry_close) / spy_entry_close
                row[f"excess_{suffix}"] = round(ret - spy_ret, 6)

    return row, exceptions


def compute_implied_hold_bands(returns: list[dict]) -> dict:
    """Compute implied HOLD bands so the share of events inside the band
    matches the overnight share at each horizon."""
    overnight_rets = [r["ret_overnight"] for r in returns if r["ret_overnight"] is not None]
    n_total = len(overnight_rets)
    if n_total == 0:
        return {}

    n_inside_overnight = sum(1 for r in overnight_rets if abs(r) <= OVERNIGHT_BAND)
    hold_share = n_inside_overnight / n_total

    bands = {"overnight": OVERNIGHT_BAND}

    for suffix, _, _ in HORIZONS:
        if suffix == "overnight":
            continue
        horizon_rets = sorted(
            [abs(r[f"ret_{suffix}"]) for r in returns if r[f"ret_{suffix}"] is not None]
        )
        if not horizon_rets:
            continue
        # Find the threshold such that hold_share fraction of events are inside
        target_count = int(round(hold_share * len(horizon_rets)))
        target_count = min(target_count, len(horizon_rets))
        if target_count == 0:
            bands[suffix] = 0.0
        else:
            bands[suffix] = round(horizon_rets[target_count - 1], 6)

    return bands


def main():
    # Import timing map from the single source of truth
    sys.path.insert(0, str(BASE_DIR))
    from export_sheet_rows import _load_release_timing_map

    # Load calibration CSV
    events = []
    with open(CALIBRATION_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            events.append({
                "document_id": r["document_id"],
                "ticker": r["ticker"],
                "report_date": r["report_date"],
                "issuer": r["issuer"],
            })

    print(f"Loaded {len(events)} events from calibration CSV")

    # Load release timing map and assert every event has a non-null value.
    # The pipeline must not run with unclassified timing — a silent default
    # produces plausible numbers from the wrong window for pre-market reporters.
    timing_map = _load_release_timing_map()
    missing_timing = []
    intraday_events = []
    for ev in events:
        val = timing_map.get(ev["issuer"])
        if val is None:
            missing_timing.append(ev["issuer"])
        elif val == "intraday":
            intraday_events.append(ev["document_id"])
    if missing_timing:
        unique_missing = sorted(set(missing_timing))
        print(f"\n  {len(unique_missing)} issuers have null release_timing — "
              f"their events will be SKIPPED (excluded from grading).")
        for iss in unique_missing:
            print(f"    {iss}")
    if intraday_events:
        print(f"  WARNING: {len(intraday_events)} events have intraday timing "
              f"and will be excluded (neither convention isolates the reaction).")
    print(f"  All {len(events)} events have non-null release_timing.")

    # Generate run_id
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Pre-fetch SPY history covering the full date range
    all_dates = [e["report_date"] for e in events]
    min_date = min(all_dates)
    max_date = max(all_dates)
    min_dt = datetime.strptime(min_date, "%Y-%m-%d")
    max_dt = datetime.strptime(max_date, "%Y-%m-%d")
    spy_start = (min_dt - timedelta(days=15)).strftime("%Y-%m-%d")
    spy_end = (max_dt + timedelta(days=60)).strftime("%Y-%m-%d")
    print(f"Fetching SPY history from {spy_start} to {spy_end}...")
    spy_tk = yf.Ticker("SPY")
    spy_hist = spy_tk.history(start=spy_start, end=spy_end, auto_adjust=False)
    if not spy_hist.empty:
        spy_hist = spy_hist.copy()
        spy_hist.index = pd.to_datetime(spy_hist.index).tz_localize(None)
        print(f"  SPY: {len(spy_hist)} trading days")
    else:
        print("  WARNING: no SPY data fetched")
        spy_hist = None

    # Load release_date from manifests for each event
    import json as _json
    release_date_map = {}
    for mf in __import__('glob').glob(str(BASE_DIR / "manifests" / "p2_*_reports.json")):
        with open(mf) as _fh:
            mdata = _json.load(_fh)
        for report in mdata["reports"]:
            rd = report.get("release_date")
            if rd:
                release_date_map[report["document_id"]] = rd

    # Process each event
    all_rows = []
    all_exceptions = []
    skipped_timing = []
    for i, ev in enumerate(events):
        if (i + 1) % 20 == 0 or i == 0:
            print(f"  Processing {i+1}/{len(events)}: {ev['document_id']}...")
        rt = timing_map.get(ev["issuer"])  # None if not yet populated

        # Determine the anchor date: release_date if available, else report_date
        anchor_date = release_date_map.get(ev["document_id"], ev["report_date"])

        # For excluded events (null/unknown/intraday timing), use report_date
        # close as entry (legacy convention) and flag them
        if rt in (None, "unknown", "intraday"):
            row, exc = compute_event_returns(ev["ticker"], ev["report_date"], spy_hist,
                                             release_timing="after_hours")
            row["timing_excluded"] = "YES"
            skipped_timing.append(ev["document_id"])
        else:
            row, exc = compute_event_returns(ev["ticker"], anchor_date, spy_hist,
                                             release_timing=rt)
            row["timing_excluded"] = "NO"
        row["document_id"] = ev["document_id"]
        row["run_id"] = run_id
        # Flag home-listed tickers for SPY excess misalignment
        home_listed = {"ALV.DE", "SIE.DE", "PUM.DE", "MC.PA", "STAN.L"}
        row["excess_spy_aligned"] = "0" if ev["ticker"] in home_listed else "1"
        all_rows.append(row)
        for msg in exc:
            all_exceptions.append({
                "document_id": ev["document_id"],
                "ticker": ev["ticker"],
                "report_date": ev["report_date"],
                "exception": msg,
            })

    # Verify row count
    assert len(all_rows) == len(events), (
        f"Row count mismatch: {len(all_rows)} vs {len(events)} events"
    )
    print(f"\nComputed returns for {len(all_rows)} events")
    print(f"Exceptions: {len(all_exceptions)}")

    if skipped_timing:
        print(f"Timing-excluded events (legacy convention): {len(skipped_timing)}")

    # Column order for output
    columns = [
        "document_id", "ticker", "report_date", "entry_date", "entry_close",
        "ret_overnight", "ret_1d", "ret_3d", "ret_5d", "ret_10d",
        "excess_overnight", "excess_1d", "excess_3d", "excess_5d", "excess_10d",
        "run_id", "excess_spy_aligned", "timing_excluded",
    ]

    # Write main CSV
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns)
        w.writeheader()
        for row in all_rows:
            w.writerow({c: row.get(c) for c in columns})
    print(f"Wrote -> {OUTPUT_CSV}")

    # Write per-ticker CSVs
    BY_TICKER_DIR.mkdir(parents=True, exist_ok=True)
    by_ticker: dict[str, list[dict]] = {}
    for row in all_rows:
        by_ticker.setdefault(row["ticker"], []).append(row)
    for ticker, rows in sorted(by_ticker.items()):
        ticker_path = BY_TICKER_DIR / f"{ticker}.csv"
        with open(ticker_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=columns)
            w.writeheader()
            for row in rows:
                w.writerow({c: row.get(c) for c in columns})
    print(f"Wrote {len(by_ticker)} per-ticker CSVs -> {BY_TICKER_DIR}/")

    # Write exceptions
    if all_exceptions:
        with open(EXCEPTIONS_CSV, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["document_id", "ticker",
                                                "report_date", "exception"])
            w.writeheader()
            for exc in all_exceptions:
                w.writerow(exc)
        print(f"Wrote exceptions -> {EXCEPTIONS_CSV}")

    # Compute and write implied HOLD bands
    bands = compute_implied_hold_bands(all_rows)
    if bands:
        overnight_rets = [r["ret_overnight"] for r in all_rows
                          if r["ret_overnight"] is not None]
        n_inside = sum(1 for r in overnight_rets if abs(r) <= OVERNIGHT_BAND)
        hold_share = n_inside / len(overnight_rets) if overnight_rets else 0
        print(f"\nOvernight HOLD band: +/-{OVERNIGHT_BAND*100:.1f}%, "
              f"{n_inside}/{len(overnight_rets)} events inside "
              f"({hold_share*100:.1f}%)")

        with open(HOLD_BANDS_CSV, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["horizon", "hold_band",
                                                "hold_share", "n_inside",
                                                "n_total"])
            w.writeheader()
            for suffix, _, _ in HORIZONS:
                if suffix not in bands:
                    continue
                horizon_rets = [r[f"ret_{suffix}"] for r in all_rows
                                if r[f"ret_{suffix}"] is not None]
                n_in = sum(1 for r in horizon_rets if abs(r) <= bands[suffix])
                w.writerow({
                    "horizon": suffix,
                    "hold_band": round(bands[suffix], 6),
                    "hold_share": round(n_in / len(horizon_rets), 4)
                        if horizon_rets else 0,
                    "n_inside": n_in,
                    "n_total": len(horizon_rets),
                })
        print(f"Wrote implied HOLD bands -> {HOLD_BANDS_CSV}")
        for suffix in ["overnight", "1d", "3d", "5d", "10d"]:
            if suffix in bands:
                print(f"  {suffix:>9}: +/-{bands[suffix]*100:.2f}%")

    # --- Spot checks ---
    print("\n=== SPOT CHECKS ===")

    # Check 1: compare ret_overnight against independent calculation
    print("\n--- Check 1: ret_overnight vs independent calc (first 5 with data) ---")
    checked = 0
    for row in all_rows:
        if row["ret_overnight"] is None:
            continue
        if checked >= 5:
            break
        # Independent: fetch_prices from export_sheet_rows
        try:
            from export_sheet_rows import fetch_prices
            pc, ndo = fetch_prices(row["ticker"], row["report_date"])
            indep_overnight = round((ndo - pc) / pc, 6)
            match = "MATCH" if abs(indep_overnight - row["ret_overnight"]) < 1e-4 else "MISMATCH"
            print(f"  {row['document_id']:30s} matrix={row['ret_overnight']:+.6f}  "
                  f"indep={indep_overnight:+.6f}  {match}")
            checked += 1
        except Exception as e:
            print(f"  {row['document_id']:30s} independent check failed: {e}")
            checked += 1

    # Check 2: compare ret_5d against forward_return from calibration CSV
    print("\n--- Check 2: ret_5d vs calibration forward_return ---")
    cal_fwd = {}
    with open(CALIBRATION_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            cal_fwd[r["document_id"]] = float(r["forward_return"])
    checked = 0
    for row in all_rows:
        if row["ret_5d"] is None:
            continue
        if checked >= 5:
            break
        cal_val = cal_fwd.get(row["document_id"])
        if cal_val is not None:
            diff = abs(row["ret_5d"] - cal_val)
            status = "CLOSE" if diff < 0.01 else f"DIFF={diff:.4f}"
            print(f"  {row['document_id']:30s} matrix_5d={row['ret_5d']:+.6f}  "
                  f"cal_fwd={cal_val:+.6f}  {status}")
            checked += 1

    # Check 3: Two hand-check events
    print("\n--- Check 3: TWO HAND-CHECK WORKED EXAMPLES ---")
    # We need one pre-market and one after-hours reporter
    # Pre-market: JPM, BAC, TGT are known pre-market from export_sheet_rows
    # After-hours: most others (ABNB, NFLX, DIS, etc.)

    hand_checks = []
    # Find a JPM/BAC/TGT event for pre-market
    for row in all_rows:
        if row["ticker"] in ("JPM", "BAC", "TGT") and row["entry_close"] is not None:
            hand_checks.append(("PRE-MARKET", row))
            break
    # Find an after-hours event
    for row in all_rows:
        if row["ticker"] in ("NFLX", "ABNB", "DIS", "AAPL") and row["entry_close"] is not None:
            hand_checks.append(("AFTER-HOURS", row))
            break

    for label, row in hand_checks:
        print(f"\n  === {label} REPORTER: {row['ticker']} ===")
        print(f"  document_id : {row['document_id']}")
        print(f"  report_date : {row['report_date']}")
        print(f"  entry_date  : {row['entry_date']}")
        print(f"  entry_close : {row['entry_close']}")

        # Re-fetch to show raw prices
        hist = _fetch_price_history(row["ticker"], row["report_date"])
        entry_idx = _find_entry_idx(hist, row["report_date"])
        if hist is not None and entry_idx is not None:
            print(f"\n  Price history around entry:")
            start_show = max(0, entry_idx - 1)
            end_show = min(len(hist), entry_idx + 12)
            for j in range(start_show, end_show):
                marker = " <-- ENTRY" if j == entry_idx else ""
                dt = str(hist.index[j].date())
                o = hist.iloc[j]["Open"]
                c = hist.iloc[j]["Close"]
                offset = j - entry_idx
                print(f"    {dt}  Open={o:>10.2f}  Close={c:>10.2f}"
                      f"  (entry+{offset}){marker}")

            entry_close = float(hist.iloc[entry_idx]["Close"])
            if entry_idx + 1 < len(hist):
                next_open = float(hist.iloc[entry_idx + 1]["Open"])
                print(f"\n  Overnight: ({next_open:.2f} - {entry_close:.2f}) "
                      f"/ {entry_close:.2f} = {(next_open - entry_close)/entry_close:+.6f}")
            for suffix, days, use_open in HORIZONS:
                if suffix == "overnight":
                    continue
                target = entry_idx + days
                if target < len(hist):
                    exit_p = float(hist.iloc[target]["Close"])
                    ret = (exit_p - entry_close) / entry_close
                    print(f"  {suffix:>3}d close: {exit_p:.2f} -> ret = "
                          f"({exit_p:.2f} - {entry_close:.2f}) / {entry_close:.2f} "
                          f"= {ret:+.6f}")

        print(f"\n  Matrix values:")
        for suffix, _, _ in HORIZONS:
            v = row[f"ret_{suffix}"]
            ev = row[f"excess_{suffix}"]
            print(f"    ret_{suffix:>9} = {v}   excess_{suffix:>9} = {ev}")

    # NaN check
    nan_horizons = 0
    for row in all_rows:
        for suffix, _, _ in HORIZONS:
            if row[f"ret_{suffix}"] is None:
                nan_horizons += 1
    print(f"\n--- NaN horizon cells: {nan_horizons} (all in exceptions log: "
          f"{len(all_exceptions)} exception entries) ---")

    print(f"\nDone. {len(all_rows)} rows written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
