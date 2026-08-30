# Surviving findings after all corrections

Date: 2026-08-13 (updated 2026-08-12 with Item E walk-forward outcome)

Six corrections have been applied: stale entry anchor (4 retracted findings),
wrong baseline comparator, and the direction decomposition retraction
(tautological, not a finding). Item E (walk-forward validation) has now been
run and its outcome is incorporated into every threshold-dependent finding
below. This document lists every result that stands.

## 1. Rank correlation with monotonic decay (strongest)

**Statistic**: Spearman rho = 0.236, p = 0.0003, on all 233 clean events.
Decays monotonically: 0.159 (1d, p=0.015), 0.112 (3d, p=0.089), 0.072
(5d, p=0.276), 0.058 (10d, p=0.380). Bootstrap CI on mean net per trade
(raw direction-signed returns, no SPY component) crosses zero between 3
and 5 days: 3d lower bound +0.029%, 5d lower bound −0.270%.

**Threshold-dependent?** No. Rho uses the continuous blended score and the
continuous return. No band, no BUY/SELL/HOLD split, no grading threshold.

**Why corrections did not touch it**: rho does not depend on the entry
convention (it uses the same returns_matrix as everything else, which was
rebuilt on the corrected anchor) but it was recomputed on the corrected
matrix and improved from 0.221 to 0.236. It is not sensitive to the HOLD
threshold because it uses all 233 events, not just traded ones.

**Note on excess-over-SPY**: the decay finding is on raw direction-signed
mean net per trade. The `excess_*` columns in `returns_matrix.csv` are a
separate per-event diagnostic (stock return minus SPY return at that
horizon) and are not used in this computation. The excess series is not
monotonic across horizons, which does not contradict this finding: the
non-monotonicity reflects SPY's own multi-horizon return pattern across
the 146 traded events' specific entry dates, not anything about the model
signal. As an illustration: removing the 25 worksheet-contaminated events
(disproportionately high-weight technology names — NVDA, AMD, TSLA, META,
AMZN) changed the composition of the 146 trading dates and therefore the
SPY benchmark at those dates, moving the 10-day excess figure from −0.076%
to +1.466% with no change to the underlying signal or raw returns.

## 2. Selectivity accuracy (qualified — not verifiable OOS)

**Statistic**: 62/95 = 65.3%, vs 54.7% majority-direction floor (52/95),
margin +10.5pp, p=0.024 (binomial). MDE = ±10.8pp (barely powered to
detect). Source: `ext2_holding_curve.csv` (overnight row, N=233),
`item_e_walkforward.json` (n_graded=95, n_correct=62).

**Must always be paired with the coverage figure**: 62/147 = 42.2% under
HOLD=wrong, 12.2pp below the 54.4% floor (80/147 always-DOWN).

**Threshold-dependent?** Yes. The HOLD thresholds (+0.25/-0.05) determine
which 95 of 233 events are graded. Those thresholds were selected by
optimising compounded total return on the full dataset (in-sample,
PSR=0.0). The 95-event denominator is itself a product of in-sample
threshold selection.

**Item E outcome (updated 2026-08-14 with N=326 combined run)**: Walk-forward
threshold refitting degenerates at N=233, and the two objectives degenerate
for different reasons that do not resolve at N=326.

