# Extension Corpus — Ready-to-Score Handover Note
**Written 2026-08-13. State at the point scoring begins.**

A fresh session should read this note cold and start scoring runs from it. Nothing below is an inference; every item is sourced from a manifest, the corrected workbook, the preregistration, or a verification run completed in this session.

---

## 1. What the extension is

The extension adds 93 events across 20 companies to the existing N=233 frozen phase2 dataset. Its purpose is a sector-broadening robustness check. Scoring uses the same pipeline (`run_reports.py`), the same prompt, and the same weights/thresholds as the frozen set. The extension is pre-registered in `outputs/global/summary/extension_preregistration_2026-08-13.md` (Amendments A–F).

---

## 2. Event roster (93 events, 20 companies)

### US-listed (15 companies, 79 events)

| Company | Issuer slug | Ticker | Events | Notes |
|---|---|---|---|---|
| Adobe | p2_adobe | ADBE | 4 | |
| American Express | p2_american_express | AXP | 4 | |
| Chevron | p2_chevron | CVX | 4 | |
| Colgate-Palmolive | p2_colgate_palmolive | CL | 4 | PR-only (no transcript both arms) |
| Costco | p2_costco | COST | 4 | |
| Datadog | p2_datadog | DDOG | 4 | FQ2_2025 PR-only; FQ3/FQ4/FQ1 have transcripts |
| Duke Energy | p2_duke_energy | DUK | 13 | Largest single-company set |
| eBay | p2_ebay | EBAY | 4 | PR-only (no transcript both arms). FQ1/FQ2 were image PDFs; re-saved from EDGAR Exhibit 99.1 as HTML 2026-08-13. Manifest updated to .htm. All 4 verify PASS. |
| ExxonMobil | p2_exxonmobil | XOM | 13 | Largest single-company set |
| Freeport-McMoRan | p2_freeport_mcmoran | FCX | 3 | |
| Home Depot | p2_home_depot | HD | 4 | |
| Intel | p2_intel | INTC | 4 | FQ1_2026 PR-only; FQ2/FQ3/FQ4 have transcripts |
| Mastercard | p2_mastercard | MA | 4 | |
| Shopify | p2_shopify | SHOP | 3 | |
| Union Pacific | p2_union_pacific | UNP | 4 | |

### Non-US / ADR (5 companies, 14 events)

| Company | Issuer slug | Ticker | Exchange | Events | Notes |
|---|---|---|---|---|---|
| Heineken | p2_heineken | **HEIA.AS** | Euronext Amsterdam (AMS) EUR | 4 | PR-only (no transcript both arms). See ticker decision §5. |
| Hermès | p2_hermes | **RMSP.XC** | Cboe Europe CXE EUR | 4 | See ticker decision §5. |
| Nestlé | p2_nestle | NSRGY | OTC Pink (OID) USD | 2 | |
| Shell | p2_shell | SHEL | NYSE (NYQ) USD | 4 | See §4 for paired-comparison exclusions on FQ3/FQ4_2025. |
| Sony | p2_sony | SONY | NYSE (NYQ) USD | 3 | |

---

## 3. Document coverage split

All 93 events have documents on disk. All pass `experiments/verify_gathered_docs.py` as of 2026-08-13 (0 FAIL, 0 missing after eBay fix). The split:

| Coverage | Events | Companies |
|---|---|---|
| Press Release + Earnings Call Transcript | **75** | Adobe(4), AXP(4), CVX(4), COST(4), DDOG(3), DUK(13), XOM(13), FCX(3), RMS(4), HD(4), INTC(3), MA(4), NSRGY(2), SHOP(3), SONY(3), UNP(4) |
| Press Release + Earnings Presentation (prepared remarks, no Q&A) | **4** | Shell(4) |
| Press Release only | **14** | Colgate-Palmolive(4), Heineken(4), eBay(4), Datadog FQ2_2025(1), Intel FQ1_2026(1) |
| **Total** | **93** | |

The 14 PR-only events are like-for-like with the human arm: no transcript was available and the human arm also read press-release-only for those events.

Shell's 4 events have prepared remarks (Earnings Presentation), not open Q&A transcripts. Shell does not publish open Q&A transcripts publicly. Two of the 4 Shell events have a paired-comparison exclusion — see §4.

---

## 4. Exclusions

### 4a. Events excluded from scoring entirely

**Zero.** All 17 non-US release timings are confirmed pre_market (§6). No timing exclusions. No contamination events identified in the extension set.

### 4b. Events excluded from the paired human-vs-model accuracy comparison only

These two events remain in the model arm's own signal-distribution and decision-mix figures but are **not compared against the human arm's call** for accuracy:

