"""
experiments/walkforward_combined.py
Item E: Walk-forward validation on the combined Set C.

Combines the frozen phase2 clean events with the N=93 extension
events (all 93 are clean — no worksheet contamination, SPOT exclusion,
or timing exclusions apply to the extension corpus).

Applies the same rolling walk-forward design as experiments/walkforward_validation.py:
  - Weights fixed at DEFAULT_WEIGHTS=(0.55, 0.45, 0.0, 0.0)
  - Only HOLD thresholds refit per window
  - Two objectives: mean net per trade, directional accuracy (>=15% trade floor)
  - Degeneracy assertion if OOS trades fall below MIN_TRADES_FLOOR

Extension overnight returns sourced from backtest_equity_extension_2026_08_13.csv
(LLM-rater rows, `gap` column). Phase2 overnight returns from returns_matrix.csv.

RETROSPECTIVE VALIDATION — NOT PRE-REGISTERED.
The deployed thresholds (hold_upper=+0.25, hold_lower=-0.05) were selected
on the full frozen phase2 dataset. The combined set is also retrospective —
every event in it has been seen. The counts are printed, not written here: the
clean universe was 233 and the combined set 326 until DIS_FQ1_2025 was excluded
on 2026-08-24, and a count in a docstring cannot be re-derived.

Outputs:
  outputs/global/summary/item_e_combined_walkforward.json
  outputs/global/summary/item_e_combined_walkforward.csv
"""
from __future__ import annotations

import csv
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev

import numpy as np
from scipy.stats import binomtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from blend import DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER, DEFAULT_WEIGHTS, blend_scores
from bootstrap_stats import bootstrap_trade_stats

SUMMARY_DIR = Path(__file__).resolve().parent.parent / "outputs" / "global" / "summary"
PHASE2_CALIBRATION_CSV = SUMMARY_DIR / "global_outcome_calibration_phase2.csv"
EXT_CALIBRATION_CSV = SUMMARY_DIR / "global_outcome_calibration_extension_2026_08_13.csv"
RETURNS_CSV = SUMMARY_DIR / "returns_matrix.csv"
# One source of truth for which extension-gap vintage is current; four files
# used to carry their own copy of this name. See eval/extension_gaps.py.
from eval.extension_gaps import CURRENT_GAP_FILE as EXT_BACKTEST_CSV  # noqa: E402
from eval.excluded_events import EXCLUDED_EVENTS  # noqa: E402
LEAK_FLAGS_CSV = SUMMARY_DIR / "worksheet_leak_flags.csv"

OUT_JSON = SUMMARY_DIR / "item_e_combined_walkforward.json"
OUT_CSV = SUMMARY_DIR / "item_e_combined_walkforward.csv"

COST_BPS = 10.0
COST_FRAC = COST_BPS / 10_000
FLAT_BAND = 0.02
MIN_TRADES_FLOOR = 5
MIN_TRADE_FRACTION = 0.15

THRESH_UPPER_RANGE = np.arange(0.05, 0.55, 0.05)
THRESH_LOWER_RANGE = np.arange(-0.50, 0.05, 0.05)


def _num(x):
    if x is None or x == "":
        return None
    return float(x)


def _load_phase2_events() -> list[dict]:
    """Load the frozen clean events from phase2 (233 before the 2026-08-24 exclusion)."""
    cal = {}
    with open(PHASE2_CALIBRATION_CSV) as f:
        for r in csv.DictReader(f):
            cal[r["document_id"]] = r

    rm = {}
    with open(RETURNS_CSV) as f:
        lines = [l for l in f if not l.startswith("#")]
    for r in csv.DictReader(lines):
        rm[r["document_id"]] = r

    worksheet_excluded = set()
    with open(LEAK_FLAGS_CSV) as f:
        for r in csv.DictReader(f):
            if r.get("has_human_score", "").strip() == "True":
                worksheet_excluded.add(r["document_id"])

    spot_excluded = set(EXCLUDED_EVENTS)
    events = []
    for did, c in cal.items():
        if did in worksheet_excluded or did in spot_excluded:
            continue
        r = rm.get(did)
        if r is None or r.get("timing_excluded") == "YES":
            continue
        ret = _num(r.get("ret_overnight"))
        if ret is None:
            continue
        events.append({
            "document_id": did,
            "ticker": c["ticker"],
            "release_date": r["report_date"],  # release_date anchor
            "micro_score": _num(c["micro_score"]),
            "macro_score": _num(c["macro_score"]),
            "news_score": _num(c.get("news_score")),
            "quant_score": _num(c.get("quant_score")),
            "ret_overnight": ret,
            "set": "frozen",
        })
    return events


