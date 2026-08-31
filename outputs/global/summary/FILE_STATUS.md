# File status — outputs/global/summary/

Date: 2026-08-31

This folder contains ~120 files produced at various stages of the project.
Three categories are documented here. Any file not listed is an intermediate
working document or diagnostic output; treat it as informational only.

---

## 1. Current — cited in the dissertation

These files were computed on the N=232 clean universe (or a correctly-sized
sub-population) at the deployed constants (weights 0.80/0.20/0.00/0.00,
thresholds hold_upper=+0.20/hold_lower=−0.10) and support figures or tables
that appear in the submitted dissertation.

| File | Dissertation use |
|---|---|
| `item_e_walkforward.json` | Primary headline figures: selectivity 62.4% (68/109), mean net per trade +1.796%, N=232. Fields `in_sample_deployed.accuracy` and `in_sample_deployed.mean_net_pct`. |
| `ext2_holding_curve.csv` | Holding-period rank-correlation curve (overnight 0.2565, 1d 0.1952, 3d 0.1353, 5d 0.0972, 10d 0.0951 — monotonically decreasing). Also the source of the signed overnight Spearman ρ = 0.2565 cited as the primary rank-correlation figure. N=232, clean_n confirmed in file header. |
| `asymmetry_rank_correlation.csv` | Two rank-correlation figures: signed Spearman(score, ret) = 0.2565 p=0.000078 (dissertation primary); Spearman(\|score\|, \|ret\|) = 0.1903 p=0.0036 (Appendix F). N=232. Regenerated 2026-08-31; see file header for supersession note on the prior 0.2288/N=268 value. |
| `frontier_table.csv` | Comparison table: deployed model vs Loughran-McDonald, FinBERT, and majority-class baselines under two grading conventions (FLAT-excluded / FLAT-as-wrong). N=186 (eval split, 80% of N=233 by date). |
| `finbert_eval_results.csv` | FinBERT per-event predictions for the phase-2 dev/eval split. N=186 eval events. Inputs to `frontier_table.csv`. |
| `lm_baseline_eval_results.csv` | Loughran-McDonald per-event predictions, same split. N=186. Inputs to `frontier_table.csv`. |
| `finbert_extension_results.csv` | FinBERT on the 93-event extension corpus (energy/utilities issuers). |
| `lm_baseline_extension_results.csv` | Loughran-McDonald on the same 93-event extension corpus. |
| `section_ablation_summary.csv` | Section ablation accuracy table: full bundle vs press-release-only vs transcript-only vs presentation-only. N=200 events for which all section arms were available. Re-thresholded at 0.20/−0.10 on 2026-08-19 (gate passed); underlying LLM scores are from run 20260812T131110Z. |
| `section_ablation_extension_summary.csv` | Section ablation on the 93-event extension corpus. |
| `human_vs_llm_statistics.csv` | Human-arm vs LLM-arm comparison statistics. N=170 paired events (first-rater-per-event, in-LLM-universe, exclusions applied). |
| `human_vs_llm_direction_decomposition.csv` | BUY/SELL/HOLD accuracy decomposition by call direction for both arms. Same N=170 paired population. |
| `backtest_equity_extension_2026_08_24.csv` | Per-trade equity curve for the 93-event extension corpus at (0.80, 0.20) weights, release_date anchor, 10bps cost. Current version; supersedes the 2026_08_13 and 2026_08_22 variants. Provenance in `backtest_equity_extension_2026_08_24.provenance.md`. |
| `ext9_cost_grid_n233.json` | Execution-cost grid and breakeven analysis at the corrected release_date anchor. The `n233_corrected_anchor` section gives N=232 figures (168 trades, breakeven 189.62bps mean-net). Supersedes `ext9_cost_grid_summary.json` for all post-exclusion figures. |
| `effective_sample_funnel.md` | Narrative of the 268→232 exclusion funnel. Cited in methodology. |
| `contamination_summary.json` | Contamination audit results: model training-cutoff self-report, pre/post-cutoff split, recall probe (30/30 refusals). |
| `returns_matrix.csv` | Per-event overnight and multi-day returns at the corrected release_date anchor (run_id 20260820_020202). Source for all horizon computations. N=268 rows (timing_excluded column marks the 9 excluded rows). |
| `worksheet_leak_flags.csv` | Definitive list of 25 worksheet-contaminated events (has_human_score=True). Used as the primary exclusion filter by all analysis scripts. |
| `implied_hold_bands.csv` | Pre-registered ±2% overnight band plus recalibrated bands for longer horizons. Used by `ext2_holding_curve.py`. |

---

## 2. Pre-exclusion — N=268 or N=233

