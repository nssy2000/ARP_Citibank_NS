"""
experiments/execution_cost_grid_n233.py

Recomputes the breakeven cost_bps for the corrected N=233 clean universe
(35 events excluded: 25 worksheet + 1 SPOT + 9 timing) alongside the
N=268 figure, and bisects on both metrics:
  1. compounded_total_return_pct  — order-dependent, retired headline metric;
                                    kept for continuity with ext9_cost_grid.py
  2. avg_net_per_trade_pct        — order-independent; the study's headline
                                    P&L metric; the primary breakeven figure

PRICE SOURCE: returns_matrix.csv (ret_overnight column, release_date anchor,
corrected 2026-08-12). This is the same source ext2_holding_curve.csv used,
ensuring per-trade gross returns match exactly.  workbook_llm_corrected.csv
was NOT used as the price source because it has next_day_open=0.0 for
KHC_FQ1_2025 (a missing-price sentinel treated as a real zero price), which
would cause a spurious +100% gross return on that trade.

ANCHOR NOTE: All figures in this file are on the CORRECTED release_date
anchor (entry_date in returns_matrix.csv = EDGAR 8-K Item 2.02 release_date,
corrected 2026-08-12).  The original ext9 figure of 162.81bps was computed by
experiments/execution_cost_grid.py on the OLD report_date anchor using
fetch_prices() with the report_date as the entry date — a different anchor and
a different price set.  The two N=268 rows are therefore NOT comparable and
must not be presented alongside 162.81bps without an explicit anchor label.

Short borrow: 0bps throughout (Settings B5=0; deployed default).

Run: python -m experiments.execution_cost_grid_n233
"""
from __future__ import annotations

import csv, json
from pathlib import Path

# ROOT on the path before the repo imports below: run as a script, sys.path[0]
# is experiments/, so `import backtest` raised ModuleNotFoundError.
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import backtest
from backtest import Prediction
from eval.excluded_events import EXCLUDED_EVENTS  # noqa: E402

ROOT    = Path(__file__).resolve().parent.parent
SUMMARY = ROOT / "outputs" / "global" / "summary"

CAL_CSV   = SUMMARY / "global_outcome_calibration_phase2.csv"
RET_CSV   = SUMMARY / "returns_matrix.csv"
WS_FLAGS  = SUMMARY / "worksheet_leak_flags.csv"
OUT_JSON  = SUMMARY / "ext9_cost_grid_n233.json"


# ── Exclusion set (same logic as build_workbook.load_exclusion_set) ───────────

def load_exclusion_set() -> set[str]:
    ws_excluded = set()
    with open(WS_FLAGS) as f:
        for r in csv.DictReader(f):
            if r["has_worksheet"] == "True" and r["has_human_score"] == "True":
                ws_excluded.add(r["document_id"])
    spot = set(EXCLUDED_EVENTS)
    timing = set()
    with open(RET_CSV) as f:
        for r in csv.DictReader(f):
            if r.get("timing_excluded") == "YES":
                timing.add(r["document_id"])
    excluded = ws_excluded | spot | timing
    print(f"  Exclusion set: {len(ws_excluded)} worksheet, 1 SPOT, {len(timing)} timing "
          f"= {len(excluded)} total")
    return excluded


# ── Load ret_overnight from returns_matrix (the authoritative price source) ───

def load_predictions(excluded: set[str]) -> tuple[list[Prediction], list[Prediction]]:
    """Build Prediction objects using ret_overnight from returns_matrix.csv.

    prior_close is set to 1.0 and next_day_open to 1.0 + ret_overnight so that
    overnight_gap() returns ret_overnight exactly, without calling fetch_prices().
    This matches the per-trade gross returns that ext2_holding_curve.csv was
    computed from.

    Rows without a valid ret_overnight are skipped (they will return None from
    overnight_gap() anyway).
    """
    # Decision comes from calibration CSV
    decisions: dict[str, str] = {}
    report_dates: dict[str, str] = {}
    with open(CAL_CSV) as f:
        for r in csv.DictReader(f):
            decisions[r["document_id"]] = r["blend_predicted_signal_default"]
            report_dates[r["document_id"]] = r["report_date"]

    all_preds: list[Prediction] = []
    clean_preds: list[Prediction] = []
    n_no_ret = 0

    with open(RET_CSV) as f:
        for r in csv.DictReader(f):
            doc_id = r["document_id"]
            ret_str = r.get("ret_overnight", "").strip()
            if not ret_str:
                n_no_ret += 1
                continue
            try:
                ret = float(ret_str)
            except ValueError:
                n_no_ret += 1
                continue

            decision = decisions.get(doc_id, "HOLD")
            report_date = report_dates.get(doc_id, r.get("report_date", ""))

            pred = Prediction(
                rater         = "LLM",
                kind          = "LLM",
                ticker        = r["ticker"],
                report_date   = report_date,
                decision      = decision,
                prior_close   = 1.0,
                next_day_open = 1.0 + ret,
            )
            all_preds.append(pred)
            if doc_id not in excluded:
                clean_preds.append(pred)

    if n_no_ret:
        print(f"  WARNING: {n_no_ret} rows skipped for missing ret_overnight")
    return all_preds, clean_preds