def _load_extension_events() -> list[dict]:
    """Load all 93 extension events. No exclusions applied (all are clean).

    The gap join is on document_id, not (ticker, report_date): this roster is the
    frozen 2026-08-13 artefact and its report_date column still carries the
    first-of-month placeholders, so a date-keyed join drops every re-anchored
    event through the `continue` below. The count is asserted at the end, because
    "all 93" is a claim this function should not be able to break quietly.
    """
    # Get overnight returns from backtest CSV (LLM rows)
    gaps: dict[str, float] = {}
    with open(EXT_BACKTEST_CSV) as f:
        reader = csv.DictReader(f)
        if "document_id" not in (reader.fieldnames or []):
            raise SystemExit(
                f"{EXT_BACKTEST_CSV.name} has no document_id column. Vintages before\n"
                f"2026-08-24 were keyed on (ticker, report_date). Regenerate with\n"
                f"`python -m eval.extension_gaps` and repoint CURRENT_GAP_FILE.")
        for r in reader:
            if r["rater"] == "LLM (DeepSeek)":
                try:
                    gaps[r["document_id"]] = float(r["gap"])
                except (ValueError, KeyError):
                    pass
    if not gaps:
        raise SystemExit(
            f"{EXT_BACKTEST_CSV.name} yielded no gaps. The loop above swallows\n"
            f"ValueError and KeyError, so a changed column set or a comment line\n"
            f"before the header reads as zero events rather than as an error.")

    events, missing_gap, missing_micro = [], [], []
    with open(EXT_CALIBRATION_CSV) as f:
        for r in csv.DictReader(f):
            key = r["document_id"]
            if key not in gaps:
                missing_gap.append(key)
                continue
            micro = _num(r.get("micro_score"))
            if micro is None:
                missing_micro.append(key)
                continue
            events.append({
                "document_id": r["document_id"],
                "ticker": r["ticker"],
                "release_date": r["report_date"],  # extension report_date = release_date anchor
                "micro_score": micro,
                "macro_score": _num(r.get("macro_score")),
                "news_score": _num(r.get("news_score")),
                "quant_score": _num(r.get("quant_score")),
                "ret_overnight": gaps[key],
                "set": "extension",
            })
    if missing_gap or missing_micro:
        raise SystemExit(
            f"extension roster and gap file disagree on the event set: "
            f"{len(missing_gap)} event(s) have no gap {missing_gap[:6]}, "
            f"{len(missing_micro)} have no micro_score {missing_micro[:6]}. "
            f"Both files must cover the same 93 events; regenerate the gap file "
            f"with `python -m eval.extension_gaps` and repoint CURRENT_GAP_FILE.")
    return events


def _blend(ev: dict) -> float:
    return blend_scores(
        ev["micro_score"], ev["macro_score"],
        ev["news_score"], ev["quant_score"],
        DEFAULT_WEIGHTS,
    )


def _signal(score: float, upper: float, lower: float) -> str:
    if score > upper:
        return "BUY"
    if score < lower:
        return "SELL"
    return "HOLD"


def _evaluate(events: list[dict], upper: float, lower: float, objective: str) -> dict:
    nets = []
    correct = 0
    graded = 0
    for ev in events:
        score = _blend(ev)
        sig = _signal(score, upper, lower)
        ret = ev["ret_overnight"]
        if sig != "HOLD":
            net = (ret if sig == "BUY" else -ret) - COST_FRAC
            nets.append(net)
            if abs(ret) > FLAT_BAND:
                graded += 1
                truth = "BUY" if ret > 0 else "SELL"
                if sig == truth:
                    correct += 1
    n_trades = len(nets)
    mean_net = mean(nets) if nets else 0.0
    accuracy = correct / graded if graded > 0 else 0.0
    if objective == "mean_net":
        value = mean_net
    else:  # directional_accuracy
        value = accuracy if graded > 0 else 0.0
    return {
        "n_trades": n_trades, "n_graded": graded, "n_correct": correct,
        "mean_net": mean_net, "accuracy": accuracy, "objective_value": value,
    }


