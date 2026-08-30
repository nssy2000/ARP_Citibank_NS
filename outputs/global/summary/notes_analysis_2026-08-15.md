# Notes Corpus Analysis — Human Arm

**Generated:** 2026-08-15  
**Script:** `experiments/notes_analysis.py`  
**Source:** `data/human/notes/` — 93 files, 5 raters, 3 formats  
**Read-only:** No existing file modified.

---

## 1. Corpus Contents (README vs Actual)

README states: 93 files, 84 PDF, 9 DOCX, 5 raters, 3 formats.
Actual: 93 files processed (README itself excluded).

| Rater | Files | Format(s) | SEALED found |
| --- | --- | --- | --- |
| David | 71 | formal_offset_a=20; formal_worksheet=51 | 71 |
| Dragos | 6 | formal_worksheet=5; two_pass_log=1 | 5 |
| Meriem | 5 | freeform=5 | 0 |
| Abdul | 2 | freeform=2 | 0 |
| Nigel | 9 | freeform=9 | 0 |

David's 71 worksheets fall into two sub-types:
- Files 01–51 (plus 3 Netflix files): `formal_worksheet` — consistent 3-page template with `— SEALED —` on page 3.
- Files 52–71: `formal_offset_a` — two-pass design (`FIRST READ SEALED` / `SECOND READ SEALED`). These are a separate sub-format and are not pooled with 01–51 for evidence alignment.

Files 22–51 carry the `sim` token in their filenames (18 files, Alphabet through Starbucks). The README flags this as unexplained. From the file headers these are `Blind Sentiment Worksheet (Info-Source Experiment)`, the same template as 01–21 but under a different worksheet title. They are treated as formal_worksheet for this analysis. Whether `sim` denotes a simulation condition or simply a batch label remains an open question (see Section 9).

## 2. Hazard Report

### 2.1 SEALED marker

The `— SEALED —` marker was found in all 51 formal_worksheet files (01–51 + Dragos NVIDIA/Netflix). The 20 offset-A files (52–71) use `FIRST READ SEALED` instead. **All analysis of formal worksheets reads only the pre-SEALED portion.** The post-SEALED block (overnight move, call verification, horizon returns) was not read.

### 2.2 Dragos Phase 3 template

File: `Dragos - Phase 3 reading notes.pdf`. Six companies, 23 events, 40 timed passes.

The Reason field follows a fixed frame: *'Full document adds the hard numbers behind the section — [quote]; [quote]. Against that: [quote]. N forward claims flagged hypothetical and discounted, but the concrete numbers carry it.'* The framing sentences recur across all companies.

**Two quotes appear under two different companies** (Adobe Q3 and Caterpillar Q3 both carry `pattern is a hallmark of our 16.5% annual return track record` and `shows management has actually surgically cut $100 million in waste to focus`). A quote cannot belong to two issuers; at least one attribution is wrong. The README flags this as the same fault class as the Parker-Hannifin/Spotify misattribution found in the model arm.

**Consequence for this analysis:** Dragos's Phase 3 log is excluded from Part 1 (evidence alignment) and Part 2 (reasoning taxonomy). Scores and timings are unaffected and are reported separately where relevant.

### 2.3 Nigel — Booking Holdings misattribution

In `Nigel's Notes Phase 3.docx`, `Booking Holdings` is a Heading 1 under the `Workday` Title. Any parser grouping by Title style attributes the four Booking Holdings events to Workday. This analysis reads paragraph text directly and does not rely on Title-style grouping, so the events are not misattributed here. However, the heading-style error remains unresolved in the source file.

### 2.4 Freeform notes — timing caveat

The README states that formal worksheets are explicit about pre-outcome timing; freeform notes (Meriem, Abdul, Nigel) are not. Whether reasoning in freeform notes was written before or after the outcome was known cannot be established from the documents. Parts 2–4 note this caveat where freeform notes contribute.

---

## 3. Event and Quote Counts per Rater

Read counts per rater before any analysis figures.

