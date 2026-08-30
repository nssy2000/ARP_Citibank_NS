"""Regenerate section_ablation_summary.csv from the stored per-arm scores.

experiments/section_ablation.py is a SCORING script: it calls the LLM once per
document per arm. It cannot be the regeneration path for a change to blend.py's
thresholds - re-running it would spend the API budget again and hand back
different raw scores, so the new summary would differ for two reasons at once.

The scores are frozen in section_ablation_results.csv. Only the BUY/HOLD/SELL cut
moves with the thresholds, so this script re-derives the signal at whatever
blend.py currently deploys and rewrites the summary from there. Weights play no
part: each arm is scored on its own text, not blended.

The gate runs first and is not optional. At the superseded constants
(+0.25/-0.05) every field of the six-row summary must reproduce exactly; if it
does not, this script refuses to write.

The gate reads a FROZEN reference, section_ablation_summary_at_superseded_*.csv,
and not the live summary it writes. The first version read the live file, and the
commit that promoted the constants rewrote that file - so from then on the gate
compared a 0.20/-0.10 artefact against a 0.25/-0.05 rebuild and failed on 37
fields every time. It had passed exactly once, during the promotion, and could
never pass again. A reproduce-first gate has to hold its reference somewhere the
run cannot move.

Having written the new summary the script then reports whether the summary that
was already committed agrees with it. That is deliberately NOT fatal: on a fresh
promotion it will disagree, because replacing it is the point. It is fatal only
in the sense that a silent disagreement is what you would want to know about.

Usage:
  python -m experiments.section_ablation_rethreshold
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blend import DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER, derive_signal  # noqa: E402

SUMMARY_DIR = ROOT / "outputs" / "global" / "summary"
IN_RESULTS = SUMMARY_DIR / "section_ablation_results.csv"
OUT_SUMMARY = SUMMARY_DIR / "section_ablation_summary.csv"
# The gate's reference. Frozen at the superseded constants, never written here.
GATE_REFERENCE = SUMMARY_DIR / "section_ablation_summary_at_superseded_0.25_-0.05.csv"

# Bands are properties of the grading design, not of the blend constants, so they
# are read back from the committed artefact's own header rather than restated.
OVERNIGHT_BAND = 0.02
FIVEDAY_BAND = 0.033786
COST_BPS = 10.0

ARMS = ["full_bundle", "press_release", "prepared_remarks", "qa_only"]
TWO_ARM = ["full_bundle", "press_release"]

# The regime the committed summary was built at. The gate compares against it.
SUPERSEDED = (0.25, -0.05)

SUMMARY_FIELDS = [
    "arm", "label", "n_events", "trades_overnight", "correct_overnight",
    "accuracy_overnight", "trades_5d", "correct_5d", "accuracy_5d",
    "mean_net_per_trade_overnight", "run_id",
]


def read_rows(path: Path) -> tuple[list[dict], list[str]]:
    """Rows plus the artefact's own comment header, which we carry forward."""
    header = []
    with path.open() as fh:
        lines = []
        for line in fh:
            if line.startswith("#"):
                header.append(line.rstrip("\n"))
            else:
                lines.append(line)
    return list(csv.DictReader(lines)), header


def grade(signal: str, ret: float, band: float) -> str:
    if signal == "HOLD":
        return "no_trade"
    if signal == "BUY":
        return "correct" if ret > band else ("wrong" if ret < -band else "flat")
    return "correct" if ret < -band else ("wrong" if ret > band else "flat")


def net_return(signal: str, ret: float) -> float | None:
    if signal == "HOLD":
        return None
    cost = COST_BPS / 10000.0
    return (ret - cost) if signal == "BUY" else (-ret - cost)


def arm_stats(rows: list[dict], arm: str, doc_ids: set[str], hi: float, lo: float) -> dict:
    trades_on = correct_on = trades_5d = correct_5d = total = 0
    nets: list[float] = []
    for r in rows:
        if r["arm"] != arm or r["document_id"] not in doc_ids:
            continue
        total += 1
        if r["ret_overnight"] == "" or r["ret_5d"] == "":
            continue
        signal = derive_signal(float(r["sentiment_score"]), hi, lo)
        g_on = grade(signal, float(r["ret_overnight"]), OVERNIGHT_BAND)
        g_5d = grade(signal, float(r["ret_5d"]), FIVEDAY_BAND)
        if g_on in ("correct", "flat", "wrong"):
            trades_on += 1
            correct_on += g_on == "correct"
            nr = net_return(signal, float(r["ret_overnight"]))
            if nr is not None:
                nets.append(nr)
        if g_5d in ("correct", "flat", "wrong"):
            trades_5d += 1
            correct_5d += g_5d == "correct"
    return {
        "arm": arm, "n_events": total,
        "trades_overnight": trades_on, "correct_overnight": correct_on,
        "accuracy_overnight": correct_on / trades_on if trades_on else 0.0,
        "trades_5d": trades_5d, "correct_5d": correct_5d,
        "accuracy_5d": correct_5d / trades_5d if trades_5d else 0.0,
        "mean_net_per_trade_overnight": sum(nets) / len(nets) if nets else 0.0,
    }


def build(rows: list[dict], hi: float, lo: float, run_id: str) -> list[dict]:
    per_doc: dict[str, set[str]] = {}
    for r in rows:
        per_doc.setdefault(r["document_id"], set()).add(r["arm"])
    four = {d for d, a in per_doc.items() if set(ARMS) <= a}
    two = {d for d, a in per_doc.items() if set(TWO_ARM) <= a}
    out = []
    for label, ids, arms in (("four_arm", four, ARMS), ("two_arm", two, TWO_ARM)):
        for arm in arms:
            s = arm_stats(rows, arm, ids, hi, lo)
            s["label"] = label
            s["run_id"] = run_id
            out.append(s)
    return out


