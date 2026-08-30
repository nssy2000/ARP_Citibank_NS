# Extension Pre-registration Note

**Date:** 2026-08-13  
**Written before any document has been gathered or any event has been scored for the extension.**

---

## Decision

The model arm is being extended to cover companies that the human arm read but the model arm
never scored. As of this date, 20 such companies have been identified from the group workbook
(Master_Data_CORRECTED_2026-08-13.xlsx), with 93 unique events across those companies.

---

## Selection Rule

The selection rule is: **every company where human readings exist in the group workbook but no
model arm scoring exists in the frozen N=233 results.**

This rule is determined entirely by the human arm's existing coverage. No property of the events
themselves — sector, return magnitude, volatility, or model-expected difficulty — was used to
select or de-select any company or quarter. Companies are included because a human read them, not
because anything is known or expected about how the model will perform on them.

---

## Scope of the Extension

93 unique events across 20 companies:

- **15 US issuers**: Adobe (ADBE), American Express (AXP), Chevron (CVX), Colgate-Palmolive (CL),
  Costco (COST), Datadog (DDOG), Duke Energy (DUK), ExxonMobil (XOM), Freeport-McMoRan (FCX),
  Home Depot (HD), Intel (INTC), Mastercard (MA), Shopify (SHOP), Union Pacific (UNP), eBay (EBAY).
- **5 non-US issuers**: Heineken (HEINY/HEIA), Hermes (RMSP.XC/RMS), Nestle (NSRGY/NESN),
  Shell (SHEL), Sony (SONY/6758.T).

The gathering checklist recording the exact event-by-event document paths is at
`outputs/global/summary/extension_gathering_checklist.csv`.

---

## Relationship to the Frozen Primary Results

The extension results **will be reported separately** from the frozen N=233 results. They are not
merged into the primary dataset and do not alter any figure, table, or finding that cites the
frozen state.

- The authoritative frozen state is tagged **model-arm-final-2026-08-13** (commit e8596e2).
- Every document citing that tag — `surviving_findings.md`, `frontier_table.csv`,
  `workbook_correction_log_2026-08-13.md`, `ext9_cost_grid_n233.json`, and all associated
  backing CSVs — remains the primary result and is not modified by this extension.
- Extension outputs will use a distinct output tree and a distinct calibration CSV
  (suffix `ext2026_08_13` or similar), never writing into the frozen results directories.

---

## Exclusion Rules Carried Over Unchanged

The following rules apply to every extension event identically to the primary N=233 universe:

1. **Release timing**: the entry date must be confirmed from a documented public timestamp.
   For US issuers this is the EDGAR 8-K Item 2.02 acceptance timestamp. For non-US issuers
   (Heineken, Hermes, Nestle, Shell, Sony) this must be sourced manually from each company's
   home exchange regulatory filing or IR announcement with a recorded date and time.
   Any event whose release timing cannot be confirmed is timing-excluded and not scored.

2. **Per-section attribution**: every document placed in the pipeline must be verified to
   contain the correct company, correct fiscal period, and correct document type before
   scoring. Documents gathered for this extension were collected through the same manual
   process that previously produced one misattributed transcript (NFLX) and two
   quarter-shifted news digests. Each file must be spot-checked (company name in opening
   text, fiscal period match to folder label) before the manifest entry is created.

3. **No post-decision-point content**: no document may contain information dated after the
   earnings release date. This includes news digests, analyst summaries, or any supplementary
   material. Press releases are sourced from the original EDGAR filing and are inherently safe
   on this criterion; any non-EDGAR document must have its date verified.

4. **Worksheet contamination**: the extension events were selected because the human arm
   read them, which means worksheet files exist for at least some raters. The worksheet leak
   check (`worksheet_leak_flags.csv`) applies unchanged: any event where a human annotated
   a worksheet score that was then visible to a subsequent scorer is excluded from the
   extension graded set.

---

## What This Note Does Not Pre-register

This note pre-registers the selection rule and the exclusion rules. It does not pre-register
a hypothesis about model performance on the extension set. The extension is a coverage
expansion, not a separate pre-registered experiment. Results will be reported descriptively
alongside the qualification that the same in-sample threshold concerns that apply to the
primary N=233 set apply here: the HOLD thresholds (+0.25/-0.05) were fitted on data the
model has already seen, and the extension events add new coverage without re-validating those
thresholds out of sample.

---

