"""Events excluded from the clean universe because the document itself is wrong.

Ten scripts each carried their own copy of `{"SPOT_FQ1_2026"}`, so adding an
exclusion meant ten edits or none - and "none" is silent. The corpus would read
232 in one script and 233 in the next, with nothing in either output to say
which was right. They import this instead, so an event added here reaches every
consumer in the same commit.

THIS IS ONLY THE BAD-DOCUMENT SET. The other three exclusions are derived from
their own artefacts at run time and stay where they are:

  - worksheet leakage      `worksheet_leak_flags.csv`, has_human_score == True
  - truncated transcripts  the LLY events, named where they are used
  - timing exclusions      `returns_matrix.csv`, timing_excluded == YES

Each entry carries its reason, because an exclusion is a claim about a document
and the claim is what a reader needs in order to disagree with it.
"""
from __future__ import annotations

EXCLUSION_REASONS: dict[str, str] = {
    "SPOT_FQ1_2026": (
        "Misattributed document: the transcript filed under this event is not "
        "Spotify's. Excluded since the phase-2 freeze."
    ),
    "DIS_FQ1_2025": (
        "Look-ahead contamination. Ruled 2026-08-24. The manifest bundles the "
        "correct Q1 FY2025 transcript with fy2025_q2xprxex991.txt, which is "
        "Disney's fiscal SECOND quarter press release - the quarter ended "
        "2025-03-29, filed 2025-05-07, EDGAR acc 0001744489-25-000096. That is "
        "91 days after this event's 2025-02-05 date. The scoring run read it: "
        "the result's own model_document_id is "
        "'DIS_Bundled Earnings Report_2025-05-07', and every financial field in "
        "the summary - revenue, EPS, guidance - is quoted from that release. "
        "The transcript quotes are genuine Q1 content, so the bundle is mixed "
        "rather than wholly wrong. The event is graded (ret_overnight +2.12%, "
        "UP) and its BUY was being scored correct, so the contamination was "
        "inflating accuracy rather than depressing it. The correct Q1 exhibit "
        "(acc 0001744489-25-000066) is not in the corpus, so the event is "
        "excluded rather than re-scored."
    ),
}

EXCLUDED_EVENTS: frozenset[str] = frozenset(EXCLUSION_REASONS)
