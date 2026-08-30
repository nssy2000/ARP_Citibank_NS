# Worksheet Exclusion Decision

Date: 2026-08-12
Decision: **Exclude** (not re-score)

## Reason

The 25 events listed below had their micro-layer score computed from input
text that included a human rater's blind sentiment worksheet via
`build_bundle_text()`. The worksheets contained:

- The human rater's sentiment score (-1 to +1) and directional signal
  (BUY/HOLD/SELL)
- The realised overnight price move and whether the call was correct
- Realised horizon returns out to D+20

This constitutes both human-judgement leakage and future-information leakage,
making those predictions invalid rather than merely noisy.

## Evidence

- **Pipeline mechanism**: `build_bundle_text()` had no `doc_type` filter.
  `"Earnings Document"` fell through to the fallback header and was
  concatenated into the LLM prompt verbatim. Fixed 2026-08-12 by adding
  `EXCLUDED_DOC_TYPES = {"Earnings Document"}` to `report_pipeline.py`.

- **Agreement contamination**: On fact-based repricing rows, agreement between
  the LLM and human raters is 62.5% (15/24) for the contaminated events vs
  23.5% (8/34) for clean events (bootstrap unpaired difference +39.0pp,
  p=0.0028). Pooled: 60.0% (15/25) vs 38.3% (69/180), +21.7pp, p=0.042.

- **Performance contamination**: Directional accuracy 44.0% vs 35.8%,
  mean net/trade +3.43% vs +1.48% (not significant at n=25, but directionally
  consistent with look-ahead).

## Excluded document_ids (25)

```
AMD_FQ1_2026    AMD_FQ2_2025    AMD_FQ4_2025
AMZN_FQ1_2026   AMZN_FQ3_2025   AMZN_FQ4_2025
COIN_FQ1_2026   COIN_FQ3_2025   COIN_FQ4_2025
LLY_FQ1_2026    LLY_FQ3_2025    LLY_FQ4_2025
META_FQ1_2026   META_FQ3_2025   META_FQ4_2025
NFLX_FQ3_2025   NFLX_FQ4_2024   NFLX_FQ4_2025
NVDA_FQ1_2025   NVDA_FQ2_2025   NVDA_FQ3_2025   NVDA_FQ4_2025
TSLA_FQ1_2026   TSLA_FQ3_2025   TSLA_FQ4_2025
```

Tickers affected: AMD (3), AMZN (3), COIN (3), LLY (3), META (3), NFLX (3),
NVDA (4), TSLA (3).

## Pipeline fix

`report_pipeline.py` now filters on document_id, not doc_type. The 25
excluded document_ids are listed in `WORKSHEET_EXCLUDED_DOCUMENT_IDS`.
Within those events, `_is_worksheet_document()` identifies the specific
worksheet file by filename pattern and excludes it from the bundle text.
Non-worksheet documents in the same event (e.g. transcripts) are still
included. The exclusion is logged in `per_doc_meta` and `combined_warnings`.

The blanket `EXCLUDED_DOC_TYPES = {"Earnings Document"}` filter was reverted
because 33 of the 59 "Earnings Document" entries are legitimate
company-authored content — but 4 of those 33 are **look-ahead contaminated**
(SEC periodic filings published after the event's decision point):

### Look-ahead contaminated (4 documents, 4 events)

| Event | Document | SEC filing date | report_date | Gap |
|---|---|---|---|---|
| UAL_FQ1_2025 | UAL 1Q25 10Q.pdf | 2025-04-16 | 2025-04-15 | +1 day |
| UAL_FQ2_2025 | UAL 2Q25 10Q.pdf | 2025-07-17 | 2025-07-16 | +1 day |
| UAL_FQ4_2025 | UAL 2025 10K.pdf | 2026-02-12 | 2026-01-20 | +23 days |
| BA_FQ4_2025 | e4434a19...pdf (10-K) | 2026-01-30 | 2026-01-26 | +4 days |

These periodic filings did not exist at the decision point. The model read
future documents. Each event has other documents (press release, transcript)
that were legitimately available — only the SEC filing needs removal.

### Borderline (2 documents, ~1-day discrepancy)

| Event | Document | Stated date | report_date | Gap |
|---|---|---|---|---|
| AMKBY_FQ1_2025 | Maersk Q1 Interim Report | 2025-05-08 | 2025-05-07 | +1 day |
| AMKBY_FQ3_2025 | Maersk Q3 Interim Report | 2025-11-06 | 2025-11-05 | +1 day |

Maersk releases headline numbers the evening before and the full interim
report the next morning (Copenhagen time). Minor risk — same numbers, more
detail.

### Clean (27 documents)

- 10 press releases / shareholder letters (WMT x5, NFLX x3, UAL x2) —
  published same day as report_date. Should be retyped to "Press Release".
- 12 financial summary / numbers sheets (IBM x3, MCD x3, NKE x3, MSFT x3) —
  all confirmed company-published official earnings press releases or call
  transcripts downloaded from corporate websites. No team-member worksheets.
  Published same day as report_date.
- 3 UAL investor updates — 8-K exhibits filed same day as report_date.
- 1 UAL financial results document — 8-K exhibit filed same day.
- 1 AMKBY_FQ2_2025 interim report — published same day.

All 33 were being read by the pipeline in deployed runs — they appear in
the extracted text files as `=== EARNINGS DOCUMENT ===` sections.
"Earnings Document" is an unreliable doc_type label covering worksheets,
look-ahead SEC filings, and legitimate source material.
