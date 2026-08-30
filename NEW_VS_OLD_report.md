# NEW vs OLD Repository Reconnaissance Report
**Generated:** 2026-08-21  
**OLD:** `/Users/nigelsim/Desktop/arp-master-4`  
**NEW:** `/Users/nigelsim/Desktop/arp-master-5`

---

## A. Orient

### A1. Git status

Both repositories share **identical git history**: 82 commits, same HEAD at:

```
124aaba6ac0e405b9b86ccaea5e36ab789d68d2b
Fix PUM.DE_FQ1_2026 outcome_label/is_correct in prototype_events.json
```

The two clones are at the same commit. **All differences are uncommitted working-tree changes** that exist in NEW but were not committed before the clone. OLD is not an ancestor of NEW at a different commit — they are diverged at the working-tree level only, not at the git history level.

### A2. Commits in NEW but absent from OLD

None — the git history is identical. The differences are working-tree modifications, not new commits.

### A3. File-level inventory of differences

Working-tree differences (uncommitted), not a `git diff` between commits:

**Source code changed (9 files):**
- `blend.py` — weights, thresholds, sanity-check assertion
- `experiments/build_workbook.py` — exclusion set, verification expectations table
- `experiments/execution_cost_grid_n233.py` — exclusion set, sys.path fix
- `experiments/finbert_baseline.py` — exclusion set, sys.path fix, excluded_n derivation
- `experiments/finbert_extension.py` — exclusion set, extension gap file join key
- `experiments/holding_period_curve.py` — exclusion set
- `experiments/human_vs_llm_backing.py` — exclusion set, exclusion reason lookup
- `experiments/lm_baseline.py` — exclusion set, sys.path fix
- `experiments/lm_baseline_extension.py` — exclusion set, extension gap file join key
- `experiments/section_ablation.py` — exclusion set
- `experiments/section_ablation_extension.py` — exclusion set, extension gap file join key, document_id join
- `experiments/section_boundary_audit.py` — exclusion set, derived expected_a
- `experiments/sector_analysis.py` — exclusion set, sys.path fix
- `experiments/walkforward_combined.py` — exclusion set, document_id join, PHASE2_EXPECTATION table
- `experiments/walkforward_validation.py` — exclusion set

**New source files in NEW (absent in OLD):**
- `eval/excluded_events.py` — single-source-of-truth exclusion set (SPOT + DIS)
- `eval/extension_gaps.py` — writer for the extension overnight gap artefact
- `experiments/kappa_and_frontier.py` — regenerates kappa and frontier table at new constants
- `experiments/section_ablation_gate_negative_test.py` — negative-case gate test
- `experiments/section_ablation_rethreshold.py` — re-derives section ablation at new thresholds

**Manifests changed (4 files):**
- `manifests/p2_duke_energy_reports.json` — `release_timing` corrected from `after_hours` to `pre_market`
- `manifests/p2_hermes_reports.json` — four Hermes `report_date` placeholders resolved to actual datelines
- `manifests/p2_lenovo_reports.json` — LNVGY_FQ2_2026 `report_date` corrected from 2026-01-30 to 2025-11-20
- `manifests/p2_lowes_reports.json` — LOW_FQ1_2025 corrected from 2026-05-20 (duplicate of FQ1_2026) to 2025-05-21

**Output artefacts changed (many — see Section E):**

**New in NEW only:**
- `data/workbook/Master_Data_Phase_3_2026-08-20.xlsx`, `Master_Data_Phase_3_2026-08-20_synced.xlsx`
- `ARP_Draft_Condensed_v2.docx`, `ARP_Draft_v4.docx`
- `outputs/global/summary/backtest_equity_extension_2026_08_22.csv` + `.provenance.md`
- `outputs/global/summary/backtest_equity_extension_2026_08_24.csv` + `.provenance.md`
- `outputs/global/summary/backtest_equity_extension_exceptions_2026_08_22.csv`
- `outputs/global/summary/backtest_equity_extension_exceptions_2026_08_24.csv`
- `outputs/global/summary/ext4_paired_bootstrap.csv`
- `outputs/global/summary/section_ablation_summary_at_superseded_0.25_-0.05.csv`

**Only in OLD (not in NEW):**
- `outputs/global/summary/summary_comparison_pairs.md`
- `outputs/p2_adobe/` — full results/logs/summary tree (OLD has these locally; NEW does not)
- `data/quantitative/price_cache/` and `sheet_export_cache/` (price data; NEW has these cleared)

---

## B. Regime Question

### B4. blend.py in NEW — exact lines

```python
# /Users/nigelsim/Desktop/arp-master-5/blend.py  lines 24, 30–31
DEFAULT_WEIGHTS = (0.80, 0.20, 0.0, 0.0)  # (micro, macro, news, quant)
DEFAULT_HOLD_UPPER = 0.20
DEFAULT_HOLD_LOWER = -0.10
```

Sanity-check assertion (line 167):
```python
assert abs(check - 0.36) < 1e-9, f"Sanity check failed: got {check}, expected 0.36"
```

### B5. blend.py in OLD — exact lines

```python
# /Users/nigelsim/Desktop/arp-master-4/blend.py  lines 24, 30–31
DEFAULT_WEIGHTS = (0.55, 0.45, 0.0, 0.0)  # (micro, macro, news, quant)
DEFAULT_HOLD_UPPER = 0.25
DEFAULT_HOLD_LOWER = -0.05
```

Sanity-check assertion (line 167):
```python
assert abs(check - 0.31) < 1e-9, f"Sanity check failed: got {check}, expected 0.31"
```

### B6. Regime-switching mechanism

