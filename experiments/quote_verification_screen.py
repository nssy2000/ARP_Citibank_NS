"""
experiments/quote_verification_screen.py
Item 8 of the model-arm spec (Nigel, 2026-08-05): mechanical verification of
the LLM's evidence quotes against the source document text, so fabricated
quotes are caught before a human spends review time on them.

Evidence quotes already exist in the scored output schema - nothing needed
adding to the pipeline. Each outputs/<issuer>/results/<document_id>.json
carries evidence[] = [{claim, quote, confidence, flag}, ...], produced per
the OUTPUT 4 instruction in prompts/llm_analysis_prompt_template.md (verbatim
quote required for every material claim). run_meta.extracted_text_path in
the same JSON points at the cached source text - no recomputation needed.

Sample: 15 documents stratified by (sector, outcome_label) so the sample
isn't all clean beats. Match: exact substring after normalizing whitespace
and quote characters, fuzzy fallback via rapidfuzz.fuzz.partial_ratio at a
90% threshold. Flags: exact / near / absent - absent is a reject before any
human sees it.

Run: python -m experiments.quote_verification_screen
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import numpy as np
from rapidfuzz import fuzz

from backtest import OUTPUTS_DIR

# phase2/build_manifests.py does a bare `from triage_docs import ...`, which only
# resolves with phase2/ itself on sys.path (its normal invocation is
# `python phase2/build_manifests.py`, not a package import) - match that
# convention rather than fighting it.
_PHASE2_DIR = Path(__file__).resolve().parent.parent / "phase2"
if str(_PHASE2_DIR) not in sys.path:
    sys.path.insert(0, str(_PHASE2_DIR))
from build_manifests import SECTORS

PHASE2_CALIBRATION_CSV = OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration_phase2.csv"
FULL_CSV = OUTPUTS_DIR / "global" / "summary" / "quote_verification_full.csv"
HANDOVER_CSV = OUTPUTS_DIR / "global" / "summary" / "quote_verification_handover.csv"

SAMPLE_N = 15
FUZZY_THRESHOLD = 90.0
RNG_SEED = 20260709

_QUOTE_CHARS = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
})


def normalize_text(s: str) -> str:
    s = s.translate(_QUOTE_CHARS)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def load_calibration_rows(path: Path = PHASE2_CALIBRATION_CSV) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def stratified_sample(rows: list[dict], n: int = SAMPLE_N, seed: int = RNG_SEED) -> list[dict]:
    """Strata key = (sector, outcome_label). Deterministic round-robin draw
    across strata until n is reached (or every row is exhausted)."""
    strata: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        sector = SECTORS.get(r["ticker"], "Unknown")
        key = (sector, r["outcome_label"])
        strata.setdefault(key, []).append(r)

    rng = np.random.default_rng(seed)
    for bucket in strata.values():
        rng.shuffle(bucket)

    keys = sorted(strata.keys())
    picked: list[dict] = []
    i = 0
    while len(picked) < n and any(strata[k] for k in keys):
        k = keys[i % len(keys)]
        if strata[k]:
            picked.append(strata[k].pop())
        i += 1
    return picked[:n]


def result_json_path(issuer: str, document_id: str) -> Path:
    return OUTPUTS_DIR / issuer / "results" / f"{document_id}.json"


_ELLIPSIS_RE = re.compile(r"\.\.\.|…")


def _match_segment(seg: str, ns: str, threshold: float) -> tuple[str, float]:
    seg = seg.strip()
    if not seg:
        return "exact", 100.0  # empty segment (leading/trailing ellipsis) trivially passes
    if seg in ns:
        return "exact", 100.0
    score = fuzz.partial_ratio(seg, ns)
    return ("near" if score >= threshold else "absent"), score


def classify_quote(quote: str, source_text: str, threshold: float = FUZZY_THRESHOLD) -> tuple[str, float]:
    """Whole-string match first. If that fails and the quote contains an
    explicit ellipsis marker ("..." or the unicode "…"), the model is
    signalling an intentional elision (common on table rows and long
    transcript answers) - split on it and require every segment to verify
    independently instead of matching the whole string as one blob, since a
    real elision breaks contiguous/fuzzy alignment across the gap even
    though every segment on its own is genuine. Without an ellipsis marker,
    a whole-string miss stays a miss - e.g. a quote that stitches together
    non-adjacent table cells (a header prepended to a data row that isn't
    contiguous in the linearized source) without signalling the gap is a
    real non-verbatim reconstruction, not something to rescue here."""
    nq = normalize_text(quote)
    ns = normalize_text(source_text)
    if not nq:
        return "absent", 0.0
    if nq in ns:
        return "exact", 100.0
    whole_score = fuzz.partial_ratio(nq, ns)
    if whole_score >= threshold:
        return "near", whole_score

    if _ELLIPSIS_RE.search(nq):
        segments = [s for s in _ELLIPSIS_RE.split(nq)]
        results = [_match_segment(seg, ns, threshold) for seg in segments]
        statuses = [r[0] for r in results]
        scores = [r[1] for r in results if r[1] > 0]
        min_score = min(scores) if scores else whole_score
        if all(s in ("exact", "near") for s in statuses):
            # every elided segment verifies independently - genuine elision,
            # not fabrication, but still not literally verbatim as a whole
            return "near", min_score
        return "absent", min_score

    return "absent", whole_score


def screen_document(calib_row: dict) -> list[dict]:
    issuer = calib_row["issuer"]
    document_id = calib_row["document_id"]
    ticker = calib_row["ticker"]
    sector = SECTORS.get(ticker, "Unknown")
    outcome_label = calib_row["outcome_label"]

    result_path = result_json_path(issuer, document_id)
    if not result_path.exists():
        print(f"  Skipping {document_id}: no result JSON at {result_path}")
        return []
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    text_path_str = payload.get("run_meta", {}).get("extracted_text_path")
    if not text_path_str or not Path(text_path_str).exists():
        print(f"  Skipping {document_id}: no extracted_text_path on disk")
        return []
    source_text = Path(text_path_str).read_text(encoding="utf-8", errors="replace")

    rows = []
    for i, item in enumerate(payload.get("evidence", [])):
        quote = item.get("quote", "") or ""
        status, score = classify_quote(quote, source_text)
        rows.append({
            "document_id": document_id, "ticker": ticker, "sector": sector,
            "outcome_label": outcome_label, "evidence_index": i,
            "claim": item.get("claim", ""), "quote": quote,
            "confidence": item.get("confidence", ""), "model_flag": item.get("flag", ""),
            "match_status": status, "match_score": round(score, 1),
        })
    return rows


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {path}")


def main() -> int:
    calib_rows = load_calibration_rows()
    sample = stratified_sample(calib_rows)
    print(f"Sampled {len(sample)} documents across "
          f"{len({(SECTORS.get(r['ticker'],'Unknown'), r['outcome_label']) for r in sample})} strata")

    all_rows: list[dict] = []
    for calib_row in sample:
        all_rows.extend(screen_document(calib_row))

    fieldnames = ["document_id", "ticker", "sector", "outcome_label", "evidence_index",
                  "claim", "quote", "confidence", "model_flag", "match_status", "match_score"]
    write_csv(FULL_CSV, all_rows, fieldnames)

    handover_rows = [r for r in all_rows if r["match_status"] in ("exact", "near")]
    handover_fields = ["document_id", "ticker", "claim", "quote", "confidence",
                        "match_status", "match_score"]
    write_csv(HANDOVER_CSV, [{k: r[k] for k in handover_fields} for r in handover_rows], handover_fields)

    n_exact = sum(1 for r in all_rows if r["match_status"] == "exact")
    n_near = sum(1 for r in all_rows if r["match_status"] == "near")
    n_absent = sum(1 for r in all_rows if r["match_status"] == "absent")
    print(f"\n{len(all_rows)} evidence items screened: "
          f"{n_exact} exact, {n_near} near, {n_absent} absent")
    if n_absent:
        print("Absent items (rejected before human review):")
        for r in all_rows:
            if r["match_status"] == "absent":
                print(f"  {r['document_id']} #{r['evidence_index']}: {r['quote'][:80]!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
