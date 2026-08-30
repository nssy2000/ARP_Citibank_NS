"""Script 2: heuristic fabrication smell-test for the gap-onboarding combos.

Task 6 of the gap-onboarding plan explicitly notes background sourcing
subagents "repeatedly fabricated placeholder/mismatched documents, caught
only by manual byte-level verification." This script re-checks every combo
`phase2/gap_combos.json` marks sourced/blended: does the source document's
extracted text actually mention the company/ticker, and does it look like a
real earnings document rather than short placeholder boilerplate? This is a
SMELL TEST, not proof - it flags candidates for a human to eyeball, it does
not certify a document is genuine (a well-written placeholder can pass; a
genuine document with unusual formatting can fail). Read-only."""
from __future__ import annotations

import re

from _common import BASE_DIR, Finding, load_gap_combos, print_findings

MIN_CHARS_OK = 2000  # matches report_pipeline.MIN_EXTRACTED_TEXT_CHARS
SMELL_MIN_CHARS = 4000  # below this, a genuine earnings doc is unusually thin


def _ticker_root(ticker: str) -> str:
    return ticker.split(".")[0].upper()


def run() -> list[Finding]:
    import report_pipeline as rp

    findings: list[Finding] = []
    combos = load_gap_combos()
    sourced = {k: v for k, v in combos.items() if v.get("status") in ("sourced", "blended", "sourced_partial_dead_end")}
    checked = 0
    smell_hits = 0

    for key, combo in sourced.items():
        company = combo.get("company", "")
        ticker = combo.get("ticker", "")
        fiscal_year = combo.get("year", "")
        for doc in combo.get("documents", []):
            src = doc.get("source_pdf")
            if not src:
                continue
            path = BASE_DIR / src
            if not path.exists():
                continue  # already reported by check_manifest_docs.py
            checked += 1
            try:
                extraction = rp.extract_doc_text(path)
            except Exception as exc:
                findings.append(Finding("HIGH", "extraction-failed", f"{key} [{doc.get('doc_type')}] {src}: {exc}"))
                smell_hits += 1
                continue

            text = extraction.text
            text_lower = text.lower()
            company_words = [w for w in re.split(r"\s+", company) if len(w) > 2]
            company_hit = any(w.lower() in text_lower for w in company_words) if company_words else True
            ticker_hit = _ticker_root(ticker) in text.upper() if ticker else True
            year_hit = fiscal_year in text if fiscal_year else True

            reasons = []
            if not company_hit:
                reasons.append(f"company name {company!r} not found in extracted text")
            if not ticker_hit:
                reasons.append(f"ticker {ticker!r} not found in extracted text")
            if not year_hit:
                reasons.append(f"fiscal year {fiscal_year!r} not found in extracted text")
            if len(text) < SMELL_MIN_CHARS:
                reasons.append(f"unusually short extracted text ({len(text)} chars)")
            if extraction.warnings:
                reasons.append(f"extractor warnings: {extraction.warnings}")

            if reasons:
                smell_hits += 1
                sev = "HIGH" if (not company_hit and not ticker_hit) else "MEDIUM"
                findings.append(Finding(
                    sev, "sourcing-smell",
                    f"{key} [{doc.get('doc_type')}] {src}: " + "; ".join(reasons),
                ))

    findings.append(Finding("INFO", "summary", f"checked {checked} documents across {len(sourced)} gap combos, {smell_hits} flagged for manual review"))
    return findings


if __name__ == "__main__":
    print_findings("Script 2: gap-sourced document fabrication smell-test", run())
