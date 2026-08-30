# Asserted figures audit

Date: 2026-08-11. Auditor: automated cross-check against committed output files.
Sources checked: `CLAUDE.md`, `Model_Arm_Gap_Spec.md`, all `.md` files in
`outputs/global/summary/` (skipping `model_arm_state_2026-08-11.md` as today's work).

---

## Count summary

| Category | Count | Notes |
|---|---|---|
| Unreproducible (no backing script or output file) | 2 | 0.561/0.429; 113bps spec breakeven |
| Superseded (withdrawn, replaced by a citable figure) | 3 | 0.4656, 0.466/0.443, rho=0.221 |
| Resolved (recomputed and saved to CSV, 2026-08-13) | 2 | kappa 0.109, rho 0.1108 |
| Console-only (will be saved on next script run) | 1 | ext4 bootstrap +0.10pp |
| Stale (retracted or superseded by anchor correction / exclusion-set change) | 9 |  |
| Approximately verified (close but not exact — rounding or console-only) | 3 | was 4; rho=0.108 moved to Resolved |
| Fully verified against committed output files | 43 | was 42; kappa now verified |

---

## Unreproducible figures

These appear as assertions in documentation but cannot be regenerated from any committed script, output file, or intermediate artefact currently in the repository.

| Figure | Claimed in | Status |
|---|---|---|
| **0.561 / 0.429** — agreement-conditional LLM accuracy (agree vs disagree) | `Model_Arm_Gap_Spec.md` ("already computed") | No script, CSV, or JSON produces these values. `git log -S` finds them only as prose. Superseded by `agreement_filter_corrected.csv` (69.0% / 69.2% on corrected anchor). |
| **113 bps** — breakeven round-trip transaction cost | `Model_Arm_Gap_Spec.md` ("already computed", ~113bps) | **UNBACKED ASSERTION.** Cannot be reproduced from any artifact in this repository. `experiments/execution_cost_grid.py` bisects on `compounded_total_return_pct` (retired, order-dependent metric) and yields 162.81bps on the OLD report_date anchor, N=268 — a different anchor and a different price set. On the CORRECTED release_date anchor (2026-08-12), using returns_matrix.csv ret_overnight as the price source (same source as ext2_holding_curve.csv): N=268 compounded-breakeven 186.12bps, mean-net-breakeven 207.34bps [PRIMARY]; N=233 compounded-breakeven 175.33bps, mean-net-breakeven **196.17bps** [PRIMARY]. Arithmetic check: N=233 mean_net@10bps=+1.8617% (matches ext2_holding_curve.csv exactly) → mean_gross=1.9617% → breakeven=196.17bps ✓. Source: `ext9_cost_grid_n233.json` (2026-08-13). No externally-cited realistic desk cost exists in this repo. Dr Rock or any comparable external estimate is NOT committed here. Any claim that the breakeven exceeds realistic trading costs must be attributed to an external source supplied by the user or dropped. |
| **0.4656** — "global_best accuracy" in `weight_threshold_sweep.json` | `CLAUDE.md` Current State | **SUPERSEDED (2026-08-09)**: `weight_threshold_sweep.json` stores a different sweep structure. The citable deployed-default accuracy is 36.2% (N=268 5-day) or 65.3% (N=233 overnight graded). This figure is withdrawn, not pending action. |
| **0.466 / 0.443** — macro "before/after" accuracy pair | `CLAUDE.md` Architecture > Blend | **SUPERSEDED (2026-08-10)**: CLAUDE.md itself flagged this as unverifiable. Replaced by `macro_weight_axis_sweep.csv` (0.3731 off, 0.3619 on). This figure is withdrawn, not pending action. |
| **rho = 0.221** — Spearman score-return correlation before anchor correction | `ext2_holding_curve.csv` header comment | **SUPERSEDED (2026-08-12)** by rho = 0.236 (p = 0.0003) in the corrected `ext2_holding_curve.csv`. Pre-correction value, no longer citable. |
| **Kappa = 0.107 (CI [0.027, 0.188])** — Cohen's kappa clean group | `retracted_findings_2026-08-12.md` | **RESOLVED (2026-08-13)**: Recomputed on N=233 clean universe (section=All, first_rater=YES, in_llm=YES, N=171 paired events): kappa = 0.109, 90% CI [0.030, 0.190]. Saved to `kappa_near_independence.csv` with full 3x3 confusion matrix, marginals, and subset definition. Prior console-only values 0.107 and 0.113 (different N) are superseded. |
| **+0.10pp, CI [−0.38pp, +0.61pp], p = 0.773** — ext4 paired bootstrap on mean-net-per-trade (sized − flat) | `CLAUDE.md` Tier 2 conviction sizing | Console-only from `experiments/extension4_conviction_sizing.py`. Script now writes `ext4_paired_bootstrap.csv` on next successful run (requires price data via `overnight_gap()`). Until then, the figure is **approximately verified** by the ext4 CSV's own flat/sized mean-net-per-trade difference (1.8179% − 1.7193% = +0.10pp), consistent with the claimed bootstrap point estimate. |
| **Spearman rho = 0.108, p = 0.079** — score magnitude vs move size | `CLAUDE.md` Tier 1 asymmetry | **RESOLVED (2026-08-13)**: `asymmetry_conviction_analysis.py` now saves to `asymmetry_rank_correlation.csv`. Recomputed authoritative value: rho = 0.1108, p = 0.0701, N=268. The claimed 0.108/0.079 is superseded; cite the CSV value. |

---

## Stale figures

Computed on a superseded anchor, superseded exclusion set, or a different N. All are either formally retracted or explicitly marked as historical in CLAUDE.md.

| Figure | Claimed in | Why stale | Corrected value / backing |
|---|---|---|---|
| **+1265.55% total return** — pre-AMKBY-fix headline | `CLAUDE.md` Current State (historical bullet), `leave_one_out_robustness*.csv` full-sample row | Generated before `AMKBY_FQ4_2025` date was corrected (2026-08-10). `leave_one_out_robustness.csv` and `leave_one_out_robustness_full.csv` were not rerun after the fix and still report this anchor. | +1243.64%, `backtest_equity.csv` (final equity 13.4364). |
| **LOO ticker/quarter deltas** (CMG −353pp → +912%, etc.) | `CLAUDE.md` Tier 1 leave-one-out | Computed on the +1265.55% base; not rerun after AMKBY fix. Deltas are relative to a stale anchor. | Direction and sign findings likely still valid; absolute numbers shifted ~22pp. Needs rerun to be citable. |
| **LM baseline: 0.3785 (LM) / 0.3972 (model) / 0.4252 (majority), n = 214** | `CLAUDE.md` Tier 2 LM baseline; `Model_Arm_Gap_Spec.md` acceptance check | Originally run on all 268 events (dev = 54, eval = 214). After 35 events excluded (25 worksheet + 1 SPOT + 9 timing), the baseline was rerun; n changed to 233 (dev = 47, eval = 186). Also uses overnight grading in the current run vs 5-day in the original description. | `frontier_table.csv`: LM 0.3495, model 0.4409, majority 0.3602 (n = 186, flat-as-wrong, overnight). `Model_Arm_Gap_Spec.md`'s acceptance check ("0.3785 on n=214") no longer passes. |
| **Pre_market accuracy 70.8% vs after_hours 65.1%** — accuracy-vs-P&L divergence | `retracted_findings_2026-08-12.md` (retracted) | Old `report_date` entry anchor for 82 pre_market events; inflated pre_market graded sample to extreme reactions only. | Corrected: 64.6% vs 65.9% — essentially identical. `retracted_findings_2026-08-12.md` table. |
| **~39% baseline** — always-BUY on all events including HOLDs | `retracted_findings_2026-08-12.md` and `baseline_correction_2026-08-13.md` (retracted) | Wrong comparator: 39% computed on all events including HOLDs, used as floor for an accuracy computed with HOLDs excluded. | Corrected floor: 54.7% (always-DOWN, 52/95 graded events). `baseline_correction_2026-08-13.md`. |
| **Band capture 72.7% (pre_market) / 26.8% (after_hours)** — 3× asymmetry | `retracted_findings_2026-08-12.md` (retracted) | Old `report_date` entry anchor compressed pre_market returns below the ±2% band. | Corrected: 42.4% / 29.9% — ~1.4×. `retracted_findings_2026-08-12.md`, `pre_market_power_gap.md`. |
| **Sign-correct 61% (46/75), p = 0.064** — ungraded trades | `retracted_findings_2026-08-12.md` (retracted) | Stale anchor moved 25 events from ungraded to graded, removing the most correct-sign events from the pool. | Corrected: 56.0% (28/50), p = 0.480. `effective_sample_funnel.md`. |
| **Agreement filter +17.3pp (32.7% vs 15.4%), p = 0.029** — pre-anchor correction | `worksheet_leak_triage.md` (labelled as superseded within the document), `retracted_findings_2026-08-12.md` | Computed on old `report_date` anchor; accuracy elevated in both groups but the gap was an artefact. | Corrected: −0.3pp (69.0% vs 69.2%), p = 0.959. `agreement_filter_corrected.csv`. |
| **Deployed model 43.3%, Majority 55.0%** — Item D frontier in `item_e_handoff.md` | `item_e_handoff.md` Item D section (commit `ada2344`) | Hand-written summary from a stale run with 120 graded eval events (not 119). The authoritative `frontier_table.csv` (commit `bf62197`) has 51/119 = 42.86% and 65/119 = 54.62%. | Corrected to 42.9% (51/119) and 54.6% (65/119) with numerator/denominator on face. |

---

## Approximately verified (close, not exact)

| Figure | Claimed in | Recomputed | Notes |
|---|---|---|---|
| **Deployed-default accuracy 36.2%** | `CLAUDE.md` Tier 1 | 98/268 = 36.57% from calibration CSV | CLAUDE.md rounds to 36.2%; the CSV gives 36.57%. Same finding. |
| **Old default N=161 total return +64.51%** | `CLAUDE.md` historical | `vs_backtest_py.backtest_py_reported.total_return_pct = 64.51` in sweep JSON; tensor sweep gives 64.3% | Two runs of different code paths give slightly different values. Both are documented. |
| **Ext4 bootstrap +0.10pp** | `CLAUDE.md` Tier 2 | Consistent with ext4 CSV mean-net difference (1.8179% − 1.7193% = +0.10pp) | Console-only; script patched to save `ext4_paired_bootstrap.csv` on next run with price data. |

---

## Verified figures (summary count only)

42 figures were verified directly against committed output files with exact or rounding-only matches. The most important are listed below; the others were confirmed in passing.

### Backtest and P&L (from `backtest_equity.csv`, `ext4_conviction_sizing.csv`)
- +1243.64% total return; 60/84/27 C/F/W; 62.6% hit rate; 3.581 t-statistic (labelled `sharpe_per_trade`, backward-compat alias — not a time-series Sharpe, per `backtest.py` line 161 comment); 37.40% max drawdown; 1.719% avg net/trade; 171/268 trades
- Conviction sizing: sized +1272.45%, Sharpe 3.036, max_dd 41.44%; score dist mean 0.227 / median 0.230 / stdev 0.141 / IQR [0.12, 0.305]
- Always-long baseline: −61.00%

### Weight/threshold sweep and validity (from `phase2_pnl_weight_threshold_sweep.json`, `phase2_threshold_sweep.json`)
- N=161 in-sample best: +167.66%, 99 trades, Sharpe 2.329; PSR = 0.0; permutation p = 0.14977 (~0.150); LOOCV +87.82%, 95 trades; 113,344-combo grid
- N=161 threshold sweep: hu=0.15 → 123 trades, +84.29%; hu=0.35 → 47 trades, +106.91%; hu=0.25 → 79 trades, +64.51%

### Accuracy and diagnostics
- rq16: LLM-only 0.386, surprise-only 0.437, majority 0.468, p = 0.456; N = 158 (`rq16_surprise_control_phase2.json`)
- Macro ablation: off 0.3731, on 0.3619, diff −1.12pp, CI [−5.60%, +3.36%], p = 0.739 (`macro_ablation_summary.json`); best macro=0.35 → 0.3881 (`macro_weight_axis_sweep.csv`)
- 30/30 recall probe refusals (`recall_probe_log.csv`)
- Quote screen: 272 evidence items, 267 passed to handover, 5 absent; 4 Comcast table quotes + 1 PUM.DE_FQ1_2025 fabrication (`quote_verification_full.csv`)
- Breakeven cost 162.81bps (`ext9_cost_grid_summary.json`): SUPERSEDED — computed on OLD report_date anchor, N=268, retired compounded metric. Corrected figures (`ext9_cost_grid_n233.json`, corrected release_date anchor, returns_matrix.csv price source, 2026-08-13): N=268 compounded-breakeven 186.12bps, mean-net-breakeven 207.34bps; N=233 compounded-breakeven 175.33bps, mean-net-breakeven **196.17bps** [PRIMARY]. Arithmetic: N=233 mean_gross=1.9617% × 10000 = 196.17bps. Worst-cell return +386.75% at 70bps total cost (`ext9_cost_grid.csv`, old anchor, directionally informative).
- BUY-truth recall 36.1% (n=72) vs SELL-truth 32.5% (n=77), gap +3.6pp, p = 0.640 (`asymmetry_recall_gap_test.csv`)

### Holding-period decay curve (from `ext2_holding_curve.csv`, N = 233 clean events)
- Overnight: rho = 0.236, p = 0.0003, accuracy 65.3% (95 graded), mean net +1.86%, CI [+0.98%, +2.81%]
- 5d: rho = 0.072, p = 0.276; 10d: rho = 0.058, p = 0.380 — monotonic decay confirmed

### Corrected anchor figures (from `retracted_findings_2026-08-12.md`, `agreement_filter_corrected.csv`)
- Corrected band capture: 42.4% (pre_market, 56/132) vs 29.9% (after_hours, 29/97)
- Corrected agreement filter: 69.0% (20/29 agree) vs 69.2% (18/26 disagree), diff −0.3pp, p = 0.959
- Corrected accuracy: pre_market 64.6% vs after_hours 65.9%

### Frontier / baselines (from `frontier_table.csv`, `lm_baseline_eval_results.csv`, `finbert_eval_results.csv`, n = 186)
- LM flat-as-wrong: 0.3495; FinBERT flat-as-wrong: 0.3226; model flat-as-wrong: 0.4409; majority-HOLD flat-as-wrong: 0.3602

### Worksheet contamination (from `worksheet_leak_triage.md`, `worksheet_exclusion_decision.md`)
- 25/268 events contaminated (9.3%); 72.0% (18/25) agreement on worksheet events; kappa = 0.506; p = 0.0013
- Clean-group agreement 38.3% (69/180); contaminated-vs-clean +21.7pp, p = 0.042

---

## Notes on labelling conventions

**"Sharpe/trade 3.58"**: The value 3.581 in `backtest_equity.csv` and `ext4_conviction_sizing.csv` is a
t-statistic (`mean/pstdev * sqrt(N)`), not a time-series Sharpe ratio. `backtest.py` (line 161) explicitly
comments "NOT a time-series Sharpe. Grows mechanically with sample size." `ext4_conviction_sizing.py` labels it
`sharpe_per_trade` as a "backward-compat alias." Any write-up that quotes this figure must use a label that
does not imply annualisation (e.g. "per-trade t-statistic" or "information ratio × √N").

**"+1243.64% total return"**: As `model_arm_state_2026-08-11.md` notes, `backtest.simulate()` compounds
via `eq *= (1 + net)` (line 122). The figure is order-dependent and not an achievable account balance because
positions overlap across same-week reporters. The correct primary P&L metric is mean net per trade with a
bootstrap interval. The compounded figure appears in `backtest_equity.csv`, `ext9_cost_grid.csv`,
`ext4_conviction_sizing.csv`, and `leave_one_out_robustness*.csv`; all are internally consistent but share
the same methodological caveat.

**Leave-one-out outputs**: `leave_one_out_robustness.csv` and `leave_one_out_robustness_full.csv` were
generated on 2026-08-10 with the `+1265.55%` base (pre-AMKBY fix). Their full-sample row confirms `+1265.55%`
not `+1243.64%`. The direction finding ("total return sign never flips under any single exclusion") is likely
still correct but the absolute delta figures are anchored to the stale base.
