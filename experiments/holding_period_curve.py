"""
experiments/holding_period_curve.py
Extension 2 (holding-period curve): does the overnight signal persist over
longer horizons, or does the overnight window choice create the result?

Computes mean net return per trade at each horizon (overnight, 1d, 3d, 5d,
10d) using the same BUY/SELL signal from the deployed blend. Returns at
each horizon are alternative versions of the same trade, never compounded
across horizons. Accuracy is graded against that horizon's implied HOLD
band from implied_hold_bands.csv; the overnight +/-2% band is
PRE-REGISTERED and fixed, all longer-horizon bands are RECALIBRATED and
secondary.

Exclusions (39 events from 268 -> N=229 clean):
  - 25 worksheet contamination (has_human_score=True in worksheet_leak_flags.csv)
  - 1 SPOT_FQ1_2026 (misattributed)
  - 13 timing-excluded (timing_excluded=YES in returns_matrix.csv)

Run: python -m experiments.holding_period_curve
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats as sp_stats

# -- project imports ----------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval.excluded_events import EXCLUDED_EVENTS  # noqa: E402
from blend import DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER, DEFAULT_WEIGHTS, blend_scores
from bootstrap_stats import bootstrap_trade_stats

# -- paths --------------------------------------------------------------------
SUMMARY_DIR = Path(__file__).resolve().parent.parent / "outputs" / "global" / "summary"
RETURNS_CSV = SUMMARY_DIR / "returns_matrix.csv"
CALIBRATION_CSV = SUMMARY_DIR / "global_outcome_calibration_phase2.csv"
HOLD_BANDS_CSV = SUMMARY_DIR / "implied_hold_bands.csv"
LEAK_FLAGS_CSV = SUMMARY_DIR / "worksheet_leak_flags.csv"

OUT_CSV = SUMMARY_DIR / "ext2_holding_curve.csv"
OUT_PNG = SUMMARY_DIR / "ext2_holding_curve.png"

# -- constants ----------------------------------------------------------------
HORIZONS = ["overnight", "1d", "3d", "5d", "10d"]
RETURN_COLS = {
    "overnight": "ret_overnight",
    "1d": "ret_1d",
    "3d": "ret_3d",
    "5d": "ret_5d",
    "10d": "ret_10d",
}
COST_BPS = 10.0
SHORT_BORROW_BPS = 0.0
COST_FRAC = COST_BPS / 10_000  # 0.001


def _num(x):
    if x is None or x == "":
        return None
    return float(x)


def _load_returns_matrix():
    """Load returns_matrix.csv, skipping comment lines."""
    rows = []
    with open(RETURNS_CSV) as f:
        lines = [l for l in f if not l.startswith("#")]
    reader = csv.DictReader(lines)
    for row in reader:
        rows.append(row)
    return rows


def _load_hold_bands():
    """Load implied_hold_bands.csv, skipping comment lines."""
    bands = {}
    with open(HOLD_BANDS_CSV) as f:
        lines = [l for l in f if not l.startswith("#")]
    reader = csv.DictReader(lines)
    for row in reader:
        bands[row["horizon"]] = float(row["hold_band"])
    return bands


def _load_leak_flags():
    """Return set of document_ids with has_human_score=True."""
    excluded = set()
    with open(LEAK_FLAGS_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("has_human_score", "").strip() == "True":
                excluded.add(row["document_id"])
    return excluded


def _load_calibration():
    """Load calibration CSV -> dict keyed by document_id."""
    cal = {}
    with open(CALIBRATION_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            cal[row["document_id"]] = row
    return cal


def _grade_accuracy(ret, band):
    """Grade a single return against a HOLD band.
    Returns (graded: bool, correct: bool|None).
    graded=False means the return fell inside the band (ungraded).
    """
    if abs(ret) <= band:
        return False, None  # inside band, ungraded
    truth = "BUY" if ret > 0 else "SELL"
    return True, truth


def main(
    extra_signal_columns: dict[str, dict[str, str]] | None = None,
):
    """
    extra_signal_columns: optional dict of {label: {document_id: "BUY"/"HOLD"/"SELL"}}
    for future human-line overlay. Only the model line is produced now.
    """
    # -- load data -----------------------------------------------------------
    returns_rows = _load_returns_matrix()
    hold_bands = _load_hold_bands()
    leak_ids = _load_leak_flags()
    cal = _load_calibration()

    # Extract run_id from the first returns row
    run_id = returns_rows[0].get("run_id", "unknown") if returns_rows else "unknown"

    # -- build event records, applying exclusions ----------------------------
    EXCLUDED_DOCS = set(EXCLUDED_EVENTS)
    events = []
    excluded_counts = {"worksheet": 0, "misattributed": 0, "timing": 0}

    for rrow in returns_rows:
        doc_id = rrow["document_id"]

        # Exclusion 1: worksheet contamination
        if doc_id in leak_ids:
            excluded_counts["worksheet"] += 1
            continue

        # Exclusion 2: misattributed
        if doc_id in EXCLUDED_DOCS:
            excluded_counts["misattributed"] += 1
            continue

        # Exclusion 3: timing-excluded
        if rrow.get("timing_excluded", "").strip() == "YES":
            excluded_counts["timing"] += 1
            continue

        crow = cal.get(doc_id)
        if crow is None:
            continue

        micro = _num(crow.get("micro_score"))
        macro = _num(crow.get("macro_score"))
        signal = crow.get("blend_predicted_signal_default", "").strip()

        # Recompute blended score for rank correlation
        if micro is not None:
            blended_score = blend_scores(micro, macro, None, None, DEFAULT_WEIGHTS)
        else:
            blended_score = None

        rec = {
            "document_id": doc_id,
            "ticker": rrow["ticker"],
            "report_date": rrow["report_date"],
            "signal": signal,
            "blended_score": blended_score,
        }
        for h in HORIZONS:
            col = RETURN_COLS[h]
            val = _num(rrow.get(col))
            rec[f"ret_{h}"] = val

        events.append(rec)

    n_clean = len(events)
    print(f"Exclusions: {excluded_counts}")
    print(f"Clean events: {n_clean}")

    # -- per-horizon analysis ------------------------------------------------
    results = []

    for h in HORIZONS:
        band = hold_bands.get(h)
        if band is None:
            print(f"WARNING: no hold band for horizon {h}, skipping")
            continue

        band_status = "pre-registered" if h == "overnight" else "recalibrated"

        # Traded events: BUY or SELL (not HOLD)
        traded_nets = []
        all_returns = []  # for rank correlation (all 229 events)
        all_scores = []

        graded_correct = 0
        graded_total = 0

        for ev in events:
            ret = ev.get(f"ret_{h}")
            if ret is None:
                continue

            bs = ev["blended_score"]
            if bs is not None:
                all_returns.append(ret)
                all_scores.append(bs)

            sig = ev["signal"]
            if sig in ("BUY", "SELL"):
                # Sign-adjust for SELL: if model says SELL, profit = -return
                if sig == "SELL":
                    net = -ret - COST_FRAC
                else:
                    net = ret - COST_FRAC
                traded_nets.append(net)

            # Grade accuracy against this horizon's band (on traded events)
            if sig in ("BUY", "SELL"):
                graded, truth = _grade_accuracy(ret, band)
                if graded:
                    graded_total += 1
                    if truth == sig:
                        graded_correct += 1

        traded_n = len(traded_nets)
        mean_net = float(np.mean(traded_nets)) if traded_n > 0 else 0.0
        accuracy = graded_correct / graded_total if graded_total > 0 else float("nan")

        # Spearman rank correlation on all clean events
        if len(all_returns) >= 3:
            rho, rho_p = sp_stats.spearmanr(all_scores, all_returns)
        else:
            rho, rho_p = float("nan"), float("nan")

        # Bootstrap CI on mean net per trade
        if traded_n >= 2:
            bs_result = bootstrap_trade_stats(traded_nets)
            ci_low = bs_result["mean_per_trade"]["ci_low"]
            ci_high = bs_result["mean_per_trade"]["ci_high"]
        else:
            ci_low, ci_high = float("nan"), float("nan")

        results.append({
            "horizon": h,
            "mean_net_per_trade": mean_net,
            "accuracy": accuracy,
            "graded_n": graded_total,
            "traded_n": traded_n,
            "rank_correlation": rho,
            "rho_pvalue": rho_p,
            "bootstrap_ci_low": ci_low,
            "bootstrap_ci_high": ci_high,
            "hold_band": band,
            "band_status": band_status,
        })

    # -- write CSV -----------------------------------------------------------
    fieldnames = [
        "horizon", "mean_net_per_trade", "accuracy", "graded_n", "traded_n",
        "rank_correlation", "rho_pvalue", "bootstrap_ci_low", "bootstrap_ci_high",
        "hold_band", "band_status",
    ]
    with open(OUT_CSV, "w", newline="") as f:
        f.write(f"# Extension 2: holding-period curve\n")
        f.write(f"# run_id: {run_id}\n")
        f.write(f"# model: DeepSeek (blend weights {DEFAULT_WEIGHTS})\n")
        f.write(f"# thresholds: hold_upper={DEFAULT_HOLD_UPPER}, hold_lower={DEFAULT_HOLD_LOWER}\n")
        f.write(f"# cost_bps: {COST_BPS}, short_borrow_bps: {SHORT_BORROW_BPS}\n")
        f.write(f"# clean_n: {n_clean} (excluded: {excluded_counts})\n")
        f.write(f"# generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# NOTE: overnight band (+/-2%) is PRE-REGISTERED and fixed.\n")
        f.write(f"#       All longer-horizon bands are RECALIBRATED and secondary.\n")
        f.write(f"#       Returns are NOT compounded across horizons; each is an\n")
        f.write(f"#       alternative version of the same trade.\n")
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nWrote {OUT_CSV}")

    # -- print table ---------------------------------------------------------
    print(f"\n{'='*110}")
    print(f"Extension 2: Holding-Period Curve (N={n_clean} clean events)")
    print(f"Overnight +/-2% band is PRE-REGISTERED. Longer-horizon bands are RECALIBRATED (secondary).")
    print(f"{'='*110}")
    print(f"{'Horizon':>10s}  {'Mean Net/Trade':>14s}  {'95% CI':>22s}  {'Accuracy':>9s}  "
          f"{'Graded N':>8s}  {'Traded N':>8s}  {'Rho':>7s}  {'p(rho)':>8s}  "
          f"{'Band':>7s}  {'Status':>14s}")
    print(f"{'-'*110}")
    for r in results:
        ci_str = f"[{r['bootstrap_ci_low']:+.4f}, {r['bootstrap_ci_high']:+.4f}]"
        print(f"{r['horizon']:>10s}  {r['mean_net_per_trade']:>+14.5f}  {ci_str:>22s}  "
              f"{r['accuracy']:>9.4f}  {r['graded_n']:>8d}  {r['traded_n']:>8d}  "
              f"{r['rank_correlation']:>7.3f}  {r['rho_pvalue']:>8.4f}  "
              f"{r['hold_band']:>7.4f}  {r['band_status']:>14s}")
    print(f"{'='*110}")

    # -- plot ----------------------------------------------------------------
    _plot_curve(results, n_clean, run_id, extra_signal_columns)

    return results


def _plot_curve(results, n_clean, run_id, extra_signal_columns=None):
    """Produce ext2_holding_curve.png with the model line (and future human line)."""
    fig, ax1 = plt.subplots(figsize=(10, 6))

    horizons = [r["horizon"] for r in results]
    x = np.arange(len(horizons))
    means = [r["mean_net_per_trade"] * 100 for r in results]  # percent
    ci_lo = [r["bootstrap_ci_low"] * 100 for r in results]
    ci_hi = [r["bootstrap_ci_high"] * 100 for r in results]

    # Model line with CI band
    ax1.plot(x, means, "o-", color="#2563eb", linewidth=2, markersize=8,
             label="Model (DeepSeek)", zorder=3)
    ax1.fill_between(x, ci_lo, ci_hi, alpha=0.2, color="#2563eb", zorder=2)

    # Placeholder for future human line
    if extra_signal_columns:
        colors = ["#dc2626", "#059669", "#d97706"]
        for i, (label, _) in enumerate(extra_signal_columns.items()):
            # Would compute per-horizon means for this signal and plot here
            pass

    ax1.axhline(0, color="gray", linestyle="--", linewidth=0.8, alpha=0.7)
    ax1.set_xticks(x)
    ax1.set_xticklabels(horizons)
    ax1.set_xlabel("Holding Horizon")
    ax1.set_ylabel("Mean Net Return per Trade (%)")
    ax1.set_title(
        f"Extension 2: Holding-Period Curve (N={n_clean} clean events)\n"
        f"Overnight band pre-registered; longer bands recalibrated (secondary)",
        fontsize=11,
    )

    # Annotate graded N on the plot
    for i, r in enumerate(results):
        ax1.annotate(
            f"n={r['graded_n']}",
            (x[i], means[i]),
            textcoords="offset points",
            xytext=(0, 12),
            ha="center",
            fontsize=8,
            color="#6b7280",
        )

    ax1.legend(loc="best", fontsize=9)
    ax1.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)
    print(f"Wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
