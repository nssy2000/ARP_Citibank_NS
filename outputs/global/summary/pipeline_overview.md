# The Earnings Analysis Pipeline: Method and Results

**Audience**: group members who have not worked on the code.  
**Date**: 2026-08-15.  
**Status**: all figures sourced from committed output files. Figures in this document were
verified and, where necessary, corrected during a robustness review conducted
2026-08-12 through 2026-08-14. Detailed records of every correction are in
`outputs/global/summary/retracted_findings_2026-08-12.md`,
`outputs/global/summary/workbook_correction_log_2026-08-13.md`, and the
`Corrections_Log` sheet of the group workbook
(`data/workbook/Master_Data_CORRECTED_2026-08-14.xlsx`).

---

## 1. Research question

Can a language model read a company's quarterly earnings disclosure and predict
whether the stock will rise or fall overnight? The pipeline takes press releases,
earnings call transcripts, and slide decks as input, asks a model to score each
quarter's earnings against the company's own prior guidance, converts that score
into a directional trade, and measures whether the trades are correct.

The question has a practical framing: the group acts as if it is trading the
overnight gap after each earnings release. Every prediction becomes a position,
every position is measured against the actual price move, and the full P&L
record is the evidence for or against the system.

---

## 2. Architecture

### 2.1 Document gathering and storage

Earnings materials are gathered manually from free sources: EDGAR for US
companies, company investor-relations pages for non-US companies. Each quarter's
documents are placed in `docs/<issuer>/CY<FY>-Q<FQ>/` where the folder name
records the fiscal period being reported. A manifest file
(`manifests/p2_<issuer>_reports.json`) lists every document for every quarter
and its type (press release, transcript, slide deck). Documents are gathered
before scoring and never changed afterwards.

### 2.2 Bundle assembly and the four scoring layers

For each quarter, the pipeline assembles a text bundle from that quarter's
documents. The bundle is then scored by up to four layers:

**Micro layer** (`report_pipeline.py`): The core layer. A language model
(DeepSeek) reads the full bundle and scores the quarter on a scale of −1 to +1,
anchoring on *change in forward guidance relative to the company's own prior
guidance*, not on whether the quarter beat consensus. A quarter that was solid
but left guidance unchanged scores near zero. This layer is the only one that
costs API calls.

**Macro layer** (`llm_macro.py`): The same model reads FOMC meeting minutes
and produces a macro sentiment score, scored once per meeting and reused for
every company reporting after that meeting. Captures broad monetary-policy
tailwinds or headwinds.

**News layer** (`llm_news.py`): Pre-earnings news digests — sourced from free
outlets before the release date — are scored to capture how stretched or
depressed market expectations were going in. Every source article is dated
strictly before the release date. This layer currently carries **zero blend
weight** and does not affect any P&L figure reported here.

**Quant layer** (`quant_layer.py`): A deterministic, no-LLM composite of price
momentum, EPS surprise, and macro numeric indicators. Also carries **zero blend
weight** and does not affect any P&L figure reported here.

### 2.3 Blending to a signal

The four layer scores are combined using a weighted sum. The deployed weights are
**micro 0.55, macro 0.45, news 0.0, quant 0.0** (fixed 2026-08-05;
source: `blend.py DEFAULT_WEIGHTS`). The blended score runs from −1 to +1.

Two thresholds convert the score to a call. The deployed thresholds are:

- **BUY** if blended score > +0.25  
- **SELL** if blended score < −0.05  
- **HOLD** otherwise  

These thresholds are asymmetric — the model is quicker to call SELL than BUY.
They were selected by optimising compounded return on the full N=233 dataset
(in-sample). This selection step carries an important qualification described
under Limitations below.

### 2.4 Grading a call

A call is graded only when the overnight price move clears the ±2% neutral band
(see section 3). BUY calls are correct if the stock rises more than 2%. SELL
calls are correct if it falls more than 2%. HOLD calls are never graded under the
selectivity convention; they are treated as wrong under the coverage convention.
Both conventions are explained in section 6.1.

---

## 3. Measurement conventions

