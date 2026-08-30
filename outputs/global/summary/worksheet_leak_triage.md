# Worksheet Leak Triage

run_id: 20260811T191953Z
date: 2026-08-11

## (a) Affected events

53 of 268 extracted text files contain an `=== EARNINGS DOCUMENT ===` section.
Of these 53, **25 are genuine human blind-sentiment worksheets** containing a
human rater's sentiment score, directional signal, correctness verdict, and
realised horizon returns. The other 28 are ordinary press releases or
supplemental filings that happen to carry `doc_type: "Earnings Document"` in the
manifest (no human judgement content).

The 25 human-worksheet events span 9 tickers: AMD (3), AMZN (3), COIN (3),
LLY (3), META (3), NFLX (3), NVDA (4), TSLA (3).

Full event list in `worksheet_leak_flags.csv` (same directory).

## (b) Pipeline path: the worksheet text IS fed to the LLM

The pipeline **does** pass worksheet content to the LLM. The mechanism:

1. Each manifest entry (`manifests/p2_*_reports.json`) lists documents by
   `doc_type`. All 53 affected events include a document with
   `"doc_type": "Earnings Document"`.

2. `report_pipeline.build_bundle_text()` (line 460) iterates over
   `report.documents` -- the manifest's document list -- and for each document
   calls `extract_doc_text()` on its `source_pdf`, then concatenates with a
   section header:

   ```python
   for doc in report.documents:                                      # line 460
       header = BUNDLE_SECTION_HEADERS.get(doc.doc_type, doc.doc_type.upper())  # line 461
       ...
       sections.append(f"=== {header} ===\n\n{extraction.text}")     # line 469
   ```

3. `BUNDLE_SECTION_HEADERS` (lines 43-47) maps only three doc_types:

   ```python
   BUNDLE_SECTION_HEADERS = {
       "Press Release": "PRESS RELEASE",
       "Earnings Presentation": "EARNINGS PRESENTATION",
       "Earnings Call Transcript": "EARNINGS CALL TRANSCRIPT",
   }
   ```

   `"Earnings Document"` is not in this map, so the fallback
   `doc.doc_type.upper()` produces `"EARNINGS DOCUMENT"`.

4. The concatenated text goes straight to `build_user_message()` as
   `report_text`, then into `call_llm()` as the user message content. There is
   **no filtering or section-stripping** between extraction and the LLM call.

5. `run_reports.process_report()` (lines 271-273) shows the flow:

   ```python
   report_text, per_doc_meta, bundle_warnings = build_bundle_text(report)
   extraction_target.write_text(report_text, encoding="utf-8")
   ```

   The same `report_text` is then passed to `build_doc_params()` and onward to
   the LLM. The extracted text file on disk is a faithful record of what the
   model received.

**Conclusion: the LLM saw the full worksheet content, including the human's
score, signal, and -- critically -- the realised price returns.**

## (c) What the worksheets contain

### Example 1: AMD_FQ1_2026 (David Eji, 14 July 2026)

Human sentiment score and directional call (category i -- leakage of human judgement):

> Score:+0.80
> Signal: BUY

Post-event realised returns (category ii -- look-ahead, fatal):

> Score given vs. correct call: signal wasBUY, matching the correct call, so
> the call was CORRECT. Horizon returns (pre-registered) [...] Overnight
> (baseline for the label) +15.26% D+1 close +18.61% D+3 close +28.13%
> D+5 close +26.19%

### Example 2: NVDA_FQ2_2025 (Dragos Macsim, 29 June 2026)

Human sentiment score and signal (category i):

> Sentiment score: +0.35. [...] Directional signal: BUY.

The worksheet also contains realised price data (category ii).

### Example 3: TSLA_FQ4_2025 (David Eji, 16 July 2026)

Human sentiment score and signal (category i):

> Score:+0.60
> Signal: BUY

Realised returns follow the same template (category ii).

All 25 human worksheets follow the same structure: conventions, metadata,
headline financials summary, human-authored analysis, a numeric sentiment score,
a directional signal, a correctness verdict against the realised overnight move,
and a full table of realised horizon returns (overnight through D+20).

**Every one of the 25 human-worksheet events contains both (i) a human
directional judgement and (ii) post-event realised returns.**

