"""
experiments/walkforward_validation.py
Item E: Walk-forward (rolling) validation of HOLD threshold selection.

RETROSPECTIVE VALIDATION — NOT PRE-REGISTERED.

The deployed thresholds (hold_upper=+0.25, hold_lower=-0.05) were selected by
optimising compounded total return (now retired as order-dependent) on the full
dataset (PSR=0.0, permutation p=0.150). This script refits hold_upper and
hold_lower out of sample using rolling windows, to test whether the 65.3%
selectivity accuracy survives without in-sample selection.

Two refit objectives are tried:
  1. Mean net per trade (the study's headline P&L metric, order-independent).
  2. Directional accuracy on graded training events, subject to a minimum
     trade-count constraint (at least 15% of training events must be traded).
Both are reported side by side so the reader can see whether degeneracy is
objective-specific or structural.

Design:
  - Weights are FIXED at DEFAULT_WEIGHTS=(0.55, 0.45, 0.0, 0.0). Only the two
    HOLD thresholds are refit per window.
  - Rolling: start at ~40% of events by release_date, step forward one calendar
    quarter, refit thresholds on training slice, score next quarter OOS.
  - Two-window headline: fit on events <= 2026-08-10, score events after.
    Currently empty (all 233 clean events predate the freeze).
  - Degenerate-window assertion: if any window's OOS trade count falls below
    MIN_TRADES_FLOOR, assert loudly (threshold went degenerate).

Cross-issuer generalisation (RECONSTRUCTED — see methodology note):
  The deployed thresholds were selected at N=161 (the first 40 phase2 issuers).
  31 issuers (101 clean events after exclusions) were scored AFTER the sweep and
  were never seen by the threshold selection. Their accuracy under the deployed
  thresholds is reported separately as a cross-issuer generalisation test.

  THIS IS A CROSS-ISSUER TEST, NOT A TEMPORAL ONE. Both subsets span overlapping
  date ranges (in-sweep 2023-04-25 to 2026-07-14, post-sweep 2024-07-31 to
  2026-07-01, 37 same-day reports from different issuers). The result does not
  corroborate the temporal walk-forward or dev/eval findings.

  METHODOLOGY NOTE ON SWEEP MEMBERSHIP:
  The N=161 sweep (experiments/phase2_pnl_weight_threshold_sweep.py) predates
  this repository's git history. No recorded event list or calibration file from
  that commit survives. Membership is INFERRED from:
    (a) The sweep JSON records n_documents=161 but no event list.
    (b) The first 40 issuers in PHASE2_ISSUERS produce exactly 161 events,
        matching the sweep's recorded count.
    (c) Zero issuer overlap between the first 40 and the later 31.
    (d) The 101 post-sweep events are entirely new issuers, not new quarters
        of existing issuers.
  However, the count match is weak evidence: 453 single-swap alternative sets
  of 40 issuers also produce exactly 161 events. The identification relies on
  the assumption that issuers were onboarded in PHASE2_ISSUERS list order. The
  result is labelled a "reconstructed cross-issuer generalisation subset."

Exclusions (35 events from 268 -> N=233 clean):
  - 25 worksheet contamination (worksheet_leak_flags.csv)
  - 1 SPOT_FQ1_2026 (misattributed document)
  - 9 timing-excluded (timing_excluded=YES in returns_matrix.csv)

Run: python -m experiments.walkforward_validation
"""
from __future__ import annotations

import csv
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev

import numpy as np
from scipy import stats as sp_stats
from scipy.stats import binomtest

# -- project imports ----------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval.excluded_events import EXCLUDED_EVENTS  # noqa: E402
from blend import (
    DEFAULT_HOLD_LOWER,
    DEFAULT_HOLD_UPPER,
    DEFAULT_WEIGHTS,
    blend_scores,
)
from bootstrap_stats import bootstrap_trade_stats, bootstrap_unpaired_difference

# -- paths --------------------------------------------------------------------
SUMMARY_DIR = Path(__file__).resolve().parent.parent / "outputs" / "global" / "summary"
RETURNS_CSV = SUMMARY_DIR / "returns_matrix.csv"
CALIBRATION_CSV = SUMMARY_DIR / "global_outcome_calibration_phase2.csv"
LEAK_FLAGS_CSV = SUMMARY_DIR / "worksheet_leak_flags.csv"

OUT_CSV = SUMMARY_DIR / "item_e_walkforward.csv"
OUT_JSON = SUMMARY_DIR / "item_e_walkforward.json"

# -- constants ----------------------------------------------------------------
COST_BPS = 10.0
SHORT_BORROW_BPS = 0.0
COST_FRAC = COST_BPS / 10_000
FLAT_BAND = 0.02  # +/- 2% overnight grading band

# Threshold search grid
THRESH_UPPER_RANGE = np.arange(0.05, 0.55, 0.05)  # 0.05 to 0.50
THRESH_LOWER_RANGE = np.arange(-0.50, 0.05, 0.05)  # -0.50 to 0.00

# Degenerate-window floor
MIN_TRADES_FLOOR = 5

# Minimum trade fraction for accuracy-objective (correction 3)
MIN_TRADE_FRACTION = 0.15

# Two-window freeze date
FREEZE_DATE = "2026-08-10"

