# Human vs LLM comparison — corrected release_date anchor

Date: 2026-08-12

## Subset definition

Source: `data/human/human_decisions_export_2026-08-12.csv`
Filters: `section == "All"`, `first_rater_for_event == YES`,
`in_llm_universe == YES`, 35-event exclusion set applied.
N = 171 paired events.

Backing CSVs: `human_vs_llm_statistics.csv` (all statistics),
`human_vs_llm_direction_decomposition.csv` (per-direction table).
Computing script: `experiments/human_vs_llm_backing.py`.

Grading: pre-registered ±2% raw overnight band on `returns_matrix.csv`
(release_date anchor). Accuracy = correct-direction rate among events
where the arm traded (BUY or SELL) and |ret_overnight| > 2%.

## Pooled comparison (all repricing classes, N=171)

|  | Human | LLM |
|---|---|---|
| BUY calls | 96 (56.1%) | 42 (24.6%) |
| HOLD calls | 40 (23.4%) | 69 (40.4%) |
| SELL calls | 35 (20.5%) | 60 (35.1%) |
| **HOLD rate** | **23.4%** | **40.4%** |
| Traded | 131 | 102 |
| Graded (traded + |ret|>2%) | 79 | 58 |
| Correct direction | 45 | 40 |
| **Accuracy** | **57.0%** (45/79) | **69.0%** (40/58) |

Always-BUY baseline: 39.4% (39/99 events with |ret|>2%).

### Paired comparison (both arms traded + |ret|>2%): N=48

|  | LLM | Human |
|---|---|---|
| Correct | 31/48 (64.6%) | 28/48 (58.3%) |

LLM − Human: +6.3pp, 90% CI [−8.3pp, +20.8pp], p=0.533.
**Paired MDE at N=48: ~±30pp.** The comparison is underpowered. Any
difference smaller than ~30pp is untestable at this sample size.

### Context on the HOLD rate difference

The LLM holds on 40.4% of events; the human arm on 23.4%. A model
that holds more will have fewer graded events (58 vs 79) and those
graded events will be the ones where it was most confident, inflating
its accuracy relative to an arm that trades more freely. The 69.0% vs
57.0% accuracy difference is confounded by this trade-frequency
asymmetry and should not be read as the LLM being "more accurate" —
it is more selective.

The fair comparison is on the 48 events where both arms committed,
which shows +6.3pp (not significant, p=0.533).

## Fact-based repricing (N=34)

| | Human | LLM |
|---|---|---|
| Graded | 12 | 9 |
| Accuracy | 41.7% (5/12) | 88.9% (8/9) |

Paired (both graded): N=7. LLM 85.7% vs Human 42.9%, diff +42.9pp,
p=0.203. **MDE ~±77pp — completely untestable at N=7.**

## Primary result: direction-only comparison (neutral on HOLD rate)

On the 76 events where both arms called BUY or SELL, sign accuracy
(did the call match the sign of the overnight return, no band filter):

| | Sign accuracy | N | vs always-BUY (p) |
|---|---|---|---|
| Human | **57.9%** (44/76) | 76 | +14.5pp (**p=0.008**) |
| LLM | **60.5%** (46/76) | 76 | +17.1pp (**p=0.002**) |
| LLM − Human | +2.6pp, 90% CI [−7.9, +13.2], p=0.750 | | |
| Always-BUY baseline | 43.4% (33/76) | 76 | |
| **Always-DOWN baseline** | **55.3%** (42/76) | 76 | Correct floor for SELL-skewed sample |
| Paired MDE | ~±23pp | | |

This is the only cut where the HOLD-rate confound is absent — both arms
committed on every event, so selectivity plays no role.

**Conclusion**: both arms extract directional information from earnings
documents — each beats the always-BUY baseline (43.4%, p<0.01). However,
the sample is SELL-skewed (55.3% negative returns), so the correct naive
floor is always-DOWN at 55.3%. Against this floor, human +2.6pp (p=0.366)
and LLM +5.3pp (p=0.210) — **neither arm beats the majority-direction
floor by a testable margin**. Resolving the difference would require a
substantially larger sample rather than a different method.

### Outcome distribution

The 76 events have 33 positive returns, 42 negative, and 1 zero
(PUM.DE_FQ4_2025). Always-BUY = 43.4% (33/76); always-DOWN = 55.3%
(42/76 strict negative) or 56.6% (43/76 including zero). The floor
p-values above use the strict 55.3%; the per-direction base rate in
finding #7 uses 56.6%. The sample is SELL-skewed, which penalises the
optimistic human arm rather than flattering it.

### Accuracy by call direction

| Arm | BUY accuracy | N | SELL accuracy | N |
|---|---|---|---|---|
| Human | 50.9% (27/53) | 53 | **73.9%** (17/23) | 23 |
| LLM | 55.6% (20/36) | 36 | **65.0%** (26/40) | 40 |

**The human arm's BUY calls carry no information beyond optimism.** Their
BUY accuracy of 50.9% exactly equals the always-BUY rate on those same 53
events (27/53 had positive returns). Their skill is entirely in their SELL
calls (73.9%, N=23). The human arm is a good sell-side analyst — their
value is in identifying trouble, not in confirming strength.

The LLM distributes its skill more evenly (55.6% BUY, 65.0% SELL) and
makes roughly balanced calls (47.4% BUY / 52.6% SELL). Its overall sign
accuracy is marginally higher (60.5% vs 57.9%) but the difference is not
significant.

## FLAT convention and the metric differential

The FLAT convention gives the LLM a 7.1pp differential advantage (see
`methodology_flat_convention.md`). The like-for-like paired gap of 6.3pp
(FLAT excluded) is smaller than this differential. Under FLAT-as-wrong,
the gap narrows to 4.8pp, also untestable.

**Under neither convention can a model advantage over the human arm be
claimed.** The comparison is underpowered (MDE ~±30pp on band-breaching
events, ~±23pp on sign accuracy) and the primary metric is not neutral on
HOLD rate.

## Price-based repricing (N=64, reported separately, never pooled)

| | Human | LLM |
|---|---|---|
| Graded | 39 | 29 |
| Accuracy | 69.2% (27/39) | 55.2% (16/29) |

Paired (both graded): N=27. Human 66.7% vs LLM 55.6%, diff −11.1pp,
p=0.322. **MDE ~±39pp — untestable.**

Note: the human arm outperforms the LLM on price-based rows. This is
expected — price-based repricing selected the measurement window to
show a move, and the human arm's directionally optimistic profile
(56% BUY) is rewarded when moves are guaranteed to be large.
