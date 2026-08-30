"""
Build Nigel's accuracy-vs-cost context table from already-scored layers.

This is deliberately local-only: it reads cached micro/macro/news scores and
the outcome CSV produced by eval.run_eval, then compares layer configurations
with leave-one-out calibration.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from blend import DEFAULT_WEIGHTS, blend_scores, derive_signal
from eval.calibrate import DEFAULT_HOLD_UPPER, THRESHOLD_CANDIDATES
from report_pipeline import OUTPUTS_DIR
from llm_macro import load_macro_manifest

SUMMARY_DIR = OUTPUTS_DIR / "global" / "summary"
OUTCOME_CSV = SUMMARY_DIR / "global_outcome_calibration.csv"
WEIGHT_STEP = 0.2


@dataclass(frozen=True)
class LayerDoc:
    issuer: str
    document_id: str
    report_date: str
    outcome_label: str
    micro_score: float | None
    macro_score: float | None
    news_score: float | None


CONFIGS = [
    {
        "name": "micro_only",
        "description": "Current earnings-document layer only",
        "layers": ("micro",),
        "cost_layers": ("micro",),
    },
    {
        "name": "micro_plus_macro",
        "description": "Earnings documents plus latest public FOMC minutes",
        "layers": ("micro", "macro"),
        "cost_layers": ("micro", "macro"),
    },
    {
        "name": "micro_plus_news",
        "description": "Earnings documents plus pre-earnings news digest",
        "layers": ("micro", "news"),
        "cost_layers": ("micro", "news"),
    },
    {
        "name": "micro_plus_macro_plus_news",
        "description": "Earnings documents plus macro plus news",
        "layers": ("micro", "macro", "news"),
        "cost_layers": ("micro", "macro", "news"),
    },
    {
        "name": "macro_only",
        "description": "Latest public FOMC minutes only",
        "layers": ("macro",),
        "cost_layers": ("macro",),
    },
    {
        "name": "news_only",
        "description": "Pre-earnings news digest only",
        "layers": ("news",),
        "cost_layers": ("news",),
    },
]


def _parse_float(value: str) -> float | None:
    if value == "":
        return None
    return float(value)


def load_docs() -> list[LayerDoc]:
    with OUTCOME_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [
        LayerDoc(
            issuer=row["issuer"],
            document_id=row["document_id"],
            report_date=row["report_date"],
            outcome_label=row["outcome_label"],
            micro_score=_parse_float(row["micro_score"]),
            macro_score=_parse_float(row["macro_score"]),
            news_score=_parse_float(row["news_score"]),
        )
        for row in rows
    ]


def _layer_score(doc: LayerDoc, layer: str) -> float | None:
    return getattr(doc, f"{layer}_score")


def _weight_grid(layers: tuple[str, ...]) -> list[dict[str, float]]:
    if len(layers) == 1:
        return [{layers[0]: 1.0}]

    steps = [round(i * WEIGHT_STEP, 1) for i in range(int(round(1.0 / WEIGHT_STEP)) + 1)]
    weights: list[dict[str, float]] = []

    def build(prefix: list[float], remaining_layers: tuple[str, ...]) -> None:
        if len(remaining_layers) == 1:
            final_weight = round(1.0 - sum(prefix), 1)
            if 0.0 <= final_weight <= 1.0:
                weights.append(dict(zip(layers, prefix + [final_weight])))
            return
        for step in steps:
            if sum(prefix) + step <= 1.0:
                build(prefix + [step], remaining_layers[1:])

    build([], layers)
    return weights


def _as_blend_tuple(layer_weights: dict[str, float]) -> tuple[float, float, float]:
    return (
        layer_weights.get("micro", 0.0),
        layer_weights.get("macro", 0.0),
        layer_weights.get("news", 0.0),
    )


def _can_score(doc: LayerDoc, layers: tuple[str, ...]) -> bool:
    return any(_layer_score(doc, layer) is not None for layer in layers)


def _predict(doc: LayerDoc, layer_weights: dict[str, float], threshold: float) -> str | None:
    if not _can_score(doc, tuple(layer_weights)):
        return None
    try:
        score = blend_scores(doc.micro_score, doc.macro_score, doc.news_score, _as_blend_tuple(layer_weights))
    except ValueError:
        return None
    return derive_signal(score, threshold, -threshold)


def _accuracy(predictions: list[str], labels: list[str]) -> float:
    if not labels:
        return 0.0
    return sum(pred == label for pred, label in zip(predictions, labels)) / len(labels)


def sweep_config(docs: list[LayerDoc], layers: tuple[str, ...]) -> tuple[dict[str, float], float, float]:
    best: tuple[float, float, dict[str, float], float] | None = None
    default_like = {"micro": DEFAULT_WEIGHTS[0], "macro": DEFAULT_WEIGHTS[1], "news": DEFAULT_WEIGHTS[2]}

    for weights in _weight_grid(layers):
        for threshold in THRESHOLD_CANDIDATES:
            predictions: list[str] = []
            labels: list[str] = []
            for doc in docs:
                prediction = _predict(doc, weights, threshold)
                if prediction is None:
                    continue
                predictions.append(prediction)
                labels.append(doc.outcome_label)
            accuracy = _accuracy(predictions, labels)
            distance = sum(abs(weights.get(layer, 0.0) - default_like.get(layer, 0.0)) for layer in layers)
            distance += abs(threshold - DEFAULT_HOLD_UPPER)
            candidate = (accuracy, -distance, weights, threshold)
            if best is None or candidate[:2] > best[:2]:
                best = candidate

    if best is None:
        raise ValueError(f"No valid weights for layers {layers}")
    accuracy, _, weights, threshold = best
    return weights, threshold, accuracy


def loocv_config(docs: list[LayerDoc], layers: tuple[str, ...]) -> dict[str, Any]:
    eligible_docs = [doc for doc in docs if _can_score(doc, layers)]
    folds = []
    for index, held_out in enumerate(eligible_docs):
        calibration = eligible_docs[:index] + eligible_docs[index + 1 :]
        weights, threshold, _ = sweep_config(calibration, layers)
        prediction = _predict(held_out, weights, threshold)
        if prediction is None:
            continue
        folds.append(
            {
                "document_id": held_out.document_id,
                "issuer": held_out.issuer,
                "outcome_label": held_out.outcome_label,
                "prediction": prediction,
                "correct": prediction == held_out.outcome_label,
                "weights": weights,
                "threshold": threshold,
            }
        )

    labels = [fold["outcome_label"] for fold in folds]
    predictions = [fold["prediction"] for fold in folds]
    modal_weights = Counter(json.dumps(fold["weights"], sort_keys=True) for fold in folds).most_common(1)[0][0]
    modal_threshold = Counter(fold["threshold"] for fold in folds).most_common(1)[0][0]
    return {
        "n_documents": len(folds),
        "accuracy": _accuracy(predictions, labels),
        "correct": sum(fold["correct"] for fold in folds),
        "modal_weights": json.loads(modal_weights),
        "modal_threshold": modal_threshold,
        "folds": folds,
    }


def _json_cost(path: Path) -> float:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cost_log = payload.get("cost_log")
    if cost_log:
        return float(cost_log.get("estimated_cost_usd", 0.0))
    return 0.0


def _micro_cost(doc: LayerDoc) -> float:
    result_path = OUTPUTS_DIR / doc.issuer / "results" / f"{doc.document_id}.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    run_id = payload.get("run_meta", {}).get("run_id")
    log_path = OUTPUTS_DIR / doc.issuer / "logs" / "first_run_costs.jsonl"
    if not log_path.exists():
        return 0.0
    fallback = 0.0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("document_id") != doc.document_id:
            continue
        fallback = float(record.get("estimated_cost_usd", 0.0))
        if run_id and record.get("run_id") == run_id:
            return fallback
    return fallback


def _news_cost(doc: LayerDoc) -> float:
    path = OUTPUTS_DIR / "news" / doc.issuer / "results" / f"{doc.document_id}_NEWS.json"
    return _json_cost(path) if path.exists() else 0.0


def _macro_costs_used(docs: list[LayerDoc]) -> float:
    meetings = load_macro_manifest()
    used_meeting_ids = set()
    for doc in docs:
        eligible = [meeting for meeting in meetings if meeting["minutes_release_date"] <= doc.report_date]
        if not eligible:
            continue
        latest = max(eligible, key=lambda meeting: meeting["minutes_release_date"])
        used_meeting_ids.add(latest["document_id"])

    total = 0.0
    for document_id in used_meeting_ids:
        path = OUTPUTS_DIR / "macro" / "results" / f"{document_id}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            total += float(payload.get("cost_log", {}).get("estimated_cost_usd", 0.0))
    return total


def cost_for_config(docs: list[LayerDoc], cost_layers: tuple[str, ...]) -> float:
    total = 0.0
    if "micro" in cost_layers:
        total += sum(_micro_cost(doc) for doc in docs)
    if "news" in cost_layers:
        total += sum(_news_cost(doc) for doc in docs)
    if "macro" in cost_layers:
        total += _macro_costs_used(docs)
    return total


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    docs = load_docs()
    rows: list[dict[str, Any]] = []
    detailed: dict[str, Any] = {}
    for config in CONFIGS:
        result = loocv_config(docs, config["layers"])
        cost = cost_for_config(docs, config["cost_layers"])
        rows.append(
            {
                "configuration": config["name"],
                "description": config["description"],
                "n_documents": result["n_documents"],
                "loocv_accuracy": round(result["accuracy"], 4),
                "correct": result["correct"],
                "estimated_cost_usd": round(cost, 6),
                "estimated_cost_per_doc_usd": round(cost / result["n_documents"], 6),
                "modal_weights": json.dumps(result["modal_weights"], sort_keys=True),
                "modal_sentiment_hold_threshold": result["modal_threshold"],
            }
        )
        detailed[config["name"]] = result

    csv_path = SUMMARY_DIR / "context_accuracy_cost_table.csv"
    json_path = SUMMARY_DIR / "context_accuracy_cost_table.json"
    write_csv(csv_path, rows)
    json_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source_outcome_csv": str(OUTCOME_CSV),
                "rows": rows,
                "details": detailed,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    for row in rows:
        print(
            f"{row['configuration']}: accuracy={row['loocv_accuracy']:.2f} "
            f"({row['correct']}/{row['n_documents']}), cost=${row['estimated_cost_usd']:.4f}, "
            f"weights={row['modal_weights']}, hold=+/-{row['modal_sentiment_hold_threshold']}"
        )
    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
