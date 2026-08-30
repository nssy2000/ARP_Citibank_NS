# Item E Handoff — Walk-Forward Validation

Status: **Complete.** See `experiments/walkforward_validation.py` and
`outputs/global/summary/item_e_walkforward.json`.

## Anchor correction (2026-08-12)

`release_date` (EDGAR 8-K filing date) is now the **sole entry anchor** for all
events. `report_date` is retained as a historical label (fiscal period identifier,
manifest key) but no longer drives the entry price. The uniform entry rule is:
- `pre_market` events: open on `release_date`
- `after_hours` events: open on the trading day after `release_date`

This correction affected ~42 pre_market events and is a prerequisite for any
walk-forward that trains on returns. Four findings from the old anchor are
retracted; see `retracted_findings_2026-08-12.md`.

## Exclusion set (N=233 clean universe)

35 events excluded from the graded universe:

| Reason | Count |
|---|---|
| Worksheet events (pending re-score decision) | 25 |
| SPOT (single-event outlier excluded by consensus) | 1 |
| Timing unresolved (9 non-US issuers) | 9 |
| **Total excluded** | **35** |

Remaining: **233 clean events**, of which **146 are traded** (BUY or SELL signal)
and **95 are graded** (traded + outcome resolved).

LMT was initially set to null pending manual verification, then resolved as
`pre_market` (press release confirmed pre-open) and **recovered into N=233**.
LMT cannot join Item C (section ablation) because its documents were not
bundled into the section-level variant set.

## Corrected performance figures (post anchor correction, N=233)

These supersede all figures quoted before 2026-08-12.

| Metric | Value |
|---|---|
| Clean events | 233 |
| Traded | 146 |
| Graded (traded + resolved) | 95 |
| Accuracy (graded) | **65.3%** (62/95) |
| Majority-direction floor (graded) | 54.7% (always-DOWN, 52/95) |
| Mean net per trade | **+1.862%** |
| Summed total return (146 trades) | **+271.81%** |
| t-statistic (mean / pstdev × √N, N=146) | **3.43** |
| Info ratio per trade | **0.284** |
| Spearman rho (overnight, all 233 events) | **0.236** |
| Spearman p-value | **0.0003** |

Note: the "t = 3.43" figure is a t-statistic computed as
`mean_net / pstdev(nets) * sqrt(N_traded)`, not a Sharpe ratio. Do not label
it Sharpe in any write-up.

## What Items B and C concluded

### Item B — horizon decay

Monotonic decay from overnight to 10-day window. The bootstrap CI crosses zero
by day 3. This validates the overnight window as the correct primary horizon and
supports using it as the walk-forward's test metric.

### Item C — section ablation (document composition)

Full bundle marginally outperforms press-release-only on signal accuracy
(6.8 pp gap, p = 0.055 — not significant at 0.05 but directionally consistent).
Full bundle costs approximately 2.3× the tokens of press-release-only.

Cost-efficiency framing (all-events, N=200; source: `section_ablation_cost_per_correct.csv`):
- Press release only: **$0.029 per correct prediction** (35/56 graded = 62.5%)
- Full bundle: **$0.046 per correct prediction** (46/70 graded = 65.7%)

Prepared remarks agrees with the full bundle on **85.7%** of signals — the
marginal contribution of adding the transcript/Q&A is small. Report as a
borderline, cost-efficiency-unfavourable result for full bundle, not a clean win.

LMT cannot join Item C (see Exclusion set above).

## Human comparison

Direction-only comparison on **76 events** (events where a human rater
submitted a direction):

| Rater | Accuracy | N |
|---|---|---|
| Human | 57.9% | 76 |
| LLM | 60.5% | 76 |
| Always-BUY baseline | 43.4% | 76 |

Gap: +2.6 pp in favour of LLM. **Not significant** (p = 0.754). Both beat the
always-BUY baseline. Do not claim LLM superiority from this result.

## Recalibrated longer-horizon bands

Longer-horizon (3d, 5d, 10d) bands were recalibrated after the anchor
correction. These are **secondary and not pre-registered** — they exist for
descriptive completeness only. The overnight window remains the primary
pre-registered metric.

## Retracted findings

Four findings from the pre-anchor-correction analysis are formally retracted.
See `outputs/global/summary/retracted_findings_2026-08-12.md` for the full
list with original values and the reason each was retracted.