## Amendment A — 2026-08-13 (written after 7-event pilot, before further gathering)

**Pilot status when this amendment was written**: the 7-event pilot (Colgate-Palmolive 4 events,
Costco 3 events) had already been scored. Its outcome was 1 graded event (|ret|>2%), 0 traded
events, no accuracy computable. This outcome could not have informed any of the decisions below:
a single graded event with no trades gives no signal about which items to run or drop.

### Items the extension runs

The extension runs all five items, A through E, on the same basis as the frozen N=233 set.
This is decided now, before gathering begins and before any extension results beyond the 7-event
pilot are known, so that no item can be added or dropped on the basis of what the results show.

- **Item A** (return matrix): overnight and multi-horizon returns, same horizons as the frozen set.
  Release dates must be confirmed before the return matrix can be built; timing-unresolved events
  are excluded exactly as in the frozen set.
- **Item B** (holding-period curve): cumulative P&L curve across the extension traded events.
- **Item C** (four-arm section ablation): see stated limitation below.
- **Item D** (FinBERT and dictionary baselines): applied to the same document set as the model arm.
- **Item E** (walk-forward threshold validation): applied to the extension graded events; if the
  extension graded count is too small for walk-forward to be informative, this will be reported
  as a structural limitation rather than omitted.

### Reporting sets

Results will be reported on three event sets:

1. **FROZEN** (N=233, tagged model-arm-final-2026-08-13): the primary result. Never overwritten.
   All findings in surviving_findings.md refer to this set.
2. **EXTENSION ONLY** (up to 93 events, subject to exclusions): the sector broadening test.
   Reported as a separate descriptive block. The extension tests whether the frozen set's fitted
   thresholds generalise across sectors, not across time (the two date ranges overlap).
3. **COMBINED** (N=233 + extension, after exclusions): the robustness check. Reported alongside
   appropriate qualification that the combined set mixes in-sample-threshold events (frozen) with
   genuinely unseen events (extension).

The frozen set is never modified. The extension and combined sets are additions.

### Prior expectation (recorded before results are known)

Extension accuracy is expected to be **lower** than the frozen set's 65.3% (62/95), for two
reasons that apply before any result is seen:

1. **Threshold selection**: the deployed HOLD thresholds (+0.25/-0.05) were fitted on the frozen
   N=233 events. The extension events are genuinely unseen by that selection step. Any in-sample
   inflation in the frozen figure does not carry to the extension.
2. **Sector character**: the extension adds utilities (Duke Energy, ExxonMobil) and non-US names
   whose earnings dynamics may differ materially from the frozen set's sector mix.

This expectation is recorded so that the result — whether it confirms or contradicts it — can be
read against a stated prior rather than interpreted post hoc.

### Item C stated limitation (recorded before gathering begins)

Item C (four-arm section ablation) requires four separately scoreable document bundles per event:
full bundle, press release only, prepared remarks, and transcript Q&A. A yield analysis of the
93 candidate events from the human arm's workbook data shows:

- **29 of 93 events** had a transcript read by at least one human rater (Document column in
  Human_Data_Entry).
- **64 of 93 events** are press-release-only: the human arm read only the press release or full
  bundle where the bundle is a press release alone.

Item C can only be run on events where a transcript exists and can be sourced. The upper bound
is 29 events, and the actual count depends on which of those 29 transcripts are gatherable.
For the 64 press-release-only events, Item C reduces to a single arm and cannot produce a
meaningful four-arm comparison.

This is recorded as a pre-stated structural limitation of the extension's Item C, not a finding
to be reported after the fact. If fewer than 20 four-arm events are achievable, Item C will be
reported as infeasible for the extension and omitted from the extension-only results block.

---

## Amendment B — 2026-08-13 (written before gathering begins, after yield analysis)

**Context**: a yield analysis of the 93 candidate events was completed using the human arm's
realised returns in the workbook, before any document beyond the 7-event pilot was gathered or
scored. This amendment records the yield findings and the decisions taken in response.

### Yield analysis results (pre-gathering)

40 of 93 extension events breach the ±2% overnight band (43% yield), against 63.1% for the
frozen N=233. The low yield is concentrated:

- **Five companies account for 42 events and 2 graded events**: Duke Energy (13 events, 1
  graded, 8%), ExxonMobil (13 events, 1 graded, 8%), Costco (4 events, 0 graded, 0%), Chevron
  (4 events, 0 graded, 0%), Shell (4 events, 0 graded, 0%).