## (d) Split figures

### 5-day directional accuracy (blend_correct_default)

| Group | n | Accuracy |
|---|---|---|
| All events | 268 | 36.57% |
| EARNINGS DOCUMENT section (any) | 53 | 41.51% |
| No EARNINGS DOCUMENT | 215 | 35.35% |
| Human-score worksheet | 25 | 44.00% |
| Non-human-score | 243 | 35.80% |

Bootstrap (unpaired) accuracy difference, EARNINGS DOCUMENT vs none:
+6.16pp, 90% CI [-6.09%, +18.82%], p=0.396.

Bootstrap accuracy difference, human-score worksheet vs none:
+8.20pp, 90% CI [-8.33%, +25.43%], p=0.433.

### Overnight mean net per trade

| Group | Trades | Mean net/trade |
|---|---|---|
| EARNINGS DOCUMENT section | 40 | +2.192% |
| No EARNINGS DOCUMENT | 131 | +1.559% |
| Human-score worksheet | 20 | +3.432% |
| Non-human-score | 151 | +1.479% |

Bootstrap (unpaired) net/trade difference, EARNINGS DOCUMENT vs none:
+0.633pp, 90% CI [-1.222%, +2.442%], p=0.587.

Bootstrap net/trade difference, human-score worksheet vs none:
+1.954pp, 90% CI [-0.887%, +4.644%], p=0.242.

### Agreement rate with human arm

Human-rater directional signals (BUY/HOLD/SELL) were extracted directly from the
worksheet text embedded in each of the 25 affected events' extracted text files
(the same text the LLM received). The human signal was parsed via the
`Signal: <BUY|HOLD|SELL>` or `Directional signal: <BUY|HOLD|SELL>` pattern
present in every worksheet. All 25 events yielded a parseable human signal.

**LLM-human agreement on the 25 worksheet events: 18/25 = 72.0%**

| Metric | Value |
|---|---|
| Agreement rate | 72.0% (18/25) |
| Chance agreement (marginals) | 43.4% |
| Cohen's kappa | 0.506 |
| 90% bootstrap CI on agreement | [56.0%, 84.0%] |
| Permutation p-value (vs chance) | 0.0013 |

Signal distributions (n=25): human BUY=17, HOLD=3, SELL=5; LLM BUY=13, HOLD=5,
SELL=7. The 7 disagreements: AMD_FQ2_2025 (human BUY, LLM HOLD),
COIN_FQ1_2026 (human BUY, LLM SELL), LLY_FQ3_2025 (human SELL, LLM BUY),
META_FQ1_2026 (human BUY, LLM SELL), NVDA_FQ2_2025 (human BUY, LLM HOLD),
TSLA_FQ1_2026 (human HOLD, LLM SELL), TSLA_FQ3_2025 (human BUY, LLM HOLD).

The 72% agreement rate is significantly above the 43.4% chance rate expected from
the marginal signal distributions (permutation p=0.0013). Cohen's kappa of 0.506
indicates moderate-to-good agreement, consistent with the LLM having read and
been influenced by the human's directional call embedded in the input text.

### Clean-group comparison (2026-08-12, from human_decisions_export)

Human-rater decisions from `data/human/human_decisions_export_2026-08-12.csv`,
derived from `Master_Data_NEW_REPAIRED_2026-08-09.xlsx`, `Human_Data_Entry` tab.
Filtered to: `section=All`, `first_rater_for_event=YES`, `in_llm_universe=YES`,
paired (both human and LLM decision present). N=205. `decisions_agree` column
verified against raw decision columns: 0 mismatches.

Join: event_key → document_id via ticker + year + quarter from manifests.
16 event_keys in LLM universe failed to match (quarters not yet scored:
JNJ Q1 2026, CAT Q1 2026, UNH Q1 2026, BKNG Q1 2025, DELL Q2 2025,
KHC Q4 2025, plus MetLife/Allianz fiscal-offset gaps). No fuzzy matching used.

The workbook's Section C re-pricing chose the measurement window per row. Of
205 paired rows, 58 are `fact_based` (release date + stated time), 64 are
`price_based` (selection on outcome), 80 are `other`, 3 are `not_repriced`.
Results reported on `fact_based` first, `price_based` as robustness check,
per the data supplier's instruction.

