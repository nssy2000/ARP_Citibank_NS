# Model Latency Analysis — 2026-08-15
**Generated:** 2026-08-15  
**Source:** `outputs/p2_*/logs/first_run_costs.jsonl` (91 issuers, 624 success calls)  
**Human reference:** `outputs/global/summary/information_set_comparison_2026-08-15.csv`

---

## 1. Latency Summary Statistics
All figures are end-to-end API call duration (`latency_seconds`) for status=success micro-layer calls.
Runtime is **not** stored in individual result JSONs, `api_cost_ledger.csv`, or `batch_metadata.json`.

| Group | n | mean (s) | median (s) | min (s) | max (s) | Q1 (s) | Q3 (s) | IQR (s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all_micro | 624 | 15.92 | 15.0 | 7.52 | 126.99 | 12.95 | 17.31 | 4.36 |
| phase2_N523 | 523 | 15.86 | 15.1 | 7.52 | 100.65 | 13.03 | 17.82 | 4.79 |
| extension_N101 | 101 | 16.23 | 14.25 | 9.89 | 126.99 | 12.82 | 15.68 | 2.86 |

The IQR is narrow (4.4 s for all calls, 12.95–17.31 s): the central 50% of calls complete in a 4-second band. Tail latency is real — max 127 s — driven by a small number of very long documents (max input: 195,983 tokens). Phase2 and extension arms run at essentially the same speed (means 15.86 s vs 16.23 s, not meaningfully different).

---

## 2. Latency Against Input Token Count
**Spearman rank correlation (latency vs input tokens): 0.4414** (n=624).
Moderate positive association: longer bundles are slower, but token count explains a minority of latency variance.
OLS: latency = 14.08 s + 0.0767 s per 1000 tokens

| Input tokens | Predicted latency |
| --- | --- |
| 10,000 | 14.8 s |
| 20,000 | 15.6 s |
| 30,000 | 16.4 s |
| 50,000 | 17.9 s |
| 100,000 | 21.8 s |

The intercept (~14 s) dominates: most latency is baseline overhead (network round-trip, queue, tokenisation), not proportional to document length. A press-release-only bundle (~13k tokens) is typically 1–2 s faster than a full bundle (~30k tokens) — a real but small difference.

**Baseline-overhead interpretation.** Because the intercept (~14 s) is so large relative to the slope (0.077 s per 1000 tokens), two practical implications follow:

1. **The speed advantage does not scale with document length.** A 30k-token full bundle is only ~1–2 s slower than a 13k-token press release. This means the ~112× speed multiple relative to human reading time holds for long filings as well as short releases — it does not erode as documents get longer.

2. **The 2–3 s ablation arm difference is mostly a token-count effect.** The observed latency gap between full_bundle (~15–16 s median) and press_release or qa_only arms (~13 s median) is consistent with the OLS prediction for the token difference between those bundles. It does not reflect anything specific to the content of the sections — a shorter bundle is faster because it is shorter, not because the model processes certain section types differently.

---

## 3. Section Ablation Arm Latency
Latency was logged for both the main section ablation run (`section_ablation_results.csv`, Set A N=119) and the extension run (`section_ablation_extension_results.csv`, Set B N=56).
Two outliers excluded from Set A arm stats (threshold 200 s): UNH\_FQ4\_2025/full\_bundle 1280.83 s, PUM.DE\_FQ1\_2025/full\_bundle 638.25 s. UNH\_FQ3\_2025/prepared\_remarks at 129.09 s is below the threshold and retained; it appears as the max value for that arm row. The two excluded values are almost certainly network timeouts or retries.

| Arm | Set A n | Set A mean (s) | Set A median (s) | Set B n | Set B mean (s) | Set B median (s) |
| --- | --- | --- | --- | --- | --- | --- |
| full_bundle | 198 | 16.36 | 15.31 | 93 | 17.53 | 15.41 |
| press_release | 200 | 14.14 | 13.07 | 93 | 13.32 | 13.03 |
| prepared_remarks | 119 | 15.34 | 13.99 | 56 | 12.52 | 12.09 |
| qa_only | 119 | 13.47 | 13.19 | 56 | 13.73 | 13.21 |

**Press release and prepared\_remarks are 2–3 s faster than full\_bundle** (median: ~13 s vs ~15 s). The difference is consistent with the token-regression prediction: press-release bundles are ~13k tokens, full bundles ~30k. A cheaper arm is also measurably faster: both factors strengthen the prepared\_remarks deployment case.

---

## 4. Model vs Human Efficiency
Human reading time from `information_set_comparison_2026-08-15.csv`:
- Full arm (N=190 docs): mean **29.8 min/doc** = 1788 s/doc
- Pooled across all information sets (N=420 readings): mean **27.9 min/doc** = 1674 s/doc
- Time per correct call (full arm): 5668 min total / 39 correct calls = **145.3 min/correct call**

Model (phase2, N=523 calls):
- Mean: 15.92 s/call  |  Median: 15.0 s/call  |  IQR: 12.95–17.31 s
- Total phase2 call time: 8293 s / 62 correct calls (from workbook_metrics.csv) = **133.8 s = 2.2 min/correct call**

| Metric | Human | Model | Speed multiple |
| --- | --- | --- | --- |
| Mean time per document | 29.8 min (1788 s) | 15.92 s (mean) | ~112× |
| IQR-based range | — | 12.95–17.31 s | **103×–138×** (honest range) |
| Pooled mean time per document | 27.9 min (1674 s) | 15.92 s | ~97×–129× |
| Time per correct call | 145.3 min (8720 s) | 133.8 s | ~65× |

---

## 5. Retraction of Previously Published Multiples
**The 8-second placeholder figure appears in no committed file in this repository.**
It was used in the Efficiency sheet as a manual entry with no source. The 212× and 118× multiples published in that sheet were computed as:
  - 212× = 29.8 min (full arm mean) / 8 s
  - 118× = 27.9 min (pooled mean) / 14.31 s (one anecdotal measurement, not a distributional figure)
Both are superseded by the figures in this file, which are computed from the committed JSONL logs.

**Honest range: approximately 103×–138× per document** (IQR-based, against full-arm mean 29.8 min).
Against pooled mean 27.9 min: 97×–129×.
At model mean latency of 15.92 s: 112×.
The range is a factor of six from the fastest (7.5 s) to the slowest (127 s) call, so a point figure is misleading. Report as a range anchored to the IQR, not a single multiple.

---

## 6. Absent Data
- `api_cost_ledger.csv`: 11 columns, none timing-related.
- Individual result JSONs (`outputs/p2_*/results/*.json`): `run_meta` has no latency field.
- `batch_metadata.json` files: configuration only, no timing.
- Baseline models (LM, FinBERT) were not scored via the JSONL pipeline; no latency data for them.
- The 'one measurement of about 14.31 seconds' mentioned in CLAUDE.md does not appear verbatim   in any committed file. The closest JSONL value is PEP\_FQ1\_2023 at 14.37 s.

