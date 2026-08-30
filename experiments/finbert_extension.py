"""
experiments/finbert_extension.py
Item D: FinBERT baseline on the 93-event extension corpus.

Uses ProsusAI/finbert with the same chunk-scoring logic as
experiments/finbert_baseline.py. Phase2 dev thresholds (from
finbert_dev_thresholds.json, fitted on earliest 20% of N=233 phase2 events)
applied frozen — extension is a pure eval set.

Design decisions mirror lm_baseline_extension.py:
  - Extension is treated as PURE EVAL. Phase2 dev thresholds frozen.
  - Overnight returns sourced from backtest_equity_extension_2026_08_13.csv
    (LLM-rater rows, `gap` column).
  - Grading band: pre-registered +-2% raw overnight.

Outputs:
  outputs/global/summary/finbert_extension_results.csv
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

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
FINBERT_THRESHOLDS_JSON = SUMMARY_DIR / "finbert_dev_thresholds.json"

OUT_CSV = SUMMARY_DIR / "finbert_extension_results.csv"

OVERNIGHT_BAND = 0.02
LLM_RATER_NAME = "LLM (DeepSeek)"
FINBERT_MODEL_NAME = "ProsusAI/finbert"
FINBERT_MAX_TOKENS = 512


def _load_finbert():
    print(f"Loading FinBERT ({FINBERT_MODEL_NAME})...")
    tokenizer = AutoTokenizer.from_pretrained(FINBERT_MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(FINBERT_MODEL_NAME)
    model.eval()
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = model.to(device)
    print(f"FinBERT loaded on {device}")
    return tokenizer, model, device


def _chunk_text(text: str, tokenizer) -> list[dict]:
    full_encoding = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    token_ids = full_encoding["input_ids"]
    offsets = full_encoding["offset_mapping"]
    if not token_ids:
        return []
    usable = FINBERT_MAX_TOKENS - 2
    chunks = []
    i = 0
    while i < len(token_ids):
        end = min(i + usable, len(token_ids))
        start_char = offsets[i][0]
        end_char = offsets[end - 1][1]
        chunks.append({"text": text[start_char:end_char], "token_count": len(token_ids[i:end])})
        i = end
    return chunks


def _score_chunks(chunks: list[dict], tokenizer, model, device: str) -> float:
    if not chunks:
        return 0.0
    scores, weights = [], []
    for chunk in chunks:
        inputs = tokenizer(
            chunk["text"], return_tensors="pt", truncation=True,
            max_length=FINBERT_MAX_TOKENS, padding=True,
        ).to(device)
        with torch.no_grad():
            probs = torch.softmax(model(**inputs).logits, dim=-1).cpu().numpy()[0]
        scores.append(float(probs[0]) - float(probs[1]))  # P(pos) - P(neg)
        weights.append(chunk["token_count"])
    w = np.array(weights, dtype=float)
    w /= w.sum()
    return float(np.dot(np.array(scores), w))


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
    thresholds = json.loads(FINBERT_THRESHOLDS_JSON.read_text(encoding="utf-8"))
    fb_upper = thresholds["fitted_upper"]
    fb_lower = thresholds["fitted_lower"]
    print(f"Phase2 FinBERT thresholds (frozen, applied to extension as pure eval):")
    print(f"  upper={fb_upper:.6f}, lower={fb_lower:.6f}")
    print(f"  Dev date range: {thresholds['dev_date_range']}")
    print()

    tokenizer, model, device = _load_finbert()

    overnight_gaps = _load_extension_overnight_returns()
    print(f"Loaded overnight returns for {len(overnight_gaps)} extension events")

    ext_events = []
    with open(EXT_CALIBRATION_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ext_events.append(dict(r))
    print(f"Extension calibration: {len(ext_events)} events")
    print(f"Scoring with FinBERT...")

    results = []
    skipped_no_text = 0
    skipped_no_ret = 0

    for idx, ev in enumerate(ext_events):
        doc_id = ev["document_id"]
        ticker = ev["ticker"]
        report_date = ev["report_date"]
        issuer = ev["issuer"]

        if doc_id not in overnight_gaps:
            skipped_no_ret += 1
            continue
        gap = overnight_gaps[doc_id]
        outcome = _overnight_outcome(gap)

        text_path = OUTPUTS_DIR / issuer / "extracted" / f"{doc_id}.txt"
        if not text_path.exists():
            skipped_no_text += 1
            continue
        text = text_path.read_text(encoding="utf-8", errors="replace")

        chunks = _chunk_text(text, tokenizer)
        if not chunks:
            skipped_no_text += 1
            continue

        fb_score = _score_chunks(chunks, tokenizer, model, device)
        n_chunks = len(chunks)
        fb_signal = _predict(fb_score, fb_upper, fb_lower)
        fb_correct = int(fb_signal == outcome) if outcome != "HOLD" else None

        model_signal = ev.get("blend_predicted_signal_default", "")
        model_correct = int(model_signal == outcome) if outcome != "HOLD" else None

        results.append({
            "document_id": doc_id,
            "ticker": ticker,
            "report_date": report_date,
            "ret_overnight": gap,
            "outcome_label": outcome,
            "finbert_score": round(fb_score, 6),
            "finbert_n_chunks": n_chunks,
            "finbert_predicted_signal": fb_signal,
            "finbert_correct": fb_correct,
            "model_predicted_signal": model_signal,
            "model_correct": model_correct,
        })

        if (idx + 1) % 10 == 0 or (idx + 1) == len(ext_events):
            print(f"  [{idx+1}/{len(ext_events)}] {doc_id}: score={fb_score:.4f} "
                  f"signal={fb_signal} chunks={n_chunks}")

    print(f"\nSkipped: {skipped_no_ret} missing overnight return, "
          f"{skipped_no_text} missing extracted text")
    print(f"Processed: {len(results)} extension events")

    graded = [r for r in results if r["outcome_label"] != "HOLD"]
    n_graded = len(graded)

    fb_correct_count = sum(1 for r in graded if r["finbert_correct"] == 1)
    fb_acc = fb_correct_count / n_graded if n_graded else float("nan")

    model_correct_count = sum(1 for r in graded if r["model_correct"] == 1)
    model_acc = model_correct_count / n_graded if n_graded else float("nan")

    always_down = sum(1 for r in graded if r["outcome_label"] == "SELL")
    floor_acc = always_down / n_graded if n_graded else float("nan")

    fb_trades = sum(1 for r in results if r["finbert_predicted_signal"] != "HOLD")

    print(f"\n{'='*70}")
    print(f"Item D: FinBERT Baseline on Extension Corpus (N={len(results)} events)")
    print(f"{'='*70}")
    print(f"Graded events (|ret|>2%):  {n_graded} / {len(results)}")
    print(f"\n{'Metric':40s}  {'FinBERT':>8}  {'Model':>8}  {'Floor':>8}")
    print(f"{'-'*70}")
    print(f"{'Accuracy (HOLD-as-wrong)':40s}  {fb_acc:>8.1%}  {model_acc:>8.1%}  {floor_acc:>8.1%}")
    print(f"{'Correct / graded':40s}  {fb_correct_count:>3}/{n_graded:<3}   "
          f"{model_correct_count:>3}/{n_graded:<3}   {always_down:>3}/{n_graded:<3}")
    print(f"{'Trade rate':40s}  {fb_trades/len(results):>8.1%}")
    print(f"\nNote: thresholds from phase2 dev set (frozen). Extension is pure eval.")
    print(f"  FinBERT upper={fb_upper:.6f}, lower={fb_lower:.6f}")

    from collections import Counter
    dist = Counter(r["finbert_predicted_signal"] for r in results)
    print(f"  FinBERT signal distribution: BUY={dist['BUY']}, HOLD={dist['HOLD']}, SELL={dist['SELL']}")

    fields = [
        "document_id", "ticker", "report_date", "ret_overnight", "outcome_label",
        "finbert_score", "finbert_n_chunks", "finbert_predicted_signal", "finbert_correct",
        "model_predicted_signal", "model_correct",
    ]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        fh.write(f"# FinBERT baseline on extension corpus\n")
        fh.write(f"# N={len(results)} extension events\n")
        fh.write(f"# Graded (|ret|>2%): {n_graded}\n")
        fh.write(f"# FinBERT thresholds (phase2 dev, frozen): upper={fb_upper:.8f}, lower={fb_lower:.8f}\n")
        fh.write(f"# Grading band: +-2% raw overnight (pre-registered)\n")
        fh.write(f"# Extension is pure eval; no dev refitting.\n")
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(results)
    print(f"\nWrote {OUT_CSV}")


if __name__ == "__main__":
    main()
