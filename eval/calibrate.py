"""
eval/calibrate.py
Leave-one-out cross-validation across each issuer's quarters. N is too small
(4 quarters/issuer) for a train/test split - LOOCV uses every document as the
held-out test exactly once, giving one independent tuned-vs-default
comparison per quarter instead of resting on a single arbitrary split.

Two calibrations are run per issuer:
  1. Threshold-only: tunes hold_upper/hold_lower against the micro layer's
     sentiment score alone.
  2. Blend weight + threshold, jointly: tunes (weights, hold_upper/hold_lower)
     together against the blended score.

Neither produces one frozen answer - LOOCV yields a tuned choice per fold.
The MODAL choice across folds is reported as "the recommended value if you
had to pick one," but the primary output is the accuracy comparison
(tuned vs. sensible-default), not the modal value on its own.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from blend import (
    DEFAULT_HOLD_LOWER,
    DEFAULT_HOLD_UPPER,
    DEFAULT_WEIGHTS,
    blend_scores,
    derive_signal,
)

THRESHOLD_CANDIDATES = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
WEIGHT_STEP = 0.2


def _weight_grid() -> list[tuple[float, float, float, float]]:
    """Enumerate (micro, macro, news, quant) weights on a WEIGHT_STEP grid that
    sum to 1.0. Adding the quant dimension grows the search space (21 -> 56
    combos at step 0.2), so overfitting risk rises at this N - that is exactly
    what the LOOCV held-out comparison is there to catch."""
    n_steps = int(round(1.0 / WEIGHT_STEP))
    steps = [round(i * WEIGHT_STEP, 1) for i in range(n_steps + 1)]
    grid = []
    for w_micro in steps:
        for w_macro in steps:
            for w_news in steps:
                w_quant = round(1.0 - w_micro - w_macro - w_news, 1)
                if 0.0 <= w_quant <= 1.0:
                    grid.append((w_micro, w_macro, w_news, w_quant))
    return grid


WEIGHT_GRID = _weight_grid()


@dataclass(frozen=True)
class Document:
    document_id: str
    issuer: str
    outcome_label: str
    micro_score: float
    macro_score: float | None
    news_score: float | None
    quant_score: float | None = None


def _accuracy(predictions: list[str], labels: list[str]) -> float:
    if not labels:
        return 0.0
    correct = sum(1 for prediction, label in zip(predictions, labels) if prediction == label)
    return correct / len(labels)


def sweep_thresholds(calibration_docs: list[Document]) -> tuple[float, float, float]:
    """Grid-searches a symmetric hold_upper == -hold_lower over
    THRESHOLD_CANDIDATES. Ties are broken by preferring the candidate
    closest to the project default (0.15), to avoid overfitting to a
    handful of calibration points."""
    best_threshold = DEFAULT_HOLD_UPPER
    best_accuracy = -1.0
    for threshold in THRESHOLD_CANDIDATES:
        predictions = [derive_signal(doc.micro_score, threshold, -threshold) for doc in calibration_docs]
        labels = [doc.outcome_label for doc in calibration_docs]
        accuracy = _accuracy(predictions, labels)
        is_better = accuracy > best_accuracy or (
            accuracy == best_accuracy
            and abs(threshold - DEFAULT_HOLD_UPPER) < abs(best_threshold - DEFAULT_HOLD_UPPER)
        )
        if is_better:
            best_accuracy = accuracy
            best_threshold = threshold
    return best_threshold, -best_threshold, best_accuracy


def loocv_threshold_only(documents: list[Document]) -> dict[str, Any]:
    folds = []
    for index, held_out in enumerate(documents):
        calibration_set = documents[:index] + documents[index + 1 :]
        tuned_upper, tuned_lower, _ = sweep_thresholds(calibration_set)

        tuned_prediction = derive_signal(held_out.micro_score, tuned_upper, tuned_lower)
        default_prediction = derive_signal(held_out.micro_score, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER)

        folds.append(
            {
                "held_out_document_id": held_out.document_id,
                "tuned_hold_upper": tuned_upper,
                "tuned_hold_lower": tuned_lower,
                "outcome_label": held_out.outcome_label,
                "tuned_prediction": tuned_prediction,
                "default_prediction": default_prediction,
                "correct_tuned": tuned_prediction == held_out.outcome_label,
                "correct_default": default_prediction == held_out.outcome_label,
            }
        )

    tuned_accuracy = _accuracy([f["tuned_prediction"] for f in folds], [f["outcome_label"] for f in folds])
    default_accuracy = _accuracy([f["default_prediction"] for f in folds], [f["outcome_label"] for f in folds])
    modal_upper = Counter(f["tuned_hold_upper"] for f in folds).most_common(1)[0][0]

    return {
        "folds": folds,
        "tuned_accuracy": tuned_accuracy,
        "default_accuracy": default_accuracy,
        "modal_tuned_hold_upper": modal_upper,
        "modal_tuned_hold_lower": -modal_upper,
        "n_documents": len(documents),
    }


def sweep_blend(calibration_docs: list[Document]) -> tuple[tuple[float, float, float], float, float, float]:
    """Jointly grid-searches (weights, threshold). A bigger search space than
    sweep_thresholds at the same N, so overfitting risk is higher - ties are
    broken by preferring the combination closest to the sensible defaults
    (0.6/0.2/0.2 weights, 0.15 threshold)."""
    best = None
    for weights in WEIGHT_GRID:
        for threshold in THRESHOLD_CANDIDATES:
            predictions = []
            labels = []
            for doc in calibration_docs:
                try:
                    blended = blend_scores(
                        doc.micro_score, doc.macro_score, doc.news_score, doc.quant_score, weights
                    )
                except ValueError:
                    predictions = []
                    break
                predictions.append(derive_signal(blended, threshold, -threshold))
                labels.append(doc.outcome_label)
            if not predictions:
                continue
            accuracy = _accuracy(predictions, labels)

            distance_from_default = sum(abs(w - d) for w, d in zip(weights, DEFAULT_WEIGHTS)) + abs(
                threshold - DEFAULT_HOLD_UPPER
            )
            candidate = (accuracy, -distance_from_default, weights, threshold)
            if best is None or candidate[:2] > best[:2]:
                best = candidate

    accuracy, _, weights, threshold = best
    return weights, threshold, -threshold, accuracy


def loocv_blend(documents: list[Document]) -> dict[str, Any]:
    folds = []
    for index, held_out in enumerate(documents):
        calibration_set = documents[:index] + documents[index + 1 :]
        tuned_weights, tuned_upper, tuned_lower, _ = sweep_blend(calibration_set)

        try:
            held_out_blended_tuned = blend_scores(
                held_out.micro_score, held_out.macro_score, held_out.news_score,
                held_out.quant_score, tuned_weights
            )
        except ValueError:
            held_out_blended_tuned = blend_scores(
                held_out.micro_score, held_out.macro_score, held_out.news_score,
                held_out.quant_score, DEFAULT_WEIGHTS
            )
            tuned_weights = DEFAULT_WEIGHTS
        held_out_blended_default = blend_scores(
            held_out.micro_score, held_out.macro_score, held_out.news_score,
            held_out.quant_score, DEFAULT_WEIGHTS
        )

        tuned_prediction = derive_signal(held_out_blended_tuned, tuned_upper, tuned_lower)
        default_prediction = derive_signal(held_out_blended_default, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER)

        folds.append(
            {
                "held_out_document_id": held_out.document_id,
                "tuned_weights": tuned_weights,
                "tuned_hold_upper": tuned_upper,
                "tuned_hold_lower": tuned_lower,
                "outcome_label": held_out.outcome_label,
                "tuned_prediction": tuned_prediction,
                "default_prediction": default_prediction,
                "correct_tuned": tuned_prediction == held_out.outcome_label,
                "correct_default": default_prediction == held_out.outcome_label,
            }
        )

    tuned_accuracy = _accuracy([f["tuned_prediction"] for f in folds], [f["outcome_label"] for f in folds])
    default_accuracy = _accuracy([f["default_prediction"] for f in folds], [f["outcome_label"] for f in folds])
    modal_weights = Counter(f["tuned_weights"] for f in folds).most_common(1)[0][0]
    modal_upper = Counter(f["tuned_hold_upper"] for f in folds).most_common(1)[0][0]

    return {
        "folds": folds,
        "tuned_accuracy": tuned_accuracy,
        "default_accuracy": default_accuracy,
        "modal_tuned_weights": modal_weights,
        "modal_tuned_hold_upper": modal_upper,
        "modal_tuned_hold_lower": -modal_upper,
        "n_documents": len(documents),
    }