def _fit_thresholds(train_events: list[dict], objective: str) -> tuple[float, float, dict]:
    """Grid search HOLD thresholds on training events. Returns (upper, lower, stats)."""
    best_val = -1e9
    best_upper = DEFAULT_HOLD_UPPER
    best_lower = DEFAULT_HOLD_LOWER
    best_stats: dict = {}

    for upper, lower in itertools.product(THRESH_UPPER_RANGE, THRESH_LOWER_RANGE):
        if lower >= upper:
            continue
        stats = _evaluate(train_events, float(upper), float(lower), objective)
        n = len(train_events)
        # Trade fraction constraint for accuracy objective
        if objective == "directional_accuracy":
            if stats["n_trades"] < MIN_TRADE_FRACTION * n:
                continue
        # Degenerate: no trades
        if stats["n_trades"] < 1:
            continue
        val = stats["objective_value"]
        if val > best_val:
            best_val = val
            best_upper = float(upper)
            best_lower = float(lower)
            best_stats = stats
    return best_upper, best_lower, best_stats


def _in_sample_stats(events: list[dict]) -> dict:
    stats = _evaluate(events, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER, "mean_net")
    nets = []
    for ev in events:
        score = _blend(ev)
        sig = _signal(score, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER)
        if sig != "HOLD":
            net = (ev["ret_overnight"] if sig == "BUY" else -ev["ret_overnight"]) - COST_FRAC
            nets.append(net)
    bs = bootstrap_trade_stats(nets) if nets else {}
    return {
        "hold_upper": DEFAULT_HOLD_UPPER,
        "hold_lower": DEFAULT_HOLD_LOWER,
        "n_trades": stats["n_trades"],
        "n_graded": stats["n_graded"],
        "n_correct": stats["n_correct"],
        "accuracy": round(stats["accuracy"], 4),
        "mean_net_pct": round(stats["mean_net"] * 100, 4),
        "ci_low_90": round(bs.get("mean_per_trade", {}).get("ci_low", 0) * 100, 4) if bs else None,
        "ci_high_90": round(bs.get("mean_per_trade", {}).get("ci_high", 0) * 100, 4) if bs else None,
    }


# The frozen-set figures this run should reproduce, keyed on the constants blend.py
# deploys. The literal that used to sit here said "146 trades, 95 graded, 62 correct,
# 0.6526" unconditionally, so after the 2026-08-19 promotion the JSON published
# n_trades 169 next to expected 146 and nothing said which was wrong. An unrecognised
# regime records itself rather than passing silently.
# The key carries the bad-document exclusions as well as the constants. Without
# them, excluding an event silently invalidates every expectation here: the numbers
# move for a legitimate reason and the check reports `agrees: false` as though the
# constants had drifted. A regime is the constants AND the universe they run on.
PHASE2_EXPECTATION = {
    ((0.55, 0.45, 0.0, 0.0), 0.25, -0.05, ("SPOT_FQ1_2026",)): (146, 95, 62, 0.6526),
    ((0.80, 0.20, 0.0, 0.0), 0.20, -0.10, ("SPOT_FQ1_2026",)): (169, 110, 69, 0.6273),
    # DIS_FQ1_2025 excluded 2026-08-24 for look-ahead; it was a graded, correct trade,
    # so all three counts fall by one.
    ((0.80, 0.20, 0.0, 0.0), 0.20, -0.10,
     ("DIS_FQ1_2025", "SPOT_FQ1_2026")): (168, 109, 68, 0.6239),
}


def _phase2_expectation(actual: dict) -> dict:
    from blend import DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER, DEFAULT_WEIGHTS
    key = (tuple(DEFAULT_WEIGHTS), DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER,
           tuple(sorted(EXCLUDED_EVENTS)))
    exp = PHASE2_EXPECTATION.get(key)
    if exp is None:
        return {"expected": f"no expectation recorded for {key} - record one",
                "agrees": None}
    got = (actual["n_trades"], actual["n_graded"], actual["n_correct"], actual["accuracy"])
    return {"expected": f"{exp[0]} trades, {exp[1]} graded, {exp[2]} correct, {exp[3]}",
            "expected_at": str(key),
            "agrees": got == exp}


