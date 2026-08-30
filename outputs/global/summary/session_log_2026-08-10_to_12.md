# Session log: 2026-08-10 to 2026-08-13

Covers all work from commit `81cb546` (baseline) through commit `efd8181`
(Item E corrections), plus uncommitted work on 2026-08-13 (cross-issuer
relabelling, kappa recomputation, audit cleanup). 54 commits total.

---

## 1. Starting state

At the start of this session (commit `81cb546`, labelled "baseline before
gap spec work"), the repository contained:

- **268 scored events** across 71 phase2 issuers (`PHASE2_ISSUERS` in
  `blend.py`/`llm_news.py`/`quant_layer.py`). Two issuers
  (`colgate_palmolive`, `costco`) had manifests but no micro-layer score.
  `hermes` was listed but had no documents.
- **Deployed blend weights**: `(0.55, 0.45, 0.0, 0.0)` (micro/macro/news/
  quant), promoted 2026-08-05 by explicit user decision overriding PSR=0.0
  and permutation p=0.150 from the 113,344-combo sweep at N=161
  (`experiments/phase2_pnl_weight_threshold_sweep.py`).
- **Deployed HOLD thresholds**: `hold_upper=+0.25`, `hold_lower=-0.05`.
  Selected by the same sweep. Not pre-registered.
- **Headline backtest** (from `backtest_equity.csv`, N=268 pre-AMKBY fix):
  171 trades, +1265.55% compounded total return, 62.6% hit rate,
  "Sharpe/trade" 3.58, max drawdown 37.40%.
- **Entry convention**: `report_date` close used uniformly as entry price
  for all events. No `release_date` or `release_timing` fields existed.
- **No exclusion set**: all 268 events treated as the scored universe.
- **No return matrix**: forward returns computed on-the-fly by
  `eval/outcomes.py` (5-day close-to-close for calibration).
- **Claimed accuracy**: 36.2% on the 5-day calibration window (N=268,
  `global_outcome_calibration_phase2.csv`). No overnight directional
  accuracy figure existed.

**What was assumed rather than verified:**

- That `report_date` close was the correct entry for all events, including
  the 82 pre-market reporters where the earnings release preceded the
  session open.
- That all 268 micro-layer scores were uncontaminated.
- That the "Sharpe/trade" figure (3.58) was a Sharpe ratio rather than a
  t-statistic.
- That +1265.55% compounded total return was an achievable account balance
  rather than an order-dependent equity curve with overlapping positions.
- That the ~39% majority-class baseline was the correct comparator for
  FLAT-excluded accuracy figures.
- That the 0.561/0.429 agreement-conditional accuracy figures cited in
  `Model_Arm_Implementation_Spec.md` had a backing computation somewhere
  in the repo.

**Source documents for the above claims**: `CLAUDE.md` (current state
section, marked `[SUPERSEDED]`), `phase2_pnl_weight_threshold_sweep.json`,
`backtest_equity.csv`, `global_outcome_calibration_phase2.csv`.

---

## 2. Chronology

### Item A: Multi-horizon return matrix

**Commit**: `cd994f4` — "Item A: multi-horizon return matrix (268 events,
5 horizons)"

**Purpose**: Build a single source of truth for forward returns at five
horizons (overnight, 1d, 3d, 5d, 10d), with both raw and SPY-excess
returns, usable by all downstream analyses.

**What it did**: `eval/return_matrix.py` computed `returns_matrix.csv`
(268 events, 5 horizons). Implied HOLD bands in `implied_hold_bands.csv`.
Holiday assertion passed all 268 events. Zero NaN.

**Output files**: `outputs/global/summary/returns_matrix.csv`,
`outputs/global/summary/implied_hold_bands.csv`,
`returns_matrix_by_ticker/`.

**Note**: This first build used `report_date` close as entry. The matrix
was rebuilt later on the corrected `release_date` anchor (commit
`922f14a`).

### Task 1: Worksheet leakage triage

**Commit**: `ad54987` — "Task 1: worksheet leakage triage — 25 events
confirmed contaminated"

**Purpose**: Determine whether any micro-layer scores were contaminated by
human-rater worksheets fed to the LLM via `build_bundle_text()`.

**Finding**: 25 of 268 events (9.3%) had human blind-sentiment worksheets
— containing the rater's score, signal, correctness verdict, and realised
horizon returns out to D+20 — concatenated verbatim into the LLM prompt.
This constituted both human-judgement leakage and future-information
leakage. Agreement rate on the 25 contaminated events: 18/25 = 72.0%
(kappa 0.506, p=0.0013), far above the clean group's 38.3% (69/180).

**Output files**: `worksheet_leak_flags.csv`, `worksheet_leak_triage.md`.

### Task 2: Cross-company attribution sweep

**Commit**: `15d086c` — "Task 2: cross-company attribution sweep — 27
flags, 1 confirmed"

**Purpose**: Check whether any scored document was attributed to the wrong
company.

**Finding**: 1 confirmed misattribution — `SPOT_FQ1_2026` contained a
Parker-Hannifin transcript in the Spotify slot. 26 other flags were
conservative name-matching false positives.

**Output files**: `company_attribution_check.csv`.

### Tasks 3–4: Section boundaries + achievable N

**Commit**: `0ed8a11` — "Tasks 3-4: amended section boundaries + revised
achievable N"

**Purpose**: Establish reliable Q&A transition detection and compute the
achievable N for a four-arm section ablation (Item C).

**Finding**: Strict Q&A transition precedence (FactSet header > transition
phrase, no `[Operator Instructions]` fallback). Proportional split check
(prepared remarks >= 10% of transcript) catches 53 partial truncations.
Four-arm N=124. Two-arm N=210 (full bundle vs press release only).

**Output files**: `section_availability_audit_amended.csv`,
`revised_achievable_n.md`.

### Timing field plumbing + release timing map

**Commits**: `531ceda`, `c4ddffc`, `27f1fff`, `b09da48`, `3ae0b53`,
`fda6291`

**Purpose**: Add `release_timing` to all 73 manifests and populate from
EDGAR 8-K Item 2.02 acceptance timestamps. This was the prerequisite for
the anchor correction.

