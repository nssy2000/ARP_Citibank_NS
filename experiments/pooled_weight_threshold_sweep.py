"""
experiments/pooled_weight_threshold_sweep.py

Re-runs the exact production weight/threshold validation methodology
(experiments/weight_threshold_sweep.py: fine grid, asymmetric thresholds,
LOOCV-stability check, significance tests) but POOLS the original 6-issuer
N=131 set together with the phase2 28-issuer set (p2_-prefixed, own docs/
manifests/outputs, never touching the canonical folders - see CLAUDE.md's
Phase 2 section), for N ~= 232.

Purpose: the deployed default weights (0.8/0.0/0.2/0.0, +-0.25) were derived
and LOOCV-validated on the ORIGINAL N=131 set only, then applied to phase2
untouched (an honest, non-overfit transfer, but not itself proof the SAME
weights are optimal for phase2's different company/sector mix - phase2 alone
(N=101) can't resolve that: its own weight search's LOOCV goes negative,
i.e. not enough signal at that N to tell a good alternative from noise).
Pooling roughly doubles N, which is the only way to get enough power to ask
"does the same weight combo still win under leave-one-out refitting once
phase2's company mix is included" without re-introducing the overfit risk of
searching on phase2 alone.

Uses the SAME outcome definition as the original N=131 validation (5-day
close-to-close, accuracy objective) - not the overnight-gap/P&L framing used
for backtest.py - because that is what actually established the default
weights as LOOCV-stable in the first place; this script asks whether that
same finding holds at higher N, not whether P&L improves.

Run:  python -m experiments.pooled_weight_threshold_sweep
Out:  outputs/global/summary/pooled_weight_threshold_sweep.json
"""
from __future__ import annotations

import json
import sys

import numpy as np

from report_pipeline import OUTPUTS_DIR
from blend import DEFAULT_WEIGHTS, PHASE2_ISSUERS
from eval.calibrate import DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER
from eval.outcomes import DEFAULT_WINDOW_TRADING_DAYS, OUTCOME_LOWER_DEFAULT, OUTCOME_UPPER_DEFAULT
from eval.run_eval import ALL_ISSUERS, build_documents_for_issuer
import quant_layer

from experiments.weight_threshold_sweep import (
    LABELS, LABEL_IDX, WEIGHT_STEP, THRESH_UPPER, THRESH_LOWER, PERMUTATIONS, RNG_SEED,
    weight_grid, evaluate_variant, significance, permutation_test, _default_predictions,
    majority_balanced_accuracy, balanced_accuracy_from_correct, _verdict,
)

QUANT_VARIANT = "quant_score"  # production already established quant is inert; no need to re-ablate here

# Phase2 issuers minus the 6 that overlap production tickers under a DIFFERENT
# key (p2_bank_of_america etc. point at phase2's own docs/manifests, never the
# canonical boeing/jpm/... folders) - so pooling is additive, no double-count.
POOLED_ISSUERS = list(ALL_ISSUERS) + [f"p2_{name}" for name in PHASE2_ISSUERS]


def load_pooled(issuers, window_trading_days, outcome_upper, outcome_lower, exit_on_open=False):
    docs = []
    skipped_issuers = []
    for issuer in issuers:
        try:
            pairs = build_documents_for_issuer(issuer, window_trading_days, outcome_upper, outcome_lower, exit_on_open)
        except FileNotFoundError:
            skipped_issuers.append(issuer)
            continue
        for outcome, doc in pairs:
            qpayload = quant_layer.get_quant_score(issuer, doc.document_id)
            qmetrics = (qpayload or {}).get("quant_metrics", {})
            docs.append({
                "document_id": doc.document_id,
                "issuer": issuer,
                "label": doc.outcome_label,
                "micro": doc.micro_score,
                "macro": doc.macro_score,
                "news": doc.news_score,
                "quant_variants": {QUANT_VARIANT: qmetrics.get(QUANT_VARIANT)},
            })
    return docs, skipped_issuers


