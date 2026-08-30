"""
Section boundary audit with amended definitions (Task 3).

Exclusion rule (fixed before timing classification was visible):
  Events whose release timing cannot be sourced from a documented public
  timestamp are excluded from grading, as are events with intraday timing.
  This rule was fixed before the timing classification was visible.
  Timestamp: 2026-08-11T23:00:00Z

Non-US exchange convention (dated decision, 2026-08-12, made before event
count was known):
  - Home-listed tickers (ALV.DE, SIE.DE, PUM.DE, MC.PA, STAN.L) are graded
    against their own exchange session. XETRA and Euronext Paris: 09:00-17:30
    CET. LSE: 08:00-16:30 London time. yfinance returns local prices in local
    currency for these lines.
  - ADR tickers (BCS, NVO, AMKBY, LNVGY) are graded against the NYSE session,
    09:30-16:00 ET. yfinance returns USD prices on the US line. All four
    issuers publish in their home market in the early hours ET, so the reaction
    necessarily lands at the US open.
  - Limitation: ADR returns carry a currency effect. A move in the underlying
    and a move in the local currency against the dollar both appear in the ADR
    line, so an ADR overnight gap is not a clean read of the earnings reaction.
  - The release time is a property of the issuer. The classification
    (pre_market/after_hours) is a property of the issuer plus the exchange
    being priced. Barclays published at 07:01 GMT via the London RNS; that
    same fact classifies as pre_market whether judged against LSE or NYSE.

Reads the calibration CSV for the 268-event list, applies strict boundary
definitions to each event's extracted text, and writes an amended audit CSV.

Boundary definitions (applied exactly):
  1. Press Release: delimited by === PRESS RELEASE === header.
  2. Prepared Remarks / Q&A split (strict precedence):
     FIRST:  FactSet "QUESTION AND ANSWER SECTION" header
     SECOND: natural-language transition phrase
     If NEITHER: mark as "manual"
     Do NOT use [Operator Instructions] as a primary marker.
  3. Guidance: untestable (mechanically infeasible with structural splitting).
  4. Q&A: everything from the transition marker through end of transcript block.

Proportional split check: prepared remarks must be >= 10% of transcript words, else
"manual". The 100-word absolute floor is kept as a belt-and-braces assertion (every
event it catches is also caught by the 10% floor at current N, so it is redundant
but harmless).

Known recoverable losses (chosen not to recover at 3 weeks to deadline):
  - WDAY_FQ2_2025, WDAY_FQ4_2025: Workday IR boilerplate uses "Following prepared
    remarks, we will take questions" before the actual prepared remarks begin,
    causing the transition phrase to match in the intro.  Recoverable with a
    per-source marker for InsiderMonkey's Workday template.
  - WDAY_FQ3_2025: Globe and Mail source formatting, same pattern.
  - NFLX_FQ1_2025, NFLX_FQ2_2025, NFLX_FQ1_2026, NFLX_FQ4_2024, NFLX_FQ4_2025,
    NFLX_FQ3_2025: InsiderMonkey source formatting places "we will begin with our
    results" or similar in the moderator intro.  Recoverable with per-source markers.
  These go in the write-up as known recoverable losses, not unexplained exclusions.

Transcript vs marker reconciliation: 231 events have a transcript section, but 6
have no split marker (transcript_split_marker=none): 3 truncated LLY transcripts
(Q&A physically omitted from source), 2 PEP events (raw HTML source, markers buried
in markup), and SPOT_FQ1_2026 (misattributed document).  225 events have a marker.
"""

import csv
import os
import re
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
from eval.excluded_events import EXCLUDED_EVENTS  # noqa: E402
CALIBRATION_CSV = os.path.join(
    PROJECT_ROOT, "outputs", "global", "summary",
    "global_outcome_calibration_phase2.csv",
)
WORKSHEET_FLAGS_CSV = os.path.join(
    PROJECT_ROOT, "outputs", "global", "summary",
    "worksheet_leak_flags.csv",
)
OUTPUT_CSV = os.path.join(
    PROJECT_ROOT, "outputs", "global", "summary",
    "section_availability_audit_amended.csv",
)
MIN_HALF_WORDS = 100
MIN_PREPARED_FRACTION = 0.10  # fail to manual if prepared < 10% of transcript

