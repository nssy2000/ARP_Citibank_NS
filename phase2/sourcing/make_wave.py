"""Prints ready-to-dispatch Agent-tool prompts for the next wave of Tier-2
sourcing, for combos gap_combos.json still needs micro docs and/or a news
digest for. Run this, then in the SAME Claude Code session dispatch one
Agent tool call per printed ticker block (parallel, run_in_background: true)
using the prompt text verbatim. This script cannot invoke the Agent tool
itself.

Usage: python phase2/sourcing/make_wave.py [--wave-size N]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GAP_COMBOS_PATH = BASE_DIR / "phase2" / "gap_combos.json"

WAVE_SIZE = int(sys.argv[sys.argv.index("--wave-size") + 1]) if "--wave-size" in sys.argv else 6

RECEIPT_SCHEMA = """{
  "ticker": "<TICKER>",
  "combos": [
    {
      "year": "2025", "quarter": "Q3",
      "documents_written": [
        {"doc_type": "Press Release", "path": "docs/<slug>/CY2025-Q3/press_release.pdf"},
        {"doc_type": "Earnings Presentation", "path": "docs/<slug>/CY2025-Q3/presentation.pdf"},
        {"doc_type": "Earnings Call Transcript", "path": "docs/<slug>/CY2025-Q3/transcript.pdf"}
      ],
      "news_digest_written": true,
      "unresolved": []
    }
  ]
}"""


def main() -> None:
    combos = json.loads(GAP_COMBOS_PATH.read_text(encoding="utf-8"))
    needs_tier2: dict[str, list[dict]] = {}
    for key, c in combos.items():
        if c["status"] != "report_date_resolved":
            continue
        have_types = {d["doc_type"] for d in c.get("documents", [])}
        needs_micro = len(have_types) < 2
        needs_news = not c.get("news_document_written")
        if needs_micro or needs_news:
            needs_tier2.setdefault(c["ticker"], []).append({**c, "key": key, "needs_micro": needs_micro, "needs_news": needs_news})

    tickers = sorted(needs_tier2.keys())
    wave = tickers[:WAVE_SIZE]
    if not wave:
        print("No combos currently need Tier-2 sourcing.")
        return

    print(f"Wave: {len(wave)} of {len(tickers)} remaining tickers ({tickers})\n")
    print("Dispatch one Agent tool call per ticker below, in parallel, run_in_background: true,")
    print("subagent_type: general-purpose, cheap/fast model. Each call MUST return ONLY the JSON")
    print("receipt (schema below) as its final message - no document text, no page content.\n")
    print("Receipt schema:\n" + RECEIPT_SCHEMA + "\n")

    for ticker in wave:
        entries = needs_tier2[ticker]
        slug = entries[0]["slug"]
        company = entries[0]["company"]
        combo_list = "\n".join(
            f"  - {e['year']} {e['quarter']} (report_date={e['report_date']}, "
            f"already have: {[d['doc_type'] for d in e.get('documents', [])]}, "
            f"needs_micro={e['needs_micro']}, needs_news={e['needs_news']})"
            for e in sorted(entries, key=lambda e: (e["year"], e["quarter"]))
        )
        print(f"--- {ticker} ({company}, slug={slug}) ---")
        print(
            f"Source earnings documents and a pre-earnings news digest for {company} ({ticker}), "
            f"slug '{slug}', for these quarters:\n{combo_list}\n\n"
            f"For each quarter needing micro docs: find and download the press release, earnings "
            f"presentation, and earnings call transcript (whichever exist publicly - investor "
            f"relations site, PR Newswire/Business Wire, Motley Fool/Seeking Alpha/Benzinga "
            f"transcripts). Save under docs/{slug}/CY<year>-Q<fq>/ (fq = 1-4 for the quarter number), "
            f"any descriptive filename. For each quarter needing a news digest: write a pre-earnings "
            f"market-expectations digest (analyst estimates, stock trend, guidance chatter heading "
            f"into the print) to docs/news/p2_{slug}/{ticker}_FQ<fq>_<year>.txt, plain text, with "
            f"source URLs and publish dates inline - EVERY source article must be dated strictly "
            f"BEFORE that quarter's report_date (hard rule: no post-earnings reaction language). "
            f"Do not read full document contents back into your response. Return ONLY the JSON "
            f"receipt (schema given) listing what you wrote and any quarters you couldn't resolve, "
            f"under 'unresolved'."
        )
        print()


if __name__ == "__main__":
    main()
