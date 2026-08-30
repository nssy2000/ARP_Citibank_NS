# Pre-market power gap (corrected on release_date anchor)

Date: 2026-08-12

## Finding (corrected)

The overnight close-to-open gap is a moderately lower-powered measure of the
earnings reaction for pre-market reporters than for after-hours reporters.
This affects 132 of 233 clean events (57%).

**Superseded figures**: the earlier version of this document reported a 3×
asymmetry (72.7% vs 26.8% inside the ±2% band) and a significant sign-correct
result (46/75, p=0.064). Both were artefacts of the stale report_date anchor.
See `retracted_findings_2026-08-12.md`.

## Corrected band capture

| | Pre_market (N=132) | After_hours (N=97) |
|---|---|---|
| Inside ±2% band | **42.4%** (56/132) | **29.9%** (29/97) |
| Traded | 80 | 62 |
| Graded (|ret| > 2%) | 48 | 44 |
| Dir. accuracy | 64.6% (31/48) | 65.9% (29/44) |
| Mean net/trade | +1.149% | +2.817% |

The asymmetry is ~1.4× (42.4% vs 29.9%), not the earlier 3×. Pre_market
reporters still show more events inside the band, consistent with the
mechanism (partial pre-market pricing compresses the gap), but the effect is
moderate rather than dominant.

## Mechanism (unchanged)

Pre-market reporters release results 1-3 hours before the exchange open. The
pre-market session prices the news partially, but the regular-session open
reflects only a fraction of the full repricing. The remainder is absorbed
during the trading session. The overnight gap captures the pre-market
fraction; the close-to-close move captures both.

## The accuracy-versus-P&L divergence has vanished

On the corrected matrix: pre_market accuracy 64.6% vs after_hours 65.9% —
nearly identical. The earlier divergence (70.8% vs 65.1%) was an anchor
artefact: the old entry inflated pre_market accuracy by restricting the graded
sample to the most extreme reactions. Pooled: accuracy 65.2% (60/92), mean
net +1.877% — both positive, no directional divergence.

## Robustness note: raw versus excess grading

In turbulent months (April 2025, October 2025), roughly one event in six
would flip its grade if measured on excess-over-SPY returns rather than raw
returns. The raw ±2% band conflates market-wide moves with company-specific
ones during market stress. Pre-registered band retained; this is a stated
limitation.

## Pre-registered convention retained

The ±2% raw overnight band is pre-registered and stays. The 5-day horizon in
`returns_matrix.csv` is available as a secondary check. Longer-horizon bands
were recalibrated on the corrected matrix (2026-08-12) and are explicitly
secondary and not pre-registered.
