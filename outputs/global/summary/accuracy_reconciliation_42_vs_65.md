# Reconciliation: 42.9% (frontier) vs 65.3% (headline)

Date: 2026-08-13

## The two figures

| Figure | Value | Convention | Denominator | Correct |
|---|---|---|---|---|
| Headline | **65.3%** (62/95) | HOLD excluded | Events model traded AND |ret|>2% | 62 |
| Frontier | **42.2%** (62/147) | HOLD = wrong | ALL events with |ret|>2% | 62 |

Both figures use the **same 62 correct calls**. The difference is the
denominator: 95 (model traded + graded) vs 147 (all graded, model call
irrelevant).

## Why they differ

The model called HOLD on 87 of 233 events. Of those 87, **52 had overnight
returns exceeding the ±2% band** — the market moved, the model abstained.

- Under HOLD-excluded: those 52 events are invisible. Accuracy = 62/95.
- Under HOLD=wrong: those 52 count as failures. Accuracy = 62/147.

## Which is authoritative for which claim

**65.3% answers**: "when the model commits to a direction, is it right?"
This rewards selection — the model picks its battles and wins 65.3% of them.

**42.2% answers**: "does the model capture directional information across all
events?" This penalises abstention — the model misses 52 events it should
have traded, and scores below the majority-direction floor (54.4%).

Neither is wrong. They measure different things. **Both must be reported,
and the convention must be stated alongside the number every time.**

## The eval split (42.9% in the frontier table)

The frontier table's 42.9% = 51/119 is the FLAT-excluded figure computed on
the eval split (earliest 20% dev, rest eval). On the same eval split, the
selectivity accuracy (traded+graded only) is 51/75 = 68.0%.

The dev/eval partition: sort 233 clean events by release_date
(returns_matrix.csv), earliest 20% (47 events) = dev, remaining 80%
(186 events) = eval. This split was defined in `experiments/lm_baseline.py`
for the Loughran-McDonald baseline and reused for FinBERT. It is not the
model's own development set — the model was scored on all events and the
split is applied post hoc for baseline comparison only.

Dev selectivity accuracy: 11/20 = 55.0%. Eval: 51/75 = 68.0%. The
model performs better on later events than earlier ones, which is the
opposite of what overfitting would predict. Source: `frontier_table.csv`.

## Is the model genuinely below the floor?

Under HOLD=wrong on the full 233: model 42.2%, floor 54.4%. **Yes — the
model is 12.2pp below the majority-direction floor.** This is driven
entirely by its 52 HOLD calls on events where the market moved. The model's
abstention rate is too high for this metric to reward.

Under HOLD-excluded: model 65.3%, floor 54.7%, margin +10.5pp, p=0.024.
The model is above the floor on the events it chose to trade.

**Both are real.** The model is a selective trader — excellent when it
commits (65.3% vs 54.7% floor), but it abstains too often for the
HOLD=wrong metric to give it credit. Whether abstention is a virtue or a
failure depends on the deployment context.
