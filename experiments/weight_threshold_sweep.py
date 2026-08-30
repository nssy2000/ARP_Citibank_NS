"""
experiments/weight_threshold_sweep.py  (Round 5)

Comprehensive, reproducible pooled weight+threshold optimization - the committed
successor to Round 4's throwaway finer-grid script. Three things the production
grid in eval/calibrate.py does NOT do, kept HERE so the production overfitting
surface stays small:

  1. Finer weight grid (step 0.05 vs production 0.2) over (micro, macro, news, quant).
  2. ASYMMETRIC hold thresholds - production only searches hold_upper == -hold_lower;
     this searches hold_upper and hold_lower independently.
  3. A "does it beat noise" verdict: binomial + permutation significance tests of
     the pooled accuracy against the majority-class baseline.

It also runs the Fed-layer (and macro-numeric) ablation by re-blending with each
quant variant (plain / +macro-numeric / +fred / +macro+fred) and reporting whether
any lifts accuracy.

Vectorized with numpy: a [combo x doc] correctness tensor is built once, so global
best-fit and full LOOCV are both cheap even at N>=131.

Run:  python -m experiments.weight_threshold_sweep
Out:  outputs/global/summary/weight_threshold_sweep.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from report_pipeline import OUTPUTS_DIR
from blend import DEFAULT_WEIGHTS
from eval.calibrate import DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER
from eval.outcomes import DEFAULT_WINDOW_TRADING_DAYS, OUTCOME_LOWER_DEFAULT, OUTCOME_UPPER_DEFAULT
from eval.run_eval import ALL_ISSUERS, build_documents_for_issuer
import quant_layer

LABELS = ("SELL", "HOLD", "BUY")
LABEL_IDX = {l: i for i, l in enumerate(LABELS)}

WEIGHT_STEP = 0.05
THRESH_UPPER = [round(0.05 * k, 2) for k in range(1, 9)]        # 0.05 .. 0.40
THRESH_LOWER = [round(-0.05 * k, 2) for k in range(1, 9)]        # -0.05 .. -0.40
PERMUTATIONS = 5000
RNG_SEED = 20260709

QUANT_VARIANTS = ["quant_score", "quant_score_with_macro", "quant_score_with_fred", "quant_score_with_macro_fred"]


def weight_grid(step: float) -> np.ndarray:
    n = round(1.0 / step)
    combos = []
    for a in range(n + 1):
        for b in range(n + 1 - a):
            for c in range(n + 1 - a - b):
                d = n - a - b - c
                combos.append((a * step, b * step, c * step, d * step))
    return np.array(combos, dtype=float)  # [nw,4] each row sums to 1.0


def load_pooled(window_trading_days: int = DEFAULT_WINDOW_TRADING_DAYS,
                outcome_upper: float = OUTCOME_UPPER_DEFAULT,
                outcome_lower: float = OUTCOME_LOWER_DEFAULT,
                exit_on_open: bool = False):
    """Reuse the production loader; also pull the alternative quant variants from
    each quant payload so we can ablate the Fed / macro-numeric sub-components."""
    docs = []
    for issuer in ALL_ISSUERS:
        for outcome, doc in build_documents_for_issuer(
            issuer, window_trading_days, outcome_upper, outcome_lower, exit_on_open
        ):
            qpayload = quant_layer.get_quant_score(issuer, doc.document_id)
            qmetrics = (qpayload or {}).get("quant_metrics", {})
            docs.append({
                "document_id": doc.document_id,
                "issuer": issuer,
                "label": doc.outcome_label,
                "micro": doc.micro_score,
                "macro": doc.macro_score,
                "news": doc.news_score,
                "quant_variants": {v: qmetrics.get(v) for v in QUANT_VARIANTS},
            })
    return docs


def build_layer_matrices(docs, quant_variant):
    """S [ndoc,4] layer scores (0 where missing), M [ndoc,4] presence mask (1/0),
    order = micro, macro, news, quant."""
    n = len(docs)
    S = np.zeros((n, 4))
    M = np.zeros((n, 4))
    for i, d in enumerate(docs):
        for j, key in enumerate(("micro", "macro", "news")):
            v = d[key]
            if v is not None:
                S[i, j] = v; M[i, j] = 1.0
        qv = d["quant_variants"].get(quant_variant)
        if qv is not None:
            S[i, 3] = qv; M[i, 3] = 1.0
    return S, M


def correctness_tensor(S, M, W, labels_idx):
    """Return C [ncombo, ndoc] uint8 correctness, a combo index -> (weights, hu, hl)
    map, and P [ncombo, ndoc] int8 predicted-label indices (for permutation-testing a
    tuned model's chosen predictions). Blend uses the same missing-layer
    redistribution as blend.blend_scores."""
    num = W @ S.T                      # [nw,ndoc]
    den = W @ M.T                      # [nw,ndoc]
    den = np.where(den == 0, np.nan, den)
    blended = num / den                # [nw,ndoc]; NaN only if a doc has zero total weight
    nw, ndoc = blended.shape

    combos_meta = []
    C_blocks = []
    P_blocks = []
    for hu in THRESH_UPPER:
        for hl in THRESH_LOWER:
            pred = np.full((nw, ndoc), LABEL_IDX["HOLD"], dtype=np.int8)
            pred[blended > hu] = LABEL_IDX["BUY"]
            pred[blended < hl] = LABEL_IDX["SELL"]
            correct = (pred == labels_idx[None, :]).astype(np.uint8)
            # a doc with no usable weight (blended NaN) is scored wrong for that combo
            correct[np.isnan(blended)] = 0
            C_blocks.append(correct)
            P_blocks.append(pred)
            for wi in range(nw):
                combos_meta.append((wi, hu, hl))
    C = np.concatenate(C_blocks, axis=0)  # [ncombo, ndoc]
    P = np.concatenate(P_blocks, axis=0)  # [ncombo, ndoc]
    return C, combos_meta, P


def dist_from_default(w, hu, hl):
    return sum(abs(a - b) for a, b in zip(w, DEFAULT_WEIGHTS)) + abs(hu - DEFAULT_HOLD_UPPER) + abs(hl - DEFAULT_HOLD_LOWER)


def onehot(labels_idx, n_classes=3):
    L = np.zeros((len(labels_idx), n_classes))
    L[np.arange(len(labels_idx)), labels_idx] = 1.0
    return L


def balanced_accuracy_from_correct(correct_vec, labels_idx, n_classes=3):
    """Mean per-class recall. Classes with zero members in this slice are skipped
    (relevant for LOOCV folds where removing one doc can empty a rare class)."""
    correct = np.asarray(correct_vec)
    labels = np.asarray(labels_idx)
    totals = np.bincount(labels, minlength=n_classes).astype(float)
    class_correct = np.array([correct[labels == c].sum() if totals[c] > 0 else 0.0 for c in range(n_classes)])
    valid = totals > 0
    return float((class_correct[valid] / totals[valid]).mean())


def majority_balanced_accuracy(labels_idx, n_classes=3):
    """Balanced accuracy of an always-predict-the-majority-class classifier - a fixed
    1/n_classes floor regardless of label skew, unlike majority-class raw accuracy."""
    labels = np.asarray(labels_idx)
    totals = np.bincount(labels, minlength=n_classes).astype(float)
    majority = int(totals.argmax())
    correct = (labels == majority).astype(np.uint8)
    return balanced_accuracy_from_correct(correct, labels, n_classes)


def evaluate_variant(docs, quant_variant, W, metric="accuracy"):
    labels_idx = np.array([LABEL_IDX[d["label"]] for d in docs])
    S, M = build_layer_matrices(docs, quant_variant)
    C, meta, P = correctness_tensor(S, M, W, labels_idx)  # [ncombo,ndoc]
    ncombo, ndoc = C.shape
    per_combo_correct = C.sum(axis=1)                     # [ncombo]

    L = onehot(labels_idx)                                 # [ndoc,3]
    class_totals = L.sum(axis=0)                           # [3]
    class_correct = C @ L                                  # [ncombo,3]
    denom = np.where(class_totals == 0, np.nan, class_totals)
    balanced_acc = np.nanmean(class_correct / denom, axis=1)   # [ncombo]

    selection_score = balanced_acc if metric == "balanced_accuracy" else per_combo_correct

    # --- global best-fit (fit on all docs; tie-break toward the default config) ---
    best_score = selection_score.max()
    tied = np.where(selection_score == best_score)[0]
    best_ci = min(tied, key=lambda ci: dist_from_default(W[meta[ci][0]], meta[ci][1], meta[ci][2]))
    bw, bhu, bhl = W[meta[best_ci][0]], meta[best_ci][1], meta[best_ci][2]
    global_best = {
        "accuracy": round(float(per_combo_correct[best_ci] / ndoc), 4),
        "balanced_accuracy": round(float(balanced_acc[best_ci]), 4),
        "weights": [round(x, 4) for x in bw.tolist()],
        "hold_upper": bhu, "hold_lower": bhl,
        "n_tied": int(len(tied)),
    }

    # --- LOOCV: for each held-out doc, best combo on the OTHER docs (by `metric`), tie-break to default ---
    default_ci = _default_combo_index(meta, W)
    held_correct = np.zeros(ndoc, dtype=np.uint8)
    loocv_tuned_pred = np.zeros(ndoc, dtype=np.int8)
    for i in range(ndoc):
        if metric == "balanced_accuracy":
            loo_class_correct = class_correct - np.outer(C[:, i], L[i])
            loo_class_totals = class_totals - L[i]
            loo_denom = np.where(loo_class_totals == 0, np.nan, loo_class_totals)
            loo_score = np.nanmean(loo_class_correct / loo_denom, axis=1)
        else:
            loo_score = per_combo_correct - C[:, i]      # correct count without doc i
        m = loo_score.max()
        tied_i = np.where(loo_score == m)[0]
        ci = min(tied_i, key=lambda ci: dist_from_default(W[meta[ci][0]], meta[ci][1], meta[ci][2]))
        held_correct[i] = C[ci, i]
        loocv_tuned_pred[i] = P[ci, i]
    loocv_tuned_correct = int(held_correct.sum())
    loocv_default_correct = int(C[default_ci].sum())

    return {
        "global_best": global_best,
        "loocv_tuned_accuracy": round(loocv_tuned_correct / ndoc, 4),
        "loocv_tuned_balanced_accuracy": round(balanced_accuracy_from_correct(held_correct, labels_idx), 4),
        "loocv_default_accuracy": round(loocv_default_correct / ndoc, 4),
        "loocv_default_balanced_accuracy": round(balanced_accuracy_from_correct(C[default_ci], labels_idx), 4),
        "default_correct_vector": C[default_ci].tolist(),
        "loocv_tuned_pred": loocv_tuned_pred.tolist(),
        "labels_idx": labels_idx.tolist(),
        "n": ndoc,
    }


def _default_combo_index(meta, W):
    # find the combo closest to (DEFAULT_WEIGHTS, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER)
    best, best_d = 0, 1e9
    for ci, (wi, hu, hl) in enumerate(meta):
        d = dist_from_default(W[wi], hu, hl)
        if d < best_d:
            best_d, best = d, ci
    return best


def significance(default_correct_vector, labels_idx, seed=RNG_SEED, perms=PERMUTATIONS):
    """Test the DEFAULT (deployed) model's pooled accuracy against the
    majority-class baseline. Binomial (vs baseline rate) + label-permutation."""
    correct = np.array(default_correct_vector, dtype=np.uint8)
    labels = np.array(labels_idx)
    n = len(labels)
    acc = correct.mean()

    counts = np.bincount(labels, minlength=len(LABELS))
    majority_rate = counts.max() / n
    majority_label = LABELS[int(counts.argmax())]

    # binomial: P(Binom(n, majority_rate) >= observed_correct), one-sided
    k = int(correct.sum())
    from math import comb
    p_binom = sum(comb(n, j) * majority_rate**j * (1 - majority_rate)**(n - j) for j in range(k, n + 1))

    return {
        "accuracy": round(float(acc), 4),
        "n": int(n),
        "majority_label": majority_label,
        "majority_rate": round(float(majority_rate), 4),
        "binomial_p_vs_majority": round(float(p_binom), 5),
    }


def permutation_test(default_pred, labels, seed=RNG_SEED, perms=PERMUTATIONS):
    """Real permutation test: hold the model's predictions FIXED, shuffle the true
    labels `perms` times, and see how often the shuffled accuracy meets/exceeds the
    observed. p = fraction >= observed."""
    rng = np.random.default_rng(seed)
    obs = float((default_pred == labels).mean())
    ge = 0
    for _ in range(perms):
        ge += int((default_pred == rng.permutation(labels)).mean() >= obs)
    return round((ge + 1) / (perms + 1), 5)


def permutation_test_balanced(default_pred, labels, seed=RNG_SEED, perms=PERMUTATIONS, n_classes=3):
    """Same idea as permutation_test but on balanced accuracy: hold predictions FIXED,
    shuffle true labels, recompute balanced accuracy each time (grouping by the
    shuffled label, since that's the reshuffled 'true' class for that draw)."""
    rng = np.random.default_rng(seed)
    obs_correct = (default_pred == labels).astype(np.uint8)
    obs = balanced_accuracy_from_correct(obs_correct, labels, n_classes)
    ge = 0
    for _ in range(perms):
        shuffled = rng.permutation(labels)
        shuffled_correct = (default_pred == shuffled).astype(np.uint8)
        ge += int(balanced_accuracy_from_correct(shuffled_correct, shuffled, n_classes) >= obs)
    return round((ge + 1) / (perms + 1), 5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-trading-days", type=int, default=DEFAULT_WINDOW_TRADING_DAYS,
                         help="Outcome window in trading days (ground-truth forward-return horizon). "
                              "Default 5 (production). Use 1 for next-day close-to-close.")
    parser.add_argument("--outcome-upper", type=float, default=OUTCOME_UPPER_DEFAULT)
    parser.add_argument("--outcome-lower", type=float, default=OUTCOME_LOWER_DEFAULT)
    parser.add_argument("--exit-on-open", action="store_true",
                         help="Score against the close-to-OPEN overnight gap (next-day Open vs report-date "
                              "Close) instead of close-to-close. With --window-trading-days 1 and "
                              "--outcome-upper/-lower 0.02 this is the group Google Sheet's exact ground "
                              "truth (Actual Direction bucketed at Settings!B3=2%).")
    parser.add_argument("--optimize-metric", choices=["accuracy", "balanced_accuracy"], default="accuracy",
                         help="Selection objective for global-best and LOOCV combo search. Default 'accuracy' "
                              "(production/committed 5-day behavior). Use 'balanced_accuracy' (mean per-class "
                              "recall) when the label distribution is skewed (e.g. short outcome windows), since "
                              "raw accuracy's majority-class baseline moves with the skew while balanced "
                              "accuracy's floor is a fixed 1/n_classes.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(f"Loading pooled documents (window_trading_days={args.window_trading_days}, "
          f"exit_on_open={args.exit_on_open})...")
    docs = load_pooled(args.window_trading_days, args.outcome_upper, args.outcome_lower, args.exit_on_open)
    W = weight_grid(WEIGHT_STEP)
    ncombo = W.shape[0] * len(THRESH_UPPER) * len(THRESH_LOWER)
    print(f"N={len(docs)} docs | weight grid={W.shape[0]} x thresholds={len(THRESH_UPPER)*len(THRESH_LOWER)} = {ncombo} combos/variant")

    variants = {}
    for v in QUANT_VARIANTS:
        variants[v] = evaluate_variant(docs, v, W, metric=args.optimize_metric)
        gb = variants[v]["global_best"]
        print(f"  [{v}] global_best acc={gb['accuracy']} bal_acc={gb['balanced_accuracy']} w={gb['weights']} "
              f"thr=({gb['hold_upper']},{gb['hold_lower']}) | LOOCV tuned acc={variants[v]['loocv_tuned_accuracy']} "
              f"bal_acc={variants[v]['loocv_tuned_balanced_accuracy']} | default acc={variants[v]['loocv_default_accuracy']} "
              f"bal_acc={variants[v]['loocv_default_balanced_accuracy']}")

    # significance on the primary (headline quant) default model
    primary = variants["quant_score"]
    labels_idx = np.array(primary["labels_idx"])
    # reconstruct default predictions from the default correctness vector is lossy;
    # recompute default predictions directly for a clean permutation test:
    default_pred = _default_predictions(docs)
    sig = significance(primary["default_correct_vector"], primary["labels_idx"])
    sig["permutation_p_vs_shuffled_labels"] = permutation_test(default_pred, labels_idx)
    sig["verdict"] = _verdict(sig)
    print(f"\nSignificance (default model): acc={sig['accuracy']} vs majority '{sig['majority_label']}'={sig['majority_rate']} "
          f"| binomial p={sig['binomial_p_vs_majority']} | permutation p={sig['permutation_p_vs_shuffled_labels']}")
    print(f"VERDICT: {sig['verdict']}")

    majority_bal_baseline = majority_balanced_accuracy(labels_idx)
    default_correct = np.array(primary["default_correct_vector"], dtype=np.uint8)
    # LOOCV-tuned-for-balanced-accuracy predictions (the skew-aware model): each doc's
    # prediction comes from a config fit on the OTHER docs, so holding these fixed and
    # shuffling labels is a valid (slightly conservative) permutation null.
    loocv_tuned_pred = np.array(primary["loocv_tuned_pred"], dtype=np.int8)
    bal_sig = {
        "default_balanced_accuracy": round(balanced_accuracy_from_correct(default_correct, labels_idx), 4),
        "default_permutation_p_balanced": permutation_test_balanced(default_pred, labels_idx),
        "loocv_tuned_balanced_accuracy": primary["loocv_tuned_balanced_accuracy"],
        "loocv_tuned_permutation_p_balanced": permutation_test_balanced(loocv_tuned_pred, labels_idx),
        "majority_balanced_accuracy_baseline": round(majority_bal_baseline, 4),
        "optimize_metric": args.optimize_metric,
    }
    # Headline = the model actually selected by --optimize-metric. When optimizing for
    # balanced accuracy this is the LOOCV-tuned skew-aware model; otherwise the default.
    if args.optimize_metric == "balanced_accuracy":
        head_ba = bal_sig["loocv_tuned_balanced_accuracy"]; head_p = bal_sig["loocv_tuned_permutation_p_balanced"]
        head_name = "LOOCV-tuned skew-aware"
    else:
        head_ba = bal_sig["default_balanced_accuracy"]; head_p = bal_sig["default_permutation_p_balanced"]
        head_name = "default"
    bal_verdict_pass = head_ba > majority_bal_baseline and head_p < 0.05
    bal_sig["verdict"] = (
        f"{head_name} balanced_accuracy {head_ba} vs majority-only floor "
        f"{round(majority_bal_baseline, 4)} - "
        f"{'BEATS' if bal_verdict_pass else 'does NOT beat'} the skew-proof baseline "
        f"(permutation p={head_p}) at N={len(labels_idx)}"
    )
    print(f"\nBalanced-accuracy significance: {bal_sig['verdict']}")

    out = {
        "n_documents": len(docs),
        "window_trading_days": args.window_trading_days,
        "exit_on_open": args.exit_on_open,
        "outcome_thresholds": {"outcome_upper": args.outcome_upper, "outcome_lower": args.outcome_lower},
        "optimize_metric": args.optimize_metric,
        "weight_step": WEIGHT_STEP,
        "threshold_grid": {"upper": THRESH_UPPER, "lower": THRESH_LOWER, "asymmetric": True},
        "combos_per_variant": ncombo,
        "default_config": {"weights": list(DEFAULT_WEIGHTS), "hold_upper": DEFAULT_HOLD_UPPER, "hold_lower": DEFAULT_HOLD_LOWER},
        "majority_balanced_accuracy_baseline": round(majority_bal_baseline, 4),
        "variants": {v: {k: r[k] for k in (
                "global_best", "loocv_tuned_accuracy", "loocv_tuned_balanced_accuracy",
                "loocv_default_accuracy", "loocv_default_balanced_accuracy", "n")}
                     for v, r in variants.items()},
        "fed_ablation_note": (
            "Compare quant_score (plain) vs quant_score_with_fred / _with_macro / _with_macro_fred. "
            "If none lifts global_best or LOOCV accuracy over plain, the Fed/macro-numeric sub-components "
            "do not earn weight - a stable negative, consistent with macro/news at earlier N."
        ),
        "significance": sig,
        "significance_balanced": bal_sig,
    }
    summary_dir = OUTPUTS_DIR / "global" / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.window_trading_days == DEFAULT_WINDOW_TRADING_DAYS else f"_window{args.window_trading_days}"
    suffix += "_gap" if args.exit_on_open else ""
    suffix += "" if args.optimize_metric == "accuracy" else "_bal"
    path = summary_dir / f"weight_threshold_sweep{suffix}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {path}")
    return 0


def _default_predictions(docs) -> np.ndarray:
    """Default-model (DEFAULT_WEIGHTS at DEFAULT thresholds) prediction per doc,
    using blend.blend_scores redistribution semantics."""
    from blend import blend_scores, derive_signal
    preds = []
    for d in docs:
        blended = blend_scores(d["micro"], d["macro"], d["news"], d["quant_variants"]["quant_score"], DEFAULT_WEIGHTS)
        preds.append(LABEL_IDX[derive_signal(blended, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER)])
    return np.array(preds)


def _verdict(sig) -> str:
    p = max(sig["binomial_p_vs_majority"], sig["permutation_p_vs_shuffled_labels"])
    if p < 0.05:
        return (f"blend {sig['accuracy']} vs majority {sig['majority_rate']} - statistically significant "
                f"(binomial p={sig['binomial_p_vs_majority']}, permutation p={sig['permutation_p_vs_shuffled_labels']}) at N={sig['n']}")
    return (f"blend {sig['accuracy']} vs majority {sig['majority_rate']} - NOT distinguishable from noise "
            f"(binomial p={sig['binomial_p_vs_majority']}, permutation p={sig['permutation_p_vs_shuffled_labels']}) at N={sig['n']}")


if __name__ == "__main__":
    sys.exit(main())