# ── Bisect helpers ─────────────────────────────────────────────────────────────

def bisect_on_metric(preds, metric_key: str, lo=0.0, hi=5000.0, tol=0.01) -> float:
    lo_val = backtest.simulate(preds, cost_bps=lo)[metric_key]
    hi_val = backtest.simulate(preds, cost_bps=hi)[metric_key]
    if lo_val < 0:
        raise ValueError(f"{metric_key} already negative at cost_bps={lo}: {lo_val:.4f}")
    if hi_val > 0:
        raise ValueError(f"{metric_key} still positive at cost_bps={hi}: {hi_val:.4f} — widen range")
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if backtest.simulate(preds, cost_bps=mid)[metric_key] > 0:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


def main():
    print("Loading exclusion set ...")
    excluded = load_exclusion_set()

    print("\nLoading predictions from returns_matrix.csv ...")
    all_preds, clean_preds = load_predictions(excluded)
    print(f"  N=268 (all): {len(all_preds)} predictions")
    print(f"  N=233 (clean, {len(excluded)} excluded): {len(clean_preds)} predictions")

    # Baseline stats at deployed cost (10bps, 0 short borrow)
    stats_268 = backtest.simulate(all_preds, cost_bps=10.0, short_borrow_bps=0.0)
    stats_233 = backtest.simulate(clean_preds, cost_bps=10.0, short_borrow_bps=0.0)

    # Arithmetic verification: avg_gross = avg_net + cost
    cost_pct = 10.0 / 100  # 10bps = 0.1%
    gross_268 = stats_268["avg_net_per_trade_pct"] + cost_pct
    gross_233 = stats_233["avg_net_per_trade_pct"] + cost_pct

    print(f"\n  N=268 at 10bps: {stats_268['n_trades']} trades, "
          f"compounded={stats_268['compounded_total_return_pct']:.2f}%, "
          f"mean_net={stats_268['avg_net_per_trade_pct']:.4f}%, "
          f"mean_gross≈{gross_268:.4f}%, implied_be≈{gross_268*100:.1f}bps")
    print(f"  N=233 at 10bps: {stats_233['n_trades']} trades, "
          f"compounded={stats_233['compounded_total_return_pct']:.2f}%, "
          f"mean_net={stats_233['avg_net_per_trade_pct']:.4f}%, "
          f"mean_gross≈{gross_233:.4f}%, implied_be≈{gross_233*100:.1f}bps")

    print(f"\n  ext2_holding_curve.csv authoritative (N=233): mean_net=1.8617% → expected be≈196.2bps")

    print("\nBisecting N=268 breakeven ...")
    be_268_compounded = bisect_on_metric(all_preds, "compounded_total_return_pct")
    be_268_mean_net   = bisect_on_metric(all_preds, "avg_net_per_trade_pct")
    print(f"  N=268 breakeven (compounded total return = 0): {be_268_compounded:.2f} bps")
    print(f"  N=268 breakeven (mean net per trade = 0):      {be_268_mean_net:.2f} bps")

    print("\nBisecting N=233 breakeven ...")
    be_233_compounded = bisect_on_metric(clean_preds, "compounded_total_return_pct")
    be_233_mean_net   = bisect_on_metric(clean_preds, "avg_net_per_trade_pct")
    print(f"  N=233 breakeven (compounded total return = 0): {be_233_compounded:.2f} bps")
    print(f"  N=233 breakeven (mean net per trade = 0):      {be_233_mean_net:.2f} bps")

    summary = {
        "date_computed": "2026-08-13",
        "price_source": (
            "returns_matrix.csv (ret_overnight, entry_date = EDGAR 8-K Item 2.02 "
            "release_date, corrected 2026-08-12). Same source as ext2_holding_curve.csv. "
            "All four rows use the CORRECTED anchor. "
            "workbook_llm_corrected.csv was NOT used because KHC_FQ1_2025 has "
            "next_day_open=0.0 (missing-price sentinel) which produces a spurious +100% gross return."
        ),
        "anchor_note": (
            "The original ext9 figure of 162.81bps (ext9_cost_grid_summary.json) was computed "
            "by experiments/execution_cost_grid.py on the OLD report_date anchor using "
            "fetch_prices(). That is a DIFFERENT anchor and a DIFFERENT price set. "
            "162.81bps is superseded; it must not be placed in the same table as the figures "
            "below without an explicit 'OLD report_date anchor' label."
        ),
        "methodology_note": (
            "Bisects backtest.simulate() cost_bps until the named metric crosses zero. "
            "short_borrow_bps=0 throughout (deployed default, Settings B5=0). "
            "compounded_total_return_pct is order-dependent and the retired headline metric; "
            "avg_net_per_trade_pct is the study's current headline P&L metric and the "
            "primary breakeven figure. "
            "N=233 excludes 35 events (25 worksheet contamination + 1 SPOT misattribution + "
            "9 timing unresolved); same exclusion set as build_workbook.py."
        ),
        "no_external_desk_cost_in_repo": (
            "No externally-cited realistic desk cost exists in this repository. "
            "Dr Rock or any comparable external estimate is not committed here. "
            "The only reference points are: deployed assumption 10bps round-trip "
            "(Model_Arm_Gap_Spec.md line 18). Any claim that the breakeven exceeds "
            "realistic trading costs is UNCITED in this repo and must either be dropped "
            "or attributed to an external source supplied by the user."
        ),
        "n268_corrected_anchor": {
            "n_predictions": len(all_preds),
            "n_trades_at_10bps": stats_268["n_trades"],
            "mean_net_at_10bps_pct": stats_268["avg_net_per_trade_pct"],
            "compounded_return_at_10bps_pct": stats_268["compounded_total_return_pct"],
            "breakeven_compounded_total_return_bps": be_268_compounded,
            "breakeven_mean_net_per_trade_bps": be_268_mean_net,
            "anchor": "corrected release_date (returns_matrix.csv entry_date, 2026-08-12)",
        },
        "n233_corrected_anchor": {
            "n_predictions": len(clean_preds),
            "n_excluded": len(all_preds) - len(clean_preds),
            "n_trades_at_10bps": stats_233["n_trades"],
            "mean_net_at_10bps_pct": stats_233["avg_net_per_trade_pct"],
            "compounded_return_at_10bps_pct": stats_233["compounded_total_return_pct"],
            "breakeven_compounded_total_return_bps": be_233_compounded,
            "breakeven_mean_net_per_trade_bps": be_233_mean_net,
            "anchor": "corrected release_date (returns_matrix.csv entry_date, 2026-08-12)",
        },
        "original_ext9_superseded": {
            "breakeven_bps": 162.81,
            "metric": "compounded_total_return_pct (retired, order-dependent)",
            "anchor": "OLD report_date anchor — SUPERSEDED 2026-08-12",
            "n": 268,
            "source": "ext9_cost_grid_summary.json / experiments/execution_cost_grid.py",
            "comparability": "NOT COMPARABLE to figures above; different anchor, different price set",
        },
        "spec_claimed_bps": 113,
        "spec_breakeven_verified_in_repo": False,
        "spec_breakeven_status": (
            "UNBACKED ASSERTION. 113bps appears in the Model_Arm_Gap_Spec.md but cannot "
            "be reproduced from any artifact in this repository. See asserted_figures_audit.md."
        ),
    }

    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote -> {OUT_JSON.name}")

    print("\n=== SUMMARY TABLE (all rows: CORRECTED release_date anchor) ===")
    print(f"{'Universe':<10} {'N':<5} {'Trades':<7} {'Metric':<42} {'Breakeven':<16}")
    print("-" * 82)
    print(f"{'N=268':<10} {len(all_preds):<5} {stats_268['n_trades']:<7} "
          f"{'compounded total return (RETIRED metric)':<42} {be_268_compounded:<16.2f}")
    print(f"{'N=268':<10} {len(all_preds):<5} {stats_268['n_trades']:<7} "
          f"{'mean net per trade (current headline) [PRIMARY]':<42} {be_268_mean_net:<16.2f}")
    print(f"{'N=233':<10} {len(clean_preds):<5} {stats_233['n_trades']:<7} "
          f"{'compounded total return (RETIRED metric)':<42} {be_233_compounded:<16.2f}")
    print(f"{'N=233':<10} {len(clean_preds):<5} {stats_233['n_trades']:<7} "
          f"{'mean net per trade (current headline) [PRIMARY]':<42} {be_233_mean_net:<16.2f}")
    print()
    print(f"NOT in this table (different anchor, not comparable):")
    print(f"  162.81bps — OLD report_date anchor, N=268, compounded metric (ext9_cost_grid.py, SUPERSEDED)")
    print(f"  113bps    — spec-claimed, UNBACKED, not reproduced from any repo artifact")
    print()
    print(f"No externally-cited realistic desk cost exists in this repo.")


if __name__ == "__main__":
    main()
