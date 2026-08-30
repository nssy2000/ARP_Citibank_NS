# Figure Manifest

Generated: 2026-08-16 (final pass: all in-figure annotations removed, F1 arrow deleted)

All figures use the corrected release_date anchor (2026-08-12). N = 233 clean
events after excluding 25 worksheet contamination + 1 SPOT misattribution + 9
timing-excluded non-US issuers. Pre-registered grading band: +/-2% raw overnight.

Style: serif (Times New Roman / Nimbus Roman), 11 cm width, navy #013B70 /
red #D9261C / mid grey #808080 only. PDF vector + PNG 300 dpi.
No baked-in titles or annotations (LaTeX captions supply them). Colour semantics:
navy = model arm, red = human arm. Exceptions: F5 red = loss / navy = gain
(sign encoding); F11 red = SELL / navy = BUY / grey = HOLD (signal direction).

---

## Tier 1 (reserved slots in report)

### F1: Sample funnel
- **File:** `F1_sample_funnel.pdf`, `.png`
- **Source:** `effective_sample_funnel.md`, `ext2_holding_curve.csv`, `results_three_sets.csv`
- **Values:** 268 -> 233 (minus 25 worksheet, 1 SPOT, 9 timing) -> 146 traded -> 95 graded -> 62 correct (65.3%)
- **HOLD limb:** 87 HOLD events (37.3%), of which 52 had |ret| > 2% (graded moves missed)
- **In-figure:** Exclusion counts, "87 HOLD (37.3%)" and "52 graded moves missed" (no arrow). Third-tier box label shortened to "Model traded". Canvas trimmed below final box.
- **Report section:** Methodology / Sample construction

### F2: Signal decay by holding horizon (two panels)
- **File:** `F2_rho_decay.pdf`, `.png`
- **Source (rho values, p-values, mean net, bootstrap CIs):** `ext2_holding_curve.csv`
- **Top panel:** Spearman rho: 0.236 (ON, p=0.0003) -> 0.159 (1d) -> 0.112 (3d) -> 0.072 (5d) -> 0.058 (10d). Fisher-z 90% CI band computed in plot script. No significance stars. Value labels show rho only (no stars).
- **Bottom panel:** Mean net per trade: 1.86% (ON) -> 1.25% (1d) -> 1.03% (3d) -> 0.85% (5d) -> 0.69% (10d). Bootstrap 90% CIs read from source. Value labels placed directly above/below their markers.
- **Removed from plot:** Significance stars, "Fisher-z 90% CI" note, "Bootstrap 90% CI" note, "CI crosses zero" annotation.
- **For LaTeX caption:** Fisher-z 90% CI computed from rho and n=233 using z = arctanh(rho), SE = 1/sqrt(n-3). Bootstrap 90% CI from source file. The bootstrap interval on mean net per trade crosses zero between 3d and 5d. The Fisher-z band on rho also reaches zero between 3d and 5d (lower bound 0.004 at 3d, -0.036 at 5d).
- **N:** 233 for rho (all clean events), 146 for mean net (traded events)
- **Report section:** Results / Holding-period analysis

### F3: Accuracy vs grading-band width
- **File:** `F3_band_sensitivity.pdf`, `.png`
- **Source:** `returns_matrix.csv` + `global_outcome_calibration_phase2.csv`, **recomputed in plot script**
- **Convention:** (a) strict > inequality
- **Six bands:** 0%, 1%, 2% (pre-registered), 3%, 4%, 5%
- **Values:** 145/62.8%, 120/64.2%, 95/65.3%, 71/67.6%, 61/68.9%, 52/71.2%
- **Axes:** Y-axis starts at zero (not 50). Right-hand axis carries graded-event count via diamond markers.
- **Report section:** Results / Sensitivity analysis

---

## Tier 2

### F4: Selectivity vs coverage accuracy
- **File:** `F4_selectivity_vs_coverage.pdf`, `.png`
- **Source:** `ext2_holding_curve.csv`, `results_three_sets.csv`
- **Values:** Selectivity 62/95 = 65.3% (floor 54.7%), Coverage 62/147 = 42.2% (floor 54.4%). Same 62 correct calls, different denominators.
- **Removed from plot:** "HOLD-excluded", "HOLD = wrong", "Pre-registered +/-2% overnight band".
- **For LaTeX caption:** Selectivity excludes HOLD events; coverage counts HOLD as wrong. Pre-registered +/-2% overnight grading band.
- **Report section:** Results / Accuracy interpretation