There is **no switch, config file, or flag** that selects between the OLD (0.55/0.45, +0.25/−0.05) and NEW (0.80/0.20, +0.20/−0.10) regimes at runtime. The constants are hard-coded in `blend.py`. The OLD constants are preserved only:
- As the `GATE_WEIGHTS`/`GATE_BAND` in `eval/extension_gaps.py` (for reproducing the 2026-08-13 artefact)
- In the `VERIFY_EXPECTATIONS` and `PHASE2_EXPECTATION` tables in `build_workbook.py` and `walkforward_combined.py` respectively (keyed on the constant tuple, used for verification only)
- In `section_ablation_summary_at_superseded_0.25_-0.05.csv` (frozen reference gate file)

### B7. revert_frozen_regime.py

**Does NOT exist** in NEW. No such file was found.

---

## C. Method Changes

### backtest.py — entry/exit anchor, cost assumptions

**No changes detected** between OLD and NEW in `backtest.py`. The file is not in the working-tree diff. Entry/exit logic, cost assumptions (10 bps round trip, 0 bps short borrow), and the pre-market vs after-hours rule all remain unchanged.

The Duke Energy manifest change (`after_hours` → `pre_market`) does change which session `backtest.py` uses as entry for the 13 Duke events, but this change is in the manifest data, not in `backtest.py` itself. This is a **data correction** that propagates to reported figures.

### eval/outcomes.py — ±2% neutral band

**No changes detected** in `eval/outcomes.py`. The pre-registered ±2% grading band (strict inequalities: `|ret_overnight| > 0.02`) remains unchanged. This file is not in the working-tree diff.

### Trading cost assumptions

Unchanged: 10 bps round-trip, 0 bps short borrow, in both `backtest.py` and `eval/extension_gaps.py`.

### Event exclusion logic and counts

**KEY CHANGE:** OLD had a hardcoded exclusion set `{"SPOT_FQ1_2026"}` (1 event) in every script. NEW introduces `eval/excluded_events.py` as a single source of truth containing **two events**:

- `SPOT_FQ1_2026` — misattributed document (present in OLD)
- `DIS_FQ1_2025` — look-ahead contamination (NEW, ruled 2026-08-24: the manifest bundled the fiscal Q2 press release with the Q1 transcript; the scored model read the future-dated Q2 document)

Every affected script in NEW imports `EXCLUDED_EVENTS` from `eval/excluded_events.py` instead of maintaining its own hardcoded set. This affects:
- `experiments/walkforward_validation.py`
- `experiments/walkforward_combined.py`
- `experiments/holding_period_curve.py`
- `experiments/execution_cost_grid_n233.py`
- `experiments/section_ablation.py`
- `experiments/section_ablation_extension.py`
- `experiments/section_boundary_audit.py`
- `experiments/sector_analysis.py`
- `experiments/lm_baseline.py`
- `experiments/finbert_baseline.py`
- `experiments/human_vs_llm_backing.py`
- `experiments/build_workbook.py`

**Consequence for counts:**  
OLD: N=233 clean events (268 − 25 worksheet − 1 SPOT − 9 timing = 233)  
NEW: N=232 clean events (268 − 25 worksheet − 2 bad-document − 9 timing = 232)

DIS_FQ1_2025 was a graded event with a BUY call on an UP outcome (ret_overnight = +2.12%), so its removal reduces both graded count and correct count by 1.

### Accuracy denominator construction

**Unchanged in method.** The project still uses two conventions:
1. **Coverage** (HOLD=wrong): denominator = all events with |ret_overnight| > 2%
2. **Selectivity** (FLAT-excluded): denominator = only traded (non-HOLD) events that are also graded

Both conventions are still used in the same scripts. The changed constant set produces different numbers under both conventions, but the construction logic is unchanged.

**Changed headline figures due to regime change (OLD → NEW):**

| Metric | OLD (0.55/0.45, +0.25/−0.05) | NEW (0.80/0.20, +0.20/−0.10) |
|--------|------|------|
| N clean events | 233 | 232 |
| Trades | 146 | 168 |
| Graded (|ret|>2%) | 95 | 109 |
| Correct | 62 | 68 |
| Selectivity | 65.3% (62/95) | 62.4% (68/109) |
| Mean net/trade | +1.862% | +1.796% |

Source: `item_e_walkforward.json` in each repo.

**Note on agrees field:** The `item_e_combined_walkforward.json` in NEW has `"agrees": False` for the phase2 sanity check against the stored expectation. The expectation for `((0.80, 0.20, 0.0, 0.0), 0.20, -0.10, ("DIS_FQ1_2025", "SPOT_FQ1_2026"))` expects (168, 109, 67, 0.6239) but the JSON records n_correct=68. This is a minor inconsistency in the NEW artefact — the expectation table has 67 correct but the actual run produced 68.

### Naive floor computation

**Changed numerically** (due to different exclusion/threshold regime), **unchanged in method**. The floor is always-DOWN (majority direction) on the graded events in the relevant subset.

In `build_workbook.py` NEW: `clean_universe = 268 - 25 - len(EXCLUDED_EVENTS) - 9` is derived, not typed. OLD had a hardcoded `233`.

### blend.py — renormalisation when a layer is missing

**Unchanged in logic.** The renormalisation code (lines 80–96 in both versions) is identical: missing layers drop out, and remaining weights are renormalised proportionally. Only `DEFAULT_WEIGHTS` and the thresholds changed.

### Walk-forward windows, objectives, degeneracy test

**Unchanged in method.** The 4-window rolling walk-forward in `walkforward_validation.py` uses the same quarterly cutoffs (Sep/Dec/Mar/Jun 2025/26), the same two objectives (mean_net_per_trade, directional_accuracy), and the same degeneracy test (fitted threshold at the grid boundary = 0.5 / −0.5). The threshold grid is also unchanged (upper: 0.05–0.5, lower: −0.5–0.0).

