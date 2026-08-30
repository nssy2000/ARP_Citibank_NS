# Revised Achievable N

Run ID: `20260820T150023Z`
Generated: 2026-08-20T15:00:25.294536+00:00

## Source

Based on `section_availability_audit_amended.csv` (amended boundary definitions).
Total events in calibration CSV: 268

## Amended boundary definitions applied

1. **Press Release**: Content delimited by `=== PRESS RELEASE ===` header.
2. **Prepared Remarks**: Within transcript, operator opening through Q&A transition marker.
   Strict precedence: (a) FactSet `QUESTION AND ANSWER SECTION` header, (b) natural-language transition phrase, (c) if neither: `manual`.
   `[Operator Instructions]` is NOT used as a primary marker.
   Minimum word-count assertion: both halves >= 100 words, else `manual`.
   Proportional check: prepared remarks >= 10% of transcript words, else `manual`.
3. **Guidance Passage**: Mechanically infeasible with structural splitting. Recorded as untestable.
4. **Q&A**: From transition marker through end of transcript block.

## Section availability summary

| Section | Available | Manual | Absent |
|---------|-----------|--------|--------|
| Press release | 211 | - | 57 |
| Prepared remarks | 162 | 69 | 37 |
| Q&A | 162 | 69 | 37 |
| Guidance | - | - | untestable |

Transcript split marker breakdown: factset_header=36, transition_phrase=189, none=43

Events failed to `manual` by min-wordcount assertion (<100 words on either half): **10**

Events failed to `manual` by proportional check (prepared < 10% of transcript): **53**

## Exclusions

| Category | Count | Events |
|----------|-------|--------|
| Human-score worksheet | 25 | AMD_FQ1_2026, AMD_FQ2_2025, AMD_FQ4_2025, AMZN_FQ1_2026, AMZN_FQ3_2025... |
| Truncated LLY transcripts | 3 | LLY_FQ1_2026, LLY_FQ3_2025, LLY_FQ4_2025 |
| Misattributed SPOT | 2 | DIS_FQ1_2025, SPOT_FQ1_2026 |

Overlap (already in human-score list): LLY_FQ1_2026, LLY_FQ3_2025, LLY_FQ4_2025

Total unique exclusions: **27**

## 1. Four-arm intersection N

Events where press_release=available AND prepared_remarks=available AND qa=available (all three separable sections exist).

- **Before exclusions: 124**
- **After exclusions: 124**

## 2. Two-arm N (full bundle vs PR only)

Events where press_release=available. Materially larger because it does not require a splittable transcript.

- **Before exclusions: 211**
- **After exclusions: 209**

## 3. No-transcript events: company and region breakdown

**37 events** have no transcript section (`=== EARNINGS CALL TRANSCRIPT ===` absent).

| Ticker | Issuer | Quarters missing |
|--------|--------|------------------|
| C | p2_citigroup | 4 |
| BAC | p2_bank_of_america | 4 |
| LNVGY | p2_lenovo | 4 |
| PLTR | p2_palantir | 4 |
| MET | p2_metlife | 3 |
| SIE.DE | p2_siemens | 3 |
| BA | p2_boeing | 2 |
| MC.PA | p2_lvmh | 2 |
| PUM.DE | p2_puma | 2 |
| STAN.L | p2_standard_chartered | 2 |
| SBUX | p2_starbucks | 2 |
| PEP | p2_pepsico | 1 |
| ALV.DE | p2_allianz | 1 |
| BKNG | p2_booking_holdings | 1 |
| GIS | p2_general_mills | 1 |
| WDAY | p2_workday | 1 |

**Regional concentration**: Of the 37 no-transcript events, 14 (37%) belong to non-US-listed names (ALV.DE, LNVGY, MC.PA, PUM.DE, SIE.DE, STAN.L) and 23 to US names. These are concentrated in non-US and newer names where free English-language earnings call transcripts are less reliably available from sources like Motley Fool, Benzinga, or FactSet.