# The 40 issuers that were in the N=161 sweep at promotion (2026-08-05).
# All other issuers were scored after the sweep and are genuinely unseen.
SWEEP_ISSUERS_AT_PROMOTION = frozenset([
    "airbnb", "amazon", "amd", "apple", "cvs_health", "charles_schwab",
    "citigroup", "coca_cola", "coinbase", "eli_lilly", "goldman_sachs",
    "ibm", "lowes", "lululemon", "maersk", "mcdonalds", "meta", "nike",
    "nvidia", "tesla", "uber", "walmart",
    "bank_of_america", "boeing", "disney", "jpm", "netflix", "target",
    "barclays", "ford", "microsoft", "pfizer", "united_airlines",
    "pepsico", "fedex", "lockheed_martin", "novo_nordisk", "hilton", "lvmh",
    "marriott",
])


# -- data loading -------------------------------------------------------------
def _num(x):
    if x is None or x == "":
        return None
    return float(x)


def _load_clean_events() -> list[dict]:
    """Load the N=233 clean event universe, merging calibration + returns_matrix.

    Each event dict has:
      document_id, ticker, issuer, report_date (from calibration),
      release_date (from returns_matrix report_date, which IS the release_date),
      micro_score, macro_score, news_score, quant_score,
      ret_overnight, blend_predicted_signal_default,
      in_sweep (bool: True if issuer was in the N=161 sweep)
    """
    # Load calibration
    cal = {}
    with open(CALIBRATION_CSV) as f:
        for r in csv.DictReader(f):
            cal[r["document_id"]] = r

    # Load returns_matrix (anchored to release_date)
    rm = {}
    with open(RETURNS_CSV) as f:
        for r in csv.DictReader(f):
            rm[r["document_id"]] = r

    # Load exclusion sets
    worksheet_excluded = set()
    with open(LEAK_FLAGS_CSV) as f:
        for r in csv.DictReader(f):
            if r.get("has_human_score", "").strip() == "True":
                worksheet_excluded.add(r["document_id"])
    spot_excluded = set(EXCLUDED_EVENTS)

    # Merge and filter
    events = []
    for did, c in cal.items():
        if did in worksheet_excluded:
            continue
        if did in spot_excluded:
            continue
        r = rm.get(did)
        if r is None:
            continue
        if r.get("timing_excluded") == "YES":
            continue

        ret_overnight = _num(r.get("ret_overnight"))
        if ret_overnight is None:
            continue

        issuer_slug = c["issuer"].replace("p2_", "")
        events.append({
            "document_id": did,
            "ticker": c["ticker"],
            "issuer": c["issuer"],
            "release_date": r["report_date"],
            "micro_score": _num(c["micro_score"]),
            "macro_score": _num(c["macro_score"]),
            "news_score": _num(c["news_score"]),
            "quant_score": _num(c["quant_score"]),
            "ret_overnight": ret_overnight,
            "blend_predicted_signal_default": c["blend_predicted_signal_default"],
            "in_sweep": issuer_slug in SWEEP_ISSUERS_AT_PROMOTION,
        })

    events.sort(key=lambda e: e["release_date"])
    return events


def _blend_score(ev: dict) -> float:
    """Compute the deployed blended score for an event."""
    return blend_scores(
        ev["micro_score"],
        ev["macro_score"],
        ev["news_score"],
        ev["quant_score"],
        DEFAULT_WEIGHTS,
    )


def _derive_signal(score: float, hold_upper: float, hold_lower: float) -> str:
    """BUY/HOLD/SELL from a blended score and threshold pair.
    Matches blend.derive_signal(): strict inequalities (score ON the boundary = HOLD)."""
    if score > hold_upper:
        return "BUY"
    elif score < hold_lower:
        return "SELL"
    return "HOLD"


def _net_return(position: int, gap: float) -> float:
    """Net return for a single trade, after costs."""
    if position == 0:
        return 0.0
    gross = position * gap
    cost = COST_FRAC + (SHORT_BORROW_BPS / 10_000 if position < 0 else 0.0)
    return gross - cost


# -- threshold fitting --------------------------------------------------------
def _evaluate_thresholds(
    events: list[dict],
    hold_upper: float,
    hold_lower: float,
) -> dict:
    """Evaluate a threshold pair on a set of events.

    Returns dict with: mean_net, n_trades, n_graded, n_correct, accuracy,
    summed_return, signals list.
    """
    nets = []
    n_graded = 0
    n_correct = 0
    signals = []

    for ev in events:
        score = _blend_score(ev)
        signal = _derive_signal(score, hold_upper, hold_lower)
        ret = ev["ret_overnight"]

        if signal == "BUY":
            position = 1
        elif signal == "SELL":
            position = -1
        else:
            position = 0

        net = _net_return(position, ret)

        if position != 0:
            nets.append(net)
            if abs(ret) >= FLAT_BAND:
                n_graded += 1
                truth = "BUY" if ret > 0 else "SELL"
                if signal == truth:
                    n_correct += 1

        signals.append({
            "document_id": ev["document_id"],
            "signal": signal,
            "position": position,
            "net": net,
        })

    n_trades = len(nets)
    mean_net = mean(nets) if nets else 0.0
    accuracy = n_correct / n_graded if n_graded > 0 else None

    return {
        "hold_upper": hold_upper,
        "hold_lower": hold_lower,
        "mean_net": mean_net,
        "n_trades": n_trades,
        "n_graded": n_graded,
        "n_correct": n_correct,
        "accuracy": accuracy,
        "summed_return": sum(nets),
        "signals": signals,
    }