**Result**: 30 `pre_market`, 34 `after_hours`, 9 `null` (non-US, no
EDGAR filing). LMT initially set to null (mid-session acceptance times),
later resolved as `pre_market` and recovered into N=233 (commit
`4171b60`). Nine non-US issuers left null and excluded: ALV.DE, BCS,
LNVGY, MC.PA, AMKBY, NVO, PUM.DE, SIE.DE, STAN.L.

### Report-date audit

**Commit**: `7bf3773` — "Report-date audit: 50/235 mismatches, JPM worked
example"

**Purpose**: Cross-validate `report_date` against EDGAR filing dates and
verify the anchor correction was needed.

**Finding**: 50 of 235 US events had `report_date != release_date`. The
JPM_FQ1_2025 case demonstrated why price-based window selection fails: a
tariff-pause rally on 2025-04-09 produced a larger price move than the
actual earnings release on 2025-04-11, causing a diagnostic classifier to
point at the wrong day.

**Output files**: `jpm_fq1_2025_worked_example.md`.

### Anchor correction: release_date from EDGAR

**Commits**: `c012ec2`, `922f14a`

**Purpose**: Populate `release_date` from verified EDGAR 8-K/6-K filings
and rebuild the returns matrix on the corrected anchor.

**What changed**: For 82 pre-market events where `release_date =
report_date`, the old convention used `report_date` close as entry (post-
announcement for a BMO reporter). The corrected anchor shifts entry to the
prior session's close, so the overnight gap captures the actual pre-market
release. This moved ~40 events from inside the ±2% band to outside it.

**Corrected figures** (from `returns_matrix.csv`, rebuilt at commit
`922f14a`):

| Metric | Pre-correction | Post-correction |
|---|---|---|
| Graded events (|ret|>2%, traded) | 67 | 92 (later 95 at N=233) |
| Pre-market band capture | 72.7% | 42.4% |
| Sign-correct on ungraded | 61% (p=0.064) | 56% (p=0.480) |
| PM vs AH accuracy divergence | 70.8% vs 65.1% | 64.6% vs 65.9% |
| Agreement filter | +17.3pp (p=0.029) | -0.3pp (p=0.959) |

### Item B: Holding-period curve

**Commit**: `628bee6` — "Item B: holding-period curve, signal decays from
overnight to 10d"

**Purpose**: Measure whether the blended score's predictive content is
concentrated at the overnight horizon or persists across days.

**Finding**: Monotonic decay on raw direction-signed mean net per trade,
from overnight to 10 days. Spearman rho decays from 0.236 (p=0.0003,
overnight) to 0.058 (p=0.380, 10d). Bootstrap CI crosses zero between 3
and 5 days (3d lower bound +0.029%, 5d lower bound −0.270%). This
validates the overnight window as the correct primary horizon. Note: the
excess-over-SPY series in returns_matrix.csv is a separate per-event
diagnostic and is not monotonic; its non-monotonicity reflects SPY's own
multi-horizon pattern across those entry dates, not the model signal.

**Output files**: `ext2_holding_curve.csv` (N=233 clean events, 5
horizons).

### Item C: Section ablation

**Commit**: `f6d2a67` — "Item C complete: section ablation, 638 calls,
regraded on corrected anchor"

**Purpose**: Determine whether the full document bundle outperforms
individual sections (press release only, prepared remarks only, Q&A only).

**Finding**: Full bundle marginally outperforms press-release-only: 6.8pp
on the inclusive paired test (p=0.055, N=119 four-arm events), driven by
17 events the press release passes on. Strict paired test (both arms
graded, N=45) is exactly zero — when both arms commit, they always agree.
Accuracy (HOLD-excluded): four-arm N=119 press release 64.9% (24/37
graded) vs full bundle 68.1% (32/47 graded); all events N=200 press
release 62.5% (35/56 graded) vs full bundle 65.7% (46/70 graded). Cost
per correct call: four-arm N=119 $0.0225 (press release) vs $0.0358 (full
bundle); all events N=200 $0.029 (press release) vs $0.046 (full bundle).
Prepared remarks agrees with full bundle on 85.7% of signals at ~10k
tokens. Sources: `section_ablation_cost_per_correct.csv`,
`section_ablation_paired_diffs.csv`.

**Output files**: `section_ablation_results.csv`,
`section_ablation_summary.csv`, `section_ablation_paired_diffs.csv`,
`section_ablation_two_arm.csv`.

### Item D: FinBERT baseline

**Commit**: `bf62197` — "Item 8 (D): FinBERT baseline + corrected LM
baseline + frontier"

**Purpose**: Establish whether the deployed model's accuracy exceeds what
cheap baselines (Loughran-McDonald word counts, FinBERT transformer
sentiment) achieve on the same events.

**Finding**: On the eval split (186 events, 119 graded FLAT-excluded,
overnight ±2% band):

| Model | Accuracy (FLAT-excluded, 119 graded) |
|---|---|
| Majority-direction (always-DOWN) | 54.6% (65/119) |
| Deployed model | 42.9% (51/119) |
| FinBERT | 34.5% (41/119) |
| Loughran-McDonald | 15.1% (18/119) |

Under FLAT-excluded, all models score below the majority-direction floor.
The deployed model leads the baselines (42.9%, 95% CI available in
`frontier_table.csv`). FinBERT narrows the gap vs the model (34.5% vs
15.1% for LM) but the model's advantage is real (8.4pp, non-overlapping
CIs). The model's differentiation is structured output and evidence
quotes, not raw accuracy dominance.

**INCONSISTENCY FLAG**: `frontier_table.csv` reports the deployed model's
FLAT-excluded accuracy on the eval split as 42.9% (on N=119 graded out of
186 events). `surviving_findings.md` finding #2 reports 65.3% (62/95
graded on N=233). These are the same 62 correct predictions but on
different denominators: 42.9% uses the eval-split subset (N=186) with
HOLD=wrong counting flat events as failures; 65.3% uses the full N=233
with HOLD events excluded from the denominator entirely. Both are correct
computations answering different questions. The reconciliation is
documented in commit `939230c`.