- If these five are excluded, the remaining 51 events yield 38/51 = 75%, comparable to the
  frozen set.
- High-yield companies (Datadog, eBay, Intel, Hermes, Shopify, Sony, Adobe, Home Depot,
  Freeport-McMoRan) yield 26–38 graded events from 33–51 events.

### Decision: gather all 93 events

All 93 events are gathered, for the following reasons, recorded before gathering begins:

1. **Coverage parity**: the extension's purpose is to give every human reading a model
   counterpart so the paired comparison uses the full human arm. Dropping low-yield companies
   on the basis of their returns would amend the selection rule after the yield analysis was
   known, which would be post hoc.
2. **Contributions beyond graded accuracy**: the 42 low-yield events still contribute to
   coverage accuracy (what the model calls when the stock barely moves), the decision-mix
   distribution (BUY/HOLD/SELL proportions), confusion matrices, and sector breakdowns. These
   are analytically meaningful even when the graded count is small.
3. **The original selection rule stands unamended**: all companies where the human arm has
   readings and the model arm has none. No company is excluded.

### Document standard

The gathering standard is: **press release plus transcript wherever a transcript can be
sourced**, matching the frozen corpus where 232 of 268 events carry a transcript. This ensures
that any accuracy difference between the frozen set and the extension isolates the sector
dimension rather than confounding it with document coverage. Presentations are gathered as a
third priority where available from the company's IR page.

### Items extended

Items A through E all extend to the full 93-event set. This is decided now, before any
extension event beyond the 7-event pilot is scored, so no item can be added or dropped on the
basis of what the results show. Item C runs on whichever events yield four separable document
arms under the same boundary rules as the frozen set; the frozen Item C result at N=119 remains
primary regardless of the extension count.

### Prior expectation (restated for this amendment)

Extension accuracy is expected to be **below the frozen 65.3% (62/95)**, because the deployed
HOLD thresholds (+0.25/-0.05) were fitted on the frozen set while the extension events are
genuinely unseen by that selection. This is stated before gathering begins and before any
extension result beyond the 7-event pilot (1 graded, 0 traded, no accuracy computable) is
known.

---

## Amendment C — 2026-08-13 (document coverage audit and like-for-like check, written before any extension event beyond the 7-event pilot is scored)

### The HEINY_FQ3_2025 question — resolved

A check was raised before scoring as to whether `HEINY_FQ3_2025` was an event where the human
arm read a transcript but the model arm would not have one. The workbook data resolves this:

- `HEINY_FQ3_2025`: Document column = **"Presentation"**, Section = **"All"** (single rater:
  Anna). This is Heineken's investor slide deck, not an earnings call transcript. **No mismatch:
  both arms lack a call transcript for this event**, and neither arm is disadvantaged.

### Actual like-for-like mismatches (human read transcript, model arm has no transcript)

Cross-referencing the workbook Document column against the manifests identified two confirmed
mismatches where the human arm explicitly read a transcript but the model arm will not have one:

- **COST_FQ4_2025**: David read Document="Transcript", Section="Outlook/Guidance". No files
  on disk; model manifest is press-release-only. **Genuine mismatch.** Transcript should be
  sourced before scoring; if unavailable, this event must be flagged as document-asymmetric
  and excluded from any paired human-vs-model comparison, while kept in the model arm's own
  figures.

- **COST_FQ1_2026**: David read Document="Transcript", Section="Transcript Q&A"; Meriem read
  Document="All". No files on disk; manifest is press-release-only. **Genuine mismatch**, same
  disposition as COST_FQ4_2025.

A third candidate (`RMS_FQ3_2025`, Hermes Q3) was initially also flagged, because the human arm
(Nigel) read Document="Transcript", Section="Transcript Q&A" and the original manifest had only
a press release. However, **the transcript file is on disk**
(`docs/hermes/CY2025-Q3/RMSP.XC_Q3_2025_Earnings_Call_Transcript.pdf`). The manifest has been
updated to reference it. `RMS_FQ3_2025` is **not a mismatch**: both arms will have the
transcript.

**Decision (recorded before scoring):** COST_FQ4_2025 and COST_FQ1_2026 will be excluded from
the paired human-vs-model comparison if transcripts cannot be sourced before scoring. They remain
in the model arm's own signal-distribution and decision-mix figures. This decision is made now,
before any result for these events is known, so it cannot be post hoc.

