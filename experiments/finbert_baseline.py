"""
experiments/finbert_baseline.py
Item 4 of the model-arm spec (Nigel, 2026-08-05), FinBERT half.

ProsusAI/finbert: a BERT model fine-tuned on financial text for sentiment
classification (positive/negative/neutral). Chunks each document to 512
tokens (FinBERT's max), scores each chunk, averages sentiment weighted by
chunk token length.

Uses the EXACT same dev/eval split, exclusion set, and grading as
experiments/lm_baseline.py - events are byte-identical by construction
(same load_events() + split_dev_eval() from that module).

Grading: overnight returns from returns_matrix.csv, pre-registered +-2% band.
Exclusion set: 25 worksheet + the bad-document set + 9 timing. It was 35 events
until DIS_FQ1_2025 was excluded on 2026-08-24; the count is derived from
load_events(), not written here, so it follows the next exclusion too.

Run: python -m experiments.finbert_baseline
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# ROOT on the path before the repo imports below: run as a script, sys.path[0]
# is experiments/, so `import backtest` raised ModuleNotFoundError.
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

from backtest import OUTPUTS_DIR

# Import shared infrastructure from lm_baseline to guarantee identical splits
from experiments.lm_baseline import (
    load_events,
    split_dev_eval,
    predict,
    accuracy_flat_excluded,
    accuracy_flat_as_wrong,
    majority_baseline_accuracy,
    write_csv,
    extracted_text_path,
    DEV_FRACTION,
    OVERNIGHT_BAND,
)

# ── paths ──
FINBERT_THRESHOLDS_JSON = OUTPUTS_DIR / "global" / "summary" / "finbert_dev_thresholds.json"
FINBERT_EVAL_CSV = OUTPUTS_DIR / "global" / "summary" / "finbert_eval_results.csv"

# ── FinBERT config ──
FINBERT_MODEL_NAME = "ProsusAI/finbert"
FINBERT_MAX_TOKENS = 512  # FinBERT's max sequence length
FINBERT_LABEL_MAP = {0: "positive", 1: "negative", 2: "neutral"}


def load_finbert():
    """Load FinBERT model and tokenizer. Downloads on first run."""
    print(f"Loading FinBERT ({FINBERT_MODEL_NAME})...")
    tokenizer = AutoTokenizer.from_pretrained(FINBERT_MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(FINBERT_MODEL_NAME)
    model.eval()
    # Move to MPS if available (macOS), else CPU
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = model.to(device)
    print(f"FinBERT loaded on {device}")
    return tokenizer, model, device


def chunk_text(text: str, tokenizer, max_tokens: int = FINBERT_MAX_TOKENS) -> list[dict]:
    """Split text into chunks that fit within FinBERT's token limit.
    Returns list of {text: str, token_count: int} dicts."""
    # Tokenize full text to get token IDs
    full_encoding = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    token_ids = full_encoding["input_ids"]
    offsets = full_encoding["offset_mapping"]

    if not token_ids:
        return []

    # Reserve 2 tokens for [CLS] and [SEP]
    usable = max_tokens - 2
    chunks = []
    i = 0
    while i < len(token_ids):
        end = min(i + usable, len(token_ids))
        chunk_ids = token_ids[i:end]
        # Extract the text span for this chunk
        start_char = offsets[i][0]
        end_char = offsets[end - 1][1]
        chunk_text_str = text[start_char:end_char]
        chunks.append({"text": chunk_text_str, "token_count": len(chunk_ids)})
        i = end

    return chunks


def score_chunks(chunks: list[dict], tokenizer, model, device: str) -> float:
    """Score each chunk with FinBERT, return token-length-weighted average
    sentiment score. Score = P(positive) - P(negative), range [-1, +1]."""
    if not chunks:
        return 0.0

    scores = []
    weights = []

    for chunk in chunks:
        inputs = tokenizer(
            chunk["text"],
            return_tensors="pt",
            truncation=True,
            max_length=FINBERT_MAX_TOKENS,
            padding=True,
        ).to(device)

        with torch.no_grad():
            outputs = model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1).cpu().numpy()[0]

        # FinBERT labels: positive=0, negative=1, neutral=2
        p_pos = float(probs[0])
        p_neg = float(probs[1])
        score = p_pos - p_neg  # range [-1, +1]

        scores.append(score)
        weights.append(chunk["token_count"])

    # Weighted average by token count
    scores_arr = np.array(scores)
    weights_arr = np.array(weights, dtype=float)
    weights_arr /= weights_arr.sum()

    return float(np.dot(scores_arr, weights_arr))


def attach_finbert_scores(events: list[dict], tokenizer, model, device: str) -> list[dict]:
    """Score each event's extracted text with FinBERT."""
    out = []
    skipped = 0
    total = len(events)

    for idx, r in enumerate(events):
        text_path = extracted_text_path(r["issuer"], r["document_id"])
        if not text_path.exists():
            skipped += 1
            continue

        text = text_path.read_text(encoding="utf-8", errors="replace")
        chunks = chunk_text(text, tokenizer)

        if not chunks:
            skipped += 1
            continue

        score = score_chunks(chunks, tokenizer, model, device)
        n_chunks = len(chunks)
        total_tokens = sum(c["token_count"] for c in chunks)

        r_out = dict(r)
        r_out.update({
            "finbert_score": score,
            "finbert_n_chunks": n_chunks,
            "finbert_total_tokens": total_tokens,
        })
        out.append(r_out)

        if (idx + 1) % 25 == 0 or (idx + 1) == total:
            print(f"  Scored {idx + 1}/{total} events ({n_chunks} chunks, "
                  f"{total_tokens} tokens, score={score:.4f})")

    if skipped:
        print(f"Skipped {skipped} events (missing extracted text)")
    return out


