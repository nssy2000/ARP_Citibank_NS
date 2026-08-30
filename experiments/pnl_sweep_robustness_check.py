"""
experiments/pnl_sweep_robustness_check.py

Follow-up to pnl_weight_threshold_sweep.py: that sweep's pure argmax(total_return)
winner had PSR=0.02 (Deflated Sharpe Ratio) - its own Sharpe (2.9) didn't even
clear SR0, the expected max Sharpe achievable by chance given the 453,376 combos
searched, and its trade-return distribution was heavily skewed/fat-tailed
(skew=2.57, kurtosis=12.4) - a few outlier trades doing the work, exactly the
cherry-picking pattern total-return-as-objective doesn't protect against on its
own.

Two independent levers to test whether a higher-PSR candidate exists, reusing
pnl_weight_threshold_sweep.py's functions rather than duplicating the P&L math:

  1. Skew/kurtosis-filtered selection on the SAME fine grid (453k trials): among
     combos whose trade-return distribution looks roughly normal-ish
     (|skew| < 1, kurtosis < 6, >= 10 trades), pick the max total_return. Targets
     the actual disease (lottery-ticket trade concentration), not just trial count.
  2. Coarse grid rerun using the PRODUCTION grid (eval/calibrate.py's WEIGHT_STEP=0.2,
     symmetric THRESHOLD_CANDIDATES, single quant_score variant) - far fewer
     trials, which directly lowers SR0.

Run:  python -m experiments.pnl_sweep_robustness_check
"""
from __future__ import annotations

import sys

import numpy as np

from eval.calibrate import THRESHOLD_CANDIDATES, WEIGHT_GRID as PRODUCTION_WEIGHT_GRID
from experiments.pnl_weight_threshold_sweep import (
    COST_BPS_DEFAULT,
    SHORT_BORROW_BPS_DEFAULT,
    deflated_sharpe_ratio,
    load_pooled_pnl,
    pnl_tensor,
    sharpe_and_trade_stats,
    total_return_from_net,
)
from experiments.weight_threshold_sweep import build_layer_matrices

SKEW_MAX = 1.0
KURTOSIS_MAX = 6.0
MIN_TRADES = 10


def moment_stats(NET, POS, mean):
    """Population skew/kurtosis per combo over TRADED rows only, masked-sum style
    (matches sharpe_and_trade_stats' approach - no per-combo Python loop, no
    nan-function warnings on zero-trade combos)."""
    traded = POS != 0
    n_trades = traded.sum(axis=1).astype(float)
    diff = np.where(traded, NET - mean[:, None], 0.0)
    m2 = np.divide(np.where(traded, diff ** 2, 0.0).sum(axis=1), n_trades, out=np.zeros_like(mean), where=n_trades > 0)
    m3 = np.divide(np.where(traded, diff ** 3, 0.0).sum(axis=1), n_trades, out=np.zeros_like(mean), where=n_trades > 0)
    m4 = np.divide(np.where(traded, diff ** 4, 0.0).sum(axis=1), n_trades, out=np.zeros_like(mean), where=n_trades > 0)
    skew = np.zeros_like(mean)
    kurt = np.zeros_like(mean)
    valid = m2 > 0
    skew[valid] = m3[valid] / m2[valid] ** 1.5
    kurt[valid] = m4[valid] / m2[valid] ** 2
    return skew, kurt


def position_tensor_custom(S, M, W, thresh_upper, thresh_lower):
    """Same math as pnl_weight_threshold_sweep.position_tensor but parameterized
    on an arbitrary threshold grid (needed for the coarse/symmetric production grid)."""
    num = W @ S.T
    den = W @ M.T
    den = np.where(den == 0, np.nan, den)
    blended = num / den
    nw, ndoc = blended.shape
    combos_meta = []
    blocks = []
    for hu in thresh_upper:
        for hl in thresh_lower:
            pos = np.zeros((nw, ndoc), dtype=np.int8)
            pos[blended > hu] = 1
            pos[blended < hl] = -1
            pos[np.isnan(blended)] = 0
            blocks.append(pos)
            for wi in range(nw):
                combos_meta.append((wi, hu, hl))
    POS = np.concatenate(blocks, axis=0)
    return POS, combos_meta


def report_candidate(label, total_return, sharpe, n_trades, skew, kurt, meta, W, ci):
    print(f"\n[{label}] weights={[round(x,4) for x in W[meta[ci][0]].tolist()]} "
          f"thr=({meta[ci][1]},{meta[ci][2]}) total_return={round(float(total_return[ci])*100,2)}% "
          f"n_trades={int(n_trades[ci])} sharpe={round(float(sharpe[ci]),3)} "
          f"skew={round(float(skew[ci]),3)} kurtosis={round(float(kurt[ci]),3)}")