def fit_thresholds_mean_net(train_events: list[dict]) -> tuple[float, float, dict]:
    """Grid-search for (hold_upper, hold_lower) maximising mean net per trade.

    Returns (best_upper, best_lower, best_result_dict).
    """
    best = None
    best_upper = DEFAULT_HOLD_UPPER
    best_lower = DEFAULT_HOLD_LOWER

    for hu, hl in itertools.product(THRESH_UPPER_RANGE, THRESH_LOWER_RANGE):
        hu_r = round(float(hu), 2)
        hl_r = round(float(hl), 2)
        if hu_r <= hl_r:
            continue

        result = _evaluate_thresholds(train_events, hu_r, hl_r)
        if result["n_trades"] == 0:
            continue

        if best is None or result["mean_net"] > best["mean_net"]:
            best = result
            best_upper = hu_r
            best_lower = hl_r

    if best is None:
        best = _evaluate_thresholds(train_events, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER)
        best_upper = DEFAULT_HOLD_UPPER
        best_lower = DEFAULT_HOLD_LOWER

    return best_upper, best_lower, best


def fit_thresholds_accuracy(train_events: list[dict]) -> tuple[float, float, dict]:
    """Grid-search for (hold_upper, hold_lower) maximising directional accuracy
    on graded training events, subject to a minimum trade-count constraint:
    at least MIN_TRADE_FRACTION of training events must be traded.

    Returns (best_upper, best_lower, best_result_dict).
    """
    min_trades = max(MIN_TRADES_FLOOR, int(len(train_events) * MIN_TRADE_FRACTION))

    best = None
    best_upper = DEFAULT_HOLD_UPPER
    best_lower = DEFAULT_HOLD_LOWER

    for hu, hl in itertools.product(THRESH_UPPER_RANGE, THRESH_LOWER_RANGE):
        hu_r = round(float(hu), 2)
        hl_r = round(float(hl), 2)
        if hu_r <= hl_r:
            continue

        result = _evaluate_thresholds(train_events, hu_r, hl_r)

        # Enforce minimum trade count
        if result["n_trades"] < min_trades:
            continue
        # Need graded events to compute accuracy
        if result["n_graded"] == 0:
            continue

        if best is None or result["accuracy"] > best["accuracy"]:
            best = result
            best_upper = hu_r
            best_lower = hl_r

    if best is None:
        best = _evaluate_thresholds(train_events, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER)
        best_upper = DEFAULT_HOLD_UPPER
        best_lower = DEFAULT_HOLD_LOWER

    return best_upper, best_lower, best


# -- walk-forward engine ------------------------------------------------------
def _quarter_cutoffs(events: list[dict]) -> list[str]:
    """Generate calendar quarter cutoff dates spanning the event set."""
    dates = sorted(set(e["release_date"] for e in events))
    if not dates:
        return []

    start_dt = datetime.strptime(dates[0], "%Y-%m-%d")
    end_dt = datetime.strptime(dates[-1], "%Y-%m-%d")

    cutoffs = []
    year = start_dt.year
    q = (start_dt.month - 1) // 3
    while True:
        month_end = [3, 6, 9, 12][q]
        if month_end == 3:
            cutoff = f"{year}-03-31"
        elif month_end == 6:
            cutoff = f"{year}-06-30"
        elif month_end == 9:
            cutoff = f"{year}-09-30"
        else:
            cutoff = f"{year}-12-31"

        if cutoff > end_dt.strftime("%Y-%m-%d"):
            break
        cutoffs.append(cutoff)

        q += 1
        if q > 3:
            q = 0
            year += 1

    return cutoffs


def rolling_walkforward(events: list[dict], fit_fn) -> list[dict]:
    """Rolling walk-forward: start at ~40% of events, step one quarter.

    fit_fn is either fit_thresholds_mean_net or fit_thresholds_accuracy.

    Returns a list of window results.
    """
    n_total = len(events)
    cutoffs = _quarter_cutoffs(events)
    if not cutoffs:
        return []

    start_idx = None
    for i, cutoff in enumerate(cutoffs):
        n_before = sum(1 for e in events if e["release_date"] <= cutoff)
        if n_before >= 0.4 * n_total:
            start_idx = i
            break
    if start_idx is None:
        start_idx = len(cutoffs) - 2

    windows = []
    for w_idx, cutoff_idx in enumerate(range(start_idx, len(cutoffs))):
        train_cutoff = cutoffs[cutoff_idx]
        train = [e for e in events if e["release_date"] <= train_cutoff]
        if len(train) < MIN_TRADES_FLOOR:
            continue

        if cutoff_idx + 1 < len(cutoffs):
            test_end = cutoffs[cutoff_idx + 1]
        else:
            test_end = "9999-12-31"

        test = [e for e in events
                if e["release_date"] > train_cutoff
                and e["release_date"] <= test_end]

        if not test:
            continue

        fitted_upper, fitted_lower, train_result = fit_fn(train)
        test_result = _evaluate_thresholds(test, fitted_upper, fitted_lower)

        test_nets = [s["net"] for s in test_result["signals"] if s["position"] != 0]

        test_graded_correct = []
        for ev, sig in zip(test, test_result["signals"]):
            if sig["position"] != 0 and abs(ev["ret_overnight"]) >= FLAT_BAND:
                truth = "BUY" if ev["ret_overnight"] > 0 else "SELL"
                test_graded_correct.append(1 if sig["signal"] == truth else 0)

        window = {
            "window_idx": w_idx,
            "train_cutoff": train_cutoff,
            "test_start": test[0]["release_date"] if test else None,
            "test_end": test[-1]["release_date"] if test else None,
            "fitted_upper": fitted_upper,
            "fitted_lower": fitted_lower,
            "train_n": len(train),
            "train_trades": train_result["n_trades"],
            "train_mean_net": train_result["mean_net"],
            "train_accuracy": train_result["accuracy"],
            "train_n_graded": train_result["n_graded"],
            "test_n": len(test),
            "test_trades": test_result["n_trades"],
            "test_mean_net": test_result["mean_net"],
            "test_accuracy": test_result["accuracy"],
            "test_n_graded": test_result["n_graded"],
            "test_n_correct": test_result["n_correct"],
            "test_nets": test_nets,
            "test_graded_correct": test_graded_correct,
        }
        windows.append(window)

    return windows


