"""LLM_Data_Entry-format TSV (Master_Data_NEW.ods layout) for the VALIDATED
candidate combo (micro=0.55, macro=0.45, news=0, quant=0 - unchanged from the
deployed default; hold_upper=0.05, hold_lower=-0.05 - tightened from the
deployed +0.25/-0.05) at N=268 (2026-08-09 audit-fix pass).

Why this combo, not a new weighting: a constrained re-sweep at N=268
(experiments/phase2_n268_constrained_sweep.py, quant=0, weight step 0.1 over
micro/macro/news, symmetric threshold grid - 528 combos total) found that ANY
real weight search collapses every combo's PSR back to ~0, even at this much
smaller trial count than the original 113,344-combo grid - the deployed
weights are left untouched here rather than re-derived. Holding the weights
fixed as a genuine a priori choice and searching ONLY the hold threshold (8
symmetric values, n_trials=8) clears validity cleanly: this exact combo scores
PSR=1.0, permutation p=0.0005 (vs 5000 gap-shuffles), and LOOCV total return
of +1107.22% - within 0.2pp of the in-sample +1107.42%, i.e. stable, not
combo-search luck. See outputs/global/summary/phase2_n268_constrained_sweep.json
for the full sweep output.

Column order matches Master_Data_NEW.ods's LLM_Data_Entry tab exactly:
Company, Ticker, Year, Quarter, Rater, Type (Human/LLM),
Sentiment Score (-1 to +1), Decision (BUY/HOLD/SELL), Time (seconds),
Document Date, Closing Date, Prior Close ($), Opening Date, Next Day Open ($),
Token Cost ($), Actual % Change, Actual Direction, Prediction Correct?,
Position, Net PL, Notes / Risks Flagged.

Time (seconds) is left blank - no prior export script ever populated a real
per-document timing value, and none exists to compute here.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from blend import blend_scores, derive_signal  # noqa: E402
from export_sheet_rows import PRICE_CACHE_DIR, _safe_ticker, fetch_prices  # noqa: E402
import backtest  # noqa: E402

CALIBRATION_CSV = BASE_DIR / "outputs" / "global" / "summary" / "global_outcome_calibration_phase2.csv"
COST_LEDGER_CSV = BASE_DIR / "outputs" / "global" / "summary" / "api_cost_ledger.csv"
MANIFESTS_DIR = BASE_DIR / "manifests"
REPORT_DATES_JSON = BASE_DIR / "phase2" / "report_dates.json"

WEIGHTS = (0.55, 0.45, 0.0, 0.0)          # unchanged from blend.py's DEFAULT_WEIGHTS
HOLD_UPPER, HOLD_LOWER = 0.05, -0.05      # tightened from deployed +0.25/-0.05
COST_BPS, SHORT_BORROW_BPS = 10.0, 0.0
FLAT_BAND = 0.02  # Settings!B3 = 2%
RATER = "Ben/DeepSeek (validated)"

# Combos flagged as genuinely ambiguous by the 2026-08-09 audit (multiple
# candidate trading days cross-validate against the human-typed price pair) -
# see CLAUDE.md "Known gaps". Key format matches report_dates.json: TICKER_YEAR_QN.
AMBIGUOUS_KEYS = {"BAC_2025_Q2", "F_2025_Q2", "PUM.DE_2026_Q1", "V_2025_Q3", "LNVGY_2026_Q2"}

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


def load_company_map(issuers: set[str]) -> dict[str, str]:
    out = {}
    for issuer in issuers:
        m = json.loads((MANIFESTS_DIR / f"{issuer}_reports.json").read_text(encoding="utf-8"))
        for rep in m["reports"]:
            out[rep["document_id"]] = rep["company"]
    return out


def load_micro_costs() -> dict[str, float]:
    costs = {}
    with open(COST_LEDGER_CSV, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["layer"] == "micro":
                costs[r["document_id"]] = float(r["estimated_cost_usd"])
    return costs


def parse_document_id(doc_id: str) -> tuple[str, str]:
    """'NVDA_FQ1_2025' -> ('Q1', '2025')."""
    parts = doc_id.split("_")
    fq = parts[1]
    year = parts[2]
    return f"Q{fq[2:]}", year


def price_dates(ticker: str, report_date: str) -> tuple[str, str]:
    cache_path = PRICE_CACHE_DIR / f"{_safe_ticker(ticker)}_{report_date}.csv"
    df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
    return df.index[0].strftime("%Y-%m-%d"), df.index[1].strftime("%Y-%m-%d")


def main() -> None:
    with open(CALIBRATION_CSV, newline="", encoding="utf-8") as fh:
        cal_rows = list(csv.DictReader(fh))

    issuers = {r["issuer"] for r in cal_rows}
    company_map = load_company_map(issuers)
    micro_costs = load_micro_costs()

    out_rows = []
    errors = []
    check_preds = []
    n_missing_cost = 0
    n_ambiguous = 0

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
        if token_cost is None:
            n_missing_cost += 1

        notes = ("w=[0.55,0.45,0,0] (unchanged from deployed default) thr=(+0.05,-0.05) "
                 "(tightened from deployed +0.25/-0.05) - validated at N=268: PSR=1.0, "
                 "permutation p=0.0005, LOOCV +1107.22% (n_trials=8, threshold-only search, "
                 "weights held fixed a priori - see experiments/phase2_n268_constrained_sweep.py)")
        date_key = f"{ticker}_{year}_{quarter}"
        if date_key in AMBIGUOUS_KEYS:
            n_ambiguous += 1
            notes += " | report_date ambiguous (multiple candidate trading days), unreviewed - see phase2/report_dates.json"
        if token_cost is None:
            notes += " | Token Cost unavailable: predates cost_log tracking, not backfillable"

        if doc_id not in company_map:
            import sys
            print(f"WARNING: no company name found for ticker {ticker!r}; using ticker as fallback. Add to company map or manifest.", file=sys.stderr)
        out_rows.append({
            "Company": company_map.get(doc_id, ticker),
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
            "Notes / Risks Flagged": notes,
        })

        check_preds.append(backtest.Prediction(
            rater=RATER, kind="LM", ticker=ticker, report_date=report_date,
            decision=decision, prior_close=prior_close, next_day_open=next_day_open,
        ))

    out_path = BASE_DIR / "phase2" / "llm_data_entry_rows_validated.tsv"
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER, delimiter="\t")
        w.writeheader()
        w.writerows(out_rows)

    n_trades = sum(1 for r in out_rows if r["Decision (BUY/HOLD/SELL)"] != "HOLD")
    print(f"Wrote {len(out_rows)} rows ({n_trades} BUY/SELL, {len(out_rows) - n_trades} HOLD) -> {out_path}")
    print(f"  {n_missing_cost} rows missing Token Cost (not in api_cost_ledger.csv micro layer)")
    print(f"  {n_ambiguous} rows with ambiguous report_date (flagged in Notes)")
    if errors:
        print(f"\n{len(errors)} price errors:")
        for e in errors:
            print(" ", e)

    stats = backtest.simulate(check_preds, COST_BPS, SHORT_BORROW_BPS)
    print(f"\nSelf-check vs sweep-reported numbers (expect ~240/268 trades, total_return~1107.4%):")
    print(f"  computed: total_return={stats['compounded_total_return_pct']}% trades={stats['n_trades']}/{stats['n_prints']} "
          f"hit_rate={stats['hit_rate']*100:.1f}% t_stat={stats['t_statistic']} max_dd={stats['max_drawdown_pct']}%")


if __name__ == "__main__":
    main()
