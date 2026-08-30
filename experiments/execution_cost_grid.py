"""
experiments/execution_cost_grid.py
Extension 9 of the model-arm spec (Nigel, 2026-08-05): a result that only
works at zero trading cost is not a result. Nothing is rescored - same
trades, same signals, more subtracted, via backtest.simulate()'s existing
cost_bps parameter.

12-cell grid: round-trip cost in {10, 20, 30, 50} bps x entry slippage in
{0, 10, 20} bps. backtest.simulate() has no separate slippage parameter -
its cost model is a single cost_bps/1e4 subtracted per trade (plus
short_borrow_bps/1e4 on SELL). Slippage is therefore modelled as additive
to cost_bps (total_cost_bps = round_trip_bps + slippage_bps), since both
are subtracted identically from gross return per trade - this is a modelling
choice made explicit here rather than silently.

The spec's own conventions section claims a ~113bps model-arm breakeven is
"already computed" - grepped the whole repo (code, CLAUDE.md, README,
outputs), no such figure exists anywhere. Rather than cite an unverifiable
number, this script bisects for the actual breakeven cost_bps on the current
N=268/DEFAULT_WEIGHTS backtest and reports that as the real, derived figure.

Run: python -m experiments.execution_cost_grid
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import backtest

PHASE2_CALIBRATION_CSV = backtest.OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration_phase2.csv"
GRID_CSV = backtest.OUTPUTS_DIR / "global" / "summary" / "ext9_cost_grid.csv"
SUMMARY_JSON = backtest.OUTPUTS_DIR / "global" / "summary" / "ext9_cost_grid_summary.json"

ROUND_TRIP_BPS = (10, 20, 30, 50)
SLIPPAGE_BPS = (0, 10, 20)

# Known deployed backtest figure (2026-08-10 rerun, after fixing AMKBY_FQ4_2025's
# corrupted report_date - see CLAUDE.md) used as a sanity anchor that this
# script's cost_bps=10 cell reproduces it exactly.
KNOWN_N268_TOTAL_RETURN_PCT = 1243.64


def run_grid(preds: list) -> list[dict]:
    rows = []
    for round_trip in ROUND_TRIP_BPS:
        for slippage in SLIPPAGE_BPS:
            total_cost = round_trip + slippage
            stats = backtest.simulate(preds, cost_bps=float(total_cost))
            rows.append({
                "round_trip_bps": round_trip,
                "slippage_bps": slippage,
                "total_cost_bps": total_cost,
                "n_trades": stats["n_trades"],
                "hit_rate": stats["hit_rate"],
                "total_return_pct": stats["compounded_total_return_pct"],
                "avg_net_per_trade_pct": stats["avg_net_per_trade_pct"],
            })
    return rows


def bisect_breakeven(preds: list, lo: float = 0.0, hi: float = 5000.0, tol: float = 0.01) -> float:
    """Find the cost_bps where total_return_pct crosses zero, via bisection.
    Assumes total_return_pct is monotonically decreasing in cost_bps (true
    here since cost is subtracted identically per trade regardless of sign)."""
    lo_ret = backtest.simulate(preds, cost_bps=lo)["compounded_total_return_pct"]
    hi_ret = backtest.simulate(preds, cost_bps=hi)["compounded_total_return_pct"]
    if lo_ret < 0:
        raise ValueError(f"compounded_total_return_pct already negative at cost_bps={lo}: {lo_ret}")
    if hi_ret > 0:
        raise ValueError(f"compounded_total_return_pct still positive at cost_bps={hi}: {hi_ret} - widen search range")

    while hi - lo > tol:
        mid = (lo + hi) / 2
        mid_ret = backtest.simulate(preds, cost_bps=mid)["compounded_total_return_pct"]
        if mid_ret > 0:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {path}")


def main() -> int:
    preds = list(backtest.llm_predictions(PHASE2_CALIBRATION_CSV))
    print(f"Loaded {len(preds)} predictions from {PHASE2_CALIBRATION_CSV.name}")

    rows = run_grid(preds)
    write_csv(GRID_CSV, rows)

    # sanity anchor: cost_bps=10, slippage=0 must reproduce the known deployed
    # N=268 total return exactly, confirming this script didn't diverge from
    # backtest.simulate()'s own defaults.
    base_cell = next(r for r in rows if r["round_trip_bps"] == 10 and r["slippage_bps"] == 0)
    matches_known = abs(base_cell["total_return_pct"] - KNOWN_N268_TOTAL_RETURN_PCT) < 0.01
    print(f"\nSanity check (cost=10bps, slippage=0): total_return_pct={base_cell['total_return_pct']}% "
          f"vs known deployed figure {KNOWN_N268_TOTAL_RETURN_PCT}% -> "
          f"{'MATCH' if matches_known else 'MISMATCH - investigate before trusting this grid'}")

    monotonic = all(
        rows[i]["total_return_pct"] >= rows[i + 1]["total_return_pct"] - 1e-6
        for i in range(len(rows) - 1)
        if rows[i]["round_trip_bps"] == rows[i + 1]["round_trip_bps"]
    )
    print(f"Monotonic decrease within each round-trip band as slippage rises: {monotonic}")

    breakeven = bisect_breakeven(preds)
    print(f"\nBisected breakeven cost_bps (total_return_pct crosses zero): {breakeven} bps")
    print("Spec's own 'already computed ~113bps' figure could not be verified anywhere in this "
          "repo (grepped code, CLAUDE.md, README, outputs) - not cited as fact. The bisected "
          f"figure above ({breakeven} bps) is this repo's own N=268/DEFAULT_WEIGHTS breakeven, "
          "not a reproduction of the spec's number, and is expected to differ since the spec's "
          "113bps was computed on a different N/weight combination.")

    summary = {
        "n_predictions": len(preds),
        "sanity_check_matches_known_n268_total_return": matches_known,
        "monotonic_decrease_within_round_trip_band": monotonic,
        "bisected_breakeven_cost_bps": breakeven,
        "spec_claimed_breakeven_bps": 113,
        "spec_breakeven_verified_in_repo": False,
        "note": ("Slippage modelled as additive to cost_bps (total_cost_bps = round_trip_bps + "
                 "slippage_bps) since backtest.simulate() has a single cost_bps parameter, no "
                 "separate slippage parameter."),
    }
    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote summary -> {SUMMARY_JSON}")

    print("\nGrid:")
    for r in rows:
        print(f"  round_trip={r['round_trip_bps']:2}bps  slippage={r['slippage_bps']:2}bps  "
              f"total_cost={r['total_cost_bps']:2}bps  total_return={r['total_return_pct']:>9.2f}%  "
              f"avg/trade={r['avg_net_per_trade_pct']:>7.4f}%  n_trades={r['n_trades']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