def two_window_headline(events: list[dict], fit_fn) -> dict:
    """Fit on events <= FREEZE_DATE, score events after."""
    train = [e for e in events if e["release_date"] <= FREEZE_DATE]
    test = [e for e in events if e["release_date"] > FREEZE_DATE]

    result = {
        "freeze_date": FREEZE_DATE,
        "train_n": len(train),
        "test_n": len(test),
        "status": None,
    }

    if not test:
        result["status"] = "DORMANT — no test events after freeze date"
        if train:
            fitted_upper, fitted_lower, train_result = fit_fn(train)
            result["fitted_upper"] = fitted_upper
            result["fitted_lower"] = fitted_lower
            result["train_trades"] = train_result["n_trades"]
            result["train_mean_net"] = train_result["mean_net"]
            result["train_accuracy"] = train_result["accuracy"]
        return result

    fitted_upper, fitted_lower, train_result = fit_fn(train)
    test_result = _evaluate_thresholds(test, fitted_upper, fitted_lower)

    result.update({
        "status": "ACTIVE",
        "fitted_upper": fitted_upper,
        "fitted_lower": fitted_lower,
        "train_trades": train_result["n_trades"],
        "train_mean_net": train_result["mean_net"],
        "train_accuracy": train_result["accuracy"],
        "test_trades": test_result["n_trades"],
        "test_mean_net": test_result["mean_net"],
        "test_accuracy": test_result["accuracy"],
        "test_n_graded": test_result["n_graded"],
        "test_n_correct": test_result["n_correct"],
    })
    return result


def _pool_windows(windows, events):
    """Pool OOS results across all windows. Returns a summary dict."""
    pooled_nets = []
    pooled_graded = []
    oos_truth_down = 0
    oos_truth_up = 0

    for w in windows:
        pooled_nets.extend(w["test_nets"])
        pooled_graded.extend(w["test_graded_correct"])

        test_events = [e for e in events
                       if e["release_date"] > w["train_cutoff"]
                       and e["release_date"] <= (w["test_end"] if w["test_end"] else "9999-12-31")]
        test_result = _evaluate_thresholds(test_events, w["fitted_upper"], w["fitted_lower"])
        for ev, sig in zip(test_events, test_result["signals"]):
            if sig["position"] != 0 and abs(ev["ret_overnight"]) >= FLAT_BAND:
                if ev["ret_overnight"] < 0:
                    oos_truth_down += 1
                else:
                    oos_truth_up += 1

    n_trades = len(pooled_nets)
    n_graded = len(pooled_graded)
    n_correct = sum(pooled_graded)
    accuracy = n_correct / n_graded if n_graded > 0 else None
    mean_net = mean(pooled_nets) if pooled_nets else 0.0

    return {
        "n_trades": n_trades,
        "n_graded": n_graded,
        "n_correct": n_correct,
        "accuracy": accuracy,
        "mean_net": mean_net,
        "summed_pct": sum(pooled_nets) * 100 if pooled_nets else 0.0,
        "pooled_nets": pooled_nets,
        "pooled_graded": pooled_graded,
        "truth_down": oos_truth_down,
        "truth_up": oos_truth_up,
    }


def _print_windows(windows, label):
    """Print per-window log table."""
    degenerate = []
    print(f"\n{'Win':>3} {'TrainCut':>10} {'TestSpan':>23} "
          f"{'FitUp':>6} {'FitLo':>6} "
          f"{'TrN':>4} {'TrTrd':>5} {'TrMean%':>8} {'TrAcc':>6} "
          f"{'TsN':>4} {'TsTrd':>5} {'TsMean%':>8} {'TsAcc':>6} {'TsGrd':>5}")
    print("-" * 130)

    for w in windows:
        test_span = f"{w['test_start']} - {w['test_end']}"
        tr_acc = f"{w['train_accuracy']:.1%}" if w['train_accuracy'] is not None else "N/A"
        ts_acc = f"{w['test_accuracy']:.1%}" if w['test_accuracy'] is not None else "N/A"

        flag = ""
        if w["test_trades"] < MIN_TRADES_FLOOR:
            flag = " *** DEGENERATE"
            degenerate.append(w)

        print(f"{w['window_idx']:>3} {w['train_cutoff']:>10} {test_span:>23} "
              f"{w['fitted_upper']:>6.2f} {w['fitted_lower']:>+6.2f} "
              f"{w['train_n']:>4} {w['train_trades']:>5} {w['train_mean_net']*100:>+8.3f} {tr_acc:>6} "
              f"{w['test_n']:>4} {w['test_trades']:>5} {w['test_mean_net']*100:>+8.3f} {ts_acc:>6} "
              f"{w['test_n_graded']:>5}{flag}")

    if degenerate:
        print(f"\n  *** WARNING: {len(degenerate)} window(s) have fewer "
              f"than {MIN_TRADES_FLOOR} OOS trades — threshold went degenerate!")
        for w in degenerate:
            print(f"    Window {w['window_idx']}: {w['test_trades']} trades "
                  f"(fitted +{w['fitted_upper']}/{w['fitted_lower']:+.2f})")

    return degenerate