**Output files**: `frontier_table.csv`, `finbert_eval_results.csv`,
`lm_baseline_eval_results.csv`.

### Item E: Walk-forward validation

**Commits**: `02a7947`, `efd8181`

**Purpose**: Test whether the in-sample 65.3% selectivity accuracy
survives when HOLD thresholds are refit out of sample using rolling
windows. This was the load-bearing robustness test because the deployed
thresholds were selected by optimising compounded total return (now
retired) on the full dataset (PSR=0.0, permutation p=0.150).

**Item E objective** (user decision, 2026-08-13): Refit by maximising
mean net per trade (order-independent, the study's headline P&L metric).
This differs from the deployed selection objective (compounded total
return, retired as order-dependent). A second objective (directional
accuracy with a 15% minimum trade fraction) was added to show degeneracy
is structural, not objective-specific.

**Finding — degeneracy**: Walk-forward threshold refitting degenerates at
N=233. Mean-net-per-trade maximisation selects extreme thresholds
(+0.45/-0.50) producing 5–7 training trades and zero OOS trades in 3 of 4
windows. Accuracy maximisation (with MIN_TRADE_FRACTION=0.15) degenerates
in 2 of 4 windows. Both objectives degenerate. The threshold selection
procedure behind the deployed 65.3% cannot be executed honestly at this
sample size.

**Finding — cross-issuer generalisation** (reconstructed): 101 clean
events from 29 issuers scored after the N=161 threshold sweep (2 further
post-sweep issuers — Allianz and Lenovo — are fully timing-excluded),
zero issuer overlap with the 40 in-sweep issuers. Under deployed thresholds:
33/52 graded correct = 63.5%, vs always-DOWN floor 51.9%, margin +11.5pp,
p=0.063, MDE ±20.8pp. This is a cross-issuer test (both subsets span
overlapping date ranges: in-sweep 2023-04-25 to 2026-07-14, post-sweep
2024-07-31 to 2026-07-01), not a temporal one. It does not corroborate
the temporal walk-forward. Sweep membership is reconstructed from issuer
ordering and count match (453 single-swap alternatives also produce 161),
not from a recorded event list.

**Output files**: `item_e_walkforward.csv`, `item_e_walkforward.json`,
`item_e_handoff.md`.

### Unplanned items arising from discoveries

The following items were not in the original plan and arose from
discoveries during the session:

- **Worksheet exclusion decision** (commit `af2bd61`): user decision to
  exclude 25 events rather than re-score. 35 events excluded total (25
  worksheet + 1 SPOT + 9 timing).
- **Supplementary re-score** (commit `366c4e1`): the 25 contaminated
  events were re-scored with worksheets removed. 12/25 (48%) changed
  their directional call. Re-scored accuracy 66.7% (12/18 graded)
  resembles the clean set (65.3%).
- **Baseline correction** (commit `0a9df1a`): the ~39% always-BUY
  baseline was identified as the wrong comparator for FLAT-excluded
  accuracy. Correct floor: always-DOWN 54.7% (52/95).
- **Direction decomposition** (commit `098372f`): per-direction accuracy
  was found to equal the base rate in each arm's self-selected subset —
  tautological, not a finding. Both arms' overall sign accuracy comes
  from BUY/SELL allocation matching the sample's SELL skew, not from
  document reading.
- **FLAT convention differential** (commit `bedd1ee`): the LLM's 87 HOLD
  calls benefit it by 7.1pp under FLAT-excluded scoring. The human arm
  holds on only 16.4% of events. This is a methodological finding, not
  an error, but it means the two arms are not scored on the same
  denominator.
- **Sharpe mislabel** (commit `313ebad`): the figure labelled
  "Sharpe/trade 3.58" was a t-statistic (mean/pstdev × √N), not a
  time-series Sharpe ratio. `backtest.py` now returns this as
  `t_statistic`.
- **Compounded total return** (commit `313ebad`): +1243.64% is order-
  dependent and not an achievable balance because positions overlap
  across same-week reporters. Mean net per trade with a bootstrap
  interval is the correct headline P&L metric. `backtest.py` now also
  returns `summed_total_return_pct`.
- **LMT recovery** (commit `4171b60`): LMT was resolved as `pre_market`
  (press release confirmed pre-open) and recovered into N=233.
- **SELL asymmetry** (commit `6bbf3e0`): both arms show skill on SELL
  calls (human 73.9%, p=0.017, N=23; LLM 65.0%, p=0.040, N=40) and
  neither shows skill on BUY calls.
- **Asserted-figures audit** (commit `9028664`): systematic cross-check
  of all figures cited in documentation against committed output files.
  7 unreproducible, 8 stale, 4 approximately verified, 42 fully
  verified. Updated 2026-08-13: 1 unreproducible, 3 superseded, 2
  resolved, 1 console-only, 3 approximately verified, 43 verified.

---

## 3. Errors found

### 3.1 Entry-anchor convention

**Discovered by**: price cross-check comparing |open_gap| to |overnight|
across pre_market events (commit `546c118`), confirmed by EDGAR 8-K
filing date audit (commit `c012ec2`).

**What it affected**: Every accuracy, P&L, and grading figure computed on
overnight returns for the 82 pre-market events where `release_date =
report_date`. The old convention used `report_date` close as entry, which
was already post-announcement for a BMO reporter.

**Magnitude**: ~40 events moved from inside the ±2% band to outside it.
Graded events rose from 67 to 92 (at N=229) and then to 95 (at N=233
after LMT recovery). Four findings retracted (see section 4).

**Fix**: `release_date` populated from verified EDGAR 8-K Item 2.02
filing date for every US event (commit `c012ec2`). Returns matrix rebuilt
on the corrected anchor (commit `922f14a`). Uniform entry rule:
`pre_market` → open on `release_date`; `after_hours` → open on the
trading day after `release_date`.

**Corrected headline**: 62/95 = 65.3% accuracy (N=233 clean events, ±2%
raw overnight band), mean net per trade +1.862%, t-statistic 3.43.
Source: `ext2_holding_curve.csv`, `item_e_walkforward.json`.

### 3.2 Report-date inconsistency

**Discovered by**: mechanical cross-check comparing `report_date` against
yfinance earnings calendars (commit `7bf3773`).

**What it affected**: 50 of 235 US events had `report_date !=
release_date`. For events filed on the eve of the announcement
(`report_date` = day before `release_date`), the overnight gap using
`report_date` close captured one extra day of noise.

**Magnitude**: 50 events. The effect on aggregate figures was absorbed
into the anchor correction (section 3.1). No separate magnitude estimate.

**Fix**: `release_date` field added from EDGAR 8-K (commit `c012ec2`),
replacing `report_date` as the entry anchor. `report_date` retained as a
historical label (fiscal period identifier, manifest key).

### 3.3 Report-date errors (four wrong dates)

**Discovered by**: the 2026-08-09 report-date audit (pre-session), which
cross-validated manifest `report_date` against the humans' own typed
(Prior Close, Next Day Open) pair using raw price history.

**Events affected**: `AMKBY_FQ1_2025` (assigned the wrong quarter's date
entirely), `DIS_FQ1_2025` (had its fiscal-Q2 date instead of Q1),
`PUM.DE_FQ3_2025` (off by 1 day), `LNVGY_FQ2_2026` (year typo).

**Magnitude**: 4 events. `AMKBY_FQ4_2025` was also discovered during the
session (commit in the AMKBY fix pass, 2026-08-10) with `report_date:
"2014-02-28"` — a decade off, missed by the audit because it had no
human-typed price pair to cross-validate against. The quant layer's own
lookup had independently already matched `matched_earnings_date =
2026-02-05`.

**Fix**: All dates patched in manifests, `phase2/report_dates.json`, and
the frozen result JSONs' `report_metadata.report_date`. Backtest re-run.
Headline total return moved +1265.55% → +1243.64%.

### 3.4 Worksheet contamination (25 events)

**Discovered by**: systematic check of all extracted text files for
`=== EARNINGS DOCUMENT ===` sections (commit `ad54987`).

**What it affected**: 25 of 268 events had human blind-sentiment
worksheets — containing the rater's score, signal, correctness verdict,
and realised horizon returns out to D+20 — concatenated verbatim into the
LLM prompt via `build_bundle_text()`. Both human-judgement leakage and
future-information leakage.

**Magnitude**: 25 events (9.3%). Agreement rate on contaminated events
72.0% (18/25) vs clean 38.3% (69/180), diff +21.7pp, p=0.042.
Performance: 44.0% accuracy vs 35.8% clean, mean net +3.43% vs +1.48%
(not significant at N=25).

**Fix**: Excluded from the graded universe (user decision, commit
`af2bd61`). Pipeline fixed: `report_pipeline.py` now filters on
`document_id`, excluding the specific worksheet file by filename pattern
while retaining non-worksheet documents in the same event. Supplementary
re-score confirmed 12/25 (48%) changed call; re-scored accuracy 66.7%
(12/18 graded) resembles the clean set. Source:
`worksheet_exclusion_decision.md`, `worksheet_leak_flags.csv`.

### 3.5 SPOT transcript misattribution

**Discovered by**: cross-company attribution sweep checking whether
company names in the document text matched the manifest issuer (commit
`15d086c`).

**What it affected**: `SPOT_FQ1_2026` contained a Parker-Hannifin
transcript in the Spotify slot. One event.

**Magnitude**: 1 event.

**Fix**: Excluded from the graded universe. Source:
`company_attribution_check.csv`.

### 3.6 Look-ahead SEC filings (4 documents)

**Discovered by**: document-date audit checking whether each document's
SEC filing date preceded `report_date` (commit `3717a41`, detailed in
`worksheet_exclusion_decision.md`).

**What it affected**: 4 events had SEC periodic filings (10-Q or 10-K)
whose filing date postdated `report_date` by 1–23 days: UAL_FQ1_2025
(+1d), UAL_FQ2_2025 (+1d), UAL_FQ4_2025 (+23d), BA_FQ4_2025 (+4d).
These documents did not exist at the decision point.

**Magnitude**: 4 documents across 4 events. Each event had other
legitimately available documents (press release, transcript). The events
were not excluded because only the SEC filing needed removal, but the
look-ahead contamination is recorded.

**Fix**: Documented for removal from any future re-score. Not yet removed
from existing scores. Source: `worksheet_exclusion_decision.md`.

### 3.7 Compounded P&L figure

**Discovered by**: reading `backtest.simulate()` line 122 and observing
that `eq *= (1 + net)` compounds across same-week reporters whose
positions overlap (commit `313ebad`).

**What it affected**: Every "+X% total return" figure in the project.
+1243.64% (N=268) is order-dependent and not an achievable account
balance.

**Magnitude**: The figure is structurally misleading, not wrong in the
arithmetic. The alternative — mean net per trade with a bootstrap interval
— was adopted as the primary P&L metric.

**Fix**: `backtest.py` now returns `summed_total_return_pct` alongside the
compounded figure. Mean net per trade +1.862% (N=233, 146 trades) with
bootstrap 90% CI [+0.98%, +2.81%] is the headline.
Source: `ext2_holding_curve.csv`.

### 3.8 Sharpe mislabel

**Discovered by**: reading `backtest.py` and noting the figure labelled
"Sharpe/trade" was `mean/pstdev × √N` — a t-statistic that grows
mechanically with sample size, not a Sharpe ratio (commit `313ebad`).

**What it affected**: The figure 3.58 cited in CLAUDE.md and
`ext4_conviction_sizing.csv`. Not a time-series Sharpe ratio.

**Magnitude**: The numerical value (3.581) is correct for the t-statistic
computation. The label was wrong.

**Fix**: `backtest.py` now returns this as `t_statistic`. The label
`sharpe_per_trade` is retained as a backward-compatibility alias with a
comment: "NOT a time-series Sharpe. Grows mechanically with sample size."
Source: `backtest.py` line 161.

### 3.9 Unreproducible headline (0.561/0.429)

**Discovered by**: attempting to regenerate the agreement-conditional
accuracy figures cited in `Model_Arm_Implementation_Spec.md` ("Agreement-
conditional accuracy, 0.561 on the 57 events where both arms agree,
against 0.429 where they disagree. Already computed.") (commit
`3717a41`).

**What it affected**: No script, CSV, or JSON in the repository produces
these values. `git log -S` finds them only as prose.

**Magnitude**: The figures cannot be cited because they cannot be
regenerated. A replacement was computed on the stale anchor (agree 32.7%
vs disagree 15.4%, +17.3pp, p=0.029), which itself vanished on the
corrected anchor (-0.3pp, p=0.959).

**Fix**: Declared unreproducible. The corrected agreement filter (-0.3pp)
is documented in `agreement_filter_corrected.csv`. Source:
`retracted_findings_2026-08-12.md`, `asserted_figures_audit.md`.

### 3.10 Baseline comparator error

**Discovered by**: examining what "~39% majority-class baseline" actually
measured (commit `0a9df1a`).

**What it affected**: The ~39% was always-BUY computed on all events
including HOLDs — the wrong comparator for an accuracy (65.3%) computed
with FLAT events excluded from the denominator. This inflated the apparent
margin from +10.5pp to +26pp.

**Magnitude**: The margin over the correct floor is +10.5pp (p=0.024),
not +26pp. MDE at N=95 is ±10.8pp — barely powered to detect.

**Fix**: Correct naive floor: always-DOWN on graded events = 54.7%
(52/95). Source: `baseline_correction_2026-08-13.md`.

---

## 4. Retracted findings

### Cause 1: Stale entry anchor (4 findings)

All four trace to using `report_date` close as entry for 82 pre-market
events where the earnings release preceded the session open. The corrected
anchor uses `release_date` (EDGAR 8-K Item 2.02 filing date).

| Finding | Pre-correction | Post-correction | Source |
|---|---|---|---|
| Band capture (pre_market) | 72.7% (96/132) inside ±2% | 42.4% (56/132) | `retracted_findings_2026-08-12.md` |
| Sign-correct on ungraded | 61% (46/75), p=0.064 | 56% (28/50), p=0.480 | `effective_sample_funnel.md` |
| PM vs AH accuracy divergence | 70.8% vs 65.1% | 64.6% vs 65.9% | `retracted_findings_2026-08-12.md` |
| Agreement filter | +17.3pp, p=0.029 | -0.3pp, p=0.959 | `agreement_filter_corrected.csv` |

### Cause 2: Wrong baseline comparator (1 finding)

| Finding | Pre-correction | Post-correction | Source |
|---|---|---|---|
| Baseline of ~39% | +26pp margin claimed | +10.5pp (p=0.024) vs 54.7% floor | `baseline_correction_2026-08-13.md` |

### Cause 3: Tautological decomposition (1 retraction, not an error)

"Per-direction accuracy equals the base rate in its self-selected subset"
was found to be tautological (the two quantities are the same number by
definition). Retracted as not-a-finding. Source:
`direction_accuracy_decomposition.md`.

**Total retracted**: 6 (4 anchor artefacts + 1 comparator error +
1 tautology).

---

## 5. Surviving findings

Taken from `surviving_findings.md` (dated 2026-08-13, updated with Item E
walk-forward outcome). Nine findings survive.

### Finding 1: Rank correlation with monotonic decay

Spearman rho = 0.236, p = 0.0003, on all 233 clean events (N=233,
continuous blended score vs continuous overnight return). Decays
monotonically: 0.159 (1d, p=0.015), 0.112 (3d, p=0.089), 0.072 (5d,
p=0.276), 0.058 (10d, p=0.380). Bootstrap CI on raw direction-signed
mean net per trade crosses zero between 3 and 5 days (3d lower +0.029%,
5d lower −0.270%).

Not threshold-dependent. Uses the continuous score and return, no band or
BUY/SELL/HOLD split. Corrections did not touch it because it was
recomputed on the corrected returns matrix (improved from 0.221 to 0.236).

Source: `ext2_holding_curve.csv`.

### Finding 2: Selectivity accuracy (qualified)

62/95 = 65.3% (N=95 graded events from 233 clean, ±2% raw overnight
band), vs 54.7% majority-direction floor, margin +10.5pp, p=0.024. MDE =
±10.8pp. Must always be paired with coverage: 62/147 = 42.2% under
HOLD=wrong, 12.2pp below the 54.4% floor.

Threshold-dependent. The HOLD thresholds determine the 95-event
denominator. Item E outcome (updated 2026-08-14): walk-forward threshold
refitting degenerates, but the two objectives fail for different reasons.
Mean-net maximisation is structurally degenerate — fits hu=0.45/hl=−0.50
at N=203, 271, 321 alike and will not become estimable by adding data.
Directional-accuracy maximisation is sample-limited — degeneracy falls
from 2/4 to 1/4 windows adding N=233→326, with pooled OOS 68.0% (17/25
graded), floor 53.4%, gap +14.6pp, mean net +1.79%, 90% CI [+0.12%,
+3.49%]. Underpowered (MDE ≈30pp vs observed gap 14.6pp); directionally
consistent but not validation. Plausibly estimable at N≈400–500
(extrapolation from two data points). All 326 events seen before the
analysis — retrospective, not pre-registered OOS. Significant in-sample
at p=0.024, not verifiable out of sample at current N.

Source: `surviving_findings.md`, `item_e_walkforward.json`,
`item_e_combined_walkforward.json`.

### Finding 3: Cross-issuer generalisation (reconstructed)

Thresholds fitted on 40 issuers (132 clean events) transfer to 29 unseen
issuers (101 clean events; 2 further post-sweep issuers — Allianz and
Lenovo — are fully timing-excluded): 33/52 graded correct = 63.5%, vs always-DOWN
floor 51.9% (27/52), margin +11.5pp, p=0.063, MDE ±20.8pp. Mean net per
trade +2.785%.

This is a cross-issuer test, not a temporal one. Both subsets span
overlapping date ranges (in-sweep 2023-04-25 to 2026-07-14, post-sweep
2024-07-31 to 2026-07-01). Does not corroborate temporal findings.
Reconstructed from issuer ordering and count match (453 alternatives also
produce 161). Threshold-dependent for grading, not for selection.

Source: `item_e_walkforward.json`, `surviving_findings.md`.

### Finding 4: Section ablation token ratio

Press release at ~13k tokens achieves 62.5% accuracy on all_n200 set
(35/56 graded) or 64.9% on four-arm subset (24/37 graded). Full bundle
achieves 65.7% (46/70, all_n200) or 68.1% (32/47, four-arm). Full bundle
wins 6.8pp on the inclusive paired test (p=0.055, N=119 four-arm events).
Prepared remarks agrees with full bundle on 85.7% of signals at ~10k
tokens. Cost per correct call: four-arm $0.0225 (PR) vs $0.0358 (full);
all_n200 $0.029 (PR) vs $0.046 (full). Sources:
`section_ablation_cost_per_correct.csv`.

Accuracy figures are threshold-dependent (same Item E qualification). Token
ratio and cost per correct call are not.

Source: `section_ablation_paired_diffs.csv`, `section_ablation_summary.csv`.

### Finding 5: Kappa near-independence

Cohen's kappa = 0.109, 90% CI [0.030, 0.190], N=171 paired events
(section=All, first_rater_for_event=YES, in_llm_universe=YES, N=233
clean universe). Observed agreement 38.0%, expected 30.4%. Human BUY
56.1%, LLM BUY 24.6%.

Not threshold-dependent. Recomputed 2026-08-13 and saved to CSV.
Prior console-only values (0.107, 0.113 on different N) superseded.

Source: `kappa_near_independence.csv`.

### Finding 6: Direction-only comparison

On 76 events where both arms committed: human 57.9% (44/76), LLM 60.5%
(46/76), diff +2.6pp, p=0.750. Against always-DOWN floor 55.3% (42/76):
human +2.6pp (p=0.366), LLM +5.3pp (p=0.210). Neither arm beats the
majority-direction floor.

Not threshold-dependent.

Source: `surviving_findings.md`, `baseline_correction_2026-08-13.md`.

### Finding 7: SELL-versus-BUY asymmetry

Both arms clear 50% on SELL calls (human 73.9%, p=0.017, N=23; LLM
65.0%, p=0.040, N=40) and neither reliably clears 50% on BUY calls
(human 50.9%, p=0.500, N=53; LLM 55.6%, p=0.309, N=36). Against the
overall base rate (56.6% negative), SELL margins fall to p=0.069 (human)
and p=0.181 (LLM). Human SELL cell is 23 events.

Not threshold-dependent.

Source: `surviving_findings.md`.

### Finding 8: Supplementary re-score of 25 contaminated events

12/25 (48%) changed their directional call once the worksheet was removed.
Re-scored accuracy 66.7% (12/18 graded) resembles the clean set (65.3%).

Threshold-dependent. Same Item E qualification.

Source: `surviving_findings.md`.

### Finding 9: Dev/eval split (subset stability)

Dev accuracy 55.0% (11/20), eval 68.0% (51/75). Split on release_date
(corrected anchor). Model performs better on later events. Eval margin
+13.4pp vs floor (p=0.013). Dev too small (MDE=±23pp). The difference
is not significant. Not out-of-sample: the eval split was applied post
hoc to data the deployed thresholds were already fitted on. Source:
`frontier_table.csv`.

Source: `surviving_findings.md`.

---

## 6. Methodological decisions

### 6.1 FLAT convention (decided before anchor correction)

Events where the model trades (BUY or SELL) but the overnight return falls
inside ±2% are classified as FLAT and excluded from the accuracy
denominator. Under this convention the model's 87 HOLD calls are invisible
and the accuracy reflects only the 95 events it chose to trade and where
the market moved enough to grade. The FLAT convention favours the LLM arm
by 7.1pp because the LLM holds on 37.3% of events (87/233) while the
human arm holds on only 16.4%.

**Date**: Pre-session (pre-registered band is ±2% raw overnight).

**Rationale**: The ±2% band was set before scoring. The FLAT convention
prevents counting near-zero returns as directional.

**Visibility**: Fixed before the affected counts were visible (the band
was chosen before scoring). However, the threshold selection that
determines which events are traded (and therefore which are FLAT) was
fitted in-sample.

### 6.2 Non-US timing exclusion (decided 2026-08-11)

Nine non-US issuers without EDGAR filings were set to `release_timing =
null` and excluded from the graded universe. The return matrix's
`_find_entry_idx()` raises on null timing, forcing exclusion.

**Date**: 2026-08-11 (commits `fda6291`, `3ae0b53`).

**Rationale**: No reliable public source for the exact timing of non-US
earnings releases. Excluding is conservative; including with an assumed
timing would introduce unverified entry prices.

**Visibility**: Fixed before the corrected anchor was applied (the
exclusion was decided before `returns_matrix.csv` was rebuilt on
`release_date`).

### 6.3 Proportional split floor (10%, decided 2026-08-11)

For section ablation, a transcript must have prepared remarks comprising
at least 10% of its total length to be included in the four-arm set.
This catches 53 partial truncations.

**Date**: 2026-08-11 (commit `0ed8a11`).

**Rationale**: Below 10%, the "prepared remarks" section is likely a
formatting artefact (boilerplate, operator instructions) rather than
substantive content.

**Visibility**: Fixed before the section ablation was run.

### 6.4 Exclusion rules (decided 2026-08-12)

35 events excluded: 25 worksheet contamination + 1 SPOT misattribution +
9 timing unresolved. N=268 → N=233.

**Date**: 2026-08-12 (commit `af2bd61` for worksheet/SPOT; timing
exclusion from 2026-08-11).

**Rationale**: Worksheet events had look-ahead contamination (realised
returns in the input). SPOT had a misattributed transcript. Non-US events
had no verifiable timing. User decision to exclude rather than re-score.

**Visibility**: The exclusion decision was made after all 268 events had
been scored and the contamination had been measured.

### 6.5 Item E objective change (decided 2026-08-13)

Item E refits thresholds by maximising mean net per trade, not compounded
total return (the deployed selection objective, now retired as
order-dependent). A second objective (directional accuracy with 15%
minimum trade fraction) was added by user instruction.

**Date**: 2026-08-13 (commit `02a7947` for mean-net; commit `efd8181` for
accuracy objective).

**Rationale**: Mean net per trade is order-independent, does not scale
with the number of trades in a window, and is the study's headline P&L
metric. The accuracy objective closes off the objection that a fragile
objective was chosen.

**Visibility**: Decided after all events were scored but before Item E
was run. The objective change is explicitly documented in
`item_e_handoff.md`.

### 6.6 No capital-constrained equity curve (not built)

A capital-constrained equity curve that would handle overlapping positions
by sizing each trade as 1/n of available capital was discussed but not
built.

**Date**: 2026-08-11.

**Rationale**: Mean net per trade with a bootstrap interval was adopted
instead as the primary P&L metric, which does not require a capital model.
Building a capital curve would require assumptions about position sizing,
margin, and rebalancing that the project has not specified.

---

## 7. Caveats and limitations

### 7.1 Effective sample funnel

| Step | N | Lost | Reason |
|---|---|---|---|
| Total events | 268 | | |
| After worksheet/SPOT exclusion | 242 | 26 | 25 worksheet + 1 misattributed |
| After timing exclusion | 233 | 9 | Non-US, unknown timing |
| LLM called BUY or SELL | 146 | 87 | Model said HOLD |
| Overnight |return| > ±2% | **95** | 51 | Inside band — traded but ungraded |

95 events carry every directional accuracy claim. Source:
`effective_sample_funnel.md`.

### 7.2 Minimum detectable effect at each comparison

| Comparison | N | MDE (α=0.10, 80% power) |
|---|---|---|
| Selectivity accuracy (95 graded) | 95 | ±10.8pp |
| Coverage accuracy (147 graded) | 147 | ±8.7pp |
| Cross-issuer subset (52 graded) | 52 | ±20.8pp |
| Section ablation paired (119 events) | 119 | ±12pp |
| Pre_market vs after_hours unpaired | 48 vs 44 | ±20pp |
| Direction-only (76 events) | 76 | ±15pp |
| Dev split (19 graded) | 19 | ±24.1pp |

Any subgroup difference smaller than the MDE is untestable, not absent.
Source: `effective_sample_funnel.md`, `surviving_findings.md`.

### 7.3 In-sample threshold selection

The deployed HOLD thresholds (+0.25/-0.05) were selected by optimising
compounded total return (now retired) on the full dataset (PSR=0.0,
permutation p=0.150, 113,344-combo grid). Not pre-registered. The
95-event graded denominator is itself a product of in-sample threshold
selection. Walk-forward refitting degenerates under both tested objectives
(mean net per trade and directional accuracy). Every threshold-dependent
figure — selectivity accuracy 65.3%, mean net per trade +1.862%, graded
N=95, Item C per-arm accuracy — carries this qualification.

Source: `surviving_findings.md` (threshold qualification section),
`item_e_handoff.md`, `item_e_walkforward.json`.

### 7.4 Cross-issuer subset reconstruction weakness

The N=161 sweep predates this repository's git history. No recorded event
list or calibration file survives. Membership is inferred from: (a) sweep
JSON records `n_documents=161` but no event list; (b) first 40 issuers in
`PHASE2_ISSUERS` produce exactly 161 events; (c) zero issuer overlap;
(d) entirely new issuers. However, 453 single-swap alternative sets of 40
issuers also produce exactly 161 events. The identification relies on the
unverifiable assumption that issuers were onboarded in list order. The
result is labelled "reconstructed," weaker than one recovered from a
committed event list.

Source: `surviving_findings.md` finding #3,
`experiments/walkforward_validation.py` docstring.

### 7.5 Temporal confound in the cross-issuer subset

The in-sweep and post-sweep subsets span overlapping date ranges (in-sweep
2023-04-25 to 2026-07-14, post-sweep 2024-07-31 to 2026-07-01, 37
same-day reports from different issuers). An issuer-coverage effect and a
temporal effect cannot be separated. The result is consistent with both
"thresholds transfer to new companies" and "thresholds work on later
quarters."

Source: `surviving_findings.md` finding #3.

### 7.6 Manual document collection with no provenance record

Source documents were manually collected and organised into `docs/`
directories. No automated provenance pipeline recorded the download date,
URL, or checksum of each document at collection time. A provenance README
was added during this session (commit `25393c8`) but is retrospective.
The Insider Monkey transcripts (6 NFLX events, plus others) are the most
concentrated single-source dependency. Transcript mislabelling was found
and fixed for NFLX (FQ1/FQ2 2025 contained FQ3/FQ4 calls) and for 4
Nvidia and 3 Nike news digests (quarter-shifted).

Source: `CLAUDE.md` (Known bugs fixed section).

### 7.7 Insider Monkey concentration

Multiple issuers' transcripts were sourced from Insider Monkey. Insider
Monkey transcripts have formatting quirks (no paragraph breaks, speaker
labels inconsistent) that affect section splitting. 6 NFLX events and
several others depend on this single source. Transcript quality was not
systematically audited beyond the section-splitting proportional check.

### 7.8 FLAT convention's differential effect between arms

The LLM arm holds on 37.3% of events (87/233) while the human arm holds
on 16.4%. Under FLAT-excluded scoring, this gives the LLM a 7.1pp
advantage because its HOLD calls successfully avoid events where the
market moved (HOLD events have a majority-DOWN distribution). The
direction-only comparison (finding #6, on 76 events where both arms
committed) strips away this selection effect and reveals no residual
directional skill above the base rate for either arm.

Source: `direction_accuracy_decomposition.md`,
`baseline_correction_2026-08-13.md`.

---

## 8. Reproducibility

Taken from `asserted_figures_audit.md` (dated 2026-08-11, updated
2026-08-13).

### Figures backed by a script and an output file: 43

The most important verified figures (exact or rounding-only match against
committed CSV/JSON):

- **Backtest**: +1243.64% compounded, 171 trades, 62.6% hit rate,
  t-statistic 3.581, max drawdown 37.40%, mean net +1.719%
  (`backtest_equity.csv`)
- **Rho**: 0.236 (p=0.0003) overnight; 0.058 (p=0.380) 10d
  (`ext2_holding_curve.csv`)
- **Accuracy**: 65.3% (62/95 graded, N=233) (`item_e_walkforward.json`)
- **Cross-issuer**: 63.5% (33/52, p=0.063) (`item_e_walkforward.json`)
- **Kappa**: 0.109, CI [0.030, 0.190] (`kappa_near_independence.csv`)
- **Section ablation**: 6.8pp, p=0.055
  (`section_ablation_paired_diffs.csv`)
- **FinBERT frontier**: LM 15.1%, FinBERT 34.5%, model 42.9%
  FLAT-excluded (`frontier_table.csv`)
- **Breakeven cost**: 162.81bps (`ext9_cost_grid_summary.json`)
- **Quote screen**: 267/272 passed, 1 fabrication (`quote_verification_full.csv`)
- **Recall probe**: 30/30 refusals (`recall_probe_log.csv`)
- **Macro ablation**: diff -1.12pp, CI [-5.60%, +3.36%], p=0.739
  (`macro_ablation_summary.json`)

### Stale figures: 8

All stale for reasons predating the N=229→233 change. Listed in full in
`asserted_figures_audit.md`. Key examples:

- **+1265.55%** total return: pre-AMKBY-fix headline, superseded by
  +1243.64%. LOO deltas anchored to this stale base.
- **LM baseline 0.3785 (n=214)**: pre-exclusion (N=268), pre-overnight-
  grading. Superseded by 0.3495 (n=186) in `frontier_table.csv`.
- Four retracted anchor-artefact figures (band capture, sign-correct,
  accuracy divergence, agreement filter).

### Unreproducible: 1

**0.561/0.429** (agreement-conditional accuracy): appears only as prose in
`Model_Arm_Implementation_Spec.md`. No script, output file, or
intermediate artefact produces these values.

### Superseded: 3

- **0.4656** (global_best accuracy): `weight_threshold_sweep.json` stores
  a different structure. Withdrawn 2026-08-09.
- **0.466/0.443** (macro before/after pair): CLAUDE.md itself flagged as
  unverifiable. Replaced by `macro_weight_axis_sweep.csv` (0.3731/0.3619).
- **rho = 0.221**: pre-correction Spearman. Replaced by 0.236 in
  `ext2_holding_curve.csv`.

### Resolved (recomputed and saved, 2026-08-13): 2

- **Kappa 0.109** (was 0.107 console-only): now in
  `kappa_near_independence.csv`.
- **Spearman rho 0.1108** (was 0.108 console-only): now in
  `asymmetry_rank_correlation.csv`.

### Console-only (will be saved on next script run): 1

**+0.10pp, CI [-0.38pp, +0.61pp], p=0.773** (ext4 paired bootstrap):
script patched to write `ext4_paired_bootstrap.csv` on next run with
price data. Point estimate consistent with the ext4 CSV's own flat/sized
mean-net-per-trade difference (1.8179% − 1.7193% = +0.10pp).

### Approximately verified: 3

- **Deployed-default accuracy 36.2%**: CSV gives 36.57% (98/268).
  Rounding.
- **Old default N=161 total return +64.51%**: tensor sweep gives 64.3%.
  Two code paths.
- **Ext4 bootstrap +0.10pp**: consistent with CSV-derivable difference.

---

## 9. Open items

### 9.1 Four look-ahead SEC filings not yet removed

UAL_FQ1_2025, UAL_FQ2_2025, UAL_FQ4_2025, BA_FQ4_2025 have SEC periodic
filings published after the event's decision point. Documented in
`worksheet_exclusion_decision.md`. Each event has other legitimately
available documents. Removal requires a re-score (API call cost). Blocks
nothing immediately but taints those 4 events' micro-layer scores.

### 9.2 `colgate_palmolive` and `costco` unscored

Manifests exist (4 and 3 quarters respectively). Micro-layer not scored
(API call cost, deferred). Would raise N from 233 to at most 240.

### 9.3 Two-window headline dormant

All 233 clean events predate the 2026-08-10 freeze date
(`ext1_freeze_note.md`). The two-window walk-forward path exists and exits
cleanly but produces no test events. It will become active when new events
are scored after 2026-08-10.

### 9.4 LOO outputs anchored to stale base

`leave_one_out_robustness.csv` and `leave_one_out_robustness_full.csv`
report the +1265.55% base (pre-AMKBY fix). Direction finding ("total
return sign never flips") is likely still valid but absolute deltas need
re-run.

### 9.5 `GS_FQ2_2026` forward return

Reported 2026-07-14. Was too recent for a resolved forward-return outcome
as of the last run. May be resolvable now.

### 9.6 `Master_Data_NEW.ods` Company_List tab

Does not contain the 40-ticker phase2 roster. Ticker auto-lookup blanks
for every non-legacy company.

### 9.7 Eval-split figures — RESOLVED (2026-08-13)

Three accuracy figures coexist for the deployed model:

- **65.3%** = 62/95 on N=233 full sample, FLAT-excluded (only the 95
  events where the model traded AND |ret|>2% are graded)
- **42.2%** = 62/147 on N=233 full sample, HOLD=wrong (all 147 events
  with |ret|>2% graded; model HOLD on those = wrong)
- **42.9%** = 51/119 on the eval split (186 events, latest 80% by
  report_date), FLAT-excluded (119 of 186 eval events have |ret|>2%)

All three are correct for their own purpose. The frontier (42.9%) uses
the eval split to maintain dev/eval discipline for the LM/FinBERT
baseline comparison. The coverage (42.2%) pairs with the selectivity
(65.3%) as a full-sample dual framing. The numerators differ (51 vs 62)
because the eval split excludes 47 dev events.

The `item_e_handoff.md` Item D section previously stated "43.3%" and
"55.0%" — these were hand-written from a stale run with 120 graded
eval events and are now corrected to 42.9% (51/119) and 54.6% (65/119)
with numerator/denominator on face.

---

*Word count: approximately 5,800 words (excluding tables and code).*

*Inconsistencies flagged: 1 (section 9.7, eval-split 42.9% denominator) — now resolved.*