#### Pooled across all repricing_basis_class (headline)

| Group | N | Agreement rate |
|---|---|---|
| Worksheet-contaminated | 25 | 60.0% (15/25) |
| Clean | 180 | 38.3% (69/180) |

Bootstrap unpaired difference: **+21.7pp**, 90% CI [+4.4pp, +38.7pp], **p=0.042**.

#### Fact-based rows only (confounded, reported for completeness)

| Group | N | Agreement rate |
|---|---|---|
| Worksheet-contaminated | 24 | 62.5% (15/24) |
| Clean | 34 | 23.5% (8/34) |

Bootstrap unpaired difference: +39.0pp, 90% CI [+18.1pp, +58.6pp], p=0.0028.

**Confound**: 24 of 25 contaminated events are `fact_based`, but only 34 of 180
clean events are, because one of the `fact_based` basis strings is "release date
+ stated time in the document (rater worksheet)" — an event is `fact_based`
largely *because* it has a worksheet. This comparison selects the two groups on
different criteria and overstates the contamination effect. The pooled figure
(+21.7pp, p=0.042) is the defensible headline.

#### Price-based rows (robustness check)

No worksheet-contaminated events have `price_based` repricing, so this
comparison is structurally empty. The clean group's agreement rate on
`price_based` rows is 46.9% (30/64), higher than the clean fact-based rate
(23.5%), consistent with price-based window selection inflating agreement
— the measurement window was chosen to show a move, and a move is easier
to agree on directionally.

#### Per-rater agreement (clean group, fact_based + all pooled)

| Rater | Clean (all rbc) | N |
|---|---|---|
| Abdul | 32.4% | 37 |
| Anna | 41.7% | 48 |
| Dragos | 25.0% | 32 |
| Meriem | 60.7% | 28 |
| Nigel | 34.3% | 35 |

David does not appear in the clean group (all his paired reads are on
worksheet-contaminated events: 11/19 = 57.9% agreement).

#### Cohen's kappa on the clean group

The clean group's 38.3% agreement is around what two three-way classifiers
would produce by chance given their marginal distributions.

3x3 confusion matrix (rows=human, cols=LLM, clean group N=180):

|            |  BUY | HOLD | SELL |
|------------|------|------|------|
| Human BUY  |   34 |   47 |   21 |
| Human HOLD |    7 |   14 |   20 |
| Human SELL |    4 |   12 |   21 |

Marginal distributions:
- Human: BUY 56.7%, HOLD 22.8%, SELL 20.6%
- LLM: BUY 25.0%, HOLD 40.6%, SELL 34.4%

The two arms disagree structurally: the human arm calls BUY on 57% of events,
the LLM arm on 25%. The LLM holds or sells where the human buys.

| Metric | Value |
|---|---|
| Observed agreement (p_o) | 0.383 |
| Expected chance agreement (p_e) | 0.305 |
| Cohen's kappa | **0.113** |
| 90% bootstrap CI on kappa | [0.036, 0.191] |

Kappa is near zero. The two arms are systematically unrelated — their
directional calls share barely more structure than two independent classifiers
with these marginals. This is a finding about the arms, not a failed check:
the human arm is directionally optimistic (BUY 57%, SELL 21%), the LLM arm is
HOLD-heavy (HOLD 41%, BUY 25%). Two opposite failure modes — the human arm
over-calls upside, the model over-hedges. Their near-independence is precisely
why their agreement is informative rather than tautological: combining weakly
correlated signals is the standard reason an agreement filter works, and the
filter does work (+17.3pp after excluding the contaminated events, p=0.029).

#### Agreement filter recomputed excluding the 25 contaminated events

The headline result (LLM accuracy higher where the arms agree than where they
disagree) was computed on a dataset that included the contaminated events.
Recomputed on `returns_matrix.csv` overnight returns with ±2% band:

|                | Before excl. |     | After excl. |     |
|----------------|-------------|-----|-------------|-----|
|                | Accuracy    | N   | Accuracy    | N   |
| Arms agree     | 38.2%       | 68  | 32.7%       | 55  |
| Arms disagree  | 23.7%       | 59  | 15.4%       | 52  |
| Difference     | +14.5pp (p=0.069) | | **+17.3pp (p=0.029)** | |

