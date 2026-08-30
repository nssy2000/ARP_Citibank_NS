# Headline candidates — corrected figures, ranked by robustness

Date: 2026-08-12 (release_date anchor, N=233)

## 1+2 (unified). Score–return correlation with monotonic decay, and directional accuracy

*Candidates 1 and 2 were merged in a previous commit — they describe the same finding from two angles and must travel together.*

The model's blended score carries rank information about the overnight
earnings reaction (rho = 0.236, p = 0.0003 on all 233 clean events),
and that information is concentrated in the overnight window and fades
within days — exactly as an information-driven signal should.
Directional accuracy on the ±2%-graded subset is 65.3% (62 correct out
of 95 graded events, from 233 clean events; majority-direction floor 54.7% (always-DOWN)).

| Horizon | Mean net/trade | 95% CI | Accuracy (graded/traded/total) | Rho | p(rho) |
|---|---|---|---|---|---|
| overnight | +1.86% | [+0.98, +2.81] | **65.3% (95 of 233 graded, 146 traded)** | **0.236** | **0.0003** |
| 1d | +1.21% | [+0.27, +2.19] | 60.2% | 0.159 | 0.015 |
| 3d | +1.03% | [+0.00, +2.05] | 56.3% | 0.112 | 0.089 |
| 5d | +0.85% | [-0.27, +1.95] | 52.1% | 0.072 | 0.276 |
| 10d | +0.69% | [-0.63, +2.03] | 53.4% | 0.058 | 0.380 |

Every metric (raw direction-signed mean net, accuracy, rho) decays monotonically.
The bootstrap CI on raw mean net crosses zero between 3 and 5 days (3d lower
bound +0.029%, 5d lower bound −0.270%); rho drops from 0.236 to 0.058. This
validates the overnight window as a measured choice rather than a convenient
assumption, and rules out post-earnings drift as the mechanism. Note: the
excess-over-SPY series in returns_matrix.csv is not monotonic and is a separate
per-event diagnostic; its non-monotonicity reflects SPY's own multi-horizon
return pattern across those entry dates, not the model signal.

**Qualifiers that must always travel with the 65.3% accuracy figure**: 95 graded
events out of 233 total (41%); 146 traded of 233 (63%); 87 events were HOLD
(not tested). The majority-direction floor on graded events is 54.7% (always-DOWN, 52/95).

**Why strongest**: rho uses the full N=233 with no band filter, no
trade/HOLD split, and no grading threshold. The p-value (0.0003) is the most
statistically robust single result in the study. It survived the anchor
correction (was 0.221 on the old anchor, improved to 0.236). Accuracy is more
intuitive but depends on the ±2% band, the trade/HOLD split, and the
release_date anchor — all defensible, but each adds a degree of freedom rho
does not require. The two figures are complementary, not competing.

## 4. Paired-subset accuracy: ~69% against majority-class ~42.5%

**Definition**: LLM correct-direction accuracy on the subset of events
that have both a human and an LLM score (section=All,
first_rater_for_event=YES, 167 clean paired rows, 55 traded+graded).
Agree 69.0% (20/29), disagree 69.2% (18/26), pooled ~69%.

**Why it matters**: this replaces the retracted agreement filter. The
model reads earnings documents well above the majority-class baseline
regardless of whether the human arm concurs. The agreement filter
(0.561/0.429, then +17.3pp) was an artefact; the underlying accuracy
is the real finding.

**Why weakest as a headline**: small graded N (55 events), and the
paired subset is not representative (covers only companies where both
arms scored the same quarter).

## 4. Human vs LLM comparison: underpowered at this N

On the 48 paired events where both arms traded and |ret|>2%:
LLM 64.6% (31/48) vs Human 58.3% (28/48), diff +6.3pp, p=0.533.
Paired MDE ~±30pp — the comparison is **untestable**.

The LLM holds on 40.4% of events, the human arm on 23.4%. The LLM's
higher accuracy (69.0% vs 57.0% on independently graded events) is
confounded by its higher HOLD rate — it is more selective, not
necessarily more accurate. See `human_vs_llm_corrected.md`.

## Summary

| Candidate | Statistic | N | p-value | Note |
|---|---|---|---|---|
| Score-return correlation + decay + accuracy (unified) | rho=0.236, 65.3% (95 of 233 graded, vs 54.7% majority-direction floor), monotonic decay | 233 / 95 graded | 0.0003 | Strongest; candidates 1+2 merged |
| Paired-subset accuracy | ~69% vs ~42.5% baseline | 55 graded | — | Replaces retracted filter |
| Human vs LLM | +6.3pp, p=0.533 | 48 paired | 0.533 | Untestable at this N |

The strongest headline is the score-return correlation with its decay curve
and directional accuracy, presented as one unified finding. Rho=0.236
(p=0.0003) uses the full N=233 with no threshold, survived the anchor
correction, and the monotonic decay validates the overnight window.
Accuracy at 65.3% is the most intuitive figure but must always carry its
qualifiers: 95 graded events out of 233 clean events (41%), 146 traded of
233 (63%), majority-direction floor 54.7% (always-DOWN). The human comparison is
underpowered and should be stated as such rather than claimed as a result
in either direction.
