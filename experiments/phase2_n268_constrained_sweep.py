"""
experiments/phase2_n268_constrained_sweep.py

Constrained re-sweep at N=268 (post 2026-08-09 audit-fix pass), built to avoid
the exact overfitting trap CLAUDE.md flags for the full 113,344-combo grid:
trying that many combos guarantees a DSR-inflated-looking winner. Instead:

  - quant fixed at weight 0 (never earns blend weight per project convention -
    production's own ablation already established this).
  - weight step 0.1 (not 0.05) over the (micro, macro, news) simplex only ->
    66 weight combos (vs thousands).
  - SYMMETRIC threshold grid only (hold_upper == -hold_lower), 8 values ->
    528 total combos, not 113,344. A much smaller trial count for the DSR
    correction to swallow.

Reuses experiments/pnl_weight_threshold_sweep.py's tensor math (position_tensor,
pnl_tensor, total_return_from_net, sharpe_and_trade_stats,
deflated_sharpe_ratio, permutation_test_pnl) untouched - only the weight/
threshold grids and the document-loading universe (current N=268 phase2
calibration CSV) change.

Run:  python -m experiments.phase2_n268_constrained_sweep
Out:  outputs/global/summary/phase2_n268_constrained_sweep.json
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from report_pipeline import OUTPUTS_DIR
from blend import DEFAULT_WEIGHTS
from eval.calibrate import DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER
from eval.outcomes import OUTCOME_LOWER_DEFAULT, OUTCOME_UPPER_DEFAULT
from eval.run_eval import build_documents_for_issuer
from experiments.weight_threshold_sweep import build_layer_matrices, dist_from_default
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

WEIGHT_STEP = 0.1                                          # coarser than the full 0.05 grid
THRESH_SYMMETRIC = [round(0.05 * k, 2) for k in range(1, 9)]  # 0.05 .. 0.40, hold_lower = -hold_upper


def weight_grid_3way(step: float) -> np.ndarray:
    """(micro, macro, news, quant) rows summing to 1.0, quant ALWAYS 0 - only
    micro/macro/news form the simplex being searched."""
    n = round(1.0 / step)
    combos = []
    for a in range(n + 1):
        for b in range(n + 1 - a):
            c = n - a - b
            combos.append((a * step, b * step, c * step, 0.0))
    return np.array(combos, dtype=float)


def _calibration_csv_keys():
    import csv
    with open(PHASE2_CALIBRATION_CSV, encoding="utf-8") as fh:
        return {(r["ticker"], r["report_date"]) for r in csv.DictReader(fh)}


def load_phase2_pnl_n268():
    keep = _calibration_csv_keys()
    docs = []
    for issuer in PHASE2_ISSUERS:
        key = f"p2_{issuer}"
        try:
            pairs = list(build_documents_for_issuer(
                key, PNL_WINDOW_TRADING_DAYS, OUTCOME_UPPER_DEFAULT, OUTCOME_LOWER_DEFAULT, exit_on_open=True
            ))
        except FileNotFoundError:
            continue
        for outcome, doc in pairs:
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
    top_k = []
    for ci in order:
        traded_ci = POS[ci] != 0
        dsr_ci = deflated_sharpe_ratio(
            float(sharpe[ci]), int(n_trades[ci]), NET[ci][traded_ci], n_trials, sharpe
        )
        top_k.append({
            "weights": [round(x, 4) for x in W[meta[ci][0]].tolist()],
            "hold_upper": meta[ci][1], "hold_lower": meta[ci][2],
            "total_return_pct": round(float(total_return[ci]) * 100, 2),
            "sharpe_per_trade": round(float(sharpe[ci]), 3),
            "n_trades": int(n_trades[ci]),
            "psr": dsr_ci["psr"] if dsr_ci else None,
        })

    # --- scan EVERY combo's PSR (not just top-K by return) to find the best
    # return achievable subject to a real validity floor, since the raw
    # top-K-by-return combos above all cluster near PSR~0 ---
    all_psr = np.full(ncombo, np.nan)
    for ci in range(ncombo):
        traded_ci = POS[ci] != 0
        if int(n_trades[ci]) < 4:
            continue
        dsr_ci = deflated_sharpe_ratio(float(sharpe[ci]), int(n_trades[ci]), NET[ci][traded_ci], n_trials, sharpe)
        all_psr[ci] = dsr_ci["psr"] if dsr_ci else np.nan
    valid_by_psr = {}
    for floor in (0.5, 0.7, 0.9, 0.95):
        eligible = np.where(all_psr >= floor)[0]
        if len(eligible) == 0:
            valid_by_psr[floor] = None
            continue
        best = eligible[np.argmax(total_return[eligible])]
        traded_b = POS[best] != 0
        dsr_b = deflated_sharpe_ratio(float(sharpe[best]), int(n_trades[best]), NET[best][traded_b], n_trials, sharpe)
        valid_by_psr[floor] = {
            "ci": int(best),
            "weights": [round(x, 4) for x in W[meta[best][0]].tolist()],
            "hold_upper": meta[best][1], "hold_lower": meta[best][2],
            "total_return_pct": round(float(total_return[best]) * 100, 2),
            "sharpe_per_trade": round(float(sharpe[best]), 3),
            "n_trades": int(n_trades[best]),
            "psr": dsr_b["psr"] if dsr_b else None,
        }

    log_net = np.log1p(NET)
    total_log = log_net.sum(axis=1)

    def loocv_for(ci_fixed=None):
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
            avg = float(loo_nets.mean())
            hit = round(float((loo_nets > 0).mean()), 4)
            shp = float(loo_nets.mean() / loo_nets.std() * np.sqrt(loocv_trades)) if loocv_trades > 1 and loo_nets.std() > 0 else 0.0
        else:
            avg, hit, shp = 0.0, 0.0, 0.0
        return {
            "total_return_pct": round(loocv_total_return * 100, 2),
            "avg_net_per_trade_pct": round(avg * 100, 4),
            "hit_rate": hit,
            "n_trades": loocv_trades,
            "sharpe_per_trade": round(shp, 3),
        }

    loocv = loocv_for()

    return {
        "global_best": global_best,
        "top_k": top_k,
        "loocv": loocv,
        "valid_by_psr_floor": valid_by_psr,
        "n": ndoc,
        "_best_ci": best_ci, "_POS": POS, "_NET": NET, "_meta": meta, "_gap": gap, "_W": W,
        "_loocv_for": loocv_for,
    }


def validate_against_backtest(cost_bps, short_borrow_bps):
    import backtest
    llm_preds = list(backtest.llm_predictions(PHASE2_CALIBRATION_CSV))
    return backtest.simulate(llm_preds, cost_bps, short_borrow_bps)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cost-bps", type=float, default=COST_BPS_DEFAULT)
    ap.add_argument("--short-borrow-bps", type=float, default=SHORT_BORROW_BPS_DEFAULT)
    args = ap.parse_args()

    print("Loading phase2 N=268 documents (overnight close-to-open gap)...")
    docs = load_phase2_pnl_n268()
    W = weight_grid_3way(WEIGHT_STEP)
    ncombo = W.shape[0] * len(THRESH_SYMMETRIC)
    n_trials = ncombo
    print(f"N={len(docs)} docs | weight grid={W.shape[0]} (micro/macro/news, quant=0) x "
          f"thresholds={len(THRESH_SYMMETRIC)} (symmetric) = {ncombo} combos")

    result = evaluate(docs, W, n_trials, args.cost_bps, args.short_borrow_bps)
    gb = result["global_best"]
    dsr = gb["deflated_sharpe"]
    psr_txt = f"psr={dsr['psr']}" if dsr else "psr=n/a (too few trades)"
    print(f"global_best total_return={gb['total_return_pct']}% trades={gb['n_trades']} "
          f"sharpe={gb['sharpe_per_trade']} ({psr_txt}) w={gb['weights']} thr=(+-{gb['hold_upper']})")
    print(f"LOOCV total_return={result['loocv']['total_return_pct']}% trades={result['loocv']['n_trades']} "
          f"sharpe={result['loocv']['sharpe_per_trade']}")

    print("\nTop 10 by total return (unconstrained by PSR):")
    for t in result["top_k"]:
        print(f"  w={t['weights'][:3]} thr=+-{t['hold_upper']} return={t['total_return_pct']}% "
              f"trades={t['n_trades']} sharpe={t['sharpe_per_trade']} psr={t['psr']}")

    print("\nBest total-return combo subject to a PSR floor (scanning ALL 528 combos):")
    for floor, v in result["valid_by_psr_floor"].items():
        if v is None:
            print(f"  floor={floor}: no combo clears this PSR")
        else:
            print(f"  floor={floor}: w={v['weights'][:3]} thr=+-{v['hold_upper']} return={v['total_return_pct']}% "
                  f"trades={v['n_trades']} sharpe={v['sharpe_per_trade']} psr={v['psr']}")

    best_ci = result["_best_ci"]
    observed_best_total_return = float(np.expm1(np.log1p(result["_NET"][best_ci]).sum()))
    perm_p = permutation_test_pnl(
        result["_POS"], args.cost_bps, args.short_borrow_bps, result["_gap"], observed_best_total_return,
    )
    print(f"\nPermutation test (top-return combo's total return vs {PERMUTATIONS} gap-shuffles): p={perm_p}")

    # permutation test + a restricted LOOCV (re-select best-by-leave-one-out ONLY among
    # combos that already clear PSR>=0.5 on the full sample) for the PSR-floor candidate
    cand = result["valid_by_psr_floor"].get(0.5)
    cand_perm_p = None
    cand_loocv = None
    if cand is not None:
        ci = cand["ci"]
        POS_all = result["_POS"]; NET_all = result["_NET"]; gap = result["_gap"]
        cand_observed = float(np.expm1(np.log1p(NET_all[ci]).sum()))
        cand_perm_p = permutation_test_pnl(
            POS_all[ci:ci + 1], args.cost_bps, args.short_borrow_bps, gap, cand_observed,
        )
        print(f"\nPSR>=0.5 candidate permutation test: p={cand_perm_p}")

        W_all = result["_W"]; meta = result["_meta"]
        # eligible combos = PSR>=0.5 on the full sample (all_psr computed above, in-scope
        # via closure would be ideal but we recompute the mask cheaply here instead)
        sharpe_all, n_trades_all, _ = sharpe_and_trade_stats(NET_all, POS_all)
        eligible_mask = np.zeros(NET_all.shape[0], dtype=bool)
        for cj in range(NET_all.shape[0]):
            if int(n_trades_all[cj]) < 4:
                continue
            traded_cj = POS_all[cj] != 0
            dsr_cj = deflated_sharpe_ratio(float(sharpe_all[cj]), int(n_trades_all[cj]), NET_all[cj][traded_cj], ncombo, sharpe_all)
            if dsr_cj and dsr_cj["psr"] >= 0.5:
                eligible_mask[cj] = True
        eligible_idx = np.where(eligible_mask)[0]

        log_net = np.log1p(NET_all)
        total_log = log_net.sum(axis=1)
        held_net = np.zeros(len(gap)); held_pos = np.zeros(len(gap), dtype=np.int8)
        for i in range(len(gap)):
            loo_log = (total_log - log_net[:, i])[eligible_idx]
            m = loo_log.max()
            tied_local = np.where(loo_log == m)[0]
            local_best = tied_local[0]
            cj = int(eligible_idx[local_best])
            held_net[i] = NET_all[cj, i]
            held_pos[i] = POS_all[cj, i]
        loocv_tr = float(np.expm1(np.log1p(held_net).sum()))
        loo_traded = held_pos != 0
        loocv_trades = int(loo_traded.sum())
        cand_loocv = {
            "total_return_pct": round(loocv_tr * 100, 2),
            "n_trades": loocv_trades,
            "n_eligible_combos": int(len(eligible_idx)),
        }
        print(f"PSR>=0.5-restricted LOOCV: total_return={cand_loocv['total_return_pct']}% "
              f"trades={cand_loocv['n_trades']} (re-selecting only among {cand_loocv['n_eligible_combos']} "
              f"combos that clear PSR>=0.5 on the full sample)")

    backtest_check = validate_against_backtest(args.cost_bps, args.short_borrow_bps)
    print(f"\nbacktest.py deployed-default (0.55/0.45/0.0/0.0, +0.25/-0.05) on N=268: "
          f"total_return={backtest_check['compounded_total_return_pct']}% trades={backtest_check['n_trades']}")

    out = {
        "n_documents": len(docs),
        "window_trading_days": PNL_WINDOW_TRADING_DAYS,
        "exit_on_open": True,
        "objective": "total_return",
        "constraint_note": "quant fixed at 0 weight; weight_step=0.1 over micro/macro/news simplex only; "
                            "symmetric threshold grid only (hold_upper == -hold_lower). 528 combos total, "
                            "vs the full unconstrained grid's 113,344 - deliberately shrinks the DSR trial "
                            "count per CLAUDE.md's Known-gaps guidance.",
        "cost_bps": args.cost_bps,
        "short_borrow_bps": args.short_borrow_bps,
        "weight_step": WEIGHT_STEP,
        "threshold_grid": {"symmetric_values": THRESH_SYMMETRIC},
        "combos": ncombo,
        "n_trials_corrected_for_dsr": n_trials,
        "deployed_default_reference": {"weights": list(DEFAULT_WEIGHTS), "hold_upper": DEFAULT_HOLD_UPPER,
                                        "hold_lower": DEFAULT_HOLD_LOWER},
        "global_best": result["global_best"],
        "top_k": result["top_k"],
        "loocv": result["loocv"],
        "valid_by_psr_floor": result["valid_by_psr_floor"],
        "psr_floor_0_5_candidate": {
            **(cand or {}),
            "permutation_p": cand_perm_p,
            "restricted_loocv": cand_loocv,
        } if cand else None,
        "significance": {
            "permutation_p_vs_gap_shuffles": perm_p,
            "note": "Positions held fixed, overnight gap shuffled across documents 5000x; "
                    "p = fraction of shuffles whose best achievable total return >= the observed best.",
        },
        "deployed_default_on_n268_backtest": {
            "total_return_pct": backtest_check["compounded_total_return_pct"],
            "n_trades": backtest_check["n_trades"],
            "t_statistic": backtest_check["t_statistic"],
            "max_drawdown_pct": backtest_check["max_drawdown_pct"],
        },
        "deployment_note": "Candidate output only - blend.py's DEFAULT_WEIGHTS is untouched pending review.",
    }
    summary_dir = OUTPUTS_DIR / "global" / "summary"
    path = summary_dir / "phase2_n268_constrained_sweep.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
