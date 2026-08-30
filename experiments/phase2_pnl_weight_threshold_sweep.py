"""
experiments/phase2_pnl_weight_threshold_sweep.py

Phase2-scoped sibling of pnl_weight_threshold_sweep.py. Handoff Next Step: now
that phase2 actually has real news digests (98/101 quarters, sourced and
scored this session - see CLAUDE.md's Phase 2 section), test whether phase2's
OWN data wants a different blend weight than the deployed default
(0.8/0.0/0.2/0.0) - motivated by, but not copying, production's own P&L-sweep
winner ([news=0.75], itself DSR-flagged and never promoted). Naively
transplanting an untested combo from a different dataset would repeat the
exact overfitting mistake this whole diagnostic effort has been trying to
avoid - hence a fresh, phase2-scoped, LOOCV + permutation + DSR-checked sweep.

Reuses pnl_weight_threshold_sweep.py's tensor math (position_tensor,
pnl_tensor, total_return_from_net, sharpe_and_trade_stats,
deflated_sharpe_ratio, permutation_test_pnl) and weight_threshold_sweep.py's
grid builders untouched - only the document-loading universe changes
(PHASE2_ISSUERS instead of ALL_ISSUERS) and the self-check target is
backtest.py's phase2 numbers, not the production ones.

Only the single "quant_score" variant is run (not the 4-way quant/Fed
ablation) - production's own ablation already established quant is inert at
N=131, no reason to re-litigate that here, and running one variant keeps the
DSR trial-count correction favorable/accurate for what's actually being
searched (weight simplex x threshold grid only).

Run:  python -m experiments.phase2_pnl_weight_threshold_sweep
Out:  outputs/global/summary/phase2_pnl_weight_threshold_sweep.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from report_pipeline import OUTPUTS_DIR
from blend import DEFAULT_WEIGHTS
from eval.calibrate import DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER
from eval.outcomes import OUTCOME_LOWER_DEFAULT, OUTCOME_UPPER_DEFAULT
from eval.run_eval import build_documents_for_issuer
from experiments.weight_threshold_sweep import (
    THRESH_LOWER,
    THRESH_UPPER,
    WEIGHT_STEP,
    _default_combo_index,
    build_layer_matrices,
    dist_from_default,
    weight_grid,
)
from experiments.pnl_weight_threshold_sweep import (
    PERMUTATIONS,
    RNG_SEED,
    TOP_K,
    deflated_sharpe_ratio,
    permutation_test_pnl,
    pnl_tensor,
    position_tensor,
    sharpe_and_trade_stats,
    total_return_from_net,
)
import quant_layer
from llm_news import PHASE2_ISSUERS

PNL_WINDOW_TRADING_DAYS = 1
COST_BPS_DEFAULT = 10.0
SHORT_BORROW_BPS_DEFAULT = 0.0
PHASE2_CALIBRATION_CSV = OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration_phase2.csv"


def _calibration_csv_keys():
    """The exact (ticker, report_date) universe backtest.py trades (N=101) -
    window=1/exit_on_open=True can resolve one extra doc (GS_FQ2_2026) that the
    accuracy eval's window=5 couldn't (price data for a report 6 days old vs a
    30-day-out window), so it's excluded here to keep this sweep's self-check
    apples-to-apples against backtest.py's actual traded universe."""
    import csv
    with open(PHASE2_CALIBRATION_CSV, encoding="utf-8") as fh:
        return {(r["ticker"], r["report_date"]) for r in csv.DictReader(fh)}


def load_phase2_pnl():
    """Same shape as pnl_weight_threshold_sweep.load_pooled_pnl(), but over the
    28 p2_ issuers instead of ALL_ISSUERS. build_documents_for_issuer works
    generically for any issuer string already (confirmed in blend.py/llm_news.py's
    p2_ MANIFESTS wiring), so no new loading logic is needed. Filtered to the
    same N=101 universe as the phase2 calibration CSV, see _calibration_csv_keys."""
    keep = _calibration_csv_keys()
    docs = []
    for issuer in PHASE2_ISSUERS:
        key = f"p2_{issuer}"
        for outcome, doc in build_documents_for_issuer(
            key, PNL_WINDOW_TRADING_DAYS, OUTCOME_UPPER_DEFAULT, OUTCOME_LOWER_DEFAULT, exit_on_open=True
        ):
            if (outcome.ticker, outcome.report_date) not in keep:
                continue
            qpayload = quant_layer.get_quant_score(key, doc.document_id)
            qmetrics = (qpayload or {}).get("quant_metrics", {})
            docs.append({
                "document_id": doc.document_id,
                "issuer": key,
                "ticker": outcome.ticker,
                "report_date": outcome.report_date,
                "gap": outcome.forward_return,
                "micro": doc.micro_score,
                "macro": doc.macro_score,
                "news": doc.news_score,
                "quant_variants": {"quant_score": qmetrics.get("quant_score")},
            })
    docs.sort(key=lambda d: d["report_date"])
    return docs


