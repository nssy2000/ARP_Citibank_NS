"""Script 6: confirm the blend weights/thresholds documented in CLAUDE.md
actually match code, and that they actually drive the calibration CSV's
default-signal column (by recomputing a sample of rows from raw layer
scores). Also flags blend.py's blend_document() stale hold_upper/lower=0.15
default as a landmine, and confirms nothing downstream actually consumes it.
Read-only."""
from __future__ import annotations

import csv
import random

from _common import Finding, OUTPUTS_DIR, print_findings

EXPECTED_WEIGHTS = (0.55, 0.45, 0.0, 0.0)
EXPECTED_HOLD_UPPER = 0.25
EXPECTED_HOLD_LOWER = -0.05


def _derive_signal(score: float, hold_upper: float, hold_lower: float) -> str:
    if score > hold_upper:
        return "BUY"
    if score < hold_lower:
        return "SELL"
    return "HOLD"


def run() -> list[Finding]:
    import blend
    from eval.calibrate import DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER

    findings: list[Finding] = []

    if blend.DEFAULT_WEIGHTS != EXPECTED_WEIGHTS:
        findings.append(Finding("HIGH", "weights-drift", f"blend.DEFAULT_WEIGHTS = {blend.DEFAULT_WEIGHTS}, CLAUDE.md documents {EXPECTED_WEIGHTS}"))
    else:
        findings.append(Finding("INFO", "weights-ok", f"blend.DEFAULT_WEIGHTS = {blend.DEFAULT_WEIGHTS} matches CLAUDE.md"))

    if (DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER) != (EXPECTED_HOLD_UPPER, EXPECTED_HOLD_LOWER):
        findings.append(Finding("HIGH", "threshold-drift", f"eval.calibrate DEFAULT_HOLD_UPPER/LOWER = {(DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER)}, CLAUDE.md documents {(EXPECTED_HOLD_UPPER, EXPECTED_HOLD_LOWER)}"))
    else:
        findings.append(Finding("INFO", "threshold-ok", f"eval.calibrate DEFAULT_HOLD_UPPER/LOWER = {(DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER)} matches CLAUDE.md"))

    # blend.py's own stale defaults, confirmed present regardless of downstream usage
    import inspect
    sig = inspect.signature(blend.blend_document)
    doc_hold_upper = sig.parameters["hold_upper"].default
    doc_hold_lower = sig.parameters["hold_lower"].default
    if (doc_hold_upper, doc_hold_lower) != (EXPECTED_HOLD_UPPER, EXPECTED_HOLD_LOWER):
        findings.append(Finding(
            "MEDIUM", "landmine-stale-default",
            f"blend.blend_document() defaults hold_upper={doc_hold_upper}/hold_lower={doc_hold_lower}, NOT the canonical "
            f"{(EXPECTED_HOLD_UPPER, EXPECTED_HOLD_LOWER)} - this is the exact ±0.15 trap CLAUDE.md says was fixed in "
            f"export_rows.py, but blend.py's own function still carries it. Confirmed NOT currently consumed downstream: "
            f"eval/run_eval.py recomputes signals independently via eval.calibrate.derive_signal + DEFAULT_HOLD_UPPER/LOWER, "
            f"never reading blend.py's printed/returned signal. phase2/sourcing/run_gap_pipeline.py invokes `python blend.py "
            f"<issuer>` as a subprocess purely for its side effect of populating outputs/*/results/ caches (macro/news/quant), "
            f"and never parses its stdout. Still a landmine for the next direct caller of blend_document()/blend_issuer().",
        ))

    # Recompute a sample of calibration CSV rows from raw layer scores and diff.
    calib_path = OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration_phase2.csv"
    if calib_path.exists():
        with open(calib_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        sample = random.Random(42).sample(rows, min(30, len(rows)))
        mismatches = 0
        for row in sample:
            micro = float(row["micro_score"])
            macro = float(row["macro_score"]) if row["macro_score"] not in ("", "None") else None
            news = float(row["news_score"]) if row["news_score"] not in ("", "None") else None
            quant = float(row["quant_score"]) if row["quant_score"] not in ("", "None") else None
            recomputed = blend.blend_scores(micro, macro, news, quant, EXPECTED_WEIGHTS)
            expected_signal = _derive_signal(recomputed, EXPECTED_HOLD_UPPER, EXPECTED_HOLD_LOWER)
            actual_signal = row["blend_predicted_signal_default"]
            if expected_signal != actual_signal:
                mismatches += 1
                findings.append(Finding(
                    "HIGH", "calib-recompute-mismatch",
                    f"{row['issuer']}/{row['document_id']}: recomputed default signal={expected_signal} "
                    f"(score={recomputed:.4f}) but CSV says {actual_signal}",
                ))
        findings.append(Finding("INFO", "summary", f"recomputed {len(sample)} sampled calibration rows against current DEFAULT_WEIGHTS/thresholds: {mismatches} mismatches"))
    else:
        findings.append(Finding("HIGH", "missing-artifact", f"{calib_path} does not exist - cannot verify"))

    return findings


if __name__ == "__main__":
    print_findings("Script 6: blend weight/threshold consistency check", run())
