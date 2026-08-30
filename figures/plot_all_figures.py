#!/usr/bin/env python3
"""
Generate all figures for the ARP report.
READ-ONLY access to all project data; writes only to figures/.

Usage:
    python figures/plot_all_figures.py
"""

import os, sys, json, csv, glob, math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from matplotlib.patches import FancyBboxPatch
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from pathlib import Path
from datetime import date as _date, timedelta as _timedelta
from scipy.stats import spearmanr

# Add project root to path for blend imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
SUMMARY = ROOT / "outputs" / "global" / "summary"
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)

# ── Style ──────────────────────────────────────────────────────────────────
# Palette: navy, red (human arm only), mid grey.
# Red is reserved for the human arm. Exceptions: F5 loss/gain split and
# F11 BUY/SELL split use red for sign encoding with an in-figure note.
NAVY   = "#013B70"
RED    = "#D9261C"
GREY   = "#808080"
LTGREY = "#C0C0C0"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Nimbus Roman", "DejaVu Serif"],
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 8,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.spines.top": False,
    "axes.spines.right": False,
})

FIG_WIDTH_CM = 11
FIG_WIDTH = FIG_WIDTH_CM / 2.54  # inches

def save(fig, name):
    fig.savefig(FIGURES / f"{name}.pdf", format="pdf")
    fig.savefig(FIGURES / f"{name}.png", format="png")
    plt.close(fig)
    print(f"  ✓ {name}.pdf + .png")