# ---------------------------------------------------------------------------
# Transition-phrase patterns (case-insensitive)
# These match natural-language cues that the operator or management uses to
# hand over to Q&A.  ORDER matters: we take the FIRST match in the text.
# ---------------------------------------------------------------------------
TRANSITION_PATTERNS = [
    # Explicit "open" phrasing (with optional "up", "it")
    r"open\s+(?:it\s+)?(?:up\s+)?(?:the\s+)?(?:call|floor|line|phone\s+line|lines|session)?\s*(?:up\s+)?(?:for|to)\s+(?:your\s+)?questions",
    # "take questions" phrasing
    r"(?:let'?s|we(?:'ll| will| would| can| shall)?|I(?:'ll| will)?)\s+(?:now\s+)?(?:take|begin\s+taking|start\s+taking)\s+(?:your\s+)?questions",
    # "happy/pleased/ready to take/answer your questions" - broad subject
    r"(?:happy|pleased|glad|ready)\s+to\s+(?:take|answer|address)\s+(?:y\s*our\s+)?questions",
    # "now take questions" / "now begin Q&A"
    r"(?:we(?:'ll| will| shall)?|I(?:'ll| will)?)\s+now\s+(?:take|begin|start|move\s+(?:on\s+)?to|proceed\s+(?:to|with))\s+(?:the\s+)?(?:Q\s*&\s*A|question)",
    # "Our/The first question comes from"
    r"(?:our|the)\s+first\s+question\s+(?:comes?\s+from|is\s+from|today\s+(?:comes?|is)\s+from)",
    # "turn it over for questions"
    r"turn\s+(?:it|the\s+call)\s+over\s+(?:for|to)\s+(?:your\s+)?questions",
    # "open the line for questions" / "open up the line"
    r"open\s+(?:up\s+)?(?:the\s+)?(?:line|lines|phone\s+lines?)\s+(?:for|to)\s+(?:your\s+)?questions",
    # "begin the question-and-answer" / "begin the Q&A" / "begin our Q&A"
    r"begin\s+(?:the\s+|our\s+)?(?:question[\s-]*and[\s-]*answer|Q\s*&\s*A)(?:\s+(?:session|portion|segment|period))?",
    # "move/turn/proceed/transition to Q&A" / "move to questions"
    r"(?:move|proceed|transition|turn|go)\s+(?:on\s+|over\s+)?(?:to|into)\s+(?:the\s+)?(?:Q\s*&\s*A|question[\s-]*and[\s-]*answer|(?:analyst\s+)?questions)",
    # "QUESTION & ANSWER:" header (some Benzinga transcripts)
    r"^QUESTION\s*&\s*ANSWER\s*:",
    # "QUESTIONS AND ANSWERS" header (LSEG transcripts)
    r"QUESTIONS\s+AND\s+ANSWERS",
    # "Questions & Answers" / "Question & Answers" (inline, e.g. United Airlines / GS transcripts)
    r"Question(?:s)?\s*&\s*Answers?",
    # "Question-and-Answer Session" header
    r"^Question[\s-]*and[\s-]*Answer\s+Session",
    # "Q&A" as a standalone section header line
    r"^Q\s*&\s*A$",
    # "open the call for questions"
    r"open\s+(?:up\s+)?(?:the\s+)?call\s+for\s+(?:your\s+)?questions",
    # "open the line for any questions" (Hilton-style)
    r"open\s+(?:up\s+)?(?:the\s+)?(?:line|lines)\s+for\s+(?:any\s+)?questions",
    # "go to the first question" (Salesforce/Dell-style)
    r"(?:go|let'?s\s+go)\s+to\s+(?:the\s+)?(?:first\s+)?question",
    # "first question will come from" (variant of "comes from")
    r"(?:our|the)\s+first\s+question\s+(?:will\s+)?(?:comes?\s+from|come\s+from|is\s+from|today\s+(?:comes?|is)\s+from)",
    # "The first analyst is" (Tesla-style webcast format)
    r"(?:move\s+on\s+to|go\s+to|start\s+with)\s+(?:the\s+)?(?:analyst\s+)?questions",
    # "open up the line" (without explicit "for questions" -- GS style)
    r"open\s+up\s+the\s+line(?:\s+for\s+questions)?",
]

