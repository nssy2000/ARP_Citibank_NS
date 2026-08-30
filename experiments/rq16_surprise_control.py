"""
experiments/rq16_surprise_control.py

RQ16: does the blended LLM sentiment score add anything beyond the EPS
surprise % that is public within seconds of the print? If not, a one-line
surprise rule replaces the entire pipeline. Read-only analysis - no blend
weights, thresholds, or production outputs are touched.

Method, per dataset (production N=131, and pooled production+phase2 N~232):
  1. Join EPS surprise onto each calibration row via quant_layer.compute_eps_surprise
     (already-cached, point-in-time, no leakage - it's revealed AT the print).
  2. Recompute the numeric DEFAULT-weighted blended score per row from the stored
     layer scores (the calibration CSV only stores the derived label, not the
     numeric blend) via blend.blend_scores.
  3. OLS: forward_return ~ surprise_pct  vs  forward_return ~ surprise_pct + blend_score.
     Report the R^2 lift from adding the score, and a permutation test (shuffle the
     score column, refit, see how often the shuffled lift meets/exceeds the observed).
  4. Three-way accuracy against the existing outcome_label: surprise-only rule,
     LLM-only (reuses blend_correct_default directly), and an equal-weight combination.

Run:  python -m experiments.rq16_surprise_control
Out:  outputs/global/summary/rq16_surprise_control.json
      outputs/global/summary/rq16_surprise_control_pooled.json
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from report_pipeline import OUTPUTS_DIR
from blend import DEFAULT_WEIGHTS, blend_scores, derive_signal
from eval.calibrate import DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER
from experiments.weight_threshold_sweep import permutation_test
import quant_layer

SUMMARY_DIR = OUTPUTS_DIR / "global" / "summary"
PRODUCTION_CSV = SUMMARY_DIR / "global_outcome_calibration.csv"
PHASE2_CSV = SUMMARY_DIR / "global_outcome_calibration_phase2.csv"

LABELS = ("SELL", "HOLD", "BUY")
PERMUTATIONS = 5000
RNG_SEED = 20260721


def _none_if_nan(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return float(value)


def load_dataset(csv_paths: list[Path]) -> pd.DataFrame:
    frames = [pd.read_csv(p) for p in csv_paths]
    df = pd.concat(frames, ignore_index=True)
    df["report_date"] = df["report_date"].astype(str)
    return df


def add_surprise(df: pd.DataFrame) -> pd.DataFrame:
    """Row-wise EPS surprise join, cached per (ticker, report_date) to avoid
    redundant lookups within a single run (quant_layer itself also caches
    per-ticker earnings history to disk)."""
    cache: dict[tuple[str, str], dict[str, Any]] = {}
    surprise_pct, surprise_score, available = [], [], []
    for ticker, report_date in zip(df["ticker"], df["report_date"]):
        key = (ticker, report_date)
        if key not in cache:
            cache[key] = quant_layer.compute_eps_surprise(ticker, report_date)
        result = cache[key]
        surprise_pct.append(result["surprise_pct"])
        surprise_score.append(result["score"])
        available.append(result["available"])
    df = df.copy()
    df["surprise_pct"] = surprise_pct
    df["surprise_score"] = surprise_score
    df["surprise_available"] = available
    return df


def add_blend_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """The calibration CSV only stores the derived label (blend_predicted_signal_default),
    not the numeric blended score - recompute it from the stored per-layer scores
    under the same DEFAULT_WEIGHTS used to produce that label."""
    scores = []
    for _, row in df.iterrows():
        scores.append(blend_scores(
            micro_score=float(row["micro_score"]),
            macro_score=_none_if_nan(row.get("macro_score")),
            news_score=_none_if_nan(row.get("news_score")),
            quant_score=_none_if_nan(row.get("quant_score")),
            weights=DEFAULT_WEIGHTS,
        ))
    df = df.copy()
    df["blend_score_numeric"] = scores
    return df


def ols_r2(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, float]:
    """X must already include an intercept column. Returns (coefficients, R^2)."""
    coeffs, *_ = np.linalg.lstsq(X, y, rcond=None)
    y_hat = X @ coeffs
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return coeffs, r2


def r2_lift_for_score(y: np.ndarray, surprise: np.ndarray, score: np.ndarray) -> float:
    n = len(y)
    X_surprise = np.column_stack([np.ones(n), surprise])
    X_full = np.column_stack([np.ones(n), surprise, score])
    _, r2_surprise = ols_r2(y, X_surprise)
    _, r2_full = ols_r2(y, X_full)
    return r2_full - r2_surprise


def permuted_lift_test(y: np.ndarray, surprise: np.ndarray, score: np.ndarray,
                        seed: int = RNG_SEED, perms: int = PERMUTATIONS) -> float:
    """Shuffle the score column, holding y and surprise fixed, and see how often
    the shuffled R^2 lift meets/exceeds the observed lift."""
    rng = np.random.default_rng(seed)
    observed = r2_lift_for_score(y, surprise, score)
    ge = 0
    for _ in range(perms):
        shuffled_score = rng.permutation(score)
        if r2_lift_for_score(y, surprise, shuffled_score) >= observed:
            ge += 1
    return round((ge + 1) / (perms + 1), 5), observed


def three_way_accuracy(df: pd.DataFrame) -> dict[str, Any]:
    outcome = df["outcome_label"].to_numpy()
    n = len(outcome)

    llm_pred = df["blend_predicted_signal_default"].to_numpy()
    llm_acc = float((llm_pred == outcome).mean())
    # cross-check against the already-computed boolean column
    llm_acc_stored = float(df["blend_correct_default"].mean())

    surprise_pred = np.array([
        derive_signal(s, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER) for s in df["surprise_score"]
    ])
    surprise_acc = float((surprise_pred == outcome).mean())

    combined_score = (df["surprise_score"] + df["blend_score_numeric"]) / 2.0
    combined_pred = np.array([
        derive_signal(s, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER) for s in combined_score
    ])
    combined_acc = float((combined_pred == outcome).mean())

    counts = pd.Series(outcome).value_counts()
    majority_label = counts.idxmax()
    majority_rate = float(counts.max() / n)

    return {
        "n": n,
        "llm_only_accuracy": round(llm_acc, 4),
        "llm_only_accuracy_stored_column_check": round(llm_acc_stored, 4),
        "surprise_only_accuracy": round(surprise_acc, 4),
        "combined_accuracy": round(combined_acc, 4),
        "majority_baseline_label": str(majority_label),
        "majority_baseline_accuracy": round(majority_rate, 4),
    }


def run_rq16(csv_paths: list[Path], label: str) -> dict[str, Any]:
    df = load_dataset(csv_paths)
    n_total = len(df)

    df = add_surprise(df)
    n_missing = int((~df["surprise_available"]).sum())
    dropped_tickers = sorted(df.loc[~df["surprise_available"], "ticker"].unique().tolist())
    df = df[df["surprise_available"]].reset_index(drop=True)

    df = add_blend_numeric(df)

    y = df["forward_return"].to_numpy(dtype=float)
    surprise = df["surprise_score"].to_numpy(dtype=float)
    score = df["blend_score_numeric"].to_numpy(dtype=float)

    n = len(df)
    X_surprise = np.column_stack([np.ones(n), surprise])
    X_full = np.column_stack([np.ones(n), surprise, score])
    coeffs_surprise, r2_surprise = ols_r2(y, X_surprise)
    coeffs_full, r2_full = ols_r2(y, X_full)
    permutation_p, observed_lift = permuted_lift_test(y, surprise, score)

    accuracy = three_way_accuracy(df)

    result = {
        "label": label,
        "n_total_rows": n_total,
        "n_missing_surprise_data": n_missing,
        "n_used": n,
        "dropped_tickers_missing_surprise": dropped_tickers,
        "regression": {
            "surprise_only": {
                "coeffs_intercept_surprise": [round(float(c), 6) for c in coeffs_surprise],
                "r2": round(r2_surprise, 5),
            },
            "surprise_plus_score": {
                "coeffs_intercept_surprise_score": [round(float(c), 6) for c in coeffs_full],
                "r2": round(r2_full, 5),
            },
            "r2_lift_from_score": round(observed_lift, 5),
            "permutation_p_lift": permutation_p,
            "permutations": PERMUTATIONS,
        },
        "accuracy": accuracy,
    }
    return result


def main() -> None:
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

    production = run_rq16([PRODUCTION_CSV], label="production_n131")
    out_path = SUMMARY_DIR / "rq16_surprise_control.json"
    out_path.write_text(json.dumps(production, indent=2))
    print(f"[production] n_used={production['n_used']} (missing surprise: {production['n_missing_surprise_data']})")
    print(f"  R^2 surprise-only={production['regression']['surprise_only']['r2']}  "
          f"surprise+score={production['regression']['surprise_plus_score']['r2']}  "
          f"lift={production['regression']['r2_lift_from_score']}  "
          f"p={production['regression']['permutation_p_lift']}")
    print(f"  accuracy: surprise-only={production['accuracy']['surprise_only_accuracy']}  "
          f"llm-only={production['accuracy']['llm_only_accuracy']}  "
          f"combined={production['accuracy']['combined_accuracy']}  "
          f"baseline={production['accuracy']['majority_baseline_accuracy']}")
    print(f"  -> {out_path}")

    pooled = run_rq16([PRODUCTION_CSV, PHASE2_CSV], label="pooled_n232")
    out_path_pooled = SUMMARY_DIR / "rq16_surprise_control_pooled.json"
    out_path_pooled.write_text(json.dumps(pooled, indent=2))
    print(f"\n[pooled] n_used={pooled['n_used']} (missing surprise: {pooled['n_missing_surprise_data']})")
    print(f"  R^2 surprise-only={pooled['regression']['surprise_only']['r2']}  "
          f"surprise+score={pooled['regression']['surprise_plus_score']['r2']}  "
          f"lift={pooled['regression']['r2_lift_from_score']}  "
          f"p={pooled['regression']['permutation_p_lift']}")
    print(f"  accuracy: surprise-only={pooled['accuracy']['surprise_only_accuracy']}  "
          f"llm-only={pooled['accuracy']['llm_only_accuracy']}  "
          f"combined={pooled['accuracy']['combined_accuracy']}  "
          f"baseline={pooled['accuracy']['majority_baseline_accuracy']}")
    print(f"  -> {out_path_pooled}")

    phase2 = run_rq16([PHASE2_CSV], label="phase2_n101")
    out_path_phase2 = SUMMARY_DIR / "rq16_surprise_control_phase2.json"
    out_path_phase2.write_text(json.dumps(phase2, indent=2))
    print(f"\n[phase2] n_used={phase2['n_used']} (missing surprise: {phase2['n_missing_surprise_data']})")
    print(f"  R^2 surprise-only={phase2['regression']['surprise_only']['r2']}  "
          f"surprise+score={phase2['regression']['surprise_plus_score']['r2']}  "
          f"lift={phase2['regression']['r2_lift_from_score']}  "
          f"p={phase2['regression']['permutation_p_lift']}")
    print(f"  accuracy: surprise-only={phase2['accuracy']['surprise_only_accuracy']}  "
          f"llm-only={phase2['accuracy']['llm_only_accuracy']}  "
          f"combined={phase2['accuracy']['combined_accuracy']}  "
          f"baseline={phase2['accuracy']['majority_baseline_accuracy']}")
    print(f"  -> {out_path_phase2}")


if __name__ == "__main__":
    main()
