"""
compare_runs.py
Citibank Applied Research Project - side-by-side comparison of two runs.

Reads the per-document result JSONs from two output folders (e.g. the default
prompt run and a --variant run on the same manifest, or an ensemble run
against a single-shot run), aligns them on document_id, and prints scores,
signals, agreement, and cost. If a ground truth CSV is supplied it also
derives the true label from the overnight move and reports directional
accuracy per arm.

Ground truth CSV columns: document_id, overnight_move_pct
The move is close[t-1] to open[t+1] as a percentage, per the project convention.
The HOLD band on the move must be fixed before anyone looks at accuracy.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_a", type=Path, help="First results folder, e.g. outputs/netflix/results")
    parser.add_argument("results_b", type=Path, help="Second results folder, e.g. outputs/netflix_v2/results")
    parser.add_argument("--label-a", default=None, help="Display name for the first arm")
    parser.add_argument("--label-b", default=None, help="Display name for the second arm")
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=None,
        help="Optional CSV of document_id, overnight_move_pct",
    )
    parser.add_argument(
        "--move-hold-band",
        type=float,
        default=None,
        help=(
            "HOLD band on the overnight move in percent, e.g. 1.0 means a move "
            "inside plus or minus 1%% is HOLD. Required with --ground-truth."
        ),
    )
    return parser.parse_args()


def load_results(folder: Path) -> dict[str, dict[str, Any]]:
    results = {}
    for path in sorted(folder.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        meta = payload.get("run_meta", {})
        label = meta.get("model", "unknown")
        if meta.get("prompt"):
            label += " / " + Path(meta["prompt"]).stem.replace("llm_", "")
        results[payload["document_id"]] = {
            "score": float(payload["sentiment"]["score"]),
            "signal": payload["signal"]["direction"],
            "model": label,
        }
    return results


def load_ground_truth(path: Path, band: float) -> dict[str, dict[str, Any]]:
    truth = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            move = float(row["overnight_move_pct"])
            if move > band:
                label = "BUY"
            elif move < -band:
                label = "SELL"
            else:
                label = "HOLD"
            truth[row["document_id"].strip()] = {"move": move, "label": label}
    return truth


def main() -> int:
    args = parse_args()
    results_a = load_results(args.results_a)
    results_b = load_results(args.results_b)

    shared = sorted(set(results_a) & set(results_b))
    if not shared:
        print("No overlapping document_ids between the two folders.")
        return 1

    label_a = args.label_a or next(iter(results_a.values()))["model"]
    label_b = args.label_b or next(iter(results_b.values()))["model"]

    truth = {}
    if args.ground_truth:
        if args.move_hold_band is None:
            print("--move-hold-band is required with --ground-truth.")
            return 1
        truth = load_ground_truth(args.ground_truth, args.move_hold_band)

    header = f"{'document_id':<18} {label_a[:24]:>24} {label_b[:24]:>24} {'agree':>6}"
    if truth:
        header += f" {'move%':>7} {'truth':>5} {'A?':>3} {'B?':>3}"
    print(header)
    print("-" * len(header))

    agree_count = 0
    correct_a = 0
    correct_b = 0
    scored = 0

    for doc_id in shared:
        a, b = results_a[doc_id], results_b[doc_id]
        agree = a["signal"] == b["signal"]
        agree_count += agree
        line = (
            f"{doc_id:<18}"
            f" {a['signal'] + ' ' + format(a['score'], '+.2f'):>24}"
            f" {b['signal'] + ' ' + format(b['score'], '+.2f'):>24}"
            f" {'yes' if agree else 'NO':>6}"
        )
        if truth:
            entry = truth.get(doc_id)
            if entry:
                scored += 1
                hit_a = a["signal"] == entry["label"]
                hit_b = b["signal"] == entry["label"]
                correct_a += hit_a
                correct_b += hit_b
                line += (
                    f" {entry['move']:>+7.2f} {entry['label']:>5}"
                    f" {'y' if hit_a else 'n':>3} {'y' if hit_b else 'n':>3}"
                )
            else:
                line += f" {'-':>7} {'-':>5} {'-':>3} {'-':>3}"
        print(line)

    print("-" * len(header))
    print(f"Documents compared: {len(shared)}")
    print(f"Signal agreement:   {agree_count}/{len(shared)}")
    if truth and scored:
        print(f"Accuracy {label_a}: {correct_a}/{scored}")
        print(f"Accuracy {label_b}: {correct_b}/{scored}")
        print(
            "Reminder: with a handful of documents these figures are directional "
            "only, so report them with that caveat."
        )
    only_a = sorted(set(results_a) - set(results_b))
    only_b = sorted(set(results_b) - set(results_a))
    if only_a:
        print(f"Only in {label_a}: {', '.join(only_a)}")
    if only_b:
        print(f"Only in {label_b}: {', '.join(only_b)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