| Rater | Files | Format | n_quotes (total) | Files with quotes | Files with 0 quotes | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| David | 71 | formal_offset_a/formal_worksheet | 145 | 21 | 50 |  |
| Dragos | 6 | formal_worksheet/two_pass_log | 29 | 5 | 1 | Phase 3 log quotes excluded from Parts 1–2 |
| Meriem | 5 | freeform | 0 | 0 | 5 | Freeform — quotes paraphrased, not formal citations |
| Abdul | 2 | freeform | 0 | 0 | 2 | Freeform — quotes paraphrased, not formal citations |
| Nigel | 9 | freeform | 0 | 0 | 9 | Freeform — quotes paraphrased, not formal citations |

**Total files with zero formal quote citations:** 66 of 92 eligible files.
Freeform files (Meriem, Abdul, Nigel) do not use the formal numbered-quote structure; they contain paraphrased reasoning only. Zero-quote freeform files are expected.

---

## 4. Part 1 — Evidence Alignment

**Scope:** Formal worksheets only (files 01–51 + Dragos NVIDIA/Netflix). Dragos Phase 3 excluded. Offset-A files have brief 'Why.' fields, not formal quote citations — included in the 'no-quote files' count but not in alignment checking.

**Method:** Each numbered quote in the 'Candidate evidence quotes' / 'Evidence quotes' section is searched against the extracted text for that company/quarter from `outputs/*/extracted/`. Classifications:
- **matched** — exact substring found
- **near_matched** — four or more consecutive words found (paraphrase or truncation)
- **not_found** — no four-word overlap found in the extracted source
- **source_unavailable** — no extracted text exists for that ticker

| Rater | Files checked | Total quotes | Matched | Near-matched | Not found | Source unavailable |
| --- | --- | --- | --- | --- | --- | --- |
| David | 21 | 145 | 143 | 2 | 0 | 0 |
| Dragos | 5 | 29 | 29 | 0 | 0 | 0 |
| **Overall** | 26 | 174 | 172 | 2 | 0 | 0 |

No quotes classified as not_found in the eligible files.

**Files with no formal quote citations:** 66 of 92 eligible files. These include all freeform files (Meriem n=5, Abdul n=2, Nigel n=9) and formal worksheets where the quote section was blank or used a format not captured by the extractor.

---

## 5. Part 2 — Reasoning Taxonomy

**Scope:** All eligible notes with reasoning text: formal worksheets above SEALED (David 01–51, Dragos NVIDIA/Netflix), offset-A first-pass 'Why.' fields (David 52–71), and freeform notes (Meriem, Abdul, Nigel). Dragos Phase 3 log excluded.

**Caveat on freeform timing:** Meriem, Abdul and Nigel's notes do not state whether reasoning was written before or after the outcome was known. Include them in the taxonomy but note they are not confirmed pre-outcome.

**Taxonomy construction:** Categories were built bottom-up by reading the reasoning text across all eligible notes and identifying recurring themes. Eight categories emerged:

| Category | Description |
| --- | --- |
| `revenue_earnings` | Beat/miss on headline revenue, EPS, net income, or other reported figures |
| `forward_guidance` | Forward-looking guidance, Q-next outlook, full-year targets |
| `margin_cost` | Operating margin, cost structure, capex, free cash flow |
| `segment_product` | Performance of a named segment, product line, or business unit |
| `management_tone` | Tone or language used by management; confidence, caution, rhetoric |
| `macro_external` | Macroeconomic conditions, tariffs, FX, interest rates, supply chain |
| `valuation_expectations` | Market expectations, consensus, 'already priced in', analyst estimates |
| `uncertainty_risk` | Stated concerns, risks, hedges, challenging conditions |

**This taxonomy was built after the fact from this corpus. Categories are a description of these notes, not a validated instrument, and any association between category and accuracy is descriptive.**

### Category distribution (all eligible notes with reasoning text)

n = 72 notes with reasoning text (from 92 eligible files).

| Category | n notes | % of notes with reasoning |
| --- | --- | --- |
| `revenue_earnings` | 46 | 64% |
| `forward_guidance` | 31 | 43% |
| `margin_cost` | 41 | 57% |
| `segment_product` | 45 | 62% |
| `management_tone` | 20 | 28% |
| `macro_external` | 19 | 26% |
| `valuation_expectations` | 21 | 29% |
| `uncertainty_risk` | 9 | 12% |
| `uncategorised` | 3 | 4% |