### F5: Per-trade return distribution
- **File:** `F5_return_distribution.pdf`, `.png`
- **Source:** `returns_matrix.csv` + `global_outcome_calibration_phase2.csv`, **recomputed in plot script** (net returns: BUY -> ret-0.001, SELL -> -ret-0.001)
- **Values:** 146 trades. 6 open-ended buckets: <-10%, -10 to -5, -5 to 0, 0 to 5, 5 to 10, >+10%. Counts: 2, 13, 41, 55, 21, 14. Mean and median in legend.
- **Removed from plot:** "n = 146 trades", "Colour encodes sign (loss/gain), not arm".
- **For LaTeX caption:** n = 146 trades. Colour encodes sign (red = loss, navy = gain), not arm.
- **Report section:** Results / P&L analysis

### F6: Baseline frontier
- **File:** `F6_baseline_frontier.pdf`, `.png`
- **Source:** `frontier_table.csv`
- **Values (eval split, N=186, 119 graded, coverage convention):**
  - Majority direction: 65/119 = 54.6% (CI [47.1%, 62.2%])
  - Loughran-McDonald: 18/119 = 15.1% (CI [10.1%, 21.0%]), 59 trades
  - FinBERT: 41/119 = 34.5% (CI [27.7%, 42.0%]), 147 trades
  - Deployed model: 51/119 = 42.9% (CI [35.3%, 50.4%]), 111 trades
- **Removed from plot:** "majority floor" text label (dashed line retained).
- **For LaTeX caption:** Dashed line = majority-direction floor (54.6%).
- **Report section:** Results / Baseline comparison

### F7: MDE vs observed effect
- **File:** `F7_mde_vs_observed.pdf`, `.png`
- **Source:** `results_three_sets.csv`, `surviving_findings.md`, `effective_sample_funnel.md`, `section_ablation_paired_diffs.csv`
- **6 comparisons (from Table 3):**
  - Selectivity vs floor (n=95, +10.5pp, MDE 10.8pp)
  - Extension vs frozen 65.3% (n=14, +6.2pp, MDE 31.6pp)
  - Section ablation paired (n=45-53, -6.8pp worst arm, MDE 12pp)
  - Model vs human dir. (n=76, +2.6pp, MDE 23pp)
  - Walk-forward OOS vs floor (n=25, +14.6pp, MDE 30pp)
  - Cross-issuer subset (n=52, +11.5pp, MDE 21pp)
- **Figure width:** 1.35x standard (wider to prevent tick-label collisions).
- **Report section:** Methodology / Statistical power

### F8: BUY/SELL asymmetry
- **File:** `F8_buy_sell_asymmetry.pdf`, `.png`
- **Source:** `human_vs_llm_direction_decomposition.csv`
- **Values (N=76 paired direction events, sign accuracy, no band):**
  - LLM BUY: 20/36 = 55.6%, LLM SELL: 26/40 = 65.0%
  - Human BUY: 27/53 = 50.9%, Human SELL: 17/23 = 73.9%
  - Base rates: BUY-outcome 43.4%, SELL-outcome 56.6%
- **Colour:** Navy = LLM (model), Red = Human. Wilson 90% CIs on each bar. Legend below plot in horizontal row (outside axes).
- **Report section:** Results / Directional decomposition

### F9: Section ablation
- **File:** `F9_section_ablation.pdf`, `.png`
- **Source:** `section_ablation_cost_per_correct.csv`, `section_ablation_paired_diffs.csv`, `section_ablation_results.csv`
- **Values (four-arm N=119, selectivity):**
  - Full bundle: 32/47 = 68.1%, $0.0358/correct
  - Press release: 24/37 = 64.9%, $0.0225/correct, 72.3% agreement
  - Prepared remarks: 26/41 = 63.4%, $0.0208/correct, 85.7% agreement
  - Q&A only: 26/38 = 68.4%, $0.0229/correct, 71.4% agreement
- **Removed from plot:** "Strict paired n: press 45, prepared 53, Q&A 43; all diffs inside MDE".
- **For LaTeX caption:** Strict paired n: press 45, prepared 53, Q\&A 43. All diffs inside +/-12pp MDE.
- **Report section:** Results / Section ablation

