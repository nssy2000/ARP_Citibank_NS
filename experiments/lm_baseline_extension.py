"""
experiments/lm_baseline_extension.py
Item D: Loughran-McDonald baseline on the 93-event extension corpus.

Uses pysentiment2 (Loughran-McDonald word lists), the same package as
experiments/lm_baseline.py. No API calls.

Design decisions:
  - Extension is treated as a PURE EVAL SET. Phase2 dev-set thresholds
    (from lm_baseline_dev_thresholds.json, fitted on the earliest 20% of
    N=233 phase2 events) are applied frozen, without refitting on extension.
    Refitting on an ~19-event extension dev set would be meaningless.
  - Overnight returns sourced from backtest_equity_extension_2026_08_13.csv
    (LLM-rater rows, `gap` column), not from returns_matrix.csv (which only
    covers the frozen N=268 phase2 universe).
  - Grading band: pre-registered +-2% raw overnight (group sheet convention).

Outputs:
  outputs/global/summary/lm_baseline_extension_results.csv
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pysentiment2 as ps

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
SUMMARY_DIR = OUTPUTS_DIR / "global" / "summary"

EXT_CALIBRATION_CSV = SUMMARY_DIR / "global_outcome_calibration_extension_2026_08_13.csv"
# One source of truth for which extension-gap vintage is current; four files
# used to carry their own copy of this name. See eval/extension_gaps.py.
# BASE_DIR has to be on the path for that import to resolve when this file is run
# as a script rather than as a module - walkforward_combined and
# section_ablation_extension already do this; these two did not, so they could
# only be started with PYTHONPATH set.
sys.path.insert(0, str(BASE_DIR))
from eval.extension_gaps import CURRENT_GAP_FILE as EXT_BACKTEST_CSV  # noqa: E402
DEV_THRESHOLDS_JSON = SUMMARY_DIR / "lm_baseline_dev_thresholds.json"

OUT_CSV = SUMMARY_DIR / "lm_baseline_extension_results.csv"

OVERNIGHT_BAND = 0.02
LLM_RATER_NAME = "LLM (DeepSeek)"

_LM = ps.LM()


def _lm_score(text: str) -> tuple[float, int, int, int]:
    tokens = _LM.tokenize(text)
    scored = _LM.get_score(tokens)
    pos, neg = scored["Positive"], scored["Negative"]
    total = len(tokens)
    score = (pos - neg) / total if total else 0.0
    return score, pos, neg, total


def _overnight_outcome(ret: float) -> str:
    if ret > OVERNIGHT_BAND:
        return "BUY"
    if ret < -OVERNIGHT_BAND:
        return "SELL"
    return "HOLD"


def _predict(score: float, upper: float, lower: float) -> str:
    if score > upper:
        return "BUY"
    if score < lower:
        return "SELL"
    return "HOLD"


def _load_extension_overnight_returns() -> dict[str, float]:
    """Load raw overnight gaps from the extension backtest CSV, keyed on document_id.

    NOT on (ticker, report_date). The calibration roster is a frozen 2026-08-13
    artefact whose report_date column still carries the first-of-month
    placeholders, so a date-keyed join silently drops every event whose anchor has
    since been corrected - four Hermes events on 2026-08-24. document_id survives
    re-anchoring.
    """
    gaps: dict[str, float] = {}
    with open(EXT_BACKTEST_CSV, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if "document_id" not in (reader.fieldnames or []):
            raise SystemExit(
                f"{EXT_BACKTEST_CSV.name} has no document_id column. Vintages before\n"
                f"2026-08-24 were keyed on (ticker, report_date). Regenerate with\n"
                f"`python -m eval.extension_gaps` and repoint CURRENT_GAP_FILE.")
        for r in reader:
            if r["rater"] != LLM_RATER_NAME:
                continue
            try:
                gaps[r["document_id"]] = float(r["gap"])
            except (ValueError, KeyError):
                pass
    if not gaps:
        raise SystemExit(
            f"{EXT_BACKTEST_CSV.name} yielded no gaps. The loop above swallows\n"
            f"ValueError and KeyError, so a changed column set or a comment line\n"
            f"before the header reads as zero events rather than as an error.")
    return gaps


def main() -> None:
    # Load phase2 dev thresholds (frozen; extension is pure eval)
    thresholds = json.loads(DEV_THRESHOLDS_JSON.read_text(encoding="utf-8"))
    lm_upper = thresholds["fitted_upper"]
    lm_lower = thresholds["fitted_lower"]
    print(f"Phase2 LM thresholds (frozen, applied to extension as pure eval):")
    print(f"  upper={lm_upper:.6f}, lower={lm_lower:.6f}")
    print(f"  Dev date range: {thresholds['dev_date_range']}")
    print()

    # Load extension overnight returns
    overnight_gaps = _load_extension_overnight_returns()
    print(f"Loaded overnight returns for {len(overnight_gaps)} extension events")

    # Load extension calibration CSV
    ext_events = []
    with open(EXT_CALIBRATION_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ext_events.append(dict(r))
    print(f"Extension calibration: {len(ext_events)} events")

    # Process each event
    results = []
    skipped_no_text = 0
    skipped_no_ret = 0

    for ev in ext_events:
        doc_id = ev["document_id"]
        ticker = ev["ticker"]
        report_date = ev["report_date"]
        issuer = ev["issuer"]

        # Overnight return
        if doc_id not in overnight_gaps:
            skipped_no_ret += 1
            continue
        gap = overnight_gaps[doc_id]
        outcome = _overnight_outcome(gap)

        # Extracted text (from extension variant output dir)
        text_path = OUTPUTS_DIR / issuer / "extracted" / f"{doc_id}.txt"
        if not text_path.exists():
            skipped_no_text += 1
            continue
        text = text_path.read_text(encoding="utf-8", errors="replace")

        # LM score
        lm_sc, lm_pos, lm_neg, lm_tokens = _lm_score(text)
        lm_signal = _predict(lm_sc, lm_upper, lm_lower)
        lm_correct = int(lm_signal == outcome) if outcome != "HOLD" else None

        model_signal = ev.get("blend_predicted_signal_default", "")
        model_correct = int(model_signal == outcome) if outcome != "HOLD" else None

        results.append({
            "document_id": doc_id,
            "ticker": ticker,
            "report_date": report_date,
            "ret_overnight": gap,
            "outcome_label": outcome,
            "lm_score": round(lm_sc, 8),
            "lm_predicted_signal": lm_signal,
            "lm_correct": lm_correct,
            "model_predicted_signal": model_signal,
            "model_correct": model_correct,
            "lm_pos": lm_pos,
            "lm_neg": lm_neg,
            "lm_tokens": lm_tokens,
        })

    print(f"Skipped: {skipped_no_ret} missing overnight return, "
          f"{skipped_no_text} missing extracted text")
    print(f"Processed: {len(results)} extension events")
    print()

    # Grade: FLAT-excluded (only BUY or SELL outcomes count)
    graded = [r for r in results if r["outcome_label"] != "HOLD"]
    n_graded = len(graded)
    n_movers = n_graded  # events that moved >2% either direction

    # LM accuracy
    lm_correct_count = sum(1 for r in graded if r["lm_correct"] == 1)
    lm_acc = lm_correct_count / n_graded if n_graded else float("nan")

    # Model accuracy
    model_correct_count = sum(1 for r in graded if r["model_correct"] == 1)
    model_acc = model_correct_count / n_graded if n_graded else float("nan")

    # Majority-direction floor (always-DOWN on graded set)
    always_down_correct = sum(1 for r in graded if r["outcome_label"] == "SELL")
    floor_acc = always_down_correct / n_graded if n_graded else float("nan")

    # LM trade rate (fraction calling BUY or SELL)
    lm_trades = sum(1 for r in results if r["lm_predicted_signal"] != "HOLD")
    model_trades = sum(1 for r in results if r["model_predicted_signal"] != "HOLD")

    print(f"{'='*70}")
    print(f"Item D: LM Baseline on Extension Corpus (N={len(results)} events)")
    print(f"{'='*70}")
    print(f"Graded events (|ret|>2%):  {n_graded} / {len(results)}")
    print()
    print(f"{'Metric':40s}  {'LM':>8}  {'Model':>8}  {'Floor':>8}")
    print(f"{'-'*70}")
    print(f"{'Accuracy (FLAT-excluded)':40s}  {lm_acc:>8.1%}  {model_acc:>8.1%}  {floor_acc:>8.1%}")
    print(f"{'Correct / graded':40s}  {lm_correct_count:>3}/{n_graded:>3}    {model_correct_count:>3}/{n_graded:>3}    {always_down_correct:>3}/{n_graded:>3}")
    print(f"{'Trade rate (% BUY or SELL)':40s}  {lm_trades/len(results):>8.1%}  {model_trades/len(results):>8.1%}  {'100%':>8}")
    print()

    # Note on thresholds
    print(f"Note: LM thresholds applied from phase2 dev set (frozen).")
    print(f"  LM upper={lm_upper:.6f}, lower={lm_lower:.6f}")
    print(f"  Extension is a pure eval set — no refitting on extension events.")
    print(f"  Model signal from blend_predicted_signal_default (deployed weights 0.55/0.45/0/0).")
    print()

    # Signal distribution
    for label, sig_key in [("LM", "lm_predicted_signal"), ("Model", "model_predicted_signal")]:
        from collections import Counter
        dist = Counter(r[sig_key] for r in results)
        print(f"  {label} signal distribution: "
              f"BUY={dist['BUY']}, HOLD={dist['HOLD']}, SELL={dist['SELL']}")

    # Write CSV
    fields = [
        "document_id", "ticker", "report_date", "ret_overnight", "outcome_label",
        "lm_score", "lm_predicted_signal", "lm_correct",
        "model_predicted_signal", "model_correct",
        "lm_pos", "lm_neg", "lm_tokens",
    ]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        fh.write(f"# LM baseline on extension corpus\n")
        fh.write(f"# N={len(results)} extension events\n")
        fh.write(f"# Graded (|ret|>2%): {n_graded}\n")
        fh.write(f"# LM thresholds (phase2 dev, frozen): upper={lm_upper:.8f}, lower={lm_lower:.8f}\n")
        fh.write(f"# Grading band: +-2% raw overnight (pre-registered)\n")
        fh.write(f"# Extension is pure eval; no dev refitting.\n")
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(results)
    print(f"\nWrote {OUT_CSV}")


if __name__ == "__main__":
    main()