The filter **strengthens** after excluding the contaminated events (+17.3pp,
significant at p<0.05, vs +14.5pp, marginal at p=0.069 before). Removing the
25 events where the LLM was reading the human's answer removes mechanically
inflated agreement, leaving a cleaner signal where genuine agreement predicts
accuracy.

**This is the authoritative agreement-filter headline.** The previously
documented 0.561 vs 0.429 figures cannot be regenerated from this codebase:
`git log -S` across all branches finds them only as prose in
`Model_Arm_Implementation_Spec.md` (assertion "already computed"), with no
script, output file, or intermediate artifact that produces them. They
should not be presented.

**RETRACTED (2026-08-12).** The +17.3pp agreement filter effect was
computed on the old `report_date` anchor. On the corrected `release_date`
anchor: agree 69.0% (20/29) vs disagree 69.2% (18/26), difference
−0.3pp (p=0.959). See `agreement_filter_corrected.csv` and
`retracted_findings_2026-08-12.md`. The figures below are retained as a
historical record only.

~~Agreement filter effect: **+17.3pp** (p=0.029). LLM correct-direction
accuracy on overnight returns (±2% band) is 32.7% (18/55 traded events)
where both arms agree, vs 15.4% (8/52) where they disagree. Computed on
107 traded events from 180 clean paired rows (section=All,
first_rater_for_event=YES, 25 worksheet events excluded).~~

#### Scope limitations on the paired analysis

- **86 event_keys** in the human data are for companies outside the LLM
  universe entirely (Adobe, Chevron, Duke Energy, ExxonMobil, Home Depot,
  Mastercard, and others). The human arm covers materially more companies
  than the LLM arm; all paired figures rest on their intersection.
- **16 event_keys** are in the LLM universe but failed to match a scored
  quarter: JNJ Q1 2026, CAT Q1 2026, UNH Q1 2026, BKNG Q1 2025, DELL Q2
  2025, KHC Q4 2025, plus MetLife and Allianz fiscal-offset gaps. These are
  unscored quarters and fiscal-calendar misalignments, not join errors.

#### Note on the two agreement figures (60% here vs 72% earlier)

The earlier 72% (18/25) was computed by extracting the human signal directly
from the worksheet text in the LLM's input (the `Signal: BUY/HOLD/SELL` line
in the embedded worksheet). This analysis uses the human rater's actual
decision from the workbook export, which can differ from the signal recorded
in the worksheet (e.g., if the rater revised their call after the worksheet
was generated). Both figures show the contaminated group significantly above
the clean baseline; the workbook-based figure (60%) is the more conservative
and the one to cite.

## (e) Conclusion

**This is a real leak, not a potential one.** The pipeline mechanism is
unambiguous: `build_bundle_text()` concatenates every document listed in the
manifest, the manifest lists the worksheet PDF as `"Earnings Document"`, and no
filtering occurs before the text reaches the LLM.

For the 25 human-worksheet events, the model received:
- A human rater's sentiment score (-1 to +1) and directional signal (BUY/HOLD/SELL)
- A human rater's written analysis and evidence reasoning
- The realised overnight price move and whether the human's call was correct
- Realised horizon returns out to D+20

The **look-ahead** component (realised returns baked into the input text) is the
more severe concern: for these 25 events, the model could read the actual
overnight move before producing its own score. This is not merely a human-
judgement contamination issue -- it is a future-information leak.

The directional performance difference (human-worksheet group: 44.0% accuracy,
3.43% mean net/trade vs. clean group: 35.8% accuracy, 1.48% mean net/trade) is
directionally consistent with contamination but not statistically significant at
conventional levels (accuracy p=0.433, net/trade p=0.242 via unpaired
bootstrap). However, with only n=25 affected events, the test has limited power
to detect a real effect.

**Severity**: 25 of 268 events (9.3%) have their micro-layer score compromised
by look-ahead data. Any accuracy or P&L figure computed over the full N=268
dataset is tainted by these events and cannot be cited as clean. The remaining
28 "Earnings Document" sections that are just press releases are benign (no human
judgement or realised returns) -- they add legitimate source material, equivalent
to any other press release section.