def fit_finbert_thresholds(dev_events: list[dict]) -> tuple[float, float, float]:
    """Grid search for (upper, lower) maximizing dev accuracy (FLAT as wrong)
    on finbert_score. Returns (best_upper, best_lower, best_dev_accuracy)."""
    scores = sorted(e["finbert_score"] for e in dev_events)
    candidates = sorted(set(np.percentile(scores, np.linspace(0, 100, 41))))

    best = (candidates[-1], candidates[0], -1.0)
    for upper in candidates:
        for lower in candidates:
            if lower > upper:
                continue
            correct = sum(
                1 for e in dev_events
                if predict(e["finbert_score"], upper, lower) == e["outcome_label"]
            )
            acc = correct / len(dev_events)
            if acc > best[2]:
                best = (upper, lower, acc)
    return best


def main() -> int:
    # ── Load events (identical to lm_baseline) ──
    events = load_events()
    print(f"Loaded {len(events)} clean events (after exclusions)")

    # ── Load FinBERT ──
    tokenizer, model, device = load_finbert()

    # ── Score all events ──
    print(f"\nScoring {len(events)} events with FinBERT...")
    events = attach_finbert_scores(events, tokenizer, model, device)
    print(f"Scored {len(events)} events")

    # ── Dev/eval split (identical to lm_baseline) ──
    dev, eval_set = split_dev_eval(events)
    print(f"\nDev split: {len(dev)} events (earliest {DEV_FRACTION:.0%} by report_date)")
    print(f"Eval split: {len(eval_set)} events")
    print(f"Dev date range: {dev[0]['report_date']} to {dev[-1]['report_date']}")
    print(f"Eval date range: {eval_set[0]['report_date']} to {eval_set[-1]['report_date']}")

    # Outcome distribution
    dev_counts = Counter(e["outcome_label"] for e in dev)
    eval_counts = Counter(e["outcome_label"] for e in eval_set)
    print(f"Dev outcome dist:  BUY={dev_counts['BUY']} HOLD={dev_counts['HOLD']} SELL={dev_counts['SELL']}")
    print(f"Eval outcome dist: BUY={eval_counts['BUY']} HOLD={eval_counts['HOLD']} SELL={eval_counts['SELL']}")

    # ── Fit thresholds on dev ──
    upper, lower, dev_acc = fit_finbert_thresholds(dev)
    print(f"\nFitted on dev only: upper={upper:.6f}, lower={lower:.6f}, "
          f"dev accuracy (FLAT-as-wrong)={dev_acc:.4f}")

    # ── Save thresholds ──
    thresholds_out = {
        "model": FINBERT_MODEL_NAME,
        "max_tokens": FINBERT_MAX_TOKENS,
        "dev_n": len(dev), "eval_n": len(eval_set),
        "dev_fraction": DEV_FRACTION,
        "overnight_band": OVERNIGHT_BAND,
        # derived, like lm_baseline does it: a literal here would have kept
        # publishing 35 after the universe changed
        "excluded_n": 268 - len(events),
        "dev_date_range": [dev[0]["report_date"], dev[-1]["report_date"]],
        "eval_date_range": [eval_set[0]["report_date"], eval_set[-1]["report_date"]],
        "fitted_upper": upper, "fitted_lower": lower,
        "dev_accuracy_flat_as_wrong": round(dev_acc, 4),
        "grading": "overnight returns from returns_matrix.csv, +-2% band",
        "note": "Thresholds fit on dev split only (earliest 20% by report_date), applied "
                "frozen to eval split. Chunk-weighted FinBERT sentiment score.",
    }
    FINBERT_THRESHOLDS_JSON.parent.mkdir(parents=True, exist_ok=True)
    FINBERT_THRESHOLDS_JSON.write_text(json.dumps(thresholds_out, indent=2), encoding="utf-8")
    print(f"Wrote thresholds -> {FINBERT_THRESHOLDS_JSON}")

    # ── Apply to eval set ──
    eval_rows = []
    for e in eval_set:
        fb_pred = predict(e["finbert_score"], upper, lower)
        model_pred = e["blend_predicted_signal_default"]
        eval_rows.append({
            "document_id": e["document_id"], "ticker": e["ticker"],
            "report_date": e["report_date"],
            "ret_overnight": round(e["ret_overnight"], 6),
            "outcome_label": e["outcome_label"],
            "finbert_score": round(e["finbert_score"], 6),
            "finbert_n_chunks": e["finbert_n_chunks"],
            "finbert_predicted_signal": fb_pred,
            "finbert_correct": int(fb_pred == e["outcome_label"]),
            "model_predicted_signal": model_pred,
            "model_correct": int(model_pred == e["outcome_label"]),
        })
    write_csv(FINBERT_EVAL_CSV, eval_rows)

    # ── Accuracy: FLAT excluded (primary) ──
    fb_c_ex, fb_n_ex, fb_acc_ex = accuracy_flat_excluded(eval_rows, "finbert_predicted_signal")
    mod_c_ex, mod_n_ex, mod_acc_ex = accuracy_flat_excluded(eval_rows, "model_predicted_signal")

    # ── Accuracy: FLAT as wrong ──
    fb_c_aw, fb_n_aw, fb_acc_aw = accuracy_flat_as_wrong(eval_rows, "finbert_predicted_signal")
    mod_c_aw, mod_n_aw, mod_acc_aw = accuracy_flat_as_wrong(eval_rows, "model_predicted_signal")

    majority_label, majority_acc_aw = majority_baseline_accuracy(
        [{"outcome_label": e["outcome_label"]} for e in eval_rows]
    )

    # Majority accuracy FLAT excluded
    graded_eval = [e for e in eval_rows if e["outcome_label"] != "HOLD"]
    if graded_eval:
        majority_graded_counts = Counter(e["outcome_label"] for e in graded_eval)
        maj_graded_label, maj_graded_n = majority_graded_counts.most_common(1)[0]
        majority_acc_ex = maj_graded_n / len(graded_eval)
    else:
        maj_graded_label, majority_acc_ex = "N/A", 0.0

    print(f"\n{'='*60}")
    print(f"EVAL SPLIT (n={len(eval_set)}, graded_n={fb_n_ex} FLAT excluded)")
    print(f"Grading: overnight returns, +-2% band")
    print(f"{'='*60}")
    print(f"\n  FLAT excluded (primary) - graded n={fb_n_ex}:")
    print(f"    FinBERT:            {fb_acc_ex:.4f} ({fb_c_ex}/{fb_n_ex})")
    print(f"    Deployed model:     {mod_acc_ex:.4f} ({mod_c_ex}/{mod_n_ex})")
    print(f"    Majority ({maj_graded_label:4}):     {majority_acc_ex:.4f}")
    print(f"\n  FLAT as wrong - total n={fb_n_aw}:")
    print(f"    FinBERT:            {fb_acc_aw:.4f} ({fb_c_aw}/{fb_n_aw})")
    print(f"    Deployed model:     {mod_acc_aw:.4f} ({mod_c_aw}/{mod_n_aw})")
    print(f"    Majority ({majority_label:4}):     {majority_acc_aw:.4f}")

    # ── Score distribution stats ──
    fb_scores = [e["finbert_score"] for e in eval_rows]
    print(f"\n  FinBERT score distribution (eval):")
    print(f"    mean={np.mean(fb_scores):.4f}, median={np.median(fb_scores):.4f}, "
          f"std={np.std(fb_scores):.4f}")
    print(f"    min={np.min(fb_scores):.4f}, max={np.max(fb_scores):.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