## Threshold selection criterion (critical for Item E)

The deployed thresholds `hold_upper=+0.25` / `hold_lower=-0.05` were selected
by `experiments/phase2_pnl_weight_threshold_sweep.py`, objective = **total
return** (in-sample), from a 113,344-combo grid. The sweep measured PSR=0.0
and permutation p=0.150 — the combo **failed the project's own overfitting
checks** and was promoted on 2026-08-05 by explicit user decision overriding
the validity gates.

**Not pre-registered.** All events were scored before the sweep was run.
The freeze note (`ext1_freeze_note.md`, dated 2026-08-10) is explicitly
labelled "retrospective not pre-registered".

`-0.05` is the minimum value of the `THRESH_LOWER` grid (0.05 step), not
a principled choice. The sweep found the least-aggressive lower threshold
maximised in-sample total return.

**Consequence**: the deployed HOLD thresholds were selected by optimising a
metric the study no longer reports (compounded total return, retired as
order-dependent), on data the study then scores (in-sample, all events
seen). The 95-event graded denominator is itself a product of in-sample
threshold selection. Every figure that depends on the HOLD threshold
(selectivity accuracy 65.3%, mean net per trade, graded N) carries this
qualification.

**Item E is therefore the load-bearing robustness test, not a supplementary
one.** Refitting thresholds out of sample is the only check on whether the
65.3% survives without in-sample selection. The only headline that is clean
of this qualification is rho = 0.236 (p = 0.0003), which does not depend
on the threshold.

**Item E objective (user decision, dated 2026-08-13):**

Item E refits `hold_upper` and `hold_lower` on each training window by
maximising **mean net per trade**, not summed total return and not compounded
total return. Mean per trade is the study's headline P&L metric, it is
order-independent, and it does not scale with the number of trades in a
window, which matters because window sizes differ.

This **differs from the deployed selection objective** (compounded total
return, now retired as order-dependent and unachievable). The deployed
objective is no longer available. Item E is therefore not reproducing the
deployed threshold choice but testing whether any honestly-selected threshold
survives out of sample.

**Per-window reporting**: report both mean net per trade and directional
accuracy per window, so the choice of objective can be seen not to have
driven the result.

**Degenerate-window assertion** (from the gap spec): maximising mean net per
trade on a thin window can be gamed by taking almost no trades (one correct
trade gives mean=100%). Assert loudly if any window's trade count falls
below a floor (e.g. 5 trades), since a collapsing trade count means the
threshold went degenerate.

## Baseline correction (2026-08-13)

The correct naive floor for FLAT-excluded accuracy is the majority direction
among graded events: **always-DOWN = 54.7% (52/95)**. The previously used
~39% was always-BUY on all events including HOLDs — wrong denominator.

**Both accuracy framings, always reported together:**
- Selectivity: 62/95 = 65.3% (model traded + |ret|>2%). Above 54.7% floor,
  +10.5pp, p=0.024 — significant but at the detection limit (MDE=±10.8pp).
- Coverage: 62/147 = 42.2% (all |ret|>2%). Below 54.4% floor by 12.2pp.

**Direction-only decomposition**: on 76 paired events where both arms
committed, each arm's per-direction accuracy exactly equals the base rate in
its self-selected subset. Zero per-direction margin. Overall sign accuracy
comes from BUY/SELL allocation matching the sample's SELL skew, not from
document reading. See `direction_accuracy_decomposition.md`.

**Dev/eval split (directional evidence for Item E)**: dev accuracy 55.0%
(11/20), eval 68.0% (51/75). Split rule: sort 233 clean events by
release_date (returns_matrix.csv), earliest 20% (47 events) = dev,
remaining 80% (186 events) = eval. The model performs better on later
events — opposite of overfitting. Eval margin +13.4pp vs floor (p=0.013).
Dev too small (MDE=±23pp). This is the finding Item E exists to test
properly. Source: `frontier_table.csv` (eval), recomputed 2026-08-13 on
corrected returns_matrix.

## Item D (FinBERT baseline) — complete

Frontier on eval split (186 events, 119 graded FLAT-excluded, overnight ±2%):
- Majority-direction (always-DOWN): 54.6% (65/119)
- Deployed model: 42.9% (51/119, FLAT-excluded)
- FinBERT: 34.5% (41/119)
- Loughran-McDonald: 15.1% (18/119)