def main() -> None:
    print("Loading phase2 frozen events...")
    phase2 = _load_phase2_events()
    print(f"  Phase2: {len(phase2)} clean events")

    print("Loading extension events...")
    extension = _load_extension_events()
    print(f"  Extension: {len(extension)} events")

    combined = phase2 + extension
    combined.sort(key=lambda e: e["release_date"])
    n_combined = len(combined)
    print(f"  Combined: {n_combined} events")
    print()

    # In-sample stats on the combined set
    print(f"In-sample statistics (deployed thresholds, combined N={len(combined)}):")
    is_stats = _in_sample_stats(combined)
    print(f"  Trades: {is_stats['n_trades']}, Graded: {is_stats['n_graded']}, "
          f"Correct: {is_stats['n_correct']}, Accuracy: {is_stats['accuracy']:.4f}")
    print(f"  Mean net: {is_stats['mean_net_pct']:+.4f}%  "
          f"90% CI [{is_stats['ci_low_90']:+.4f}%, {is_stats['ci_high_90']:+.4f}%]")
    print()

    # Verify phase2 subset matches known figures
    is_p2 = _in_sample_stats(phase2)
    exp2 = _phase2_expectation(is_p2)
    print(f"Sanity check — phase2 subset (expected at {exp2.get('expected_at', 'this regime')}: "
          f"{exp2['expected']}):")
    print(f"  Trades={is_p2['n_trades']}, Graded={is_p2['n_graded']}, "
          f"Correct={is_p2['n_correct']}, Acc={is_p2['accuracy']:.4f}"
          f"   -> {'agrees' if exp2['agrees'] else 'DOES NOT AGREE'}")
    print()

    # Rolling walk-forward (same window cutoffs as item_e_walkforward.json)
    WINDOW_CUTOFFS = ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]

    objectives = {
        "mean_net_per_trade": "mean_net",
        "directional_accuracy": "directional_accuracy",
    }

    wf_results: dict[str, dict] = {}
    for obj_label, obj_key in objectives.items():
        print(f"Walk-forward: {obj_label}")
        windows = []
        all_oos_nets = []
        all_oos_graded = 0
        all_oos_correct = 0
        degenerate_windows = 0

        for wi, cutoff in enumerate(WINDOW_CUTOFFS):
            train = [ev for ev in combined if ev["release_date"] <= cutoff]
            test = [ev for ev in combined if ev["release_date"] > cutoff]
            # Test window bounded by next cutoff
            if wi + 1 < len(WINDOW_CUTOFFS):
                next_cutoff = WINDOW_CUTOFFS[wi + 1]
                test = [ev for ev in test if ev["release_date"] <= next_cutoff]

            if len(train) < 5:
                degenerate_windows += 1
                continue

            best_u, best_l, train_stats = _fit_thresholds(train, obj_key)
            test_stats = _evaluate(test, best_u, best_l, obj_key)

            is_degenerate = test_stats["n_trades"] < MIN_TRADES_FLOOR
            if is_degenerate:
                degenerate_windows += 1

            win = {
                "window_idx": wi,
                "train_cutoff": cutoff,
                "test_start": test[0]["release_date"] if test else None,
                "test_end": test[-1]["release_date"] if test else None,
                "fitted_upper": round(best_u, 4),
                "fitted_lower": round(best_l, 4),
                "train_n": len(train),
                "train_trades": train_stats.get("n_trades", 0),
                "train_mean_net": round(train_stats.get("mean_net", 0), 7),
                "train_accuracy": round(train_stats.get("accuracy", 0), 4),
                "train_n_graded": train_stats.get("n_graded", 0),
                "test_n": len(test),
                "test_trades": test_stats["n_trades"],
                "test_mean_net": round(test_stats["mean_net"], 7),
                "test_accuracy": round(test_stats["accuracy"], 4) if test_stats["n_graded"] > 0 else None,
                "test_n_graded": test_stats["n_graded"],
                "test_n_correct": test_stats["n_correct"],
                "degenerate": is_degenerate,
            }
            windows.append(win)

            degenerate_str = " [DEGENERATE]" if is_degenerate else ""
            print(f"  Window {wi}: train≤{cutoff} (n={len(train)}), "
                  f"fitted ({best_u:.2f}/{best_l:.2f}), "
                  f"test n={len(test)}, trades={test_stats['n_trades']}, "
                  f"acc={test_stats['accuracy']:.3f}{degenerate_str}")

            # Accumulate OOS nets
            for ev in test:
                score = _blend(ev)
                sig = _signal(score, best_u, best_l)
                if sig != "HOLD":
                    net = (ev["ret_overnight"] if sig == "BUY" else -ev["ret_overnight"]) - COST_FRAC
                    all_oos_nets.append(net)
                    if abs(ev["ret_overnight"]) > FLAT_BAND:
                        all_oos_graded += 1
                        truth = "BUY" if ev["ret_overnight"] > 0 else "SELL"
                        if sig == truth:
                            all_oos_correct += 1

        oos_acc = all_oos_correct / all_oos_graded if all_oos_graded > 0 else None
        oos_mean_net = mean(all_oos_nets) * 100 if all_oos_nets else 0.0
        bs_oos = bootstrap_trade_stats(all_oos_nets) if all_oos_nets else {}

        floor_events = [ev for ev in combined
                        if abs(ev["ret_overnight"]) > FLAT_BAND and
                        ev["ret_overnight"] < 0]
        n_graded_total = sum(1 for ev in combined if abs(ev["ret_overnight"]) > FLAT_BAND)
        floor = len(floor_events) / n_graded_total if n_graded_total else 0.5

        pooled = {
            "objective": obj_label,
            "n_trades": len(all_oos_nets),
            "n_graded": all_oos_graded,
            "n_correct": all_oos_correct,
            "accuracy": round(oos_acc, 4) if oos_acc is not None else None,
            "mean_net_pct": round(oos_mean_net, 4),
            "majority_direction_floor": round(floor, 4),
            "bootstrap_90ci_mean_net_pct": {
                "point": round(bs_oos.get("mean_per_trade", {}).get("point", 0) * 100, 4) if bs_oos else 0,
                "ci_low": round(bs_oos.get("mean_per_trade", {}).get("ci_low", 0) * 100, 4) if bs_oos else 0,
                "ci_high": round(bs_oos.get("mean_per_trade", {}).get("ci_high", 0) * 100, 4) if bs_oos else 0,
            } if bs_oos else None,
        }

        acc_str = f"{oos_acc:.3f}" if oos_acc is not None else "N/A"
        print(f"  Pooled OOS: {len(all_oos_nets)} trades, "
              f"acc={acc_str}, "
              f"mean_net={oos_mean_net:+.4f}%")
        print(f"  Degenerate windows: {degenerate_windows}/{len(WINDOW_CUTOFFS)}")
        print()

        wf_results[obj_label] = {
            "degenerate_windows": degenerate_windows,
            "total_windows": len(WINDOW_CUTOFFS),
            "windows": windows,
            "pooled_oos": pooled,
        }

    # Compile output
    out = {
        "label": f"RETROSPECTIVE VALIDATION — NOT PRE-REGISTERED (combined N={len(combined)})",
        "n_combined_events": n_combined,
        "n_phase2_events": len(phase2),
        "n_extension_events": len(extension),
        "date_range": [combined[0]["release_date"], combined[-1]["release_date"]],
        "weights_fixed": list(DEFAULT_WEIGHTS),
        "cost_bps": COST_BPS,
        "flat_band": FLAT_BAND,
        "in_sample_deployed": is_stats,
        "rolling_walkforward": {
            "n_windows": len(WINDOW_CUTOFFS),
            "min_trades_floor": MIN_TRADES_FLOOR,
            "objectives_tried": list(objectives.keys()),
            "mean_net_per_trade": wf_results.get("mean_net_per_trade", {}),
            "directional_accuracy": wf_results.get("directional_accuracy", {}),
            "degeneracy_finding": {
                "mean_net_degenerate": wf_results.get("mean_net_per_trade", {}).get("degenerate_windows", None),
                "accuracy_degenerate": wf_results.get("directional_accuracy", {}).get("degenerate_windows", None),
                "total_windows": len(WINDOW_CUTOFFS),
                "both_degenerate": (
                    wf_results.get("mean_net_per_trade", {}).get("degenerate_windows", 0) > 0 and
                    wf_results.get("directional_accuracy", {}).get("degenerate_windows", 0) > 0
                ),
            },
        },
        "phase2_sanity_check": dict(
            {k: is_p2[k] for k in ("n_trades", "n_graded", "n_correct", "accuracy")},
            **_phase2_expectation(is_p2)),
    }

    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_JSON}")

    # Write summary CSV
    rows = []
    for obj_label, obj_data in wf_results.items():
        for win in obj_data.get("windows", []):
            rows.append({
                "objective": obj_label,
                **{k: v for k, v in win.items()},
            })

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print(f"Wrote {OUT_CSV}")


if __name__ == "__main__":
    main()