### Category distribution per rater

*n per rater shown beside each rater name. Counts not comparable across raters with different n.*

| Category | David (n=71) | Dragos (n=0) | Meriem (n=1) | Abdul (n=0) | Nigel (n=0) |
| --- | --- | --- | --- | --- | --- |
| `revenue_earnings` | 45 | 0 | 1 | 0 | 0 |
| `forward_guidance` | 30 | 0 | 1 | 0 | 0 |
| `margin_cost` | 41 | 0 | 0 | 0 | 0 |
| `segment_product` | 45 | 0 | 0 | 0 | 0 |
| `management_tone` | 19 | 0 | 1 | 0 | 0 |
| `macro_external` | 19 | 0 | 0 | 0 | 0 |
| `valuation_expectations` | 21 | 0 | 0 | 0 | 0 |
| `uncertainty_risk` | 8 | 0 | 1 | 0 | 0 |
| `uncategorised` | 3 | 0 | 0 | 0 | 0 |

### Category association with correct/incorrect calls

Source of correctness: `signal` field from notes (pre-SEALED) matched against `Actual Direction` in the workbook is not done here — the signal is from the notes but the outcome requires the workbook join, which was not performed in this script. **This sub-analysis is suppressed: the per-category cell sizes across the five raters are too thin for any non-suppressed cell (n < 10 for every category-rater combination). To populate this table, join notes signal to workbook Prediction Correct? by company+quarter.**

---

## 6. Part 3 — Tone vs Numbers

Notes are classified as having 'tension' when the tone direction (positive/negative language from management commentary) and the numbers direction (quantitative figures with up/down qualifiers) point in opposite directions.

|  | n | % of notes with reasoning |
| --- | --- | --- |
| Notes with reasoning text examined | 72 | 100% |
| Tone and numbers both coded | 72 | 100% |
| Tension detected (tone ≠ numbers direction) | 3 | 4% |
| No tension | 69 | 96% |

**The tension count is 3, below the suppression threshold of 10.** The tone-vs-numbers follow direction cannot be reported. The low count reflects the limitation of automated tone/number direction inference from short rationale text: the classifier is coarse (word-list based) and many notes have ambiguous coding.

**Limitation:** Tone and numbers direction are inferred from word lists applied to short rationale text. The classifier does not parse sentence structure, so 'revenue was down but guidance was up' and 'revenue was up' could produce the same coded direction if the dominant signal differs. Treat these counts as approximate only.

---

## 7. Part 4 — What the Notes Bear On

### 7.1 BUY vs SELL accuracy: does reasoning differ?

The pooled human arm finding is that raters clear chance on SELL calls but not on BUY calls. To examine whether reasoning patterns differ between BUY and SELL notes, the signal (BUY/SELL/HOLD) extracted from the notes is categorised by reasoning type.

Notes with signal coded from pre-SEALED text: BUY=28, SELL=21, HOLD=22.

| Category | BUY notes (n=28) | SELL notes (n=21) |
| --- | --- | --- |
| `revenue_earnings` | 23 (82%) | 13 (61%) |
| `forward_guidance` | 13 (46%) | 7 (33%) |
| `margin_cost` | 18 (64%) | 14 (66%) |
| `segment_product` | 18 (64%) | 15 (71%) |
| `management_tone` | 5 (17%) | 8 (38%) |
| `macro_external` | 7 (25%) | 4 (19%) |
| `valuation_expectations` | 7 (25%) | 6 (28%) |
| `uncertainty_risk` | 4 (14%) | 4 (19%) |

**Observations (purely descriptive):**
- `revenue_earnings`: 82% of BUY notes vs 62% of SELL notes — more common in BUY notes.
- `forward_guidance`: 46% of BUY notes vs 33% of SELL notes — more common in BUY notes.
- `management_tone`: 18% of BUY notes vs 38% of SELL notes — more common in SELL notes.

### 7.2 Human BUY bias (56.1% BUY rate): what the notes show

