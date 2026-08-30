"""One-off: LLM_Data_Entry-format TSV (Master_Data_NEW.ods layout) for the
sweep's global_best combo (micro=0.55, macro=0.45, news=0, quant=0;
hold_upper=0.25, hold_lower=-0.05), 99 trades, total_return=167.66% per
outputs/global/summary/phase2_pnl_weight_threshold_sweep.json.

NOT PSR/permutation-validated (PSR=0.0, perm p=0.150) - candidate row only, not a
proposal to change blend.py's DEFAULT_WEIGHTS. All columns computed directly (no
blank sheet-formula columns) so the row is paste-ready as literal values.

Column order matches Master_Data_NEW.ods's LLM_Data_Entry tab exactly:
Company, Ticker, Year, Quarter, Rater, Type (Human/LLM),
Sentiment Score (-1 to +1), Decision (BUY/HOLD/SELL), Time (seconds),
Document Date, Closing Date, Prior Close ($), Opening Date, Next Day Open ($),
Token Cost ($), Actual % Change, Actual Direction, Prediction Correct?,
Position, Net PL, Notes / Risks Flagged.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from blend import blend_scores, derive_signal  # noqa: E402
from export_sheet_rows import PRICE_CACHE_DIR, _safe_ticker, fetch_prices  # noqa: E402
from phase2.export_rows import COMPANY_NAMES, parse_document_id  # noqa: E402
import backtest  # noqa: E402

CALIBRATION_CSV = BASE_DIR / "outputs" / "global" / "summary" / "global_outcome_calibration_phase2.csv"
COST_LEDGER_CSV = BASE_DIR / "outputs" / "global" / "summary" / "api_cost_ledger.csv"
WEIGHTS = (0.55, 0.45, 0.0, 0.0)
HOLD_UPPER, HOLD_LOWER = 0.25, -0.05
COST_BPS, SHORT_BORROW_BPS = 10.0, 0.0
FLAT_BAND = 0.02  # Settings!B3 = 2%
RATER = "Ben/DeepSeek (aggressive: micro.55/macro.45)"

HEADER = [
    "Company", "Ticker", "Year", "Quarter", "Rater", "Type (Human/LLM)",
    "Sentiment Score (-1 to +1)", "Decision (BUY/HOLD/SELL)", "Time (seconds)",
    "Document Date", "Closing Date", "Prior Close ($)", "Opening Date",
    "Next Day Open ($)", "Token Cost ($)", "Actual % Change", "Actual Direction",
    "Prediction Correct?", "Position", "Net PL", "Notes / Risks Flagged",
]


def _num(x):
    if x in (None, "", "None"):
        return None
    return float(x)


def load_micro_costs():
    """document_id -> micro-layer estimated_cost_usd (the LLM call that scored
    that specific quarter; macro is amortized across companies so excluded)."""
    costs = {}
    with open(COST_LEDGER_CSV, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["layer"] == "micro":
                costs[r["document_id"]] = float(r["estimated_cost_usd"])
    return costs


def price_dates(ticker: str, report_date: str):
    """Read the cached yfinance history to recover the actual calendar dates
    behind fetch_prices()'s prior_close (iloc[0]) / next_day_open (iloc[1])."""
    cache_path = PRICE_CACHE_DIR / f"{_safe_ticker(ticker)}_{report_date}.csv"
    df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
    closing_date = df.index[0].strftime("%Y-%m-%d")
    opening_date = df.index[1].strftime("%Y-%m-%d")
    return closing_date, opening_date


