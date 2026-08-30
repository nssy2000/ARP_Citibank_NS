"""Script 4: news digest date-leakage scan. The News layer's whole premise
(CLAUDE.md > Architecture > News; llm_news.py docstring) is that every source
article is dated strictly before report_date - an earlier version leaked
post-earnings reaction language by pulling from "earnings date and following."
No automated checker enforces this today. This script parses every
docs/news/<issuer>/<document_id>.txt, extracts every date mentioned in the
file, and flags any date >= that combo's report_date. Read-only."""
from __future__ import annotations

import re
from datetime import date, datetime

from _common import BASE_DIR, Finding, all_phase2_reports, print_findings

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
ISO_DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
LONG_DATE = re.compile(rf"\b({MONTHS})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b")
URL_DATE = re.compile(r"/(20\d{2})/(\d{2})/(\d{2})/")

MONTH_INDEX = {m: i + 1 for i, m in enumerate(MONTHS.split("|"))}


def _extract_dates(text: str) -> list[date]:
    found: list[date] = []
    for m in ISO_DATE.finditer(text):
        try:
            found.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    for m in LONG_DATE.finditer(text):
        try:
            found.append(date(int(m.group(3)), MONTH_INDEX[m.group(1)], int(m.group(2))))
        except ValueError:
            pass
    for m in URL_DATE.finditer(text):
        try:
            found.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    return found


def run() -> list[Finding]:
    findings: list[Finding] = []
    news_dir = BASE_DIR / "docs" / "news"
    checked = 0
    leaks = 0
    on_date = 0

    for report in all_phase2_reports():
        issuer = report.get("issuer")
        document_id = report.get("document_id")
        report_date_str = report.get("report_date")
        if not (issuer and document_id and report_date_str):
            continue
        report_date = datetime.strptime(report_date_str, "%Y-%m-%d").date()

        news_path = news_dir / issuer / f"{document_id}.txt"
        if not news_path.exists():
            continue  # documented gap (Maersk/Netflix Q4 2024) - not this script's job to flag
        checked += 1
        text = news_path.read_text(encoding="utf-8", errors="replace")

        # Skip the digest's own header line ("... (report date YYYY-MM-DD)"),
        # which intentionally states report_date and isn't a source citation.
        lines = text.splitlines()
        body = "\n".join(lines[1:]) if lines else text

        dates_found = _extract_dates(body)
        after = sorted({d for d in dates_found if d > report_date})
        same_day = sorted({d for d in dates_found if d == report_date})

        if after:
            leaks += 1
            findings.append(Finding(
                "CRITICAL", "news-date-leakage",
                f"{issuer}/{document_id}.txt: source date(s) {after} are AFTER report_date {report_date} - "
                f"post-earnings language may have leaked into the pre-earnings digest",
            ))
        if same_day:
            on_date += 1
            findings.append(Finding(
                "LOW", "news-date-same-day",
                f"{issuer}/{document_id}.txt: source date(s) {same_day} equal report_date {report_date} (borderline, not strictly before)",
            ))

    findings.append(Finding("INFO", "summary", f"checked {checked} news digests, {leaks} with post-report_date source dates, {on_date} with same-day source dates"))
    return findings


if __name__ == "__main__":
    print_findings("Script 4: news digest date-leakage scan", run())