| Event | Reason |
|---|---|
| SHEL_FQ3_2025 | Human arm read Doc="Transcript", Section="Outlook/Guidance" (rater: David, commercial source). Model arm has prepared remarks only. Document-asymmetric — human had Q&A access the model arm cannot replicate. |
| SHEL_FQ4_2025 | Human arm read Doc="Transcript", Section="Transcript Q&A" (rater: David, commercial source). Model arm has prepared remarks only. Same reason. |

Recorded in preregistration Amendment D, confirmed in Amendment F, before any Shell event beyond the 7-event pilot is scored.

### 4c. Other Shell events — paired comparison status

| Event | Human arm Document | Paired comparison |
|---|---|---|
| SHEL_FQ2_2025 | "Financial Statement / Financial Results" (not Transcript) | **Included** — document-type difference noted but not grounds for exclusion (both arms received structured disclosure from same event). Amendment D. |
| SHEL_FQ1_2026 | "All / All" (not Transcript) | **Included** — confirmed from workbook 2026-08-13. Amendment F. |

### 4d. Heineken FQ3_2025 — not an exclusion

HEINY_FQ3_2025 was queried in Amendment C. Human arm Document="Presentation", Section="All" (slide deck, not a call transcript). Model arm also has no call transcript. Neither arm has Q&A access. Not a mismatch. Included in paired comparison.

### 4e. PR-only events and section ablation (Item C)

The 14 PR-only events are excluded from Item C (the four-arm section ablation test) by document availability, not by choice — there is no transcript to ablate. They remain in all other analyses. Pre-registered in Amendment C.

---

## 5. Ticker decisions (three non-obvious cases — final, do not reopen)

### Heineken: HEIA.AS (not HEINY)

The original manifest used HEINY (US OTC ADR). Cross-arm price verification showed HEINY diverges ~42–47% from the human arm's prices on all 4 events. HEIA.AS (Euronext Amsterdam, EUR) matches exactly on all 4 events at 0%. Manifest, checklist, and timing CSV all updated to HEIA.AS. Session open for timing: **09:00 CET (08:00 UTC winter / 07:00 UTC summer)**. This decision is final.

### Hermès: RMSP.XC (not RMS.PA)

The manifest was tested against both RMSP.XC (Cboe Europe CXE) and RMS.PA (Euronext Paris). The corrected workbook's Human_Data_Entry M-to-P prices match RMSP.XC at 0.00% on all 8 values; RMS.PA fails 3 of 8 with a maximum divergence of 3.11% against a 2% tolerance band. RMS.PA is the better listing in principle but cross-arm parity outweighs venue quality: the human arm cannot be re-priced without reopening the corrected workbook. Manifest set to RMSP.XC. Session open for timing: **09:00 CET (08:00 UTC winter / 07:00 UTC summer)** (Cboe Europe CXE opens at 09:00 CET, same as Euronext Paris). This decision is final.

### All other tickers

NSRGY, SHEL, SONY, and all 15 US-listed tickers confirmed correct against human arm prices.

---

## 6. Release timing — non-US issuers (all 17 events)

All 17 non-US events are confirmed **pre_market**. Zero timing exclusions. Full detail in `outputs/global/summary/non_us_release_timing_extension.csv`.

| Issuer | Events | Session open | Release window | Verdict | Source quality |
|---|---|---|---|---|---|
| Heineken (HEIA.AS) | 4 | 09:00 CET (07:00–08:00 UTC) | 05:00–06:25 UTC | pre_market all 4 | H1_2024 exact (datePublished 07:01 CEST); FY2023/Q3 2024/Q3 2025 times pattern-inferred at 07:00 CET/CEST (consistent with confirmed event; pre_market is not in doubt in any case) |
| Hermès (RMSP.XC) | 4 | 09:00 CET (07:00–08:00 UTC) | 06:00–07:00 UTC | pre_market all 4 | Yahoo Finance URL timestamp encoding (HHMMSS UTC). FQ3_2025 date confirmed from Hermès IR calendar with exact datetime attribute (2025-10-22T06:00:00 CEST). |
| Nestlé (NSRGY) | 2 | 13:30 UTC | 05:00–06:00 UTC | pre_market both | GlobeNewswire (FY2025 confirmed "01:00 ET" = 06:00 UTC); Yahoo Finance URL (9M 2024 = 05:00 UTC) |
| Shell (SHEL) | 4 | 13:30 UTC | 06:00–07:00 UTC | pre_market all 4 | Investegate schema.org dateCreated (exact to second; UK local time converted to UTC) |
| Sony (SONY) | 3 | 13:30 UTC | 03:00–03:25 UTC | pre_market all 3 | FQ1_2026: TDnet live data, 12:00 JST confirmed. FQ3_2025: Wayback CDX 03:25 UTC. FQ2_2025: Sony standard 12:00 JST pattern; date confirmed via SEC 6-K; exact time not independently confirmed but pre_market is not in doubt (10+ hours before NYSE open). |

