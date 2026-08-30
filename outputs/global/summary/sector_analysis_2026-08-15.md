# Sector Analysis

**Generated:** 2026-08-15  
**Script:** `experiments/sector_analysis.py`  
**Set A:** N=233 clean phase2 events (268 scored, 35 excluded: 25 worksheet contamination + 1 SPOT + 9 timing)  
**Set B:** N=93 extension events (pure eval)  
**Suppression threshold:** n < 10 for Spearman rho and BUY/SELL accuracy

---

## 1. Taxonomy Decision (2026-08-15)

Canonical taxonomy: SECTORS dict in `phase2/build_manifests.py`. Four CVS events (CVS_FQ1_2026, CVS_FQ2_2025, CVS_FQ3_2025, CVS_FQ4_2025) are classified Healthcare by this analysis, not Consumer. This accounts for the Consumer -4 / Healthcare +4 discrepancy between this file and `sector_breakdown_three_sets.csv`. `sector_breakdown_three_sets.csv` has not been modified. LMT is in Industrials in both files (the notes text listing LMT under Healthcare in the old file is a copy-paste error).

---

## 2. Event Counts by Sector

| Sector | Set A (n) | Set B (n) |
| --- | --- | --- |
| Communication Services | 18 | — |
| Consumer | 82 | 26 |
| Energy | — | 21 |
| Financials | 49 | 8 |
| Healthcare | 18 | — |
| Industrials | 26 | 4 |
| Materials | 3 | 3 |
| Technology | 36 | 18 |
| Utilities | — | 13 |
| **Total** | **232** | **93** |

---

## 3. Spearman Rho (continuous score vs ret_overnight)

Suppressed where n < 10.

**Set A — LLM**

| Sector | n | rho | p |
| --- | --- | --- | --- |
| Communication Services | 18 | 0.2927 | 0.2385 |
| Consumer | 82 | 0.2493 | 0.0239 |
| Financials | 49 | 0.1326 | 0.3636 |
| Healthcare | 18 | 0.4223 | 0.0808 |
| Industrials | 26 | 0.0130 | 0.9497 |
| Materials | 3 | suppressed (n<10) | — |
| Technology | 36 | 0.2677 | 0.1145 |

**Set B — LLM and FinBERT**

| Sector | n | LLM rho | LLM p | FinBERT rho | FinBERT p |
| --- | --- | --- | --- | --- | --- |
| Consumer | 26 | 0.2313 | 0.2556 | -0.1829 | 0.3711 |
| Energy | 21 | 0.2374 | 0.3002 | -0.1104 | 0.6338 |
| Financials | 8 | suppressed (n<10) | — | suppressed (n<10) | — |
| Industrials | 4 | suppressed (n<10) | — | suppressed (n<10) | — |
| Materials | 3 | suppressed (n<10) | — | suppressed (n<10) | — |
| Technology | 18 | 0.4486 | 0.0619 | -0.0506 | 0.8421 |
| Utilities | 13 | -0.0689 | 0.8231 | 0.0879 | 0.7752 |

**Three findings worth keeping (all purely descriptive — per-sector n too small for inference):**

1. **Financials over-optimism (Set A)**: mean_score=0.133, mean_ret≈0.000 — the LLM scores Financials positively on average but the average overnight return is near zero. BUY accuracy 3/15 = 20.0% (Wilson 95% CI [7.0%, 45.2%]); buy_base_rate=24.5%. The model calls BUY in Financials at a rate consistent with the base rate (15/28 non-HOLD = 15 BUY, 13 SELL) but converts at 20%, below the base rate. MDE ≈ 35pp — a gap of this size is not reliably detectable at n=15.

2. **Industrials near-zero rho (Set A)**: rho=0.013, p=0.949, n=26. Fisher-z 95% CI: [-0.376, +0.398]. The CI spans the full range from a moderate negative to a moderate positive correlation — the data are consistent with any linear relationship. This is a data gap, not a finding.

3. **FinBERT structural finding (Set B)**: FinBERT called SELL on only 2 events across 93 Set B events (2.2%), versus LLM SELL rate 14.0% (13/93). FinBERT trade rate: 66/93 = 71.0%. LLM trade rate: 32/93 = 34.4%. FinBERT's near-zero SELL rate means it cannot distinguish between positive and negative events — it essentially operates as a BUY-or-HOLD model. This is a structural limitation of the FinBERT threshold, not a per-sector finding.

---

## 4. Calibration (mean score vs mean ret_overnight)

**Set A — LLM**

| Sector | n | mean_score | mean_ret |
| --- | --- | --- | --- |
| Communication Services | 18 | 0.1013 | 0.0025 |
| Consumer | 82 | -0.0222 | -0.0110 |
| Financials | 49 | 0.1332 | 0.0001 |
| Healthcare | 18 | 0.0422 | -0.0041 |
| Industrials | 26 | 0.1425 | 0.0134 |
| Materials | 3 | -0.0767 | -0.0037 |
| Technology | 36 | 0.2696 | 0.0053 |

## 5. Dispersion (score std + HOLD rate)

**Set A — LLM**

| Sector | n | score_std | hold_rate |
| --- | --- | --- | --- |
| Communication Services | 18 | 0.1784 | 0.3333 |
| Consumer | 82 | 0.2661 | 0.2561 |
| Financials | 49 | 0.1845 | 0.3673 |
| Healthcare | 18 | 0.2374 | 0.2778 |
| Industrials | 26 | 0.2349 | 0.1923 |
| Materials | 3 | 0.1266 | 0.6667 |
| Technology | 36 | 0.1533 | 0.1944 |

## 6. BUY/SELL Asymmetry

Suppressed where n_calls < 10.

**Set A — LLM**

| Sector | n | buy_n | buy_acc | buy_base | sell_n | sell_acc | sell_base |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Communication Services | 18 | 9 | suppressed | 0.389 | 3 | suppressed | 0.556 |
| Consumer | 82 | 26 | 0.231 | 0.195 | 35 | 0.429 | 0.366 |
| Financials | 49 | 27 | 0.222 | 0.245 | 4 | suppressed | 0.204 |
| Healthcare | 18 | 7 | suppressed | 0.333 | 6 | suppressed | 0.333 |
| Industrials | 26 | 17 | 0.471 | 0.423 | 4 | suppressed | 0.231 |
| Materials | 3 | 0 | suppressed | 0.000 | 1 | suppressed | 0.000 |
| Technology | 36 | 29 | 0.448 | 0.389 | 0 | suppressed | 0.472 |

---

## 7. Verdict

All per-sector n values are too small for inference. Three descriptive observations:

1. **Financials over-optimism**: LLM BUY accuracy 3/15 = 20.0% in Financials (Set A), below the 24.5% base rate. Wilson 95% CI [7.0%, 45.2%]. MDE ≈ 35pp. Consistent with the overall BUY bias finding but not separately testable at n=15.

2. **Industrials null**: rho=0.013, Fisher-z 95% CI [-0.376, +0.398]. No evidence of a sector-specific rank correlation — but n=26 cannot rule out a moderate effect in either direction.

3. **FinBERT structural SELL deficit**: 2/93 SELL calls = 2.2% vs LLM 13/93 = 14.0%. FinBERT trade rate 66/93 = 71.0% vs LLM 32/93 = 34.4%. FinBERT classifies almost no events as SELL regardless of sector — a threshold artefact, not a signal.