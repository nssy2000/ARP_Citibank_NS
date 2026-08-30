# Workbook Correction Log — 2026-08-13

**Scope**: `data/workbook/Master_Data_CORRECTED_2026-08-13.xlsx` and
`data/workbook/Master_Data_LOCKED_2026-08-13.xlsx`.  
**Author**: automated correction pass, 2026-08-13.  
**Audience**: group members who have not followed this session; passages are
intended to be lifted into a dissertation or team message verbatim. Every
figure carries its N, its definition, and its source file.

---

## (a) What the workbook looked like before

### Main pricing window (columns M–P)

The Human_Data_Entry sheet computed each rater's return from four cells:

| Column | Label | Content |
|--------|-------|---------|
| M | Prior Closing Date | The closing date used as the entry |
| N | Prior Close ($) | The closing price on that date |
| O | Next Opening Date | The date of the exit open |
| P | Next Day Open ($) | The opening price on that date |

Columns Q (Actual % Change), R (Actual Direction), S (Prediction Correct?),
T (Position), and U (Net P&L) were all formula-driven from M–P. The Summary,
Charts, and Efficiency sheets read from those same formula results. In the
original workbook, M was populated with the **close of report_date** and P
with the **next open after report_date**, uniformly for every event, regardless
of when the company actually released.

### The re-pricing block (columns AB–AK)

A second pricing block occupied columns AB–AK. Column AB recorded the rater's
stated basis for their price choice (for example, "release date + stated time",
"price signal — only this window shows an abnormal move"). Columns AC–AK held
the rater's re-derived dates and prices. **No formula in the sheet read this
block.** Q through U and every summary tab continued to read M–P. The re-priced
values were recorded and never applied.

### Extent of the mismatch

A cross-check comparing the corrected EDGAR closing dates against the live
column M found that **only 287 of 420 Human_Data_Entry rows agreed** on the
prior-close date. The remaining 133 rows were using a different session as
their entry.

---

## (b) What was wrong — two distinct problems

### Problem 1: Uniform window, wrong for pre-market reporters

The original scheme entered at the close of report_date and exited at the next
open. For **after-hours reporters** (company releases after 4 pm on report_date)
this is the correct window: the news becomes public after the close, so the
close of report_date is the last price before the announcement. For
**pre-market reporters** (company releases before 9:30 am on report_date) the
window is wrong: the close of report_date is already several hours *after* the
news was out. The correct entry for a pre-market release is the close of the
session *before* report_date — the last trade that occurred without knowledge
of the results.

Using the close of the release day for pre-market events overstates the
magnitude of the measured move and biases the return in an unpredictable
direction depending on how the stock traded during the day.

### Problem 2: Price-signal re-pricing selects on the outcome

Approximately 175 of the 420 re-priced rows (across all passes and raters)
used a basis of "price signal — only this window shows an abnormal move" or
a close variant. This selects the pricing window by observing which window
produced the larger or more abnormal move — an outcome-dependent choice.
Even if each individual row selects the mechanically correct window, the
aggregate procedure is not independent of the return magnitude: events with
large moves are more likely to have one window clearly dominant, and the
re-pricer consistently picks that window. This introduces a selection bias
toward large observed returns, regardless of whether the selected date is
the release date or not.

These two problems are independent. A row can be wrong on Problem 1 (uniform
window misses pre-market timing) and right on Problem 2 (rater used a
stated-time basis, not a price signal). The correction addresses Problem 1
directly and flags Problem 2 as a limitation that cannot be fully corrected
in retrospect.

---

## (c) What was done

### Release dates sourced per event

For each event in the LLM universe (N=268 phase-2 scored events), the EDGAR
8-K Item 2.02 filing date was already embedded in `returns_matrix.csv` as
`entry_date`. This column was established by the anchor correction on
2026-08-12 and serves as the authoritative release date. For non-US issuers
and human-only events not covered by EDGAR, the home-exchange announcement
date was used where documented by the rater.

### Timing rule applied per event

- **Pre-market release**: correct prior close = release_date − 1 business day;
  correct exit open = release_date open.