def wilson_ci(k, n, z=1.645):
    """Wilson score 90% CI for a binomial proportion k/n."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0, centre - margin), min(1, centre + margin)


RNG_SEED = 20260709


def bootstrap_mean_ci(data, n_boot=10000, ci=90.0):
    rng = np.random.default_rng(RNG_SEED)
    data = np.asarray(data, dtype=float)
    n = len(data)
    boots = np.array([np.mean(rng.choice(data, size=n, replace=True)) for _ in range(n_boot)])
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(np.percentile(boots, lo)), float(np.percentile(boots, hi))


COST_BPS = 0.001  # 10bps round-trip as fraction


def compute_nets(events, cost=COST_BPS):
    """Compute net per-trade return for each traded event."""
    nets = []
    for e in events:
        signal = e.get("blend_predicted_signal_default", "HOLD")
        if signal == "HOLD":
            continue
        ret = float(e["ret_overnight"])
        if signal == "BUY":
            nets.append(ret - cost)
        else:
            nets.append(-ret - cost)
    return np.array(nets)


def get_traded_events(events):
    return [e for e in events if e.get("blend_predicted_signal_default", "HOLD") != "HOLD"]


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS: load data
# ═══════════════════════════════════════════════════════════════════════════

def load_returns_matrix():
    rows = []
    with open(SUMMARY / "returns_matrix.csv") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows

def load_calibration_csv():
    rows = []
    with open(SUMMARY / "global_outcome_calibration_phase2.csv") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows

def load_excluded_ids():
    ids = set()
    with open(SUMMARY / "supplementary_rescore_25.csv") as f:
        lines = [l for l in f if not l.startswith("#")]
        for r in csv.DictReader(lines):
            ids.add(r["document_id"])
    return ids

def clean_universe(returns_rows, calibration_rows):
    excluded_ws = load_excluded_ids()
    cal_map = {r["document_id"]: r for r in calibration_rows}
    clean = []
    for r in returns_rows:
        doc_id = r["document_id"]
        if r.get("timing_excluded", "NO") == "YES":
            continue
        if doc_id in excluded_ws:
            continue
        if doc_id == "SPOT_FQ1_2026":
            continue
        if doc_id in cal_map:
            clean.append({**r, **cal_map[doc_id]})
    return clean

def load_holding_curve():
    rows = []
    with open(SUMMARY / "ext2_holding_curve.csv") as f:
        headers = None
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            if line.startswith("horizon"):
                headers = line.strip().split(",")
                continue
            vals = line.strip().split(",")
            rows.append(dict(zip(headers, vals)))
    return rows

def load_latency_jsonl():
    latencies = []
    for jf in glob.glob(str(ROOT / "outputs" / "p2_*" / "logs" / "first_run_costs.jsonl")):
        with open(jf) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if rec.get("status") == "success" and rec.get("latency_seconds") is not None:
                        latencies.append(float(rec["latency_seconds"]))
                except (json.JSONDecodeError, KeyError):
                    pass
    return np.array(latencies)


# ═══════════════════════════════════════════════════════════════════════════
# F1: SAMPLE FUNNEL
# ═══════════════════════════════════════════════════════════════════════════

def plot_f1():
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.9))
    ax.set_xlim(0, 10)
    ax.set_ylim(1.5, 12.5)
    ax.axis("off")

    levels = [
        ("Total scored events", "N = 268", 10.5),
        ("Clean universe", "N = 233", 8.5),
        ("Model traded", "N = 146", 6.5),
        ("Graded (|ret| > 2%)", "N = 95", 4.5),
        ("Correct", "N = 62  (65.3%)", 2.5),
    ]

    box_h = 1.4
    for label, count, y in levels:
        w = 2.8 + (y / 10.5) * 3.5
        x = 4.5 - w / 2
        rect = FancyBboxPatch((x, y), w, box_h, boxstyle="round,pad=0.1",
                              facecolor=NAVY, edgecolor="white", alpha=0.85)
        ax.add_patch(rect)
        ax.text(4.5, y + box_h / 2 + 0.15, label, ha="center", va="center",
                color="white", fontsize=7, fontweight="bold")
        ax.text(4.5, y + box_h / 2 - 0.35, count, ha="center", va="center",
                color="white", fontsize=8)

    # Right-side exclusion annotations — shortened, well-spaced
    excl = [
        (11.2, "−25 worksheet"),
        (10.7, "−1 SPOT"),
        (10.2, "−9 timing"),
        (5.6, "−51 inside band"),
    ]
    for y, line in excl:
        ax.text(7.6, y, line, ha="left", va="center", fontsize=6.5, color=GREY)

    # HOLD limb — no arrow, position implies the branch
    ax.text(7.8, 7.2, "87 HOLD (37.3%)", ha="left", va="center",
            fontsize=6.5, color=GREY)
    ax.text(7.8, 6.4, "52 graded moves\nmissed", ha="left", va="center",
            fontsize=9, color=GREY, style="italic")

    save(fig, "F1_sample_funnel")


# ═══════════════════════════════════════════════════════════════════════════
# F2: RHO DECAY + MEAN NET DECAY (two stacked panels)
# ═══════════════════════════════════════════════════════════════════════════

def plot_f2():
    hc = load_holding_curve()
    x_vals = [0, 1, 3, 5, 10]

    rhos = [float(r["rank_correlation"]) for r in hc]
    pvals = [float(r["rho_pvalue"]) for r in hc]
    means = [float(r["mean_net_per_trade"]) * 100 for r in hc]
    ci_lo = [float(r["bootstrap_ci_low"]) * 100 for r in hc]
    ci_hi = [float(r["bootstrap_ci_high"]) * 100 for r in hc]

    # Fisher-z 90% CI for rho (computed in plot script)
    n = 233
    z_crit = 1.645
    rho_ci_lo, rho_ci_hi = [], []
    for rho in rhos:
        z = math.atanh(rho)
        se = 1.0 / math.sqrt(n - 3)
        rho_ci_lo.append(math.tanh(z - z_crit * se))
        rho_ci_hi.append(math.tanh(z + z_crit * se))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(FIG_WIDTH, FIG_WIDTH * 1.3),
                                    sharex=True, gridspec_kw={"hspace": 0.18})

    # Top panel: rho — no significance stars
    ax1.fill_between(x_vals, rho_ci_lo, rho_ci_hi, alpha=0.15, color=NAVY)
    ax1.plot(x_vals, rhos, "o-", color=NAVY, markersize=5, lw=1.5)
    ax1.axhline(0, color=GREY, lw=0.5, ls="--")
    for i, (x, rho, p) in enumerate(zip(x_vals, rhos, pvals)):
        ax1.annotate(f"{rho:.3f}", (x, rho), textcoords="offset points",
                     xytext=(0, 10), ha="center", fontsize=7, color=NAVY)
    ax1.set_ylabel("Spearman ρ")

    # Bottom panel: mean net per trade — labels directly above/below markers
    err_lo = [m - l for m, l in zip(means, ci_lo)]
    err_hi = [h - m for m, h in zip(means, ci_hi)]
    ax2.errorbar(x_vals, means, yerr=[err_lo, err_hi], fmt="s-",
                 color=NAVY, markersize=5, lw=1.5, capsize=3, ecolor=GREY)
    ax2.axhline(0, color=GREY, lw=0.5, ls="--")
    for i, (x, m) in enumerate(zip(x_vals, means)):
        offset_y = 10 if m >= 0 else -14
        ax2.annotate(f"{m:.2f}%", (x, m), textcoords="offset points",
                     xytext=(0, offset_y), ha="center", fontsize=7, color=NAVY)
    ax2.set_xlabel("Holding horizon (trading days)")
    ax2.set_ylabel("Mean net per trade (%)")

    ax2.set_xticks(x_vals)
    ax2.set_xticklabels(["ON", "1d", "3d", "5d", "10d"])

    save(fig, "F2_rho_decay")


# ═══════════════════════════════════════════════════════════════════════════
# F3: ACCURACY VS BAND WIDTH (0–5% bands)
# ═══════════════════════════════════════════════════════════════════════════

def plot_f3():
    ret_rows = load_returns_matrix()
    cal_rows = load_calibration_csv()
    events = clean_universe(ret_rows, cal_rows)

    bands = [0.0, 0.01, 0.02, 0.03, 0.04, 0.05]
    band_labels = ["0%", "1%", "2%", "3%", "4%", "5%"]

    results = []
    lower_means = []
    for band in bands:
        n_graded = 0
        n_correct = 0
        traded_nets = []
        for e in events:
            ret = float(e["ret_overnight"])
            signal = e.get("blend_predicted_signal_default", "HOLD")
            if signal == "HOLD":
                continue
            if abs(ret) > band:
                n_graded += 1
                if (signal == "BUY" and ret > 0) or (signal == "SELL" and ret < 0):
                    n_correct += 1
            # compute net for mean net lower panel (all traded events with |ret|>band)
            if abs(ret) > band:
                if signal == "BUY":
                    traded_nets.append(ret - COST_BPS)
                else:
                    traded_nets.append(-ret - COST_BPS)
        acc = n_correct / n_graded * 100 if n_graded > 0 else 0
        results.append((band, n_graded, n_correct, acc))
        lower_means.append(np.mean(traded_nets) * 100 if traded_nets else 0.0)

    n_graded = [r[1] for r in results]
    accuracies = [r[3] for r in results]

    print("F3 lower panel (mean net per trade at each band):", lower_means)

    fig, (ax1_top, ax1_bot) = plt.subplots(2, 1, figsize=(FIG_WIDTH, FIG_WIDTH * 1.2),
                                            sharex=True, gridspec_kw={"hspace": 0.12})
    ax2 = ax1_top.twinx()

    # Upper panel: accuracy bars + graded-n line
    bars = ax1_top.bar(range(len(bands)), accuracies, color=NAVY, alpha=0.8, width=0.6)
    ax1_top.set_ylabel("Directional accuracy (%)", color=NAVY)
    ax1_top.set_ylim(0, 80)

    ax2.plot(range(len(bands)), n_graded, "D-", color=GREY, markersize=5, lw=1.2)
    ax2.set_ylabel("Graded events (n)", color=GREY)
    ax2.set_ylim(30, 180)

    # Annotate accuracy above each bar; n carried by the right-hand axis
    for i, acc in enumerate(accuracies):
        ax1_top.text(i, acc + 0.5, f"{acc:.1f}%", ha="center", fontsize=9,
                     color=NAVY, fontweight="bold")

    # Pre-registered 2% band marker
    ax1_top.axvline(2, color=GREY, ls="--", lw=0.7, alpha=0.5)
    ax1_top.text(2.15, 78, "pre-\nregistered", fontsize=9, color=GREY,
                 style="italic", va="top")

    # Lower panel: mean net per trade at each band
    ax1_bot.bar(range(len(bands)), lower_means, color=NAVY, alpha=0.8, width=0.6)
    ax1_bot.set_ylim(0, max(lower_means) * 1.3 if max(lower_means) > 0 else 1)
    ax1_bot.set_ylabel("Mean net/trade (%)")
    for i, m in enumerate(lower_means):
        ax1_bot.text(i, m + 0.02, f"{m:.2f}%", ha="center", fontsize=8, color=NAVY)
    ax1_bot.axvline(2, color=GREY, ls="--", lw=0.7, alpha=0.5)

    ax1_bot.set_xticks(range(len(bands)))
    ax1_bot.set_xticklabels(band_labels)
    ax1_bot.set_xlabel("Grading band (±)")

    save(fig, "F3_band_sensitivity")


# ═══════════════════════════════════════════════════════════════════════════
# F4: SELECTIVITY VS COVERAGE
# ═══════════════════════════════════════════════════════════════════════════

def plot_f4():
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.75))

    metrics = ["Selectivity", "Coverage"]
    values = [65.3, 42.2]
    floors = [54.7, 54.4]
    denoms = [95, 147]
    correct = [62, 62]

    x = np.arange(len(metrics))
    w = 0.35

    ax.bar(x, values, w, color=NAVY, alpha=0.85)
    for i in range(len(metrics)):
        ax.plot([x[i] - w/2, x[i] + w/2], [floors[i], floors[i]],
                color=GREY, lw=2, ls="--")
        ax.text(x[i] + w/2 + 0.05, floors[i], f"floor {floors[i]:.1f}%",
                fontsize=7, color=GREY, va="center")

    for i in range(len(metrics)):
        ax.text(x[i], values[i] + 1.5,
                f"{correct[i]}/{denoms[i]} = {values[i]:.1f}%",
                ha="center", fontsize=8, color=NAVY, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontsize=9)
    ax.set_ylabel("Accuracy (%)")
    ax.set_ylim(0, 80)

    save(fig, "F4_selectivity_vs_coverage")


# ═══════════════════════════════════════════════════════════════════════════
# F5: RETURN DISTRIBUTION (open-ended tails)
# ═══════════════════════════════════════════════════════════════════════════

def plot_f5():
    ret_rows = load_returns_matrix()
    cal_rows = load_calibration_csv()
    events = clean_universe(ret_rows, cal_rows)

    nets = []
    for e in events:
        signal = e.get("blend_predicted_signal_default", "HOLD")
        if signal == "HOLD":
            continue
        ret = float(e["ret_overnight"])
        cost = 0.001
        if signal == "BUY":
            net = ret - cost
        else:
            net = -ret - cost
        nets.append(net * 100)

    nets = np.array(nets)

    bucket_defs = [
        ("< −10%",      lambda n: n < -10),
        ("−10\nto −5%", lambda n: -10 <= n < -5),
        ("−5\nto 0%",   lambda n: -5 <= n < 0),
        ("0\nto 5%",    lambda n: 0 <= n < 5),
        ("5\nto 10%",   lambda n: 5 <= n < 10),
        ("> +10%",      lambda n: n >= 10),
    ]

    counts = [sum(1 for n in nets if pred(n)) for _, pred in bucket_defs]
    labels = [b[0] for b in bucket_defs]

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.7))

    x_pos = np.arange(len(counts))
    # Diverging: red for loss, navy for gain. Note required by palette rule.
    colors = [RED if i < 3 else NAVY for i in range(len(counts))]
    ax.bar(x_pos, counts, color=colors, alpha=0.8, edgecolor="white", lw=0.5)

    for i, c in enumerate(counts):
        ax.text(i, c + 0.8, str(c), ha="center", fontsize=8, color=GREY)

    mean_net = np.mean(nets)
    median_net = np.median(nets)

    # Map mean/median to bar positions for vertical lines
    edges = [-10, -5, 0, 5, 10]
    centres = [0.5, 1.5, 2.5, 3.5, 4.5]
    mean_x = np.interp(mean_net, edges, centres)
    med_x = np.interp(median_net, edges, centres)
    ax.axvline(mean_x, color=NAVY, ls="--", lw=1.2, label=f"Mean = {mean_net:.2f}%")
    ax.axvline(med_x, color=GREY, ls="-.", lw=1.2, label=f"Median = {median_net:.2f}%")

    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_xlabel("Net return per trade (%)")
    ax.set_ylabel("Count")
    ax.legend(loc="upper right", fontsize=7)

    save(fig, "F5_return_distribution")


# ═══════════════════════════════════════════════════════════════════════════
# F6: BASELINE FRONTIER
# ═══════════════════════════════════════════════════════════════════════════

def plot_f6():
    methods = ["Majority\ndirection", "Loughran-\nMcDonald", "FinBERT", "Deployed\nmodel"]
    accs = [54.6, 15.1, 34.5, 42.9]
    ci_lo = [47.1, 10.1, 27.7, 35.3]
    ci_hi = [62.2, 21.0, 42.0, 50.4]
    n_correct = ["65/119", "18/119", "41/119", "51/119"]
    trade_rates = ["0/186", "59/186", "147/186", "111/186"]

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.75))

    x = np.arange(len(methods))
    colors = [GREY, GREY, GREY, NAVY]

    ax.bar(x, accs, 0.55, color=colors, alpha=0.85, edgecolor="white")

    for i in range(len(methods)):
        ax.plot([x[i], x[i]], [ci_lo[i], ci_hi[i]], color="black", lw=1.2)
        ax.plot([x[i]-0.08, x[i]+0.08], [ci_lo[i], ci_lo[i]], color="black", lw=1.2)
        ax.plot([x[i]-0.08, x[i]+0.08], [ci_hi[i], ci_hi[i]], color="black", lw=1.2)

    ax.axhline(54.6, color=GREY, ls="--", lw=0.8, alpha=0.6)

    for i in range(len(methods)):
        y_top = ci_hi[i] + 1.5
        ax.text(x[i], y_top, n_correct[i], ha="center", fontsize=7, fontweight="bold")
        ax.text(x[i], y_top + 4, f"{accs[i]:.1f}%", ha="center", fontsize=7)
        ax.text(x[i], -5, trade_rates[i],
                ha="center", fontsize=9, color=GREY)

    ax.set_xticks(x)
    ax.set_xticklabels(methods, fontsize=8)
    ax.set_ylabel("Coverage accuracy (%)")
    ax.set_ylim(-8, 75)

    save(fig, "F6_baseline_frontier")


# ═══════════════════════════════════════════════════════════════════════════
# F7: MDE VS OBSERVED DIFFERENCE (6 comparisons from Table 3)
# ═══════════════════════════════════════════════════════════════════════════

def plot_f7():
    comparisons = [
        # (label, observed_pp, mde_pp)
        ("Selectivity\nvs floor\n(n = 95)",            10.5, 10.8),
        ("Extension vs\nfrozen 65.3%\n(n = 14)",       6.2, 31.6),
        ("Section\nablation\n(n = 45–53)",             -6.8, 12.0),
        ("Model vs\nhuman dir.\n(n = 76)",              2.6, 23.0),
        ("Walk-forward\nOOS vs floor\n(n = 25)",       14.6, 30.0),
        ("Cross-issuer\nsubset\n(n = 52)",             11.5, 21.0),
    ]

    labels = [c[0] for c in comparisons]
    observed = [c[1] for c in comparisons]
    mde = [c[2] for c in comparisons]

    fig, ax = plt.subplots(figsize=(FIG_WIDTH * 1.35, FIG_WIDTH * 0.85))

    x = np.arange(len(comparisons))

    for i in range(len(comparisons)):
        ax.fill_between([i - 0.3, i + 0.3], [-mde[i], -mde[i]], [mde[i], mde[i]],
                        color=LTGREY, alpha=0.3)
        ax.plot([i - 0.3, i + 0.3], [mde[i], mde[i]], color=GREY, lw=0.7, ls=":")
        ax.plot([i - 0.3, i + 0.3], [-mde[i], -mde[i]], color=GREY, lw=0.7, ls=":")

    ax.scatter(x, observed, c=NAVY, s=60, zorder=5, marker="D")

    for i, (obs, m) in enumerate(zip(observed, mde)):
        offset = 8 if obs >= 0 else -12
        ax.annotate(f"{obs:+.1f}pp", (i, obs), textcoords="offset points",
                    xytext=(0, offset), ha="center", fontsize=7, color=NAVY)

    ax.axhline(0, color="black", lw=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Effect size (pp)")

    legend_elements = [
        Line2D([0], [0], marker="D", color="w", markerfacecolor=NAVY,
               markersize=7, label="Observed effect"),
        plt.Rectangle((0,0), 1, 1, fc=LTGREY, alpha=0.3,
                       label="±MDE (80% power, α = 0.10)")
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=6.5)

    save(fig, "F7_mde_vs_observed")


# ═══════════════════════════════════════════════════════════════════════════
# F8: BUY/SELL ASYMMETRY — navy = model, red = human
# ═══════════════════════════════════════════════════════════════════════════

def plot_f8():
    labels = ["LLM\nBUY", "LLM\nSELL", "Human\nBUY", "Human\nSELL"]
    correct = [20, 26, 27, 17]
    ns = [36, 40, 53, 23]
    accs = [c / n * 100 for c, n in zip(correct, ns)]
    base_buy = 43.4
    base_sell = 56.6

    cis = [wilson_ci(c, n) for c, n in zip(correct, ns)]
    ci_lo = [lo * 100 for lo, _ in cis]
    ci_hi = [hi * 100 for _, hi in cis]
    err_lo = [a - lo for a, lo in zip(accs, ci_lo)]
    err_hi = [hi - a for a, hi in zip(accs, ci_hi)]

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.82))

    x = np.arange(4)
    colors = [NAVY, NAVY, RED, RED]

    ax.bar(x, accs, 0.55, color=colors, alpha=0.85, edgecolor="white")
    ax.errorbar(x, accs, yerr=[err_lo, err_hi], fmt="none", ecolor="black",
                capsize=3, lw=1)

    for i in range(4):
        ax.text(x[i], ci_hi[i] + 3, f"{correct[i]}/{ns[i]}\n{accs[i]:.1f}%",
                ha="center", fontsize=7, fontweight="bold")

    ax.axhline(50, color=GREY, ls="--", lw=0.7, label="50% (coin flip)")
    ax.axhline(base_buy, color=GREY, ls=":", lw=0.8, alpha=0.6,
               label=f"BUY base rate {base_buy}%")
    ax.axhline(base_sell, color=GREY, ls="-.", lw=0.8, alpha=0.6,
               label=f"SELL base rate {base_sell}%")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Sign accuracy (%)")
    ax.set_ylim(0, 95)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18),
              ncol=3, fontsize=6.5, frameon=False)

    save(fig, "F8_buy_sell_asymmetry")


# ═══════════════════════════════════════════════════════════════════════════
# F9: SECTION ABLATION
# ═══════════════════════════════════════════════════════════════════════════

def plot_f9():
    arms = ["Full bundle", "Press release", "Prepared\nremarks", "Q&A only"]
    accs = [68.1, 64.9, 63.4, 68.4]
    cost_per_correct = [0.0358, 0.0225, 0.0208, 0.0229]
    n_graded = [47, 37, 41, 38]
    n_correct = [32, 24, 26, 26]
    agreement = [100.0, 72.3, 85.7, 71.4]
    mde_pp = 12.0

    fig, ax1 = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.75))
    ax2 = ax1.twinx()

    x = np.arange(4)
    w = 0.35

    ax1.bar(x - w/2, accs, w, color=NAVY, alpha=0.8, label="Accuracy (%)")

    # MDE band — labelled in legend
    ax1.fill_between([-0.5, 3.5], [68.1 - mde_pp]*2, [68.1 + mde_pp]*2,
                     color=LTGREY, alpha=0.15, label=f"±{mde_pp:.0f}pp MDE")
    ax1.legend(loc="upper right", fontsize=6.5)

    # Cost bars in grey
    ax2.bar(x + w/2, [c * 100 for c in cost_per_correct], w,
            color=GREY, alpha=0.6)
    ax2.set_ylabel("Cost per correct call (¢)", color=GREY)

    for i in range(4):
        ax1.text(x[i] - w/2, accs[i] + 1, f"{n_correct[i]}/{n_graded[i]}\n{accs[i]:.1f}%",
                ha="center", fontsize=6.5, color=NAVY)
        ax2.text(x[i] + w/2, cost_per_correct[i] * 100 + 0.2,
                f"{cost_per_correct[i]*100:.1f}¢", ha="center", fontsize=6.5, color=GREY)
        ax1.text(x[i], -6, f"agr: {agreement[i]:.0f}%", ha="center",
                fontsize=6.5, color=GREY)

    ax1.set_xticks(x)
    ax1.set_xticklabels(arms, fontsize=8)
    ax1.set_ylabel("Selectivity accuracy (%)", color=NAVY)
    ax1.set_ylim(-10, 90)
    ax2.set_ylim(0, 5)

    save(fig, "F9_section_ablation")


# ═══════════════════════════════════════════════════════════════════════════
# F10: LATENCY DISTRIBUTION
# ═══════════════════════════════════════════════════════════════════════════

def plot_f10():
    latencies = load_latency_jsonl()
    if len(latencies) == 0:
        print("  ✗ F10: no latency data found")
        return

    clip = 60
    clipped = latencies[latencies <= clip]
    n_outliers = len(latencies) - len(clipped)

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.7))

    bins = np.arange(0, clip + 2, 2)
    ax.hist(clipped, bins=bins, color=NAVY, alpha=0.8, edgecolor="white", lw=0.3)

    med = np.median(latencies)
    mean = np.mean(latencies)
    q1, q3 = np.percentile(latencies, [25, 75])

    ax.axvline(med, color=NAVY, ls="-", lw=1.2, label=f"Median = {med:.1f}s")
    ax.axvline(mean, color=GREY, ls=":", lw=1.2, label=f"Mean = {mean:.1f}s")

    ax.set_xlabel("Latency (seconds)")
    ax.set_ylabel("Count")
    ax.legend(loc="upper right", fontsize=7)

    save(fig, "F10_latency_distribution")


# ═══════════════════════════════════════════════════════════════════════════
# F11: BLENDED SCORE VS OVERNIGHT RETURN SCATTER
# ═══════════════════════════════════════════════════════════════════════════

def plot_f11():
    from blend import blend_scores, DEFAULT_WEIGHTS

    ret_rows = load_returns_matrix()
    cal_rows = load_calibration_csv()
    excluded_ws = load_excluded_ids()
    cal_map = {r["document_id"]: r for r in cal_rows}

    scores, rets, signals = [], [], []
    for r in ret_rows:
        doc = r["document_id"]
        if r.get("timing_excluded", "NO") == "YES": continue
        if doc in excluded_ws: continue
        if doc == "SPOT_FQ1_2026": continue
        if doc not in cal_map: continue

        c = cal_map[doc]
        micro_s = c.get("micro_score", "")
        macro_s = c.get("macro_score", "")
        if not micro_s:
            continue
        micro = float(micro_s)
        macro = float(macro_s) if macro_s else None

        blended = blend_scores(micro, macro, None, None, DEFAULT_WEIGHTS)
        scores.append(blended)
        rets.append(float(r["ret_overnight"]) * 100)
        signals.append(c.get("blend_predicted_signal_default", "HOLD"))

    scores = np.array(scores)
    rets = np.array(rets)

    rho, p = spearmanr(scores, rets)
    assert abs(rho - 0.23600083738353303) < 1e-8, f"rho mismatch: {rho}"

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.85))

    # BUY/SELL/HOLD use navy/red/grey for signal direction (not arm).
    colors_map = {"BUY": NAVY, "SELL": RED, "HOLD": GREY}
    for sig_val in ["HOLD", "BUY", "SELL"]:
        mask = np.array([s == sig_val for s in signals])
        ax.scatter(scores[mask], rets[mask], c=colors_map[sig_val], s=12,
                   alpha=0.5, label=sig_val, edgecolors="none")

    ax.axhline(0, color=GREY, lw=0.5, ls="--")
    ax.axvline(0, color=GREY, lw=0.5, ls="--")
    ax.axvline(0.25, color=GREY, lw=0.8, ls="--", alpha=0.7)
    ax.axvline(-0.05, color=GREY, lw=0.8, ls="--", alpha=0.7)

    ax.axhline(2, color=LTGREY, lw=0.5, ls=":")
    ax.axhline(-2, color=LTGREY, lw=0.5, ls=":")
    ax.text(0.72, 2.5, "±2% band", fontsize=6.5, color=LTGREY,
            transform=ax.get_yaxis_transform())

    # OLS trend line — grey
    z = np.polyfit(scores, rets, 1)
    x_line = np.linspace(scores.min(), scores.max(), 100)
    ax.plot(x_line, np.polyval(z, x_line), color=GREY, lw=1.2, ls="--", alpha=0.7)

    ax.set_xlabel("Blended score (recomputed via blend_scores())")
    ax.set_ylabel("Overnight return (%)")
    ax.legend(loc="upper left", fontsize=7, framealpha=0.8)

    save(fig, "F11_score_vs_return")


# ═══════════════════════════════════════════════════════════════════════════
# F12: CONFUSION MATRIX (human vs LLM, 3×3) — navy ramp
# ═══════════════════════════════════════════════════════════════════════════

def plot_f12():
    matrix = np.array([
        [32, 43, 21],  # Human BUY
        [ 6, 14, 20],  # Human HOLD
        [ 4, 12, 19],  # Human SELL
    ])

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.9))

    # Navy ramp: near-white to full navy
    navy_cmap = LinearSegmentedColormap.from_list("navy_ramp", ["#F0F4F8", NAVY])
    im = ax.imshow(matrix, cmap=navy_cmap, aspect="auto")

    cell_labels = ["BUY", "HOLD", "SELL"]

    ax.set_xticks(range(3))
    ax.set_xticklabels(cell_labels, fontsize=9)
    ax.set_yticks(range(3))
    ax.set_yticklabels(cell_labels, fontsize=9)
    ax.set_xlabel("LLM decision", labelpad=8)
    ax.set_ylabel("Human decision")

    for i in range(3):
        for j in range(3):
            val = matrix[i, j]
            pct = val / 171 * 100
            color = "white" if val > 30 else "black"
            ax.text(j, i, f"{val}\n({pct:.0f}%)", ha="center", va="center",
                    fontsize=9, color=color, fontweight="bold")

    # Row totals — labelled, right margin
    ax.text(3.6, -0.5, "Total", ha="center", va="center", fontsize=7, color=GREY,
            fontweight="bold")
    for i in range(3):
        ax.text(3.6, i, f"{matrix[i,:].sum()}", ha="center", va="center",
                fontsize=8, color=GREY)

    # Column totals — labelled, bottom margin (inside axes limits)
    ax.text(-0.7, 3.3, "Total", ha="center", va="center", fontsize=7, color=GREY,
            fontweight="bold")
    for j in range(3):
        ax.text(j, 3.3, f"{matrix[:,j].sum()}", ha="center", va="center",
                fontsize=8, color=GREY)

    save(fig, "F12_confusion_matrix")


# ═══════════════════════════════════════════════════════════════════════════
# F13: ACCURACY BY MOVE MAGNITUDE — all navy, hatching on thin bucket
# ═══════════════════════════════════════════════════════════════════════════

def plot_f13():
    ret_rows = load_returns_matrix()
    cal_rows = load_calibration_csv()
    events = clean_universe(ret_rows, cal_rows)

    buckets = [(0.02, 0.05, "2–5%"), (0.05, 0.10, "5–10%"), (0.10, 1.0, ">10%")]

    results = []
    for lo, hi, label in buckets:
        n_graded = 0
        n_correct = 0
        for e in events:
            signal = e.get("blend_predicted_signal_default", "HOLD")
            if signal == "HOLD":
                continue
            ret = float(e["ret_overnight"])
            abs_ret = abs(ret)
            if abs_ret > lo and (abs_ret <= hi if hi < 1.0 else True):
                n_graded += 1
                if (signal == "BUY" and ret > 0) or (signal == "SELL" and ret < 0):
                    n_correct += 1
        acc = n_correct / n_graded * 100 if n_graded > 0 else 0
        results.append((label, n_graded, n_correct, acc))

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.65))

    x = np.arange(len(results))
    labels_b = [r[0] for r in results]
    accs = [r[3] for r in results]
    ns = [r[1] for r in results]
    corrects = [r[2] for r in results]

    bars = ax.bar(x, accs, 0.5, color=NAVY, alpha=0.8)
    for i, bar in enumerate(bars):
        if ns[i] < 20:
            bar.set_hatch("///")
            bar.set_edgecolor("white")

    for i in range(len(results)):
        ax.text(x[i], accs[i] + 1.5, f"{corrects[i]}/{ns[i]}\n{accs[i]:.1f}%",
                ha="center", fontsize=8, fontweight="bold")

    ax.axhline(50, color=GREY, ls="--", lw=0.7, label="50% baseline")
    ax.set_xticks(x)
    ax.set_xticklabels(labels_b, fontsize=9)
    ax.set_xlabel("Absolute overnight return")
    ax.set_ylabel("Directional accuracy (%)")
    ax.set_ylim(0, 100)
    ax.legend(loc="upper left", fontsize=7)

    save(fig, "F13_accuracy_by_magnitude")


# ═══════════════════════════════════════════════════════════════════════════
# F14: COST SENSITIVITY
# ═══════════════════════════════════════════════════════════════════════════

def plot_f14():
    ret_rows = load_returns_matrix()
    cal_rows = load_calibration_csv()
    events = clean_universe(ret_rows, cal_rows)
    traded = get_traded_events(events)

    rets_buy_sell = []
    for e in traded:
        sig = e["blend_predicted_signal_default"]
        ret = float(e["ret_overnight"])
        if sig == "BUY":
            rets_buy_sell.append(("BUY", ret))
        else:
            rets_buy_sell.append(("SELL", ret))

    # Dense 1bp point estimates
    cost_range_dense = np.arange(0, 251, 1)
    means_dense = []
    for cost_bps in cost_range_dense:
        cost = cost_bps / 10000.0
        nets = []
        for sig, ret in rets_buy_sell:
            if sig == "BUY":
                nets.append(ret - cost)
            else:
                nets.append(-ret - cost)
        means_dense.append(np.mean(nets) * 100)

    # Bootstrap CI at every 5 bps
    cost_range_ci = np.arange(0, 251, 5)
    ci_lo_pts = []
    ci_hi_pts = []
    for cost_bps in cost_range_ci:
        cost = cost_bps / 10000.0
        nets = np.array([
            (ret - cost) if sig == "BUY" else (-ret - cost)
            for sig, ret in rets_buy_sell
        ]) * 100
        lo, hi = bootstrap_mean_ci(nets, n_boot=5000, ci=90.0)
        ci_lo_pts.append(lo)
        ci_hi_pts.append(hi)

    # Interpolate CI to dense grid
    ci_lo_dense = np.interp(cost_range_dense, cost_range_ci, ci_lo_pts)
    ci_hi_dense = np.interp(cost_range_dense, cost_range_ci, ci_hi_pts)

    # Find zero crossings by linear interpolation
    def find_zero_crossing(x, y):
        for i in range(len(y) - 1):
            if y[i] >= 0 and y[i+1] < 0:
                # linear interp
                frac = y[i] / (y[i] - y[i+1])
                return x[i] + frac * (x[i+1] - x[i])
        return None

    mean_zero = find_zero_crossing(cost_range_dense, means_dense)
    ci_lower_zero = find_zero_crossing(cost_range_dense, ci_lo_dense)
    val_at_10bps = float(np.interp(10, cost_range_dense, means_dense))

    print(f"F14 crossing: mean zero at {mean_zero:.1f}bps, CI lower zero at {ci_lower_zero:.1f}bps, 10bps point={val_at_10bps:.4f}%")

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.75))

    ax.fill_between(cost_range_dense, ci_lo_dense, ci_hi_dense, alpha=0.18, color=NAVY)
    ax.plot(cost_range_dense, means_dense, color=NAVY, lw=1.5, label="Mean net/trade")
    ax.axhline(0, color=GREY, lw=0.6, ls="--")

    # Vertical marker lines
    ax.axvline(10, color=GREY, lw=0.9, ls="--", alpha=0.85)
    ax.text(10, ax.get_ylim()[0] if ax.get_ylim()[0] != 0 else -0.1,
            "10bps\n(live)", ha="center", va="top", fontsize=7.5, color=GREY)

    if mean_zero is not None:
        ax.axvline(mean_zero, color=NAVY, lw=0.9, ls=":", alpha=0.75)
        ax.text(mean_zero, min(means_dense) * 0.3,
                f"{mean_zero:.0f}bps\n(mean=0)", ha="center", va="top", fontsize=7.5, color=NAVY)

    if ci_lower_zero is not None:
        ax.axvline(ci_lower_zero, color=GREY, lw=0.9, ls=":", alpha=0.75)
        ax.text(ci_lower_zero, min(means_dense) * 0.7,
                f"{ci_lower_zero:.0f}bps\n(CI lo=0)", ha="center", va="top", fontsize=7.5, color=GREY)

    ax.set_xlabel("Round-trip cost (bps)")
    ax.set_ylabel("Mean net per trade (%)")
    ax.legend(fontsize=7)

    save(fig, "F14_cost_sensitivity")


# ═══════════════════════════════════════════════════════════════════════════
# F15: MEAN OVERNIGHT RETURN BY SCORE DECILE
# ═══════════════════════════════════════════════════════════════════════════

def plot_f15():
    from blend import blend_scores, DEFAULT_WEIGHTS

    ret_rows = load_returns_matrix()
    cal_rows = load_calibration_csv()
    events = clean_universe(ret_rows, cal_rows)

    scores_list = []
    rets_list = []
    for e in events:
        micro_s = e.get("micro_score", "")
        macro_s = e.get("macro_score", "")
        if not micro_s:
            continue
        micro = float(micro_s)
        macro = float(macro_s) if macro_s else None
        blended = blend_scores(micro, macro, None, None, DEFAULT_WEIGHTS)
        scores_list.append(blended)
        rets_list.append(float(e["ret_overnight"]) * 100)

    scores_arr = np.array(scores_list)
    rets_arr = np.array(rets_list)

    # Decile edges
    decile_edges = np.quantile(scores_arr, np.linspace(0, 1, 11))
    # Use digitize but clip to 1-10
    bin_idx = np.digitize(scores_arr, decile_edges[1:-1])  # 0-9
    # Force max to 9
    bin_idx = np.clip(bin_idx, 0, 9)

    decile_means = []
    decile_ns = []
    decile_ci_lo = []
    decile_ci_hi = []
    print("F15 decile means (n, mean_overnight_pct):")
    for d in range(10):
        mask = bin_idx == d
        sub = rets_arr[mask]
        n = len(sub)
        m = np.mean(sub) if n > 0 else 0.0
        decile_means.append(m)
        decile_ns.append(n)
        lo, hi = bootstrap_mean_ci(sub, n_boot=5000, ci=90.0) if n > 1 else (m, m)
        decile_ci_lo.append(lo)
        decile_ci_hi.append(hi)
        print(f"  decile {d+1}: n={n}, mean={m:.4f}%")

    # Check monotonic
    is_mono = all(decile_means[i] <= decile_means[i+1] for i in range(9))
    print(f"F15 monotonic: {is_mono}")

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.75))

    x = np.arange(10)
    bars = ax.bar(x, decile_means, color=NAVY, alpha=0.8, width=0.65)
    err_lo = [m - lo for m, lo in zip(decile_means, decile_ci_lo)]
    err_hi = [hi - m for m, hi in zip(decile_means, decile_ci_hi)]
    ax.errorbar(x, decile_means, yerr=[err_lo, err_hi], fmt="none",
                ecolor="black", capsize=3, lw=0.8)

    ax.axhline(0, color=GREY, lw=0.6, ls="--")

    for i, (m, n) in enumerate(zip(decile_means, decile_ns)):
        offset = 0.15 if m >= 0 else -0.35
        ax.text(i, m + offset, f"{m:.2f}%\n(n={n})", ha="center", fontsize=7, color=NAVY)

    ax.set_xticks(x)
    ax.set_xticklabels([f"D{i+1}" for i in range(10)], fontsize=8)
    ax.set_xlabel("Score decile (low to high)")
    ax.set_ylabel("Mean overnight return (%)")

    save(fig, "F15_decile_returns")


# ═══════════════════════════════════════════════════════════════════════════
# F16: SORTED PER-TRADE RETURNS
# ═══════════════════════════════════════════════════════════════════════════

def plot_f16():
    ret_rows = load_returns_matrix()
    cal_rows = load_calibration_csv()
    events = clean_universe(ret_rows, cal_rows)

    nets = compute_nets(events) * 100
    nets_sorted = np.sort(nets)

    loss_count = int(np.sum(nets_sorted < 0))
    median_val = float(np.median(nets_sorted))
    mean_val = float(np.mean(nets_sorted))
    print(f"F16 loss count: {loss_count} of 146")
    print(f"F16 median: {median_val:.4f}%, mean: {mean_val:.4f}%")

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.75))

    x = np.arange(1, len(nets_sorted) + 1)
    colors = [RED if n < 0 else NAVY for n in nets_sorted]
    ax.bar(x, nets_sorted, color=colors, width=1.0, edgecolor="none")

    ax.axhline(0, color=GREY, lw=0.6, ls="--")
    ax.axhline(median_val, color=GREY, lw=1.0, ls="-.", label=f"Median = {median_val:.2f}%")
    ax.axhline(mean_val, color=NAVY, lw=1.0, ls="--", label=f"Mean = {mean_val:.2f}%")

    ax.set_xlabel("Trade rank (worst to best)")
    ax.set_ylabel("Net return (%)")
    ax.legend(fontsize=7, loc="upper left")

    save(fig, "F16_sorted_returns")


# ═══════════════════════════════════════════════════════════════════════════
# F17: MODEL VS ALWAYS-BUY
# ═══════════════════════════════════════════════════════════════════════════

def plot_f17():
    ret_rows = load_returns_matrix()
    cal_rows = load_calibration_csv()
    events = clean_universe(ret_rows, cal_rows)
    traded = get_traded_events(events)

    model_nets = []
    always_buy_nets = []
    for e in traded:
        sig = e["blend_predicted_signal_default"]
        ret = float(e["ret_overnight"])
        cost = COST_BPS
        if sig == "BUY":
            model_nets.append((ret - cost) * 100)
        else:
            model_nets.append((-ret - cost) * 100)
        always_buy_nets.append((ret - cost) * 100)

    model_nets = np.array(model_nets)
    always_buy_nets = np.array(always_buy_nets)

    model_mean = float(np.mean(model_nets))
    model_lo, model_hi = bootstrap_mean_ci(model_nets, n_boot=10000, ci=90.0)
    ab_mean = float(np.mean(always_buy_nets))
    ab_lo, ab_hi = bootstrap_mean_ci(always_buy_nets, n_boot=10000, ci=90.0)

    print(f"F17 model mean: {model_mean:.4f}%, CI [{model_lo:.4f}%, {model_hi:.4f}%]")
    print(f"F17 always-buy mean: {ab_mean:.4f}%, CI [{ab_lo:.4f}%, {ab_hi:.4f}%]")

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.65))

    labels = ["Model\n(146 trades)", "Always-BUY\n(146 events)"]
    means = [model_mean, ab_mean]
    ci_los = [model_lo, ab_lo]
    ci_his = [model_hi, ab_hi]
    bar_colors = [NAVY, GREY]

    x = np.arange(2)
    bars = ax.bar(x, means, color=bar_colors, alpha=0.85, width=0.45)
    err_lo = [m - lo for m, lo in zip(means, ci_los)]
    err_hi = [hi - m for m, hi in zip(means, ci_his)]
    ax.errorbar(x, means, yerr=[err_lo, err_hi], fmt="none",
                ecolor="black", capsize=4, lw=1.2)

    ax.axhline(0, color=GREY, lw=0.6, ls="--")

    for i, (m, lo, hi) in enumerate(zip(means, ci_los, ci_his)):
        offset = 0.05 if m >= 0 else -0.15
        ax.text(i, hi + 0.05, f"{m:.3f}%", ha="center", fontsize=8, color=bar_colors[i])

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Mean net per trade (%)")

    save(fig, "F17_model_vs_always_buy")


# ═══════════════════════════════════════════════════════════════════════════
# F18: INFORMATION RATIO VS T-STATISTIC
# ═══════════════════════════════════════════════════════════════════════════

def plot_f18():
    # Hardcoded from per_trade_stats.csv
    sets = ["146", "32", "178"]
    ir_vals = [0.2840, 0.2407, 0.2764]
    t_vals = [3.4322, 1.3618, 3.6878]

    fig, ax1 = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.7))
    ax2 = ax1.twinx()

    x = np.arange(len(sets))
    w = 0.32

    bars1 = ax1.bar(x - w/2, ir_vals, w, color=NAVY, alpha=0.85, label="Info ratio (IR)")
    bars2 = ax2.bar(x + w/2, t_vals, w, color=GREY, alpha=0.75, label="t-statistic")

    ax1.set_ylabel("Information ratio (IR)", color=NAVY)
    ax2.set_ylabel("t-statistic", color=GREY)

    ax1.set_xticks(x)
    ax1.set_xticklabels(sets, fontsize=9)
    ax1.set_xlabel("Trade count (n)")
    ax1.set_ylim(0, max(ir_vals) * 1.4)
    ax2.set_ylim(0, max(t_vals) * 1.4)

    # Combined legend
    handles = [bars1, bars2]
    labels_leg = ["IR (left axis)", "t-statistic (right axis)"]
    ax1.legend(handles, labels_leg, fontsize=7, loc="upper left")

    save(fig, "F18_ir_vs_tstat")


# ═══════════════════════════════════════════════════════════════════════════
# F19: ORDERED CUMULATIVE SUM
# ═══════════════════════════════════════════════════════════════════════════

def plot_f19():
    ret_rows = load_returns_matrix()
    cal_rows = load_calibration_csv()
    events = clean_universe(ret_rows, cal_rows)
    traded = get_traded_events(events)

    # Sort by report_date ascending (ISO strings sort correctly)
    traded_sorted = sorted(traded, key=lambda e: e["report_date"])

    cost_live = 0.001      # 10bps
    cost_grey = 0.019617   # 196.17bps

    nets_live = []
    nets_grey = []
    for e in traded_sorted:
        sig = e["blend_predicted_signal_default"]
        ret = float(e["ret_overnight"])
        if sig == "BUY":
            nets_live.append((ret - cost_live) * 100)
            nets_grey.append((ret - cost_grey) * 100)
        else:
            nets_live.append((-ret - cost_live) * 100)
            nets_grey.append((-ret - cost_grey) * 100)

    cum_live = np.cumsum(nets_live)
    cum_grey = np.cumsum(nets_grey)

    print(f"F19 terminal navy (10bps): {cum_live[-1]:.2f}%")
    print(f"F19 terminal grey (196.17bps): {cum_grey[-1]:.2f}%")

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.7))

    x = np.arange(1, len(cum_live) + 1)
    ax.plot(x, cum_live, color=NAVY, lw=1.5, label="10bps cost")
    ax.plot(x, cum_grey, color=GREY, lw=1.2, ls="--", label="196.17bps cost")
    ax.axhline(0, color=GREY, lw=0.5, ls=":")

    ax.set_xlabel("Trade sequence (date-sorted)")
    ax.set_ylabel("Summed net return (%)")
    ax.legend(fontsize=7, loc="upper left")

    save(fig, "F19_cumulative_sum")


# ═══════════════════════════════════════════════════════════════════════════
# F20: MEAN NET BY MOVE-SIZE BUCKET
# ═══════════════════════════════════════════════════════════════════════════

def plot_f20():
    ret_rows = load_returns_matrix()
    cal_rows = load_calibration_csv()
    events = clean_universe(ret_rows, cal_rows)
    traded = get_traded_events(events)

    buckets = [
        (0.02, 0.05, "2–5%"),
        (0.05, 0.10, "5–10%"),
        (0.10, float("inf"), ">10%"),
    ]

    bucket_results = []
    for lo, hi, label in buckets:
        nets = []
        for e in traded:
            ret = float(e["ret_overnight"])
            abs_ret = abs(ret)
            if abs_ret > lo and abs_ret <= hi:
                sig = e["blend_predicted_signal_default"]
                if sig == "BUY":
                    nets.append((ret - COST_BPS) * 100)
                else:
                    nets.append((-ret - COST_BPS) * 100)
        n = len(nets)
        m = np.mean(nets) if nets else 0.0
        bucket_results.append((label, n, m))

    ns = [r[1] for r in bucket_results]
    ms = [r[2] for r in bucket_results]
    labels_b = [r[0] for r in bucket_results]
    print(f"F20 bucket means: 2-5% n={ns[0]} mean={ms[0]:.4f}%, 5-10% n={ns[1]} mean={ms[1]:.4f}%, >10% n={ns[2]} mean={ms[2]:.4f}%")

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.65))

    x = np.arange(3)
    bars = ax.bar(x, ms, color=NAVY, alpha=0.85, width=0.5)
    # Hatch the n<20 bucket (>10%)
    for i, (bar, n) in enumerate(zip(bars, ns)):
        if n < 20:
            bar.set_hatch("///")
            bar.set_edgecolor("white")

    for i, (m, n) in enumerate(zip(ms, ns)):
        ax.text(i, m + 0.03, f"{m:.2f}%\n(n={n})", ha="center", fontsize=8, color=NAVY)

    ax.set_xticks(x)
    ax.set_xticklabels(labels_b, fontsize=9)
    ax.set_xlabel("Absolute overnight return")
    ax.set_ylabel("Mean net per trade (%)")
    ax.set_ylim(0, max(ms) * 1.4 if max(ms) > 0 else 1)

    save(fig, "F20_net_by_bucket")


# ═══════════════════════════════════════════════════════════════════════════
# F21: MEAN NET BY BAND WIDTH
# ═══════════════════════════════════════════════════════════════════════════

def plot_f21():
    ret_rows = load_returns_matrix()
    cal_rows = load_calibration_csv()
    events = clean_universe(ret_rows, cal_rows)
    traded = get_traded_events(events)

    bands = [0.00, 0.01, 0.02, 0.03, 0.04, 0.05]
    expected_ns = [145, 120, 95, 71, 61, 52]

    band_results = []
    print("F21 means:", end=" ")
    for band, exp_n in zip(bands, expected_ns):
        nets = []
        for e in traded:
            ret = float(e["ret_overnight"])
            if abs(ret) > band:
                sig = e["blend_predicted_signal_default"]
                if sig == "BUY":
                    nets.append((ret - COST_BPS) * 100)
                else:
                    nets.append((-ret - COST_BPS) * 100)
        n = len(nets)
        m = np.mean(nets) if nets else 0.0
        band_results.append((band, n, m))
        print(f"band={band*100:.0f}% n={n} mean={m:.4f}%", end="; ")
    print()

    ns = [r[1] for r in band_results]
    ms = [r[2] for r in band_results]
    tick_labels = [f"{int(b*100)}%\n(n={n})" for b, n in zip(bands, ns)]

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.75))

    x = np.arange(len(bands))
    ax.bar(x, ms, color=NAVY, alpha=0.85, width=0.6)

    for i, m in enumerate(ms):
        ax.text(i, m + 0.02, f"{m:.2f}%", ha="center", fontsize=8, color=NAVY)

    ax.axvline(2, color=GREY, lw=0.9, ls="--", alpha=0.7)
    ax.text(2.1, max(ms) * 0.92, "pre-reg.\n2% band", fontsize=7, color=GREY, style="italic")

    ax.set_xticks(x)
    ax.set_xticklabels(tick_labels, fontsize=8)
    ax.set_xlabel("Grading band (±)")
    ax.set_ylabel("Mean net per trade (%)")
    ax.set_ylim(0, max(ms) * 1.25 if max(ms) > 0 else 1)

    save(fig, "F21_net_by_band")


# ═══════════════════════════════════════════════════════════════════════════
# F22: MODEL VS HUMAN CUMULATIVE SUM
# ═══════════════════════════════════════════════════════════════════════════

def plot_f22():
    ret_rows = load_returns_matrix()
    cal_rows = load_calibration_csv()
    events = clean_universe(ret_rows, cal_rows)
    excluded_ws = load_excluded_ids()

    # Build lookup: (ticker, report_date_str) -> event dict
    cal_by_ticker_date = {}
    for e in events:
        key = (e["ticker"], e["report_date"])
        cal_by_ticker_date[key] = e

    # Load human decisions
    human_file = ROOT / "data" / "human" / "human_decisions_export_2026-08-12.csv"
    human_rows = []
    with open(human_file) as f:
        for r in csv.DictReader(f):
            human_rows.append(r)

    # Filter: section=All, first_rater=YES, in_llm_universe=YES
    human_filtered = [
        r for r in human_rows
        if r.get("section", "") == "All"
        and r.get("first_rater_for_event", "") == "YES"
        and r.get("in_llm_universe", "") == "YES"
    ]

    paired = []
    for r in human_filtered:
        ticker = r.get("ticker", "").strip()
        doc_date = r.get("document_date", "").strip()
        human_dec = r.get("human_decision", "").strip().upper()

        # Match to clean universe
        event = cal_by_ticker_date.get((ticker, doc_date))
        if event is None:
            # Try ±1 day
            try:
                d = _date.fromisoformat(doc_date)
                for delta in [1, -1]:
                    alt = str(d + _timedelta(days=delta))
                    event = cal_by_ticker_date.get((ticker, alt))
                    if event is not None:
                        break
            except ValueError:
                pass

        if event is None:
            continue

        # Exclude contaminated/SPOT
        doc_id = event.get("document_id", "")
        if doc_id in excluded_ws or doc_id == "SPOT_FQ1_2026":
            continue

        llm_dec = event.get("blend_predicted_signal_default", "HOLD").strip().upper()

        # Both must be trading (not HOLD)
        if human_dec == "HOLD" or llm_dec == "HOLD":
            continue

        ret = float(event["ret_overnight"])
        cost = COST_BPS

        model_net = (ret - cost) * 100 if llm_dec == "BUY" else (-ret - cost) * 100
        human_net = (ret - cost) * 100 if human_dec == "BUY" else (-ret - cost) * 100

        paired.append({
            "report_date": event["report_date"],
            "model_net": model_net,
            "human_net": human_net,
        })

    # Sort by report_date
    paired.sort(key=lambda p: p["report_date"])
    n_paired = len(paired)
    print(f"F22 paired n: {n_paired}")

    model_nets = np.array([p["model_net"] for p in paired])
    human_nets = np.array([p["human_net"] for p in paired])
    cum_model = np.cumsum(model_nets)
    cum_human = np.cumsum(human_nets)

    print(f"F22 terminal model: {cum_model[-1]:.2f}%, terminal human: {cum_human[-1]:.2f}%")

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH * 0.75))

    x = np.arange(1, n_paired + 1)
    ax.plot(x, cum_model, color=NAVY, lw=1.5, label="Model (LLM)")
    ax.plot(x, cum_human, color=RED, lw=1.5, label="Human")
    ax.axhline(0, color=GREY, lw=0.5, ls=":")

    ax.set_xlabel("Trade sequence (date-sorted)")
    ax.set_ylabel("Summed net return (%)")
    ax.legend(fontsize=7, loc="upper left")

    save(fig, "F22_model_vs_human_cumsum")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Generating figures...")
    plot_f1()
    plot_f2()
    plot_f3()
    plot_f4()
    plot_f5()
    plot_f6()
    plot_f7()
    plot_f8()
    plot_f9()
    plot_f10()
    plot_f11()
    plot_f12()
    plot_f13()
    plot_f14()
    plot_f15()
    plot_f16()
    plot_f17()
    plot_f18()
    plot_f19()
    plot_f20()
    plot_f21()
    plot_f22()
    print("\nDone. All outputs in figures/")