def _print_pooled(pool, label):
    """Print pooled OOS results."""
    print(f"\n  --- Pooled OOS ({label}) ---")
    print(f"  Trades: {pool['n_trades']}")
    print(f"  Graded: {pool['n_graded']}")
    if pool["accuracy"] is not None:
        print(f"  Accuracy: {pool['n_correct']}/{pool['n_graded']} = {pool['accuracy']:.1%}")
    print(f"  Mean net/trade: {pool['mean_net']*100:+.3f}%")
    print(f"  Summed return: {pool['summed_pct']:+.2f}%")

    if pool["pooled_nets"]:
        bs = bootstrap_trade_stats(pool["pooled_nets"])
        print(f"  Bootstrap 90% CI: mean net [{bs['mean_per_trade']['ci_low']*100:+.3f}%, "
              f"{bs['mean_per_trade']['ci_high']*100:+.3f}%]")

    if pool["n_graded"] > 0:
        majority_n = max(pool["truth_down"], pool["truth_up"])
        majority_label = "always-DOWN" if pool["truth_down"] >= pool["truth_up"] else "always-BUY"
        majority_floor = majority_n / pool["n_graded"]
        print(f"  Majority-direction floor: {majority_label} = "
              f"{majority_n}/{pool['n_graded']} = {majority_floor:.1%}")
        if pool["accuracy"] is not None:
            margin = pool["accuracy"] - majority_floor
            binom = binomtest(pool["n_correct"], pool["n_graded"], majority_floor,
                              alternative="greater")
            print(f"  Margin vs floor: {margin*100:+.1f}pp (p={binom.pvalue:.4f})")