### 3.1 Entry and exit

Every trade uses the same window: **enter at the close of the session before
the earnings release; exit at the open of the session on release day**. This is
the overnight gap that spans the announcement.

### 3.2 Pre-market vs after-hours reporters

The correct prior close depends on when the company released:

- **After-hours reporters** (news out after 4 pm on the release date): the
  prior close is the close *on* the release date. The next open is the following
  morning's open.

- **Pre-market reporters** (news out before 9:30 am on the release date): the
  prior close is the close of the session *before* the release date. The next
  open is the open on the release date itself.

This distinction matters because using the release-date close for a pre-market
reporter includes hours of post-announcement trading in the "entry" price,
understating the measured reaction. The project anchors every event to the EDGAR
8-K Item 2.02 filing timestamp to determine which rule applies. Using the
wrong rule for 82 pre-market events was the source of five retracted findings
(see `outputs/global/summary/retracted_findings_2026-08-12.md`).

### 3.3 The ±2% neutral band

Returns within ±2% of zero are classified FLAT and excluded from the accuracy
denominator under the selectivity convention. The band is pre-registered and
unchanged throughout the project. Its purpose is to focus accuracy measurement
on the events where the earnings reaction was large enough to trade meaningfully.

### 3.4 Cost assumption

All P&L figures deduct a round-trip transaction cost of **10 basis points**
(0.10% of position size). This is the deployed assumption (source: `backtest.py`
default, `Settings!B4` in the group workbook). Short-borrow cost is set to zero.
The breakeven round-trip cost at which the strategy becomes unprofitable — the
point where mean net per trade equals zero — is **196 basis points** on the
N=233 clean universe (source: `outputs/global/summary/ext9_cost_grid_n233.json`,
`breakeven_mean_net_per_trade_bps`). No externally-cited desk-cost estimate is
committed to this repository; any comparison to realistic transaction costs must
come from an external source.

---

## 4. The event universe

### 4.1 Scored and clean

**268 events** were scored across 69 phase-2 issuers spanning 2023–2026. Of
these, **233 form the clean universe** used for all primary findings.

### 4.2 Why 35 events are excluded

| Reason | Count |
|---|---|
| Worksheet contamination (human score visible to later raters) | 25 |
| Ticker misattribution (SPOT: wrong company in the scored bundle) | 1 |
| Release timing unresolved (cannot determine pre-market vs after-hours) | 9 |
| **Total excluded** | **35** |

The 25 worksheet-contaminated events disproportionately include high-weight
technology names (NVDA, AMD, TSLA, META, AMZN). The full exclusion record is in
`outputs/global/summary/effective_sample_funnel.md`.

### 4.3 The 93-event extension

On 2026-08-13, the model arm was extended to cover **93 events across 20
companies** that the human arm had read but the model had never scored. The
selection rule was: every company where human readings exist in the group
workbook but no model scoring existed in the frozen N=233 results. No property
of the events (sector, return, volatility) was used to select or exclude any
company. The selection rule and all exclusion criteria were registered in writing
before any document was gathered (source:
`outputs/global/summary/extension_preregistration_2026-08-13.md`).

The 20 companies are: Adobe (ADBE), American Express (AXP), Chevron (CVX),
Colgate-Palmolive (CL), Costco (COST), Datadog (DDOG), Duke Energy (DUK),
ExxonMobil (XOM), Freeport-McMoRan (FCX), Heineken (HEIA.AS), Hermès (RMSP.XC),
Home Depot (HD), Intel (INTC), Mastercard (MA), Nestlé (NSRGY), Shell (SHEL),
Shopify (SHOP), Sony (SONY), Union Pacific (UNP), and eBay (EBAY). 15 are
US-listed; 5 are non-US (Heineken, Hermès, Nestlé, Shell, Sony).

Extension results are reported separately from the frozen N=233 results and do
not alter any frozen figure.

---

## 5. What each item establishes (Items A–E)

