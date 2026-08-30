# Direction accuracy decomposition

Date: 2026-08-13 (corrected 2026-08-13: tautology identified and restated)

Backing CSVs: `human_vs_llm_direction_decomposition.csv`,
`human_vs_llm_statistics.csv`. Computing script:
`experiments/human_vs_llm_backing.py`.

## Corrected finding

The earlier claim that "per-direction accuracy exactly equals the base rate
in its self-selected subset" is **tautological**: the accuracy of BUY calls
is the proportion of positive returns among events the arm called BUY, and
the "base rate in the subset" is the same proportion. They are the same
number by definition, for any arm, on any data. This is not a finding.

The informative comparisons are each arm's accuracy **vs 50%** and **vs the
overall base rate** (not the subset base rate).

### Human arm

| Call | Correct | N | Accuracy | Base rate in subset | Margin |
|---|---|---|---|---|---|
| BUY | 27 | 53 | 50.9% | 50.9% (27/53 positive) | **0.0pp** |
| SELL | 17 | 23 | 73.9% | 73.9% (17/23 negative) | **0.0pp** |
| Overall | 44 | 76 | 57.9% | — | — |

### LLM arm

| Call | Correct | N | Accuracy | Base rate in subset | Margin |
|---|---|---|---|---|---|
| BUY | 20 | 36 | 55.6% | 55.6% (20/36 positive) | **0.0pp** |
| SELL | 26 | 40 | 65.0% | 65.0% (26/40 negative) | **0.0pp** |
| Overall | 46 | 76 | 60.5% | — | — |

### Interpretation

Both arms' overall sign accuracy (57.9% and 60.5%) comes **entirely from
how they allocate events between BUY and SELL**, not from reading the
documents better than chance within each bucket. Given its BUY/SELL split
of 53/23, the human arm would score 57.9% even if it assigned BUY and
SELL at random — because the events it calls BUY happen to have a 50.9%
positive rate and the events it calls SELL happen to have a 73.9% negative
rate.

The model's small edge (+2.6pp) over the human comes from a more balanced
BUY/SELL split (36/40) that is closer to the sample's SELL skew (43 of 76
events negative). It is base-rate matching, not document reading.

### Why both arms beat always-BUY but not always-DOWN

Always-BUY scores 43.4% because the sample is 56.6% negative. Both arms
beat this (p<0.01) by calling SELL on some events. But always-DOWN scores
55.3%, and neither arm beats that (human p=0.366, LLM p=0.210), because
neither arm's per-direction accuracy exceeds the base rate within its own
subsets.

### What this means for the headline

The model's **headline accuracy of 65.3% (62/95 graded, HOLD-excluded)**
survives this decomposition because it includes a selection component: the
model's 87 HOLD calls successfully avoid events where the market moved.
The direction-only comparison strips away that selection and reveals no
residual directional skill.

The **rho = 0.236 (p=0.0003)** result on all 233 events also survives,
because it measures rank correlation between the blended score and the
return, not direction-of-call accuracy. A model can have positive rank
correlation (higher scores predict higher returns in the continuous sense)
without having directional accuracy above the base rate (its BUY/SELL
calls do not beat within-subset chance).

### Fragility statement

The headline margin of +10.5pp (65.3% vs 54.7%, p=0.024) is significant
but sits at the detection limit (MDE = ±10.8pp at N=95). The study was
barely powered to detect the effect it found. A modestly smaller true
effect would have been undetectable at this sample size.

## Dev vs eval split

| | Dev | Eval |
|---|---|---|
| N | 47 | 186 |
| Traded+graded | 20 | 75 |
| Accuracy | 55.0% (11/20) | 68.0% (51/75) |
| Floor (always-DOWN) | 53.6% | 54.6% |
| Margin | +1.4pp | +13.4pp (p=0.013) |

Split rule: sort 233 clean events by release_date (returns_matrix.csv),
earliest 20% = dev, remaining 80% = eval. Source: `frontier_table.csv`.

The model performs better on later events (eval) than earlier ones (dev).
This is the opposite of what overfitting produces. The eval-split margin
of +13.4pp against the floor is significant (p=0.013). However:
- Dev N=19 is too small to draw conclusions (MDE=±24.1pp)
- The eval-dev difference is +15.8pp but not significant (p=0.229)
- Mean docs per event: dev 2.26, eval 2.39 — modestly richer sourcing
  in later quarters, which could partly explain the improvement
- This is the finding Item E (walk-forward) exists to test properly

## Both accuracy framings, always reported together

| Framing | Accuracy | Denominator | Floor | Margin | Story |
|---|---|---|---|---|---|
| **Selectivity** | 62/95 = 65.3% | Model traded + |ret|>2% | 54.7% | +10.5pp (p=0.024) | When it commits, it is right |
| **Coverage** | 62/147 = 42.2% | All |ret|>2% | 54.4% | -12.2pp | It misses 52 events that moved |

A deployment reader needs both: the model is right when it speaks but
silent on a third of the tradeable events.