def evaluate(docs, W, n_trials, cost_bps, short_borrow_bps):
    gap = np.array([d["gap"] for d in docs])
    S, M = build_layer_matrices(docs, "quant_score")
    POS, meta = position_tensor(S, M, W)
    NET = pnl_tensor(POS, gap, cost_bps, short_borrow_bps)
    ncombo, ndoc = NET.shape

    total_return = total_return_from_net(NET)
    sharpe, n_trades, avg_net_per_trade = sharpe_and_trade_stats(NET, POS)

    best_val = total_return.max()
    tied = np.where(total_return == best_val)[0]
    best_ci = int(min(tied, key=lambda ci: dist_from_default(W[meta[ci][0]], meta[ci][1], meta[ci][2])))
    bw, bhu, bhl = W[meta[best_ci][0]], meta[best_ci][1], meta[best_ci][2]

    best_traded = POS[best_ci] != 0
    dsr = deflated_sharpe_ratio(
        float(sharpe[best_ci]), int(n_trades[best_ci]), NET[best_ci][best_traded], n_trials, sharpe
    )

    global_best = {
        "total_return_pct": round(float(total_return[best_ci]) * 100, 2),
        "avg_net_per_trade_pct": round(float(avg_net_per_trade[best_ci]) * 100, 4),
        "sharpe_per_trade": round(float(sharpe[best_ci]), 3),
        "n_trades": int(n_trades[best_ci]),
        "weights": [round(x, 4) for x in bw.tolist()],
        "hold_upper": bhu, "hold_lower": bhl,
        "n_tied": int(len(tied)),
        "deflated_sharpe": dsr,
    }

    order = np.argsort(-total_return)[:TOP_K]
    top_k = [{
        "weights": [round(x, 4) for x in W[meta[ci][0]].tolist()],
        "hold_upper": meta[ci][1], "hold_lower": meta[ci][2],
        "total_return_pct": round(float(total_return[ci]) * 100, 2),
        "sharpe_per_trade": round(float(sharpe[ci]), 3),
        "n_trades": int(n_trades[ci]),
    } for ci in order]

    log_net = np.log1p(NET)
    total_log = log_net.sum(axis=1)
    default_ci = _default_combo_index(meta, W)

    held_net = np.zeros(ndoc)
    held_pos = np.zeros(ndoc, dtype=np.int8)
    for i in range(ndoc):
        loo_log = total_log - log_net[:, i]
        m = loo_log.max()
        tied_i = np.where(loo_log == m)[0]
        ci = int(min(tied_i, key=lambda ci: dist_from_default(W[meta[ci][0]], meta[ci][1], meta[ci][2])))
        held_net[i] = NET[ci, i]
        held_pos[i] = POS[ci, i]

    loocv_total_return = float(np.expm1(np.log1p(held_net).sum()))
    loo_traded = held_pos != 0
    loocv_trades = int(loo_traded.sum())
    if loocv_trades:
        loo_nets = held_net[loo_traded]
        loocv_avg_net_per_trade = float(loo_nets.mean())
        loocv_hit_rate = round(float((loo_nets > 0).mean()), 4)
        loocv_sharpe = float(loo_nets.mean() / loo_nets.std() * np.sqrt(loocv_trades)) if loocv_trades > 1 and loo_nets.std() > 0 else 0.0
    else:
        loocv_avg_net_per_trade = 0.0
        loocv_hit_rate = 0.0
        loocv_sharpe = 0.0

    return {
        "global_best": global_best,
        "top_k": top_k,
        "loocv_total_return_pct": round(loocv_total_return * 100, 2),
        "loocv_avg_net_per_trade_pct": round(loocv_avg_net_per_trade * 100, 4),
        "loocv_hit_rate": loocv_hit_rate,
        "loocv_n_trades": loocv_trades,
        "loocv_sharpe_per_trade": round(loocv_sharpe, 3),
        "default_total_return_pct": round(float(total_return[default_ci]) * 100, 2),
        "default_avg_net_per_trade_pct": round(float(avg_net_per_trade[default_ci]) * 100, 4),
        "default_sharpe_per_trade": round(float(sharpe[default_ci]), 3),
        "default_n_trades": int(n_trades[default_ci]),
        "n": ndoc,
        "_best_ci": best_ci, "_POS": POS, "_NET": NET, "_meta": meta, "_gap": gap,
    }


