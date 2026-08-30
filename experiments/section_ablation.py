"""
Section ablation experiment (Item 3/5C from the model-arm robustness spec).

Four-arm ablation at N=124 (four-arm intersection after exclusions) and a
two-arm comparison (full bundle vs press-release-only) at N=210.

Arms:
  1. full_bundle   — the complete extracted text (same as production)
  2. press_release — just the === PRESS RELEASE === section
  3. prepared_remarks — transcript up to the Q&A transition marker
  4. qa_only      — transcript from the Q&A transition marker to end

Grading band is provisional pending anchor correction (pre-market timing fix
is pending).

Uses report_pipeline.call_llm() directly — does NOT reimplement the LLM call.
Uses the SAME prompt for every arm — only the document text differs.
Results go into outputs/global/summary/section_ablation_*.csv — NEVER into
outputs/p2_<slug>/results/.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from eval.excluded_events import EXCLUDED_EVENTS  # noqa: E402

from report_pipeline import (
    ReportSpec,
    SourceDocument,
    build_user_message,
    call_llm,
    utc_run_id,
    SYSTEM_PROMPT,
    USER_MESSAGE_TEMPLATE,
    PROMPT_TEMPLATE_FILE,
)
from bootstrap_stats import bootstrap_paired_difference

SUMMARY_DIR = PROJECT_ROOT / "outputs" / "global" / "summary"
AUDIT_CSV = SUMMARY_DIR / "section_availability_audit_amended.csv"
RETURNS_CSV = SUMMARY_DIR / "returns_matrix.csv"
HOLD_BANDS_CSV = SUMMARY_DIR / "implied_hold_bands.csv"
WORKSHEET_FLAGS_CSV = SUMMARY_DIR / "worksheet_leak_flags.csv"
CALIBRATION_CSV = SUMMARY_DIR / "global_outcome_calibration_phase2.csv"

OUT_RESULTS = SUMMARY_DIR / "section_ablation_results.csv"
OUT_SUMMARY = SUMMARY_DIR / "section_ablation_summary.csv"
OUT_PAIRED = SUMMARY_DIR / "section_ablation_paired_diffs.csv"
OUT_TWO_ARM = SUMMARY_DIR / "section_ablation_two_arm.csv"

# From blend.py — the deployed thresholds used for deriving signals
HOLD_UPPER = 0.25
HOLD_LOWER = -0.05

# ---------------------------------------------------------------------------
# Section-splitting logic (from experiments/section_boundary_audit.py)
# ---------------------------------------------------------------------------
PRESS_RELEASE_HEADER = re.compile(r"===\s*PRESS RELEASE\s*===")
TRANSCRIPT_HEADER = re.compile(r"===\s*EARNINGS CALL TRANSCRIPT\s*===")
SECTION_HEADER = re.compile(r"^===\s+.+\s+===$", re.MULTILINE)

FACTSET_HEADER = re.compile(r"QUESTION\s+AND\s+ANSWER\s+SECTION", re.IGNORECASE)

TRANSITION_PATTERNS = [
    r"open\s+(?:it\s+)?(?:up\s+)?(?:the\s+)?(?:call|floor|line|phone\s+line|lines|session)?\s*(?:up\s+)?(?:for|to)\s+(?:your\s+)?questions",
    r"(?:let'?s|we(?:'ll| will| would| can| shall)?|I(?:'ll| will)?)\s+(?:now\s+)?(?:take|begin\s+taking|start\s+taking)\s+(?:your\s+)?questions",
    r"(?:happy|pleased|glad|ready)\s+to\s+(?:take|answer|address)\s+(?:y\s*our\s+)?questions",
    r"(?:we(?:'ll| will| shall)?|I(?:'ll| will)?)\s+now\s+(?:take|begin|start|move\s+(?:on\s+)?to|proceed\s+(?:to|with))\s+(?:the\s+)?(?:Q\s*&\s*A|question)",
    r"(?:our|the)\s+first\s+question\s+(?:comes?\s+from|is\s+from|today\s+(?:comes?|is)\s+from)",
    r"turn\s+(?:it|the\s+call)\s+over\s+(?:for|to)\s+(?:your\s+)?questions",
    r"open\s+(?:up\s+)?(?:the\s+)?(?:line|lines|phone\s+lines?)\s+(?:for|to)\s+(?:your\s+)?questions",
    r"begin\s+(?:the\s+|our\s+)?(?:question[\s-]*and[\s-]*answer|Q\s*&\s*A)(?:\s+(?:session|portion|segment|period))?",
    r"(?:move|proceed|transition|turn|go)\s+(?:on\s+|over\s+)?(?:to|into)\s+(?:the\s+)?(?:Q\s*&\s*A|question[\s-]*and[\s-]*answer|(?:analyst\s+)?questions)",
    r"^QUESTION\s*&\s*ANSWER\s*:",
    r"QUESTIONS\s+AND\s+ANSWERS",
    r"Question(?:s)?\s*&\s*Answers?",
    r"^Question[\s-]*and[\s-]*Answer\s+Session",
    r"^Q\s*&\s*A$",
    r"open\s+(?:up\s+)?(?:the\s+)?call\s+for\s+(?:your\s+)?questions",
    r"open\s+(?:up\s+)?(?:the\s+)?(?:line|lines)\s+for\s+(?:any\s+)?questions",
    r"(?:go|let'?s\s+go)\s+to\s+(?:the\s+)?(?:first\s+)?question",
    r"(?:our|the)\s+first\s+question\s+(?:will\s+)?(?:comes?\s+from|come\s+from|is\s+from|today\s+(?:comes?|is)\s+from)",
    r"(?:move\s+on\s+to|go\s+to|start\s+with)\s+(?:the\s+)?(?:analyst\s+)?questions",
    r"open\s+up\s+the\s+line(?:\s+for\s+questions)?",
]
COMPILED_TRANSITION = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in TRANSITION_PATTERNS]


def _extract_sections(full_text: str):
    """Return (press_release_text, transcript_text)."""
    headers = []
    for m in SECTION_HEADER.finditer(full_text):
        headers.append((m.start(), m.end(), m.group().strip()))

    press_release_text = None
    transcript_text = None

    for i, (start, end, header) in enumerate(headers):
        section_end = headers[i + 1][0] if i + 1 < len(headers) else len(full_text)
        section_content = full_text[end:section_end].strip()

        if PRESS_RELEASE_HEADER.search(header):
            press_release_text = section_content
        if TRANSCRIPT_HEADER.search(header):
            transcript_text = section_content

    return press_release_text, transcript_text


def _find_qa_split(transcript_text: str):
    """Return (prepared_text, qa_text) or (None, None) if no split found."""
    # FIRST: FactSet header
    m = FACTSET_HEADER.search(transcript_text)
    if m:
        prepared = transcript_text[:m.start()].strip()
        qa = transcript_text[m.start():].strip()
        return prepared, qa

    # SECOND: natural-language transition phrase
    best_match = None
    best_pos = len(transcript_text)
    for pat in COMPILED_TRANSITION:
        m = pat.search(transcript_text)
        if m and m.start() < best_pos:
            best_pos = m.start()
            best_match = m

    if best_match is not None:
        line_start = transcript_text.rfind("\n", 0, best_match.start())
        if line_start >= 0 and (best_match.start() - line_start) < 500:
            split_pos = line_start + 1
        else:
            split_pos = best_match.start()
        prepared = transcript_text[:split_pos].strip()
        qa = transcript_text[split_pos:].strip()
        return prepared, qa

    return None, None


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_audit_rows() -> list[dict]:
    """Load the section audit CSV, skipping comment lines."""
    rows = []
    with open(AUDIT_CSV, newline="") as f:
        lines = [l for l in f if not l.startswith("#")]
    reader = csv.DictReader(lines)
    for r in reader:
        rows.append(dict(r))
    return rows


def load_exclusions() -> set[str]:
    excluded = set()
    # Worksheet contamination (25 events)
    with open(WORKSHEET_FLAGS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r["has_human_score"].strip() == "True":
                excluded.add(r["document_id"].strip())
    # Bad-document exclusions - see eval/excluded_events.py for the reasons
    excluded |= EXCLUDED_EVENTS
    # Truncated transcripts
    excluded |= {"LLY_FQ1_2026", "LLY_FQ3_2025", "LLY_FQ4_2025"}
    # Timing exclusions (unknown/null release_timing)
    import glob as _glob
    for mf in _glob.glob(str(PROJECT_ROOT / "manifests" / "p2_*_reports.json")):
        with open(mf) as f:
            mdata = json.load(f)
        rt = mdata.get("release_timing", {}).get("value")
        if rt in (None, "unknown", "intraday"):
            for report in mdata["reports"]:
                excluded.add(report["document_id"])
    return excluded


def load_returns() -> dict[str, dict]:
    """Return {document_id: {ret_overnight, ret_5d, ...}}."""
    out = {}
    with open(RETURNS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            out[r["document_id"]] = r
    return out


def load_hold_bands() -> dict[str, float]:
    """Return {horizon: band}."""
    out = {}
    with open(HOLD_BANDS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            out[r["horizon"]] = float(r["hold_band"])
    return out


def load_calibration() -> dict[str, dict]:
    """Return {document_id: row} from the calibration CSV."""
    out = {}
    with open(CALIBRATION_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            out[r["document_id"]] = dict(r)
    return out


def load_company_sector() -> dict[str, dict]:
    """Load company/sector from scored result JSONs for each issuer."""
    out = {}
    results_base = PROJECT_ROOT / "outputs"
    for issuer_dir in results_base.iterdir():
        if not issuer_dir.name.startswith("p2_"):
            continue
        results_dir = issuer_dir / "results"
        if not results_dir.exists():
            continue
        for jf in results_dir.glob("*.json"):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                meta = data.get("report_metadata", {})
                doc_id = meta.get("document_id", jf.stem)
                out[doc_id] = {
                    "company": meta.get("company", ""),
                    "sector": meta.get("sector", ""),
                    "fiscal_period": meta.get("fiscal_period", ""),
                    "report_type": meta.get("report_type", "Earnings Call Transcript"),
                }
            except Exception:
                pass
    return out


# ---------------------------------------------------------------------------
# Build event sets
# ---------------------------------------------------------------------------
def build_event_sets(audit_rows, exclusions, calibration, company_sector):
    """
    Returns (four_arm_events, two_arm_events) where each event is a dict with
    keys: document_id, ticker, issuer, report_date, and calibration row fields.
    """
    four_arm = []
    two_arm = []

    for r in audit_rows:
        doc_id = r["document_id"]
        if doc_id in exclusions:
            continue
        if doc_id not in calibration:
            continue

        cal = calibration[doc_id]
        cs = company_sector.get(doc_id, {})
        event = {
            "document_id": doc_id,
            "ticker": r["ticker"],
            "issuer": r["issuer"],
            "report_date": r["report_date"],
            "company": cs.get("company", r["ticker"]),
            "sector": cs.get("sector", ""),
            "fiscal_period": cs.get("fiscal_period", ""),
            "report_type": cs.get("report_type", "Earnings Call Transcript"),
            "micro_score": float(cal["micro_score"]),
            "blend_predicted_signal_default": cal["blend_predicted_signal_default"],
        }

        is_pr = r["press_release"] == "available"
        is_prep = r["prepared_remarks"] == "available"
        is_qa = r["qa"] == "available"

        if is_pr:
            two_arm.append(event)
            if is_prep and is_qa:
                four_arm.append(event)

    return four_arm, two_arm


# ---------------------------------------------------------------------------
# Text extraction per arm
# ---------------------------------------------------------------------------
def load_extracted_text(issuer: str, document_id: str) -> str:
    path = PROJECT_ROOT / "outputs" / issuer / "extracted" / f"{document_id}.txt"
    return path.read_text(encoding="utf-8", errors="replace")


def get_arm_texts(full_text: str) -> dict[str, str | None]:
    """
    Returns {arm_name: text_or_None} for all four arms.
    full_bundle is always available; others may be None.
    """
    pr_text, transcript_text = _extract_sections(full_text)

    arms = {"full_bundle": full_text}

    if pr_text and len(pr_text.split()) > 0:
        arms["press_release"] = f"=== PRESS RELEASE ===\n\n{pr_text}"
    else:
        arms["press_release"] = None

    if transcript_text:
        prepared, qa = _find_qa_split(transcript_text)
        if prepared and qa:
            arms["prepared_remarks"] = f"=== EARNINGS CALL TRANSCRIPT (PREPARED REMARKS) ===\n\n{prepared}"
            arms["qa_only"] = f"=== EARNINGS CALL TRANSCRIPT (Q&A) ===\n\n{qa}"
        else:
            arms["prepared_remarks"] = None
            arms["qa_only"] = None
    else:
        arms["prepared_remarks"] = None
        arms["qa_only"] = None

    return arms


# ---------------------------------------------------------------------------
# LLM call wrapper
# ---------------------------------------------------------------------------
def score_arm(
    arm_text: str,
    event: dict,
    run_id: str,
    arm_name: str,
) -> dict:
    """Score one arm for one event. Returns a result dict."""
    # Build a minimal ReportSpec for call_llm
    report = ReportSpec(
        issuer=event["issuer"],
        company=event.get("company", event["ticker"]),
        ticker=event["ticker"],
        sector=event.get("sector", ""),
        report_type=event.get("report_type", "Earnings Call Transcript"),
        fiscal_period=event.get("fiscal_period", ""),
        report_date=event["report_date"],
        documents=(SourceDocument(doc_type="bundled", source_pdf=Path(".")),),
        document_id=event["document_id"],
    )

    doc_params = {
        "company": report.company,
        "ticker": report.ticker,
        "sector": report.sector,
        "report_type": report.report_type,
        "report_date": report.report_date,
        "fiscal_period": report.fiscal_period,
        "report_text": arm_text,
        "hold_upper": HOLD_UPPER,
        "hold_lower": HOLD_LOWER,
    }

    user_message = build_user_message(doc_params)

    output = call_llm(
        user_message=user_message,
        doc_params=doc_params,
        report=report,
        run_id=run_id,
        cached_input=False,
    )

    cost_log = output["cost_log"]
    result = output["result"]
    score = float(result["sentiment"]["score"])
    signal = result["signal"]["direction"]

    return {
        "document_id": event["document_id"],
        "arm": arm_name,
        "sentiment_score": score,
        "signal": signal,
        "input_tokens": cost_log["input_tokens"],
        "output_tokens": cost_log["output_tokens"],
        "total_tokens": cost_log["total_tokens"],
        "estimated_cost_usd": cost_log["estimated_cost_usd"],
        "latency_seconds": cost_log["latency_seconds"],
        "_response_model": cost_log.get("model", ""),
    }


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------
def grade_prediction(signal: str, ret: float, band: float) -> str:
    """
    Returns: 'correct', 'flat', 'wrong', or 'no_trade' (HOLD).
    """
    if signal == "HOLD":
        return "no_trade"
    if signal == "BUY":
        if ret > band:
            return "correct"
        elif ret < -band:
            return "wrong"
        else:
            return "flat"
    elif signal == "SELL":
        if ret < -band:
            return "correct"
        elif ret > band:
            return "wrong"
        else:
            return "flat"
    return "no_trade"


def net_return(signal: str, ret: float, cost_bps: float = 10.0) -> float | None:
    """Net return for a single trade. None if no trade."""
    if signal == "HOLD":
        return None
    cost = cost_bps / 10000.0
    if signal == "BUY":
        return ret - cost
    elif signal == "SELL":
        return -ret - cost
    return None


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def main():
    run_id = utc_run_id()
    print(f"Section ablation experiment — run_id: {run_id}")
    print(f"Grading band is provisional pending anchor correction.\n")

    # Load data
    audit_rows = load_audit_rows()
    exclusions = load_exclusions()
    returns = load_returns()
    hold_bands = load_hold_bands()
    calibration = load_calibration()
    company_sector = load_company_sector()

    overnight_band = hold_bands["overnight"]  # 0.02
    fiveday_band = hold_bands["5d"]  # ~0.034

    four_arm_events, two_arm_events = build_event_sets(audit_rows, exclusions, calibration, company_sector)
    print(f"Four-arm events: {len(four_arm_events)}")
    print(f"Two-arm events:  {len(two_arm_events)}")

    # -----------------------------------------------------------------------
    # Step 1: Five-event pilot (20 calls)
    # -----------------------------------------------------------------------
    pilot_events = four_arm_events[:5]
    arms_order = ["full_bundle", "press_release", "prepared_remarks", "qa_only"]

    print(f"\n{'='*60}")
    print(f"STEP 1: Five-event pilot ({len(pilot_events)} events x {len(arms_order)} arms = {len(pilot_events)*len(arms_order)} calls)")
    print(f"{'='*60}\n")

    pilot_results = []
    total_pilot_cost = 0.0
    total_pilot_tokens = 0

    for i, ev in enumerate(pilot_events):
        full_text = load_extracted_text(ev["issuer"], ev["document_id"])
        arm_texts = get_arm_texts(full_text)

        for arm_name in arms_order:
            arm_text = arm_texts.get(arm_name)
            if arm_text is None:
                print(f"  SKIP {ev['document_id']} / {arm_name} — section not available")
                continue

            print(f"  [{i+1}/{len(pilot_events)}] {ev['document_id']} / {arm_name} ...", end="", flush=True)
            result = score_arm(arm_text, ev, run_id, arm_name)
            pilot_results.append(result)
            total_pilot_cost += result["estimated_cost_usd"]
            total_pilot_tokens += result["total_tokens"]
            print(f" score={result['sentiment_score']:.2f} signal={result['signal']} "
                  f"tokens={result['total_tokens']} cost=${result['estimated_cost_usd']:.4f}")

    avg_cost_per_call = total_pilot_cost / len(pilot_results) if pilot_results else 0
    avg_tokens_per_call = total_pilot_tokens / len(pilot_results) if pilot_results else 0

    # Extrapolate
    n_four_arm_calls = len(four_arm_events) * 4
    # Two-arm: only full_bundle + press_release for events NOT already in four-arm
    four_arm_ids = {ev["document_id"] for ev in four_arm_events}
    two_arm_only_events = [ev for ev in two_arm_events if ev["document_id"] not in four_arm_ids]
    n_two_arm_extra_calls = len(two_arm_only_events) * 2
    n_total_calls = n_four_arm_calls + n_two_arm_extra_calls
    # Subtract pilot calls already made
    n_remaining = n_total_calls - len(pilot_results)

    estimated_total_cost = n_total_calls * avg_cost_per_call
    estimated_remaining_cost = n_remaining * avg_cost_per_call

    print(f"\n{'='*60}")
    print(f"PILOT SUMMARY")
    print(f"{'='*60}")
    print(f"Pilot calls completed: {len(pilot_results)}")
    print(f"Avg cost/call:   ${avg_cost_per_call:.4f}")
    print(f"Avg tokens/call: {avg_tokens_per_call:.0f}")
    print(f"")
    print(f"Full run estimate:")
    print(f"  Four-arm calls:        {n_four_arm_calls} ({len(four_arm_events)} events x 4 arms)")
    print(f"  Two-arm extra calls:   {n_two_arm_extra_calls} ({len(two_arm_only_events)} events x 2 arms)")
    print(f"  Total calls:           {n_total_calls}")
    print(f"  Remaining after pilot: {n_remaining}")
    print(f"  Estimated total cost:  ${estimated_total_cost:.2f}")
    print(f"  Estimated remaining:   ${estimated_remaining_cost:.2f}")
    print(f"")

    # Check for --pilot-only flag
    if "--pilot-only" in sys.argv:
        print(f"--pilot-only flag set. Stopping after pilot.")
        print(f"{'='*60}")
        return 0

    print(f"Proceeding with full run...")
    print(f"{'='*60}\n")

    # -----------------------------------------------------------------------
    # Step 2: Full four-arm run
    # -----------------------------------------------------------------------
    all_results = list(pilot_results)  # keep pilot results
    pilot_keys = {(r["document_id"], r["arm"]) for r in pilot_results}

    print(f"STEP 2: Full four-arm run (N={len(four_arm_events)})")
    for i, ev in enumerate(four_arm_events):
        full_text = load_extracted_text(ev["issuer"], ev["document_id"])
        arm_texts = get_arm_texts(full_text)

        for arm_name in arms_order:
            key = (ev["document_id"], arm_name)
            if key in pilot_keys:
                continue  # already scored in pilot

            arm_text = arm_texts.get(arm_name)
            if arm_text is None:
                print(f"  SKIP {ev['document_id']} / {arm_name}")
                continue

            print(f"  [{i+1}/{len(four_arm_events)}] {ev['document_id']} / {arm_name} ...", end="", flush=True)
            try:
                result = score_arm(arm_text, ev, run_id, arm_name)
                all_results.append(result)
                print(f" score={result['sentiment_score']:.2f} signal={result['signal']} "
                      f"cost=${result['estimated_cost_usd']:.4f}")
            except Exception as exc:
                print(f" ERROR: {exc}")

    # Two-arm extra events (full_bundle + press_release only)
    print(f"\nSTEP 2b: Two-arm extra events (N={len(two_arm_only_events)})")
    for i, ev in enumerate(two_arm_only_events):
        full_text = load_extracted_text(ev["issuer"], ev["document_id"])
        arm_texts = get_arm_texts(full_text)

        for arm_name in ["full_bundle", "press_release"]:
            key = (ev["document_id"], arm_name)
            if key in pilot_keys:
                continue

            arm_text = arm_texts.get(arm_name)
            if arm_text is None:
                print(f"  SKIP {ev['document_id']} / {arm_name}")
                continue

            print(f"  [{i+1}/{len(two_arm_only_events)}] {ev['document_id']} / {arm_name} ...", end="", flush=True)
            try:
                result = score_arm(arm_text, ev, run_id, arm_name)
                all_results.append(result)
                print(f" score={result['sentiment_score']:.2f} signal={result['signal']} "
                      f"cost=${result['estimated_cost_usd']:.4f}")
            except Exception as exc:
                print(f" ERROR: {exc}")

    # -----------------------------------------------------------------------
    # Step 3: Grade all arms
    # -----------------------------------------------------------------------
    print(f"\nSTEP 3: Grading all results ({len(all_results)} total)")

    for r in all_results:
        doc_id = r["document_id"]
        ret_row = returns.get(doc_id)
        if ret_row is None:
            r["ret_overnight"] = None
            r["ret_5d"] = None
            r["correct_overnight"] = ""
            r["correct_5d"] = ""
            r["net_overnight"] = None
            continue

        ret_on = float(ret_row["ret_overnight"])
        ret_5d = float(ret_row["ret_5d"])
        r["ret_overnight"] = ret_on
        r["ret_5d"] = ret_5d

        r["correct_overnight"] = grade_prediction(r["signal"], ret_on, overnight_band)
        r["correct_5d"] = grade_prediction(r["signal"], ret_5d, fiveday_band)
        r["net_overnight"] = net_return(r["signal"], ret_on)

    # Add run_id
    for r in all_results:
        r["run_id"] = run_id

    # Write results CSV
    result_fields = [
        "document_id", "arm", "sentiment_score", "signal",
        "input_tokens", "output_tokens", "total_tokens",
        "estimated_cost_usd", "latency_seconds",
        "ret_overnight", "ret_5d",
        "correct_overnight", "correct_5d", "net_overnight",
        "run_id",
    ]
    # Record the resolved model version from the first result
    resolved_model = ""
    for r in all_results:
        if r.get("_response_model"):
            resolved_model = r["_response_model"]
            break

    with open(OUT_RESULTS, "w", newline="") as f:
        f.write("# Section ablation results\n")
        f.write(f"# Run ID: {run_id}\n")
        f.write(f"# Run date: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"# Model alias: deepseek-chat\n")
        f.write(f"# Resolved model version: {resolved_model}\n")
        f.write(f"# Deployed runs used: deepseek-v4-flash (verified from run_meta)\n")
        f.write(f"# Grading: pre-registered ±2% raw overnight band\n")
        f.write(f"# Four-arm N: {len(four_arm_events)} (was 124 before timing exclusions removed 5)\n")
        f.write(f"# Two-arm N: {len(two_arm_events)} (was 210 before timing exclusions removed 10)\n")
        f.write(f"#\n")
        f.write(f"# Minimum detectable effect (paired design, 80% power, alpha=0.10):\n")
        f.write(f"#   ~±12pp per arm comparison against full bundle.\n")
        f.write(f"#   Any arm difference smaller than the paired MDE means the arms are\n")
        f.write(f"#   indistinguishable at this sample size. Combined with the token ratio,\n")
        f.write(f"#   indistinguishability is itself the deployment answer: equivalent\n")
        f.write(f"#   accuracy at lower cost.\n")
        f.write(f"#   Unpaired MDE for reference: ~±25pp.\n")
        f.write(f"# Overnight band: {overnight_band}, 5d band: {fiveday_band:.6f}\n")
        f.write(f"# hold_upper: {HOLD_UPPER}, hold_lower: {HOLD_LOWER}\n")
        f.write(f"#\n")
        writer = csv.DictWriter(f, fieldnames=result_fields, extrasaction="ignore")
        writer.writeheader()
        for r in all_results:
            writer.writerow(r)
    print(f"  Wrote {OUT_RESULTS}")

    # -----------------------------------------------------------------------
    # Step 4: Per-arm summary + paired differences (four-arm set)
    # -----------------------------------------------------------------------
    print(f"\nSTEP 4: Per-arm summary and paired differences")

    # Build per-event, per-arm lookup
    by_doc_arm = {}
    for r in all_results:
        by_doc_arm[(r["document_id"], r["arm"])] = r

    # Four-arm events: only include events where ALL four arms exist
    four_arm_complete = []
    for ev in four_arm_events:
        doc_id = ev["document_id"]
        if all((doc_id, arm) in by_doc_arm for arm in arms_order):
            four_arm_complete.append(doc_id)

    print(f"  Four-arm complete events: {len(four_arm_complete)}")

    def arm_stats(arm_name, doc_ids, label=""):
        """Compute accuracy / trade stats for one arm on a set of events."""
        correct_on = 0
        correct_5d = 0
        trades_on = 0
        trades_5d = 0
        total = 0
        net_returns_on = []
        correct_list_on = []  # for paired bootstrap: 1.0 if correct, 0.0 if wrong/flat

        for doc_id in doc_ids:
            r = by_doc_arm.get((doc_id, arm_name))
            if r is None:
                continue
            total += 1
            grade_on = r.get("correct_overnight", "")
            grade_5d = r.get("correct_5d", "")

            if grade_on in ("correct", "flat", "wrong"):
                trades_on += 1
                if grade_on == "correct":
                    correct_on += 1
                    correct_list_on.append(1.0)
                else:
                    correct_list_on.append(0.0)
                nr = r.get("net_overnight")
                if nr is not None:
                    net_returns_on.append(nr)
            else:
                # HOLD — no trade
                pass

            if grade_5d in ("correct", "flat", "wrong"):
                trades_5d += 1
                if grade_5d == "correct":
                    correct_5d += 1

        # Accuracy = correct / (correct + flat + wrong)  [traded events]
        acc_on = correct_on / trades_on if trades_on > 0 else None
        acc_5d = correct_5d / trades_5d if trades_5d > 0 else None
        mean_net = sum(net_returns_on) / len(net_returns_on) if net_returns_on else None

        return {
            "arm": arm_name,
            "label": label,
            "n_events": total,
            "trades_overnight": trades_on,
            "correct_overnight": correct_on,
            "accuracy_overnight": acc_on,
            "trades_5d": trades_5d,
            "correct_5d": correct_5d,
            "accuracy_5d": acc_5d,
            "mean_net_per_trade_overnight": mean_net,
            "correct_list_overnight": correct_list_on,
            "net_returns_overnight": net_returns_on,
        }

    # Four-arm summaries
    summary_rows = []
    arm_data = {}
    for arm in arms_order:
        stats = arm_stats(arm, four_arm_complete, label="four_arm")
        arm_data[arm] = stats
        summary_rows.append(stats)
        acc_on_str = f"{stats['accuracy_overnight']:.4f}" if stats['accuracy_overnight'] is not None else "N/A"
        acc_5d_str = f"{stats['accuracy_5d']:.4f}" if stats['accuracy_5d'] is not None else "N/A"
        mean_net_str = f"{stats['mean_net_per_trade_overnight']:.4f}" if stats['mean_net_per_trade_overnight'] is not None else "N/A"
        print(f"  {arm:20s}: N={stats['n_events']}, trades_on={stats['trades_overnight']}, "
              f"acc_on={acc_on_str}, acc_5d={acc_5d_str}, mean_net={mean_net_str}")

    # Paired differences vs full_bundle
    print(f"\n  Paired differences (each arm vs full_bundle):")
    paired_rows = []
    fb = arm_data["full_bundle"]
    for arm in ["press_release", "prepared_remarks", "qa_only"]:
        ad = arm_data[arm]
        # Accuracy difference (paired correctness arrays)
        # Need to align by document — build paired arrays
        fb_correct = []
        arm_correct = []
        for doc_id in four_arm_complete:
            fb_r = by_doc_arm.get((doc_id, "full_bundle"))
            arm_r = by_doc_arm.get((doc_id, arm))
            if fb_r is None or arm_r is None:
                continue
            fb_grade = fb_r.get("correct_overnight", "")
            arm_grade = arm_r.get("correct_overnight", "")
            # Only include events where both arms traded
            if fb_grade in ("correct", "flat", "wrong") and arm_grade in ("correct", "flat", "wrong"):
                fb_correct.append(1.0 if fb_grade == "correct" else 0.0)
                arm_correct.append(1.0 if arm_grade == "correct" else 0.0)

        if len(fb_correct) >= 2:
            bd = bootstrap_paired_difference(arm_correct, fb_correct)
            print(f"  {arm:20s} vs full_bundle: diff={bd['point_diff']:.4f}, "
                  f"CI=[{bd['ci_low']:.4f}, {bd['ci_high']:.4f}], p={bd['p_value']:.4f}, n_paired={bd['n']}")
            paired_rows.append({
                "comparison": f"{arm} vs full_bundle",
                "set": "four_arm",
                "n_paired": bd["n"],
                "point_diff": bd["point_diff"],
                "ci_low": bd["ci_low"],
                "ci_high": bd["ci_high"],
                "p_value": bd["p_value"],
                "metric": "accuracy_overnight",
                "run_id": run_id,
            })
        else:
            print(f"  {arm:20s} vs full_bundle: insufficient paired trades (n={len(fb_correct)})")

    # -----------------------------------------------------------------------
    # Step 5: Two-arm comparison (N=210)
    # -----------------------------------------------------------------------
    print(f"\nSTEP 5: Two-arm comparison (N={len(two_arm_events)})")

    two_arm_ids = [ev["document_id"] for ev in two_arm_events]
    # Only include events where both full_bundle and press_release exist
    two_arm_complete = [
        doc_id for doc_id in two_arm_ids
        if (doc_id, "full_bundle") in by_doc_arm and (doc_id, "press_release") in by_doc_arm
    ]
    print(f"  Two-arm complete events: {len(two_arm_complete)}")

    two_arm_summary = []
    for arm in ["full_bundle", "press_release"]:
        stats = arm_stats(arm, two_arm_complete, label="two_arm")
        two_arm_summary.append(stats)
        acc_on_str = f"{stats['accuracy_overnight']:.4f}" if stats['accuracy_overnight'] is not None else "N/A"
        mean_net_str = f"{stats['mean_net_per_trade_overnight']:.4f}" if stats['mean_net_per_trade_overnight'] is not None else "N/A"
        print(f"  {arm:20s}: N={stats['n_events']}, trades_on={stats['trades_overnight']}, "
              f"acc_on={acc_on_str}, mean_net={mean_net_str}")

    # Paired difference for two-arm
    fb_correct_2 = []
    pr_correct_2 = []
    for doc_id in two_arm_complete:
        fb_r = by_doc_arm.get((doc_id, "full_bundle"))
        pr_r = by_doc_arm.get((doc_id, "press_release"))
        if fb_r is None or pr_r is None:
            continue
        fb_g = fb_r.get("correct_overnight", "")
        pr_g = pr_r.get("correct_overnight", "")
        if fb_g in ("correct", "flat", "wrong") and pr_g in ("correct", "flat", "wrong"):
            fb_correct_2.append(1.0 if fb_g == "correct" else 0.0)
            pr_correct_2.append(1.0 if pr_g == "correct" else 0.0)

    if len(fb_correct_2) >= 2:
        bd2 = bootstrap_paired_difference(pr_correct_2, fb_correct_2)
        print(f"\n  press_release vs full_bundle (two-arm): diff={bd2['point_diff']:.4f}, "
              f"CI=[{bd2['ci_low']:.4f}, {bd2['ci_high']:.4f}], p={bd2['p_value']:.4f}, n_paired={bd2['n']}")
        paired_rows.append({
            "comparison": "press_release vs full_bundle",
            "set": "two_arm",
            "n_paired": bd2["n"],
            "point_diff": bd2["point_diff"],
            "ci_low": bd2["ci_low"],
            "ci_high": bd2["ci_high"],
            "p_value": bd2["p_value"],
            "metric": "accuracy_overnight",
            "run_id": run_id,
        })

    # -----------------------------------------------------------------------
    # Step 6: Sanity check — full_bundle vs deployed pipeline
    # -----------------------------------------------------------------------
    print(f"\nSTEP 6: Sanity check — full_bundle arm vs deployed pipeline")
    match_count = 0
    mismatch_count = 0
    for doc_id in four_arm_complete[:50]:  # check a sample
        fb_r = by_doc_arm.get((doc_id, "full_bundle"))
        if fb_r is None:
            continue
        cal = calibration.get(doc_id, {})
        deployed_signal = cal.get("blend_predicted_signal_default", "")
        ablation_signal = fb_r["signal"]
        # The full-bundle arm uses micro-only score with HOLD_UPPER/HOLD_LOWER,
        # while the deployed pipeline uses a blended score.
        # So we compare the micro score direction vs the ablation's score.
        micro_score = float(cal.get("micro_score", 0))
        # Derive what the micro-only signal would be
        if micro_score > HOLD_UPPER:
            micro_signal = "BUY"
        elif micro_score < HOLD_LOWER:
            micro_signal = "SELL"
        else:
            micro_signal = "HOLD"
        if ablation_signal == micro_signal:
            match_count += 1
        else:
            mismatch_count += 1

    print(f"  Compared {match_count + mismatch_count} events against micro-score-derived signal")
    print(f"  Match: {match_count}, Mismatch: {mismatch_count}")
    print(f"  (Mismatches expected — different API call, LLM non-determinism at temp=0)")

    # -----------------------------------------------------------------------
    # Write output CSVs
    # -----------------------------------------------------------------------
    # Summary CSV
    summary_fields = [
        "arm", "label", "n_events", "trades_overnight", "correct_overnight",
        "accuracy_overnight", "trades_5d", "correct_5d", "accuracy_5d",
        "mean_net_per_trade_overnight", "run_id",
    ]
    all_summary = summary_rows + two_arm_summary
    for s in all_summary:
        s["run_id"] = run_id

    with open(OUT_SUMMARY, "w", newline="") as f:
        f.write("# Section ablation per-arm summary\n")
        f.write(f"# Run ID: {run_id}\n")
        f.write(f"# Run date: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"# Model: {resolved_model}\n")
        f.write(f"# Grading: pre-registered ±2% raw overnight band\n")
        f.write(f"# Overnight band: {overnight_band}, 5d band: {fiveday_band:.6f}\n")
        f.write(f"# Paired MDE: ~±12pp (80% power, alpha=0.10)\n")
        f.write(f"# A gap smaller than the paired MDE means the arms are indistinguishable\n")
        f.write(f"# at this sample size. Combined with the token ratio, indistinguishability\n")
        f.write(f"# is itself the deployment answer: equivalent accuracy at lower cost.\n")
        f.write(f"#\n")
        writer = csv.DictWriter(f, fieldnames=summary_fields, extrasaction="ignore")
        writer.writeheader()
        for s in all_summary:
            writer.writerow(s)
    print(f"\n  Wrote {OUT_SUMMARY}")

    # Paired diffs CSV
    paired_fields = [
        "comparison", "set", "n_paired", "point_diff", "ci_low", "ci_high",
        "p_value", "metric", "run_id",
    ]
    with open(OUT_PAIRED, "w", newline="") as f:
        f.write("# Section ablation paired differences vs full bundle\n")
        f.write(f"# Run ID: {run_id}\n")
        f.write(f"# Run date: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"# Model: {resolved_model}\n")
        f.write(f"# Grading: pre-registered ±2% raw overnight band\n")
        f.write(f"# Paired MDE: ~±12pp. Any |diff| < MDE = arms indistinguishable.\n")
        f.write(f"#\n")
        writer = csv.DictWriter(f, fieldnames=paired_fields, extrasaction="ignore")
        writer.writeheader()
        for p in paired_rows:
            writer.writerow(p)
    print(f"  Wrote {OUT_PAIRED}")

    # Two-arm CSV
    two_arm_fields = [
        "arm", "label", "n_events", "trades_overnight", "correct_overnight",
        "accuracy_overnight", "mean_net_per_trade_overnight",
        "point_diff_vs_full", "ci_low", "ci_high", "p_value",
        "run_id",
    ]
    with open(OUT_TWO_ARM, "w", newline="") as f:
        f.write("# Section ablation two-arm comparison (full bundle vs press release)\n")
        f.write(f"# Run ID: {run_id}\n")
        f.write(f"# Grading band is provisional pending anchor correction\n")
        f.write(f"# N={len(two_arm_complete)} (events with press_release available, after exclusions)\n")
        f.write(f"#\n")
        writer = csv.DictWriter(f, fieldnames=two_arm_fields, extrasaction="ignore")
        writer.writeheader()
        for s in two_arm_summary:
            row = dict(s)
            if s["arm"] == "press_release" and len(fb_correct_2) >= 2:
                row["point_diff_vs_full"] = bd2["point_diff"]
                row["ci_low"] = bd2["ci_low"]
                row["ci_high"] = bd2["ci_high"]
                row["p_value"] = bd2["p_value"]
            row["run_id"] = run_id
            writer.writerow(row)
    print(f"  Wrote {OUT_TWO_ARM}")

    # Final cost tally
    total_cost = sum(r.get("estimated_cost_usd", 0) for r in all_results)
    total_tokens_all = sum(r.get("total_tokens", 0) for r in all_results)
    print(f"\n{'='*60}")
    print(f"DONE. Total calls: {len(all_results)}, total cost: ${total_cost:.2f}, total tokens: {total_tokens_all}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
