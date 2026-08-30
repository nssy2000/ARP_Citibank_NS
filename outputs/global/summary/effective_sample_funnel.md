# Effective sample funnel

Date: 2026-08-30 (updated to N=232 after DIS_FQ1_2025 exclusion on 2026-08-24)

Source: `item_e_walkforward.json` (n_clean=232, n_traded=168, n_graded=109,
n_correct=68, accuracy=0.6239, mean_net=1.7963%).

Deployed constants: weights (0.80, 0.20, 0.0, 0.0), hold_upper=0.20,
hold_lower=−0.10, cost_bps=10, flat_band=±2%.

## The funnel

| Step | N | Lost | Reason |
|---|---|---|---|
| Total events | 268 | | |
| After worksheet + misattributed exclusion | 241 | 27 | 25 worksheet contamination + 2 misattributed documents (SPOT_FQ1_2026, DIS_FQ1_2025) |
| After timing exclusion | **232** | 9 | 9 non-US issuers with unreliable overnight returns |
| LLM called BUY or SELL | 168 | 64 | Model said HOLD — no trade, no directional test |
| Overnight \|return\| > ±2% band | **109** | 59 | Return inside ±2% band — traded but ungraded ("bet on flat") |

**109 events carry every directional accuracy claim in the study.** The directional
accuracy of 62.4% (68/109) is computed on this base (`item_e_walkforward.json`
`in_sample_deployed`).

## Exclusion details

The 36 excluded events are defined in `eval/excluded_events.py`:

| Category | Count | Description |
|---|---|---|
| Worksheet contamination | 25 | Human rater peeked at outcome before scoring |
| Misattributed document | 2 | SPOT_FQ1_2026: transcript filed under wrong issuer; DIS_FQ1_2025: Q2 document bundled into Q1 event |
| Timing unresolved | 9 | Non-US issuers where overnight return window is unreliable |
| **Total excluded** | **36** | 268 − 36 = **232 clean** |

## Why "traded but ungraded" is a separate category

The grading convention uses the ±2% overnight band to classify outcomes as BUY-correct,
SELL-correct, or flat. When the model calls BUY or SELL but the overnight return is
inside ±2%, the event is **traded** (the model took a position) but **ungraded** —
the outcome is ambiguous and the event contributes approximately zero net P&L. These
events are counted in mean-net-per-trade calculations but not in directional accuracy.

- **Accuracy** is computed on the 109 graded events only: 68 correct / 109 = 62.4%.
- **Mean net per trade** is computed on all 168 traded events, including the 59 flat
  bets, and is +1.796% (`item_e_walkforward.json`).

## Superseded figures

| Superseded value | Current value | Reason for change |
|---|---|---|
| N = 233 | N = 232 | DIS_FQ1_2025 excluded 2026-08-24 (look-ahead contamination) |
| n_graded = 95 | n_graded = 109 | Threshold change: +0.25/−0.05 → +0.20/−0.10 widens the traded set |
| accuracy = 65.3% (62/95) | accuracy = 62.4% (68/109) | Both N and threshold changed |
| mean_net = +1.862% | mean_net = +1.796% | Threshold change affects which events are traded |
| weights 0.55/0.45 | weights 0.80/0.20 | Regime promoted 2026-08-19 |

The earlier funnel (dated 2026-08-13, N=233) is retained in git history.
See `NEW_VS_OLD_report.md` for a full figure-by-figure reconciliation.