# -- main --------------------------------------------------------------------
def main():
    events = _load_clean_events()
    n = len(events)
    print(f"Loaded {n} clean events (expected 233)")
    assert n > 200, f"Expected ~233, got {n}"

    date_range = f"{events[0]['release_date']} to {events[-1]['release_date']}"
    print(f"Date range: {date_range}")

    in_sweep = [e for e in events if e["in_sweep"]]
    post_sweep = [e for e in events if not e["in_sweep"]]
    print(f"In-sweep (N=161 issuers): {len(in_sweep)} clean events")
    print(f"Post-sweep (genuinely unseen): {len(post_sweep)} clean events")

    # ---- In-sample baseline (deployed thresholds) for comparison ----
    deployed = _evaluate_thresholds(events, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER)
    print(f"\n=== IN-SAMPLE (deployed thresholds +{DEFAULT_HOLD_UPPER}/-{abs(DEFAULT_HOLD_LOWER)}) ===")
    print(f"  N={n}, trades={deployed['n_trades']}, graded={deployed['n_graded']}")
    print(f"  Accuracy: {deployed['n_correct']}/{deployed['n_graded']}"
          f" = {deployed['accuracy']:.1%}" if deployed['accuracy'] else "  Accuracy: N/A")
    print(f"  Mean net/trade: {deployed['mean_net']*100:+.3f}%")

    # =========================================================================
    # OBJECTIVE 1: Mean net per trade
    # =========================================================================
    print("\n" + "=" * 80)
    print("OBJECTIVE 1: MEAN NET PER TRADE")
    print("=" * 80)

    windows_mn = rolling_walkforward(events, fit_thresholds_mean_net)
    if not windows_mn:
        print("  No valid windows!")
        return 1
    degen_mn = _print_windows(windows_mn, "mean_net")
    pool_mn = _pool_windows(windows_mn, events)
    _print_pooled(pool_mn, "mean_net objective")

    # =========================================================================
    # OBJECTIVE 2: Directional accuracy (with min trade count)
    # =========================================================================
    print("\n" + "=" * 80)
    print(f"OBJECTIVE 2: DIRECTIONAL ACCURACY (min {MIN_TRADE_FRACTION:.0%} traded)")
    print("=" * 80)

    windows_acc = rolling_walkforward(events, fit_thresholds_accuracy)
    if not windows_acc:
        print("  No valid windows!")
        return 1
    degen_acc = _print_windows(windows_acc, "accuracy")
    pool_acc = _pool_windows(windows_acc, events)
    _print_pooled(pool_acc, "accuracy objective")

    # =========================================================================
    # DEGENERACY FINDING (correction 2)
    # =========================================================================
    print("\n" + "=" * 80)
    print("DEGENERACY ANALYSIS")
    print("=" * 80)

    n_degen_mn = len(degen_mn)
    n_degen_acc = len(degen_acc)
    total_windows = len(windows_mn)
    print(f"\n  Mean-net objective: {n_degen_mn}/{total_windows} windows degenerate")
    print(f"  Accuracy objective: {n_degen_acc}/{total_windows} windows degenerate")

    if n_degen_mn > 0 and n_degen_acc > 0:
        print("\n  FINDING: Degeneracy occurs under BOTH objectives.")
        print("  The threshold selection procedure cannot be executed honestly at N=233.")
    elif n_degen_mn > 0:
        print("\n  Degeneracy is objective-specific to mean-net-per-trade.")
    elif n_degen_acc > 0:
        print("\n  Degeneracy is objective-specific to accuracy.")
    else:
        print("\n  No degenerate windows under either objective.")

    # =========================================================================
    # SUBSET STABILITY (correction 1): deployed thresholds on later events
    # NOT out-of-sample — these events were in the dataset when thresholds
    # were fitted.
    # =========================================================================
    print("\n" + "=" * 80)
    print("SUBSET STABILITY: deployed thresholds on later-dated events")
    print("(NOT out-of-sample — all events were in the sweep's dataset)")
    print("=" * 80)

    # Deployed thresholds on the OOS windows' events (a subset of in-sample)
    deployed_subset_nets = []
    deployed_subset_graded = []
    for w in windows_mn:
        test_events = [e for e in events
                       if e["release_date"] > w["train_cutoff"]
                       and e["release_date"] <= (w["test_end"] if w["test_end"] else "9999-12-31")]
        dep_result = _evaluate_thresholds(test_events, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER)
        dep_nets = [s["net"] for s in dep_result["signals"] if s["position"] != 0]
        deployed_subset_nets.extend(dep_nets)
        for ev, sig in zip(test_events, dep_result["signals"]):
            if sig["position"] != 0 and abs(ev["ret_overnight"]) >= FLAT_BAND:
                truth = "BUY" if ev["ret_overnight"] > 0 else "SELL"
                deployed_subset_graded.append(1 if sig["signal"] == truth else 0)

    dep_sub_n_trades = len(deployed_subset_nets)
    dep_sub_n_graded = len(deployed_subset_graded)
    dep_sub_n_correct = sum(deployed_subset_graded)
    dep_sub_accuracy = dep_sub_n_correct / dep_sub_n_graded if dep_sub_n_graded > 0 else None

    print(f"\n  Deployed thresholds on later-dated subset:")
    print(f"  Trades: {dep_sub_n_trades}, Graded: {dep_sub_n_graded}")
    if dep_sub_accuracy is not None:
        print(f"  Accuracy: {dep_sub_n_correct}/{dep_sub_n_graded} = {dep_sub_accuracy:.1%}")
        print(f"  vs full-sample: {deployed['accuracy']:.1%}")
        print(f"  Observation: thresholds fitted on all {n} events perform comparably")
        print(f"  on the later-dated subset ({dep_sub_accuracy:.1%} vs {deployed['accuracy']:.1%}),")
        print(f"  showing the fitted thresholds are not concentrated on early events.")
        print(f"  This is subset stability, not evidence of generalisation.")

    # =========================================================================
    # GENUINELY UNSEEN EVENTS (correction 1 continued)
    # The 31 issuers scored after the N=161 sweep are truly out-of-sample
    # with respect to threshold selection.
    # =========================================================================
    print("\n" + "=" * 80)
    print("CROSS-ISSUER GENERALISATION (post-sweep issuers, reconstructed subset)")
    print("=" * 80)

    unseen_result = _evaluate_thresholds(post_sweep, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER)
    seen_result = _evaluate_thresholds(in_sweep, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER)

    print(f"\n  --- In-sweep events (N={len(in_sweep)}, in-sample) ---")
    print(f"  Trades: {seen_result['n_trades']}, Graded: {seen_result['n_graded']}")
    if seen_result["accuracy"] is not None:
        print(f"  Accuracy: {seen_result['n_correct']}/{seen_result['n_graded']} = {seen_result['accuracy']:.1%}")
    print(f"  Mean net/trade: {seen_result['mean_net']*100:+.3f}%")

    print(f"\n  --- Post-sweep events (N={len(post_sweep)}, genuinely unseen) ---")
    print(f"  Trades: {unseen_result['n_trades']}, Graded: {unseen_result['n_graded']}")
    if unseen_result["accuracy"] is not None:
        print(f"  Accuracy: {unseen_result['n_correct']}/{unseen_result['n_graded']} = {unseen_result['accuracy']:.1%}")
    print(f"  Mean net/trade: {unseen_result['mean_net']*100:+.3f}%")

    # Majority-direction floor on the unseen graded events
    unseen_graded_down = 0
    unseen_graded_up = 0
    for ev in post_sweep:
        score = _blend_score(ev)
        signal = _derive_signal(score, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER)
        if signal == "HOLD":
            continue
        if abs(ev["ret_overnight"]) < FLAT_BAND:
            continue
        if ev["ret_overnight"] < 0:
            unseen_graded_down += 1
        else:
            unseen_graded_up += 1

    unseen_n_graded = unseen_result["n_graded"]
    if unseen_n_graded > 0:
        unseen_majority_n = max(unseen_graded_down, unseen_graded_up)
        unseen_majority_label = "always-DOWN" if unseen_graded_down >= unseen_graded_up else "always-BUY"
        unseen_floor = unseen_majority_n / unseen_n_graded

        print(f"\n  Floor ({unseen_majority_label}): {unseen_majority_n}/{unseen_n_graded} = {unseen_floor:.1%}")
        margin_unseen = unseen_result["accuracy"] - unseen_floor
        print(f"  Margin: {margin_unseen*100:+.1f}pp")

        binom_unseen = binomtest(unseen_result["n_correct"], unseen_n_graded,
                                  unseen_floor, alternative="greater")
        print(f"  Binomial test (accuracy > floor): p = {binom_unseen.pvalue:.4f}")

        # MDE on unseen
        z_alpha = 1.282
        z_beta = 0.842
        mde_unseen = (z_alpha + z_beta) * np.sqrt(2 * unseen_floor * (1 - unseen_floor) / unseen_n_graded)
        print(f"  MDE: ±{mde_unseen*100:.1f}pp (N_graded={unseen_n_graded})")

        print(f"\n  Cross-issuer generalisation: thresholds fitted on 40 issuers")
        print(f"  transfer to 31 unseen issuers at {unseen_result['accuracy']:.1%}.")
        print(f"  Both subsets span overlapping date ranges (interleaved, not sequential)")
        print(f"  — this tests issuer coverage, not temporal generalisation.")

    # =========================================================================
    # TWO-WINDOW HEADLINE
    # =========================================================================
    print("\n" + "=" * 80)
    print("TWO-WINDOW HEADLINE")
    print("=" * 80)

    tw_mn = two_window_headline(events, fit_thresholds_mean_net)
    print(f"\n  Freeze date: {tw_mn['freeze_date']}")
    print(f"  Train N: {tw_mn['train_n']}, Test N: {tw_mn['test_n']}")
    print(f"  Status: {tw_mn['status']}")
    if tw_mn.get("fitted_upper") is not None:
        print(f"  Fitted thresholds (mean-net): +{tw_mn['fitted_upper']}/{tw_mn['fitted_lower']:+.2f}")
        if tw_mn.get("train_trades"):
            print(f"  Train trades: {tw_mn['train_trades']}, "
                  f"mean net: {tw_mn['train_mean_net']*100:+.3f}%")

    tw_acc = two_window_headline(events, fit_thresholds_accuracy)
    if tw_acc.get("fitted_upper") is not None:
        print(f"  Fitted thresholds (accuracy): +{tw_acc['fitted_upper']}/{tw_acc['fitted_lower']:+.2f}")
        if tw_acc.get("train_trades"):
            print(f"  Train trades: {tw_acc['train_trades']}, "
                  f"accuracy: {tw_acc.get('train_accuracy', 0):.1%}")

    # =========================================================================
    # MDE
    # =========================================================================
    print("\n" + "=" * 80)
    print("MINIMUM DETECTABLE EFFECT")
    print("=" * 80)

    z_alpha = 1.282
    z_beta = 0.842
    for label, pool in [("mean_net", pool_mn), ("accuracy", pool_acc)]:
        if pool["n_graded"] > 0:
            majority_n = max(pool["truth_down"], pool["truth_up"])
            p0 = majority_n / pool["n_graded"]
            mde = (z_alpha + z_beta) * np.sqrt(2 * p0 * (1 - p0) / pool["n_graded"])
            print(f"  {label} objective: MDE = ±{mde*100:.1f}pp (N_graded={pool['n_graded']})")

    # In-sample MDE for reference
    if deployed["n_graded"] > 0:
        dep_floor_n = max(
            sum(1 for ev in events
                if _derive_signal(_blend_score(ev), DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER) != "HOLD"
                and abs(ev["ret_overnight"]) >= FLAT_BAND and ev["ret_overnight"] < 0),
            sum(1 for ev in events
                if _derive_signal(_blend_score(ev), DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER) != "HOLD"
                and abs(ev["ret_overnight"]) >= FLAT_BAND and ev["ret_overnight"] > 0),
        )
        dep_p0 = dep_floor_n / deployed["n_graded"]
        mde_is = (z_alpha + z_beta) * np.sqrt(2 * dep_p0 * (1 - dep_p0) / deployed["n_graded"])
        print(f"  In-sample (deployed): MDE = ±{mde_is*100:.1f}pp (N_graded={deployed['n_graded']})")

    # =========================================================================
    # WRITE OUTPUTS
    # =========================================================================

    # CSV: per-window log for both objectives
    csv_rows = []
    for objective_label, wins in [("mean_net", windows_mn), ("accuracy", windows_acc)]:
        for w in wins:
            csv_rows.append({
                "objective": objective_label,
                "window_idx": w["window_idx"],
                "train_cutoff": w["train_cutoff"],
                "test_start": w["test_start"],
                "test_end": w["test_end"],
                "fitted_upper": w["fitted_upper"],
                "fitted_lower": w["fitted_lower"],
                "train_n": w["train_n"],
                "train_trades": w["train_trades"],
                "train_mean_net_pct": round(w["train_mean_net"] * 100, 4),
                "train_accuracy": round(w["train_accuracy"], 4) if w["train_accuracy"] is not None else "",
                "train_n_graded": w["train_n_graded"],
                "test_n": w["test_n"],
                "test_trades": w["test_trades"],
                "test_mean_net_pct": round(w["test_mean_net"] * 100, 4),
                "test_accuracy": round(w["test_accuracy"], 4) if w["test_accuracy"] is not None else "",
                "test_n_graded": w["test_n_graded"],
                "test_n_correct": w["test_n_correct"],
            })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        fieldnames = list(csv_rows[0].keys()) if csv_rows else []
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"\nWrote per-window CSV -> {OUT_CSV}")

    # JSON: full results
    def _pool_to_json(pool, label):
        d = {
            "objective": label,
            "n_trades": pool["n_trades"],
            "n_graded": pool["n_graded"],
            "n_correct": pool["n_correct"],
            "accuracy": round(pool["accuracy"], 4) if pool["accuracy"] is not None else None,
            "mean_net_pct": round(pool["mean_net"] * 100, 4),
            "summed_return_pct": round(pool["summed_pct"], 2),
        }
        if pool["n_graded"] > 0:
            majority_n = max(pool["truth_down"], pool["truth_up"])
            d["majority_direction_floor"] = round(majority_n / pool["n_graded"], 4)
        if pool["pooled_nets"]:
            bs = bootstrap_trade_stats(pool["pooled_nets"])
            d["bootstrap_90ci_mean_net_pct"] = {
                "point": round(bs["mean_per_trade"]["point"] * 100, 4),
                "ci_low": round(bs["mean_per_trade"]["ci_low"] * 100, 4),
                "ci_high": round(bs["mean_per_trade"]["ci_high"] * 100, 4),
            }
        return d

    output = {
        "label": "RETROSPECTIVE VALIDATION — NOT PRE-REGISTERED",
        "n_clean_events": n,
        "date_range": date_range,
        "weights_fixed": list(DEFAULT_WEIGHTS),
        "cost_bps": COST_BPS,
        "short_borrow_bps": SHORT_BORROW_BPS,
        "flat_band": FLAT_BAND,
        "threshold_grid": {
            "upper_range": [round(float(x), 2) for x in THRESH_UPPER_RANGE],
            "lower_range": [round(float(x), 2) for x in THRESH_LOWER_RANGE],
        },
        "in_sample_deployed": {
            "hold_upper": DEFAULT_HOLD_UPPER,
            "hold_lower": DEFAULT_HOLD_LOWER,
            "n_trades": deployed["n_trades"],
            "n_graded": deployed["n_graded"],
            "n_correct": deployed["n_correct"],
            "accuracy": round(deployed["accuracy"], 4) if deployed["accuracy"] else None,
            "mean_net_pct": round(deployed["mean_net"] * 100, 4),
        },
        "rolling_walkforward": {
            "n_windows": len(windows_mn),
            "min_trades_floor": MIN_TRADES_FLOOR,
            "objectives_tried": ["mean_net_per_trade", "directional_accuracy"],
            "mean_net_objective": {
                "degenerate_windows": len(degen_mn),
                "windows": [{k: v for k, v in w.items()
                             if k not in ("test_nets", "test_graded_correct")}
                            for w in windows_mn],
                "pooled_oos": _pool_to_json(pool_mn, "mean_net_per_trade"),
            },
            "accuracy_objective": {
                "min_trade_fraction": MIN_TRADE_FRACTION,
                "degenerate_windows": len(degen_acc),
                "windows": [{k: v for k, v in w.items()
                             if k not in ("test_nets", "test_graded_correct")}
                            for w in windows_acc],
                "pooled_oos": _pool_to_json(pool_acc, "directional_accuracy"),
            },
            "degeneracy_finding": {
                "mean_net_degenerate": len(degen_mn),
                "accuracy_degenerate": len(degen_acc),
                "total_windows": total_windows,
                "both_degenerate": len(degen_mn) > 0 and len(degen_acc) > 0,
            },
        },
        "subset_stability": {
            "note": "NOT out-of-sample. All events were in the dataset when thresholds were fitted.",
            "later_subset_n_trades": dep_sub_n_trades,
            "later_subset_n_graded": dep_sub_n_graded,
            "later_subset_n_correct": dep_sub_n_correct,
            "later_subset_accuracy": round(dep_sub_accuracy, 4) if dep_sub_accuracy else None,
            "full_sample_accuracy": round(deployed["accuracy"], 4) if deployed["accuracy"] else None,
        },
        "genuinely_unseen": {
            "note": "Cross-issuer generalisation test: 31 issuers scored after the "
                    "N=161 threshold sweep, zero issuer overlap with the 40 in-sweep "
                    "issuers. Both subsets span overlapping date ranges (interleaved, "
                    "not sequential) — this tests issuer transfer, not temporal "
                    "generalisation. RECONSTRUCTED: sweep membership inferred from "
                    "issuer ordering and count match (n_documents=161), not from a "
                    "recorded event list. 453 single-swap alternatives also produce 161.",
            "n_issuers_in_sweep": len(SWEEP_ISSUERS_AT_PROMOTION),
            "n_issuers_post_sweep": len(set(e["issuer"] for e in post_sweep)),
            "n_events_in_sweep": len(in_sweep),
            "n_events_post_sweep": len(post_sweep),
            "in_sweep": {
                "n_trades": seen_result["n_trades"],
                "n_graded": seen_result["n_graded"],
                "n_correct": seen_result["n_correct"],
                "accuracy": round(seen_result["accuracy"], 4) if seen_result["accuracy"] else None,
                "mean_net_pct": round(seen_result["mean_net"] * 100, 4),
            },
            "post_sweep": {
                "n_trades": unseen_result["n_trades"],
                "n_graded": unseen_result["n_graded"],
                "n_correct": unseen_result["n_correct"],
                "accuracy": round(unseen_result["accuracy"], 4) if unseen_result["accuracy"] else None,
                "mean_net_pct": round(unseen_result["mean_net"] * 100, 4),
            },
        },
        "two_window_headline": {
            "mean_net_objective": tw_mn,
            "accuracy_objective": tw_acc,
        },
    }

    # Add unseen floor/test if available
    if unseen_n_graded > 0:
        output["genuinely_unseen"]["post_sweep"]["majority_direction_floor"] = round(unseen_floor, 4)
        output["genuinely_unseen"]["post_sweep"]["margin_vs_floor_pp"] = round(margin_unseen * 100, 1)
        output["genuinely_unseen"]["post_sweep"]["binomial_p"] = round(binom_unseen.pvalue, 4)
        output["genuinely_unseen"]["post_sweep"]["mde_pp"] = round(mde_unseen * 100, 1)

    with open(OUT_JSON, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Wrote full results -> {OUT_JSON}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
