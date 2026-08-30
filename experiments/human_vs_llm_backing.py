"""
Compute all statistics reported in human_vs_llm_corrected.md and
direction_accuracy_decomposition.md and save them to backing CSVs.

Outputs:
  outputs/global/summary/human_vs_llm_statistics.csv
  outputs/global/summary/human_vs_llm_direction_decomposition.csv

Usage:
  python -m experiments.human_vs_llm_backing
"""

import csv
import math
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import stats

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.excluded_events import EXCLUDED_EVENTS  # noqa: E402
HUMAN_CSV = ROOT / "data" / "human" / "human_decisions_export_2026-08-12.csv"
CALIBRATION_CSV = ROOT / "outputs" / "global" / "summary" / "global_outcome_calibration_phase2.csv"
RETURNS_CSV = ROOT / "outputs" / "global" / "summary" / "returns_matrix.csv"
WORKSHEET_CSV = ROOT / "outputs" / "global" / "summary" / "worksheet_leak_flags.csv"
OUT_DIR = ROOT / "outputs" / "global" / "summary"

OUT_STATS = OUT_DIR / "human_vs_llm_statistics.csv"
OUT_DECOMP = OUT_DIR / "human_vs_llm_direction_decomposition.csv"

RNG_SEED = 20260709
N_BOOTSTRAP = 10_000