### F10: Latency distribution
- **File:** `F10_latency_distribution.pdf`, `.png`
- **Source:** `outputs/p2_*/logs/first_run_costs.jsonl` (all issuers with JSONL logs)
- **Values:** n=624 calls (status=success, latency_seconds not null). Median=15.0s, Mean=15.92s, Q1=12.95s, Q3=17.31s (cross-verified against `model_latency_2026-08-15.csv`).
- **Line styles:** Median = navy solid, Mean = grey dotted.
- **Removed from plot:** Stats text box (n, Q1, Q3, IQR, outlier count).
- **For LaTeX caption:** n = 624 calls. Q1 = 12.95s, Q3 = 17.31s, IQR = 4.36s. Outliers > 60s clipped from histogram.
- **Report section:** Results / Efficiency

### F11: Blended score vs overnight return scatter
- **File:** `F11_score_vs_return.pdf`, `.png`
- **Source (layer scores):** `micro_score` and `macro_score` columns from `global_outcome_calibration_phase2.csv`
- **Source (returns):** `ret_overnight` column from `returns_matrix.csv`
- **Blended score:** Recomputed in plot script via `blend.blend_scores(micro, macro, None, None, DEFAULT_WEIGHTS)`. Verified: rho = 0.236, p = 0.000279, n=233.
- **OLS trend line:** Fitted in plot script for visual reference only.
- **Removed from plot:** Rho/p-value/n text box, "Colour encodes signal direction, not arm" note.
- **For LaTeX caption:** Spearman rho = 0.236 (p = 0.0003, n = 233). Score recomputed via blend.blend\_scores(). Colour encodes signal direction (navy = BUY, red = SELL, grey = HOLD), not arm.
- **Report section:** Results / Rank correlation

### F13: Accuracy by move magnitude
- **File:** `F13_accuracy_by_magnitude.pdf`, `.png`
- **Source:** `returns_matrix.csv` + `global_outcome_calibration_phase2.csv`, **recomputed in plot script**
- **3 buckets:** 2-5%, 5-10%, >10% absolute overnight return (traded+graded events)
- **Values:** 2-5%: 25/43=58.1%; 5-10%: 23/36=63.9%; >10%: 14/16=87.5% (n=16, hatched)
- **Removed from plot:** "* Hatched: n = 16 (interpret with caution)".
- **For LaTeX caption:** Hatched bar: n = 16 (interpret with caution).
- **Report section:** Results / Move-size analysis

---

## Tier 3

### F12: Confusion matrix (human vs LLM)
- **File:** `F12_confusion_matrix.pdf`, `.png`
- **Source:** `kappa_near_independence.csv`
- **Values:** 3x3 matrix, N=171 paired events. Kappa = 0.109 (90% CI [0.030, 0.190]).
- **Colour ramp:** Navy (near-white #F0F4F8 to full #013B70).
- **Removed from plot:** "N = 171 paired events, kappa = 0.109, 90% CI [0.030, 0.190]".
- **For LaTeX caption:** N = 171 paired events. Cohen's kappa = 0.109 (90\% CI [0.030, 0.190]).
- **Report section:** Results / Human-model agreement

---

## Derived quantities (computed in plot script, not read from source files)

Every value below was computed in `figures/plot_all_figures.py` during this
session. None comes from a pre-existing output file.

| Figure | Quantity | Method | Inputs |
|--------|----------|--------|--------|
| F2 (top panel) | Fisher-z 90% CI band on rho at each horizon | `z = arctanh(rho)`, `SE = 1/sqrt(n-3)`, back-transform | rho from `ext2_holding_curve.csv`, n=233 |
| F3 | All 6 accuracy/n_graded values | Strict > inequality on `abs(ret_overnight) > band` for traded events | `returns_matrix.csv` + `global_outcome_calibration_phase2.csv` (blend_predicted_signal_default) |
| F5 | Net return per trade, bucket counts, and histogram | `BUY: ret-0.001`, `SELL: -ret-0.001`; open-ended bins | `returns_matrix.csv` + `global_outcome_calibration_phase2.csv` |
| F8 | Wilson 90% CIs on each bar | `wilson_ci(k, n, z=1.645)` | Counts from `human_vs_llm_direction_decomposition.csv` |
| F11 | Continuous blended score for all 233 events | `blend.blend_scores(micro, macro, None, None, DEFAULT_WEIGHTS)` | `micro_score`, `macro_score` from `global_outcome_calibration_phase2.csv` |
| F11 | OLS trend line | `numpy.polyfit(scores, rets, 1)` | Blended scores and overnight returns |
| F13 | Accuracy per magnitude bucket | Same strict > grading as F3, bucketed by `abs(ret_overnight)` | `returns_matrix.csv` + `global_outcome_calibration_phase2.csv` |
