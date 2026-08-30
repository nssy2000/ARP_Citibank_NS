# Retracted findings — 2026-08-12

Two findings reported on 2026-08-12 were artefacts of the stale entry anchor
(report_date close used uniformly instead of release_date-aware entry). Both
are documented here so the pattern is on the record.

## 1. "72.7% of pre_market events fall inside the ±2% band"

**What was claimed**: 72.7% of pre_market events (96/132) had overnight
returns inside the ±2% HOLD band, against 26.8% (26/97) for after_hours.
This was presented as a 3× structural asymmetry in what the study could
measure, driven by the overnight gap capturing less of the earnings reaction
for BMO reporters.

**Corrected figure**: 42.4% (56/132) for pre_market, 29.9% (29/97) for
after_hours. The asymmetry is real but roughly 1.4×, not 3×.

**Why the artefact arose**: For 82 pre_market events where release_date =
report_date, the old convention used report_date close as entry — which was
already post-announcement for a BMO reporter. The overnight gap from that
close to the next morning's open was residual drift, not the earnings
reaction. The corrected anchor shifts entry to the prior session's close, so
the gap now spans the actual pre-market release and captures most of the
reaction. This moved ~40 events from inside the band to outside it.

## 2. "61% of ungraded trades were directionally correct (p=0.064)"

**What was claimed**: 46 of 75 ungraded trades (events where the model traded
but the overnight return fell inside ±2%) had their directional sign match the
model's call. This was presented as a measured cost of the pre-registered HOLD
band — the band was discarding events where the model had real signal.

**Corrected figure**: 28 of 50 ungraded trades = 56.0%, p=0.480 (not
significant).

**Why the artefact arose**: The 25 events that moved from "flat traded"
(ungraded) to "graded" were disproportionately the ones with correct signs
and larger magnitudes — they sat just below the ±2% boundary under the old
entry and moved above it under the corrected entry. Removing them from the
ungraded pool dropped the rate from 61% to 56% and eliminated the
significance. The band is not discarding signal; the old entry was compressing
returns below the band.

## 3. Accuracy-versus-P&L divergence

**What was claimed in earlier project notes**: accuracy and P&L point in
opposite directions because the HOLD metric rewards hedging while P&L rewards
exposure, with pre_market showing higher accuracy (70.8%) and lower mean net
(+0.723%) than after_hours (65.1%, +2.749%).

**Corrected figures**: pre_market accuracy 64.6% vs after_hours 65.9% — nearly
identical. Mean net +1.149% vs +2.817%. The accuracy divergence has vanished.
Pooled: accuracy 65.2% (60/92), mean net +1.877% — both positive, no
directional divergence.

The earlier divergence was an anchor artefact: the old entry inflated
pre_market accuracy by restricting the graded sample to the 24 most extreme
reactions (70.8% on an easy subset) while deflating mean net by including 56
near-zero flat trades. The corrected anchor doubles the pre_market graded
sample to 48 events, diluting the inflated accuracy and increasing mean net.

## 4. Agreement filter (+17.3pp, p=0.029) — the most consequential retraction

### The original claim (never reproducible)

The project's documented headline was that LLM accuracy is 0.561 where both
the human and LLM arms agree, against 0.429 where they disagree. This figure
appears only as prose in `Model_Arm_Implementation_Spec.md` ("Agreement-
conditional accuracy, 0.561 on the 57 events where both arms agree, against
0.429 where they disagree. Already computed."). No script, output file, or
intermediate artefact in this repository produces these numbers. They cannot
be regenerated and should not be presented.

### The interim measured version (stale anchor)

A replacement was computed on the `report_date` anchor: agree 32.7% (18/55)
vs disagree 15.4% (8/52), difference +17.3pp, bootstrap p=0.029. This was
presented as the authoritative figure. It was computed on the stale anchor.

### The corrected figure

On the `release_date` anchor: agree 69.0% (20/29) vs disagree 69.2% (18/26),
difference -0.3pp, p=0.959. **The agreement filter vanishes entirely.**

### Why the artefact arose

The stale anchor compressed overnight returns for 82 pre_market events by
using post-announcement close as entry. Most of those returns fell inside
the ±2% band and were ungraded. The corrected anchor produces larger, more
accurate overnight returns, raising accuracy across the board from ~25% to
~69%. But it raises accuracy equally for both the agree and disagree groups,
eliminating the differential. The filter was not measuring a real property
of agreement; it was measuring which events happened to have returns large
enough to breach the band under the wrong entry.

### Consistency with kappa

Cohen's kappa on the clean group is 0.107 (90% CI [0.027, 0.188]) — near
zero, meaning the human and LLM arms are close to independent. Two
near-independent arms give no reason to expect their agreement to carry
information about accuracy, and indeed it does not. The retraction is
consistent with evidence already in hand.

### The positive result that replaces it

The corrected accuracy of ~69% on the paired subset (against a majority-class
baseline of ~42.5%) is a substantial finding that holds regardless of whether
the arms agree. Under the old anchor the agree cell was 32.7%, below the
naive baseline. The corrected picture is a model that reads earnings documents
well above chance, not one that works only when a human concurs.

## 5. Baseline of ~39% (always-BUY on all events including HOLDs)

**What was claimed**: accuracy of 65.3% "against a majority-class baseline of
about 39%", implying a +26pp margin.

**Corrected figure**: the correct naive floor is always-predict-DOWN on graded
events = 54.7% (52/95). The margin is +10.5pp (p=0.024), barely significant
(MDE=±10.8pp at N=95).

**Why the error arose**: the ~39% was always-BUY computed on all events
including HOLDs — the wrong denominator for an accuracy computed with FLAT
events excluded. This is not a stale-anchor artefact but a comparator error
present from the start. The naive floor must be computed on the same
denominator as the accuracy it is compared against.

See `baseline_correction_2026-08-13.md` for the full analysis.

## Lesson: one convention error plus one comparator error, five retracted findings

All four artefacts trace to one cause: using `report_date` close uniformly
as entry, which was wrong for 82 pre_market events. The corrected anchor
(`release_date` from EDGAR 8-K Item 2.02) resolves the entry to the correct
session.

| Finding | Stale | Corrected | Mechanism |
|---|---|---|---|
| Band capture | 72.7% PM inside | 42.4% | Wrong entry compressed returns below band |
| Sign-correct | 61% p=0.064 | 56% p=0.480 | Best sign-correct events moved to graded |
| Accuracy divergence | PM 70.8% vs AH 65.1% | 64.6% vs 65.9% | Inflated by extreme-only grading |
| Agreement filter | +17.3pp p=0.029 | -0.3pp p=0.959 | Both groups lifted equally |

The methodological lesson: verify entry anchors against documented filing
dates, not price behaviour. The JPM_FQ1_2025 case (tariff-pause rally on
2025-04-09 masking the actual 2025-04-11 release) is the clearest
demonstration — see `jpm_fq1_2025_worked_example.md`.