### Model arm document coverage across the 93 extension events

After fixing the Hermes manifest paths (files were on disk under the `RMSP.XC_` prefix) and
adding the Nestle FQ3 2024 transcript (file was on disk but manifest listed PR-only), the
corrected model arm document plan is:

| Company | Events | With transcript | PR-only | Notes |
|---|---|---|---|---|
| Adobe | 4 | 4 | 0 | Files on disk as .pdf; manifest uses .htm — **filename fix needed** |
| American Express | 4 | 4 | 0 | 2 transcript filenames have typos (EAXP_, AAXP_) — **fix needed** |
| Chevron | 4 | 4 | 0 | Files .pdf; manifest expects .htm — **filename fix needed** |
| Colgate-Palmolive | 4 | 0 | **4** | No transcript exists; human arm also PR-only. Like-for-like. |
| Costco | 4 | 1 | **3** | FQ3_2026 has transcript; FQ4/FQ1/FQ2 have no files on disk |
| Datadog | 4 | 4 | 0 | FQ3/FQ4/FQ1 transcripts on disk as .pdf; manifest expects .htm |
| Duke Energy | 13 | 13 | 0 | Transcripts named `_Earnings_Call_Transcript.htm`; manifest expects `_Transcript.htm` — **fix needed** |
| ExxonMobil | 13 | 13 | 0 | Same filename pattern as Duke Energy — **fix needed** |
| Freeport-McMoRan | 3 | 3 | 0 | FQ1 transcript has `FFCX_` typo — **fix needed** |
| Heineken | 4 | 0 | **4** | No transcript exists; human arm read Presentation. Like-for-like. |
| Hermes | 4 | 4 | 0 | All four transcripts on disk (RMSP.XC_ prefix). Manifest fixed. |
| Home Depot | 4 | 4 | 0 | Files .pdf; manifest expects .htm — **filename fix needed** |
| Intel | 4 | 4 | 0 | FQ1_2026 may be PR-only on disk (single file found); others OK |
| Mastercard | 4 | 4 | 0 | FQ2 transcript has `EMA_` prefix typo — **fix needed** |
| Nestle | 2 | 2 | 0 | FQ3_2024 transcript on disk; manifest updated to include it. |
| Shell | 4 | 4 | 0 | FQ4_2025 press release has `.pdf.pdf` double-extension — **fix needed** |
| Shopify | 3 | 3 | 0 | FQ1_2026 folder has a Q4_2025-labeled transcript — **verify** |
| Sony | 3 | 3 | 0 | All files on disk, OK |
| Union Pacific | 4 | 4 | 0 | **0 files on disk.** All 4 events ungathered. |
| eBay | 4 | 0 | **4** | Only press releases on disk; no transcripts gathered |
| **TOTAL (planned)** | **93** | **82** | **11** | After Hermes + Nestle manifest fixes |

**As of 2026-08-13, files on disk support:**
- 72 events with transcript (files present)
- 14 events PR-only (files present, no transcript on disk)
- 7 events with no files at all (Costco FQ4/FQ1/FQ2, Union Pacific all 4)

The 14 PR-only and 72 with-transcript figures count what exists at the time of this recording.
Several of the 72 have filename mismatches that will cause the pipeline to fail to find the file
unless the manifest paths or filenames are corrected before scoring. These are listed in the
"fix needed" column above and must be resolved before `run_reports.py` is invoked.

### Colgate-Palmolive and Heineken: confirmed PR-only, both arms

**Colgate-Palmolive (4 events)**: no earnings call transcript freely available. Human arm read
"Press Release Document" for all four events. Both arms on identical information set. Excluded
from Item C by document availability, not by choice. Recorded before any event scored.

**Heineken (4 events)**: no earnings call transcript freely available in English. Human arm read
Heineken's investor presentation (a slide deck, not a call transcript) for all four events
(Document = "Presentation"). Neither arm has a call transcript; both are on press-release /
investor-presentation content only. Excluded from Item C by document availability, not by choice.
Recorded before any event scored. The Heineken manifest was initially built with planned transcript
entries for FQ1 and FQ2 2024; those entries were removed on 2026-08-13 after confirming no free
transcript exists.

### Document coverage comparison: extension vs frozen set

