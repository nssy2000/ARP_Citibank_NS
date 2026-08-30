"""Generate paste-ready Data Entry rows for the Phase 2 (apples-to-apples,
102-combo) LLM run - one row per scoreable combo, in the exact Data Entry
column order (Company, Ticker blank/auto, Year, Quarter, Rater, Type,
Sentiment Score, Decision, Time blank, Prior Close, Next Day Open,
Actual % Change/Actual Direction/Prediction Correct/Position/Net P&L
blank - sheet formulas fill these, Notes).
Company spelling matches the `list` sheet exactly so the XLOOKUP resolves.

Decision/Sentiment Score are read from the calibration CSV
(global_outcome_calibration_phase2.csv), NOT recomputed via
blend.blend_document() - that function's own default hold_upper/lower is
+/-0.15, while the canonical methodology used everywhere else (eval/calibrate.py,
backtest.py, the deployed default) is +/-0.25. Using blend_document()'s signal
here previously produced a Decision column with a tighter trade-taking band
than backtest.py actually scores, causing the pasted sheet numbers (77 trades)
to disagree with backtest.py's own reported numbers (52 trades) even though
both were reading the same underlying data - a real inconsistency, not sheet
noise. Run `python -m eval.run_eval --issuers ... --output-suffix phase2`
before this script so the calibration CSV is current.

No live sheet editing (per project rule) - just writes a CSV for copy-paste.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from export_sheet_rows import compute_blend_score, fetch_prices, load_notes  # noqa: E402

CALIBRATION_CSV = BASE_DIR / "outputs" / "global" / "summary" / "global_outcome_calibration_phase2.csv"

COMPANY_NAMES = {
    "ABNB": "Airbnb", "AMZN": "Amazon", "AMD": "AMD", "AAPL": "Apple",
    "BAC": "Bank of America", "BA": "Boeing", "CVS": "CVS Health",
    "SCHW": "Charles Schwab", "C": "Citigroup", "KO": "Coca-Cola",
    "COIN": "Coinbase", "DIS": "Disney", "LLY": "Eli Lilly",
    "GS": "Goldman Sachs", "IBM": "IBM", "JPM": "JPMorgan",
    "LOW": "Lowe's", "LULU": "Lululemon", "AMKBY": "Maersk",
    "MCD": "McDonald's", "META": "Meta", "NFLX": "Netflix", "NKE": "Nike",
    "NVDA": "Nvidia", "TGT": "Target", "TSLA": "Tesla", "UBER": "Uber",
    "WMT": "Walmart",
    "BCS": "Barclays", "F": "Ford", "MSFT": "Microsoft", "PFE": "Pfizer",
    "UAL": "United Airlines",
    "PEP": "PepsiCo", "FDX": "FedEx", "LMT": "Lockheed Martin",
    "NVO": "Novo Nordisk", "HLT": "Hilton", "MC.PA": "LVMH", "MAR": "Marriott",
}

QUARTER_NUM = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}


def parse_document_id(doc_id: str) -> tuple[str, str]:
    """'NVDA_FQ1_2025' -> ('Q1', '2025')."""
    parts = doc_id.split("_")
    fq = parts[1]  # 'FQ1'
    year = parts[2]
    return f"Q{fq[2:]}", year


def main() -> None:
    if not CALIBRATION_CSV.exists():
        raise SystemExit(
            f"{CALIBRATION_CSV} not found - run "
            f"`python -m eval.run_eval --issuers <p2_issuers> --output-suffix phase2` first"
        )

    with open(CALIBRATION_CSV, newline="", encoding="utf-8") as fh:
        cal_rows = list(csv.DictReader(fh))

    out_rows = []
    errors = []

    for row in cal_rows:
        issuer = row["issuer"]
        doc_id = row["document_id"]
        ticker = row["ticker"]
        report_date = row["report_date"]
        micro = float(row["micro_score"])
        news_val = row["news_score"]
        news = float(news_val) if news_val not in ("", "None", None) else None
        blend_score = compute_blend_score(micro, news)
        decision = row["blend_predicted_signal_default"]
        quarter, year = parse_document_id(doc_id)

        try:
            prior_close, next_day_open = fetch_prices(ticker, report_date)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{issuer}/{doc_id}: price fetch failed: {exc}")
            prior_close, next_day_open = "", ""

        notes = load_notes(issuer, doc_id, micro, blend_score, news is not None)

        out_rows.append({
            "Company": COMPANY_NAMES[ticker],
            "Ticker": "",  # auto via XLOOKUP off Company
            "Year": year,
            "Quarter": quarter,
            "Rater": "Ben/DeepSeek",
            "Type": "LLM",
            "Sentiment Score": f"{blend_score:.2f}",
            "Decision": decision,
            "Time": "",
            "Prior Close": f"{prior_close:.2f}" if prior_close != "" else "",
            "Next Day Open": f"{next_day_open:.2f}" if next_day_open != "" else "",
            "Actual % Change": "",
            "Actual Direction": "",
            "Prediction Correct": "",
            "Position": "",
            "Net P&L": "",
            "Notes": notes,
        })

    out_path = BASE_DIR / "phase2" / "data_entry_rows.tsv"
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(out_rows)

    n_trades = sum(1 for r in out_rows if r["Decision"] != "HOLD")
    print(f"Wrote {len(out_rows)} rows ({n_trades} BUY/SELL, {len(out_rows) - n_trades} HOLD) -> {out_path}")
    if errors:
        print(f"\n{len(errors)} errors:")
        for e in errors:
            print(" ", e)


if __name__ == "__main__":
    main()
