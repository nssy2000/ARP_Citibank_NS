"""
experiments/pnl_weight_threshold_sweep.py

P&L-objective sibling of weight_threshold_sweep.py (the accuracy-objective
Round 5 sweep). Total return - not average P&L per trade, which rewards
cherry-picking a handful of lucky trades - is the sweep's objective, over the
identical N=131 pooled document universe and the identical (micro, macro,
news, quant) weight simplex / asymmetric hold-threshold grid. Ground truth is
the overnight close-to-open gap (window_trading_days=1, exit_on_open=True) -
the strategy backtest.py actually trades, not the 5-day accuracy-tuning
window.

Total return is order-invariant (a product of (1+net) terms), so the whole
combo grid is scored with two matrix multiplies + a log-space sum - no
per-combo refit and no per-combo price refetch (the overnight gap for each of
the 131 documents is fetched once, exactly like the accuracy sweep's ground
truth).

Sharpe is reported for every combo (not just the winner) as a risk lens
alongside total return, plus a Deflated Sharpe Ratio (Bailey & Lopez de Prado,
2014) for the winning combo: it discounts the naive Sharpe estimate for (a)
how many combos were searched (~113k combos x 4 quant variants - trying that
many and taking the best inflates Sharpe by construction) and (b) the winning
combo's own trade count / skew / kurtosis, instead of an arbitrary "Sharpe > X
is too risky" cutoff.

Run:  python -m experiments.pnl_weight_threshold_sweep
Out:  outputs/global/summary/pnl_weight_threshold_sweep.json
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np
from scipy.stats import kurtosis as _kurtosis, norm, skew as _skew

from report_pipeline import OUTPUTS_DIR
from blend import DEFAULT_WEIGHTS, blend_scores, derive_signal
from eval.calibrate import DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER
from eval.outcomes import OUTCOME_LOWER_DEFAULT, OUTCOME_UPPER_DEFAULT
from eval.run_eval import ALL_ISSUERS, build_documents_for_issuer
from experiments.weight_threshold_sweep import (
    QUANT_VARIANTS,
    THRESH_LOWER,
    THRESH_UPPER,
    WEIGHT_STEP,
    _default_combo_index,
    build_layer_matrices,
    dist_from_default,
    weight_grid,
)
import quant_layer

PNL_WINDOW_TRADING_DAYS = 1   # overnight close-to-open, matches backtest.py's traded strategy
COST_BPS_DEFAULT = 10.0
SHORT_BORROW_BPS_DEFAULT = 0.0
PERMUTATIONS = 5000
RNG_SEED = 20260709
TOP_K = 10
EULER_MASCHERONI = 0.5772156649


def load_pooled_pnl():
    """Same pooled document set as weight_threshold_sweep.load_pooled(), plus each
    doc's overnight close-to-open gap return (continuous P&L ground truth, not a
    bucketed label). outcome_upper/lower are unused for P&L (only bucket the label
    we discard) so the module defaults are passed through untouched."""
    docs = []
    for issuer in ALL_ISSUERS:
        for outcome, doc in build_documents_for_issuer(
            issuer, PNL_WINDOW_TRADING_DAYS, OUTCOME_UPPER_DEFAULT, OUTCOME_LOWER_DEFAULT, exit_on_open=True
        ):
            qpayload = quant_layer.get_quant_score(issuer, doc.document_id)
            qmetrics = (qpayload or {}).get("quant_metrics", {})
            docs.append({
                "document_id": doc.document_id,
                "issuer": issuer,
                "ticker": outcome.ticker,
                "report_date": outcome.report_date,
                "gap": outcome.forward_return,
                "micro": doc.micro_score,
                "macro": doc.macro_score,
                "news": doc.news_score,
                "quant_variants": {v: qmetrics.get(v) for v in QUANT_VARIANTS},
            })
    docs.sort(key=lambda d: d["report_date"])
    return docs


def position_tensor(S, M, W):
    """blended [nw,ndoc] then POS [ncombo,ndoc] int8 in {-1,0,+1} for every
    (weight row, hold_upper, hold_lower) combo. combos_meta parallels
    weight_threshold_sweep.correctness_tensor's (weight_idx, hu, hl) layout, so
    the exact same combo ordering/tie-break helpers apply."""
    num = W @ S.T
    den = W @ M.T
    den = np.where(den == 0, np.nan, den)
    blended = num / den                # [nw,ndoc]; NaN only if a doc has zero total weight
    nw, ndoc = blended.shape

    combos_meta = []
    blocks = []
    for hu in THRESH_UPPER:
        for hl in THRESH_LOWER:
            pos = np.zeros((nw, ndoc), dtype=np.int8)
            pos[blended > hu] = 1
            pos[blended < hl] = -1
            pos[np.isnan(blended)] = 0   # no usable weight -> no trade, not a loss
            blocks.append(pos)
            for wi in range(nw):
                combos_meta.append((wi, hu, hl))
    POS = np.concatenate(blocks, axis=0)  # [ncombo,ndoc]
    return POS, combos_meta


def pnl_tensor(POS, gap, cost_bps=COST_BPS_DEFAULT, short_borrow_bps=SHORT_BORROW_BPS_DEFAULT):
    """NET [ncombo,ndoc] - identical cost model to backtest.py's simulate(): cost
    charged only when a position is taken, extra short-borrow bps only on SELLs."""
    gross = POS * gap[None, :]
    cost = np.where(POS != 0, cost_bps / 1e4, 0.0) + np.where(POS < 0, short_borrow_bps / 1e4, 0.0)
    return gross - cost


def total_return_from_net(NET):
    """Total return is order-invariant (product of (1+net) terms), computed in
    log-space for numerical stability across ~113k combos at once."""
    return np.expm1(np.log1p(NET).sum(axis=1))


def sharpe_and_trade_stats(NET, POS):
    """Per-combo per-trade Sharpe (mean/std over TRADED rows only, population std,
    scaled by sqrt(n_trades) - matches backtest.py's sharpe_per_trade exactly),
    n_trades, and avg_net_per_trade. Masked sums instead of nan-functions so no
    combo with zero trades emits a warning."""
    traded = POS != 0
    n_trades = traded.sum(axis=1).astype(float)
    sum_net = np.where(traded, NET, 0.0).sum(axis=1)
    mean = np.divide(sum_net, n_trades, out=np.zeros_like(sum_net), where=n_trades > 0)
    sq = np.where(traded, (NET - mean[:, None]) ** 2, 0.0).sum(axis=1)
    var = np.divide(sq, n_trades, out=np.zeros_like(sum_net), where=n_trades > 0)
    std = np.sqrt(var)
    sharpe = np.zeros(len(n_trades))
    valid = (n_trades > 1) & (std > 0)
    sharpe[valid] = mean[valid] / std[valid] * np.sqrt(n_trades[valid])
    return sharpe, n_trades.astype(int), mean


def deflated_sharpe_ratio(sr_hat, n_trades, net_trades, n_trials, sr_all_combos):
    """Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio. Corrects the observed
    per-trade Sharpe for (a) selection bias from trying n_trials combos - via SR0,
    the expected max Sharpe achievable under a zero-skill null given that many
    trials and the sweep's OWN observed cross-combo Sharpe variance - and (b) the
    winning combo's sample size / skew / kurtosis, via the Probabilistic Sharpe
    Ratio. Returns None if there are too few trades to estimate skew/kurtosis.
    psr (0..1): the confidence the Sharpe is real skill, not a search/luck
    artifact - NOT a flat "Sharpe > X" cutoff."""
    if n_trades < 4:
        return None
    var_sr = float(np.var(sr_all_combos, ddof=1))
    if var_sr <= 0 or n_trials < 2:
        sr0 = 0.0
    else:
        z1 = norm.ppf(1 - 1.0 / n_trials)
        z2 = norm.ppf(1 - 1.0 / (n_trials * np.e))
        sr0 = float(np.sqrt(var_sr) * ((1 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2))
    g3 = float(_skew(net_trades))
    g4 = float(_kurtosis(net_trades, fisher=False))  # Pearson (non-excess) kurtosis
    denom = np.sqrt(max(1e-12, 1 - g3 * sr_hat + ((g4 - 1) / 4) * sr_hat ** 2))
    psr_stat = (sr_hat - sr0) * np.sqrt(n_trades - 1) / denom
    return {
        "sr0_expected_max_under_null": round(sr0, 4),
        "skew": round(g3, 4),
        "kurtosis": round(g4, 4),
        "psr": round(float(norm.cdf(psr_stat)), 4),
        "n_trials_corrected_for": int(n_trials),
    }


def evaluate_variant(docs, quant_variant, W, n_trials, cost_bps, short_borrow_bps):
    gap = np.array([d["gap"] for d in docs])
    S, M = build_layer_matrices(docs, quant_variant)
    POS, meta = position_tensor(S, M, W)
    NET = pnl_tensor(POS, gap, cost_bps, short_borrow_bps)
    ncombo, ndoc = NET.shape

    total_return = total_return_from_net(NET)
    sharpe, n_trades, avg_net_per_trade = sharpe_and_trade_stats(NET, POS)

    # --- global best-fit (fit on all docs; tie-break toward the default config) ---
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

    # --- top-K candidates by total return, for the risk/return tradeoff table ---
    order = np.argsort(-total_return)[:TOP_K]
    top_k = [{
        "weights": [round(x, 4) for x in W[meta[ci][0]].tolist()],
        "hold_upper": meta[ci][1], "hold_lower": meta[ci][2],
        "total_return_pct": round(float(total_return[ci]) * 100, 2),
        "sharpe_per_trade": round(float(sharpe[ci]), 3),
        "n_trades": int(n_trades[ci]),
    } for ci in order]

    # --- pooled LOOCV (leave-one-doc-out): total return is a log-space sum, so
    # excluding doc i is a vectorized subtraction, not a refit ---
    log_net = np.log1p(NET)                 # [ncombo,ndoc]
    total_log = log_net.sum(axis=1)         # [ncombo]
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
        "_best_ci": best_ci, "_default_ci": default_ci,  # internal, stripped before JSON dump
        "_POS": POS, "_NET": NET, "_meta": meta, "_gap": gap,  # internal, used for permutation test only
    }


def permutation_test_pnl(POS, cost_bps, short_borrow_bps, gap, observed_best_total_return,
                          seed=RNG_SEED, perms=PERMUTATIONS):
    """Hold every combo's POSITIONS fixed, shuffle which document's overnight gap
    return each position is paired with, and see how often the best achievable
    total return under that null meets/exceeds the observed best. p = fraction
    >= observed - a real permutation test, same spirit as the accuracy sweep's."""
    cost = np.where(POS != 0, cost_bps / 1e4, 0.0) + np.where(POS < 0, short_borrow_bps / 1e4, 0.0)
    rng = np.random.default_rng(seed)
    ge = 0
    for _ in range(perms):
        gap_perm = rng.permutation(gap)
        net_perm = POS * gap_perm[None, :] - cost
        tr = np.expm1(np.log1p(net_perm).sum(axis=1))
        ge += int(tr.max() >= observed_best_total_return)
    return round((ge + 1) / (perms + 1), 5)


def validate_against_backtest(cost_bps, short_borrow_bps):
    """Self-check: the deployed default combo (0.8/0.0/0.2/0.0, +-0.25) run through
    THIS script's own pnl_tensor math must reproduce backtest.py's existing
    reported numbers (same calibration CSV, same cost model), or the P&L
    reimplementation has a bug."""
    import backtest
    llm_preds = list(backtest.llm_predictions())
    return backtest.simulate(llm_preds, cost_bps, short_borrow_bps)


def _strip_internal(result: dict) -> dict:
    return {k: v for k, v in result.items() if not k.startswith("_")}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cost-bps", type=float, default=COST_BPS_DEFAULT,
                     help="Round-trip transaction cost in basis points (default 10, matches backtest.py).")
    ap.add_argument("--short-borrow-bps", type=float, default=SHORT_BORROW_BPS_DEFAULT,
                     help="Extra per-night borrow cost on SELL trades (default 0, matches backtest.py).")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    print("Loading pooled documents (overnight close-to-open gap, window_trading_days=1)...")
    docs = load_pooled_pnl()
    W = weight_grid(WEIGHT_STEP)
    ncombo = W.shape[0] * len(THRESH_UPPER) * len(THRESH_LOWER)
    n_trials = ncombo * len(QUANT_VARIANTS)
    print(f"N={len(docs)} docs | weight grid={W.shape[0]} x thresholds={len(THRESH_UPPER)*len(THRESH_LOWER)} "
          f"= {ncombo} combos/variant ({n_trials} total trials across {len(QUANT_VARIANTS)} quant variants)")

    variants = {}
    raw = {}
    for v in QUANT_VARIANTS:
        r = evaluate_variant(docs, v, W, n_trials, args.cost_bps, args.short_borrow_bps)
        raw[v] = r
        variants[v] = _strip_internal(r)
        gb = variants[v]["global_best"]
        dsr = gb["deflated_sharpe"]
        psr_txt = f"psr={dsr['psr']}" if dsr else "psr=n/a (too few trades)"
        print(f"  [{v}] global_best total_return={gb['total_return_pct']}% trades={gb['n_trades']} "
              f"sharpe={gb['sharpe_per_trade']} ({psr_txt}) w={gb['weights']} thr=({gb['hold_upper']},{gb['hold_lower']}) "
              f"| LOOCV total_return={variants[v]['loocv_total_return_pct']}% trades={variants[v]['loocv_n_trades']} "
              f"sharpe={variants[v]['loocv_sharpe_per_trade']} | deployed-default total_return={variants[v]['default_total_return_pct']}%")

    # significance + validation on the primary (headline) quant variant only
    primary = raw["quant_score"]
    best_ci = primary["_best_ci"]
    observed_best_total_return = float(np.expm1(np.log1p(primary["_NET"][best_ci]).sum()))
    perm_p = permutation_test_pnl(
        primary["_POS"], args.cost_bps, args.short_borrow_bps, primary["_gap"],
        observed_best_total_return,
    )
    print(f"\nPermutation test (best combo's total return vs {PERMUTATIONS} gap-shuffles): p={perm_p}")

    backtest_check = validate_against_backtest(args.cost_bps, args.short_borrow_bps)
    default_via_sweep = variants["quant_score"]["default_total_return_pct"]
    default_via_backtest = backtest_check["compounded_total_return_pct"]
    match = abs(default_via_sweep - default_via_backtest) < 0.5
    print(f"\nSelf-check vs backtest.py: sweep's default-combo total_return={default_via_sweep}% "
          f"vs backtest.py's reported={default_via_backtest}% -> {'MATCH' if match else 'MISMATCH - investigate'}")

    out = {
        "n_documents": len(docs),
        "window_trading_days": PNL_WINDOW_TRADING_DAYS,
        "exit_on_open": True,
        "objective": "total_return",
        "cost_bps": args.cost_bps,
        "short_borrow_bps": args.short_borrow_bps,
        "weight_step": WEIGHT_STEP,
        "threshold_grid": {"upper": THRESH_UPPER, "lower": THRESH_LOWER, "asymmetric": True},
        "combos_per_variant": ncombo,
        "n_trials_corrected_for_dsr": n_trials,
        "default_config": {"weights": list(DEFAULT_WEIGHTS), "hold_upper": DEFAULT_HOLD_UPPER, "hold_lower": DEFAULT_HOLD_LOWER},
        "variants": variants,
        "significance": {
            "permutation_p_vs_gap_shuffles": perm_p,
            "note": "Positions held fixed, overnight gap shuffled across documents 5000x; "
                    "p = fraction of shuffles whose best achievable total return >= the observed best.",
        },
        "vs_deployed_default": {
            "backtest_py_reported": {
                "n_trades": backtest_check["n_trades"],
                "total_return_pct": backtest_check["compounded_total_return_pct"],
                "avg_net_per_trade_pct": backtest_check["avg_net_per_trade_pct"],
                "t_statistic": backtest_check["t_statistic"],
                "max_drawdown_pct": backtest_check["max_drawdown_pct"],
            },
            "this_sweep_default_combo": {
                "total_return_pct": default_via_sweep,
                "n_trades": variants["quant_score"]["default_n_trades"],
                "avg_net_per_trade_pct": variants["quant_score"]["default_avg_net_per_trade_pct"],
                "sharpe_per_trade": variants["quant_score"]["default_sharpe_per_trade"],
            },
            "self_check_match": match,
        },
        "deployment_note": "Candidate output only - blend.py's DEFAULT_WEIGHTS is untouched pending review.",
    }
    summary_dir = OUTPUTS_DIR / "global" / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    path = summary_dir / "pnl_weight_threshold_sweep.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