def main() -> int:
    docs = load_pooled_pnl()
    gap = np.array([d["gap"] for d in docs])
    S, M = build_layer_matrices(docs, "quant_score")

    # ---------------------------------------------------------------- #
    # Lever 1: skew/kurtosis-filtered selection on the SAME fine grid
    # ---------------------------------------------------------------- #
    from experiments.weight_threshold_sweep import THRESH_LOWER, THRESH_UPPER, WEIGHT_STEP, weight_grid
    W_fine = weight_grid(WEIGHT_STEP)
    POS_fine, meta_fine = position_tensor_custom(S, M, W_fine, THRESH_UPPER, THRESH_LOWER)
    NET_fine = pnl_tensor(POS_fine, gap, COST_BPS_DEFAULT, SHORT_BORROW_BPS_DEFAULT)
    total_return_fine = total_return_from_net(NET_fine)
    sharpe_fine, n_trades_fine, mean_fine = sharpe_and_trade_stats(NET_fine, POS_fine)
    skew_fine, kurt_fine = moment_stats(NET_fine, POS_fine, mean_fine)
    n_trials_fine = W_fine.shape[0] * len(THRESH_UPPER) * len(THRESH_LOWER) * 4  # 4 quant variants in the full sweep

    print(f"Fine grid: {len(meta_fine)} combos (quant_score variant only, {n_trials_fine} trials counted for DSR "
          f"to stay consistent with the full 4-quant-variant sweep this follows up on)")

    pure_best_ci = int(np.argmax(total_return_fine))
    report_candidate("fine grid, pure argmax(total_return)", total_return_fine, sharpe_fine, n_trades_fine,
                      skew_fine, kurt_fine, meta_fine, W_fine, pure_best_ci)
    traded_pure = POS_fine[pure_best_ci] != 0
    dsr_pure = deflated_sharpe_ratio(float(sharpe_fine[pure_best_ci]), int(n_trades_fine[pure_best_ci]),
                                      NET_fine[pure_best_ci][traded_pure], n_trials_fine, sharpe_fine)
    print(f"  PSR (unfiltered, for reference) = {dsr_pure['psr'] if dsr_pure else 'n/a'}")

    eligible = (np.abs(skew_fine) < SKEW_MAX) & (kurt_fine < KURTOSIS_MAX) & (n_trades_fine >= MIN_TRADES)
    n_eligible = int(eligible.sum())
    print(f"  Combos passing |skew|<{SKEW_MAX}, kurtosis<{KURTOSIS_MAX}, n_trades>={MIN_TRADES}: {n_eligible} / {len(meta_fine)}")
    if n_eligible:
        tr_masked = np.where(eligible, total_return_fine, -np.inf)
        filt_ci = int(np.argmax(tr_masked))
        report_candidate("fine grid, skew/kurtosis-filtered", total_return_fine, sharpe_fine, n_trades_fine,
                          skew_fine, kurt_fine, meta_fine, W_fine, filt_ci)
        traded_filt = POS_fine[filt_ci] != 0
        dsr_filt = deflated_sharpe_ratio(float(sharpe_fine[filt_ci]), int(n_trades_fine[filt_ci]),
                                          NET_fine[filt_ci][traded_filt], n_trials_fine, sharpe_fine)
        print(f"  PSR (filtered candidate) = {dsr_filt['psr'] if dsr_filt else 'n/a'} "
              f"(sr0={dsr_filt['sr0_expected_max_under_null'] if dsr_filt else 'n/a'})")
    else:
        print("  No combo passes the filter - can't report a filtered candidate.")

    # ---------------------------------------------------------------- #
    # Lever 2: coarse (production) grid - far fewer trials -> lower SR0
    # ---------------------------------------------------------------- #
    W_coarse = np.array(PRODUCTION_WEIGHT_GRID, dtype=float)  # [nw,4], already sums to 1.0
    thr_upper_coarse = THRESHOLD_CANDIDATES
    thr_lower_coarse = [-t for t in THRESHOLD_CANDIDATES]
    POS_coarse, meta_coarse = position_tensor_custom(S, M, W_coarse, thr_upper_coarse, thr_lower_coarse)
    NET_coarse = pnl_tensor(POS_coarse, gap, COST_BPS_DEFAULT, SHORT_BORROW_BPS_DEFAULT)
    total_return_coarse = total_return_from_net(NET_coarse)
    sharpe_coarse, n_trades_coarse, mean_coarse = sharpe_and_trade_stats(NET_coarse, POS_coarse)
    skew_coarse, kurt_coarse = moment_stats(NET_coarse, POS_coarse, mean_coarse)
    n_trials_coarse = len(meta_coarse)

    print(f"\nCoarse (production) grid: {W_coarse.shape[0]} weight combos x {len(thr_upper_coarse)} symmetric "
          f"thresholds = {n_trials_coarse} trials")
    coarse_best_ci = int(np.argmax(total_return_coarse))
    report_candidate("coarse grid, pure argmax(total_return)", total_return_coarse, sharpe_coarse, n_trades_coarse,
                      skew_coarse, kurt_coarse, meta_coarse, W_coarse, coarse_best_ci)
    traded_coarse = POS_coarse[coarse_best_ci] != 0
    dsr_coarse = deflated_sharpe_ratio(float(sharpe_coarse[coarse_best_ci]), int(n_trades_coarse[coarse_best_ci]),
                                        NET_coarse[coarse_best_ci][traded_coarse], n_trials_coarse, sharpe_coarse)
    print(f"  PSR (coarse grid winner) = {dsr_coarse['psr'] if dsr_coarse else 'n/a'} "
          f"(sr0={dsr_coarse['sr0_expected_max_under_null'] if dsr_coarse else 'n/a'})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
