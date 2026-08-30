"""
eval/outcomes.py
Fetches actual stock price outcomes via yfinance and buckets them into a
ground-truth BUY/HOLD/SELL label - the label the pipeline's predictions are
scored against.

Two distinct threshold concepts exist in this project and must never be
confused:
  - hold_upper / hold_lower (report_pipeline.py, run_reports.py, blend.py):
    thresholds on the LLM's -1..+1 SENTIMENT SCORE, used to derive a
    prediction (BUY/HOLD/SELL) from what the model said about a document.
  - outcome_upper / outcome_lower (this module): thresholds on the stock's
    actual forward RETURN, used to derive the ground-truth label the
    prediction is checked against. This module always uses the outcome_*
    names - never hold_upper/hold_lower - so the two can't be confused by a
    reader grepping the codebase.

Entry price depends on release_timing (per-issuer, from the manifest):
  after_hours / intraday: Close on report_date (first trading day on/after).
  pre_market: Close on the session BEFORE report_date, so the overnight gap
              captures the actual earnings reaction at the next morning's open.
When release_timing is None, defaults to the after_hours convention.

Overnight-gap mode (exit_on_open=True): exit price is the OPEN of the
window_trading_days-th session after entry, instead of its Close. With
window_trading_days=1 this is the group Google Sheet's ground-truth convention -
(next_day_open - report_date_close) / report_date_close - i.e. the close-to-open
overnight gap the sheet's Actual-Direction formula buckets against Settings!B3.
It matches export_sheet_rows.fetch_prices (prior_close=Close iloc[0],
next_day_open=Open iloc[1]) exactly, so eval and the pasted sheet rows agree.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

OUTCOME_UPPER_DEFAULT = 0.03
OUTCOME_LOWER_DEFAULT = -0.03
DEFAULT_WINDOW_TRADING_DAYS = 5


@dataclass(frozen=True)
class ForwardReturn:
    document_id: str
    ticker: str
    report_date: str
    window_trading_days: int
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    forward_return: float
    outcome_label: str


def bucket_outcome(
    forward_return: float,
    outcome_upper: float = OUTCOME_UPPER_DEFAULT,
    outcome_lower: float = OUTCOME_LOWER_DEFAULT,
) -> str:
    if forward_return > outcome_upper:
        return "BUY"
    if forward_return < outcome_lower:
        return "SELL"
    return "HOLD"


def fetch_forward_return(
    document_id: str,
    ticker: str,
    report_date: str,
    window_trading_days: int = DEFAULT_WINDOW_TRADING_DAYS,
    outcome_upper: float = OUTCOME_UPPER_DEFAULT,
    outcome_lower: float = OUTCOME_LOWER_DEFAULT,
    exit_on_open: bool = False,
    release_timing: str | None = None,
) -> ForwardReturn | None:
    """Fetch forward return for an event.

    release_timing controls entry-date resolution (see export_sheet_rows.fetch_prices):
      pre_market:   entry = close of session BEFORE report_date
      after_hours:  entry = close of report_date itself
      intraday:     raises ValueError (must be excluded)
      None:         raises ValueError (must be populated)
    """
    if release_timing is None:
        raise ValueError(
            f"release_timing is None for {ticker} {report_date} — "
            f"populate the manifest before running"
        )
    if release_timing == "intraday":
        raise ValueError(
            f"release_timing is 'intraday' for {ticker} {report_date} — "
            f"event must be excluded, cannot resolve entry"
        )
    report_dt = datetime.strptime(report_date, "%Y-%m-%d")
    # Pull a wide-enough window to guarantee window_trading_days of trading
    # sessions exist after report_date even across long weekends/holidays.
    # Start earlier if pre_market, since entry is the prior session.
    pre_buffer = 10 if release_timing == "pre_market" else 0
    start = (report_dt - timedelta(days=pre_buffer)).strftime("%Y-%m-%d")
    end = (report_dt + timedelta(days=window_trading_days * 3 + 10)).strftime("%Y-%m-%d")

    history = yf.Ticker(ticker).history(start=start, end=end)
    if history.empty:
        return None
    # Drop timezone
    history = history.copy()
    history.index = pd.to_datetime(history.index).tz_localize(None)

    # Find entry index using timing-aware logic
    report_ts = pd.Timestamp(report_date)
    if release_timing == "pre_market":
        prior_mask = history.index < report_ts
        if not prior_mask.any():
            return None
        import numpy as np
        entry_idx = int(np.asarray(prior_mask).nonzero()[0][-1])
    else:
        rdate_mask = history.index >= report_ts
        if not rdate_mask.any():
            return None
        import numpy as np
        entry_idx = int(np.asarray(rdate_mask).nonzero()[0][0])

    exit_idx = entry_idx + window_trading_days
    if exit_idx >= len(history):
        return None

    entry_row = history.iloc[entry_idx]
    exit_row = history.iloc[exit_idx]
    entry_price = float(entry_row["Close"])
    exit_price = float(exit_row["Open"] if exit_on_open else exit_row["Close"])
    forward_return = (exit_price - entry_price) / entry_price

    return ForwardReturn(
        document_id=document_id,
        ticker=ticker,
        report_date=report_date,
        window_trading_days=window_trading_days,
        entry_date=str(history.index[entry_idx].date()),
        entry_price=round(entry_price, 4),
        exit_date=str(history.index[exit_idx].date()),
        exit_price=round(exit_price, 4),
        forward_return=round(forward_return, 6),
        outcome_label=bucket_outcome(forward_return, outcome_upper, outcome_lower),
    )


def collect_outcomes_for_issuer(
    issuer: str,
    results_dir: Path,
    window_trading_days: int = DEFAULT_WINDOW_TRADING_DAYS,
    outcome_upper: float = OUTCOME_UPPER_DEFAULT,
    outcome_lower: float = OUTCOME_LOWER_DEFAULT,
    exit_on_open: bool = False,
) -> list[ForwardReturn]:
    outcomes: list[ForwardReturn] = []
    for result_path in sorted(results_dir.glob("*.json")):
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        metadata = payload.get("report_metadata", {})
        ticker = metadata.get("ticker")
        report_date = metadata.get("report_date")
        document_id = payload.get("document_id")
        if not ticker or not report_date:
            print(f"  Skipping {result_path.name}: missing ticker/report_date in report_metadata")
            continue

        release_timing = metadata.get("release_timing") or "after_hours"
        outcome = fetch_forward_return(
            document_id, ticker, report_date, window_trading_days, outcome_upper, outcome_lower, exit_on_open,
            release_timing=release_timing,
        )
        if outcome is None:
            print(f"  Skipping {document_id}: no price data available for {ticker} around {report_date}")
            continue
        outcomes.append(outcome)

    return outcomes
