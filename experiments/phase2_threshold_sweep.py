"""
experiments/phase2_threshold_sweep.py

Handoff Next Step: on the phase2 apples-to-apples track (28-issuer human
comparison set), sweep hold_upper/hold_lower upward from 0.15 with weights
held fixed at the deployed DEFAULT_WEIGHTS (0.8/0.0/0.2/0.0), to see how much
of the phase2-vs-production avg-P&L/trade gap (0.657%/trade vs 2.504%/trade)
closes as trade-taking selectivity drops toward the deployed model's ~34%
(44/131) rate. Absolute total return stays the priority metric, not just
matching the selectivity rate - both are reported per threshold.

Deliberately NOT built on the tensor-vectorized weight x threshold grid
pnl_weight_threshold_sweep.py uses for its 113k-combo search: weights are
fixed here, so the blended score per document only needs computing once, and
a plain Python loop over ~10 threshold levels x 101 documents calls
backtest.simulate() directly - reusing the exact validated P&L/cost/equity
logic instead of re-deriving it.

Run:  python -m experiments.phase2_threshold_sweep
Out:  outputs/global/summary/phase2_threshold_sweep.json
"""
from __future__ import annotations

import csv
import json

from report_pipeline import OUTPUTS_DIR
from blend import DEFAULT_WEIGHTS, blend_scores, derive_signal
import backtest

PHASE2_CALIBRATION_CSV = OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration_phase2.csv"
THRESHOLD_GRID = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
DEPLOYED_SELECTIVITY = 44 / 131  # production 6-issuer/N=131 trade rate, the target to compare against
COST_BPS = 10.0
SHORT_BORROW_BPS = 0.0


def _num(x):
    if x is None:
        return None
    x = str(x).strip()
    return float(x) if x else None


def load_phase2_docs(path=PHASE2_CALIBRATION_CSV):
    docs = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            docs.append({
                "ticker": r["ticker"],
                "report_date": r["report_date"],
                "micro": _num(r["micro_score"]),
                "macro": _num(r["macro_score"]),
                "news": _num(r["news_score"]),
                "quant": _num(r["quant_score"]),
            })
    return docs


def blended_scores(docs, weights=DEFAULT_WEIGHTS):
    """Blended score per doc, computed once - independent of threshold."""
    return [blend_scores(d["micro"], d["macro"], d["news"], d["quant"], weights) for d in docs]


def sweep(docs, blended, thresholds=THRESHOLD_GRID, cost_bps=COST_BPS, short_borrow_bps=SHORT_BORROW_BPS):
    rows = []
    for hu in thresholds:
        preds = [
            backtest.Prediction(
                rater="LLM (DeepSeek) phase2", kind="LM",
                ticker=d["ticker"], report_date=d["report_date"],
                decision=derive_signal(b, hu, -hu),
            )
            for d, b in zip(docs, blended)
        ]
        stats = backtest.simulate(preds, cost_bps, short_borrow_bps)
        rows.append({
            "hold_upper": hu,
            "hold_lower": -hu,
            "n_trades": stats["n_trades"],
            "n_prints": stats["n_prints"],
            "selectivity_pct": round(100 * stats["n_trades"] / stats["n_prints"], 2) if stats["n_prints"] else 0.0,
            "total_return_pct": stats["compounded_total_return_pct"],
            "avg_net_per_trade_pct": stats["avg_net_per_trade_pct"],
            "hit_rate": stats["hit_rate"],
            "sharpe_per_trade": stats["t_statistic"],
            "max_drawdown_pct": stats["max_drawdown_pct"],
        })
        if stats["n_trades"] == 0:
            break
    return rows