**Item A — Return matrix**: overnight and multi-horizon returns (1, 3, 5, 10
trading days) for all scored events, anchored to the EDGAR release date. The
Spearman rank correlation between the model's blended score and the overnight
return is the primary threshold-independent result (rho = 0.236, p = 0.0003,
N=233; source: `outputs/global/summary/ext2_holding_curve.csv`). The correlation
decays monotonically across horizons, reaching rho = 0.058 (p = 0.380) at 10
days.

**Item B — Holding-period curve**: the cumulative P&L curve across traded events
at each horizon. Shows that the overnight window captures almost all the
measurable signal; multi-day holding dilutes returns and loses statistical
support (the bootstrap mean-net 90% confidence interval lower bound crosses zero
between the 3-day and 5-day windows;
source: `outputs/global/summary/ext2_holding_curve.csv`).

**Item C — Section ablation**: the same events scored three additional times
using progressively shorter document subsets (press release only, prepared
remarks only, Q&A transcript only) and compared to the full bundle. Establishes
the cost-efficiency trade-off: the press release alone at roughly 13,000 tokens
achieves 62.5% accuracy on its own graded set (35 of 56 HOLD-excluded graded
events, N=200 events; source:
`outputs/global/summary/section_ablation_cost_per_correct.csv`), versus 65.7%
for the full bundle at roughly 30,000 tokens (46/70 graded). Cost per correct
call: press release $0.029, full bundle $0.046. On the four-arm subset (N=119,
all four bundles scored), the full bundle wins by 6.8 percentage points
(p=0.055, n=66 paired events; source:
`outputs/global/summary/section_ablation_paired_diffs.csv`), driven by 17 events
the press release passes on entirely (HOLD).

**Item D — Baselines**: two word-based alternatives — a Loughran-McDonald
dictionary scorer and FinBERT — applied to the same document set using thresholds
fitted only on the earliest 20% of the dataset (dev split) and applied frozen to
the remaining 80% (eval split, N=186 events, 119 graded). On the frozen eval
split: LM 15.1% (18/119 graded correct), FinBERT 34.4% (41/119), deployed model
42.9% (51/119), majority-direction floor 54.6% (65/119); all figures under the
coverage convention (source: `outputs/global/summary/frontier_table.csv`). The
model leads both baselines but all three are below the majority-direction floor,
meaning that simply always predicting DOWN would have beaten any of them on the
coverage denominator.

**Item E — Walk-forward validation**: tests whether HOLD thresholds fitted on
one period of data hold up on later data. Applied to both the frozen N=233 set
and the combined N=326 set. Result: threshold refitting degenerates at both
sample sizes (see Limitations, section 7). The combined N=326 walk-forward
produces 37 trades and 17/25 graded correct (68.0%) with a mean net of +1.79%
and a 90% CI of [+0.12%, +3.49%] on the pooled out-of-sample windows
(source: `outputs/global/summary/item_e_combined_walkforward.json`). This is
directionally consistent but underpowered: the observed gap versus the floor
(+14.6 percentage points) is roughly half the minimum detectable effect.

---

## 6. Results

### 6.1 Two accuracy conventions — both must be reported

There are two ways to compute accuracy, and they give very different numbers
from the same data. Both must be cited together to give an honest picture.

**Selectivity accuracy (HOLD-excluded)**: denominator = events where the model
traded AND the overnight return was outside ±2%. The model's HOLD decisions are
not penalised. This answers "how often was the model right when it made a
directional bet on a large move?"

**Coverage accuracy (HOLD=wrong)**: denominator = all events where the overnight
return was outside ±2%, regardless of what the model called. HOLD decisions on
large moves count as wrong. This answers "what fraction of large overnight moves
did the model get right, including the ones it declined to trade?"

The reason both matter: a model that never trades would score 0% on coverage and
undefined on selectivity. Selectivity rewards caution; coverage penalises it.

### 6.2 Set A — Frozen N=233 primary results

Source: `outputs/global/summary/ext2_holding_curve.csv`,
`outputs/global/summary/item_e_walkforward.json`.