*Mean-net maximisation* (the study's headline P&L metric): fits extreme
thresholds (hu=0.45 / hl=−0.50) producing 5–7 training trades in 3 of 4
windows at N=233, and still 3 of 4 at N=326 (train N=203, 271, 321). The
fitted thresholds do not move as N increases. Trading rarely maximises the
mean-net objective, so the grid is structurally drawn to near-zero trade
rates regardless of sample size. **This objective will not become estimable
by adding data.**

*Directional-accuracy maximisation* (with 15% minimum trade fraction): degenerates
in 2 of 4 windows at N=233, improving to 1 of 4 at N=326. Pooled OOS at
N=326: 37 trades, 17/25 graded correct, accuracy 68.0%, floor 53.4%, gap
+14.6pp, mean net +1.79%, 90% CI [+0.12%, +3.49%]. The interval just clears
zero at the lower bound. MDE ≈ 30pp (scaling from the cross-issuer MDE of
20.8pp at n_graded=52; n_graded here is 25). The observed gap of 14.6pp is
roughly half the MDE. **Directionally consistent but underpowered — this is
not validation.** The result is also retrospective: all 326 events were seen
before this analysis, so it cannot be presented as out-of-sample in the
pre-registered sense. On the observed trajectory (degeneracy falling from 2/4
to 1/4 adding 93 events), full non-degeneracy for the accuracy objective would
plausibly require N ≈ 400–500. That is an extrapolation from two data points,
not an estimate.

This objective *does* respond to sample size and *is* the one to extend; the
mean-net objective is not. **The threshold selection procedure behind the
deployed 65.3% cannot be executed honestly at either N.** Significant
in-sample at p=0.024, and not verifiable out of sample at current N.

**Cross-issuer generalisation** (finding #3): 101 events from 29 issuers
scored after the N=161 threshold sweep, zero issuer overlap with the 40
in-sweep issuers. Under the deployed thresholds: 33/52 graded correct =
63.5%, vs always-DOWN floor 51.9% (27/52), margin +11.5pp, p=0.063 (MDE ±20.8pp).
This tests issuer transfer, not temporal generalisation (both subsets span
overlapping dates). Reconstructed subset — see finding #3 for the full
qualification.

**Fragility statement**: the in-sample margin is significant but sits at
the detection limit. The cross-issuer margin is comparable in magnitude
(+11.5pp) but not significant (p=0.063, N=52). A modestly smaller true
effect would have been undetectable at either sample size.

## 3. Cross-issuer generalisation (reconstructed subset)

**Statistic**: Thresholds fitted on 40 issuers (132 clean events) transfer
to 29 unseen issuers (101 clean events, `item_e_walkforward.json`): 33/52 graded correct = 63.5%,
vs always-DOWN floor 51.9% (27/52), margin +11.5pp, p=0.063
(MDE ±20.8pp). Mean net per trade: +2.785%.

**This is a cross-issuer test, not a temporal one.** The 101 post-sweep
events are entirely new issuers — zero issuer overlap with the 40
in-sweep issuers. Both subsets span overlapping date ranges (in-sweep:
2023-04-25 to 2026-07-14; post-sweep: 2024-07-31 to 2026-07-01; 37
same-day reports from different issuers). The two subsets are interleaved
in time, not sequential.

**Does not corroborate the temporal findings.** The walk-forward
(finding #2's degeneracy result) and the dev/eval split (finding #9)
test whether thresholds generalise across time. This tests whether they
generalise across issuers. Three results on two different axes should
not be presented as three lines of agreement. The temporal axis
(walk-forward) degenerates; the cross-issuer axis shows a directionally
consistent but non-significant margin.

**Confound**: because the two subsets overlap in time, an issuer-coverage
effect and a temporal effect cannot be separated. The result is consistent
with both "the thresholds transfer to new companies" and "the thresholds
work on later quarters" — the design cannot distinguish these.

**Threshold-dependent?** Yes — the deployed thresholds determine which of
the 101 events are graded. But unlike finding #2, the thresholds were not
selected on these events, so the threshold-dependency is for grading only,
not for selection.

**Qualification — reconstructed, not recorded**: The N=161 sweep
(`experiments/phase2_pnl_weight_threshold_sweep.py`) predates this
repository's git history. No recorded event list or calibration file from
that commit survives. Sweep membership is inferred from: (a) the sweep
JSON records `n_documents=161` but no event list; (b) the first 40
issuers in `PHASE2_ISSUERS` produce exactly 161 events, matching the
sweep's recorded count; (c) zero issuer overlap between the first 40 and
the later 29; (d) the 101 post-sweep events are entirely new issuers, not
new quarters of existing issuers. However, the count match is weak
evidence: 453 single-swap alternative sets of 40 issuers also produce
exactly 161 events (any same-count issuer can be swapped without changing
the total). The identification relies primarily on the assumption that
issuers were onboarded in `PHASE2_ISSUERS` list order, which is plausible
but unverifiable. The result is therefore labelled a **reconstructed
cross-issuer generalisation subset**, weaker than one recovered from a
recorded event list.

**Interpretation**: The margin (+11.5pp) is comparable in magnitude to
the in-sample figure (+10.5pp, finding #2), which is the pattern expected
if the deployed thresholds capture a real effect. But p=0.063 does not
clear 0.05, and the MDE (±20.8pp) shows this subset was underpowered.
Report as directionally consistent, not confirmed.

## 4. Item C: section ablation token ratio

**Statistic**: press release at ~13k tokens achieves 62.5% accuracy
(35/56 graded, HOLD-excluded, on its own graded set, N=200) vs full
bundle at ~30k tokens at 65.7% (46/70 graded). Cost per correct call:
$0.029 (PR) vs $0.046 (full). On the four-arm subset (N=119, all arms
scored), per-arm accuracy is 64.9% (PR, 24/37) vs 68.1% (full, 32/47),
cost $0.0225 vs $0.0358. Full bundle wins 6.8pp on the inclusive paired
test (p=0.055, n=66 four-arm events), driven by 17 events the PR passes
on. Prepared remarks agrees with full bundle on 85.7% of signals at ~10k
tokens. Source: `section_ablation_cost_per_correct.csv` (per-arm
accuracy and cost), `section_ablation_paired_diffs.csv` (paired test),
`section_ablation_results.csv` (per-call tokens and costs).

**Threshold-dependent?** The accuracy figures are threshold-dependent
(same qualification as #2, including the Item E walk-forward outcome:
threshold refitting degenerates at this N). The token ratio and cost per
correct call are not — they are properties of the documents, not the
grading convention.

**Why corrections did not touch it**: Item C was scored and graded on the
corrected returns_matrix. The model version (deepseek-v4-flash) matches
the deployed runs.

## 5. Kappa near-independence (human vs model)

**Statistic**: Cohen's kappa = 0.109, 90% CI [0.030, 0.190], N=171
paired events. Recomputed 2026-08-13 on the N=233 clean universe
(section=All, first_rater_for_event=YES, in_llm_universe=YES; LLM
decision from `blend_predicted_signal_default`). The human and LLM arms
are close to independent — their directional calls share barely more
structure than two independent classifiers with their marginals (human
BUY 56.1% (96/171), LLM BUY 24.6% (42/171)). Observed agreement 38.0%
(65/171), expected 30.4% (52/171).

**Backing**: `kappa_near_independence.csv` (3x3 confusion matrix, both
arms' marginals, observed/expected agreement, kappa, bootstrap CI, subset
definition).

**Prior values**: 0.107 (CI [0.027, 0.188]) reported in
`retracted_findings_2026-08-12.md` — close but console-only, no backing
CSV. 0.113 (CI [0.036, 0.191]) in `worksheet_leak_triage.md` — different
computation on a different N. Both superseded by the CSV-backed 0.109.

**Threshold-dependent?** No. Kappa compares the BUY/HOLD/SELL calls
directly, not graded outcomes.

## 6. Direction-only comparison (human vs model)

**Statistic**: on 76 events where both arms committed, human 57.9%
(44/76) vs LLM 60.5% (46/76), diff +2.6pp, p=0.750. Neither detectably
better. Source: `human_vs_llm_statistics.csv` (all statistics),
`human_vs_llm_corrected.md` (prose). Computing script:
`experiments/human_vs_llm_backing.py`.

**Against the majority-direction floor**: always-DOWN = 55.3% (42/76).
Human +2.6pp (p=0.366), LLM +5.3pp (p=0.210). **Neither arm beats the
majority-direction floor by a testable margin.** The null stands.

**Threshold-dependent?** No. Uses sign accuracy, no band.

## 7. SELL-versus-BUY asymmetry (a finding in its own right)

Source: `human_vs_llm_direction_decomposition.csv` (per-direction table),
`human_vs_llm_statistics.csv` (all statistics).
Computing script: `experiments/human_vs_llm_backing.py`.
P-values are one-sided binomial tests (alternative=greater).

Both arms show skill on SELL calls and neither shows skill on BUY calls:

| Arm | Call | Accuracy | N | vs 50% (p) | vs overall base rate (p) |
|---|---|---|---|---|---|
| Human | BUY | 50.9% (27/53) | 53 | +0.9pp (0.500) | +7.5pp vs 43.4% (0.167) |
| Human | SELL | **73.9%** (17/23) | **23** | **+23.9pp (0.017)** | +17.3pp vs 56.6% (0.069) |
| LLM | BUY | 55.6% (20/36) | 36 | +5.6pp (0.309) | +12.1pp vs 43.4% (0.097) |
| LLM | SELL | **65.0%** (26/40) | **40** | **+15.0pp (0.040)** | +8.4pp vs 56.6% (0.181) |

Reading earnings documents supports identifying trouble more reliably than
confirming strength. Both arms clear 50% on SELL calls (human p=0.017,
LLM p=0.040) and neither reliably clears 50% on BUY calls (human p=0.500,
LLM p=0.309).

Against the overall base rate (56.6% negative) rather than 50%, the SELL
margins fall to p=0.069 (human) and p=0.181 (LLM). The defensible
statement is that both arms clear chance on SELL calls and neither
reliably clears the base rate in either direction.

**Caveat on N**: the human SELL cell is 23 events and cannot carry much
weight; the LLM SELL cell at 40 is more credible. The human BUY cell
(53 events) has the most power but shows no signal.

**Connection to earlier observations**: the model was noted to have
"downside blindness" while the human arm is "directionally optimistic"
(56.1% BUY calls). This asymmetry is now measured: the human arm's value
concentrates in its minority SELL calls (73.9%, N=23), not its majority
BUY calls (50.9%, N=53). The LLM distributes skill more evenly but
achieves it on SELL rather than BUY.

**Threshold-dependent?** No. Uses sign accuracy, no band.

## 8. Supplementary re-score of 25 contaminated events

**Statistic**: 12/25 (48%) changed their directional call once the
worksheet was removed. Re-scored accuracy 66.7% (12/18 graded) resembles
the clean set (65.3%), corroborating the exclusion.

**Threshold-dependent?** Yes (grading uses the HOLD threshold). Same
walk-forward qualification as finding #2.

## 9. Dev/eval split (subset stability, not a result)

**Statistic**: eval accuracy 68.0% (51/75) clears its always-DOWN floor
of 54.6% (65/119) by +13.4pp (p=0.013, MDE=±14.4pp). Dev accuracy
55.0% (11/20) does not clear its own floor of 53.6% (+1.4pp,
MDE=±27.8pp — underpowered
to detect any plausible effect). The finding is that the model clears the
floor on later events and cannot be shown to do so on earlier ones, not a
clean comparison between two halves. Split rule: sort 233 clean events by
release_date (`returns_matrix.csv`), earliest 20% (47 events) = dev,
remaining 80% (186 events) = eval. Source: `frontier_table.csv` (eval
graded N=119, of which 75 traded+graded).

**Not a result**: the dev-eval difference is not significant.

**Not out-of-sample**: the dev/eval split was applied post hoc to data
the deployed thresholds were already fitted on. The eval split's 68.0%
is an in-sample figure computed on a subset of the same events the
threshold sweep saw. It shows subset stability (the fitted thresholds
are not concentrated on early events), not generalisation. Finding #3
(33/52 = 63.5%, p=0.063) tests cross-issuer transfer, not temporal
generalisation — both this dev/eval split and finding #3 are suggestive
but neither provides a clean temporal OOS test (the walk-forward
degenerates at this N).

## What did not survive

1. 72.7% band capture → 42.4% (anchor artefact)
2. 61% sign-correct p=0.064 → 56% p=0.480 (anchor artefact)
3. PM 70.8% vs AH 65.1% accuracy divergence → vanished (anchor artefact)
4. +17.3pp agreement filter → -0.3pp (anchor artefact)
5. ~39% baseline → 54.7% majority-direction (comparator error)
6. "Zero per-direction margin" → tautological (not a finding)

## The threshold qualification, stated once

The deployed HOLD thresholds were selected by optimising compounded total
return — a metric the study no longer reports — on the full dataset the
study then scores. PSR=0.0, permutation p=0.150. The thresholds are not
pre-registered. The 95-event graded denominator is itself a product of
in-sample threshold selection.

**Every figure that depends on the HOLD threshold** (selectivity accuracy,
mean net per trade, the graded N, Item C per-arm accuracy) carries this
qualification.

**Item E outcome — the two objectives degenerate for different reasons
(updated 2026-08-14 with N=326 combined run)**:

Walk-forward threshold refitting degenerates at N=233, and the behaviour
at N=326 reveals that the two objectives are not equivalent failures.

1. **Mean-net maximisation**: structurally degenerate. Fits hu=0.45/hl=−0.50
   (near-zero trade rate) in 3 of 4 windows at both N=233 and N=326. The
   fitted thresholds do not change as training N grows from 146 to 321. This
   is because trading rarely maximises the mean-net objective — a wide
   hold-band that produces almost no trades tends to win in-sample. **This
   objective will not become estimable by adding data.**

2. **Directional-accuracy maximisation**: sample-limited. Degenerates in
   2 of 4 windows at N=233, 1 of 4 at N=326. Pooled OOS at N=326 is 37 trades,
   accuracy 68.0% (17/25 graded), floor 53.4%, mean net +1.79%, 90% CI
   [+0.12%, +3.49%]. Directionally consistent but underpowered: the gap
   (14.6pp) is roughly half the MDE (≈30pp). **This objective responds to
   sample size.** On the observed trajectory, full non-degeneracy would
   plausibly require N ≈ 400–500 (extrapolation from two data points, not
   an estimate).

Both objectives degenerate at current N. The threshold selection procedure
behind the deployed 65.3% cannot be executed honestly at N=233 or N=326.
Every threshold-dependent figure in this study — selectivity accuracy, mean
net per trade, graded N, Item C per-arm accuracy — rests on a selection step
that does not survive honest replication at this N.

The N=326 OOS result (accuracy walk-forward, pooled) is also retrospective:
all 326 events were seen before the analysis. It cannot be presented as
out-of-sample in the pre-registered sense.

The deployed thresholds' performance on 101 genuinely unseen events
(29 issuers scored after the N=161 sweep, reconstructed cross-issuer
generalisation subset — see finding #3) is 33/52 = 63.5% (p=0.063 vs floor).
Directionally consistent but not significant at 0.05.

**Rho (finding #1) does not depend on the threshold** and is the only
headline that is clean of this qualification. That rho = 0.236 at
p = 0.0003 is why it, not the selectivity accuracy, is the study's
primary result.

## Stated limitations

**Consistency asymmetry (Set A vs Set B):** The frozen phase2 set (Set A, N=233) was scored with --ensemble runs, producing per-event consistency scores that allow output-stability cross-checks. The extension set (Set B, N=93) was not run with --ensemble; no consistency data exists for any of the 93 extension events. Any claim about output stability applies to Set A only. No comparison of ensemble consistency between sets is possible. Running the extension with --ensemble would cost approximately $0.77 (the same order as the original extension micro-layer run).