- **After-hours release**: correct prior close = release_date close;
  correct exit open = release_date + 1 business day open.

### Values written into M–P

The corrected closing date, closing price, opening date, and opening price were
written directly into columns M, N, O, and P so that all downstream formulas
(Q through U, Summary, Charts, Efficiency) would finally read the right window.

### Coverage

Of 420 Human_Data_Entry rows, **295 were corrected** (column BS = "Price Basis
Corrected" = YES). The remaining **125 rows were left on the original basis**
because no verified release date was available for those events. Each uncorrected
row carries the reason in column BT. The 295 corrected rows and the 125
uncorrected rows are mutually exclusive; the corrected subset is the one to
use for any quantitative human-arm result.

---

## (d) Corroboration result — headline of this log

**Of 128 documented-release-time first-rater rows** (rows where the rater
recorded an explicit release time or a documented public release moment as
their pricing basis, deduplicated to the first rater per event):

| Category | Count |
|----------|-------|
| No EDGAR record — incomparable | 33 |
| With EDGAR record | **95** |
| — of which: agree directly with EDGAR | 89 |
| — of which: European exchange-convention difference | 6 |
| — of which: rater error already corrected (PBC=YES) | 2 |
| — of which: genuine remaining error, fixed this session | **1** |

The **6 European-convention rows** (LVMH|2025|Q2, Lenovo|2026|Q3, Puma|2026|Q1,
Siemens|2025|Q4, Siemens|2026|Q1, Siemens|2026|Q2) show a 1-day offset because
the rater correctly used the European prior-close date while the EDGAR reference
uses the US SEC filing timestamp. These are not pricing errors.

The **2 rater errors already corrected** are Charles Schwab|2025|Q3 and
Charles Schwab|2025|Q4. Schwab releases after-hours. The rater used the session
before the release as their prior close (the pre-market convention, applied
incorrectly to an after-hours event). The main column M had already been corrected
to the release date (the correct prior close for an after-hours event) with
Price Basis Corrected = YES before this session. The Re-priced prior close
date column (AD) retains the rater's original wrong date as documentation.

The **1 genuine error** is described in section (g) below.

**After all corrections: all 95 documented-release-time rows with an EDGAR
baseline are either in direct agreement or a known exchange-convention
difference. The documented-release-time manual re-pricing method is sound
where an explicit release time was recorded and an EDGAR comparison is possible.**

Source: `outputs/global/summary/manual_repricing_reconciliation.csv`
(clean corroboration rate block, appended 2026-08-13).

---

## (e) Multi-session discrepancies found

The repricing cross-check identified four rows where the human prior-close date
was more than one session from the EDGAR-anchored date. All four used a
price-signal basis (Problem 2 above), not a documented-time basis.

| Event | Rater(s) | Human AD date | EDGAR date | Gap | Diagnosis |
|-------|----------|--------------|------------|-----|-----------|
| Bank of America\|2025\|Q2 | Abdul | 2025-07-14 | 2025-07-16 | 2 calendar days | Human prior-close 2 days before EDGAR entry_date; price-signal basis |
| JPMorgan\|2025\|Q1 | Nigel, Abdul | 2025-03-31 | 2025-04-11 | 11 calendar days | Human used fiscal quarter-end (March 31) rather than the actual release date (April 11) |
| Lowe's\|2026\|Q1 | Anna | 2025-05-20 | 2026-05-20 | 365 calendar days | Year typo: rater entered 2025 instead of 2026 |

The JPMorgan error (11-day gap, fiscal quarter-end used as the entry date) is
the most consequential: the fiscal quarter ends on 31 March but JPMorgan
reported Q1 2025 on 11 April 2025. None of these rows are in the 295-row
corrected subset (all have Price Basis Corrected ≠ YES), so they do not affect
any corrected-subset figures. They are flagged here because they represent
errors that were recorded in the re-pricing block but, since no formula read
that block, were never caught before this audit.

Source: `outputs/global/summary/manual_repricing_reconciliation.csv`,
multi-session disagree sections.

---

## (f) The two workbooks

### Master_Data_LOCKED_2026-08-13.xlsx

Holds the **original human prices and dates untouched**. The LLM arm in this
file was reverted to the old report_date anchor so that the entire file
reflects the pre-correction state. This is a historical record. It should not
be used to compute any figure cited in the dissertation; it exists so that the
before-state can be audited.

### Master_Data_CORRECTED_2026-08-13.xlsx

Holds **both arms on verified release dates**. The LLM arm uses the corrected
EDGAR release_date anchor throughout (all 268 events). The human arm has 295
of 420 rows corrected (Price Basis Corrected = YES), with 125 rows flagged as
uncorrected.

**Cross-arm consistency check**: of 289 events present in both sheets with
Price Basis Corrected = YES, **all 289 agree exactly** on both dates and both
prices (prior-close date, prior-close price, opening date, opening price), to
within one cent rounding tolerance. This was not true before the correction.
The human-vs-model comparison is defensible on those 289 events and not
defensible on the 125 uncorrected rows, which remain on the original
report_date basis.

---

## (g) The KHC sentinel — worked example

### What happened

`KHC_FQ1_2025` (Kraft Heinz, fiscal Q4 2025, reported 2026-02-10 pre-market)
had `next_day_open = 0.0` in the corrected LLM workbook export
(`workbook_llm_corrected.csv`). Zero was not a real price; it was a
missing-price sentinel written where the price fetch returned nothing.

The sentinel propagated through every downstream formula:

| Step | Result |
|------|--------|
| `next_day_open = 0.0`, `prior_close = 24.14` (old anchor) | Actual % Change = (0 − 24.14) / 24.14 = −100% |
| −100% return, but cell displayed as `0` in the CORRECTED export | Actual % Change = 0.0% |
| Direction formula on 0.0%  | Direction = FLAT |
| FLAT direction, decision = SELL | Prediction Correct? = NO |
| |ret| = 0% < 2% threshold | KHC excluded from selectivity denominator |

The FLAT direction caused KHC to be excluded from the selectivity formula,
giving 61/94 = 64.9% instead of the authoritative 62/95 = 65.3%.

A second consequence: because `next_day_open = 0.0` with a SELL decision would
produce a computed return of approximately +100% (short a stock that fell to
zero), had any cost-grid script read from the workbook CSV rather than from
`returns_matrix.csv`, it would have treated KHC as a near-100% profit on a
single trade. For N=233 with 146 traded events, that single spurious return
would inflate the mean net per trade by approximately +0.68 percentage points
(100% / 146), raising the implied breakeven transaction cost from 196.17 bps
to approximately 254 bps — an inflation of roughly one third. The cost-grid
script (`experiments/execution_cost_grid_n233.py`) explicitly avoided this by
reading `returns_matrix.csv` directly, but the sentinel remained in the
workbook until this session.

### Corrected values

Source: `returns_matrix.csv`, document_id = `KHC_FQ1_2025`.

| Field | Before (sentinel) | After (corrected) |
|-------|-------------------|-------------------|
| release_date | — | 2026-02-10 (pre-market; from EDGAR 8-K filing date) |
| Prior close date (M / closing_date) | 2026-02-11 (human); blank (LLM) | **2026-02-09** (session before release) |
| Prior close price (N / prior_close) | 24.14 (old anchor); 24.99 (human) | **24.90** (returns_matrix entry_close) |
| Opening date (O / opening_date) | 2026-02-12 (human); blank (LLM) | **2026-02-10** (release date open) |
| Next day open (P / next_day_open) | blank / 0.0 | **23.80** (= 24.9 × (1 − 0.044177)) |
| Actual % change | 0.0% | **−4.4177%** |
| Actual direction | FLAT | **DOWN** |
| Prediction correct? | NO | **YES** (SELL matched DOWN) |
| ret_overnight (returns_matrix) | — | **−0.0442** |

After the fix the LLM sheet formula reproduces **62/95 = 65.3%** exactly,
consistent with the authoritative figure from `item_e_walkforward.json`.
The human arm KHC row (Human_Data_Entry row 193, Meriem) had no decision
recorded (column J = blank), so Prediction Correct? remains blank; only
M, N, O, P, Q, R, and Price Basis Corrected were updated.

---

## (h) Caveats at full strength

### 1. 109 unique human events remain on the original price basis

Approximately 109 unique human events (roughly 121 Human_Data_Entry rows,
including multi-rater passes) remain on the original report_date price basis
because no verified EDGAR release date was sourced. These split into:

- **Human-only US issuers** (~81 rows): MetLife, Duke Energy, ExxonMobil,
  American Express, Chevron, Intel, Mastercard, Costco, Colgate-Palmolive,
  Datadog, eBay, Union Pacific, Home Depot, Adobe, Shopify, Freeport-McMoRan,
  Johnson & Johnson, Booking Holdings, Dell, UnitedHealth, Caterpillar.
  An EDGAR 8-K lookup is feasible for all of these but was not attempted.

- **Non-US issuers** (~20 rows): Shell, Heineken, Hermès, Allianz, Sony, Nestlé.
  No SEC filing exists; the home-exchange announcement date would need to be
  sourced from each exchange individually.

**Human-arm figures must be reported on the corrected 295-row subset, with the
full 420-row figure alongside and clearly labelled.** The 125 uncorrected rows
are knowingly on the original basis; treating them as equivalent to the
corrected rows would reintroduce the systematic timing error described in (b).

### 2. The LLM sheet holds all 268 events; N=233 requires an explicit filter

`LLM_Data_Entry` contains all 268 phase-2 scored events. The clean universe of
N=233 is defined by the **In Clean Universe** column (column BA): 233 rows read
YES, 35 read NO (25 worksheet contamination, 1 SPOT misattribution, 9 timing
unresolved). Any formula or pivot that reads from LLM_Data_Entry without
filtering on In Clean Universe = YES is computing on N=268 and will not
reproduce the N=233 figures quoted throughout the dissertation.

### 3. Formula-driven cells are unverified until opened in Excel and recalculated

The XLSX files were written by openpyxl. LibreOffice Calc does not evaluate
XLOOKUP, which is used in several helper columns (LLM Decision, LLM Correct?
in Human_Data_Entry; cross-tab lookups in Summary). Every formula-driven cell
should be treated as unverified until the file is opened in Microsoft Excel and
recalculated (Ctrl+Alt+F9). Values written as literals (including all M–P
corrections and In Clean Universe flags) are not formula-dependent and are
correct as written.

### 4. No externally-cited realistic desk cost exists in this repository

The only transaction-cost reference point committed to this repository is the
deployed assumption of 10 bps round-trip (CLAUDE.md, Model_Arm_Gap_Spec.md
line 18). The mean-net breakeven for the N=233 clean universe on the corrected
release-date anchor is **196.17 bps** (primary metric; `ext9_cost_grid_n233.json`,
`breakeven_mean_net_per_trade_bps`, source `returns_matrix.csv` ret_overnight).
No figure from Dr Rock or any comparable external cost estimate is committed
here. Any claim that the breakeven exceeds realistic trading costs must be
attributed to an external source supplied explicitly, or dropped.

---

## (i) Full list of changes — cell ranges and counts

### `data/workbook/Master_Data_CORRECTED_2026-08-13.xlsx`

| Sheet | What changed | Rows/cells affected |
|-------|-------------|---------------------|
| LLM_Data_Entry | KHC row 202 corrected: K(closing_date)→2026-02-09, L(prior_close)→24.9, M(opening_date)→2026-02-10, N(next_day_open)→23.80, P(actual_pct)→−4.4177, Q(direction)→DOWN, R(prediction_correct)→YES, T(net_pnl)→0.043177 | Row 202 |
| LLM_Data_Entry | Column BA (In Clean Universe): 233 YES, 35 NO, written as literals | Rows 3–270 (268 data rows) |
| LLM_Data_Entry | Column BB (Exclusion Reason): populated for 35 excluded rows; blank for 233 clean | Rows 3–270 |
| Human_Data_Entry | Column M (Prior Closing Date), N (Prior Close $), O (Next Opening Date), P (Next Day Open $) corrected to verified release-date-anchored values | 295 rows (Price Basis Corrected = YES) |
| Human_Data_Entry | Column BS (Price Basis Corrected): YES or NO for all 420 rows | All data rows |
| Human_Data_Entry | Column BT (Not Corrected Reason): populated for 125 uncorrected rows | 125 rows |
| Human_Data_Entry | KHC row 193 (Meriem, 2025 Q4): M→2026-02-09, N→24.9, O→2026-02-10, P→23.80, Q→−4.4177%, R→DOWN, AN→YES | Row 193 |
| Accuracy_Conventions | Chart floor note added at row 30 | Row 30 |
| Accuracy_Conventions | N=233 static section added (rows 78–89): coverage 62/147 = 42.2%, selectivity 62/95 = 65.3% | Rows 78–89 |
| Accuracy_Conventions | Row 88 reconciliation note: names KHC_FQ1_2025 as the event causing 61/94 vs 62/95, states it is resolved | Row 88 |
| Accuracy_Conventions | Human-arm coverage limitation note (rows 91–92): 109 unique events, 121 rows uncorrected, split by US/non-US | Rows 91–92 |
| Corrections_Log | 3 entries: KHC LLM fix (sentinel); exclusion columns added; KHC human row 193 fix | Rows 2–4 |
| Corrections_Log | Header added | Row 1 |

### `data/workbook/Master_Data_LOCKED_2026-08-13.xlsx`

| Sheet | What changed | Rows/cells affected |
|-------|-------------|---------------------|
| LLM_Data_Entry | KHC row 202 **left at old-anchor values** (L=24.14, N=23.64) as historical record | Row 202 unchanged |
| LLM_Data_Entry | Column BA (In Clean Universe): 233 YES, 35 NO | Rows 3–270 |
| LLM_Data_Entry | Column BB (Exclusion Reason) | Rows 3–270 |
| Accuracy_Conventions | Same chart note and N=233 static section as CORRECTED | Rows 30, 78–89, 91–92 |
| Corrections_Log | Same entries as CORRECTED | Rows 1–4 |

### `outputs/global/summary/workbook_llm_corrected.csv`

KHC_FQ1_2025 row corrected: prior_close 24.14→24.9, closing_date→2026-02-09,
next_day_open 0.0→23.80, opening_date→2026-02-10, actual_pct_change→−4.4177,
actual_direction→DOWN, prediction_correct→YES, net_pnl→0.043177,
release_date→2026-02-10, release_timing→pre_market,
release_date_source→returns_matrix.csv, document_date→2026-02-10.

### `outputs/global/summary/manual_repricing_reconciliation.csv`

New file, created this session. Contains:
- Pass 1 summary (all raters, all rows with AD date populated, N=400):
  243 agree with EDGAR, 37 classifiable disagrees (5+10+4+17+1=37), 121 no EDGAR record.
- Pass 2 summary (first rater per event, N=356):
  217 agree, 104 no EDGAR record, 17 listing/currency, 10 one-session afterhours,
  5 one-session premarket, 3 multi-session.
- Full row-level detail for all 400 rows with AD date populated.
- Multi-session disagree detail (4 rows: BAC, JPM×2, Lowe's).
- Clean corroboration rate block (appended 2026-08-13): 95/95 comparable
  documented-time rows correct or convention difference after corrections.

### `outputs/global/summary/ext9_cost_grid_n233.json`

New file, created this session by `experiments/execution_cost_grid_n233.py`.
Records breakeven transaction costs on corrected release-date anchor:

| Universe | Metric | Breakeven |
|----------|--------|-----------|
| N=268 (corrected anchor) | compounded total return = 0 (retired, order-dependent) | 186.12 bps |
| N=268 (corrected anchor) | mean net per trade = 0 **[PRIMARY]** | 207.34 bps |
| N=233 (clean, corrected anchor) | compounded total return = 0 (retired) | 175.33 bps |
| N=233 (clean, corrected anchor) | mean net per trade = 0 **[PRIMARY]** | **196.17 bps** |

Not in this table (different anchor, different price set, not comparable):
162.81 bps (ext9_cost_grid_summary.json, OLD report_date anchor, N=268,
compounded metric — superseded 2026-08-12).

### Unchanged files — confirmed current

| File | Status |
|------|--------|
| `outputs/global/summary/surviving_findings.md` | Figures unchanged; denominator counts added to several percentages (e.g. "(27/52)", "(96/171)") during today's session for clarity. All nine findings and their statistics are current as of the corrected anchor. |
| `outputs/global/summary/workbook_metrics.csv` | Unmodified since last commit. All figures are on the N=233 clean universe, corrected release-date anchor. Authoritative source: `ext2_holding_curve.csv`, `item_e_walkforward.json`, `returns_matrix.csv`. |
| `outputs/global/summary/frontier_table.csv` | "always-SELL" label corrected to "always-DOWN"; three-figure reconciliation block added. Data rows and numeric values unchanged. |

---

## (j) Ticker-identity faults — extension pre-scoring audit, 2026-08-13

### Category description

A ticker-identity fault occurs when the human arm and the model arm resolve a
company's price series from different underlying instruments, producing
plausible-looking but non-comparable return figures. The fault does not raise
an error: yfinance returns data for the wrong ticker silently, the prices are
numerically reasonable, and any downstream comparison proceeds as if the two
arms are on the same series. The 42–47% magnitude on the Heineken fault is the
most striking illustration: HEINY and HEIA.AS track the same underlying
company through the same events but differ by roughly half in absolute price
because one is a US ADR and the other is the EUR primary listing — yet both
would produce a valid overnight return if the earnings release moved the stock,
and a spot check of the return sign would not reveal the error.

The fault was found by cross-arm price verification: fetching yfinance data for
the manifest ticker on the exact dates in Human_Data_Entry columns M–P and
comparing the closing/opening prices within a 1.5% tolerance. Three instances
have been identified across the project:

### Instance 1 — MetLife (frozen N=233 set, prior session)

**Fault**: a ticker capitalisation or format difference caused the model arm
price lookup to resolve a different price series than the human arm for MetLife
events. The exact mechanism (e.g. `metlife` vs `MetLife`, `MET` vs an ADR
symbol) is not re-documented here; the fault was found and noted in a prior
session. MetLife events are in the frozen N=233 set, which is tagged
`model-arm-final-2026-08-13` and not modified.

**Magnitude**: 6 unpaired events. The fault was a ticker capitalisation or
format mismatch that prevented 6 MetLife events from pairing in the cross-arm
comparison — not a price divergence of a given percentage. The events were
unresolvable rather than mis-priced.

**Status**: noted as a pre-existing fault class. Not corrected in this log
(frozen set is immutable). Relevant to the write-up as the first documented
instance of this category.

### Instance 2 — Hermes (extension set, found 2026-08-13)

**Fault**: the gathering checklist used ticker `RMSP.XC` (Cboe Europe, CXE,
EUR) for Hermes event keys `RMS_FQ1_2025` through `RMS_FQ4_2025`. The manifest
was also initially set to `RMSP.XC`. The human arm's corrected M–P prices
(Master_Data_CORRECTED_2026-08-13.xlsx) match RMSP.XC at 0.00% on all 4
events; they do not cleanly match RMS.PA (Euronext Paris, 0.55–3.11%
difference across the 8 closing/opening prices, with the largest deviation
3.11% on the Q1 opening price).

**Resolution**: manifest and checklist set to `RMSP.XC` for cross-arm parity.
This decision was made before any event was scored (2026-08-13) and is a
pre-registered design choice, not a response to any result. The reasoning:
(1) the M–P verification shows the human arm is definitively on RMSP.XC —
0.00% deviation on all 8 values, vs 0.55–3.11% for RMS.PA; (2) a 3.11%
deviation against the ±2% grading band is large enough to move an event across
the graded/ungraded boundary — an event could appear graded in one arm and
ungraded in the other on identical underlying news; (3) cross-arm parity was
judged to outweigh venue quality. The decision is documented in the
`ticker_selection_note` field of `manifests/p2_hermes_reports.json`. A known
limitation is that both arms now use the Cboe Europe secondary venue (RMSP.XC)
rather than the Euronext Paris primary listing (RMS.PA). The timing
classification is unaffected (both venues open 09:00 CET).

**Magnitude**: largest price deviation between RMS.PA and RMSP.XC is 3.11%
(Q1 opening price: RMS.PA 2306 vs RMSP.XC/human-arm 2236.5). This is small
relative to the Heineken fault but non-trivial.

### Instance 3 — Heineken (extension set, found 2026-08-13)

**Fault**: the manifest had `ticker: "HEINY"` (US OTC ADR, OTCQX, USD).
The human arm's corrected M–P prices match `HEIA.AS` (Euronext Amsterdam,
AMS, EUR) at 0.00% on all 4 events (prior close and opening price, 8 values
total). `HEINY` prices on the same dates diverge from the human arm by
42.0–47.2% — a factor-of-two error explained by the ADR-to-primary-listing
gap (HEINY ≈ HEIA.AS / conversion ratio, but quoted in USD while HEIA.AS is
EUR). The workbook's `rep_listing` column confirms `HEIA.AS` was already known
as the re-priced listing.

**Resolution**: manifest ticker corrected to `HEIA.AS` (all 4 reports);
checklist ticker corrected to `HEIA.AS` (4 rows). Session-open in the timing
capture sheet updated from 09:30 ET (US OTC) to 09:00 CET (Euronext
Amsterdam). Document_ids `HEINY_FQ*` are unchanged (names, not price lookups).

**Magnitude**: 42–47% divergence. Had HEINY been used at scoring time, the
four Heineken events would have computed overnight returns from HEINY prices
against a human arm anchored to HEIA.AS prices, making the two arms
non-comparable on those events.

### Method and applicability

The cross-arm check fetches `yfinance.download(manifest_ticker, start, end,
auto_adjust=False)` for the M–P date range and compares closing/opening prices
within 1.5% tolerance. It is the same procedure that found 289/289 agreement
on the frozen N=233 corrected set. For the extension: 85/93 events MATCH; 4
Heineken events were MISMATCH (now fixed); 4 Hermes events are NO_MANIFEST_MATCH
because the checklist event_key `RMS_FQ*` did not align with the initial manifest
key `RMSP.XC_FQ*` (resolved by aligning both to `RMS_FQ*` with ticker `RMSP.XC`).
Nestle, Shell, and Sony all returned MATCH on their priced events.

**The three instances together constitute a category** in the methodology: silent
ticker-identity faults that produce numerically plausible but non-comparable
cross-arm returns. The pre-scoring check prevented all three from entering the
scored extension dataset undetected.

---

---

## (k) A third instance of the inoperative-check pattern — the gathering verification script

**Date recorded**: 2026-08-13.

### Category

This entry documents the third instance of a recurring failure pattern in this project: a
check or correction mechanism that was built, appeared to be in force, and was never
actually executed. The first two instances are documented in (a)–(b) above:

1. **PRE_MARKET_ISSUERS constant** (first instance): a set of tickers intended to apply a
   pre-market pricing correction was defined in `phase2/export_rows.py` but no code path
   in that file or any downstream script ever read it. The correction was asserted to be
   applied and was not.

2. **Manual re-pricing block** (second instance): re-derived dates and prices were recorded
   in Human_Data_Entry columns AB–AK by raters. No formula in the workbook read that block.
   Q–U and every summary tab continued to read the uncorrected M–P. The re-priced values
   were recorded and never applied — for 133 of 420 rows, this meant the pricing window was
   systematically wrong.

3. **`experiments/verify_gathered_docs.py`** (third instance, documented here): a script
   was written to verify that every gathered document contained the correct company name,
   matched the correct fiscal period, and — for transcripts — included an open Q&A section.
   The script appeared to be a working verification tool. It was never successfully executed.

### Mechanism

The bug was a variable scope error in `check_file()`. The variable `qa_opened` was assigned
only inside the branch `if fname_type == "Earnings Call Transcript":`. Outside that branch,
a dead-code block also referenced `qa_opened` — not in the Q&A check itself, but implicitly
in the structure of the function as written. In practice: the script's outer loop called
`check_file()` on every file in every issuer directory in alphabetical order. Every issuer
directory contains press release files. Press releases are encountered before transcripts
alphabetically. On the first press release in each issuer directory, `fname_type` is
`"Press Release"`, the `if fname_type == "Earnings Call Transcript":` branch is skipped,
and the script crashed with `UnboundLocalError: local variable 'qa_opened' referenced
before assignment`.

### Period inoperative

From the initial commit of the script to this session (2026-08-13). The script was never
repaired between writing and this session. Every call to the script — including any that
may have been attempted against the seven-event pilot (Colgate-Palmolive, Costco) — crashed
on the first press release encountered for the first issuer.

**No document in this project was verified through this script at any point prior to this
session.** This includes the seven-event pilot and all twenty extension companies. The first
successful completion of a full verification run is from this session (2026-08-13).

### Resolution

The bug was fixed in this session. The specific fix: `check_file()` was restructured so
that the Q&A check block — including the assignment of `qa_opened` — is entered only for
files classified as `Earnings Call Transcript`, and the variable is not referenced outside
that branch. A separate change downgraded the "no closing phrase in final 500 characters"
finding from WARN/FAIL to an informational NOTE, since many legitimate transcripts end with
language that does not match the pattern list. The company-name check was also widened from
the first 2000 characters to the full document, since several transcript formats place
disclaimers and boilerplate before the company name appears.

The first clean run — all 20 extension companies, 0 missing documents, 0 FAIL,
0 WARN — was completed immediately after the fix, in this session.

### Methodology observation

The three instances share a structure: in each case, a safeguard was created at a point in
the project when it appeared necessary, the mechanism was believed to be running, and a
later audit found it had never run. In two of the three instances the check was silent
(no error, no signal that it was not executing). In the third (this one) the script
crashed immediately on any real run, which means the silence was preserved by the crashes
not being investigated or logged.

The practical consequence for the extension corpus is that the first confirmed verification
of document coverage is from 2026-08-13. Prior gathering decisions were made without verified
coverage data. The verification results are documented in Amendment E of the extension
pre-registration (see `extension_preregistration_2026-08-13.md`).

---

## (l) Speed multiples computed on a placeholder with no committed source (2026-08-15)

**Category:** Figure with no computation behind it, published and quoted.

### Mechanism

The Efficiency sheet published two speed multiples comparing model wall-clock time to human
reading time:

- **212×** = 29.8 min (human full arm mean) / 8 s
- **118×** = 27.9 min (human pooled mean) / 14.31 s

The 8-second value has no source in any committed file. It does not appear in
`api_cost_ledger.csv`, any per-issuer result JSON (`run_meta` has no latency field), any
`batch_metadata.json`, or any summary CSV. It was used in the Efficiency sheet as a manual
entry with no documented origin.

The 14.31-second value cited alongside the 118× figure is a single anecdotal measurement
(the nearest JSONL value is `PEP_FQ1_2023` at 14.37 s), not a distributional figure.
Neither denominator represents the distribution of actual model latency.

### Period inoperative

Both multiples were present in the Efficiency sheet from the point it was built; their
precise introduction date is not recoverable from git history (the sheet is not committed).
No prior session flagged either figure as unverified.

### Resolution

Real per-call latency was recovered from `outputs/p2_*/logs/first_run_costs.jsonl` across
91 issuers (624 success calls). The committed source is
`outputs/global/summary/model_latency_2026-08-15.csv`.

**Corrected figures (IQR-based, vs human full arm mean 29.8 min = 1788 s):**

| Metric | Value |
| --- | --- |
| IQR of model latency | 12.95 s (Q1) – 17.31 s (Q3) |
| Honest speed range (per document) | **103× – 138×** |
| At model mean (15.92 s) | ~112× |
| Per correct call | ~65× (human 145.3 min; model 2.2 min) |

The 212× and 118× figures are superseded by these. The Efficiency sheet will be updated by
the user directly; this log records the source error.

---

*End of log.*
