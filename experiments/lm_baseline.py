"""
experiments/lm_baseline.py
Item 4 of the model-arm spec (Nigel, 2026-08-05), word-list half.

Loughran-McDonald finance word-count score via pysentiment2, pushed through
the identical evaluation path as the deployed model.

Grading: overnight returns from returns_matrix.csv, pre-registered +-2% band.
  - |ret_overnight| > 0.02: BUY if positive, SELL if negative
  - |ret_overnight| <= 0.02: HOLD (flat)

Exclusion set (35 events):
  - 25 worksheet-contaminated events (human score leaked into LLM input)
  - 1 misattributed document (SPOT_FQ1_2026)
  - 9 timing-excluded events (non-US issuers with unreliable overnight returns)

Dev/eval split: sort all clean events by release_date (from returns_matrix.csv,
the corrected EDGAR 8-K anchor), earliest 20% = dev, remaining 80% = eval.
Thresholds fit on dev only, frozen, applied to eval.

Accuracy is reported two ways:
  - FLAT excluded: only events where outcome is BUY or SELL are graded
  - FLAT as wrong: HOLD outcomes count as wrong if the model predicted BUY/SELL

Run: python -m experiments.lm_baseline
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pysentiment2 as ps

# ROOT on the path before the repo imports below: run as a script, sys.path[0]
# is experiments/, so `import backtest` raised ModuleNotFoundError.
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

from backtest import OUTPUTS_DIR
from eval.excluded_events import EXCLUDED_EVENTS  # noqa: E402

# ── paths ──
PHASE2_CALIBRATION_CSV = OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration_phase2.csv"
RETURNS_MATRIX_CSV = OUTPUTS_DIR / "global" / "summary" / "returns_matrix.csv"
THRESHOLDS_JSON = OUTPUTS_DIR / "global" / "summary" / "lm_baseline_dev_thresholds.json"
EVAL_CSV = OUTPUTS_DIR / "global" / "summary" / "lm_baseline_eval_results.csv"

DEV_FRACTION = 0.20
OVERNIGHT_BAND = 0.02  # +-2% band for BUY/SELL/HOLD grading

# ── exclusion set (35 events) ──
WORKSHEET_EXCLUDED = frozenset({
    "AMD_FQ1_2026", "AMD_FQ2_2025", "AMD_FQ4_2025",
    "AMZN_FQ1_2026", "AMZN_FQ3_2025", "AMZN_FQ4_2025",
    "COIN_FQ1_2026", "COIN_FQ3_2025", "COIN_FQ4_2025",
    "LLY_FQ1_2026", "LLY_FQ3_2025", "LLY_FQ4_2025",
    "META_FQ1_2026", "META_FQ3_2025", "META_FQ4_2025",
    "NFLX_FQ3_2025", "NFLX_FQ4_2024", "NFLX_FQ4_2025",
    "NVDA_FQ1_2025", "NVDA_FQ2_2025", "NVDA_FQ3_2025", "NVDA_FQ4_2025",
    "TSLA_FQ1_2026", "TSLA_FQ3_2025", "TSLA_FQ4_2025",
})
# Bad-document exclusions - see eval/excluded_events.py for the reasons.
SPOT_EXCLUDED = EXCLUDED_EVENTS

_LM = ps.LM()


def _load_returns_matrix() -> dict[str, dict]:
    """Load returns_matrix.csv keyed by document_id."""
    with open(RETURNS_MATRIX_CSV, encoding="utf-8") as fh:
        return {r["document_id"]: r for r in csv.DictReader(fh)}


def _timing_excluded_set(rm: dict[str, dict]) -> frozenset[str]:
    return frozenset(did for did, r in rm.items() if r.get("timing_excluded") == "YES")


def overnight_outcome_label(ret_overnight: float) -> str:
    if ret_overnight > OVERNIGHT_BAND:
        return "BUY"
    if ret_overnight < -OVERNIGHT_BAND:
        return "SELL"
    return "HOLD"


def extracted_text_path(issuer: str, document_id: str) -> Path:
    """Resolve local extracted text path from issuer + document_id."""
    return OUTPUTS_DIR / issuer / "extracted" / f"{document_id}.txt"


def result_json_path(issuer: str, document_id: str) -> Path:
    return OUTPUTS_DIR / issuer / "results" / f"{document_id}.json"


def lm_score(text: str) -> tuple[float, int, int, int]:
    """Returns (score, pos_count, neg_count, total_tokens).
    score = (pos - neg) / total_tokens, 0.0 if no tokens."""
    tokens = _LM.tokenize(text)
    scored = _LM.get_score(tokens)
    pos, neg = scored["Positive"], scored["Negative"]
    total = len(tokens)
    score = (pos - neg) / total if total else 0.0
    return score, pos, neg, total


def load_events() -> list[dict]:
    """Load events from calibration CSV + returns matrix, apply exclusions,
    grade using overnight returns with +-2% band.

    The 'report_date' field in each returned dict is the **release_date**
    (from returns_matrix.csv, which uses the corrected EDGAR 8-K anchor),
    not the calibration CSV's report_date. split_dev_eval() sorts on this
    field, so the dev/eval partition is drawn on the entry anchor date.
    """
    rm = _load_returns_matrix()
    timing_excl = _timing_excluded_set(rm)
    all_excluded = WORKSHEET_EXCLUDED | SPOT_EXCLUDED | timing_excl

    events = []
    with open(PHASE2_CALIBRATION_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            did = r["document_id"]
            if not r["micro_score"]:
                continue
            if did in all_excluded:
                continue
            if did not in rm:
                continue
            ret_overnight = float(rm[did]["ret_overnight"])
            outcome = overnight_outcome_label(ret_overnight)
            # Use release_date from returns_matrix (corrected anchor),
            # not report_date from calibration CSV (retired field).
            events.append({
                "document_id": did,
                "issuer": r["issuer"],
                "ticker": r["ticker"],
                "report_date": rm[did]["report_date"],  # release_date
                "ret_overnight": ret_overnight,
                "outcome_label": outcome,
                "blend_predicted_signal_default": r["blend_predicted_signal_default"],
            })
    # "SPOT" was accurate while that set held one event. It now holds the
    # bad-document exclusions, of which SPOT_FQ1_2026 is one.
    print(f"Exclusions applied: {len(WORKSHEET_EXCLUDED)} worksheet + "
          f"{len(SPOT_EXCLUDED)} bad-document + {len(timing_excl)} timing = "
          f"{len(all_excluded)} total")
    return events


def attach_lm_scores(events: list[dict]) -> list[dict]:
    out = []
    skipped = 0
    for r in events:
        # Try local extracted text path first
        text_path = extracted_text_path(r["issuer"], r["document_id"])
        if not text_path.exists():
            # Fallback: try to resolve from result JSON
            json_path = result_json_path(r["issuer"], r["document_id"])
            if json_path.exists():
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                tp = payload.get("run_meta", {}).get("extracted_text_path")
                if tp:
                    text_path = Path(tp)
            if not text_path.exists():
                skipped += 1
                continue
        text = text_path.read_text(encoding="utf-8", errors="replace")
        score, pos, neg, total = lm_score(text)
        r_out = dict(r)
        r_out.update({
            "lm_score": score, "lm_pos": pos, "lm_neg": neg, "lm_total_tokens": total,
        })
        out.append(r_out)
    if skipped:
        print(f"Skipped {skipped} events (missing extracted text)")
    return out


def split_dev_eval(events: list[dict], dev_fraction: float = DEV_FRACTION) -> tuple[list[dict], list[dict]]:
    events_sorted = sorted(events, key=lambda e: e["report_date"])
    n_dev = round(len(events_sorted) * dev_fraction)
    return events_sorted[:n_dev], events_sorted[n_dev:]


def predict(score: float, upper: float, lower: float) -> str:
    if score > upper:
        return "BUY"
    if score < lower:
        return "SELL"
    return "HOLD"


def accuracy_flat_excluded(events: list[dict], pred_key: str) -> tuple[int, int, float]:
    """Count correct among events where outcome is BUY or SELL (FLAT excluded).
    Returns (correct, graded_n, accuracy)."""
    graded = [e for e in events if e["outcome_label"] != "HOLD"]
    if not graded:
        return 0, 0, 0.0
    correct = sum(1 for e in graded if e[pred_key] == e["outcome_label"])
    return correct, len(graded), correct / len(graded)


def accuracy_flat_as_wrong(events: list[dict], pred_key: str) -> tuple[int, int, float]:
    """All events graded; prediction matches outcome (including HOLD) = correct.
    Returns (correct, total_n, accuracy)."""
    if not events:
        return 0, 0, 0.0
    correct = sum(1 for e in events if e[pred_key] == e["outcome_label"])
    return correct, len(events), correct / len(events)


def fit_thresholds(dev_events: list[dict], score_key: str = "lm_score") -> tuple[float, float, float]:
    """Grid search for (upper, lower) maximizing dev accuracy (FLAT as wrong).
    Returns (best_upper, best_lower, best_dev_accuracy)."""
    scores = sorted(e[score_key] for e in dev_events)
    candidates = sorted(set(np.percentile(scores, np.linspace(0, 100, 41))))

    best = (candidates[-1], candidates[0], -1.0)
    for upper in candidates:
        for lower in candidates:
            if lower > upper:
                continue
            correct = sum(
                1 for e in dev_events
                if predict(e[score_key], upper, lower) == e["outcome_label"]
            )
            acc = correct / len(dev_events)
            if acc > best[2]:
                best = (upper, lower, acc)
    return best


def majority_baseline_accuracy(events: list[dict]) -> tuple[str, float]:
    counts = Counter(e["outcome_label"] for e in events)
    majority_label, majority_count = counts.most_common(1)[0]
    return majority_label, majority_count / len(events)


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {path}")


def main() -> int:
    events = load_events()
    print(f"Loaded {len(events)} clean events (after exclusions)")
    events = attach_lm_scores(events)
    print(f"Attached LM scores to {len(events)} events")

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

    upper, lower, dev_acc = fit_thresholds(dev)
    print(f"\nFitted on dev only: upper={upper:.6f}, lower={lower:.6f}, dev accuracy (FLAT-as-wrong)={dev_acc:.4f}")

    thresholds_out = {
        "dev_n": len(dev), "eval_n": len(eval_set),
        "dev_fraction": DEV_FRACTION,
        "overnight_band": OVERNIGHT_BAND,
        "excluded_n": 268 - len(events),
        "excluded_worksheet": len(WORKSHEET_EXCLUDED),
        "excluded_spot": len(SPOT_EXCLUDED),
        "excluded_timing": 268 - len(events) - len(WORKSHEET_EXCLUDED) - len(SPOT_EXCLUDED),
        "dev_date_range": [dev[0]["report_date"], dev[-1]["report_date"]],
        "eval_date_range": [eval_set[0]["report_date"], eval_set[-1]["report_date"]],
        "fitted_upper": upper, "fitted_lower": lower,
        "dev_accuracy_flat_as_wrong": round(dev_acc, 4),
        "grading": "overnight returns from returns_matrix.csv, +-2% band",
        "note": "Thresholds fit on dev split only (earliest 20% by report_date), applied "
                "frozen to eval split. Graded on overnight returns with +-2% band.",
    }
    THRESHOLDS_JSON.parent.mkdir(parents=True, exist_ok=True)
    THRESHOLDS_JSON.write_text(json.dumps(thresholds_out, indent=2), encoding="utf-8")
    print(f"Wrote thresholds -> {THRESHOLDS_JSON}")

    # Apply to eval set
    eval_rows = []
    for e in eval_set:
        lm_pred = predict(e["lm_score"], upper, lower)
        model_pred = e["blend_predicted_signal_default"]
        eval_rows.append({
            "document_id": e["document_id"], "ticker": e["ticker"],
            "report_date": e["report_date"],
            "ret_overnight": round(e["ret_overnight"], 6),
            "outcome_label": e["outcome_label"],
            "lm_score": round(e["lm_score"], 6),
            "lm_predicted_signal": lm_pred,
            "lm_correct": int(lm_pred == e["outcome_label"]),
            "model_predicted_signal": model_pred,
            "model_correct": int(model_pred == e["outcome_label"]),
        })
    write_csv(EVAL_CSV, eval_rows)

    # ── Accuracy: FLAT excluded (primary) ──
    for e in eval_rows:
        e["_lm_pred"] = e["lm_predicted_signal"]
        e["_model_pred"] = e["model_predicted_signal"]

    lm_c_ex, lm_n_ex, lm_acc_ex = accuracy_flat_excluded(eval_rows, "lm_predicted_signal")
    mod_c_ex, mod_n_ex, mod_acc_ex = accuracy_flat_excluded(eval_rows, "model_predicted_signal")

    # ── Accuracy: FLAT as wrong ──
    lm_c_aw, lm_n_aw, lm_acc_aw = accuracy_flat_as_wrong(eval_rows, "lm_predicted_signal")
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
    print(f"EVAL SPLIT (n={len(eval_set)}, graded_n={lm_n_ex} FLAT excluded)")
    print(f"Grading: overnight returns, +-2% band")
    print(f"{'='*60}")
    print(f"\n  FLAT excluded (primary) - graded n={lm_n_ex}:")
    print(f"    LM baseline:        {lm_acc_ex:.4f} ({lm_c_ex}/{lm_n_ex})")
    print(f"    Deployed model:     {mod_acc_ex:.4f} ({mod_c_ex}/{mod_n_ex})")
    print(f"    Majority ({maj_graded_label:4}):     {majority_acc_ex:.4f}")
    print(f"\n  FLAT as wrong - total n={lm_n_aw}:")
    print(f"    LM baseline:        {lm_acc_aw:.4f} ({lm_c_aw}/{lm_n_aw})")
    print(f"    Deployed model:     {mod_acc_aw:.4f} ({mod_c_aw}/{mod_n_aw})")
    print(f"    Majority ({majority_label:4}):     {majority_acc_aw:.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
