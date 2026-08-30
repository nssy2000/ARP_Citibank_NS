"""
experiments/macro_ablation_analysis.py
Item 1b/1c of the model-arm spec (Nigel, 2026-08-05): a paired bootstrap
interval on the macro-on vs macro-off accuracy difference (per-event, not two
overlapping single-arm intervals - the sample size rewards pairing since
event-to-event variation cancels out), plus the same comparison split by
sector.

No second scored run needed - the phase2 calibration CSV already carries raw
per-layer scores, so this is two blend_scores() calls per row:
  macro_on  = blend_scores(micro, macro, news, quant, weights=(0.55,0.45,0,0))  # DEFAULT_WEIGHTS
  macro_off = blend_scores(micro, macro, news, quant, weights=(0.55,0.0,0,0))   # renormalizes to
                                                                                  # blended=micro_score
Deliberately NOT using the CSV's own blend_correct_default vs
blend_correct_tuned columns for this - blend_tuned_weights is a constant
(0.6, 0.0, 0.4, 0.0) across every row, which moves micro AND news at the same
time as zeroing macro, so it isn't a clean ceteris-paribus ablation.

Run: python -m experiments.macro_ablation_analysis
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from backtest import OUTPUTS_DIR
from blend import DEFAULT_WEIGHTS, blend_scores, derive_signal
from bootstrap_stats import bootstrap_paired_difference

_PHASE2_DIR = Path(__file__).resolve().parent.parent / "phase2"
if str(_PHASE2_DIR) not in sys.path:
    sys.path.insert(0, str(_PHASE2_DIR))
from build_manifests import SECTORS

PHASE2_CALIBRATION_CSV = OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration_phase2.csv"
PAIRED_CSV = OUTPUTS_DIR / "global" / "summary" / "macro_ablation_paired.csv"
SUMMARY_JSON = OUTPUTS_DIR / "global" / "summary" / "macro_ablation_summary.json"
SECTOR_CSV = OUTPUTS_DIR / "global" / "summary" / "macro_ablation_by_sector.csv"

MACRO_OFF_WEIGHTS = (DEFAULT_WEIGHTS[0], 0.0, 0.0, 0.0)


def _num(x):
    if x is None or x == "":
        return None
    return float(x)


def macro_ablation_per_event(path: Path = PHASE2_CALIBRATION_CSV) -> list[dict]:
    events = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            micro = _num(r["micro_score"])
            if micro is None:
                continue
            macro, news, quant = _num(r["macro_score"]), _num(r["news_score"]), _num(r["quant_score"])
            truth = r["outcome_label"]

            score_on = blend_scores(micro, macro, news, quant, weights=DEFAULT_WEIGHTS)
            score_off = blend_scores(micro, macro, news, quant, weights=MACRO_OFF_WEIGHTS)

            events.append({
                "document_id": r["document_id"], "ticker": r["ticker"],
                "outcome_label": truth,
                "macro_on_correct": int(derive_signal(score_on) == truth),
                "macro_off_correct": int(derive_signal(score_off) == truth),
            })
    return events


def by_sector(events: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for e in events:
        sector = SECTORS.get(e["ticker"], "Unknown")
        grouped.setdefault(sector, []).append(e)

    out = []
    for sector, evs in sorted(grouped.items()):
        n = len(evs)
        acc_on = sum(e["macro_on_correct"] for e in evs) / n
        acc_off = sum(e["macro_off_correct"] for e in evs) / n
        out.append({
            "sector": sector, "n": n,
            "accuracy_on": round(acc_on, 4), "accuracy_off": round(acc_off, 4),
            "delta": round(acc_on - acc_off, 4),
        })
    return out


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {path}")


def main() -> int:
    events = macro_ablation_per_event()
    print(f"Loaded {len(events)} events for macro ablation (phase2 calibration CSV)")

    # sanity assertion: macro-off weights (0.55,0,0,0) must renormalize to
    # exactly the micro-only blend - confirms blend_scores' redistribution
    # behaves as expected rather than silently producing something else.
    on_off_events = [
        (blend_scores(_num("0.4"), _num("0.2"), _num("-0.2"), _num("0.5"), weights=DEFAULT_WEIGHTS),
         blend_scores(_num("0.4"), _num("0.2"), _num("-0.2"), _num("0.5"), weights=MACRO_OFF_WEIGHTS)),
    ]
    _, off_test = on_off_events[0]
    assert abs(off_test - 0.4) < 1e-9, f"macro-off ablation sanity check failed: got {off_test}, expected micro=0.4"
    print("Sanity check passed: macro-off weights renormalize to blended == micro_score")

    write_csv(PAIRED_CSV, events)

    on_correct = [e["macro_on_correct"] for e in events]
    off_correct = [e["macro_off_correct"] for e in events]
    diff = bootstrap_paired_difference(on_correct, off_correct)

    acc_on = sum(on_correct) / len(events)
    acc_off = sum(off_correct) / len(events)
    summary = {
        "n": len(events),
        "accuracy_macro_on": round(acc_on, 4),
        "accuracy_macro_off": round(acc_off, 4),
        "point_diff": round(diff["point_diff"], 4),
        "ci_low": round(diff["ci_low"], 4),
        "ci_high": round(diff["ci_high"], 4),
        "p_value": round(diff["p_value"], 4),
        "deployed_default_weights": list(DEFAULT_WEIGHTS),
        "macro_off_weights": list(MACRO_OFF_WEIGHTS),
    }
    import json
    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote summary -> {SUMMARY_JSON}")
    print(f"\nmacro-on accuracy={acc_on:.4f}, macro-off accuracy={acc_off:.4f}, "
          f"diff={diff['point_diff']:+.4f} [{diff['ci_low']:+.4f}, {diff['ci_high']:+.4f}], "
          f"p={diff['p_value']:.4f}")

    sector_rows = by_sector(events)
    write_csv(SECTOR_CSV, sector_rows)
    print("\nBy sector:")
    for s in sector_rows:
        print(f"  {s['sector']:35} n={s['n']:3}  on={s['accuracy_on']:.3f}  "
              f"off={s['accuracy_off']:.3f}  delta={s['delta']:+.3f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