| Set | With transcript | PR-only | Total |
|---|---|---|---|
| Frozen (N=268, manifested) | 231 (86.2%) | 37 (13.8%) | 268 |
| Extension (N=93, manifest plan post-fix) | 82 (88.2%) | 11 (11.8%) | 93 |
| Extension (files on disk today) | 72 (77.4%) | 21 (22.6%) | 93 |

The manifest plan (82/93 = 88.2%) is marginally better documented than the frozen set (86.2%)
and substantially better than the 86/14 split of Amendment C's earlier draft, which counted
Hermes FQ3 as PR-only before the on-disk transcript was discovered. The on-disk count (72/93)
is lower because filename mismatches and absent files (Costco, Union Pacific) prevent the
pipeline from locating documents it has been told to use. Resolving the filename fixes and
sourcing the 7 missing events would bring the on-disk count to 82/93 at most.

**Stated before scoring**: any accuracy difference between the extension and frozen sets cannot
be attributed to the model arm being worse-documented. The manifest plan is as rich as the frozen
corpus on the transcript/PR dimension, and richer than it if the outstanding filename fixes are
applied before scoring begins.

---

## Amendment D — 2026-08-13 (post-gathering audit, written before any extension event beyond the 7-event pilot is scored)

### Costco conditional exclusion lifted

Amendment C stated: "COST_FQ4_2025 and COST_FQ1_2026 will be excluded from the paired
human-vs-model comparison if transcripts cannot be sourced before scoring."

The transcripts **have been sourced** and are now on disk:
- `docs/costco/CY2025-Q4/COST_Q4_2025_Earnings_Call_Transcript.htm`
- `docs/costco/CY2026-Q1/COST_Q1_2026_Earnings_Call_Transcript.htm`
- `docs/costco/CY2026-Q2/COST_Q2_2026_Earnings_Call_Transcript.htm`

The conditional exclusion no longer applies. **COST_FQ4_2025, COST_FQ1_2026, and COST_FQ2_2026
are included in the paired human-vs-model comparison** on the same basis as all other events.
The manifest has been updated to reference both the press release and the transcript for each
of the three quarters.

This change is recorded before any Costco event is scored beyond the 7-event pilot (which
included only COST_FQ3_2026 and which yielded 0 traded events). No result for
COST_FQ4_2025, COST_FQ1_2026, or COST_FQ2_2026 is known at the time of this amendment.

### Shell human-arm mismatch: prepared remarks vs transcript

A post-gathering audit of the Shell workbook data against the Shell manifest identified a
**genuine like-for-like asymmetry** for two Shell events. The audit findings by quarter:

- **SHEL_FQ2_2025**: Human arm read Document="Financial Statement", Section="Financial Results"
  (1 rater). Model arm document: prepared remarks (scripted CEO/CFO monologue, no Q&A).
  The human arm read a structured financial document; the model arm has a scripted narrative.
  This is a document-type difference but not a transcript-vs-no-transcript mismatch.

- **SHEL_FQ3_2025**: Human arm read Document="Transcript", Section="Outlook/Guidance"
  (1 rater). Model arm document: prepared remarks only — no Q&A transcript sourced or
  available. **Genuine like-for-like mismatch**: the human arm read a transcript; the model
  arm will not have one.

- **SHEL_FQ4_2025**: Human arm read Document="Transcript", Section="Transcript Q&A"
  (1 rater). Model arm document: prepared remarks only. **Genuine like-for-like mismatch**,
  same as SHEL_FQ3_2025.

- **SHEL_FQ1_2026**: Human arm document not confirmed at time of this amendment. Model arm:
  prepared remarks.

Shell does not publish earnings call transcripts with open Q&A. The prepared remarks files
on disk (SHEL_QN_YYYY_Prepared_Remarks.pdf) are the only freely available document for each
quarter. The human arm raters for Q3/Q4 2025 appear to have accessed a transcript from a
commercial source not available to the model arm.

**Decision (recorded before any Shell event is scored beyond the 7-event pilot, which did not
include any Shell event):**

- SHEL_FQ3_2025 and SHEL_FQ4_2025 are **flagged as document-asymmetric**. They are kept in
  the model arm's own signal-distribution and decision-mix figures but **excluded from any
  paired human-vs-model accuracy comparison** for the same reason as the original Costco
  conditional exclusion: a rater who read a full Q&A transcript had access to materially
  different information than the model arm, and any accuracy difference cannot be attributed
  to model signal.