COMPILED_TRANSITION = [
    re.compile(p, re.IGNORECASE | re.MULTILINE) for p in TRANSITION_PATTERNS
]

FACTSET_HEADER = re.compile(
    r"QUESTION\s+AND\s+ANSWER\s+SECTION", re.IGNORECASE
)

PRESS_RELEASE_HEADER = re.compile(r"===\s*PRESS RELEASE\s*===")
TRANSCRIPT_HEADER = re.compile(r"===\s*EARNINGS CALL TRANSCRIPT\s*===")
# Match any === ... === header to find the next section after transcript
SECTION_HEADER = re.compile(r"^===\s+.+\s+===$", re.MULTILINE)


def _word_count(text: str) -> int:
    return len(text.split())


def _extract_sections(full_text: str):
    """Return (press_release_text, transcript_text, doc_types_present)."""
    # Find all section headers and their positions
    headers = []
    for m in SECTION_HEADER.finditer(full_text):
        headers.append((m.start(), m.end(), m.group().strip()))

    press_release_text = None
    transcript_text = None
    doc_types = []

    for i, (start, end, header) in enumerate(headers):
        # Determine the end of this section (start of next header, or end of file)
        section_end = headers[i + 1][0] if i + 1 < len(headers) else len(full_text)
        section_content = full_text[end:section_end].strip()

        # Clean header for doc_types
        clean = header.replace("=", "").strip()
        doc_types.append(clean)

        if PRESS_RELEASE_HEADER.search(header):
            press_release_text = section_content
        if TRANSCRIPT_HEADER.search(header):
            transcript_text = section_content

    return press_release_text, transcript_text, "; ".join(doc_types)


def _find_qa_split(transcript_text: str):
    """
    Apply strict precedence to find the Q&A boundary within a transcript.

    Returns (marker_type, split_pos, prepared_text, qa_text) or
            (marker_type, None, None, None) if no split found.

    marker_type: 'factset_header' | 'transition_phrase' | 'none'
    split_pos: character position in transcript_text where Q&A begins
    """
    # FIRST: FactSet header
    m = FACTSET_HEADER.search(transcript_text)
    if m:
        # Split at the start of the header line
        split_pos = m.start()
        prepared = transcript_text[:split_pos].strip()
        qa = transcript_text[split_pos:].strip()
        return "factset_header", split_pos, prepared, qa

    # SECOND: natural-language transition phrase
    best_match = None
    best_pos = len(transcript_text)  # We want the FIRST occurrence

    for pat in COMPILED_TRANSITION:
        m = pat.search(transcript_text)
        if m and m.start() < best_pos:
            best_pos = m.start()
            best_match = m

    if best_match is not None:
        # Split at the match position.  Try to back up to the start of the
        # line containing the match, but only if that line is reasonably
        # close (within 500 chars) -- some transcripts are single-line
        # (Insider Monkey, Benzinga) where rfind("\n") jumps to position 0.
        line_start = transcript_text.rfind("\n", 0, best_match.start())
        if line_start >= 0 and (best_match.start() - line_start) < 500:
            split_pos = line_start + 1
        else:
            split_pos = best_match.start()
        prepared = transcript_text[:split_pos].strip()
        qa = transcript_text[split_pos:].strip()
        return "transition_phrase", split_pos, prepared, qa

    return "none", None, None, None