**Changed numerically:** At the new constants, mean_net_objective has 4 degenerate windows (all four) vs 3 in OLD. accuracy_objective has 1 degenerate window vs 2 in OLD. Pooled OOS results differ substantially:

| Objective | Metric | OLD | NEW |
|-----------|--------|-----|-----|
| mean_net | OOS trades | 8 | 5 |
| mean_net | OOS accuracy | 0.500 | 0.500 |
| mean_net | OOS mean_net_pct | +1.54% | −0.002% |
| accuracy | OOS trades | 21 | 38 |
| accuracy | OOS accuracy | 0.500 | 0.6538 |
| accuracy | OOS mean_net_pct | +0.47% | +1.89% |

The genuinely_unseen cross-issuer block differs in n_events_in_sweep (OLD: 132, NEW: 131) because DIS is now excluded.

### Bootstrap/permutation procedures (bootstrap_stats.py)

**Unchanged.** `bootstrap_stats.py` is not in the working-tree diff. The RNG seed (20260709) and resampling logic are unchanged.

### experiments/walkforward_validation.py

Changed: exclusion set now uses `EXCLUDED_EVENTS` import; `n_clean_events` drops from 233 to 232 in the JSON output; all numerical results differ (see above).

### experiments/walkforward_combined.py

**Significant changes:**
1. Exclusion set: `EXCLUDED_EVENTS` import instead of hardcoded `{"SPOT_FQ1_2026"}`
2. Extension gap file join: changed from `(ticker, report_date)` key to `document_id` key — fixes silent data loss for Hermes events whose report_dates were corrected
3. `CURRENT_GAP_FILE` now imported from `eval/extension_gaps.py` (single source of truth, pointing to `backtest_equity_extension_2026_08_24.csv`)
4. `PHASE2_EXPECTATION` table added — regime-keyed sanity checks
5. Combined N changes: 326 → 325 (one fewer phase2 clean event due to DIS exclusion)
6. Combined in-sample: trades 178→221, graded 109→127, correct 72→81, accuracy 0.6606→0.6378, mean_net 1.75%→1.72%

### experiments/section_ablation.py

