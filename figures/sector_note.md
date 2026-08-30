# Sector dispersion: human arm vs model arm, extension set (Set B)

**Source (human):** `data/human/human_decisions_export_2026-08-12.csv`
**Source (model):** `outputs/global/summary/global_outcome_calibration_extension_2026_08_13.csv`

**Filter:** `first_rater_for_event = YES` AND `information_set ≠ 'presentation only'`

**N = 83.** Of 93 extension events, 4 RMS (Hermès) have no human reading
and 6 (EBAY × 2, HEINY × 4) have `information_set = 'presentation only'`.

Human score_std: sample standard deviation of `human_sentiment_score` (ddof = 1).
Model score_std: sample standard deviation of `micro_score` (ddof = 1).
HOLD rate: fraction of events where the arm's decision is HOLD.

## Extension set, paired universe (N = 83)

| Sector | n | Human std | Human HOLD | Model std | Model HOLD |
|---|---|---|---|---|---|
| Energy | 21 | 0.2298 | 67% | 0.0489 | 86% |
| Consumer Staples | 10 | 0.1337 | 50% | 0.3035 | 70% |
| Information Technology | 15 | 0.3753 | 7% | 0.2216 | 60% |
| Materials | 3 | 0.1528 | 0% | 0.4481 | 67% |
| Industrials | 4 | 0.1732 | 25% | 0.2345 | 75% |