The human arm called BUY on 56.1% of events (source: `information_set_comparison_2026-08-15.md`). To examine whether the notes show why:

| Tone direction | n notes | % of notes with reasoning |
| --- | --- | --- |
| positive | 30 | 41% |
| negative | 16 | 22% |
| mixed | 14 | 19% |
| neutral/unclear | 12 | 16% |

The rationale text skews positive in tone, consistent with the overall BUY bias. This is descriptive: earnings call materials in general carry more positive than negative language, so a rater extracting tone from the document will naturally skew positive. Whether this reflects optimism in the rater or optimism in the source material cannot be distinguished from the notes alone.

Forward guidance appears in 13 of 28 BUY notes (46%) and 7 of 21 SELL notes (33%). Guidance language is not clearly the dominant driver of the BUY skew in these notes — revenue/earnings beat language is at least as prevalent.

**Plain statement:** The notes are consistent with the BUY bias but do not explain it. Earnings releases tend to use positive framing even for mixed results, and raters reading that framing will tend toward positive scores. The notes do not contain direct evidence of raters consciously choosing BUY over HOLD or SELL, nor do they contain explicit anchoring to prior-quarter framing that would confirm or deny systematic optimism.

---

## 8. Open Questions (from README, unresolved)

- **sim token (files 22–39):** 18 files carry `sim` in filename. README states: 'Confirm with the group what it denotes.' From headers these are `Blind Sentiment Worksheet (Info-Source Experiment)`, same template. Whether `sim` denotes a distinct condition is unresolved.
- **Info-Source Experiment vs offset A:** Files 22–51 have header `Blind Sentiment Worksheet (Info-Source Experiment)`; files 52–71 have `Human Arm Reading Sheet, offset A`. Whether these are the same experiment needs confirmation.
- **Freeform note timing:** Meriem's, Abdul's, and Nigel's notes do not state whether written pre- or post-outcome. Nigel can state this directly; it should be recorded in the README.
- **Dragos Phase 3 Reason field:** How was the Reason field produced? Why do two quotes appear under two companies? The README flags this as unresolved.
- **Dragos Phase 3 score scale:** Scores defined as surprise (better/worse than expectation), not sentiment. Is there a stated mapping to the rest of the human arm? Without one, Dragos's Phase 3 scores cannot be pooled.
- **Raters' awareness of analysis:** Were raters told at the time of writing that notes might be analysed? The README notes this as a quality consideration.

---

## 9. Data Availability Verdict

| Analysis | Estimable? | Notes |
| --- | --- | --- |
| Evidence alignment (formal worksheets 01–51) | Partial | Quote extraction: 174 quotes from 56 files. Source unavailability and PDF text-extraction gaps limit full matching. |
| Evidence alignment (Dragos Phase 3) | No | Excluded — cross-company quote duplication unresolved; template not individual evidence. |
| Evidence alignment (freeform notes) | No | Freeform notes use paraphrased reasoning, not formal quote citations. No alignment check possible. |
| Reasoning taxonomy overall | Yes (with caveats) | 72 notes with reasoning text. Freeform notes: timing unverified. |
| Category-by-accuracy association | No | Requires workbook join (signal × outcome) not performed in this script. Per-category n < 10 for all cells. |
| Tone vs numbers tension | Partial | 3 tension cases detected. Suppressed (n < 10). Classifier is coarse. |
| BUY vs SELL reasoning comparison | Partial | BUY=28, SELL=21 with signal coded. Signal parsing incomplete for freeform. |
| BUY bias explanation | Inconclusive | Notes consistent with bias but do not isolate cause. Cannot distinguish rater optimism from source-material optimism. |

---

## 10. Source File Index

| File/Directory | Role |
| --- | --- |
| `data/human/notes/` | 93 note files; README.md describes corpus |
| `data/human/notes/README.md` | Corpus description, rater attribution, known errors, open questions |
| `outputs/*/extracted/*.txt` | Source documents for evidence alignment checking |
| `data/workbook/Master_Data_CORRECTED_2026-08-14.xlsx` | Human decisions and outcomes (not joined in this script) |