- SHEL_FQ2_2025 is a borderline case (financial statement vs prepared remarks, not
  transcript-vs-no-transcript). It is **retained in the paired comparison** but noted as
  having a document-type difference. This is recorded rather than used as grounds for exclusion
  because both arms received structured disclosure content from the same earnings event.

- SHEL_FQ1_2026 disposition will be confirmed once the human arm's workbook entry is verified.
  If the human rater read a transcript, the same exclusion applies as for Q3/Q4 2025.

This decision is made before any Shell scoring result is known, so it cannot be post hoc.

---

## Amendment E — 2026-08-13 (first verified document coverage, written before any extension event beyond the 7-event pilot is scored)

### The gathering verification script was never successfully run before this session

The script `experiments/verify_gathered_docs.py` was written to verify that every gathered
document contained the correct company name, matched the correct fiscal period, and — for
transcripts — included a Q&A section. Due to a variable scope bug (`qa_opened` referenced
before assignment on any non-transcript file), the script crashed on the first press release
encountered for each issuer. **No verification run completed before this session.** The bug
was fixed on 2026-08-13. The first successful run is the one whose results are recorded in
this amendment.

This is the third instance in this project of a check that was built, appeared to be in
force, and was never executed. The mechanism and full write-up appear in section (k) of
`workbook_correction_log_2026-08-13.md`.

### First confirmed verification results — all 20 companies

The verified run (2026-08-13, after bug fix and all manifest corrections) shows:

| Company | Expected | Found | FAIL | WARN | Status |
|---|---|---|---|---|---|
| Adobe | 8 | 8 | 0 | 0 | OK |
| American Express | 8 | 8 | 0 | 0 | OK |
| Chevron | 8 | 8 | 0 | 0 | OK |
| Colgate-Palmolive | 4 | 4 | 0 | 0 | OK |
| Costco | 8 | 8 | 0 | 0 | OK |
| Datadog | 7 | 7 | 0 | 0 | OK |
| Duke Energy | 26 | 26 | 0 | 0 | OK |
| eBay | 4 | 4 | 2 | 0 | FAIL (Q1/Q2 PRs) |
| ExxonMobil | 26 | 26 | 0 | 0 | OK |
| Freeport-McMoRan | 6 | 6 | 0 | 0 | OK |
| Heineken | 4 | 4 | 0 | 0 | OK |
| Hermes | 8 | 8 | 0 | 0 | OK |
| Home Depot | 8 | 8 | 0 | 0 | OK |
| Intel | 7 | 7 | 0 | 0 | OK |
| Mastercard | 8 | 8 | 0 | 0 | OK |
| Nestle | 4 | 4 | 0 | 0 | OK |
| Shell | 8 | 8 | 0 | 0 | OK |
| Shopify | 6 | 6 | 0 | 0 | OK |
| Sony | 6 | 6 | 0 | 0 | OK |
| Union Pacific | 8 | 8 | 0 | 0 | OK |
| **TOTAL** | **172** | **172** | **2** | **0** | |

Missing documents: **0**. The two FAIL entries are eBay FQ1_2025 and FQ2_2025 press releases,
documented below.

### Extension corpus matches the human arm event by event

The extension corpus in `docs/` is the same information set the human arm read, event by
event. Where a transcript is absent from `docs/`, it is because no free transcript could be
sourced, and the human arm read press-release-only for that event as well. The comparison
is therefore like-for-like on every event by construction.

**Final document split (93 events):**

| Coverage | Events | Companies |
|---|---|---|
| Press Release + Earnings Call Transcript | **75** | Adobe(4), AXP(4), CVX(4), COST(4), DDOG(3), DUK(13), XOM(13), FCX(3), RMS(4), HD(4), INTC(3), MA(4), NSRGY(2), SHOP(3), SONY(3), UNP(4) |
| Press Release + Prepared Remarks (no Q&A) | **4** | Shell(4) — scripted monologue only; see Amendment D for the like-for-like mismatch on SHEL_FQ3/FQ4_2025 |
| Press Release only | **14** | Colgate-Palmolive(4), Heineken(4), eBay(4), Datadog FQ2_2025(1), Intel FQ1_2026(1) |
| **Total** | **93** | |

PR-only events are excluded from Item C (four-arm section ablation) by document availability,
not by choice. This was pre-registered for Colgate-Palmolive and Heineken in Amendment C.
It now also applies to eBay (all 4 events), Datadog FQ2_2025, and Intel FQ1_2026 on the
same basis: no transcript could be sourced, and the human arm is also press-release-only for
those events.

