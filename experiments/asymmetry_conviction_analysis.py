"""
experiments/asymmetry_conviction_analysis.py
Item 6 of the model-arm spec (Nigel, 2026-08-05): is the model worse at bad
news, and does the magnitude of its sentiment score carry information (a
prerequisite check before betting size on conviction, Extension 4).

Score = the DEPLOYED BLENDED score (0.55 micro + 0.45 macro, blend.DEFAULT_WEIGHTS),
recomputed per event from the calibration CSV's raw layer scores - not stored
as a continuous column, only the discretized decision is. Locked with the
user: this is "the model's score" for conviction purposes, not micro_score
alone, since it's what actually drives the deployed BUY/HOLD/SELL call.

Neutral on the raw score axis is 0.0 (scores run -1..+1) - distinct from the
DEPLOYED asymmetric HOLD band (blend.DEFAULT_HOLD_UPPER=0.25,
DEFAULT_HOLD_LOWER=-0.05). Conviction is measured as distance from 0.0, the
scale's own neutral point, not from the (asymmetric) decision boundary.

Run: python -m experiments.asymmetry_conviction_analysis
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import norm, spearmanr

from backtest import OUTPUTS_DIR
from blend import DEFAULT_WEIGHTS, blend_scores, derive_signal
from bootstrap_stats import bootstrap_unpaired_difference

PHASE2_CALIBRATION_CSV = OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration_phase2.csv"
CONFUSION_CSV = OUTPUTS_DIR / "global" / "summary" / "asymmetry_direction_confusion.csv"
MAGNITUDE_CSV = OUTPUTS_DIR / "global" / "summary" / "asymmetry_magnitude_bins.csv"
SCORE_MAGNITUDE_CSV = OUTPUTS_DIR / "global" / "summary" / "asymmetry_score_magnitude_bins.csv"
RECALL_GAP_CSV = OUTPUTS_DIR / "global" / "summary" / "asymmetry_recall_gap_test.csv"
CONVICTION_PNG = OUTPUTS_DIR / "global" / "summary" / "conviction_curve.png"

MAGNITUDE_BINS = [(0.0, 0.01), (0.01, 0.03), (0.03, 0.05), (0.05, float("inf"))]
SCORE_BINS = [(0.0, 0.10), (0.10, 0.25), (0.25, 0.50), (0.50, 1.01)]


def _num(x):
    if x is None or x == "":
        return None
    return float(x)


def load_rows(path: Path = PHASE2_CALIBRATION_CSV) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            micro = _num(r["micro_score"])
            macro = _num(r["macro_score"])
            news = _num(r["news_score"])
            quant = _num(r["quant_score"])
            if micro is None:
                continue  # micro is the anchor layer, never missing in practice
            score = blend_scores(micro, macro, news, quant, weights=DEFAULT_WEIGHTS)
            pred = derive_signal(score)
            rows.append({
                "document_id": r["document_id"], "ticker": r["ticker"],
                "truth": r["outcome_label"], "pred": pred, "score": score,
                "forward_return": _num(r["forward_return"]),
            })
    return rows


def confusion_by_direction(rows: list[dict]) -> list[dict]:
    """Hand-rolled 3-class precision/recall/F1 (matches repo convention -
    no sklearn used anywhere despite being installed)."""
    classes = ["BUY", "HOLD", "SELL"]
    out = []
    for c in classes:
        tp = sum(1 for r in rows if r["truth"] == c and r["pred"] == c)
        fp = sum(1 for r in rows if r["truth"] != c and r["pred"] == c)
        fn = sum(1 for r in rows if r["truth"] == c and r["pred"] != c)
        n_truth = sum(1 for r in rows if r["truth"] == c)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        hold_rate = sum(1 for r in rows if r["truth"] == c and r["pred"] == "HOLD") / n_truth if n_truth else 0.0
        out.append({
            "truth_class": c, "n_truth": n_truth, "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "hold_rate_given_truth": round(hold_rate, 4),
        })
    return out


def hit_rate_by_magnitude_bin(rows: list[dict]) -> list[dict]:
    out = []
    for lo, hi in MAGNITUDE_BINS:
        for direction in ("BUY", "SELL"):
            sub = [r for r in rows if r["truth"] == direction
                   and lo <= abs(r["forward_return"]) < hi]
            n = len(sub)
            hits = sum(1 for r in sub if r["pred"] == direction)
            out.append({
                "bin_low": lo, "bin_high": hi if hi != float("inf") else "inf",
                "truth_direction": direction, "n": n,
                "hit_rate": round(hits / n, 4) if n else "n/a",
            })
    return out


def score_magnitude_accuracy(rows: list[dict]) -> list[dict]:
    out = []
    for lo, hi in SCORE_BINS:
        sub = [r for r in rows if lo <= abs(r["score"]) < hi]
        n = len(sub)
        correct = sum(1 for r in sub if r["pred"] == r["truth"])
        out.append({
            "bin_low": lo, "bin_high": hi, "n": n,
            "accuracy": round(correct / n, 4) if n else "n/a",
        })
    return out


def rank_correlation(rows: list[dict]) -> dict:
    abs_score = [abs(r["score"]) for r in rows]
    abs_return = [abs(r["forward_return"]) for r in rows]
    rho, p = spearmanr(abs_score, abs_return)
    return {"n": len(rows), "spearman_rho": round(float(rho), 4), "p_value": round(float(p), 4)}


def recall_gap_test(rows: list[dict]) -> dict:
    """Recall per direction = fraction of truth-D events where the model
    correctly predicted D (D in {BUY, SELL}, HOLD-truth events excluded -
    this is specifically about directional calls, not the HOLD class).
    Unpaired comparison (different events per group) - primary test is the
    closed-form two-proportion z-test, companion is a bootstrap CI on the
    same unpaired difference."""
    buy_truth = [r for r in rows if r["truth"] == "BUY"]
    sell_truth = [r for r in rows if r["truth"] == "SELL"]
    n1, n2 = len(buy_truth), len(sell_truth)
    x1 = sum(1 for r in buy_truth if r["pred"] == "BUY")
    x2 = sum(1 for r in sell_truth if r["pred"] == "SELL")
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se = (p_pool * (1 - p_pool) * (1 / n1 + 1 / n2)) ** 0.5
    z = (p1 - p2) / se if se > 0 else 0.0
    p_value_z = 2 * (1 - norm.cdf(abs(z)))

    buy_indicator = [1.0 if r["pred"] == "BUY" else 0.0 for r in buy_truth]
    sell_indicator = [1.0 if r["pred"] == "SELL" else 0.0 for r in sell_truth]
    boot = bootstrap_unpaired_difference(buy_indicator, sell_indicator)

    return {
        "n_buy_truth": n1, "n_sell_truth": n2,
        "recall_buy": round(p1, 4), "recall_sell": round(p2, 4),
        "recall_gap": round(p1 - p2, 4),
        "z_statistic": round(float(z), 4), "p_value_ztest": round(float(p_value_z), 4),
        "bootstrap_ci_low": round(boot["ci_low"], 4), "bootstrap_ci_high": round(boot["ci_high"], 4),
        "bootstrap_p_value": round(boot["p_value"], 4),
    }


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {path}")


def plot_conviction_curve(score_bins: list[dict], path: Path = CONVICTION_PNG):
    labels = [f"[{b['bin_low']:.2f},{b['bin_high']:.2f})" for b in score_bins]
    accs = [b["accuracy"] if b["accuracy"] != "n/a" else np.nan for b in score_bins]
    ns = [b["n"] for b in score_bins]

    fig, ax1 = plt.subplots(figsize=(7, 4.5))
    ax1.plot(labels, accs, marker="o", color="#2b6cb0", label="accuracy")
    ax1.set_ylabel("Accuracy")
    ax1.set_xlabel("Absolute score magnitude bin (distance from 0.0)")
    ax1.set_ylim(0, 1)
    ax1.axhline(y=1 / 3, color="gray", linestyle="--", linewidth=1, label="3-class chance (1/3)")

    ax2 = ax1.twinx()
    ax2.bar(labels, ns, alpha=0.15, color="#2b6cb0")
    ax2.set_ylabel("n events (bar)")

    ax1.set_title("Conviction curve: accuracy vs |score| magnitude")
    ax1.legend(loc="lower right")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Wrote chart -> {path}")


def main() -> int:
    rows = load_rows()
    print(f"Loaded {len(rows)} events with blended scores recomputed from raw layer scores")

    confusion = confusion_by_direction(rows)
    write_csv(CONFUSION_CSV, confusion)
    for c in confusion:
        print(f"  {c['truth_class']:4} n={c['n_truth']:3}  precision={c['precision']:.3f} "
              f"recall={c['recall']:.3f} f1={c['f1']:.3f} hold_rate={c['hold_rate_given_truth']:.3f}")

    magnitude_bins = hit_rate_by_magnitude_bin(rows)
    write_csv(MAGNITUDE_CSV, magnitude_bins)

    score_bins = score_magnitude_accuracy(rows)
    write_csv(SCORE_MAGNITUDE_CSV, score_bins)
    plot_conviction_curve(score_bins)

    rc = rank_correlation(rows)
    rc_csv = OUTPUTS_DIR / "global" / "summary" / "asymmetry_rank_correlation.csv"
    write_csv(rc_csv, [rc])
    print(f"\nSpearman rank correlation |score| vs |forward_return|: "
          f"rho={rc['spearman_rho']}, p={rc['p_value']}, n={rc['n']}")
    print(f"  Saved -> {rc_csv}")

    gap = recall_gap_test(rows)
    write_csv(RECALL_GAP_CSV, [gap])
    print(f"\nRecall gap: BUY-truth={gap['recall_buy']:.3f} (n={gap['n_buy_truth']}), "
          f"SELL-truth={gap['recall_sell']:.3f} (n={gap['n_sell_truth']}), "
          f"gap={gap['recall_gap']:+.3f}")
    print(f"  z-test p={gap['p_value_ztest']:.4f}; bootstrap CI "
          f"[{gap['bootstrap_ci_low']:+.3f}, {gap['bootstrap_ci_high']:+.3f}], "
          f"bootstrap p={gap['bootstrap_p_value']:.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