def main() -> int:
    print(f"Pooling {len(POOLED_ISSUERS)} issuers ({len(ALL_ISSUERS)} production + {len(PHASE2_ISSUERS)} phase2)...")
    docs, skipped = load_pooled(POOLED_ISSUERS, DEFAULT_WINDOW_TRADING_DAYS, OUTCOME_UPPER_DEFAULT, OUTCOME_LOWER_DEFAULT)
    if skipped:
        print(f"  Skipped (no results dir yet): {skipped}")
    print(f"N={len(docs)} pooled documents (5-day close-to-close, accuracy objective, matching the original N=131 validation)")

    W = weight_grid(WEIGHT_STEP)
    ncombo = W.shape[0] * len(THRESH_UPPER) * len(THRESH_LOWER)
    print(f"weight grid={W.shape[0]} x thresholds={len(THRESH_UPPER)*len(THRESH_LOWER)} = {ncombo} combos")

    result = evaluate_variant(docs, QUANT_VARIANT, W, metric="accuracy")
    gb = result["global_best"]
    print(f"global_best acc={gb['accuracy']} bal_acc={gb['balanced_accuracy']} w={gb['weights']} "
          f"thr=({gb['hold_upper']},{gb['hold_lower']}) (n_tied={gb['n_tied']})")
    print(f"LOOCV tuned acc={result['loocv_tuned_accuracy']} | LOOCV default (deployed weights) acc={result['loocv_default_accuracy']}")

    labels_idx = np.array(result["labels_idx"])
    default_pred = _default_predictions(docs)
    sig = significance(result["default_correct_vector"], result["labels_idx"])
    sig["permutation_p_vs_shuffled_labels"] = permutation_test(default_pred, labels_idx)
    sig["verdict"] = _verdict(sig)
    print(f"\nDeployed-weights significance at pooled N: {sig['verdict']}")

    same_as_deployed = (
        tuple(round(x, 4) for x in gb["weights"]) == tuple(round(x, 4) for x in DEFAULT_WEIGHTS)
        and gb["hold_upper"] == DEFAULT_HOLD_UPPER and gb["hold_lower"] == abs(DEFAULT_HOLD_LOWER) * -1
    )

    out = {
        "n_documents": len(docs),
        "issuers_pooled": POOLED_ISSUERS,
        "issuers_skipped": skipped,
        "window_trading_days": DEFAULT_WINDOW_TRADING_DAYS,
        "outcome_thresholds": {"outcome_upper": OUTCOME_UPPER_DEFAULT, "outcome_lower": OUTCOME_LOWER_DEFAULT},
        "weight_step": WEIGHT_STEP,
        "threshold_grid": {"upper": THRESH_UPPER, "lower": THRESH_LOWER, "asymmetric": True},
        "combos": ncombo,
        "default_config": {"weights": list(DEFAULT_WEIGHTS), "hold_upper": DEFAULT_HOLD_UPPER, "hold_lower": DEFAULT_HOLD_LOWER},
        "global_best": gb,
        "global_best_matches_deployed_default": same_as_deployed,
        "loocv_tuned_accuracy": result["loocv_tuned_accuracy"],
        "loocv_default_accuracy": result["loocv_default_accuracy"],
        "loocv_tuned_balanced_accuracy": result["loocv_tuned_balanced_accuracy"],
        "loocv_default_balanced_accuracy": result["loocv_default_balanced_accuracy"],
        "significance_deployed_weights": sig,
        "interpretation": (
            "If global_best_matches_deployed_default is true and LOOCV tuned/default accuracy are close, "
            "the original weights hold up under leave-one-out refitting at ~2x the N, i.e. real evidence "
            "they transfer to phase2's company mix rather than being an artifact of the original 6-issuer set. "
            "If a different combo wins here, or LOOCV tuned clearly beats LOOCV default, that is real evidence "
            "the deployed weights are stale for the broader universe - not proof from phase2 alone (which can't "
            "support this test at N=101), but from the pooled N which can."
        ),
    }
    summary_dir = OUTPUTS_DIR / "global" / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    path = summary_dir / "pooled_weight_threshold_sweep.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