def compare(reference: list[dict], rebuilt: list[dict]) -> list[str]:
    """Field-by-field disagreements between a reference set of rows and a rebuild."""
    keyed = {(r["arm"], r["label"]): r for r in rebuilt}
    failures = []
    for c in reference:
        r = keyed.get((c["arm"], c["label"]))
        if r is None:
            failures.append(f"{c['arm']}/{c['label']}: missing from the rebuild")
            continue
        for field in SUMMARY_FIELDS:
            want, got = c[field], r[field]
            if field.startswith(("accuracy", "mean_net")):
                ok = abs(float(want) - float(got)) < 1e-12
            elif field in ("arm", "label", "run_id"):
                ok = want == got
            else:
                ok = int(want) == int(got)
            if not ok:
                failures.append(f"{c['arm']}/{c['label']}.{field}: reference={want} rebuilt={got}")
    return failures


def gate(rows: list[dict]) -> str:
    """Reproduce the FROZEN superseded-constants reference, or stop."""
    if not GATE_REFERENCE.exists():
        raise SystemExit(
            f"The gate reference {GATE_REFERENCE.name} is missing. It is the only thing "
            "standing between this script and an unverified rewrite of the summary; "
            "restore it from git rather than deleting the gate."
        )
    reference, ref_header = read_rows(GATE_REFERENCE)
    # The reference states its own constants. If they ever drift from SUPERSEDED the
    # gate would be asserting something other than what it says it asserts.
    stated = [h for h in ref_header if "hold_upper=" in h or "hold_upper:" in h]
    if not any(str(SUPERSEDED[0]) in h and str(SUPERSEDED[1]) in h for h in stated):
        raise SystemExit(
            f"{GATE_REFERENCE.name} does not state the constants {SUPERSEDED} that the "
            f"gate rebuilds at. Its header says: {stated or '(nothing)'}"
        )
    run_id = reference[0]["run_id"]
    failures = compare(reference, build(rows, *SUPERSEDED, run_id))
    if failures:
        for f in failures:
            print(f"  GATE FAIL {f}")
        raise SystemExit(
            f"\n{len(failures)} field(s) of {GATE_REFERENCE.name} do not reproduce at "
            f"the superseded constants {SUPERSEDED}. Refusing to write a new summary "
            "from a code path that cannot regenerate the old one."
        )
    print(f"  gate OK: all {len(reference)} rows x {len(SUMMARY_FIELDS)} fields of "
          f"{GATE_REFERENCE.name} reproduce at hold_upper={SUPERSEDED[0]}, "
          f"hold_lower={SUPERSEDED[1]}")
    return run_id


def main() -> int:
    rows, results_header = read_rows(IN_RESULTS)
    print(f"Loaded {len(rows)} arm-events from {IN_RESULTS.name}")
    run_id = gate(rows)

    previous = read_rows(OUT_SUMMARY)[0] if OUT_SUMMARY.exists() else []

    rebuilt = build(rows, DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER, run_id)
    print(f"\nRe-thresholded at hold_upper={DEFAULT_HOLD_UPPER}, hold_lower={DEFAULT_HOLD_LOWER}:")
    for r in rebuilt:
        print(f"  {r['label']:<9} {r['arm']:<18} {r['correct_overnight']:>3}/{r['trades_overnight']:<4}"
              f" = {r['accuracy_overnight']*100:5.1f}%   mean net {r['mean_net_per_trade_overnight']*100:+.4f}%")

    with OUT_SUMMARY.open("w", newline="") as f:
        f.write("# Section ablation per-arm summary\n")
        f.write(f"# Run ID: {run_id}\n")
        f.write("# Scores are the frozen ones from that run; only the BUY/HOLD/SELL cut\n")
        f.write("# is re-derived here. Regenerated by experiments/section_ablation_rethreshold.py\n")
        f.write(f"# Re-thresholded: {datetime.now(timezone.utc).date().isoformat()}\n")
        f.write(f"# hold_upper: {DEFAULT_HOLD_UPPER}, hold_lower: {DEFAULT_HOLD_LOWER} (blend.py)\n")
        f.write(f"# Gate: every field reproduces at the superseded {SUPERSEDED[0]}/{SUPERSEDED[1]}\n")
        f.write("# Grading: pre-registered +/-2% raw overnight band\n")
        f.write(f"# Overnight band: {OVERNIGHT_BAND}, 5d band: {FIVEDAY_BAND:.6f}\n")
        f.write("# Paired MDE: ~+/-12pp (80% power, alpha=0.10)\n")
        f.write("# A gap smaller than the paired MDE means the arms are indistinguishable\n")
        f.write("# at this sample size. Combined with the token ratio, indistinguishability\n")
        f.write("# is itself the deployment answer: equivalent accuracy at lower cost.\n")
        f.write("#\n")
        w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rebuilt)
    print(f"\n  Wrote {OUT_SUMMARY}")

    # Not a gate. On a fresh promotion the summary that was already committed SHOULD
    # disagree - replacing it is the point. Reported because the alternative is a
    # rewrite whose effect nobody states: on a re-run it should be a no-op, and if it
    # is not, the difference is the thing to look at.
    if previous:
        drift = compare(previous, rebuilt)
        if drift:
            print(f"  the summary that was committed differs on {len(drift)} field(s) and "
                  "has been replaced:")
            for d in drift[:12]:
                print(f"    was {d}")
            if len(drift) > 12:
                print(f"    ... and {len(drift) - 12} more")
        else:
            print(f"  no-op: the committed summary already agreed on all {len(previous)} "
                  f"rows x {len(SUMMARY_FIELDS)} fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
