"""
experiments/conviction_position_sizing_sweep.py

Tests the one P&L lever nothing else in this project has tried: conviction-
weighted position sizing. backtest.py's simulate() sizes every trade at a
fixed +-1 unit regardless of |blend_score| - a BUY at blended=0.26 and a BUY
at blended=0.95 get identical exposure. This script asks whether scaling
trade size with how far the blended score sits past the hold threshold beats
that fixed sizing, on the SAME weights/threshold/document set backtest.py
already uses (production N=131, overnight close-to-open gap) - it does not
re-sweep weights or thresholds, which are held at the deployed default
(blend.DEFAULT_WEIGHTS, +-0.25) so this experiment isolates sizing as an
orthogonal lever, not a joint re-search.

Sizing function (per document, once a trade is taken):
    excess    = clip(|blended| - hold_upper, 0, None)
    size_mag  = clip(1.0 + slope * excess, 1.0, size_max)
    size      = sign(blended) * size_mag        (0 inside the hold band)

slope=0 (any size_max >= 1) is the CONTROL combo: size_mag is always exactly
1.0, so it must reproduce backtest.py's fixed +-1 sizing bit-for-bit. That
reproduction is asserted, not just printed, before any other combo's numbers
are trusted.

Cost scales with |size| (cost_bps/1e4 * |size|, plus short_borrow_bps/1e4 *
|size| on shorts) rather than backtest.py's flat per-trade charge. This is a
deliberate generalization, not a divergence bug: backtest.py's flat cost was
only ever exercised at |position| == 1, where "flat" and "proportional to
size" are the same number. A future reader porting cost logic back to
backtest.py should NOT copy the flat version here - it would undercount cost
on any trade sized above 1 unit.

size_max is capped at 3.0. total_return_from_net()'s log1p(NET) trick needs
NET > -1 per trade (a single trade can't lose more than 100% of allocated
capital or the log-space product breaks). NFLX's historical +-15-30% gap
moves are this dataset's tail (see CLAUDE.md's production-benchmark
concentration finding) - size_max=3 keeps meaningful headroom under that
tail; NET is also explicitly clipped and any clipping is reported, not
silently absorbed.

Every other P&L lever tried in this project (production/phase2/pooled weight-
threshold sweeps) has been held to a 4-gate discipline before being
considered for promotion: (1) beats the deployed default on total return
in-sample, (2) survives leave-one-doc-out CV, (3) survives a permutation
test, (4) survives a Deflated Sharpe Ratio check if the winner came from a
combinatorial search. This script applies the identical four gates and
reuses deflated_sharpe_ratio() from pnl_weight_threshold_sweep.py rather than
reimplementing it.

Run:  python -m experiments.conviction_position_sizing_sweep
Out:  outputs/global/summary/conviction_position_sizing_sweep.json
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from report_pipeline import OUTPUTS_DIR
from blend import DEFAULT_WEIGHTS, blend_scores
from eval.calibrate import DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER
from experiments.pnl_weight_threshold_sweep import (
    COST_BPS_DEFAULT,
    PERMUTATIONS,
    RNG_SEED,
    SHORT_BORROW_BPS_DEFAULT,
    TOP_K,
    deflated_sharpe_ratio,
    load_pooled_pnl,
    validate_against_backtest,
)

SLOPES = [round(x, 2) for x in np.arange(0.0, 4.01, 0.25)]   # 17 values, 0 = control
SIZE_MAXES = [1.0, 1.5, 2.0, 2.5, 3.0]                        # 5 values, leverage cap
SIZE_MIN = 1.0                                                 # floor exposure once a trade is taken
NET_FLOOR = -0.999                                              # keeps log1p(NET) in-domain


def blended_scores(docs, weights=DEFAULT_WEIGHTS) -> np.ndarray:
    """blend.blend_scores() per doc. quant weight is 0.0 in the deployed default,
    so which quant variant is attached to each doc is irrelevant to the result -
    the headline "quant_score" variant is used purely for a stable field name."""
    return np.array([
        blend_scores(d["micro"], d["macro"], d["news"], d["quant_variants"]["quant_score"], weights)
        for d in docs
    ])


def size_tensor(blended, hold_upper, hold_lower, slopes=SLOPES, size_maxes=SIZE_MAXES, size_min=SIZE_MIN):
    """SIZE [ncombo,ndoc] float: signed trade size per (slope, size_max) combo.
    combos_meta parallels SIZE's row order for LOOCV/permutation bookkeeping."""
    sign = np.sign(blended)
    hold_mask = (blended <= hold_upper) & (blended >= hold_lower)
    excess = np.clip(np.abs(blended) - hold_upper, 0, None)

    combos_meta = []
    blocks = []
    for slope in slopes:
        for size_max in size_maxes:
            size_mag = np.clip(size_min + slope * excess, size_min, size_max)
            size = sign * size_mag
            size[hold_mask] = 0.0
            blocks.append(size)
            combos_meta.append((slope, size_max))
    SIZE = np.stack(blocks, axis=0)
    return SIZE, combos_meta