def main() -> int:
    docs = load_phase2_docs()
    blended = blended_scores(docs)
    print(f"N={len(docs)} phase2 docs, weights={DEFAULT_WEIGHTS}")

    rows = sweep(docs, blended)

    # self-check: hu=0.25 is the real deployed threshold (eval/calibrate.py's
    # DEFAULT_HOLD_UPPER/LOWER), not 0.15 - must reproduce backtest.py's own
    # already-reported phase2 numbers off the same calibration CSV.
    backtest_check = backtest.simulate(
        list(backtest.llm_predictions(PHASE2_CALIBRATION_CSV)), COST_BPS, SHORT_BORROW_BPS
    )
    row_025 = next(r for r in rows if r["hold_upper"] == 0.25)
    match = (
        row_025["n_trades"] == backtest_check["n_trades"]
        and abs(row_025["total_return_pct"] - backtest_check["compounded_total_return_pct"]) < 0.5
    )
    print(
        f"\nSelf-check @ hu=0.25 vs backtest.py: sweep trades={row_025['n_trades']} "
        f"total_return={row_025['total_return_pct']}% | backtest.py trades={backtest_check['n_trades']} "
        f"total_return={backtest_check['compounded_total_return_pct']}% -> {'MATCH' if match else 'MISMATCH - investigate'}"
    )

    print(f"\n{'hu':>5} {'trades':>7} {'select%':>8} {'totRet%':>9} {'avg%/trd':>9} {'hit%':>6} {'Shrp':>6} {'maxDD%':>7}")
    print("-" * 62)
    for r in rows:
        print(
            f"{r['hold_upper']:>5.2f} {r['n_trades']:>7} {r['selectivity_pct']:>7.1f}% "
            f"{r['total_return_pct']:>9.2f} {r['avg_net_per_trade_pct']:>9.3f} "
            f"{r['hit_rate']*100:>5.1f}% {r['sharpe_per_trade']:>6.2f} {r['max_drawdown_pct']:>7.2f}"
        )

    target_trades = round(DEPLOYED_SELECTIVITY * rows[0]["n_prints"])
    closest_to_target = min(rows, key=lambda r: abs(r["n_trades"] - target_trades))
    best_total_return = max(rows, key=lambda r: r["total_return_pct"])
    print(f"\nDeployed selectivity {DEPLOYED_SELECTIVITY*100:.1f}% (44/131) -> target ~{target_trades} trades on phase2's N={rows[0]['n_prints']}")
    print(f"Closest-to-target selectivity: hu={closest_to_target['hold_upper']} ({closest_to_target['n_trades']} trades, "
          f"total_return={closest_to_target['total_return_pct']}%, avg={closest_to_target['avg_net_per_trade_pct']}%/trade)")
    print(f"Best total return: hu={best_total_return['hold_upper']} ({best_total_return['n_trades']} trades, "
          f"total_return={best_total_return['total_return_pct']}%, avg={best_total_return['avg_net_per_trade_pct']}%/trade)")

    out = {
        "n_documents": len(docs),
        "weights": list(DEFAULT_WEIGHTS),
        "cost_bps": COST_BPS,
        "short_borrow_bps": SHORT_BORROW_BPS,
        "threshold_grid": THRESHOLD_GRID,
        "deployed_default_note": "eval/calibrate.py's DEFAULT_HOLD_UPPER/LOWER=0.25 is the real baked-in "
                                  "phase2 threshold, not the 0.15 documented in CLAUDE.md/handoff.md - see hu=0.25 row.",
        "rows": rows,
        "self_check_vs_backtest_py": {
            "match": match,
            "sweep_hu025": {"n_trades": row_025["n_trades"], "total_return_pct": row_025["total_return_pct"]},
            "backtest_py_reported": {
                "n_trades": backtest_check["n_trades"],
                "total_return_pct": backtest_check["compounded_total_return_pct"],
                "avg_net_per_trade_pct": backtest_check["avg_net_per_trade_pct"],
            },
        },
        "deployed_selectivity_pct": round(DEPLOYED_SELECTIVITY * 100, 2),
        "target_trades_for_deployed_selectivity": target_trades,
        "closest_to_deployed_selectivity": closest_to_target,
        "best_total_return": best_total_return,
    }
    summary_dir = OUTPUTS_DIR / "global" / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    path = summary_dir / "phase2_threshold_sweep.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
