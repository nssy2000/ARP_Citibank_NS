"""
experiments/section_ablation_extension.py
Item C: Four-arm section ablation on the 93-event extension corpus.

Arms:
  1. full_bundle        — complete extracted text (same as production run)
  2. press_release      — === PRESS RELEASE === section only
  3. prepared_remarks   — transcript up to Q&A transition marker
  4. qa_only            — transcript from Q&A transition marker to end

Four-arm events (PR + prepared remarks + Q&A): those extension events
that have a transcript with a successful Q&A split.
Two-arm events (PR + full bundle): all extension events with a transcript.

The 14 PR-only events (Colgate-Palmolive×4, Heineken×4, eBay×4,
Datadog FQ2_2025×1, Intel FQ1_2026×1) are excluded — no transcript to ablate.
Shell's 4 events (Earnings Presentation, no Q&A) contribute to two-arm only.

Overnight returns sourced from backtest_equity_extension_2026_08_13.csv.
Grading band: pre-registered ±2% raw overnight.

Pass --pilot-only to run only the first 5 four-arm-capable events (20 calls).

Outputs:
  outputs/global/summary/section_ablation_extension_results.csv
  outputs/global/summary/section_ablation_extension_summary.csv
  outputs/global/summary/section_ablation_extension_paired.csv
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from report_pipeline import (
    ReportSpec,
    SourceDocument,
    build_user_message,
    call_llm,
    utc_run_id,
)
from bootstrap_stats import bootstrap_paired_difference

SUMMARY_DIR = PROJECT_ROOT / "outputs" / "global" / "summary"
EXT_CALIBRATION_CSV = SUMMARY_DIR / "global_outcome_calibration_extension_2026_08_13.csv"
# One source of truth for which extension-gap vintage is current; four files
# used to carry their own copy of this name. See eval/extension_gaps.py.
from eval.extension_gaps import CURRENT_GAP_FILE as EXT_BACKTEST_CSV  # noqa: E402

OUT_RESULTS = SUMMARY_DIR / "section_ablation_extension_results.csv"
OUT_SUMMARY = SUMMARY_DIR / "section_ablation_extension_summary.csv"
OUT_PAIRED = SUMMARY_DIR / "section_ablation_extension_paired.csv"

HOLD_UPPER = 0.25
HOLD_LOWER = -0.05
OVERNIGHT_BAND = 0.02
COST_BPS = 10.0
COST_FRAC = COST_BPS / 10_000

# ── section splitting (same patterns as section_ablation.py) ─────────────────
PRESS_RELEASE_HEADER = re.compile(r"===\s*PRESS RELEASE\s*===")
TRANSCRIPT_HEADER = re.compile(r"===\s*EARNINGS CALL TRANSCRIPT\s*===")
PRESENTATION_HEADER = re.compile(r"===\s*EARNINGS PRESENTATION\s*===")
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
    """Returns (press_release_text, transcript_text, prepared_remarks_text)."""
    headers = []
    for m in SECTION_HEADER.finditer(full_text):
        headers.append((m.start(), m.end(), m.group().strip()))

    pr_text = transcript_text = presentation_text = None
    for i, (start, end, header) in enumerate(headers):
        section_end = headers[i + 1][0] if i + 1 < len(headers) else len(full_text)
        content = full_text[end:section_end].strip()
        if PRESS_RELEASE_HEADER.search(header):
            pr_text = content
        if TRANSCRIPT_HEADER.search(header):
            transcript_text = content
        if PRESENTATION_HEADER.search(header):
            presentation_text = content
    return pr_text, transcript_text, presentation_text


def _find_qa_split(transcript_text: str):
    """Returns (prepared_text, qa_text) or (None, None)."""
    m = FACTSET_HEADER.search(transcript_text)
    if m:
        return transcript_text[:m.start()].strip(), transcript_text[m.start():].strip()

    best_match = None
    best_pos = len(transcript_text)
    for pat in COMPILED_TRANSITION:
        m2 = pat.search(transcript_text)
        if m2 and m2.start() < best_pos:
            best_pos = m2.start()
            best_match = m2

    if best_match is not None:
        line_start = transcript_text.rfind("\n", 0, best_match.start())
        split_pos = (line_start + 1) if (line_start >= 0 and best_match.start() - line_start < 500) else best_match.start()
        return transcript_text[:split_pos].strip(), transcript_text[split_pos:].strip()
    return None, None


def _get_arm_texts(full_text: str) -> dict[str, str | None]:
    pr_text, transcript_text, presentation_text = _extract_sections(full_text)
    arms: dict[str, str | None] = {"full_bundle": full_text}

    if pr_text and len(pr_text.split()) > 10:
        arms["press_release"] = f"=== PRESS RELEASE ===\n\n{pr_text}"
    else:
        arms["press_release"] = None

    if transcript_text:
        prepared, qa = _find_qa_split(transcript_text)
        prepared_words = len(prepared.split()) if prepared else 0
        transcript_words = len(transcript_text.split())
        # 10% prepared fraction + 100 word absolute floor (same as section_ablation.py)
        if prepared and qa and prepared_words >= 100 and prepared_words >= 0.10 * transcript_words:
            arms["prepared_remarks"] = f"=== EARNINGS CALL TRANSCRIPT (PREPARED REMARKS) ===\n\n{prepared}"
            arms["qa_only"] = f"=== EARNINGS CALL TRANSCRIPT (Q&A) ===\n\n{qa}"
        else:
            arms["prepared_remarks"] = None
            arms["qa_only"] = None
    elif presentation_text:
        # Shell-type: has prepared remarks (EARNINGS PRESENTATION) but no Q&A
        arms["prepared_remarks"] = f"=== EARNINGS PRESENTATION ===\n\n{presentation_text}"
        arms["qa_only"] = None
    else:
        arms["prepared_remarks"] = None
        arms["qa_only"] = None

    return arms


# ── data loading ─────────────────────────────────────────────────────────────

def _load_overnight_returns() -> dict[str, float]:
    """Overnight gaps from the extension backtest CSV, keyed on document_id.

    NOT on (ticker, report_date). The calibration roster is a frozen 2026-08-13
    artefact whose report_date column still carries the first-of-month
    placeholders, so a date-keyed join silently drops every event whose anchor has
    since been corrected - four Hermes events on 2026-08-24.
    """
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
    return gaps


def _load_events(overnight_gaps) -> list[dict]:
    events = []
    with open(EXT_CALIBRATION_CSV) as f:
        for r in csv.DictReader(f):
            key = r["document_id"]
            if key not in overnight_gaps:
                continue
            events.append({
                "document_id": r["document_id"],
                "ticker": r["ticker"],
                "issuer": r["issuer"],
                "report_date": r["report_date"],
                "ret_overnight": overnight_gaps[key],
                "blend_predicted_signal_default": r.get("blend_predicted_signal_default", ""),
                "micro_score": r.get("micro_score", ""),
            })
    return events


# ── scoring ───────────────────────────────────────────────────────────────────

def _score_arm(arm_text: str, event: dict, run_id: str, arm_name: str) -> dict:
    report = ReportSpec(
        issuer=event["issuer"],
        company=event["ticker"],
        ticker=event["ticker"],
        sector="",
        report_type="Earnings Call Transcript",
        fiscal_period="",
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
    output = call_llm(user_message=user_message, doc_params=doc_params,
                      report=report, run_id=run_id, cached_input=False)
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
    }


def _grade(signal: str, ret: float) -> str:
    if signal == "HOLD":
        return "no_trade"
    if signal == "BUY":
        return "correct" if ret > OVERNIGHT_BAND else ("wrong" if ret < -OVERNIGHT_BAND else "flat")
    else:  # SELL
        return "correct" if ret < -OVERNIGHT_BAND else ("wrong" if ret > OVERNIGHT_BAND else "flat")


def _net(signal: str, ret: float) -> float | None:
    if signal == "HOLD":
        return None
    return (ret if signal == "BUY" else -ret) - COST_FRAC


# ── analysis ─────────────────────────────────────────────────────────────────

def _arm_stats(arm_name: str, doc_ids: list[str], by_doc_arm: dict) -> dict:
    correct = trades = 0
    nets = []
    for did in doc_ids:
        r = by_doc_arm.get((did, arm_name))
        if r is None:
            continue
        grade = r.get("grade", "")
        if grade in ("correct", "flat", "wrong"):
            trades += 1
            if grade == "correct":
                correct += 1
            nr = r.get("net_overnight")
            if nr is not None:
                nets.append(nr)
    acc = correct / trades if trades else None
    mean_net = sum(nets) / len(nets) if nets else None
    return {
        "arm": arm_name,
        "n_events": len(doc_ids),
        "trades": trades,
        "correct": correct,
        "accuracy": acc,
        "mean_net": mean_net,
    }


def main() -> None:
    pilot_only = "--pilot-only" in sys.argv
    from_results = "--from-results" in sys.argv
    run_id = utc_run_id()
    print(f"Section ablation extension — run_id: {run_id}")
    print(f"Pilot-only mode: {pilot_only}\n")

    overnight_gaps = _load_overnight_returns()
    events = _load_events(overnight_gaps)
    print(f"Extension events loaded: {len(events)}")

    # Classify events by section availability
    four_arm_events = []
    two_arm_events = []   # transcript available (PR + full bundle)
    pr_only_events = []   # no transcript

    for ev in events:
        text_path = PROJECT_ROOT / "outputs" / ev["issuer"] / "extracted" / f"{ev['document_id']}.txt"
        if not text_path.exists():
            continue
        full_text = text_path.read_text(encoding="utf-8", errors="replace")
        arm_texts = _get_arm_texts(full_text)
        ev["_full_text"] = full_text
        ev["_arm_texts"] = arm_texts

        has_pr = arm_texts.get("press_release") is not None
        has_prep = arm_texts.get("prepared_remarks") is not None
        has_qa = arm_texts.get("qa_only") is not None

        if not has_pr:
            pr_only_events.append(ev)
        elif has_prep and has_qa:
            two_arm_events.append(ev)
            four_arm_events.append(ev)
        else:
            two_arm_events.append(ev)

    print(f"Four-arm events (PR + prepared + Q&A): {len(four_arm_events)}")
    print(f"Two-arm events (PR + full bundle):      {len(two_arm_events)}")
    print(f"No press release found:                 {len(pr_only_events)}")
    print()

    arms_order = ["full_bundle", "press_release", "prepared_remarks", "qa_only"]
    four_arm_ids = {ev["document_id"] for ev in four_arm_events}
    two_only_events = [ev for ev in two_arm_events if ev["document_id"] not in four_arm_ids]

    if from_results:
        print(f"--from-results: loading scored results from {OUT_RESULTS}")
        all_results = []
        with open(OUT_RESULTS, encoding="utf-8") as fh:
            for row in csv.DictReader(r for r in fh if not r.startswith("#") and r.strip()):
                row["sentiment_score"] = float(row["sentiment_score"])
                row["ret_overnight"] = float(row["ret_overnight"]) if row.get("ret_overnight") else None
                row["net_overnight"] = float(row["net_overnight"]) if row.get("net_overnight") else None
                row["estimated_cost_usd"] = float(row["estimated_cost_usd"])
                all_results.append(row)
        print(f"  Loaded {len(all_results)} result rows")
    else:
        # Pilot: first 5 four-arm events (20 calls)
        pilot_n = min(5, len(four_arm_events))
        pilot_events = four_arm_events[:pilot_n]

        print(f"{'='*60}")
        print(f"PILOT: {pilot_n} events × 4 arms = {pilot_n*4} calls")
        print(f"{'='*60}")

        pilot_results = []
        total_cost = 0.0
        total_tokens = 0

        for i, ev in enumerate(pilot_events):
            arm_texts = ev["_arm_texts"]
            for arm_name in arms_order:
                arm_text = arm_texts.get(arm_name)
                if arm_text is None:
                    continue
                print(f"  [{i+1}/{pilot_n}] {ev['document_id']} / {arm_name} ...", end="", flush=True)
                result = _score_arm(arm_text, ev, run_id, arm_name)
                pilot_results.append(result)
                total_cost += result["estimated_cost_usd"]
                total_tokens += result["total_tokens"]
                print(f" score={result['sentiment_score']:.2f} signal={result['signal']} "
                      f"tokens={result['total_tokens']} cost=${result['estimated_cost_usd']:.4f}")

        avg_cost = total_cost / len(pilot_results) if pilot_results else 0
        avg_tokens = total_tokens / len(pilot_results) if pilot_results else 0

        n_four_calls = len(four_arm_events) * 4
        n_two_extra = len(two_only_events) * 2
        n_total = n_four_calls + n_two_extra
        n_remaining = n_total - len(pilot_results)

        print(f"\n{'='*60}")
        print(f"PILOT SUMMARY")
        print(f"  Calls completed:     {len(pilot_results)}")
        print(f"  Avg cost/call:       ${avg_cost:.4f}")
        print(f"  Avg tokens/call:     {avg_tokens:.0f}")
        print(f"  Four-arm total:      {n_four_calls} ({len(four_arm_events)} events × 4)")
        print(f"  Two-arm extra:       {n_two_extra} ({len(two_only_events)} events × 2)")
        print(f"  Total calls (full):  {n_total}")
        print(f"  Remaining:           {n_remaining}")
        print(f"  Est. remaining cost: ${n_remaining * avg_cost:.2f}")
        print(f"  Est. total cost:     ${n_total * avg_cost:.2f}")
        print(f"{'='*60}")

        if pilot_only:
            print("--pilot-only: stopping after pilot.")
            return 0

        print(f"\nProceeding with full run...")

        # Full four-arm run
        all_results = list(pilot_results)
        pilot_keys = {(r["document_id"], r["arm"]) for r in pilot_results}

        print(f"\nFour-arm run (N={len(four_arm_events)})")
        for i, ev in enumerate(four_arm_events):
            arm_texts = ev["_arm_texts"]
            for arm_name in arms_order:
                if (ev["document_id"], arm_name) in pilot_keys:
                    continue
                arm_text = arm_texts.get(arm_name)
                if arm_text is None:
                    continue
                print(f"  [{i+1}/{len(four_arm_events)}] {ev['document_id']} / {arm_name} ...", end="", flush=True)
                try:
                    result = _score_arm(arm_text, ev, run_id, arm_name)
                    all_results.append(result)
                    print(f" score={result['sentiment_score']:.2f} signal={result['signal']} "
                          f"cost=${result['estimated_cost_usd']:.4f}")
                except Exception as exc:
                    print(f" ERROR: {exc}")

        print(f"\nTwo-arm extra events (N={len(two_only_events)})")
        for i, ev in enumerate(two_only_events):
            arm_texts = ev["_arm_texts"]
            for arm_name in ["full_bundle", "press_release"]:
                if (ev["document_id"], arm_name) in pilot_keys:
                    continue
                arm_text = arm_texts.get(arm_name)
                if arm_text is None:
                    continue
                print(f"  [{i+1}/{len(two_only_events)}] {ev['document_id']} / {arm_name} ...", end="", flush=True)
                try:
                    result = _score_arm(arm_text, ev, run_id, arm_name)
                    all_results.append(result)
                    print(f" score={result['sentiment_score']:.2f} signal={result['signal']} "
                          f"cost=${result['estimated_cost_usd']:.4f}")
                except Exception as exc:
                    print(f" ERROR: {exc}")

        # Grade
        event_ret = {ev["document_id"]: ev["ret_overnight"] for ev in events}
        for r in all_results:
            ret = event_ret.get(r["document_id"])
            r["ret_overnight"] = ret
            if ret is not None:
                r["grade"] = _grade(r["signal"], ret)
                r["net_overnight"] = _net(r["signal"], ret)
            else:
                r["grade"] = ""
                r["net_overnight"] = None
            r["run_id"] = run_id

    # Write results
    if not from_results:
        result_fields = [
            "document_id", "arm", "sentiment_score", "signal",
            "input_tokens", "output_tokens", "total_tokens", "estimated_cost_usd",
            "latency_seconds", "ret_overnight", "grade", "net_overnight", "run_id",
        ]
        with open(OUT_RESULTS, "w", newline="") as f:
            f.write(f"# Section ablation extension results\n")
            f.write(f"# Run ID: {run_id}\n")
            f.write(f"# Four-arm N: {len(four_arm_events)}, Two-arm N: {len(two_arm_events)}\n")
            f.write(f"# Grading: +-2% raw overnight band (pre-registered)\n")
            f.write(f"# hold_upper: {HOLD_UPPER}, hold_lower: {HOLD_LOWER}\n\n")
            w = csv.DictWriter(f, fieldnames=result_fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(all_results)
        print(f"\nWrote {OUT_RESULTS}")

    # Per-arm summary
    by_doc_arm = {(r["document_id"], r["arm"]): r for r in all_results}
    four_arm_complete = [
        ev["document_id"] for ev in four_arm_events
        if all((ev["document_id"], arm) in by_doc_arm for arm in arms_order)
    ]
    print(f"\nFour-arm complete events: {len(four_arm_complete)}")

    summary_rows = []
    for arm_name in arms_order:
        stats = _arm_stats(arm_name, four_arm_complete, by_doc_arm)
        stats["set"] = "four_arm"
        stats["run_id"] = run_id
        summary_rows.append(stats)
        acc_s = f"{stats['accuracy']:.4f}" if stats["accuracy"] is not None else "N/A"
        net_s = f"{stats['mean_net']:.4f}" if stats["mean_net"] is not None else "N/A"
        print(f"  {arm_name:22s}: trades={stats['trades']}, acc={acc_s}, mean_net={net_s}")

    # Two-arm comparison
    two_arm_doc_ids = [ev["document_id"] for ev in two_arm_events]
    two_arm_complete = [
        did for did in two_arm_doc_ids
        if (did, "full_bundle") in by_doc_arm and (did, "press_release") in by_doc_arm
    ]
    for arm_name in ["full_bundle", "press_release"]:
        stats = _arm_stats(arm_name, two_arm_complete, by_doc_arm)
        stats["set"] = "two_arm"
        stats["run_id"] = run_id
        summary_rows.append(stats)

    # Paired differences vs full_bundle
    paired_rows = []
    fb_stats = {s["arm"]: s for s in summary_rows if s["set"] == "four_arm"}
    for arm_name in ["press_release", "prepared_remarks", "qa_only"]:
        fb_correct = []
        arm_correct = []
        for did in four_arm_complete:
            fb_r = by_doc_arm.get((did, "full_bundle"))
            arm_r = by_doc_arm.get((did, arm_name))
            if fb_r is None or arm_r is None:
                continue
            fg = fb_r.get("grade", "")
            ag = arm_r.get("grade", "")
            if fg in ("correct", "flat", "wrong") and ag in ("correct", "flat", "wrong"):
                fb_correct.append(1.0 if fg == "correct" else 0.0)
                arm_correct.append(1.0 if ag == "correct" else 0.0)
        if len(fb_correct) >= 2:
            bd = bootstrap_paired_difference(arm_correct, fb_correct)
            paired_rows.append({
                "comparison": f"{arm_name} vs full_bundle",
                "set": "four_arm",
                "n_paired": bd["n"],
                "point_diff": bd["point_diff"],
                "ci_low": bd["ci_low"],
                "ci_high": bd["ci_high"],
                "p_value": bd["p_value"],
                "run_id": run_id,
            })
            print(f"  {arm_name:22s} vs full: diff={bd['point_diff']:+.4f}, "
                  f"CI=[{bd['ci_low']:+.4f},{bd['ci_high']:+.4f}], p={bd['p_value']:.4f}")

    # Write summaries
    summary_fields = ["arm", "set", "n_events", "trades", "correct", "accuracy", "mean_net", "run_id"]
    with open(OUT_SUMMARY, "w", newline="") as f:
        f.write(f"# Section ablation extension per-arm summary\n")
        f.write(f"# Run ID: {run_id}\n")
        f.write(f"# Grading: +-2% raw overnight band\n\n")
        w = csv.DictWriter(f, fieldnames=summary_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(summary_rows)
    print(f"Wrote {OUT_SUMMARY}")

    paired_fields = ["comparison", "set", "n_paired", "point_diff", "ci_low", "ci_high", "p_value", "run_id"]
    with open(OUT_PAIRED, "w", newline="") as f:
        f.write(f"# Section ablation extension paired diffs vs full_bundle\n")
        f.write(f"# Run ID: {run_id}\n\n")
        w = csv.DictWriter(f, fieldnames=paired_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(paired_rows)
    print(f"Wrote {OUT_PAIRED}")

    total = sum(r.get("estimated_cost_usd", 0) for r in all_results)
    print(f"\nDone. {len(all_results)} calls, total cost ${total:.2f}")


if __name__ == "__main__":
    main()