Changed: exclusion set only. Numerical outputs change because 1 more event is excluded (DIS_FQ1_2025 is no longer scored in this section's universe). The section ablation scores themselves (frozen from 20260812T131110Z) are unchanged; only the signal derivation at the new thresholds produces different BUY/HOLD/SELL calls.

The live `section_ablation_summary.csv` in NEW was regenerated by `experiments/section_ablation_rethreshold.py` at the new thresholds (+0.20/−0.10). The superseded version at +0.25/−0.05 is preserved in `section_ablation_summary_at_superseded_0.25_-0.05.csv`.

**Changed section ablation figures (four-arm, overnight):**

| Arm | OLD trades | OLD accuracy | NEW trades | NEW accuracy |
|-----|-----------|-------------|-----------|-------------|
| full_bundle | 87 | 27.6% | 83 | 37.3% |
| press_release | 66 | 28.8% | 65 | 36.9% |
| prepared_remarks | 77 | 28.6% | 79 | 36.7% |
| qa_only | 67 | 31.3% | 65 | 41.5% |

The section ablation finding about "full bundle wins marginally at 6.8pp" is invalidated by the re-threshold. The new comment in the CSV states: "A gap smaller than the paired MDE means the arms are indistinguishable at this sample size. Combined with the token ratio, indistinguishability is itself the deployment answer."

### experiments/section_ablation_extension.py

Changed: extension gap file join changed from `(ticker, report_date)` to `document_id`; `CURRENT_GAP_FILE` imported from `eval/extension_gaps.py`. This fixes silent data loss for re-anchored Hermes events.

### experiments/finbert_baseline.py

Changed: exclusion set (now 36, not 35); excluded_n derived from `268 - len(events)` not hardcoded; sys.path fix for running as a script.

**Changed numerical output (`finbert_dev_thresholds.json`):**
- dev_n: 47 → 46
- excluded_n: 35 → 36
- dev date range shifted (earliest date 2025-05-22 → 2025-05-21, latest 2026-07-13 → 2026-07-14)
- fitted_upper: 0.0873 → 0.2066
- fitted_lower: −0.1290 → −0.1303
- dev_accuracy_flat_as_wrong: 0.4681 → 0.4783

The shifted thresholds change FinBERT's signal for multiple events in the eval split and extension set.

### experiments/finbert_extension.py

Changed: extension gap file join key (`document_id` not `(ticker, report_date)`); `CURRENT_GAP_FILE` from `eval/extension_gaps.py`; sys.path fix.

**Changed: graded count in extension** 31 → 34, because the new gap file (2026-08-24 vintage) includes correctly anchored Hermes events.

### experiments/lm_baseline.py

Changed: exclusion set (now 36, not 35); SPOT_EXCLUDED renamed to still refer to `EXCLUDED_EVENTS`; the print statement calls it "bad-document" not "SPOT"; sys.path fix.

**Changed numerical output (`lm_baseline_dev_thresholds.json`):**
- dev_n: 47 → 46
- excluded_spot: 1 → 2
- date range shifted
- fitted_upper: 0.0160 → 0.0302
- dev_accuracy_flat_as_wrong: 0.4043 → 0.4348

### experiments/lm_baseline_extension.py

Changed: extension gap file join key; `CURRENT_GAP_FILE` from `eval/extension_gaps.py`; sys.path fix. Graded count in extension changes (29 → 34) for the same reason as finbert_extension.

### experiments/human_vs_llm_backing.py

Changed: exclusion set; exclusion reason now looked up from `EXCLUSION_REASONS` dict instead of hardcoded "SPOT misattribution". The `build_workbook.py` `excluded_bad_document` count is now `len(EXCLUDED_EVENTS)` (2), and `clean_universe` is derived as `268 - 25 - len(EXCLUDED_EVENTS) - 9 = 232` instead of hardcoded 233. The `event_set` label reads "N=232 clean universe" in NEW.

### experiments/holding_period_curve.py

Changed: exclusion set only. The **holding curve CSV and PNG are re-generated at the new constants**, producing substantially different numbers:

| Horizon | OLD mean_net | OLD accuracy | NEW mean_net | NEW accuracy | OLD rho | NEW rho |
|---------|------------|------------|------------|------------|---------|---------|
| overnight | +1.862% | 65.3% (95g) | +1.796% | 62.4% (109g) | 0.236 (p=0.0003) | 0.256 (p=0.0001) |
| 1d | +1.251% | 60.2% | +1.183% | 60.2% | 0.159 | 0.195 |
| 3d | +1.026% | 56.3% | +0.830% | 52.6% | 0.112 | 0.135 |
| 5d | +0.846% | 52.1% | +0.937% | 51.9% | 0.072 | 0.097 |
| 10d | +0.686% | 53.4% | +1.446% | 57.0% | 0.058 | 0.095 |

**Critical finding:** The NEW holding curve is **not monotonically decaying**. The 5-day figure is higher than 3-day, and the 10-day figure (+1.45%) is higher than the overnight figure (+1.80%). This is the non-monotonic pattern that the CLAUDE.md warned about when promoting these constants: "it falls to three days, then rises, ending near its overnight level. ext2_holding_curve.csv was relied on to rule out post-earnings drift, and a ten-day return back at the overnight level is the drift signature it was meant to exclude." The OLD curve was monotonically decaying (1.86/1.25/1.03/0.85/0.69).

The "monotonic decay validates overnight window" argument **cannot be made at the NEW constants**.

### experiments/execution_cost_grid_n233.py

Changed: exclusion set; sys.path fix. The cost grid artefact (`ext9_cost_grid_n233.json`) is re-run at the new constants:

| Metric | OLD N=233 | NEW N=232 |
|--------|-----------|-----------|
| n_trades_at_10bps | 146 | 168 |
| mean_net_at_10bps_pct | 1.8617% | 1.7963% |
| breakeven_mean_net_bps | 196.17 | 189.62 |
| compounded_return_at_10bps | 1001.03% | 1349.97% |

And for N=268:

| Metric | OLD N=268 | NEW N=268 |
|--------|-----------|-----------|
| n_trades | 171 | 196 |
| mean_net_at_10bps_pct | 1.9735% | 1.8477% |
| breakeven_mean_net_bps | 207.34 | 194.76 |

### experiments/sector_analysis.py

Changed: exclusion set; sys.path fix. The sector analysis CSV in NEW uses scipy 1.14.1 vs OLD's 1.16.3, which slightly changes Spearman p-values (rho values are version-independent). The underlying signal distribution changes because the LLM's thresholds changed.

### experiments/build_workbook.py

**Major changes:**
1. Exclusion set via import
2. Exclusion reason lookup from `EXCLUSION_REASONS` dict
3. `clean_universe` count derived, not hardcoded
4. `VERIFY_EXPECTATIONS` table added (regime-keyed verification table, 3 regimes: OLD constants, NEW constants, NEW constants + DIS exclusion)
5. `check()` function reads from the deployed expectations table rather than positional expected values
6. Two specific corrections: `LLM graded` 58→57, `LLM correct (pooled)` 40→39 (Lowe's FQ1 fix propagated)

The key human-vs-LLM figures in NEW (`human_vs_llm_statistics.csv`):

At **OLD** constants (0.55/0.45, +0.25/−0.05):
- LLM BUY calls: 42, HOLD: 69, SELL: 60 (N=171 paired)
- LLM traded: 102, graded: 58, correct: 40
- Paired graded N: 48

At **NEW** constants (0.80/0.20, +0.20/−0.10):
- LLM BUY calls: 73, HOLD: 53, SELL: 45 (N=171 paired)
- LLM traded: 118, graded: 70, correct: 44 (but also reports 57/39 from Lowe's fix: see below)
- Paired graded N: 55

**Note on Lowe's fix:** The NEW workbook also incorporates a correction for LOW_FQ1_2025 (report_date was 2026-05-20, a duplicate of FQ1_2026; corrected to 2025-05-21). This changes the returns for that event and moves the LLM graded/correct pooled counts. This correction is independent of the threshold promotion.

### Cohen's kappa

| Metric | OLD (0.55/0.45, +0.25/−0.05) | NEW (0.80/0.20, +0.20/−0.10) |
|--------|------|------|
| Observed agreement | 0.3801 | 0.4561 |
| Expected agreement | 0.3041 | 0.3660 |
| Cohen's kappa | 0.1092 | 0.1421 |
| 90% CI | [0.030, 0.190] | [0.055, 0.230] |

### Asymmetry and conviction analysis

**Changed figures** (`asymmetry_direction_confusion.csv`, `asymmetry_recall_gap_test.csv`, `asymmetry_rank_correlation.csv`):

BUY-truth recall: OLD 36.1% (26/72), NEW 51.4% (37/72)  
SELL-truth recall: OLD 32.5% (25/77), NEW 28.6% (22/77)  
Recall gap: OLD +3.6pp (not significant, z-test p=0.64), NEW +22.8pp (significant, z-test p=0.004)  

**This reversal is dissertation-critical.** OLD found no significant BUY/SELL asymmetry; NEW finds a significant 22.8pp gap favoring BUY-truth recall. The dissertation must not cite the OLD "null" result if the NEW constants are the deployed ones.

Spearman rho (|score| vs |return|): OLD 0.1108 (p=0.0701), NEW 0.2288 (p=0.0002)  
The NEW rho is significant (p<0.001), while OLD's was marginal (p=0.07). These are the same N=268 events — the change is entirely due to the different blended scores.

### Frontier table

At OLD constants: deployed model FLAT-excluded = 42.9% (51/119), FLAT-as-wrong = 44.1% (82/186)  
At NEW constants: deployed model FLAT-excluded = 47.9% (57/119), FLAT-as-wrong = 41.4% (77/186)

The two conventions move in **opposite directions** at the new constants. The FLAT-excluded rate went up; FLAT-as-wrong went down. The 90% CI on FLAT-excluded moved from [0.353, 0.504] to [0.403, 0.555].

---

## D. Ensemble Question

### D12. Default and production invocation

`run_reports.py` line 81: `default=1`

The `--ensemble` flag defaults to 1, which means single-run (no ensemble averaging). The ensemble path (`ensemble_llm()`) is only invoked when `args.ensemble > 1` (line 293).

### D11. Output artefacts with multiple scored runs

No output file in either repo contains an `ensemble_runs` column with a value >1, or a `score_range` / `signal_agreement` column populated from an actual ensemble run. Every scored JSON in `outputs/p2_*/results/` has `ensemble: 1` in its metadata.

The workbook correction log in OLD (not in NEW) explicitly documented: "The `signal_agreement` boolean and `score_range` metric the function produces were never populated for any canonical result. The consistency path was built, wired, and documented as a project requirement, and was never invoked." NEW's version of this log removes this fourth instance, reducing it to three instances of "safeguard built but never run."

### D13. Definitive answer

**NO.** Ensemble runs did not happen. Every production scoring event was scored exactly once (ensemble=1). The `--ensemble N` flag is available in the CLI but was never used with N>1 for any event in the canonical N=233/232 universe or the N=93 extension.

---

## E. Figures and Outputs

### E14. Figure-producing scripts in NEW

Scripts that produce .png or .pdf files:
- `experiments/asymmetry_conviction_analysis.py` → `conviction_curve.png`, `ext4_score_distribution.png`
- `experiments/holding_period_curve.py` → `ext2_holding_curve.png`
- `experiments/macro_weight_axis_sweep.py` → `macro_weight_curve.png`
- `experiments/section_ablation_rethreshold.py` → (no PNG, CSV only)
- `experiments/section_ablation.py` → (no PNG)
- `experiments/finbert_baseline.py` → (no PNG)

Committed PNG files in both repos:
- `outputs/global/summary/conviction_curve.png` — CHANGED (new constants)
- `outputs/global/summary/ext2_holding_curve.png` — CHANGED (new constants, non-monotonic)
- `outputs/global/summary/ext4_score_distribution.png` — CHANGED (new constants)
- `outputs/global/summary/macro_weight_curve.png` — unchanged (macro_weight_axis_sweep.py not re-run)

### E15. CSV and JSON output files

| File | Status | Key change |
|------|--------|------------|
| `global_outcome_calibration_phase2.csv` | CHANGED | Generated 2026-08-19 at new constants; `blend_predicted_signal_default` distribution: OLD BUY/HOLD/SELL=88/97/83, NEW=136/72/60 |
| `global_calibration_summary_phase2.json` | CHANGED | New constants reflected; generated 2026-08-19 |
| `returns_matrix.csv` | CHANGED | LOW_FQ1_2025 report_date corrected (2026-05-20→2025-05-21); all return columns for that event change; run_id updated |
| `backtest_equity.csv` | CHANGED | 259 LLM rows in both, but 166→190 trades; final equity 10.4x→15.5x |
| `item_e_walkforward.json` | CHANGED | n_clean_events 233→232, all in-sample figures at new constants |
| `item_e_combined_walkforward.json` | CHANGED | Combined N=325 (was 326), all in-sample figures at new constants |
| `item_e_walkforward.csv` | CHANGED | Same regime change |
| `item_e_combined_walkforward.csv` | CHANGED | Same regime change |
| `ext2_holding_curve.csv` | CHANGED | New constants, non-monotonic decay |
| `ext4_conviction_sizing.csv` | CHANGED | n_trades 171→196; column name `sharpe_per_trade`→`t_statistic` |
| `ext4_paired_bootstrap.csv` | NEW in NEW | n_paired_trades=196, point_diff=+0.30pp, CI [−0.056, +0.71], p=0.178 |
| `ext9_cost_grid_n233.json` | CHANGED | All P&L figures at new constants; N=232 for clean set |
| `asymmetry_direction_confusion.csv` | CHANGED | BUY/SELL recall distribution at new thresholds |
| `asymmetry_magnitude_bins.csv` | CHANGED | New thresholds |
| `asymmetry_rank_correlation.csv` | CHANGED | rho 0.1108→0.2288, p 0.0701→0.0002 |
| `asymmetry_recall_gap_test.csv` | CHANGED | Null→significant, p 0.6395→0.0044 |
| `asymmetry_score_magnitude_bins.csv` | CHANGED | New scores |
| `finbert_dev_thresholds.json` | CHANGED | dev_n 47→46, excluded_n 35→36, fitted thresholds shift |
| `finbert_eval_results.csv` | CHANGED | NEW includes TGT_FQ1_2025; several events change decision/correct |
| `finbert_extension_results.csv` | CHANGED | Graded count 31→34; thresholds shift |
| `lm_baseline_dev_thresholds.json` | CHANGED | dev_n 47→46, excluded_n 35→36 |
| `lm_baseline_eval_results.csv` | CHANGED | NEW includes TGT_FQ1_2025 |
| `lm_baseline_extension_results.csv` | CHANGED | Graded count 29→34 |
| `frontier_table.csv` | CHANGED | FLAT-excluded 42.9%→47.9%, FLAT-as-wrong 44.1%→41.4% |
| `kappa_near_independence.csv` | CHANGED | kappa 0.1092→0.1421, CI shifts |
| `human_vs_llm_statistics.csv` | CHANGED | All LLM call/accuracy figures at new constants; LOW_FQ1_2025 fix |
| `human_vs_llm_direction_decomposition.csv` | CHANGED | Pooled accuracy figures change |
| `section_ablation_summary.csv` | CHANGED | Re-thresholded at +0.20/−0.10; finding narrative changes |
| `section_ablation_summary_at_superseded_0.25_-0.05.csv` | NEW in NEW | Frozen gate reference |
| `section_availability_audit_amended.csv` | CHANGED | Run ID updated; exclusion rule note added |
| `sector_analysis_2026-08-15.csv` | CHANGED | scipy version note; signal distribution at new thresholds |
| `sector_analysis_2026-08-15.md` | CHANGED | Same |
| `implied_hold_bands.csv` | CHANGED | Band fractions at new constants (93→94 graded at overnight, 0.347→0.3507) |
| `conviction_curve.png` | CHANGED | New scores/thresholds |
| `ext2_holding_curve.png` | CHANGED | Non-monotonic at new constants |
| `ext4_score_distribution.png` | CHANGED | New score distribution |
| `backtest_equity_extension_2026_08_22.csv` | NEW in NEW | Extension backtest at new constants (report_date anchor) |
| `backtest_equity_extension_2026_08_24.csv` | NEW in NEW | Extension backtest at new constants (with Hermes corrections, document_id keyed) |
| `returns_matrix_by_ticker/*.csv` | CHANGED (all) | LOW_FQ1_2025 correction propagates to LOW.csv; run_id update on all |
| `revised_achievable_n.md` | CHANGED | Run metadata updated |
| `workbook_correction_log_2026-08-13.md` | CHANGED | misattributed_spot count 1→2; total exclusions 26→27; N after exclusions 210→209; ensemble instance removed |

**Only in OLD:**
- `outputs/global/summary/summary_comparison_pairs.md`

### E16. Mapping to dissertation figures

| Dissertation figure type | Source in NEW | Changed? |
|--------------------------|--------------|----------|
| Funnel (268→232 clean) | `revised_achievable_n.md`, `build_workbook.py` | YES — 233→232, "bad-document" count 1→2 |
| Decay curve (holding period) | `ext2_holding_curve.csv`, `ext2_holding_curve.png` | YES — non-monotonic at new constants |
| Band sweep / threshold grid | `item_e_walkforward.json` threshold_grid section | YES — in-sample figures differ |
| Cost sensitivity | `ext9_cost_grid_n233.json` | YES — all figures differ |
| Score deciles / conviction | `conviction_curve.png`, `ext4_score_distribution.png` | YES |
| Sorted per-trade returns | `backtest_equity.csv` | YES — 146→168 LLM trades, different equity curve |
| Cumulative equity | `backtest_equity.csv` | YES — 10.4x→15.5x |
| Move-size buckets | `asymmetry_magnitude_bins.csv` | YES |
| Model vs always-BUY | `build_workbook.py`, `human_vs_llm_statistics.csv` | YES |
| Frontier / accuracy-coverage | `frontier_table.csv` | YES — 42.9%→47.9% FLAT-excluded |
| Cohen's kappa | `kappa_near_independence.csv` | YES — 0.1092→0.1421 |
| Section ablation | `section_ablation_summary.csv` | YES — finding narrative changes |
| BUY/SELL asymmetry | `asymmetry_recall_gap_test.csv` | YES — null→significant |
| Spearman rho | `asymmetry_rank_correlation.csv` | YES — 0.111→0.229 |
| Extension combined walk-forward | `item_e_combined_walkforward.json` | YES — N=325, different figures |

### E17. Figures/analyses in NEW not covered by OLD

1. **`section_ablation_summary_at_superseded_0.25_-0.05.csv`** — frozen gate reference file; records what the OLD constants published
2. **`ext4_paired_bootstrap.csv`** — paired bootstrap on conviction sizing at new constants
3. **`backtest_equity_extension_2026_08_22.csv`** and **`backtest_equity_extension_2026_08_24.csv`** — extension gap files with `document_id` column; 2026_08_24 is the current live file
4. **`eval/extension_gaps.py`** — complete new module for deriving extension gaps (document_id keyed, Hermes date-corrected)
5. **`eval/excluded_events.py`** — new centralised exclusion registry
6. **`experiments/kappa_and_frontier.py`** — new script regenerating kappa and frontier at promoted constants
7. **`experiments/section_ablation_rethreshold.py`** — re-derives section ablation signals at new thresholds without rescoring
8. **`experiments/section_ablation_gate_negative_test.py`** — negative-case test verifying the gate rejects bad inputs

---

## F. Data Integrity

### F18. Exclusion set integrity

**Nine timing-excluded events:** Confirmed unchanged. `returns_matrix.csv` in NEW has the same 9 events flagged `timing_excluded=YES` as OLD.

**25 worksheet-contaminated events:** Confirmed unchanged. The worksheet contamination flags come from `worksheet_leak_flags.csv`, which is not in the diff. No contamination events were added or removed.

**One SPOT misattribution → Two bad-document events:**  
OLD: 1 event excluded (`SPOT_FQ1_2026`)  
NEW: 2 events excluded (`SPOT_FQ1_2026` + `DIS_FQ1_2025`)

`DIS_FQ1_2025` exclusion reason (from `eval/excluded_events.py`): "Look-ahead contamination. Ruled 2026-08-24. The manifest bundles the correct Q1 FY2025 transcript with `fy2025_q2xprxex991.txt`, which is Disney's fiscal SECOND quarter press release — the quarter ended 2025-03-29, filed 2025-05-07. That is 91 days after this event's 2025-02-05 date. The scoring run read it... the result's own model_document_id is 'DIS_Bundled Earnings Report_2025-05-07'."

This event was BUY on UP (+2.12% overnight), so its removal reduces n_correct by 1. The N=233 headline becomes N=232.

### F19. Extension events (93 events) and price basis

The extension set remains 93 events. The price basis for the extension has **changed** in NEW:

- **OLD:** `backtest_equity_extension_2026_08_13.csv` — keyed on `(ticker, report_date)`, using placeholder dates for non-US events (e.g. Hermes dates were first-of-month)
- **NEW:** `backtest_equity_extension_2026_08_24.csv` — keyed on `document_id`, Hermes report_dates corrected to actual press-release datelines, Duke Energy entry changed from `after_hours` to `pre_market` (13 Duke events affected)

The 2026-08-24 gap file was produced by `eval/extension_gaps.py` which verified it first reproduced the 2026-08-13 artefact (at OLD constants and Duke after_hours). The four Hermes events have different anchors:

| Event | OLD anchor | NEW anchor |
|-------|-----------|-----------|
| RMS_FQ1_2025 | 2025-02-01 (placeholder) | 2025-04-17 (dateline) |
| RMS_FQ2_2025 | 2025-07-01 (placeholder) | 2025-07-30 (dateline) |
| RMS_FQ3_2025 | 2025-10-01 (placeholder) | TBD |
| RMS_FQ4_2025 | 2026-02-01 (placeholder) | TBD |

13 Duke Energy events changed from `after_hours` (entry = announcement day close) to `pre_market` (entry = prior day close).

### F20. returns_matrix comparison

The `returns_matrix.csv` differs in exactly **one event**:

- **`LOW_FQ1_2025`**: report_date corrected from 2026-05-20 (was a duplicate of LOW_FQ1_2026) to 2025-05-21. Entry close: 218.37→231.25. All return columns differ. This is a data correction, not an analytical change.

All other 267 events have identical returns (the return columns are frozen from the 2026-08-12 anchor-correction run). The `run_id` field changed on all rows from `20260812_183842` to `20260820_020202`, indicating a full matrix regeneration date, but the data is the same except for LOW_FQ1_2025.

The `DIS_FQ1_2025` row is **still present** in the NEW returns_matrix (it is not removed, just flagged for exclusion at the analysis stage via `eval/excluded_events.py`). `timing_excluded=NO` and `ret_overnight=+0.021183` are unchanged.

---

## G. What Must Change in the Dissertation

### G21. Claims that are false or unsupported in the NEW state

**1. Weights and thresholds**  
- OLD claim: "blend weights 0.55 micro / 0.45 macro, thresholds +0.25/−0.05"  
- NEW truth: 0.80 micro / 0.20 macro, thresholds +0.20/−0.10  
- Verdict: Every mention of the old constants must be updated. This affects the architecture description, any methods table, and any passages citing the scoring formula.

**2. Primary accuracy headline**  
- OLD claim: "65.3% accuracy (62/95 graded events)"  
- NEW truth: 62.4% accuracy (68/109 graded events) — but see note on DIS_FQ1_2025 below  
- If DIS_FQ1_2025 is excluded (as it is in the clean N=232 universe): 62/95 becomes 62/95 under OLD; under NEW with SPOT+DIS exclusions the walkforward JSON reports (168 trades, 109 graded, 68 correct, 62.4%) for N=232. The correction is: **62.4% on 109 graded events from N=232**.

**3. Mean net per trade (overnight)**  
- OLD claim: "+1.862% mean net per trade"  
- NEW truth: +1.796% mean net per trade  
- Source: `ext2_holding_curve.csv` in NEW.

**4. Coverage vs selectivity framing**  
- OLD claim: The CLAUDE.md states accuracy 65.3% is the selectivity figure; coverage (HOLD=wrong denominator) was 42.2%.  
- NEW truth: selectivity 62.4% (68/109), coverage figure changes with new thresholds. The frontier table shows FLAT-excluded 47.9% (57/119 in eval split) and FLAT-as-wrong 41.4% (77/186 in eval split). These move in opposite directions; any dissertation claiming one "implies" the other is wrong.

**5. Trade count**  
- OLD claim: "146 trades" (from N=233)  
- NEW truth: 168 trades (from N=232, new thresholds)  
- Source: `item_e_walkforward.json` in NEW.

**6. Monotonic decay of returns**  
- OLD claim: "Mean net per trade decays monotonically from +1.86% (overnight) to +0.69% (10d), validating the overnight window as a measured choice and ruling out post-earnings drift."  
- NEW truth: The decay is non-monotonic. The 5-day mean (+0.937%) exceeds the 3-day mean (+0.830%), and the 10-day mean (+1.446%) is nearly as high as the overnight figure (+1.796%). The CLAUDE.md itself warns: "do not cite 'monotonic decay' at these constants." The post-earnings drift argument **cannot be made**; the curve matches the drift signature.  
- Source: `ext2_holding_curve.csv` in NEW.

**7. BUY/SELL asymmetry finding**  
- OLD claim: "BUY-truth recall 36.1% vs SELL-truth recall 32.5%; gap +3.6pp, not significant (z-test p=0.64, bootstrap CI [−8.7%, +16.7%]). Report as the null it is."  
- NEW truth: BUY-truth recall 51.4% vs SELL-truth recall 28.6%; gap +22.8pp, **significant** (z-test p=0.004). This is no longer a null result. The dissertation's claim of no asymmetry is wrong at the new constants.  
- Source: `asymmetry_recall_gap_test.csv` in NEW.

**8. Spearman rho (score magnitude vs return magnitude)**  
- OLD claim: "Spearman rho=0.111, p=0.070" (marginal, not significant at α=0.05)  
- NEW truth: rho=0.229, p=0.0002 (significant)  
- Source: `asymmetry_rank_correlation.csv` in NEW.

**9. Cohen's kappa**  
- OLD claim: κ=0.1092, 90% CI [0.030, 0.190]  
- NEW truth: κ=0.1421, 90% CI [0.055, 0.230]  
- Source: `kappa_near_independence.csv` in NEW.

**10. Clean universe N**  
- OLD claim: N=233 (25 worksheet + 1 SPOT + 9 timing excluded)  
- NEW truth: N=232 (25 worksheet + 2 bad-document [SPOT + DIS] + 9 timing excluded)  
- Every N=233 mention in the dissertation must be updated to N=232.

**11. Lowe's FQ1 duplicate event**  
- OLD: LOW_FQ1_2025 had report_date 2026-05-20 (duplicate of LOW_FQ1_2026); returns for LOW_FQ1_2025 in OLD were the same as LOW_FQ1_2026 (a data error)  
- NEW: LOW_FQ1_2025 corrected to 2025-05-21, different returns  
- Any citation of the Lowe's FQ1 2025 trade specifically is wrong in OLD.

**12. Section ablation finding**  
- OLD claim: "Full bundle wins marginally: 6.8pp at p=0.055 on the inclusive paired test vs press_release. Prepared_remarks is arguably the better deployment arm."  
- NEW truth: At the new thresholds, the finding narrative changes. The new comment in the CSV states "arms are indistinguishable at this sample size; indistinguishability is itself the deployment answer." The 6.8pp figure is invalidated.

**13. Frontier table figures**  
- OLD: FLAT-excluded = 42.9% (51/119), FLAT-as-wrong = 44.1% (82/186)  
- NEW: FLAT-excluded = 47.9% (57/119), FLAT-as-wrong = 41.4% (77/186)  
- These move in opposite directions; the dissertation must not present them as if they are interchangeable.

**14. Cost breakeven**  
- OLD: breakeven (mean_net) 196 bps (N=233), breakeven (N=268 corrected) 207 bps  
- NEW: breakeven (mean_net) 190 bps (N=232), breakeven (N=268) 195 bps  
- The "spec claimed ~113 bps" note remains: that figure is still unverifiable from any repo artefact.

**15. Combined walk-forward figures (N=326)**  
- OLD: N=326, 178 trades, 109 graded, 72 correct, accuracy 0.6606, mean_net 1.75%  
- NEW: N=325, 221 trades, 127 graded, 81 correct, accuracy 0.6378, mean_net 1.72%  
- Any dissertation mention of "N=326" or the combined walk-forward figures must be updated.

**16. Extension gap file join key**  
- OLD: all extension analyses joined on `(ticker, report_date)` — this silently dropped re-anchored Hermes events  
- NEW: joined on `document_id` — fixes the silent data loss  
- Affected analyses: finbert_extension (graded 31→34), lm_baseline_extension (graded 29→34), section_ablation_extension, walkforward_combined  
- Any dissertation figures citing these analyses at N=93 extension must verify which vintage was used.

**17. Duke Energy release timing**  
- OLD: `release_timing = after_hours` for all 13 Duke events  
- NEW: `release_timing = pre_market` — the 8-K acceptance timestamp is a filing time, not an announcement time; the press releases state results before the morning session  
- This changes the entry close for all 13 Duke events in the extension. Any figures citing Duke Energy specifically are affected.

**18. Ensemble consistency finding**  
- OLD workbook correction log: "four instances" of safeguards built but never run; the fourth was the ensemble consistency path  
- NEW workbook correction log: "three instances" — the ensemble instance is removed from the log  
- If the dissertation cites "four instances," it should cite "three instances" in NEW; alternatively, if the ensemble non-invocation is specifically discussed, confirm which version of the log applies.

**19. Human-vs-LLM paired statistics (directly from VERIFY_EXPECTATIONS table)**  

At OLD constants (0.55/0.45, +0.25/−0.05), N=171 paired:  
- LLM BUY 42, HOLD 69, SELL 60  
- LLM graded 58, LLM correct pooled 40  

At NEW constants (0.80/0.20, +0.20/−0.10), N=171 paired:  
- LLM BUY 73, HOLD 53, SELL 45  
- LLM graded 70, LLM correct pooled 44  
(After LOW_FQ1_2025 Lowe's fix: LLM graded 57 / LLM correct pooled 39 under OLD; 70/44 under NEW)

If DIS_FQ1_2025 is also excluded from the paired set (N=170): all BUY figures fall by 1.

---

## Appendix: Summary of Numerical Changes

### Primary headline figures

| Metric | OLD (arp-master-4) | NEW (arp-master-5) |
|--------|-------------------|-------------------|
| Weights | (0.55, 0.45, 0.0, 0.0) | (0.80, 0.20, 0.0, 0.0) |
| Hold thresholds | +0.25 / −0.05 | +0.20 / −0.10 |
| N clean events | 233 | 232 |
| N trades | 146 | 168 |
| N graded | 95 | 109 |
| N correct | 62 | 68 |
| Selectivity | 65.3% | 62.4% |
| Mean net/trade (overnight) | +1.862% | +1.796% |
| Rho (|score| vs |return|) | 0.111 (p=0.07) | 0.229 (p=0.0002) |
| BUY/SELL recall gap | +3.6pp (p=0.64) | +22.8pp (p=0.004) |
| Cohen's kappa | 0.109 | 0.142 |
| Frontier FLAT-excluded | 42.9% | 47.9% |
| Frontier FLAT-as-wrong | 44.1% | 41.4% |
| Monotonic decay | YES | NO |
| Breakeven (mean_net, N=232) | 196 bps | 190 bps |

### Exclusion set

| Category | OLD | NEW |
|----------|-----|-----|
| Worksheet contamination | 25 | 25 (unchanged) |
| Bad-document | 1 (SPOT) | 2 (SPOT + DIS) |
| Timing unresolved | 9 | 9 (unchanged) |
| **Total excluded** | **35** | **36** |
| **Clean N** | **233** | **232** |