| Metric | Value | N |
|---|---|---|
| Events scored | 268 | — |
| Clean universe | 233 | — |
| Traded (BUY or SELL) | 146 | of 233 |
| Graded (|ret| > 2%) | 147 | of 233 |
| Graded and traded | 95 | of 233 |
| **Selectivity accuracy** | **65.3%** (62/95) | 95 |
| Selectivity floor (always-DOWN) | 54.7% (52/95) | 95 |
| Selectivity margin vs floor | +10.5pp, p=0.024 (MDE ±10.8pp) | 95 |
| **Coverage accuracy** | **42.2%** (62/147) | 147 |
| Coverage floor (always-DOWN) | 54.4% (80/147) | 147 |
| Coverage margin vs floor | −12.2pp (model is below floor) | 147 |
| Mean net per trade (overnight) | +1.862% | 146 |
| 90% bootstrap CI | [+0.984%, +2.756%] | 146 |
| Spearman rho (score vs return) | 0.236, p=0.0003 | 233 |
| Per-trade t-statistic | 3.43 | 146 |
| Per-trade information ratio | 0.284 | 146 |
| Breakeven transaction cost | 196 bps | 146 |

Source for t-statistic: `outputs/global/summary/per_trade_stats.csv`
(mean_net=+1.8617%, pstdev=6.554%, n=146, population standard deviation).

The model exceeds the majority-direction floor on selectivity (p=0.024) and
falls below it on coverage. Both are true simultaneously; they measure different
things.

### 6.3 Set B — Extension N=93 results

Source: `outputs/global/summary/backtest_equity_extension_2026_08_13.csv`,
`outputs/global/summary/finbert_extension_results.csv`.

| Metric | Value | N |
|---|---|---|
| Events scored | 93 | — |
| Traded | 32 | of 93 |
| Graded (|ret| > 2%) | 31 | of 93 |
| Graded and traded | 14 | of 93 |
| **Selectivity accuracy** | **71.4%** (10/14) | 14 |
| Selectivity floor (even split) | 50.0% (7/14) | 14 |
| **Coverage accuracy** | **32.3%** (10/31) | 31 |
| Coverage floor (majority-UP) | 51.6% (16/31) | 31 |
| Mean net per trade (overnight) | +1.216% | 32 |
| 90% bootstrap CI | [−0.212%, +2.707%] | 32 |
| Spearman rho (score vs return) | 0.272, p=0.008 | 93 |

The extension graded set is too small for most conclusions (n=14 graded and
traded). The CI on mean net includes zero. These figures are descriptive.

Baselines on the extension (coverage, n=31 graded):
LM 9.7% (3/31), FinBERT 38.7% (12/31), model 32.3% (10/31), floor 48.4% (15/31)
(sources: `outputs/global/summary/lm_baseline_extension_results.csv`,
`outputs/global/summary/finbert_extension_results.csv`). The model and FinBERT
reverse ordering versus Set A: in Set A the model leads FinBERT (42.9% vs 34.4%);
in Set B FinBERT leads the model (38.7% vs 32.3%). The mechanism is trade rate:
FinBERT traded 71% of extension events (mostly BUY); the model held on 67%.

### 6.4 Set C — Combined N=326

Source: `outputs/global/summary/item_e_combined_walkforward.json`.

| Metric | Value | N |
|---|---|---|
| Total events | 326 | — |
| In-sample selectivity (deployed thresholds) | 66.1% (72/109) | 109 graded+traded |
| In-sample mean net | +1.746% | 178 traded |
| Walk-forward OOS accuracy (accuracy objective) | 68.0% (17/25 graded) | 37 trades |
| Walk-forward OOS mean net | +1.79%, CI [+0.12%, +3.49%] (90%) | 37 trades |

The in-sample figures on N=326 use the same deployed thresholds that were fitted
on the frozen N=233. They are not out-of-sample results. The walk-forward OOS
figure is out-of-sample in the sense that held-out windows were not seen during
threshold fitting, but all 326 events were known before the analysis (see
Limitations).

### 6.5 Trader-facing cuts