Note: the "42.9%" here is FLAT-excluded on the **eval split** (119 graded
out of 186 eval events). The "42.2%" in `surviving_findings.md` is the
full-sample coverage figure (62/147, all graded events in N=233). Both are
correct for their own purpose — the frontier uses the eval split to
maintain dev/eval discipline; the coverage figure pairs with the
full-sample selectivity accuracy (62/95 = 65.3%).

FinBERT narrows the gap to the model (34.5% vs 15.1% for LM) but the model's
advantage is real (8.4pp, non-overlapping CIs). The model's differentiation
is structured output and evidence quotes, not raw accuracy dominance.

## Item E outcome

### Degeneracy finding

Walk-forward threshold refitting degenerates at N=233. Two refit
objectives were tried:

1. **Mean net per trade**: selects extreme thresholds (+0.45/-0.50)
   producing 5-7 training trades and zero OOS trades in 3 of 4 windows.
2. **Directional accuracy** (with 15% minimum trade fraction): degenerates
   in 2 of 4 windows.

Both objectives degenerate. The threshold selection procedure behind the
deployed 65.3% cannot be executed honestly at this sample size. This
means any threshold-dependent figure (selectivity accuracy, mean net per
trade, graded N, Item C per-arm accuracy) rests on a selection step that
does not survive honest replication.

The blended score itself retains predictive content independent of any
threshold: rho = 0.236 at p = 0.0003. That is the study's primary result.

### Cross-issuer generalisation (reconstructed subset)

The deployed thresholds were selected at N=161 (the first 40 issuers).
29 issuers (101 clean events) were scored after the sweep and were never
in the sweep's dataset (2 further post-sweep issuers — Allianz and
Lenovo — are fully timing-excluded).

**This is a cross-issuer test, not a temporal one.** Both subsets span
overlapping date ranges (in-sweep: 2023-04-25 to 2026-07-14; post-sweep:
2024-07-31 to 2026-07-01; 37 same-day reports from different issuers).
The result tests whether thresholds transfer to new companies, not
whether they generalise to new time periods. It does not corroborate the
temporal findings (walk-forward degeneracy, dev/eval split).

**Reconstruction methodology**: The N=161 sweep predates this
repository's git history. No recorded event list or calibration file
from that commit survives. Sweep membership is inferred from: (a) the
sweep JSON records `n_documents=161` but no event list; (b) the first
40 issuers in `PHASE2_ISSUERS` produce exactly 161 events, matching
the sweep's recorded count; (c) zero issuer overlap between the first
40 and the later 31; (d) the 101 post-sweep events are entirely new
issuers, not new quarters of existing issuers. However, the count match
is weak: **453 single-swap alternatives** (any same-count issuer swap)
also produce exactly 161. The identification relies primarily on the
assumption that issuers were onboarded in list order. The result is a
**reconstructed cross-issuer generalisation subset**.

| Subset | N clean | Trades | Graded | Accuracy | Mean net |
|---|---|---|---|---|---|
| In-sweep (in-sample) | 132 | 76 | 43 | 67.4% (29/43) | +1.012% |
| Post-sweep (cross-issuer) | 101 | 70 | 52 | 63.5% (33/52) | +2.785% |
| Full sample | 233 | 146 | 95 | 65.3% (62/95) | +1.862% |

Post-sweep accuracy vs always-DOWN floor (51.9%): margin +11.5pp,
p = 0.063 (MDE ±20.8pp). Directionally consistent with the in-sample
figure but not significant at 0.05.

### Subset stability (not out-of-sample)

The deployed thresholds applied to the later-dated events (those in the
OOS windows) produce 41/61 = 67.2%, vs 65.3% on the full sample. This
shows the fitted thresholds are not concentrated on early events. It is
subset stability, not evidence of generalisation — all events were in
the dataset when the thresholds were fitted.

### Two-window headline

Dormant. All 233 events predate the 2026-08-10 freeze. The path exists
and exits cleanly.

## Release timing map state (2026-08-12, post correction)

| Value | Count | Notes |
|---|---|---|
| `pre_market` | 31 | 30 confirmed + LMT resolved pre_market, recovered into N=233 |
| `after_hours` | 34 | All confirmed |
| `null` (non-US, excluded) | 9 | ALV.DE, BCS, LNVGY, MC.PA, AMKBY, NVO, PUM.DE, SIE.DE, STAN.L |