def pnl_tensor_sized(SIZE, gap, cost_bps=COST_BPS_DEFAULT, short_borrow_bps=SHORT_BORROW_BPS_DEFAULT):
    """NET [ncombo,ndoc]. Cost scales with |size| - see module docstring for why
    this deliberately does NOT match backtest.py's flat per-trade charge."""
    gross = SIZE * gap[None, :]
    abs_size = np.abs(SIZE)
    cost = abs_size * (cost_bps / 1e4) + np.where(SIZE < 0, abs_size * (short_borrow_bps / 1e4), 0.0)
    net = gross - cost
    clipped = net < NET_FLOOR
    if clipped.any():
        net = np.clip(net, NET_FLOOR, None)
    return net, int(clipped.sum())


def total_return_from_net(NET):
    return np.expm1(np.log1p(NET).sum(axis=1))


def sharpe_and_trade_stats(NET, SIZE):
    traded = SIZE != 0
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


def dist_from_control(slope, size_max):
    return abs(slope - 0.0) + abs(size_max - 1.0)


def _control_index(combos_meta):
    return min(range(len(combos_meta)), key=lambda i: dist_from_control(*combos_meta[i]))


def permutation_test_pnl(SIZE, cost_bps, short_borrow_bps, gap, observed_best_total_return,
                          seed=RNG_SEED, perms=PERMUTATIONS):
    """Hold every combo's SIZE fixed, shuffle which document's overnight gap it's
    paired with; p = fraction of shuffles whose best achievable total return
    meets/exceeds the observed best. Same spirit as the weight-sweep's test."""
    abs_size = np.abs(SIZE)
    cost = abs_size * (cost_bps / 1e4) + np.where(SIZE < 0, abs_size * (short_borrow_bps / 1e4), 0.0)
    rng = np.random.default_rng(seed)
    ge = 0
    for _ in range(perms):
        gap_perm = rng.permutation(gap)
        net_perm = np.clip(SIZE * gap_perm[None, :] - cost, NET_FLOOR, None)
        tr = np.expm1(np.log1p(net_perm).sum(axis=1))
        ge += int(tr.max() >= observed_best_total_return)
    return round((ge + 1) / (perms + 1), 5)


def evaluate(docs, cost_bps, short_borrow_bps, hold_upper=DEFAULT_HOLD_UPPER, hold_lower=DEFAULT_HOLD_LOWER):
    gap = np.array([d["gap"] for d in docs])
    blended = blended_scores(docs)
    SIZE, meta = size_tensor(blended, hold_upper, hold_lower)
    NET, n_clipped = pnl_tensor_sized(SIZE, gap, cost_bps, short_borrow_bps)
    ncombo, ndoc = NET.shape
    n_trials = ncombo

    total_return = total_return_from_net(NET)
    sharpe, n_trades, avg_net_per_trade = sharpe_and_trade_stats(NET, SIZE)

    control_ci = _control_index(meta)

    best_val = total_return.max()
    tied = np.where(total_return == best_val)[0]
    best_ci = int(min(tied, key=lambda ci: dist_from_control(*meta[ci])))
    b_slope, b_size_max = meta[best_ci]

    best_traded = SIZE[best_ci] != 0
    dsr = deflated_sharpe_ratio(
        float(sharpe[best_ci]), int(n_trades[best_ci]), NET[best_ci][best_traded], n_trials, sharpe
    )

    global_best = {
        "total_return_pct": round(float(total_return[best_ci]) * 100, 2),
        "avg_net_per_trade_pct": round(float(avg_net_per_trade[best_ci]) * 100, 4),
        "sharpe_per_trade": round(float(sharpe[best_ci]), 3),
        "n_trades": int(n_trades[best_ci]),
        "slope": b_slope, "size_max": b_size_max, "size_min": SIZE_MIN,
        "n_tied": int(len(tied)),
        "deflated_sharpe": dsr,
    }

    order = np.argsort(-total_return)[:TOP_K]
    top_k = [{
        "slope": meta[ci][0], "size_max": meta[ci][1],
        "total_return_pct": round(float(total_return[ci]) * 100, 2),
        "sharpe_per_trade": round(float(sharpe[ci]), 3),
        "n_trades": int(n_trades[ci]),
    } for ci in order]

    # pooled LOOCV (leave-one-doc-out): total return is a log-space sum, so
    # excluding doc i is a vectorized subtraction, not a refit
    log_net = np.log1p(NET)
    total_log = log_net.sum(axis=1)

    held_net = np.zeros(ndoc)
    held_size = np.zeros(ndoc)
    for i in range(ndoc):
        loo_log = total_log - log_net[:, i]
        m = loo_log.max()
        tied_i = np.where(loo_log == m)[0]
        ci = int(min(tied_i, key=lambda ci: dist_from_control(*meta[ci])))
        held_net[i] = NET[ci, i]
        held_size[i] = SIZE[ci, i]

    loocv_total_return = float(np.expm1(np.log1p(held_net).sum()))
    loo_traded = held_size != 0
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
        "control_total_return_pct": round(float(total_return[control_ci]) * 100, 2),
        "control_avg_net_per_trade_pct": round(float(avg_net_per_trade[control_ci]) * 100, 4),
        "control_sharpe_per_trade": round(float(sharpe[control_ci]), 3),
        "control_n_trades": int(n_trades[control_ci]),
        "n": ndoc,
        "n_net_clipped_at_floor": n_clipped,
        "_best_ci": best_ci, "_control_ci": control_ci,
        "_SIZE": SIZE, "_NET": NET, "_meta": meta, "_gap": gap,
    }