**Conviction vs accuracy** (source: `outputs/global/summary/asymmetry_rank_correlation.csv`):
Score magnitude does not predict move size. Spearman rho between |blended score|
and |overnight return| is 0.111 (p=0.070, N=268). Conviction-weighted sizing
produces nominally higher total return (+1,272% vs +1,244%) but lower
risk-adjusted return (per-trade t-statistic 3.04 sized vs 3.58 flat, both on
N=268 pre-exclusion; note the N=233 clean-universe figure is 3.43 —
source: `per_trade_stats.csv`) and higher drawdown (41.4% vs 37.4%), with the
sizing improvement not significant (paired bootstrap on mean net per trade:
+0.10pp, CI [−0.38pp, +0.61pp], p=0.773;
source: `outputs/global/summary/ext4_conviction_sizing.csv`).

**Return distribution** (source: `outputs/global/summary/ext2_holding_curve.csv`):
Mean net per trade is +1.862% at overnight (N=146 trades), falling to +1.251%
at 1 day, +1.026% at 3 days, +0.846% at 5 days (CI lower bound crosses zero),
+0.686% at 10 days. The overnight window is where the effect is.

**Accuracy by realised move size**
(source: `outputs/global/summary/asymmetry_magnitude_bins.csv`): accuracy
increases with the size of the overnight move in both BUY and SELL groups.
The overall SELL recall (65.0%, 26/40 LLM committed events, p=0.040 vs 50%)
exceeds BUY recall (55.6%, 20/36, p=0.309). The human arm shows the same
asymmetry more strongly: SELL 73.9% (17/23, p=0.017), BUY 50.9% (27/53,
p=0.500). Source: `outputs/global/summary/human_vs_llm_statistics.csv`.

**Band sweep** (cost grid; source: `outputs/global/summary/ext9_cost_grid_n233.json`):
Mean net per trade at the deployed 10 bps cost is +1.862%. The strategy remains
profitable until round-trip costs reach 196 bps. Every cell of the 12-cell cost
grid (combinations of 10–50 bps round-trip and 0–20 bps entry slippage) is
positive (source: `outputs/global/summary/ext9_cost_grid.csv`).

---

## 7. Limitations

### 7.1 The effective graded sample is small

Under the selectivity convention, the primary accuracy figure rests on **95
graded and traded events** from the frozen set. The detection limit at N=95 is
roughly ±10.8 percentage points. The observed margin over the floor is +10.5pp —
almost exactly at the detection limit (source: `ext2_holding_curve.csv`). The
extension adds 14 graded and traded events (n=14), which is too small to draw
conclusions from independently.

On the coverage convention the denominator is 147, but the model is below the
floor on coverage, so coverage does not support a positive finding.

### 7.2 Almost nothing is testable at this sample size

The minimum detectable effect for most comparisons at these Ns is roughly ±10–20
percentage points. Observed margins smaller than that are consistent with both a
real effect and chance. The walk-forward test requires roughly N=400–500 events
to reach adequate power on the directional-accuracy objective
(source: `outputs/global/summary/surviving_findings.md`, extrapolation from
observed degeneracy at N=233 and N=326).

### 7.3 The threshold qualification

The HOLD thresholds (+0.25/−0.05) were selected by optimising compounded return
on the full N=233 dataset (PSR=0.0, permutation p=0.150). The 95-event graded
denominator is itself a product of this in-sample selection. Every figure that
depends on the HOLD threshold — selectivity accuracy, mean net per trade, the
graded N, and Item C per-arm accuracy — carries this qualification. The rank
correlation (rho=0.236) does not depend on any threshold and is the study's
primary result. Source: `outputs/global/summary/surviving_findings.md`.

### 7.4 The walk-forward degenerates at current N

The threshold selection procedure behind the deployed 65.3% cannot be executed
honestly at N=233 or N=326. The mean-net objective is structurally degenerate
and will not improve with more data. The directional-accuracy objective degenerates
in 2 of 4 windows at N=233 and 1 of 4 at N=326, and would require roughly
N=400–500 to reach non-degeneracy. Source:
`outputs/global/summary/item_e_combined_walkforward.json`,
`outputs/global/summary/surviving_findings.md`.