def validate_against_backtest(cost_bps, short_borrow_bps):
    """Self-check against backtest.py's phase2 numbers (post-news-sourcing state:
    51 trades, +30.16% total return), same discipline as the production sweep."""
    import backtest
    llm_preds = list(backtest.llm_predictions(PHASE2_CALIBRATION_CSV))
    return backtest.simulate(llm_preds, cost_bps, short_borrow_bps)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cost-bps", type=float, default=COST_BPS_DEFAULT)
    ap.add_argument("--short-borrow-bps", type=float, default=SHORT_BORROW_BPS_DEFAULT)
    args = ap.parse_args()

    print("Loading phase2 documents (overnight close-to-open gap, window_trading_days=1)...")
    docs = load_phase2_pnl()
    W = weight_grid(WEIGHT_STEP)
    ncombo = W.shape[0] * len(THRESH_UPPER) * len(THRESH_LOWER)
    n_trials = ncombo  # single quant variant only
    print(f"N={len(docs)} docs | weight grid={W.shape[0]} x thresholds={len(THRESH_UPPER)*len(THRESH_LOWER)} "
          f"= {ncombo} combos (single quant_score variant)")

    result = evaluate(docs, W, n_trials, args.cost_bps, args.short_borrow_bps)
    gb = result["global_best"]
    dsr = gb["deflated_sharpe"]
    psr_txt = f"psr={dsr['psr']}" if dsr else "psr=n/a (too few trades)"
    print(f"global_best total_return={gb['total_return_pct']}% trades={gb['n_trades']} "
          f"sharpe={gb['sharpe_per_trade']} ({psr_txt}) w={gb['weights']} thr=({gb['hold_upper']},{gb['hold_lower']})")
    print(f"LOOCV total_return={result['loocv_total_return_pct']}% trades={result['loocv_n_trades']} "
          f"sharpe={result['loocv_sharpe_per_trade']}")
    print(f"deployed-default (0.8/0.0/0.2/0.0, +-0.25) total_return={result['default_total_return_pct']}% "
          f"trades={result['default_n_trades']} avg/trade={result['default_avg_net_per_trade_pct']}%")

    best_ci = result["_best_ci"]
    observed_best_total_return = float(np.expm1(np.log1p(result["_NET"][best_ci]).sum()))
    perm_p = permutation_test_pnl(
        result["_POS"], args.cost_bps, args.short_borrow_bps, result["_gap"], observed_best_total_return,
    )
    print(f"\nPermutation test (best combo's total return vs {PERMUTATIONS} gap-shuffles): p={perm_p}")

    backtest_check = validate_against_backtest(args.cost_bps, args.short_borrow_bps)
    default_via_sweep = result["default_total_return_pct"]
    default_via_backtest = backtest_check["compounded_total_return_pct"]
    match = abs(default_via_sweep - default_via_backtest) < 0.5
    print(f"\nSelf-check vs backtest.py: sweep's default-combo total_return={default_via_sweep}% "
          f"vs backtest.py's reported={default_via_backtest}% -> {'MATCH' if match else 'MISMATCH - investigate'}")

    out = {
        "n_documents": len(docs),
        "window_trading_days": PNL_WINDOW_TRADING_DAYS,
        "exit_on_open": True,
        "objective": "total_return",
        "quant_variant": "quant_score (single variant only - production already established quant is inert)",
        "cost_bps": args.cost_bps,
        "short_borrow_bps": args.short_borrow_bps,
        "weight_step": WEIGHT_STEP,
        "threshold_grid": {"upper": THRESH_UPPER, "lower": THRESH_LOWER, "asymmetric": True},
        "combos": ncombo,
        "n_trials_corrected_for_dsr": n_trials,
        "default_config": {"weights": list(DEFAULT_WEIGHTS), "hold_upper": DEFAULT_HOLD_UPPER, "hold_lower": DEFAULT_HOLD_LOWER},
        "global_best": result["global_best"],
        "top_k": result["top_k"],
        "loocv": {
            "total_return_pct": result["loocv_total_return_pct"],
            "avg_net_per_trade_pct": result["loocv_avg_net_per_trade_pct"],
            "hit_rate": result["loocv_hit_rate"],
            "n_trades": result["loocv_n_trades"],
            "sharpe_per_trade": result["loocv_sharpe_per_trade"],
        },
        "deployed_default_on_phase2": {
            "total_return_pct": result["default_total_return_pct"],
            "avg_net_per_trade_pct": result["default_avg_net_per_trade_pct"],
            "sharpe_per_trade": result["default_sharpe_per_trade"],
            "n_trades": result["default_n_trades"],
        },
        "significance": {
            "permutation_p_vs_gap_shuffles": perm_p,
            "note": "Positions held fixed, overnight gap shuffled across documents 5000x; "
                    "p = fraction of shuffles whose best achievable total return >= the observed best.",
        },
        "vs_backtest_py": {
            "backtest_py_reported": {k: backtest_check[k] for k in (
                "n_trades", "total_return_pct", "avg_net_per_trade_pct", "sharpe_per_trade", "max_drawdown_pct")},
            "self_check_match": match,
        },
        "deployment_note": "Candidate output only - blend.py's DEFAULT_WEIGHTS is untouched pending review. "
                            "Compare global_best/loocv against production's own P&L-sweep winner "
                            "([micro=0.2, macro=0.0, news=0.75, quant=0.05], PSR=0.02) for context, "
                            "but this is phase2's own independently-fit and independently-DSR-checked result.",
    }
    summary_dir = OUTPUTS_DIR / "global" / "summary"
    path = summary_dir / "phase2_pnl_weight_threshold_sweep.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