**Named exceptions to full like-for-like parity:**

- **eBay FQ1_2025 and FQ2_2025**: press release files on disk are 35-page image-only PDFs
  with zero extractable text (likely eBay's earnings slide deck saved as a scan, not the
  EDGAR Exhibit 99.1 text document). These two files cannot be scored by the pipeline in
  their current state. The real EDGAR press releases exist (CIK 1065088) but have not been
  saved. **These are the only two documents in the extension corpus that exist and have not
  been correctly saved.** All other documents pass content verification. These events will
  be re-filed before scoring; if re-filing is not completed before the scoring deadline,
  EBAY_FQ1_2025 and EBAY_FQ2_2025 will be excluded from extension results with this note.

- **Shell FQ3_2025 and FQ4_2025**: human arm read transcript documents for these two events;
  model arm has prepared remarks only (see Amendment D). Excluded from paired comparison.

- **Heineken FQ3_2025**: human arm read Heineken's investor presentation (slide deck, not
  an earnings call transcript). Neither arm has a call transcript. This was noted in
  Amendment C and is not a mismatch.

### What the verify run confirmed that was previously unverified

Prior to this session, no document in the extension corpus had been checked for: (a) correct
company name in the document text, (b) fiscal period match between folder label and filename,
(c) presence of a Q&A section in files classified as earnings call transcripts. The fixes
made before and during this session — manifest filename corrections for 13 companies, Shell
file renames, Costco transcript additions, Union Pacific folder rename, eBay/Intel/Datadog
manifest de-listing of absent transcripts — were made without a working verification tool.
The results above are the first confirmed evidence that the corpus content is correct.
For the two eBay image PDFs, the content verification found the fault; it did not exist
before the first working run.

---

## Amendment F — 2026-08-13 (SHEL_FQ1_2026 disposition confirmed; eBay image PDF fix confirmed; RMS_FQ3_2025 date confirmed; written before any extension event is scored)

### SHEL_FQ1_2026 — included in paired comparison

Amendment D left SHEL_FQ1_2026's paired-comparison disposition open pending workbook verification. The workbook (`data/workbook/Master_Data_CORRECTED_2026-08-13.xlsx`, sheet `Human_Data_Entry`) has been read and the Shell entries are:

| Quarter | Human arm Document | Human arm Section | Rater | Paired comparison |
|---|---|---|---|---|
| Q2 2025 (SHEL_FQ2_2025) | Financial Statement | Financial Results | David | Included (Amendment D) |
| Q3 2025 (SHEL_FQ3_2025) | Transcript | Outlook/Guidance | David | **Excluded** (Amendment D) |
| Q4 2025 (SHEL_FQ4_2025) | Transcript | Transcript Q&A | David | **Excluded** (Amendment D) |
| Q1 2026 (SHEL_FQ1_2026) | All | All | David | **Included** (this amendment) |

SHEL_FQ1_2026 is labeled "All/All" in the Document and Section columns — not "Transcript". The criterion in Amendment D was "if the human rater read a transcript, the same exclusion applies as for Q3/Q4 2025." That criterion is not met. SHEL_FQ1_2026 is therefore **included in the paired comparison**. This is recorded before any SHEL_FQ1_2026 result is known.

### eBay image PDF fix confirmed

EBAY_FQ1_2025 and EBAY_FQ2_2025 have been re-saved from EDGAR Exhibit 99.1 as HTML and re-verified by `experiments/verify_gathered_docs.py`. All four eBay events now pass all checks (0 FAIL, 0 missing). Manifest updated from `.pdf` to `.htm` paths for all four events. The "named exception" recorded in Amendment E is now closed.

### RMS_FQ3_2025 date confirmed

A date conflict (Oct 22 vs Oct 24) was noted in the timing CSV. Resolved by reading the Hermes official IR calendar at `finance.hermes.com/en/calendar/` via Wayback Machine snapshot (captured 2025-10-14, eight days before the event). The page contains an explicit `datetime` attribute: `2025-10-22T06:00:00` with label "08.00am CEST", for the event titled "Third Quarter 2025 Revenue". **Confirmed date: 2025-10-22. Confirmed time: 06:00 UTC (08:00 CEST)**. The Oct 24 figure was from an investing.com aggregator and is incorrect. The timing CSV has been updated to reflect the confirmed values with this source.