def main() -> None:
    with open(CALIBRATION_CSV, newline="", encoding="utf-8") as fh:
        cal_rows = list(csv.DictReader(fh))
    micro_costs = load_micro_costs()

    out_rows = []
    errors = []
    check_preds = []

    for row in cal_rows:
        ticker = row["ticker"]
        report_date = row["report_date"]
        doc_id = row["document_id"]
        micro = float(row["micro_score"])
        macro = _num(row["macro_score"])
        news = _num(row["news_score"])
        quant = _num(row["quant_score"])

        blend_score = blend_scores(micro, macro, news, quant, WEIGHTS)
        decision = derive_signal(blend_score, HOLD_UPPER, HOLD_LOWER)
        quarter, year = parse_document_id(doc_id)

        try:
            prior_close, next_day_open = fetch_prices(ticker, report_date)
            closing_date, opening_date = price_dates(ticker, report_date)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{doc_id}: price fetch failed: {exc}")
            continue

        pct_change = (next_day_open - prior_close) / prior_close
        if pct_change >= FLAT_BAND:
            direction = "UP"
        elif pct_change <= -FLAT_BAND:
            direction = "DOWN"
        else:
            direction = "FLAT"

        correct = (
            (decision == "BUY" and direction == "UP")
            or (decision == "SELL" and direction == "DOWN")
            or (decision == "HOLD" and direction == "FLAT")
        )

        position = {"BUY": 1, "SELL": -1, "HOLD": 0}[decision]
        if position == 0:
            net_pnl = 0.0
        else:
            cost = COST_BPS / 1e4 + (SHORT_BORROW_BPS / 1e4 if position < 0 else 0.0)
            net_pnl = position * pct_change - cost

        token_cost = micro_costs.get(doc_id)

        out_rows.append({
            "Company": COMPANY_NAMES.get(ticker, ticker),
            "Ticker": ticker,
            "Year": year,
            "Quarter": quarter,
            "Rater": RATER,
            "Type (Human/LLM)": "LLM",
            "Sentiment Score (-1 to +1)": f"{blend_score:.4f}",
            "Decision (BUY/HOLD/SELL)": decision,
            "Time (seconds)": "",
            "Document Date": report_date,
            "Closing Date": closing_date,
            "Prior Close ($)": f"{prior_close:.2f}",
            "Opening Date": opening_date,
            "Next Day Open ($)": f"{next_day_open:.2f}",
            "Token Cost ($)": f"{token_cost:.6f}" if token_cost is not None else "",
            "Actual % Change": f"{pct_change*100:.2f}%",
            "Actual Direction": direction,
            "Prediction Correct?": "YES" if correct else "NO",
            "Position": position,
            "Net PL": f"{net_pnl*100:.4f}%",
            "Notes / Risks Flagged": f"micro={micro:.2f} macro={'n/a' if macro is None else f'{macro:.2f}'} "
                                      f"w=[0.55,0.45,0,0] thr=(0.25,-0.05) - PSR=0.0/perm_p=0.150, unvalidated",
        })

        check_preds.append(backtest.Prediction(
            rater=RATER, kind="LM", ticker=ticker, report_date=report_date,
            decision=decision, prior_close=prior_close, next_day_open=next_day_open,
        ))

    out_path = BASE_DIR / "phase2" / "llm_data_entry_rows_aggressive.tsv"
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER, delimiter="\t")
        w.writeheader()
        w.writerows(out_rows)

    n_trades = sum(1 for r in out_rows if r["Decision (BUY/HOLD/SELL)"] != "HOLD")
    n_missing_cost = sum(1 for r in out_rows if not r["Token Cost ($)"])
    print(f"Wrote {len(out_rows)} rows ({n_trades} BUY/SELL, {len(out_rows) - n_trades} HOLD) -> {out_path}")
    if n_missing_cost:
        print(f"  {n_missing_cost} rows missing Token Cost (not in api_cost_ledger.csv micro layer)")
    if errors:
        print(f"\n{len(errors)} price errors:")
        for e in errors:
            print(" ", e)

    stats = backtest.simulate(check_preds, COST_BPS, SHORT_BORROW_BPS)
    print(f"\nSelf-check vs sweep JSON (expect total_return=167.66%, trades=99):")
    print(f"  computed: total_return={stats['compounded_total_return_pct']}% trades={stats['n_trades']} "
          f"hit_rate={stats['hit_rate']*100:.1f}% t_stat={stats['t_statistic']}")


if __name__ == "__main__":
    main()
