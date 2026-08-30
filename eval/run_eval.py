"""
eval/run_eval.py
CLI: python -m eval.run_eval [--issuers boeing,jpm,netflix]

Pools documents across ALL issuers before calibrating - the sentiment
threshold and blend weights are meant to be one shared answer applied to
every company, not tuned separately per issuer (which would overfit even
harder at N=4/issuer than the already-small pooled N).

Fetches actual price outcomes, joins them with already-computed micro/macro/
news scores, runs both the threshold-only and blend-weight+threshold LOOCV
calibrations over the pooled set, and writes:
  outputs/global/summary/global_outcome_calibration.csv  (per-document rows, tagged by issuer)
  outputs/global/summary/global_calibration_summary.json (LOOCV aggregate)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from report_pipeline import OUTPUTS_DIR
from blend import DEFAULT_WEIGHTS, PHASE2_ISSUERS
from eval.calibrate import DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER, Document, loocv_blend, loocv_threshold_only
from eval.outcomes import (
    DEFAULT_WINDOW_TRADING_DAYS,
    OUTCOME_LOWER_DEFAULT,
    OUTCOME_UPPER_DEFAULT,
    collect_outcomes_for_issuer,
)

import llm_macro
import llm_news
import quant_layer

ALL_ISSUERS = ["boeing", "jpm", "netflix", "bank_of_america", "disney", "target"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calibrate the sentiment threshold and blend weights against actual price "
            "outcomes, pooled across issuers so the result is one shared answer."
        )
    )
    parser.add_argument(
        "--issuers",
        default="",
        help=(
            "Comma-separated issuers to pool. Default: empty, meaning bare invocation "
            "pools every phase2 issuer (same as --phase2-all) - phase2 is the only "
            "active track. Pass this explicitly (e.g. --issuers boeing,jpm,...) to "
            "touch the retired pre-phase2 production issuers."
        ),
    )
    parser.add_argument(
        "--phase2-all",
        action="store_true",
        help=(
            "Pool every registered phase2 issuer (blend.PHASE2_ISSUERS, 'p2_' prefixed) "
            "instead of hand-typing --issuers. Avoids silently omitting a ticker from the "
            "phase2 calibration rebuild whenever a new p2_ issuer is onboarded. "
            "This is also what a bare invocation (no flags) now does by default. "
            "Overrides --issuers if both are given."
        ),
    )
    parser.add_argument("--window-trading-days", type=int, default=DEFAULT_WINDOW_TRADING_DAYS)
    parser.add_argument("--outcome-upper", type=float, default=OUTCOME_UPPER_DEFAULT)
    parser.add_argument("--outcome-lower", type=float, default=OUTCOME_LOWER_DEFAULT)
    parser.add_argument(
        "--output-suffix",
        default="",
        help=(
            "Optional suffix appended to the output filenames, e.g. 'phase2' writes "
            "global_outcome_calibration_phase2.csv / global_calibration_summary_phase2.json "
            "instead of the production defaults, so an alternate-track run never "
            "overwrites the production calibration files."
        ),
    )
    return parser.parse_args()


def _base_issuer(issuer: str) -> str:
    """Map an output-folder label like 'boeing_ensemble3' back to the real
    issuer name ('boeing') so macro/news lookups (which are keyed by the
    manifest issuer, not the output folder) still resolve for --variant
    output folders used to A/B test a prompt or ensemble setting."""
    for known in ALL_ISSUERS:
        if issuer == known or issuer.startswith(f"{known}_"):
            return known
    return issuer


def build_documents_for_issuer(issuer: str, window_trading_days: int, outcome_upper: float, outcome_lower: float,
                               exit_on_open: bool = False):
    results_dir = OUTPUTS_DIR / issuer / "results"
    outcomes = collect_outcomes_for_issuer(issuer, results_dir, window_trading_days, outcome_upper, outcome_lower, exit_on_open)
    news_issuer = _base_issuer(issuer)

    pairs = []
    for outcome in outcomes:
        payload = json.loads((results_dir / f"{outcome.document_id}.json").read_text(encoding="utf-8"))
        micro_score = payload["sentiment"]["score"]
        report_date = payload["report_metadata"]["report_date"]

        macro_result = llm_macro.get_macro_score_for_date(report_date)
        macro_score = macro_result["sentiment"]["score"] if macro_result else None

        news_result = llm_news.get_news_score(news_issuer, outcome.document_id)
        news_score = news_result["sentiment"]["score"] if news_result else None

        quant_result = quant_layer.get_quant_score(news_issuer, outcome.document_id)
        quant_score = quant_result["sentiment"]["score"] if quant_result else None

        document = Document(
            document_id=outcome.document_id,
            issuer=issuer,
            outcome_label=outcome.outcome_label,
            micro_score=micro_score,
            macro_score=macro_score,
            news_score=news_score,
            quant_score=quant_score,
        )
        pairs.append((outcome, document))
    return pairs


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    if args.phase2_all or not args.issuers.strip():
        issuers = [f"p2_{name}" for name in PHASE2_ISSUERS]
    else:
        issuers = [issuer.strip() for issuer in args.issuers.split(",") if issuer.strip()]

    pairs = []
    for issuer in issuers:
        issuer_pairs = build_documents_for_issuer(
            issuer, args.window_trading_days, args.outcome_upper, args.outcome_lower
        )
        pairs.extend(issuer_pairs)

    if not pairs:
        print(f"No documents with usable outcomes for issuers {issuers}")
        return 1

    outcomes = [pair[0] for pair in pairs]
    documents = [pair[1] for pair in pairs]

    threshold_result = loocv_threshold_only(documents)
    blend_result = loocv_blend(documents)

    summary_dir = OUTPUTS_DIR / "global" / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)

    csv_rows = []
    for outcome, doc, t_fold, b_fold in zip(outcomes, documents, threshold_result["folds"], blend_result["folds"]):
        csv_rows.append(
            {
                "issuer": doc.issuer,
                "document_id": doc.document_id,
                "ticker": outcome.ticker,
                "report_date": outcome.report_date,
                "micro_score": doc.micro_score,
                "macro_score": doc.macro_score,
                "news_score": doc.news_score,
                "quant_score": doc.quant_score,
                "forward_return": outcome.forward_return,
                "window_trading_days": outcome.window_trading_days,
                "outcome_label": outcome.outcome_label,
                "predicted_signal_default": t_fold["default_prediction"],
                "correct_default": t_fold["correct_default"],
                "predicted_signal_tuned": t_fold["tuned_prediction"],
                "correct_tuned": t_fold["correct_tuned"],
                "tuned_hold_upper": t_fold["tuned_hold_upper"],
                "blend_predicted_signal_default": b_fold["default_prediction"],
                "blend_correct_default": b_fold["correct_default"],
                "blend_predicted_signal_tuned": b_fold["tuned_prediction"],
                "blend_correct_tuned": b_fold["correct_tuned"],
                "blend_tuned_weights": b_fold["tuned_weights"],
            }
        )
    suffix = f"_{args.output_suffix}" if args.output_suffix else ""
    csv_path = summary_dir / f"global_outcome_calibration{suffix}.csv"
    write_csv(csv_path, csv_rows)

    summary_payload = {
        "issuers": issuers,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "outcome_thresholds": {"outcome_upper": args.outcome_upper, "outcome_lower": args.outcome_lower},
        "outcome_window_trading_days": args.window_trading_days,
        "default_sentiment_thresholds": {"hold_upper": DEFAULT_HOLD_UPPER, "hold_lower": DEFAULT_HOLD_LOWER},
        "default_blend_weights": {
            "micro": DEFAULT_WEIGHTS[0],
            "macro": DEFAULT_WEIGHTS[1],
            "news": DEFAULT_WEIGHTS[2],
            "quant": DEFAULT_WEIGHTS[3],
        },
        "note": (
            "Pooled across all issuers so the tuned threshold/weights are one shared "
            "answer, not overfit per issuer. Still LOOCV at a small pooled N (one fold "
            "per document) - a tuned choice per fold, not one frozen answer. Modal values "
            "are the 'if you had to pick one' choice; the tuned-vs-default accuracy "
            "comparison is the primary result."
        ),
        "threshold_only": {
            "loocv_folds": threshold_result["folds"],
            "tuned_accuracy": threshold_result["tuned_accuracy"],
            "default_accuracy": threshold_result["default_accuracy"],
            "modal_tuned_hold_upper": threshold_result["modal_tuned_hold_upper"],
            "modal_tuned_hold_lower": threshold_result["modal_tuned_hold_lower"],
        },
        "blend_weight_and_threshold": {
            "loocv_folds": blend_result["folds"],
            "tuned_accuracy": blend_result["tuned_accuracy"],
            "default_accuracy": blend_result["default_accuracy"],
            "modal_tuned_weights": blend_result["modal_tuned_weights"],
            "modal_tuned_hold_upper": blend_result["modal_tuned_hold_upper"],
            "modal_tuned_hold_lower": blend_result["modal_tuned_hold_lower"],
        },
        "n_documents": threshold_result["n_documents"],
    }
    json_path = summary_dir / f"global_calibration_summary{suffix}.json"
    json_path.write_text(json.dumps(summary_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        f"Pooled across {issuers} (N={threshold_result['n_documents']})"
    )
    print(
        f"Threshold-only LOOCV: tuned_accuracy={threshold_result['tuned_accuracy']:.2f} "
        f"default_accuracy={threshold_result['default_accuracy']:.2f}"
    )
    print(
        f"Blend weight+threshold LOOCV: tuned_accuracy={blend_result['tuned_accuracy']:.2f} "
        f"default_accuracy={blend_result['default_accuracy']:.2f}"
    )
    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