These files predate the 36-event exclusion documented in
`effective_sample_funnel.md` (25 worksheet contamination + 2 misattributed
documents + 9 timing-unresolved = 36 excluded; 268 − 36 = 232 clean). They
are retained as a record of the intermediate state of the analysis. No figure
in the dissertation is drawn from any of these files.

| File | Population | Note |
|---|---|---|
| `global_outcome_calibration_phase2.csv` | N=268 | The master calibration table; 268 rows include all 36 excluded events. Downstream scripts that import it directly will inherit the pre-exclusion universe unless they apply the exclusion filters themselves. |
| `global_calibration_summary_phase2.json` | N=268 (`n_documents: 268`) | Summary of the above. |
| `backtest_equity.csv` | 259 LLM rows (268 − 9 timing); includes 22 worksheet-contaminated + 2 misattributed events | The equity curve was produced before the worksheet and misattribution exclusions were finalised. |
| `leave_one_out_robustness.csv` | FULL-row baseline 171 trades (pre-exclusion; N=232 gives 168) | Ran against the pre-exclusion calibration CSV. |
| `leave_one_out_robustness_full.csv` | Same as above | Extended version of the same run. |
| `macro_ablation_paired.csv` | N=268 rows | One row per event including all 36 excluded. |
| `macro_ablation_summary.json` | `"n": 268` | Summary of the above. |
| `macro_weight_axis_sweep.csv` | n=268 per row | Macro-weight sensitivity sweep on pre-exclusion universe. |
| `asymmetry_direction_confusion.csv` | BUY(72)+HOLD(119)+SELL(77) = 268 | Confusion matrix on pre-exclusion universe. |
| `asymmetry_recall_gap_test.csv` | n_buy_truth=72, n_sell_truth=77 drawn from N=268 | **Note:** the README verification table cites p=0.004 from this file; that value was produced on N=268. The file is retained as-is. If a N=232 figure is needed it must be recomputed. |
| `asymmetry_score_magnitude_bins.csv` | Total n=268 | Score-magnitude accuracy bins on pre-exclusion universe. |
| `ext4_conviction_sizing.csv` | `n_prints: 268`, 196 trades | Conviction-sizing comparison on pre-exclusion universe (N=232 gives 168 traded). |
| `ext4_paired_bootstrap.csv` | n_paired_trades: 196 (pre-exclusion) | Bootstrap CI for the sized-vs-flat book comparison on the same pre-exclusion run. |
| `ext9_cost_grid.csv` | n_trades: 171 (pre-exclusion) | 12-cell cost grid on pre-exclusion universe; superseded by `ext9_cost_grid_n233.json` for the N=232 figure. |
| `ext9_cost_grid_summary.json` | n_predictions: 268 | Breakeven analysis on pre-exclusion universe (162.81bps). Superseded for the N=232 figure. |
| `kappa_near_independence.csv` | n_paired_events: 171 (pre-DIS exclusion, N=233) | Cohen's kappa computation on the N=233 universe (DIS_FQ1_2025 not yet excluded). |
| `per_trade_stats.csv` | Header says "N=233 clean universe" | Pre-dates the DIS_FQ1_2025 exclusion that reduced N from 233 to 232. |

---

## 3. Old-regime — 0.55/0.45 weights or ±0.25/−0.05 thresholds

These files were produced under the weight/threshold configuration that was
superseded on 2026-08-19 (promoted from 0.55/0.45, ±0.25/−0.05 to
0.80/0.20, +0.20/−0.10). They are retained as a record of the intermediate
state and as gate references. No figure in the dissertation is drawn from
either file.

| File | Regime | Note |
|---|---|---|
| `section_ablation_results.csv` | hold_upper=0.25, hold_lower=−0.05; run ID 20260812T131110Z | Raw per-document LLM scores and signals from the section ablation scoring run, produced at the old thresholds. `section_ablation_summary.csv` (Section 1) re-derives signals from these scores at the promoted constants, so the summary is current but the raw scores here are from the old regime. |
| `section_ablation_summary_at_superseded_0.25_-0.05.csv` | hold_upper=0.25, hold_lower=−0.05 (explicitly) | Frozen gate reference. The header marks it as such and instructs that it must not be regenerated. Retained to prove that `section_ablation_summary.csv` reproduces the old-regime figures before recomputing at the new ones. |
| `phase2_pnl_weight_threshold_sweep.json` | n_documents=161 (old N, old regime) | Full 113,344-combo grid search that produced the 0.55/0.45 combo. Historical record; the 0.80/0.20 search is not in this repository (see CLAUDE.md, Architecture > Blend). |
