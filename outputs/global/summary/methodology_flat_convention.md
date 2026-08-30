# Methodology: FLAT convention and sample mismatch

Date: 2026-08-12

## 1. The FLAT convention (dated methodological choice)

Events whose realised overnight return falls inside the pre-registered ±2%
band are **excluded from the directional accuracy denominator** for both
arms, not counted as incorrect.

**Reason**: a three-way BUY/HOLD/SELL scheme with a neutral band cannot
fairly score a directional call against an outcome the band itself defines
as neutral. A BUY call on a +0.5% move is neither clearly right nor clearly
wrong — the band exists precisely to mark this range as ambiguous.

**Effect on both arms** (paired subset, N=171):

| Convention | Human accuracy | N | LLM accuracy | N |
|---|---|---|---|---|
| FLAT excluded | **57.0%** (45/79) | 79 graded | **69.0%** (40/58) | 58 graded |
| FLAT as wrong | **34.4%** (45/131) | 131 traded | **39.2%** (40/102) | 102 traded |

| | Human swing | LLM swing | Differential |
|---|---|---|---|
| FLAT excluded vs wrong | +22.6pp | +29.7pp | **LLM favoured by 7.1pp** |

**The choice favours the LLM arm by 7.1pp.** The LLM has a higher HOLD rate
(40.4% vs 23.4%), so when it does trade, a larger proportion of its trades
land on events with |ret| > 2% (because it avoids the ambiguous middle).
Excluding FLAT rewards this selectivity. The human arm trades more freely
(131 vs 102 trades) and a larger share of its trades land inside the band.

Both figures are reported wherever human accuracy appears, so the choice
is visible rather than buried. The FLAT-excluded figure is used as the
primary because it matches the accuracy definition applied to the LLM arm
throughout the study. The FLAT-as-wrong figure is the robustness check.

**The differential exceeds the finding.** The FLAT convention gives the LLM
a 7.1pp advantage over the human arm. The like-for-like paired gap on
band-breaching events is 6.3pp (LLM 64.6% vs Human 58.3%). The entire
apparent model advantage is smaller than the bias the metric choice
introduces. Under FLAT-as-wrong, the gap narrows to 4.8pp (LLM 39.2% vs
Human 34.4%), also untestable at N=48 (MDE ~±30pp).

**Conclusion: under neither convention can a model advantage over the human
arm be claimed.** FLAT-excluded flatters the model because it holds 40.4%
against 23.4%, so its traded events disproportionately breach the band.
FLAT-as-wrong narrows the gap but remains untestable. The comparison is
underpowered and the metric is not neutral, and both facts belong together.

**Direction-only comparison (supplementary, neutral on HOLD rate):**
On the 76 events where both arms called BUY or SELL (no band filter, no
HOLD-rate confound): Human sign accuracy 57.9% (44/76), LLM sign accuracy
60.5% (46/76), paired diff +2.6pp, 90% CI [−7.9pp, +13.2pp], p=0.754.
Paired MDE ~±23pp. This is the only cut where the HOLD-rate confound is
absent. It shows no detectable difference. Always-BUY baseline: 43.4%.
HOLD rates must accompany every accuracy figure for both arms.

## 2. The sample mismatch between accuracy and mean net per trade

Accuracy is computed on **band-breaching events** (79 graded for human,
58 for LLM, 95 for the full LLM universe).

Mean net per trade is computed on **all traded events** (131 for human,
102 for LLM, 146 for the full LLM universe), including flat trades that
contribute ~0% net each.

This is not an error — the two metrics answer different questions on
different samples by design. But it means accuracy and mean net per trade
should not be plotted on the same axis or combined into a single
performance claim. Accuracy describes directional skill on the events
where the outcome was unambiguous. Mean net per trade describes the
economic value of all trading decisions including the ambiguous ones.

The retracted accuracy-versus-P&L divergence (pre_market 70.8% accuracy
with +0.72% net vs after_hours 65.1% with +2.75%) was partly a
consequence of this mismatch interacting with the stale anchor. On the
corrected anchor the divergence vanishes (64.6% vs 65.9%), but the
mismatch remains as a structural property of the metric pair.