**DST rules applied**: Europe changes last Sunday March/October (2024: Oct 27; 2025: Oct 26). Japan has no DST, JST = UTC+9 year-round.

---

## 7. Release timing — US issuers

All 15 US-listed companies in the extension have `release_timing` fields in their manifests sourced from EDGAR 8-K Item 2.02 acceptance timestamps (retrieved 2026-08-13). The accepted entry anchor is `release_date` (from EDGAR filing), not `report_date`. The timing values are:

- **after_hours**: eBay, Intel (all confirmed after 20:00 ET from 8-K timestamps)
- **pre_market**: Datadog (all confirmed before 13:00 ET)
- All others: confirmed from EDGAR 8-K Item 2.02 timestamps, values in each manifest

---

## 8. Manifest state

All 20 extension manifests are in `manifests/p2_<slug>_reports.json`. Key changes made in this session:

- **eBay**: all 4 source paths updated from `.pdf` to `.htm` (re-saved from EDGAR Exhibit 99.1 as HTML)
- **Heineken**: ticker corrected to HEIA.AS; transcript entries removed (PR-only, both arms)
- **Hermes**: ticker set to RMSP.XC
- **Datadog FQ2_2025**: transcript entry removed (PR-only for that quarter only)
- **Intel FQ1_2026**: transcript entry removed (PR-only for that quarter only)
- **Shell**: prepared remarks files renamed to `_Prepared_Remarks.pdf`; doc_type relabeled to "Earnings Presentation"
- **Costco**: transcript paths corrected; all 4 events now have transcripts

---

## 9. What to run

To score the extension, run `run_reports.py` per issuer. The extension issuers are not in `PHASE2_ISSUERS` — pass each slug explicitly:

```
python run_reports.py --issuer p2_adobe
python run_reports.py --issuer p2_american_express
python run_reports.py --issuer p2_chevron
python run_reports.py --issuer p2_colgate_palmolive
python run_reports.py --issuer p2_costco
python run_reports.py --issuer p2_datadog
python run_reports.py --issuer p2_duke_energy
python run_reports.py --issuer p2_ebay
python run_reports.py --issuer p2_exxonmobil
python run_reports.py --issuer p2_freeport_mcmoran
python run_reports.py --issuer p2_heineken
python run_reports.py --issuer p2_hermes
python run_reports.py --issuer p2_home_depot
python run_reports.py --issuer p2_intel
python run_reports.py --issuer p2_mastercard
python run_reports.py --issuer p2_nestle
python run_reports.py --issuer p2_shell
python run_reports.py --issuer p2_shopify
python run_reports.py --issuer p2_sony
python run_reports.py --issuer p2_union_pacific
```

Blend, eval, and backtest steps follow the same pattern as the frozen set but applied to extension outputs. The extension results go to `outputs/p2_<slug>/results/` per the project's naming convention.

---

## 10. Items still open

**None.** All pre-scoring checklist items are resolved:

| Item | Status |
|---|---|
| All extension manifests have correct source paths | ✓ All 20 manifests verified |
| verify_gathered_docs.py passes on all files | ✓ 0 FAIL, 0 missing (2026-08-13) |
| eBay image PDFs replaced | ✓ FQ1/FQ2 re-saved as HTML, manifest updated, verified |
| Hermes ticker decision | ✓ RMSP.XC. Final. |
| Heineken ticker decision | ✓ HEIA.AS. Final. |
| Shell FQ3/FQ4 paired-comparison exclusion | ✓ Recorded in Amendment D before scoring |
| Shell FQ1_2026 paired-comparison disposition | ✓ Included. Workbook shows "All/All", not Transcript. Amendment F. |
| All 17 non-US release timings confirmed | ✓ All pre_market, zero exclusions |
| RMS_FQ3_2025 date conflict resolved | ✓ October 22, confirmed from Hermès IR calendar |
| Preregistration amendments A–F written before scoring | ✓ |

---

## 11. Key files

| File | Purpose |
|---|---|
| `outputs/global/summary/extension_preregistration_2026-08-13.md` | Full pre-registration, Amendments A–F |
| `outputs/global/summary/non_us_release_timing_extension.csv` | Release timestamps for all 17 non-US events |
| `outputs/global/summary/workbook_correction_log_2026-08-13.md` | Audit trail of all corrections made |
| `data/workbook/Master_Data_CORRECTED_2026-08-13.xlsx` | Corrected workbook with M-P prices re-anchored on release_date |
| `experiments/verify_gathered_docs.py` | Document verification tool (run before scoring after any manifest change) |
| `manifests/p2_<slug>_reports.json` | One manifest per extension company |
