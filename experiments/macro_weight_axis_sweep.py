"""
experiments/macro_weight_axis_sweep.py
Item 1a of the model-arm spec (Nigel, 2026-08-05): the macro-weight search
result ("settled at zero") was never persisted as a curve, only its winning
combo (outputs/global/summary/weight_threshold_sweep.json's global_best).
This produces the actual curve so the write-up can show it, not just assert
the conclusion.

Deliberately built directly from the current phase2 calibration CSV (N=268)
rather than reusing experiments/weight_threshold_sweep.py's load_pooled(),
which draws from ALL_ISSUERS - a pooled original+phase2 universe of N=232,
NOT the current N=268 phase2 track this project treats as canonical (see
CLAUDE.md: "phase2 is the only active track"). Reusing that loader would
silently score the wrong dataset - the exact class of bug this project's own
docs repeatedly warn about. blend_scores/derive_signal are still reused from
blend.py, matching the deployed logic exactly.

HOLD-thresholds are held FIXED at the deployed default
(blend.DEFAULT_HOLD_UPPER/LOWER) while macro weight sweeps - isolates the
macro-weight effect as one variable, rather than conflating it with a
threshold re-search at every point (locked decision with the user).

Run: python -m experiments.macro_weight_axis_sweep
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from backtest import OUTPUTS_DIR
from blend import DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER, DEFAULT_WEIGHTS, blend_scores, derive_signal

PHASE2_CALIBRATION_CSV = OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration_phase2.csv"
SWEEP_CSV = OUTPUTS_DIR / "global" / "summary" / "macro_weight_axis_sweep.csv"
CURVE_PNG = OUTPUTS_DIR / "global" / "summary" / "macro_weight_curve.png"

MACRO_WEIGHTS = np.round(np.arange(0.0, 1.001, 0.05), 2)  # 21 points
DEPLOYED_MACRO_WEIGHT = DEFAULT_WEIGHTS[1]  # 0.45


def _num(x):
    if x is None or x == "":
        return None
    return float(x)


def load_rows(path: Path = PHASE2_CALIBRATION_CSV) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            micro = _num(r["micro_score"])
            if micro is None:
                continue
            rows.append({
                "document_id": r["document_id"],
                "micro": micro, "macro": _num(r["macro_score"]),
                "news": _num(r["news_score"]), "quant": _num(r["quant_score"]),
                "truth": r["outcome_label"],
            })
    return rows


def sweep(rows: list[dict]) -> list[dict]:
    """News/quant pinned at 0 throughout, matching DEFAULT_WEIGHTS' own
    non-macro entries - so this isolates exactly the micro/macro tradeoff
    the deployed model actually uses."""
    out = []
    for mw in MACRO_WEIGHTS:
        weights = (round(1.0 - mw, 2), mw, 0.0, 0.0)
        correct = 0
        for r in rows:
            available = [(r["micro"], weights[0]), (r["macro"], weights[1]),
                         (r["news"], weights[2]), (r["quant"], weights[3])]
            total_weight = sum(w for v, w in available if v is not None)
            if total_weight == 0:
                continue  # no usable layer at this weight point - scored wrong (excluded from correct, kept in n)
            score = blend_scores(r["micro"], r["macro"], r["news"], r["quant"], weights=weights)
            pred = derive_signal(score, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER)
            if pred == r["truth"]:
                correct += 1
        out.append({
            "macro_weight": float(mw), "micro_weight": weights[0],
            "n": len(rows), "accuracy": round(correct / len(rows), 4),
            "is_deployed_default": abs(mw - DEPLOYED_MACRO_WEIGHT) < 1e-9,
        })
    return out


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {path}")


def plot_curve(curve: list[dict], path: Path = CURVE_PNG):
    xs = [c["macro_weight"] for c in curve]
    ys = [c["accuracy"] for c in curve]
    zero_acc = curve[0]["accuracy"]
    deployed_row = next(c for c in curve if c["is_deployed_default"])

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(xs, ys, marker="o", color="#2b6cb0")
    ax.axvline(x=0.0, color="green", linestyle="--", linewidth=1,
               label=f"macro=0 (accuracy={zero_acc:.3f})")
    ax.axvline(x=DEPLOYED_MACRO_WEIGHT, color="red", linestyle="--", linewidth=1,
               label=f"deployed default (macro={DEPLOYED_MACRO_WEIGHT}, "
                     f"accuracy={deployed_row['accuracy']:.3f})")
    ax.set_xlabel("Macro weight (micro weight = 1 - macro weight, news/quant pinned at 0)")
    ax.set_ylabel("Accuracy (5-day window, N={})".format(curve[0]["n"]))
    ax.set_title("Accuracy vs macro weight, HOLD thresholds fixed at deployed default")
    ax.legend(loc="best")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Wrote chart -> {path}")


def main() -> int:
    rows = load_rows()
    print(f"Loaded {len(rows)} events (phase2 calibration CSV, N=268 expected)")

    curve = sweep(rows)
    write_csv(SWEEP_CSV, curve)

    zero = curve[0]
    deployed = next(c for c in curve if c["is_deployed_default"])
    best = max(curve, key=lambda c: c["accuracy"])
    print(f"\nmacro=0.00: accuracy={zero['accuracy']:.4f}")
    print(f"macro={DEPLOYED_MACRO_WEIGHT} (deployed default): accuracy={deployed['accuracy']:.4f}")
    print(f"best on curve: macro={best['macro_weight']}: accuracy={best['accuracy']:.4f}")

    plot_curve(curve)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