SOURCE_FILES = (
    "data/human/human_decisions_export_2026-08-12.csv; "
    "outputs/global/summary/global_outcome_calibration_phase2.csv; "
    "outputs/global/summary/returns_matrix.csv; "
    "outputs/global/summary/worksheet_leak_flags.csv"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def binomial_p(k, n, p0=0.5, alternative="greater"):
    """One-sided binomial test (default: greater, i.e. is accuracy > floor?)."""
    if n == 0:
        return float("nan")
    result = stats.binomtest(k, n, p0, alternative=alternative)
    return result.pvalue


def mde(p, n):
    """Minimum detectable effect: 2 * 1.96 * sqrt(p*(1-p)/n)."""
    if n == 0:
        return float("nan")
    return 2 * 1.96 * math.sqrt(p * (1 - p) / n)


def bootstrap_paired_diff(a_correct, b_correct, n_boot=N_BOOTSTRAP, seed=RNG_SEED, ci=0.90):
    """
    Bootstrap the paired difference (a - b) where a_correct and b_correct
    are boolean arrays of the same length. Returns (mean_diff, ci_low, ci_high, p_value).
    """
    rng = np.random.RandomState(seed)
    a = np.asarray(a_correct, dtype=float)
    b = np.asarray(b_correct, dtype=float)
    diffs = a - b
    n = len(diffs)
    obs_diff = diffs.mean()

    boot_diffs = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.randint(0, n, size=n)
        boot_diffs[i] = diffs[idx].mean()

    alpha = 1 - ci
    ci_low = np.percentile(boot_diffs, 100 * alpha / 2)
    ci_high = np.percentile(boot_diffs, 100 * (1 - alpha / 2))

    # Two-sided p-value: fraction of bootstrap samples on the opposite side of zero
    if obs_diff >= 0:
        p_val = 2 * np.mean(boot_diffs <= 0)
    else:
        p_val = 2 * np.mean(boot_diffs >= 0)
    p_val = min(p_val, 1.0)

    return obs_diff, ci_low, ci_high, p_val


def bootstrap_unpaired_diff(a_correct, b_correct, n_boot=N_BOOTSTRAP, seed=RNG_SEED, ci=0.90):
    """
    Bootstrap the unpaired difference in means (a - b).
    Returns (mean_diff, ci_low, ci_high, p_value).
    """
    rng = np.random.RandomState(seed)
    a = np.asarray(a_correct, dtype=float)
    b = np.asarray(b_correct, dtype=float)
    obs_diff = a.mean() - b.mean()
    na, nb = len(a), len(b)

    boot_diffs = np.empty(n_boot)
    for i in range(n_boot):
        a_samp = a[rng.randint(0, na, size=na)]
        b_samp = b[rng.randint(0, nb, size=nb)]
        boot_diffs[i] = a_samp.mean() - b_samp.mean()

    alpha = 1 - ci
    ci_low = np.percentile(boot_diffs, 100 * alpha / 2)
    ci_high = np.percentile(boot_diffs, 100 * (1 - alpha / 2))

    if obs_diff >= 0:
        p_val = 2 * np.mean(boot_diffs <= 0)
    else:
        p_val = 2 * np.mean(boot_diffs >= 0)
    p_val = min(p_val, 1.0)

    return obs_diff, ci_low, ci_high, p_val


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_data():
    """Load and join all data sources, returning the N=171 paired universe."""

    # Exclusion sets
    with open(WORKSHEET_CSV) as f:
        ws_excluded = set(
            r["document_id"] for r in csv.DictReader(f)
            if r["has_worksheet"] == "True" and r["has_human_score"] == "True"
        )

    with open(RETURNS_CSV) as f:
        ret_rows = list(csv.DictReader(f))
    ret_map = {r["document_id"]: r for r in ret_rows}
    timing_excluded = set(r["document_id"] for r in ret_rows if r["timing_excluded"] == "YES")

    spot_excluded = set(EXCLUDED_EVENTS)

    all_excluded = ws_excluded | spot_excluded | timing_excluded

    # Calibration (LLM decisions)
    with open(CALIBRATION_CSV) as f:
        cal_map = {r["document_id"]: r for r in csv.DictReader(f)}

    clean_universe = set(cal_map.keys()) - all_excluded

    # Human decisions
    with open(HUMAN_CSV) as f:
        human_all = list(csv.DictReader(f))

    human_filtered = [
        r for r in human_all
        if r["section"] == "All"
        and r["first_rater_for_event"] == "YES"
        and r["in_llm_universe"] == "YES"
    ]

    # Build document_id for each human row
    for h in human_filtered:
        qnum = h["quarter"].replace("Q", "")
        h["document_id"] = f"{h['ticker']}_FQ{qnum}_{h['year']}"

    # Paired universe: human events that are in the clean LLM universe
    paired = []
    for h in human_filtered:
        did = h["document_id"]
        if did not in clean_universe:
            continue
        ret_row = ret_map.get(did)
        if ret_row is None:
            continue
        try:
            ro = float(ret_row["ret_overnight"])
        except (ValueError, KeyError):
            continue

        paired.append({
            "document_id": did,
            "human_decision": h["human_decision"].strip().upper(),
            "llm_decision": cal_map[did]["blend_predicted_signal_default"].strip().upper(),
            "ret_overnight": ro,
            "repricing_basis_class": h.get("repricing_basis_class", "").strip(),
        })

    return paired


# ---------------------------------------------------------------------------
# Compute statistics
# ---------------------------------------------------------------------------

def is_correct(call, ret):
    """BUY correct if ret > 0, SELL correct if ret < 0."""
    if call == "BUY":
        return ret > 0
    elif call == "SELL":
        return ret < 0
    return False


def compute_all(paired):
    """Compute all statistics and return (rows_stats, rows_decomp)."""
    rows = []  # for human_vs_llm_statistics.csv

    def add(stat, value, n="", definition="", event_set="", convention="", test=""):
        rows.append({
            "statistic": stat,
            "value": f"{value}",
            "n": f"{n}",
            "definition": definition,
            "event_set": event_set,
            "convention": convention,
            "test": test,
            "source_files": SOURCE_FILES,
        })

    N = len(paired)

    # -----------------------------------------------------------------------
    # Pooled comparison (N=171)
    # -----------------------------------------------------------------------
    event_set_pooled = f"N={N} paired events (section=All, first_rater=YES, in_llm=YES, exclusion set applied)"

    # Call counts
    for arm, key in [("human", "human_decision"), ("llm", "llm_decision")]:
        calls = Counter(e[key] for e in paired)
        for signal in ["BUY", "HOLD", "SELL"]:
            cnt = calls.get(signal, 0)
            frac = cnt / N
            add(f"{arm}_call_{signal.lower()}_count", cnt, n=N,
                definition=f"Number of {signal} calls by {arm} arm",
                event_set=event_set_pooled)
            add(f"{arm}_call_{signal.lower()}_frac", f"{frac:.4f}", n=N,
                definition=f"Fraction of {signal} calls by {arm} arm",
                event_set=event_set_pooled)

    # Traded, graded, correct, accuracy
    for arm, key in [("human", "human_decision"), ("llm", "llm_decision")]:
        traded = [e for e in paired if e[key] in ("BUY", "SELL")]
        graded = [e for e in traded if abs(e["ret_overnight"]) > 0.02]
        correct = [e for e in graded if is_correct(e[key], e["ret_overnight"])]

        add(f"{arm}_traded_count", len(traded), n=N,
            definition=f"Events where {arm} called BUY or SELL",
            event_set=event_set_pooled)
        add(f"{arm}_graded_count", len(graded), n=len(traded),
            definition=f"Traded events with |ret_overnight| > 2%",
            event_set=event_set_pooled, convention="±2% overnight band")
        add(f"{arm}_correct_count", len(correct), n=len(graded),
            definition=f"Graded events where call matches return sign",
            event_set=event_set_pooled, convention="±2% overnight band")
        if len(graded) > 0:
            acc = len(correct) / len(graded)
            add(f"{arm}_accuracy", f"{acc:.4f}", n=len(graded),
                definition=f"correct / graded for {arm}",
                event_set=event_set_pooled, convention="±2% overnight band")

    # Always-BUY baseline on graded events
    all_graded_events = [e for e in paired if abs(e["ret_overnight"]) > 0.02]
    always_buy_correct = sum(1 for e in all_graded_events if e["ret_overnight"] > 0)
    n_graded_all = len(all_graded_events)
    if n_graded_all > 0:
        add("always_buy_baseline_graded", f"{always_buy_correct / n_graded_all:.4f}",
            n=n_graded_all,
            definition="Fraction with ret > 0 among events with |ret| > 2%",
            event_set=event_set_pooled, convention="±2% overnight band")
        add("always_buy_baseline_graded_count", f"{always_buy_correct}/{n_graded_all}",
            n=n_graded_all,
            definition="always-BUY correct / total graded events",
            event_set=event_set_pooled, convention="±2% overnight band")

    # -----------------------------------------------------------------------
    # Paired comparison: both traded AND both graded (N=48)
    # -----------------------------------------------------------------------
    paired_both_traded = [
        e for e in paired
        if e["human_decision"] in ("BUY", "SELL") and e["llm_decision"] in ("BUY", "SELL")
    ]
    paired_both_graded = [e for e in paired_both_traded if abs(e["ret_overnight"]) > 0.02]
    n_paired_graded = len(paired_both_graded)
    event_set_paired_graded = f"N={n_paired_graded} events where both arms traded AND |ret|>2%"

    if n_paired_graded > 0:
        llm_correct_paired = [is_correct(e["llm_decision"], e["ret_overnight"]) for e in paired_both_graded]
        human_correct_paired = [is_correct(e["human_decision"], e["ret_overnight"]) for e in paired_both_graded]

        llm_c = sum(llm_correct_paired)
        human_c = sum(human_correct_paired)

        add("paired_graded_n", n_paired_graded, n=n_paired_graded,
            definition="Events where both arms traded and |ret|>2%",
            event_set=event_set_paired_graded, convention="±2% overnight band")
        add("paired_graded_llm_correct", llm_c, n=n_paired_graded,
            definition="LLM correct in paired graded set",
            event_set=event_set_paired_graded, convention="±2% overnight band")
        add("paired_graded_llm_accuracy", f"{llm_c / n_paired_graded:.4f}",
            n=n_paired_graded, event_set=event_set_paired_graded)
        add("paired_graded_human_correct", human_c, n=n_paired_graded,
            definition="Human correct in paired graded set",
            event_set=event_set_paired_graded, convention="±2% overnight band")
        add("paired_graded_human_accuracy", f"{human_c / n_paired_graded:.4f}",
            n=n_paired_graded, event_set=event_set_paired_graded)

        diff_pp = (llm_c - human_c) / n_paired_graded * 100
        add("paired_graded_diff_pp", f"{diff_pp:.1f}",
            n=n_paired_graded,
            definition="LLM accuracy - Human accuracy (pp)",
            event_set=event_set_paired_graded)

        # Bootstrap paired CI
        obs_diff, ci_lo, ci_hi, p_val = bootstrap_paired_diff(
            llm_correct_paired, human_correct_paired
        )
        add("paired_graded_90ci_low_pp", f"{ci_lo * 100:.1f}",
            n=n_paired_graded, test="bootstrap paired, 10000 resamples, seed 20260709",
            event_set=event_set_paired_graded)
        add("paired_graded_90ci_high_pp", f"{ci_hi * 100:.1f}",
            n=n_paired_graded, test="bootstrap paired, 10000 resamples, seed 20260709",
            event_set=event_set_paired_graded)
        add("paired_graded_p_value", f"{p_val:.3f}",
            n=n_paired_graded, test="bootstrap paired, 10000 resamples, seed 20260709",
            event_set=event_set_paired_graded)

        # MDE
        p_obs = llm_c / n_paired_graded
        paired_mde = mde(p_obs, n_paired_graded) * 100
        add("paired_graded_mde_pp", f"{paired_mde:.0f}",
            n=n_paired_graded,
            definition="MDE = 2*1.96*sqrt(p*(1-p)/n) in pp",
            event_set=event_set_paired_graded)

    # -----------------------------------------------------------------------
    # Direction-only comparison (N=76 where both arms traded, no band filter)
    # -----------------------------------------------------------------------
    direction_only = [
        e for e in paired
        if e["human_decision"] in ("BUY", "SELL") and e["llm_decision"] in ("BUY", "SELL")
    ]
    n_dir = len(direction_only)
    event_set_dir = f"N={n_dir} events where both arms called BUY or SELL (direction-only)"

    # Sign accuracy
    human_sign_correct = [is_correct(e["human_decision"], e["ret_overnight"]) for e in direction_only]
    llm_sign_correct = [is_correct(e["llm_decision"], e["ret_overnight"]) for e in direction_only]

    h_correct = sum(human_sign_correct)
    l_correct = sum(llm_sign_correct)

    add("direction_only_n", n_dir, n=n_dir,
        definition="Events where both arms called BUY or SELL",
        event_set=event_set_dir, convention="sign accuracy, no band filter")

    add("direction_human_sign_accuracy", f"{h_correct / n_dir:.4f}",
        n=n_dir, definition="Human sign accuracy (call matches ret sign)",
        event_set=event_set_dir, convention="sign accuracy, no band filter")
    add("direction_human_sign_correct", f"{h_correct}/{n_dir}",
        n=n_dir, event_set=event_set_dir)

    add("direction_llm_sign_accuracy", f"{l_correct / n_dir:.4f}",
        n=n_dir, definition="LLM sign accuracy (call matches ret sign)",
        event_set=event_set_dir, convention="sign accuracy, no band filter")
    add("direction_llm_sign_correct", f"{l_correct}/{n_dir}",
        n=n_dir, event_set=event_set_dir)

    # Always-BUY / Always-DOWN baselines
    n_positive = sum(1 for e in direction_only if e["ret_overnight"] > 0)
    n_negative = sum(1 for e in direction_only if e["ret_overnight"] < 0)
    n_zero = n_dir - n_positive - n_negative
    # For base-rate comparisons, zero-return events count as DOWN (not positive),
    # giving n_down = n_negative + n_zero. This matches the prose convention
    # (56.6% = 43/76 in surviving_findings.md finding #7).
    n_down = n_negative + n_zero

    add("direction_always_buy_accuracy", f"{n_positive / n_dir:.4f}",
        n=n_dir, definition="Fraction with ret > 0",
        event_set=event_set_dir)
    add("direction_always_buy_correct", f"{n_positive}/{n_dir}",
        n=n_dir, event_set=event_set_dir)

    add("direction_always_down_accuracy", f"{n_down / n_dir:.4f}",
        n=n_dir, definition="Fraction with ret <= 0 (zero counted as DOWN)",
        event_set=event_set_dir)
    add("direction_always_down_correct", f"{n_down}/{n_dir}",
        n=n_dir, event_set=event_set_dir)
    add("direction_n_zero_return", n_zero, n=n_dir,
        definition="Events with exactly zero overnight return",
        event_set=event_set_dir)

    # LLM - Human diff, bootstrap
    obs_diff, ci_lo, ci_hi, p_val = bootstrap_paired_diff(
        llm_sign_correct, human_sign_correct
    )
    add("direction_llm_minus_human_pp", f"{obs_diff * 100:.1f}",
        n=n_dir, definition="LLM sign accuracy - Human sign accuracy (pp)",
        event_set=event_set_dir, test="bootstrap paired, 10000 resamples, seed 20260709")
    add("direction_90ci_low_pp", f"{ci_lo * 100:.1f}",
        n=n_dir, test="bootstrap paired, 10000 resamples, seed 20260709",
        event_set=event_set_dir)
    add("direction_90ci_high_pp", f"{ci_hi * 100:.1f}",
        n=n_dir, test="bootstrap paired, 10000 resamples, seed 20260709",
        event_set=event_set_dir)
    add("direction_p_value", f"{p_val:.3f}",
        n=n_dir, test="bootstrap paired, 10000 resamples, seed 20260709",
        event_set=event_set_dir)

    # Human vs always-DOWN: binomial (one-sided greater)
    # Floor = n_negative/n_dir = 42/76 = 55.3% (strict negative, matching prose)
    p_human_vs_down = binomial_p(h_correct, n_dir, n_negative / n_dir)
    add("direction_human_vs_always_down_p", f"{p_human_vs_down:.3f}",
        n=n_dir, test=f"binomial test one-sided greater, p0={n_negative/n_dir:.4f}",
        event_set=event_set_dir,
        definition="Human sign accuracy vs always-DOWN rate (strict negative)")

    # LLM vs always-DOWN: binomial (one-sided greater)
    p_llm_vs_down = binomial_p(l_correct, n_dir, n_negative / n_dir)
    add("direction_llm_vs_always_down_p", f"{p_llm_vs_down:.3f}",
        n=n_dir, test=f"binomial test one-sided greater, p0={n_negative/n_dir:.4f}",
        event_set=event_set_dir,
        definition="LLM sign accuracy vs always-DOWN rate (strict negative)")

    # MDE at N=76
    dir_mde = mde(h_correct / n_dir, n_dir) * 100
    add("direction_mde_pp", f"{dir_mde:.0f}",
        n=n_dir, definition="MDE = 2*1.96*sqrt(p*(1-p)/n) in pp",
        event_set=event_set_dir)

    # -----------------------------------------------------------------------
    # By call direction (on the N=76 direction-only set)
    # -----------------------------------------------------------------------
    overall_frac_down = n_down / n_dir  # base rate for SELL calls (zero = DOWN)
    overall_frac_positive = n_positive / n_dir  # base rate for BUY calls

    for arm, key in [("human", "human_decision"), ("llm", "llm_decision")]:
        for call_dir in ["BUY", "SELL"]:
            subset = [e for e in direction_only if e[key] == call_dir]
            n_sub = len(subset)
            if n_sub == 0:
                continue
            if call_dir == "BUY":
                correct_count = sum(1 for e in subset if e["ret_overnight"] > 0)
                base_rate = overall_frac_positive
            else:
                correct_count = sum(1 for e in subset if e["ret_overnight"] < 0)
                base_rate = overall_frac_down

            acc = correct_count / n_sub
            p_vs_50 = binomial_p(correct_count, n_sub, 0.5)

            # vs overall base rate: for BUY calls, base rate is frac positive overall;
            # for SELL calls, base rate is frac negative overall
            p_vs_base = binomial_p(correct_count, n_sub, base_rate)

            add(f"direction_{arm}_{call_dir.lower()}_accuracy", f"{acc:.4f}",
                n=n_sub,
                definition=f"{arm} {call_dir} accuracy (fraction correct among {call_dir} calls)",
                event_set=event_set_dir, convention="sign accuracy, no band filter")
            add(f"direction_{arm}_{call_dir.lower()}_correct", f"{correct_count}/{n_sub}",
                n=n_sub, event_set=event_set_dir)
            add(f"direction_{arm}_{call_dir.lower()}_vs_50pct_p", f"{p_vs_50:.3f}",
                n=n_sub, test="binomial test, p0=0.5",
                event_set=event_set_dir)
            add(f"direction_{arm}_{call_dir.lower()}_vs_base_rate_p", f"{p_vs_base:.3f}",
                n=n_sub, test=f"binomial test, p0={base_rate:.4f}",
                event_set=event_set_dir,
                definition=f"vs overall {'positive' if call_dir == 'BUY' else 'negative'} rate = {base_rate:.4f}")

    # -----------------------------------------------------------------------
    # By repricing_basis_class
    # -----------------------------------------------------------------------
    for rbc, rbc_label in [("fact_based", "fact_based"), ("price_based", "price_based")]:
        subset = [e for e in paired if e["repricing_basis_class"] == rbc]
        n_rbc = len(subset)
        event_set_rbc = f"N={n_rbc} {rbc_label} events"

        add(f"rbc_{rbc_label}_n", n_rbc, n=n_rbc,
            definition=f"Events with repricing_basis_class == {rbc_label}",
            event_set=event_set_rbc)

        for arm, key in [("human", "human_decision"), ("llm", "llm_decision")]:
            traded = [e for e in subset if e[key] in ("BUY", "SELL")]
            graded = [e for e in traded if abs(e["ret_overnight"]) > 0.02]
            correct = [e for e in graded if is_correct(e[key], e["ret_overnight"])]

            add(f"rbc_{rbc_label}_{arm}_graded", len(graded), n=len(traded),
                definition=f"{arm} graded in {rbc_label} subset",
                event_set=event_set_rbc, convention="±2% overnight band")
            if len(graded) > 0:
                acc = len(correct) / len(graded)
                add(f"rbc_{rbc_label}_{arm}_correct", len(correct), n=len(graded),
                    event_set=event_set_rbc)
                add(f"rbc_{rbc_label}_{arm}_accuracy", f"{acc:.4f}",
                    n=len(graded),
                    definition=f"{arm} accuracy in {rbc_label} subset",
                    event_set=event_set_rbc, convention="±2% overnight band")

        # Paired stats where both graded
        both_traded_rbc = [
            e for e in subset
            if e["human_decision"] in ("BUY", "SELL") and e["llm_decision"] in ("BUY", "SELL")
        ]
        both_graded_rbc = [e for e in both_traded_rbc if abs(e["ret_overnight"]) > 0.02]
        n_bg = len(both_graded_rbc)
        add(f"rbc_{rbc_label}_paired_graded_n", n_bg, n=n_bg,
            definition=f"Events where both arms traded + |ret|>2% in {rbc_label}",
            event_set=event_set_rbc, convention="±2% overnight band")

        if n_bg > 0:
            llm_c_rbc = [is_correct(e["llm_decision"], e["ret_overnight"]) for e in both_graded_rbc]
            human_c_rbc = [is_correct(e["human_decision"], e["ret_overnight"]) for e in both_graded_rbc]
            llm_sum = sum(llm_c_rbc)
            human_sum = sum(human_c_rbc)

            add(f"rbc_{rbc_label}_paired_llm_accuracy", f"{llm_sum / n_bg:.4f}",
                n=n_bg, event_set=event_set_rbc)
            add(f"rbc_{rbc_label}_paired_human_accuracy", f"{human_sum / n_bg:.4f}",
                n=n_bg, event_set=event_set_rbc)

            diff_pp = (llm_sum - human_sum) / n_bg * 100
            add(f"rbc_{rbc_label}_paired_diff_pp", f"{diff_pp:.1f}",
                n=n_bg, event_set=event_set_rbc)

            if n_bg >= 5:
                obs, ci_lo, ci_hi, pv = bootstrap_paired_diff(llm_c_rbc, human_c_rbc)
                add(f"rbc_{rbc_label}_paired_p_value", f"{pv:.3f}",
                    n=n_bg, test="bootstrap paired",
                    event_set=event_set_rbc)

            paired_mde_rbc = mde(llm_sum / n_bg if n_bg > 0 else 0.5, n_bg) * 100
            add(f"rbc_{rbc_label}_paired_mde_pp", f"{paired_mde_rbc:.0f}",
                n=n_bg, event_set=event_set_rbc)

    # -----------------------------------------------------------------------
    # Direction accuracy decomposition (Output 2)
    # -----------------------------------------------------------------------
    decomp_rows = []
    # base rates for the N=76 direction-only set
    base_rate_positive = n_positive / n_dir  # for BUY calls
    base_rate_down = n_down / n_dir  # for SELL calls (zero = DOWN)

    for arm, key in [("human", "human_decision"), ("llm", "llm_decision")]:
        for call_dir in ["BUY", "SELL"]:
            subset = [e for e in direction_only if e[key] == call_dir]
            n_sub = len(subset)
            if n_sub == 0:
                continue
            if call_dir == "BUY":
                n_correct = sum(1 for e in subset if e["ret_overnight"] > 0)
                br = base_rate_positive
            else:
                n_correct = sum(1 for e in subset if e["ret_overnight"] < 0)
                br = base_rate_down

            acc = n_correct / n_sub
            margin_vs_50 = (acc - 0.5) * 100
            p_vs_50 = binomial_p(n_correct, n_sub, 0.5)
            margin_vs_br = (acc - br) * 100
            p_vs_br = binomial_p(n_correct, n_sub, br)

            decomp_rows.append({
                "arm": arm,
                "call": call_dir,
                "n_correct": n_correct,
                "n_total": n_sub,
                "accuracy": f"{acc:.4f}",
                "vs_50pct_margin_pp": f"{margin_vs_50:.1f}",
                "vs_50pct_p": f"{p_vs_50:.4f}",
                "vs_base_rate_margin_pp": f"{margin_vs_br:.1f}",
                "vs_base_rate_p": f"{p_vs_br:.4f}",
                "base_rate": f"{br:.4f}",
            })

        # Overall row for each arm
        arm_correct = h_correct if arm == "human" else l_correct
        arm_acc = arm_correct / n_dir
        decomp_rows.append({
            "arm": arm,
            "call": "Overall",
            "n_correct": arm_correct,
            "n_total": n_dir,
            "accuracy": f"{arm_acc:.4f}",
            "vs_50pct_margin_pp": f"{(arm_acc - 0.5) * 100:.1f}",
            "vs_50pct_p": f"{binomial_p(arm_correct, n_dir, 0.5):.4f}",
            "vs_base_rate_margin_pp": "",
            "vs_base_rate_p": "",
            "base_rate": "",
        })

    return rows, decomp_rows


# ---------------------------------------------------------------------------
# Verification expectations, keyed on the DEPLOYED constants
# ---------------------------------------------------------------------------
# Every figure below moves when blend.py's constants move, so a single hardcoded
# table stops asserting anything the moment they are promoted - it just fails 24
# times and prints "Continuing anyway". Keying the table on the deployed regime
# keeps the guard biting at whichever regime is deployed, and keeps the
# superseded regime's figures in the file as the record of what it published.
#
# An unrecognised regime is a hard error, not an empty pass: a future constants
# change has to record what it expects before this script will run at all.
#
# The key carries the bad-document exclusions as well as the constants, for the
# same reason it carries the constants: excluding an event moves every figure here
# for a legitimate reason, and without the exclusions in the key the table reports
# 23 mismatches as though the constants had drifted. A regime is the constants AND
# the universe they run on.
VERIFY_EXPECTATIONS = {
    # committed 2026-08-05, superseded 2026-08-19. These are the figures the
    # individual report and Master_Data_Phase_3.xlsx published.
    ((0.55, 0.45, 0.0, 0.0), 0.25, -0.05, ("SPOT_FQ1_2026",)): {
        "N paired": 171,
        "Direction-only N": 76,
        "Human sign correct": 44, "Human sign accuracy %": "57.9",
        "LLM sign correct": 46, "LLM sign accuracy %": "60.5",
        "Always-BUY correct": 33, "Always-BUY %": "43.4",
        "Always-DOWN correct (incl zero)": 43, "Always-DOWN %": "56.6",
        "Human BUY calls": 96, "Human HOLD calls": 40, "Human SELL calls": 35,
        "LLM BUY calls": 42, "LLM HOLD calls": 69, "LLM SELL calls": 60,
        "Human traded": 131, "Human graded": 79, "Human correct (pooled)": 45,
        "LLM traded": 102, "LLM graded": 58, "LLM correct (pooled)": 40,
        "Paired graded N": 48,
        "Human BUY accuracy numerator": 27, "Human BUY accuracy denominator": 53,
        "Human SELL accuracy numerator": 17, "Human SELL accuracy denominator": 23,
        "LLM BUY accuracy numerator": 20, "LLM BUY accuracy denominator": 36,
        "LLM SELL accuracy numerator": 26, "LLM SELL accuracy denominator": 40,
        "fact_based N": 34, "price_based N": 64,
    },
    # promoted 2026-08-19. Recorded only after the block above reproduced 33/33
    # on the same code path - the gate this project runs on every figure.
    ((0.80, 0.20, 0.0, 0.0), 0.20, -0.10, ("SPOT_FQ1_2026",)): {
        "N paired": 171,
        "Direction-only N": 86,
        "Human sign correct": 50, "Human sign accuracy %": "58.1",
        "LLM sign correct": 51, "LLM sign accuracy %": "59.3",
        "Always-BUY correct": 40, "Always-BUY %": "46.5",
        "Always-DOWN correct (incl zero)": 46, "Always-DOWN %": "53.5",
        "Human BUY calls": 96, "Human HOLD calls": 40, "Human SELL calls": 35,
        "LLM BUY calls": 73, "LLM HOLD calls": 53, "LLM SELL calls": 45,
        "Human traded": 131, "Human graded": 79, "Human correct (pooled)": 45,
        "LLM traded": 118, "LLM graded": 70, "LLM correct (pooled)": 44,
        "Paired graded N": 55,
        "Human BUY accuracy numerator": 34, "Human BUY accuracy denominator": 64,
        "Human SELL accuracy numerator": 16, "Human SELL accuracy denominator": 22,
        "LLM BUY accuracy numerator": 33, "LLM BUY accuracy denominator": 60,
        "LLM SELL accuracy numerator": 18, "LLM SELL accuracy denominator": 26,
        "fact_based N": 34, "price_based N": 64,
    },
    # DIS_FQ1_2025 excluded 2026-08-24 for look-ahead. It is a paired event and a
    # BUY on an UP outcome, so every BUY-side and every pooled figure falls by
    # exactly one, and every HOLD, SELL and always-DOWN figure is untouched. That
    # pattern is the check on this block: recorded after confirming the 33 actuals
    # against the block above, which differs from it only in those places.
    ((0.80, 0.20, 0.0, 0.0), 0.20, -0.10,
     ("DIS_FQ1_2025", "SPOT_FQ1_2026")): {
        "N paired": 170,
        "Direction-only N": 85,
        "Human sign correct": 49, "Human sign accuracy %": "57.6",
        "LLM sign correct": 50, "LLM sign accuracy %": "58.8",
        "Always-BUY correct": 39, "Always-BUY %": "45.9",
        "Always-DOWN correct (incl zero)": 46, "Always-DOWN %": "54.1",
        "Human BUY calls": 95, "Human HOLD calls": 40, "Human SELL calls": 35,
        "LLM BUY calls": 72, "LLM HOLD calls": 53, "LLM SELL calls": 45,
        "Human traded": 130, "Human graded": 78, "Human correct (pooled)": 44,
        "LLM traded": 117, "LLM graded": 69, "LLM correct (pooled)": 43,
        "Paired graded N": 54,
        "Human BUY accuracy numerator": 33, "Human BUY accuracy denominator": 63,
        "Human SELL accuracy numerator": 16, "Human SELL accuracy denominator": 22,
        "LLM BUY accuracy numerator": 32, "LLM BUY accuracy denominator": 59,
        "LLM SELL accuracy numerator": 18, "LLM SELL accuracy denominator": 26,
        "fact_based N": 33, "price_based N": 64,
    },
}


def deployed_expectations():
    """The expectation block for whatever blend.py currently deploys."""
    # ROOT, not the cwd: this script is run both as a module and by path, and
    # its inputs are already resolved from __file__ for the same reason.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from blend import DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER, DEFAULT_WEIGHTS
    key = (tuple(round(w, 6) for w in DEFAULT_WEIGHTS),
           round(DEFAULT_HOLD_UPPER, 6), round(DEFAULT_HOLD_LOWER, 6),
           tuple(sorted(EXCLUDED_EVENTS)))
    if key not in VERIFY_EXPECTATIONS:
        raise SystemExit(
            f"No verification expectations recorded for the deployed constants {key}.\n"
            "Add a block to VERIFY_EXPECTATIONS - gated against the superseded regime "
            "first - before running this script at new constants."
        )
    return VERIFY_EXPECTATIONS[key]


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify(paired):
    """Print verification of key figures against human_vs_llm_corrected.md.

    Expectations come from VERIFY_EXPECTATIONS, keyed on the deployed constants,
    so the assertions follow a promotion instead of being silently invalidated
    by one.
    """
    N = len(paired)
    expectations = deployed_expectations()
    print(f"\n=== VERIFICATION ===")

    checks = []

    def check(label, _legacy, actual):
        expected = expectations[label]
        ok = expected == actual
        status = "OK" if ok else "MISMATCH"
        checks.append((label, expected, actual, ok))
        print(f"  [{status}] {label}: expected={expected}, actual={actual}")

    check("N paired", 171, N)

    direction_only = [
        e for e in paired
        if e["human_decision"] in ("BUY", "SELL") and e["llm_decision"] in ("BUY", "SELL")
    ]
    check("Direction-only N", 76, len(direction_only))

    h_correct = sum(
        1 for e in direction_only
        if is_correct(e["human_decision"], e["ret_overnight"])
    )
    l_correct = sum(
        1 for e in direction_only
        if is_correct(e["llm_decision"], e["ret_overnight"])
    )
    n_dir = len(direction_only)

    check("Human sign correct", 44, h_correct)
    check("Human sign accuracy %", "57.9", f"{h_correct / n_dir * 100:.1f}")
    check("LLM sign correct", 46, l_correct)
    check("LLM sign accuracy %", "60.5", f"{l_correct / n_dir * 100:.1f}")

    n_positive = sum(1 for e in direction_only if e["ret_overnight"] > 0)
    n_negative = sum(1 for e in direction_only if e["ret_overnight"] < 0)
    n_down = n_dir - n_positive  # zero-return events count as DOWN
    check("Always-BUY correct", 33, n_positive)
    check("Always-BUY %", "43.4", f"{n_positive / n_dir * 100:.1f}")
    check("Always-DOWN correct (incl zero)", 43, n_down)
    check("Always-DOWN %", "56.6", f"{n_down / n_dir * 100:.1f}")

    # Also check pooled figures from the md
    human_buy = sum(1 for e in paired if e["human_decision"] == "BUY")
    human_hold = sum(1 for e in paired if e["human_decision"] == "HOLD")
    human_sell = sum(1 for e in paired if e["human_decision"] == "SELL")
    check("Human BUY calls", 96, human_buy)
    check("Human HOLD calls", 40, human_hold)
    check("Human SELL calls", 35, human_sell)

    llm_buy = sum(1 for e in paired if e["llm_decision"] == "BUY")
    llm_hold = sum(1 for e in paired if e["llm_decision"] == "HOLD")
    llm_sell = sum(1 for e in paired if e["llm_decision"] == "SELL")
    check("LLM BUY calls", 42, llm_buy)
    check("LLM HOLD calls", 69, llm_hold)
    check("LLM SELL calls", 60, llm_sell)

    # Graded/correct from pooled
    human_traded = [e for e in paired if e["human_decision"] in ("BUY", "SELL")]
    human_graded = [e for e in human_traded if abs(e["ret_overnight"]) > 0.02]
    human_correct_pooled = [e for e in human_graded if is_correct(e["human_decision"], e["ret_overnight"])]
    check("Human traded", 131, len(human_traded))
    check("Human graded", 79, len(human_graded))
    check("Human correct (pooled)", 45, len(human_correct_pooled))

    llm_traded = [e for e in paired if e["llm_decision"] in ("BUY", "SELL")]
    llm_graded = [e for e in llm_traded if abs(e["ret_overnight"]) > 0.02]
    llm_correct_pooled = [e for e in llm_graded if is_correct(e["llm_decision"], e["ret_overnight"])]
    check("LLM traded", 102, len(llm_traded))
    # 57 / 39 came in with master's Lowe's fix, which moved these two at the
    # SUPERSEDED constants. On this branch the positional is inert - check() reads
    # VERIFY_EXPECTATIONS instead - and the superseded block above deliberately
    # keeps 58 / 40, which is what the report and the workbook published.
    check("LLM graded", 57, len(llm_graded))
    check("LLM correct (pooled)", 39, len(llm_correct_pooled))

    # Paired graded
    both_traded = [
        e for e in paired
        if e["human_decision"] in ("BUY", "SELL") and e["llm_decision"] in ("BUY", "SELL")
    ]
    both_graded = [e for e in both_traded if abs(e["ret_overnight"]) > 0.02]
    check("Paired graded N", 48, len(both_graded))

    # By-direction from the md
    human_buy_subset = [e for e in direction_only if e["human_decision"] == "BUY"]
    human_buy_correct = sum(1 for e in human_buy_subset if e["ret_overnight"] > 0)
    check("Human BUY accuracy numerator", 27, human_buy_correct)
    check("Human BUY accuracy denominator", 53, len(human_buy_subset))

    human_sell_subset = [e for e in direction_only if e["human_decision"] == "SELL"]
    human_sell_correct = sum(1 for e in human_sell_subset if e["ret_overnight"] < 0)
    check("Human SELL accuracy numerator", 17, human_sell_correct)
    check("Human SELL accuracy denominator", 23, len(human_sell_subset))

    llm_buy_subset = [e for e in direction_only if e["llm_decision"] == "BUY"]
    llm_buy_correct = sum(1 for e in llm_buy_subset if e["ret_overnight"] > 0)
    check("LLM BUY accuracy numerator", 20, llm_buy_correct)
    check("LLM BUY accuracy denominator", 36, len(llm_buy_subset))

    llm_sell_subset = [e for e in direction_only if e["llm_decision"] == "SELL"]
    llm_sell_correct = sum(1 for e in llm_sell_subset if e["ret_overnight"] < 0)
    check("LLM SELL accuracy numerator", 26, llm_sell_correct)
    check("LLM SELL accuracy denominator", 40, len(llm_sell_subset))

    # repricing basis
    fact_based = [e for e in paired if e["repricing_basis_class"] == "fact_based"]
    price_based = [e for e in paired if e["repricing_basis_class"] == "price_based"]
    check("fact_based N", 34, len(fact_based))
    check("price_based N", 64, len(price_based))

    n_ok = sum(1 for _, _, _, ok in checks if ok)
    n_fail = sum(1 for _, _, _, ok in checks if not ok)
    print(f"\n  {n_ok} checks passed, {n_fail} failed.")
    if n_fail > 0:
        print("  WARNING: some figures do not match. Continuing anyway.")
    return n_fail == 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading data...")
    paired = load_data()
    print(f"Paired universe: N={len(paired)}")

    all_ok = verify(paired)

    print("\nComputing statistics...")
    stats_rows, decomp_rows = compute_all(paired)

    # Write output 1
    fieldnames1 = ["statistic", "value", "n", "definition", "event_set", "convention", "test", "source_files"]
    with open(OUT_STATS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames1)
        w.writeheader()
        w.writerows(stats_rows)
    print(f"\nWrote {len(stats_rows)} rows to {OUT_STATS}")

    # Write output 2
    fieldnames2 = ["arm", "call", "n_correct", "n_total", "accuracy",
                    "vs_50pct_margin_pp", "vs_50pct_p",
                    "vs_base_rate_margin_pp", "vs_base_rate_p", "base_rate"]
    with open(OUT_DECOMP, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames2)
        w.writeheader()
        w.writerows(decomp_rows)
    print(f"Wrote {len(decomp_rows)} rows to {OUT_DECOMP}")

    if not all_ok:
        print("\nWARNING: verification failures detected - check output carefully.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
