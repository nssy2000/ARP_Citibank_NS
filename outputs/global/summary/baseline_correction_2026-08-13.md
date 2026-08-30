# Baseline correction — majority-direction floor

Date: 2026-08-13

## The error

The project reported accuracy of 65.3% (62/95) "against a majority-class
baseline of about 39%". The ~39% figure was always-BUY computed on all
events including HOLDs — the wrong comparator for an accuracy computed with
FLAT events excluded from the denominator.

The correct naive floor for a FLAT-excluded accuracy is the majority
direction among graded events: **always-predict-DOWN gives 54.7% (52/95)**.
The margin over the correct floor is **+10.5pp**, not +26pp.

This is distinct from the five stale-anchor retractions. It was a comparator
error present from the start: the naive floor must be computed on the same
denominator as the accuracy it is compared against.

## Tested headline margin

| Metric | Value |
|---|---|
| Accuracy | 62/95 = 65.3% |
| Majority-direction floor | 52/95 = 54.7% (always-DOWN) |
| Margin | +10.5pp |
| Binomial test (H1: acc > floor) | **p = 0.024** |
| 90% CI on accuracy | [56.4%, 73.4%] |
| MDE at N=95, α=0.10, 80% power | ±10.8pp |

The margin is significant at p=0.024. The MDE is ±10.8pp, so a 10.5pp
margin is right at the detection limit — barely significant rather than
comfortably so.

## The HOLD rate determines which story the data tells

| Convention | Accuracy | N | Floor | Margin | Story |
|---|---|---|---|---|---|
| HOLD excluded | 62/95 = **65.3%** | 95 | 54.7% | **+10.5pp** (p=0.024) | Model selects well and calls direction |
| HOLD = wrong | 62/147 = **42.2%** | 147 | 54.4% | **-12.2pp** | Model fails — holds on 52 events that moved |

Under HOLD-excluded, the model's 87 HOLD calls are invisible and the
accuracy reflects only the 95 events it chose to trade. Under HOLD=wrong,
those 52 HOLD calls on events with |ret|>2% count as failures, and the
model scores below the floor.

The model's HOLD rate (37.3%, 87/233) is doing real work: it avoids
events it is uncertain about, and the events it avoids have a majority-
DOWN distribution. The model's accuracy is a product of selection plus
direction together, not direction alone.

## Selection contribution

On all 147 events with |ret|>2% (regardless of model call):
- Model correct: 62/147 = 42.2%
- Always-DOWN floor: 80/147 = 54.4%
- Model is **12.2pp below the floor**

On the 95 events the model chose to trade:
- Model correct: 62/95 = 65.3%
- Floor: 52/95 = 54.7%
- Model is **10.5pp above the floor**

The 23.1pp gap (65.3% - 42.2%) is the selection effect — the model's
HOLD calls successfully avoid events where it would have been wrong.

## Direction-only comparison (76 events, both arms committed)

| | Accuracy | Floor (always-DOWN) | Margin | p |
|---|---|---|---|---|
| Human | 57.9% (44/76) | 55.3% (42/76) | +2.6pp | 0.366 |
| LLM | 60.5% (46/76) | 55.3% (42/76) | +5.3pp | 0.210 |

Neither arm beats the majority-direction floor by a testable margin.
The model's small edge (+5.3pp) comes partly from matching the sample's
SELL skew: the model calls SELL on 52.6% of events, close to the
sample's 56.6% DOWN rate, while the human arm calls SELL on only 30.3%.

## Correct naive floors for every event set

| Event set | N graded | Majority direction | Floor |
|---|---|---|---|
| 95 headline graded | 95 | DOWN 52/95 | **54.7%** |
| 147 all graded (HOLD=wrong) | 147 | DOWN 80/147 | **54.4%** |
| 119 eval-split graded | 119 | DOWN 65/119 | **54.6%** |
| 76 direction-only | 76 | DOWN 43/76 | **56.6%** |

## Lesson

The naive floor must be computed on the same denominator and the same
outcome distribution as the accuracy it is compared against. A floor
computed on all events (including HOLDs) is the wrong comparator for an
accuracy computed with FLAT events excluded — and the gap between the
two (54.7% vs ~39%) is larger than the margin the model claims over it.