def _strip_internal(result: dict) -> dict:
    return {k: v for k, v in result.items() if not k.startswith("_")}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cost-bps", type=float, default=COST_BPS_DEFAULT)
    ap.add_argument("--short-borrow-bps", type=float, default=SHORT_BORROW_BPS_DEFAULT)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    print("Loading pooled documents (overnight close-to-open gap, window_trading_days=1)...")
    docs = load_pooled_pnl()
    ncombo = len(SLOPES) * len(SIZE_MAXES)
    print(f"N={len(docs)} docs | sizing grid = {len(SLOPES)} slopes x {len(SIZE_MAXES)} size_max caps "
          f"= {ncombo} combos (weights/threshold fixed at deployed default)")

    result = evaluate(docs, args.cost_bps, args.short_borrow_bps)
    out_public = _strip_internal(result)

    gb = out_public["global_best"]
    dsr = gb["deflated_sharpe"]
    psr_txt = f"psr={dsr['psr']}" if dsr else "psr=n/a (too few trades)"
    print(f"\nglobal_best total_return={gb['total_return_pct']}% trades={gb['n_trades']} "
          f"sharpe={gb['sharpe_per_trade']} ({psr_txt}) slope={gb['slope']} size_max={gb['size_max']} "
          f"| LOOCV total_return={out_public['loocv_total_return_pct']}% trades={out_public['loocv_n_trades']} "
          f"sharpe={out_public['loocv_sharpe_per_trade']} "
          f"| control (fixed +-1, matches backtest.py) total_return={out_public['control_total_return_pct']}%")

    best_ci = result["_best_ci"]
    observed_best_total_return = float(np.expm1(np.log1p(result["_NET"][best_ci]).sum()))
    perm_p = permutation_test_pnl(
        result["_SIZE"], args.cost_bps, args.short_borrow_bps, result["_gap"], observed_best_total_return,
    )
    print(f"\nPermutation test (best combo's total return vs {PERMUTATIONS} gap-shuffles): p={perm_p}")

    backtest_check = validate_against_backtest(args.cost_bps, args.short_borrow_bps)
    control_via_sweep = out_public["control_total_return_pct"]
    control_via_backtest = backtest_check["compounded_total_return_pct"]
    match = abs(control_via_sweep - control_via_backtest) < 0.5
    print(f"\nSelf-check vs backtest.py: control combo (slope=0, size_max=1) total_return="
          f"{control_via_sweep}% vs backtest.py's reported={control_via_backtest}% -> "
          f"{'MATCH' if match else 'MISMATCH - investigate'}")
    if not match:
        print("WARNING: control combo does not reproduce backtest.py's fixed +-1 sizing. "
              "Do not trust any other combo's numbers until this is fixed.")

    out = {
        "n_documents": len(docs),
        "window_trading_days": 1,
        "exit_on_open": True,
        "objective": "total_return",
        "cost_bps": args.cost_bps,
        "short_borrow_bps": args.short_borrow_bps,
        "weights_held_fixed_at": list(DEFAULT_WEIGHTS),
        "hold_upper": DEFAULT_HOLD_UPPER, "hold_lower": DEFAULT_HOLD_LOWER,
        "sizing_grid": {"slopes": SLOPES, "size_maxes": SIZE_MAXES, "size_min": SIZE_MIN},
        "combos": ncombo,
        "n_trials_corrected_for_dsr": ncombo,
        **out_public,
        "significance": {
            "permutation_p_vs_gap_shuffles": perm_p,
            "note": "Sizes held fixed, overnight gap shuffled across documents 5000x; "
                    "p = fraction of shuffles whose best achievable total return >= the observed best.",
        },
        "vs_fixed_size_backtest": {
            "backtest_py_reported": {
                "n_trades": backtest_check["n_trades"],
                "total_return_pct": backtest_check["compounded_total_return_pct"],
                "avg_net_per_trade_pct": backtest_check["avg_net_per_trade_pct"],
                "t_statistic": backtest_check["t_statistic"],
                "max_drawdown_pct": backtest_check["max_drawdown_pct"],
            },
            "self_check_match": match,
        },
        "deployment_note": "Candidate output only - backtest.py's simulate() keeps fixed +-1 sizing "
                            "untouched pending review; must not be promoted unless it clears all four "
                            "gates (in-sample win, LOOCV, permutation, DSR), consistent with every other "
                            "lever tried in this project.",
    }
    summary_dir = OUTPUTS_DIR / "global" / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    path = summary_dir / "conviction_position_sizing_sweep.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