def load_human_score_events():
    """Return set of document_ids with has_human_score == True."""
    events = set()
    with open(WORKSHEET_FLAGS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["has_human_score"].strip() == "True":
                events.add(row["document_id"].strip())
    return events


def audit_event(issuer: str, document_id: str, human_score_events: set):
    """Audit a single event. Returns a dict for the output row."""
    # Build extracted text path
    extracted_path = os.path.join(
        PROJECT_ROOT, "outputs", issuer, "extracted", f"{document_id}.txt"
    )

    has_human = document_id in human_score_events

    result = {
        "document_id": document_id,
        "issuer": issuer,
        "press_release": "absent",
        "prepared_remarks": "absent",
        "qa": "absent",
        "transcript_split_marker": "none",
        "min_half_wordcount": "",
        "doc_types_present": "",
        "has_human_worksheet": str(has_human),
        "notes": "",
    }

    if not os.path.exists(extracted_path):
        result["notes"] = "extracted text file not found"
        return result

    with open(extracted_path, "r", encoding="utf-8", errors="replace") as f:
        full_text = f.read()

    press_text, transcript_text, doc_types = _extract_sections(full_text)
    result["doc_types_present"] = doc_types

    # 1. Press release
    if press_text is not None and _word_count(press_text) > 0:
        result["press_release"] = "available"

    # 2/4. Prepared remarks + Q&A (requires transcript)
    if transcript_text is None or _word_count(transcript_text) < 10:
        # No transcript at all
        result["prepared_remarks"] = "absent"
        result["qa"] = "absent"
        result["transcript_split_marker"] = "none"
        if transcript_text is None:
            result["notes"] = "no transcript section"
        else:
            result["notes"] = "transcript too short"
        return result

    marker_type, split_pos, prepared, qa = _find_qa_split(transcript_text)
    result["transcript_split_marker"] = marker_type

    if marker_type == "none":
        result["prepared_remarks"] = "manual"
        result["qa"] = "manual"
        result["notes"] = "no Q&A transition marker found"
        return result

    # Minimum word-count assertion on both halves
    wc_prepared = _word_count(prepared) if prepared else 0
    wc_qa = _word_count(qa) if qa else 0
    wc_total = _word_count(transcript_text) if transcript_text else 0
    min_half = min(wc_prepared, wc_qa)
    result["min_half_wordcount"] = str(min_half)

    if min_half < MIN_HALF_WORDS:
        result["prepared_remarks"] = "manual"
        result["qa"] = "manual"
        result["notes"] = (
            f"min-half wordcount {min_half} < {MIN_HALF_WORDS} "
            f"(prepared={wc_prepared}, qa={wc_qa}); "
            f"marker was {marker_type}"
        )
        return result

    # Proportional split check: prepared remarks must be >= 10% of transcript
    prepared_frac = wc_prepared / wc_total if wc_total > 0 else 0
    if prepared_frac < MIN_PREPARED_FRACTION:
        result["prepared_remarks"] = "manual"
        result["qa"] = "manual"
        result["notes"] = (
            f"prepared fraction {prepared_frac:.1%} < {MIN_PREPARED_FRACTION:.0%} "
            f"(prepared={wc_prepared}, transcript={wc_total}); "
            f"marker was {marker_type}"
        )
        return result

    result["prepared_remarks"] = "available"
    result["qa"] = "available"

    return result


def main():
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Load calibration CSV for event list
    events = []
    with open(CALIBRATION_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            events.append({
                "issuer": row["issuer"],
                "document_id": row["document_id"],
                "ticker": row["ticker"],
                "report_date": row["report_date"],
            })

    human_score_events = load_human_score_events()

    # Audit each event
    rows = []
    manual_from_min_wc = 0
    manual_from_proportion = 0
    for ev in events:
        result = audit_event(ev["issuer"], ev["document_id"], human_score_events)
        result["ticker"] = ev["ticker"]
        result["report_date"] = ev["report_date"]
        result["run_id"] = run_id
        rows.append(result)
        if "min-half wordcount" in result.get("notes", ""):
            manual_from_min_wc += 1
        elif "prepared fraction" in result.get("notes", ""):
            manual_from_proportion += 1

    # Write output CSV with metadata header
    fieldnames = [
        "document_id", "ticker", "issuer", "report_date",
        "press_release", "prepared_remarks", "qa",
        "transcript_split_marker", "min_half_wordcount",
        "doc_types_present", "has_human_worksheet", "notes", "run_id",
    ]

    with open(OUTPUT_CSV, "w", newline="") as f:
        # Metadata header as comment lines
        f.write(f"# Section Boundary Audit (amended definitions)\n")
        f.write(f"# Run ID: {run_id}\n")
        f.write(f"# Timestamp: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"# Minimum half word count: {MIN_HALF_WORDS}\n")
        f.write(f"# Minimum prepared fraction: {MIN_PREPARED_FRACTION:.0%}\n")
        f.write(f"#\n")
        f.write(f"# Exclusion rule (fixed before timing classification was visible):\n")
        f.write(f"# Events whose release timing cannot be sourced from a documented public\n")
        f.write(f"# timestamp are excluded from grading, as are events with intraday timing.\n")
        f.write(f"# This rule was fixed before the timing classification was visible.\n")
        f.write(f"# Timestamp: 2026-08-11T23:00:00Z\n")
        f.write(f"#\n")
        f.write(f"# Amended boundary definitions:\n")
        f.write(f"# 1. Press Release: Content delimited by === PRESS RELEASE === header.\n")
        f.write(f"# 2. Prepared Remarks: Within transcript, operator opening through Q&A transition.\n")
        f.write(f"#    Strict precedence: (a) FactSet QUESTION AND ANSWER SECTION header,\n")
        f.write(f"#    (b) natural-language transition phrase, (c) if neither: manual.\n")
        f.write(f"#    [Operator Instructions] NOT used as primary marker.\n")
        f.write(f"# 3. Guidance Passage: Untestable (mechanically infeasible).\n")
        f.write(f"# 4. Q&A: From transition marker through end of transcript block.\n")
        f.write(f"#\n")
        f.write(f"# Known recoverable losses (not recovered, 3 weeks to deadline):\n")
        f.write(f"#   WDAY x3: IR boilerplate transition phrase in intro (InsiderMonkey/Globe and Mail)\n")
        f.write(f"#   NFLX x6: InsiderMonkey moderator intro transition phrase\n")
        f.write(f"#   These are per-source formatting issues, recoverable with source-specific markers.\n")
        f.write(f"#\n")
        f.write(f"# Transcript/marker reconciliation: 231 have transcript, 6 have no marker\n")
        f.write(f"#   (3 truncated LLY, 2 raw-HTML PEP, 1 misattributed SPOT).\n")
        f.write(f"#\n")
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    # Compute summary statistics
    n_total = len(rows)
    n_pr = sum(1 for r in rows if r["press_release"] == "available")
    n_prep_avail = sum(1 for r in rows if r["prepared_remarks"] == "available")
    n_qa_avail = sum(1 for r in rows if r["qa"] == "available")
    n_prep_manual = sum(1 for r in rows if r["prepared_remarks"] == "manual")
    n_no_transcript = sum(1 for r in rows if r["prepared_remarks"] == "absent")
    n_factset = sum(1 for r in rows if r["transcript_split_marker"] == "factset_header")
    n_transition = sum(1 for r in rows if r["transcript_split_marker"] == "transition_phrase")
    n_none_marker = sum(1 for r in rows if r["transcript_split_marker"] == "none")

    # Four-arm intersection
    four_arm_all = sum(
        1 for r in rows
        if r["press_release"] == "available"
        and r["prepared_remarks"] == "available"
        and r["qa"] == "available"
    )

    # ----- Task 4: Revised Achievable N -----
    # Exclusion sets
    excluded_human = human_score_events  # 25 events
    excluded_lly = {"LLY_FQ1_2026", "LLY_FQ3_2025", "LLY_FQ4_2025"}
    excluded_spot = set(EXCLUDED_EVENTS)
    all_exclusions = excluded_human | excluded_lly | excluded_spot

    def is_excluded(doc_id):
        return doc_id in all_exclusions

    # Four-arm with and without exclusions
    four_arm_excl = sum(
        1 for r in rows
        if r["press_release"] == "available"
        and r["prepared_remarks"] == "available"
        and r["qa"] == "available"
        and not is_excluded(r["document_id"])
    )

    # Two-arm with and without exclusions
    two_arm_all = n_pr
    two_arm_excl = sum(
        1 for r in rows
        if r["press_release"] == "available"
        and not is_excluded(r["document_id"])
    )

    # Events with no transcript - company breakdown
    no_transcript = [r for r in rows if r["prepared_remarks"] == "absent"]
    from collections import Counter
    no_transcript_by_company = Counter(
        (r["ticker"], r["issuer"]) for r in no_transcript
    )

    # Print summary
    print(f"Section Boundary Audit (amended definitions)")
    print(f"Run ID: {run_id}")
    print(f"Total events: {n_total}")
    print(f"")
    print(f"Press release:   available={n_pr}, absent={n_total - n_pr}")
    print(f"Prepared remarks: available={n_prep_avail}, manual={n_prep_manual}, absent={n_no_transcript}")
    print(f"Q&A:             available={n_qa_avail}, manual={n_prep_manual}, absent={n_no_transcript}")
    print(f"")
    print(f"Transcript split marker breakdown:")
    print(f"  factset_header:    {n_factset}")
    print(f"  transition_phrase: {n_transition}")
    print(f"  none:              {n_none_marker}")
    print(f"")
    print(f"Events failed to manual by min-wordcount assertion (<{MIN_HALF_WORDS} words): {manual_from_min_wc}")
    print(f"Events failed to manual by proportional check (<{MIN_PREPARED_FRACTION:.0%} prepared): {manual_from_proportion}")
    print(f"")
    print(f"=== Task 4: Revised Achievable N ===")
    print(f"")
    print(f"Exclusions applied:")
    print(f"  Human-score worksheet events: {len(excluded_human)}")
    print(f"  Truncated LLY transcripts:    {len(excluded_lly)}")
    print(f"  Misattributed SPOT:           {len(excluded_spot)}")
    n_excl_overlap = sum(1 for d in (excluded_lly | excluded_spot) if d in excluded_human)
    total_unique_exclusions = len(all_exclusions)
    print(f"  Total unique exclusions:      {total_unique_exclusions}")
    print(f"")
    print(f"1. Four-arm intersection (PR + prepared_remarks + Q&A all available):")
    print(f"   Before exclusions: {four_arm_all}")
    print(f"   After exclusions:  {four_arm_excl}")
    print(f"")
    print(f"2. Two-arm N (PR available):")
    print(f"   Before exclusions: {two_arm_all}")
    print(f"   After exclusions:  {two_arm_excl}")
    print(f"")
    print(f"3. Events with no transcript ({len(no_transcript)} total):")
    for (ticker, issuer), count in sorted(no_transcript_by_company.items(), key=lambda x: -x[1]):
        print(f"   {ticker:12s} ({issuer:30s}): {count}")
    print(f"")
    print(f"Output written to:")
    print(f"  {OUTPUT_CSV}")

    # Write revised_achievable_n.md
    md_path = os.path.join(
        PROJECT_ROOT, "outputs", "global", "summary",
        "revised_achievable_n.md",
    )
    with open(md_path, "w") as f:
        f.write(f"# Revised Achievable N\n\n")
        f.write(f"Run ID: `{run_id}`\n")
        f.write(f"Generated: {datetime.now(timezone.utc).isoformat()}\n\n")
        f.write(f"## Source\n\n")
        f.write(f"Based on `section_availability_audit_amended.csv` (amended boundary definitions).\n")
        f.write(f"Total events in calibration CSV: {n_total}\n\n")
        f.write(f"## Amended boundary definitions applied\n\n")
        f.write(f"1. **Press Release**: Content delimited by `=== PRESS RELEASE ===` header.\n")
        f.write(f"2. **Prepared Remarks**: Within transcript, operator opening through Q&A transition marker.\n")
        f.write(f"   Strict precedence: (a) FactSet `QUESTION AND ANSWER SECTION` header, "
                f"(b) natural-language transition phrase, (c) if neither: `manual`.\n")
        f.write(f"   `[Operator Instructions]` is NOT used as a primary marker.\n")
        f.write(f"   Minimum word-count assertion: both halves >= {MIN_HALF_WORDS} words, else `manual`.\n")
        f.write(f"   Proportional check: prepared remarks >= {MIN_PREPARED_FRACTION:.0%} of transcript words, else `manual`.\n")
        f.write(f"3. **Guidance Passage**: Mechanically infeasible with structural splitting. Recorded as untestable.\n")
        f.write(f"4. **Q&A**: From transition marker through end of transcript block.\n\n")
        f.write(f"## Section availability summary\n\n")
        f.write(f"| Section | Available | Manual | Absent |\n")
        f.write(f"|---------|-----------|--------|--------|\n")
        f.write(f"| Press release | {n_pr} | - | {n_total - n_pr} |\n")
        f.write(f"| Prepared remarks | {n_prep_avail} | {n_prep_manual} | {n_no_transcript} |\n")
        f.write(f"| Q&A | {n_qa_avail} | {n_prep_manual} | {n_no_transcript} |\n")
        f.write(f"| Guidance | - | - | untestable |\n\n")
        f.write(f"Transcript split marker breakdown: "
                f"factset_header={n_factset}, transition_phrase={n_transition}, none={n_none_marker}\n\n")
        f.write(f"Events failed to `manual` by min-wordcount assertion "
                f"(<{MIN_HALF_WORDS} words on either half): **{manual_from_min_wc}**\n\n")
        f.write(f"Events failed to `manual` by proportional check "
                f"(prepared < {MIN_PREPARED_FRACTION:.0%} of transcript): **{manual_from_proportion}**\n\n")
        f.write(f"## Exclusions\n\n")
        f.write(f"| Category | Count | Events |\n")
        f.write(f"|----------|-------|--------|\n")
        f.write(f"| Human-score worksheet | {len(excluded_human)} | "
                f"{', '.join(sorted(excluded_human)[:5])}... |\n")
        f.write(f"| Truncated LLY transcripts | {len(excluded_lly)} | "
                f"{', '.join(sorted(excluded_lly))} |\n")
        f.write(f"| Misattributed SPOT | {len(excluded_spot)} | "
                f"{', '.join(sorted(excluded_spot))} |\n")
        # Check for overlaps
        lly_in_human = excluded_lly & excluded_human
        spot_in_human = excluded_spot & excluded_human
        if lly_in_human or spot_in_human:
            overlap_docs = lly_in_human | spot_in_human
            f.write(f"\nOverlap (already in human-score list): "
                    f"{', '.join(sorted(overlap_docs))}\n")
        f.write(f"\nTotal unique exclusions: **{total_unique_exclusions}**\n\n")

        f.write(f"## 1. Four-arm intersection N\n\n")
        f.write(f"Events where press_release=available AND prepared_remarks=available "
                f"AND qa=available (all three separable sections exist).\n\n")
        f.write(f"- **Before exclusions: {four_arm_all}**\n")
        f.write(f"- **After exclusions: {four_arm_excl}**\n\n")

        f.write(f"## 2. Two-arm N (full bundle vs PR only)\n\n")
        f.write(f"Events where press_release=available. Materially larger because it does not "
                f"require a splittable transcript.\n\n")
        f.write(f"- **Before exclusions: {two_arm_all}**\n")
        f.write(f"- **After exclusions: {two_arm_excl}**\n\n")

        f.write(f"## 3. No-transcript events: company and region breakdown\n\n")
        f.write(f"**{len(no_transcript)} events** have no transcript section "
                f"(`=== EARNINGS CALL TRANSCRIPT ===` absent).\n\n")
        f.write(f"| Ticker | Issuer | Quarters missing |\n")
        f.write(f"|--------|--------|------------------|\n")
        for (ticker, issuer), count in sorted(
            no_transcript_by_company.items(), key=lambda x: -x[1]
        ):
            f.write(f"| {ticker} | {issuer} | {count} |\n")

        # Classify by region
        non_us_tickers = {
            "ALV.DE", "BCS", "LNVGY", "MC.PA", "PUM.DE",
            "SIE.DE", "STAN.L", "AMKBY",
        }
        no_tr_non_us = sum(
            1 for r in no_transcript if r["ticker"] in non_us_tickers
        )
        no_tr_us = len(no_transcript) - no_tr_non_us

        f.write(f"\n**Regional concentration**: Of the {len(no_transcript)} no-transcript events, "
                f"{no_tr_non_us} ({no_tr_non_us*100//len(no_transcript) if no_transcript else 0}%) "
                f"belong to non-US-listed names ({', '.join(sorted(t for t in non_us_tickers if any(r['ticker']==t for r in no_transcript)))}) "
                f"and {no_tr_us} to US names. "
                f"These are concentrated in non-US and newer names where free English-language "
                f"earnings call transcripts are less reliably available from sources like "
                f"Motley Fool, Benzinga, or FactSet.\n")

    print(f"  {md_path}")


if __name__ == "__main__":
    main()
