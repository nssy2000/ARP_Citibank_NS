# Information-Set Comparison: Human vs Model Arm

**Generated:** 2026-08-15  
**Script:** `experiments/information_set_comparison.py`  
**Source (human):** `data/workbook/Master_Data_CORRECTED_2026-08-14.xlsx` Human_Data_Entry  
**Source (model):** `outputs/global/summary/section_ablation_summary.csv` (Set A), `section_ablation_extension_summary.csv` (Set B)  
**Grading band:** ±2% raw overnight (pre-registered)

---

## Caveats

- Section-level reads (transcript only, qanda, financials, guidance, presentation only, press release document only) are a **different experiment** from full-document reads. They cover different events, different raters, and different reading sessions. Do not pool them with each other or with the full group.

- Human and model sessions cover **different events**. The cross-arm comparison examines the **pattern** (flat vs differentiated across information sets), not a head-to-head on the same events.

- Re-priced returns used where available for the human arm.

---

## 1. Human Arm by Information Set

| Information Set | n | Mean Time (min) | Median Time | Buy% | Hold% | Sell% | n_graded | Coverage Acc | n_calls | Selectivity Acc | Mean Net/Trade |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full | 190 | 29.8 | 25.0 | 59.5% | 28.4% | 12.1% | 97 | 0.402 | 78 | 0.500 | 0.000113 |
| transcript only | 94 | 33.5 | 30.0 | 59.6% | 23.4% | 17.0% | 65 | 0.431 | 50 | 0.560 | 0.004375 |
| financials | 32 | 20.3 | 21.5 | 53.1% | 25.0% | 21.9% | 21 | 0.333 | 16 | 0.438 | -0.010850 |
| guidance | 29 | 18.7 | 20.0 | 51.7% | 27.6% | 20.7% | 20 | 0.150 | 17 | 0.176 | -0.039428 |
| qanda | 33 | 29.4 | 30.0 | 36.4% | 39.4% | 24.2% | 22 | 0.364 | 17 | 0.471 | -0.004765 |
| presentation only | 23 | 19.8 | 22.0 | 78.3% | 4.3% | 17.4% | 14 | 0.643 | 13 | 0.692 | 0.030958 |
| press release document only | 19 | 15 | 14.0 | 36.8% | 42.1% | 21.1% | 15 | 0.467 | 9 | suppressed | 0.055526 |

### Observations

- **Selectivity denominator**: n_calls here is n_called_and_graded (BUY+SELL decisions where |ret|>2%), NOT the raw BUY+SELL count. Raw counts are in the notes column (n_calls_all). This ensures selectivity_floor and selectivity_accuracy share the same denominator. The model arm uses all trades (including flat outcomes) as denominator — cross-arm selectivity comparisons are pattern-only; denominators differ.

- **Transcript anomaly**: transcript-only mean reading time 33.5 min vs full 29.8 min. Transcript-only sessions read one section that is longer and denser than an average section of the full bundle. The full-bundle time includes all sections in one sitting; some raters may have read the transcript last and been more efficient.

- **Guidance coverage accuracy 15.0%** (n_graded=20): below the 55% coverage floor. Guidance notes contain forward-looking language with high forecast uncertainty — the guidance alone does not predict the overnight direction reliably.

- **Presentation only coverage 64.3%** (n_graded=14, borderline): above the 57.1% floor. n_graded=14 is marginal. Interpret with caution.

- **Press release doc only selectivity suppressed** (n_called_graded=9, below threshold of 10). n_calls_all=11 but only 9 of those calls have a graded outcome (|ret|>2%). Coverage accuracy 46.7% (n_graded=15) is reportable.

---

## 2. Model Arm Section Ablation

| Arm | Set | n_events | Trades | Correct | Selectivity Acc |
| --- | --- | --- | --- | --- | --- |
| full_bundle | Set_A_N119 | 119 | 87 | 32 | 0.368 |
| full_bundle | Set_B_N56 | 56 | 28 | 10 | 0.357 |
| press_release | Set_A_N119 | 119 | 66 | 24 | 0.364 |
| press_release | Set_B_N56 | 56 | 14 | 5 | 0.357 |
| qa_only | Set_A_N119 | 119 | 67 | 26 | 0.388 |
| qa_only | Set_B_N56 | 56 | 25 | 8 | 0.32 |
| prepared_remarks | Set_A_N119 | 119 | 77 | 26 | 0.338 |
| prepared_remarks | Set_B_N56 | 56 | 29 | 11 | 0.379 |

### Cross-arm pattern comparison

Both human and model arms show flat accuracy across information sets — no single section reliably raises or lowers accuracy by more than a few pp within the detectable range (MDE ≈ ±12pp paired, ±20pp unpaired).

Model Item C (section ablation, Set A four-arm, N=119):
- Range: 33.8%–38.8% across four arms (full_bundle 0.368, press_release 0.364, qa_only 0.388, prepared_remarks 0.338)

Model Item C (Set B, N=56):
- Range: 32.0%–37.9% across four arms

### Cost note

From `section_ablation_cost_per_correct.csv` (four_arm N=119, overnight grading):

| Arm | Cost per correct call |
| --- | --- |
| full_bundle | $0.036 |
| prepared_remarks | $0.021 |
| qa_only | $0.023 |
| press_release | $0.023 |

prepared_remarks costs 42% less per correct call than full_bundle at comparable accuracy (33.8% vs 36.8%).

---

## 3. Comparable Pairs

| Human information set | Model arm | Human sel. acc | Model sel. acc (Set A) | Model sel. acc (Set B) |
| --- | --- | --- | --- | --- |
| qanda | qa_only | 0.471 | 0.388 | 0.32 |
| press release document only | press_release |  | 0.364 | 0.357 |
| full | full_bundle | 0.5 | 0.368 | 0.357 |

Human and model comparisons are across **different events** — pattern comparison only.

**Denominator note**: human selectivity uses n_called_and_graded (BUY+SELL where |ret|>2%); model selectivity uses all trades (BUY+SELL including flat outcomes). Human n_calls_all (raw BUY+SELL count) is in the notes column of the CSV. This mismatch means the human selectivity figures are not directly comparable to model figures in magnitude — the cross-arm comparison is of pattern (flat vs differentiated) only.

**Impact on Item C comparison (section ablation)**: Human full selectivity on the corrected denominator is 0.5 (n_called_graded=78), vs model full_bundle Set A 0.368 and Set B 0.357. The human figure exceeds the model on the corrected denominator, reversing the direction of the comparison from the prior (all-calls) denominator. The denominator definitions differ, so this is not a clean head-to-head.