### 7.5 The two accuracy conventions and why both are required

Reporting only selectivity flatters the model (HOLD decisions are not penalised).
Reporting only coverage penalises it for a deliberate design choice (the asymmetric
threshold holds more than it trades). Both figures must be reported side by side,
with denominator and convention named on each.

### 7.6 The FLAT convention differential

The group workbook applies a ±2% band using percentage points (Setting B3 = 2.0).
The pipeline applies the same band as a decimal fraction (0.02). The two are
identical. Any formula that reads a percentage-form return (e.g. −4.4% stored
as −4.4 rather than −0.044) against this threshold will misclassify the event.
This class of error was found and corrected; see the Corrections_Log sheet in
the workbook.

### 7.7 Consistency runs exist for the frozen set only

The frozen N=233 set was scored with ensemble runs, producing per-event
consistency scores. The 93-event extension was not. Any claim about output
stability applies to the frozen set only.

### 7.8 The in-sample walk-forward figure is retrospective

The N=326 walk-forward result (68.0%, CI [+0.12%, +3.49%]) is retrospective:
all 326 events were seen before the analysis was run. It cannot be presented as
out-of-sample in the pre-registered sense. Source:
`outputs/global/summary/surviving_findings.md`.

---

## 8. Where to find every figure

| Topic | File |
|---|---|
| Primary accuracy and P&L (Set A) | `outputs/global/summary/ext2_holding_curve.csv` |
| Graded event counts, correct/wrong/flat | `outputs/global/summary/item_e_walkforward.json` |
| Extension P&L and rho (Set B) | `outputs/global/summary/backtest_equity_extension_2026_08_13.csv` |
| Set B grading, FinBERT signal, model signal | `outputs/global/summary/finbert_extension_results.csv` |
| Combined walk-forward (Set C) | `outputs/global/summary/item_e_combined_walkforward.json` |
| Comprehensive metric table | `outputs/global/summary/results_three_sets.csv` |
| Sector breakdowns | `outputs/global/summary/sector_breakdown_three_sets.csv` |
| Holding-period decay | `outputs/global/summary/ext2_holding_curve.csv` |
| Breakeven cost grid | `outputs/global/summary/ext9_cost_grid_n233.json` |
| Section ablation accuracy and cost | `outputs/global/summary/section_ablation_cost_per_correct.csv` |
| Section ablation paired test | `outputs/global/summary/section_ablation_paired_diffs.csv` |
| LM and FinBERT baselines (frozen eval) | `outputs/global/summary/frontier_table.csv` |
| FinBERT on extension | `outputs/global/summary/finbert_extension_results.csv` |
| LM on extension | `outputs/global/summary/lm_baseline_extension_results.csv` |
| Conviction sizing | `outputs/global/summary/ext4_conviction_sizing.csv` |
| Per-trade t-statistic and information ratio | `outputs/global/summary/per_trade_stats.csv` |
| Score vs move size (asymmetry) | `outputs/global/summary/asymmetry_rank_correlation.csv` |
| BUY/SELL recall gap | `outputs/global/summary/asymmetry_recall_gap_test.csv` |
| Human vs LLM comparison | `outputs/global/summary/human_vs_llm_statistics.csv` |
| Kappa (human vs model independence) | `outputs/global/summary/kappa_near_independence.csv` |
| Macro ablation | `outputs/global/summary/macro_ablation_summary.json` |
| Extension events and selection rule | `outputs/global/summary/extension_preregistration_2026-08-13.md` |
| Exclusion funnel | `outputs/global/summary/effective_sample_funnel.md` |
| Retracted findings | `outputs/global/summary/retracted_findings_2026-08-12.md` |
| Workbook price correction detail | `outputs/global/summary/workbook_correction_log_2026-08-13.md` |
| Surviving findings with full qualification | `outputs/global/summary/surviving_findings.md` |
| Asserted figures audit | `outputs/global/summary/asserted_figures_audit.md` |
| Group workbook | `data/workbook/Master_Data_CORRECTED_2026-08-14.xlsx` |

*End of document.*
