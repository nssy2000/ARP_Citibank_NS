# Repository Inventory: ARP Citibank Earnings Analysis

**Repository:** `/Users/nigelsim/Desktop/ARP_Citibank_NS`  
**Project Type:** Python (LLM-powered earnings analysis pipeline)  
**Total Size:** 1.7 GB  
**Date Generated:** 2026-08-30  
**Python Files:** 105  
**Total Manifests:** 98  
**Total Docs:** 1,391 files

---

## Section 1 — Directory Tree (3 Levels Deep)

### Root Directory Structure (1.7G, 18 top-level items)

Key folders:
- **data/** (58M) - workbooks, caches
- **docs/** (951M) - 1,391 earnings materials + FOMC + news (51 active phase2 issuers)
- **outputs/** (700M+) - canonical results and run archives
- **experiments/** (904K, 42 scripts) - validation, sweeps, ablations
- **phase2/** (888K) - manifest building, sourcing, auditing infrastructure
- **eval/** - calibration/evaluation modules
- **manifests/** (98 JSON files) - document lists for each issuer

### Directory Sizes (Level 0-1)

| Folder | Size | Items | Notes |
|--------|------|-------|-------|
| `data/` | 58M | 3 subdirs | 6 Master_Data xlsx, 54M yfinance cache |
| `docs/` | 951M | 151 folders | Earnings (400+), FOMC (11), news (300) |
| `outputs/` | 700M+ | 150+ folders | Canonical results + run archives |
| `experiments/` | 904K | 42 .py | Validation scripts |
| `phase2/` | 888K | 3 subdirs | Build/audit infrastructure |
| `eval/` | 200K | 7 .py | Calibration |
| `manifests/` | 2M | 98 .json | Document manifests |

### Level 2 Examples

**outputs/global/summary/** (147 files)
- Canonical results: `global_outcome_calibration_phase2.csv`, `backtest_equity.csv`, `item_e_walkforward.json`, `ext2_holding_curve.csv`, `api_cost_ledger.csv`
- Analysis: robustness, ablation, contamination, cost grids, baseline comparisons

**outputs/p2_[issuer]/** (71 phase2 issuers)
- `results/` - canonical JSON (TICKER_FQn_YYYY.json per quarter)
- `runs/` - timestamped archives (same files, version control)
- `extracted/` - cached text (speeds rescores)

**data/workbook/** (6 xlsx files)
- Latest: `Master_Data_Phase_3_2026-08-20_synced.xlsx` (1.1M)
- Backups: _CORRECTED, _LOCKED, _NEW_REPAIRED versions

**phase2/audit/** (8 scripts)
- Report dates, news leakage, blend consistency, manifest docs, freshness, coverage

---

## Section 2 — Python File Inventory

**Total: 105 .py files** (105 tracked, excluding __pycache__)

### Core Pipeline (11 files)

| File | Purpose | Status | Imports |
|------|---------|--------|---------|
| `report_pipeline.py` | LLM orchestration | **[LIVE]** | 24 |
| `run_reports.py` | CLI: micro layer scoring | **[LIVE]** | 5 |
| `blend.py` | Score blending + thresholds | **[LIVE]** | 52 |
| `backtest.py` | P&L backtester | **[LIVE]** | 32 |
| `quant_layer.py` | Quantitative scoring | **[LIVE]** | 13 |
| `llm_macro.py` | FOMC scoring | **[LIVE]** | 6 |
| `llm_news.py` | News digest scoring | **[LIVE]** | 10 |
| `eval/run_eval.py` | Calibration engine | **[LIVE]** | 12 |
| `eval/calibrate.py` | Threshold tuning | **[LIVE]** | 15 |
| `eval/outcomes.py` | Ground truth labeling | **[LIVE]** | 15 |
| `bootstrap_stats.py` | Resampling utilities | **[LIVE]** | 10 |

### Infrastructure (7 files)

| File | Purpose | Status |
|------|---------|--------|
| `build_cost_ledger.py` | Aggregate API costs | **[LIVE]** |
| `export_sheet_rows.py` | Export to group workbook | **[LIVE]** |
| `compare_runs.py` | Diff results | **[STANDALONE]** |
| `phase2/build_manifests.py` | Generate manifests | **[LIVE]** |
| `phase2/export_rows.py` | Export phase2 to sheet | **[LIVE]** |
| `phase2/ods_utils.py` | ODS/Excel utilities | **[LIVE]** |

### Data Resolution (9 files)

| File | Purpose | Status |
|------|---------|--------|
| `phase2/resolve_report_dates.py` | Map fiscal → real dates | **[LIVE]** |
| `phase2/fix_report_dates_from_human_prices.py` | Cross-validate dates | **[LIVE]** |
| `phase2/build_human_prices.py` | Cache prices for validation | **[LIVE]** |
| `phase2/triage_docs.py` | Categorize documents | **[STANDALONE]** |
| `phase2/gap_report.py` | Report missing quarters | **[STANDALONE]** |
| `phase2/sourcing/edgar_lookup.py` | Fetch SEC EDGAR | **[LIVE]** |
| `phase2/sourcing/run_gap_pipeline.py` | CLI: batch sourcing | **[STANDALONE]** |
| `phase2/sourcing/make_wave.py` | Prepare batch | **[LIVE]** |

### Audit (8 files in phase2/audit/)

| File | Purpose | Status |
|------|---------|--------|
| `check_report_dates.py` | Date validation | **[LIVE]** |
| `check_news_leakage.py` | Temporal boundaries | **[LIVE]** |
| `check_manifest_docs.py` | Manifest integrity | **[LIVE]** |
| `check_blend_consistency.py` | Internal consistency | **[LIVE]** |
| `check_artifact_freshness.py` | Score freshness | **[LIVE]** |
| `check_coverage_reconciliation.py` | Event counting | **[LIVE]** |
| `check_gap_sourcing.py` | Unsourced tracking | **[LIVE]** |
| `_common.py` | Audit utilities | **[LIVE]** |

### Eval (7 files in eval/)

| File | Purpose | Status |
|------|---------|--------|
| `__init__.py` | Package | **[LIVE]** |
| `excluded_events.py` | Contamination list | **[LIVE]** |
| `return_matrix.py` | Attribution analysis | **[LIVE]** |
| `extension_gaps.py` | Gap tracking | **[LIVE]** |
| `context_experiment.py` | Contextual accuracy | **[STANDALONE]** |

### Experiments (42 files)

**Robustness (5):** leave_one_out, quote_verification, asymmetry, macro_weight_axis, macro_ablation

**Extensions (12):** execution_cost_grid, lm_baseline, contamination_audit, conviction_sizing, finbert, kappa, holding_period, rq16_surprise, section_ablation, walkforward, human_vs_llm, information_set

**Sweeps (10):** phase2_pnl_weight_threshold, weight_threshold, phase2_threshold, phase2_n268_constrained, pooled, pnl, pnl_sweep_robustness, conviction_position_sizing, section_ablation_rethreshold, section_boundary_audit

**Baselines (9):** finbert_extension, lm_baseline_extension, section_ablation_gate_negative_test, section_attribution_check, sector_analysis, supplementary_rescore, notes_analysis, build_workbook, verify_gathered_docs

### One-Off & Debug (16 files)

| File | Purpose | Status | Notes |
|------|---------|--------|-------|
| `workbook_audit.py` | Audit group sheet | **[DEAD]** | v1, superseded |
| `workbook_audit_v2.py` | Audit v2 | **[DEAD]** | v2 variant |
| `workbook_debug*.py` (6 files) | Debug Human rows, prices, counts | **[DEAD]** | ephemeral |
| `fix_workbook_2026_08_14.py` | One-off workbook correction | **[STANDALONE]** | 2026-08-14 |
| `example_runthrough.py` | Tutorial | **[STANDALONE]** | educational |
| `generate_report_figures.py` | Figure generation | **[STANDALONE]** | reporting |
| `regenerate_figures.py` | Regenerate figures | **[STANDALONE]** | reporting |
| `scratch/extract_pre_sealed.py` | Obsolete pre-sealed extract | **[DEAD]** | deprecated |
| `figures/plot_all_figures.py` | Visualization | **[LIVE]** | 0 imports |
| `tests/phase2/test_gap_report.py` | Unit test | **[LIVE]** | 1 file |

### Cross-Reference Summary

**Most Imported:**
1. blend.py (52 files)
2. backtest.py (32)
3. report_pipeline.py (24)
4. calibrate.py (15)
5. outcomes.py (15)
6. quant_layer.py (13)
7. run_eval.py (12)
8. weight_threshold_sweep.py (12)
9. _common.py (12)
10. bootstrap_stats.py (10)

**Isolated (0-2 imports):** All workbook_debug*.py, fix_workbook_2026_08_14.py, scratch/extract_pre_sealed.py

---

## Section 3 — outputs/ Subfolder Inventory

### outputs/global/summary/ (147 files, canonical results)

**Core results (CLAUDE.md references):**
- `global_outcome_calibration_phase2.csv` (39K) - thresholds, weights, accuracy
- `backtest_equity.csv` (46K) - daily P&L curve, 171 trades
- `item_e_walkforward.json` (8.7K) - walk-forward metrics
- `ext2_holding_curve.csv` (1.4K) - returns by holding period
- `api_cost_ledger.csv` (68K) - costs by issuer/layer

**Tier 1 robustness:** leave_one_out, quote_verification, asymmetry, macro ablation results

**Tier 2/Extensions:** cost grid, LM baseline, contamination audit, conviction sizing, FinBERT

**Calibration:** phase2_threshold_sweep, weight_threshold_sweep, accuracy reconciliation

**Analysis:** company attribution, direction decomposition, frontier table, return matrix, sector analysis

**Audit:** effective_sample_funnel, figure_reconciliation, extension preregistration, retracted findings

### outputs/macro/ (FOMC scoring results)
- Cached scores, reused across all issuers with same report_date window

### outputs/news/ (Pre-earnings digest scores)
- Currently earns 0.0 blend weight

### outputs/quant/ (Quantitative layer results)
- p2_[issuer]/results/ directories
- Also earns 0.0 blend weight

### outputs/p2_[71 phase2 issuers]/ (active results)

Each issuer folder:
- **results/** - canonical JSON files (TICKER_FQn_YYYY.json)
- **runs/** - timestamped archives (20260718T214107Z/, etc.)
  - Each run: results/, summary/, logs/, batch_metadata.json
  - **Duplication:** results/ files are byte-for-byte identical to latest run's results/
- **extracted/** - cached extracted text (PDFs→text)
- **logs/** - API call logs
- **summary/** - per-issuer statistics

**Phase 2 Issuers (71 total):**
Adobe, Airbnb, Allianz, Alphabet, Amazon, AMD, Apple, Bank of America, Barclays, Boeing, Booking Holdings, Broadcom, Caterpillar, Charles Schwab, Chevron, Chipotle, Citigroup, Coca-Cola, Coinbase, Colgate-Palmolive, Comcast, Costco, CVS Health, Datadog, Dell, Delta Air Lines, Disney, Duke Energy, eBay, Eli Lilly, Expedia, ExxonMobil, FedEx, Ford, Freeport-McMoran, General Mills, Goldman Sachs, Heineken, Hilton, Home Depot, IBM, Intel, Johnson & Johnson, Kraft Heinz, Lenovo, Linde, Lockheed Martin, Lowes, Lululemon, LVMH, Maersk, Marriott, Mastercard, McDonald's, Meta, MetLife, Micron, Microsoft, Nestlé, Netflix, Nike, Novo Nordisk, NVIDIA, Oracle, Palantir, PayPal, PepsiCo, Pfizer, Pinterest, PUMA, Robinhood Markets, Salesforce, Shell, Shopify, Siemens, Sony, Spotify, Standard Chartered, Starbucks, Target, Tesla, Uber, Union Pacific, United Airlines, UnitedHealth, Visa, Walmart, Workday

**Variants with extensions:**
- p2_adobe_ext2026_08_13/, p2_american_express_ext2026_08_13/, etc. (20+ folders)
- Different weights/thresholds for ablation studies

### Retired Issuers (6 folders, NOT active)
- bank_of_america/, boeing/, disney/, jpm/, netflix/, target/
- Used to build/validate pipeline pre-phase2
- Should NOT be cited going forward (per CLAUDE.md)

### Duplication Analysis

**Finding: YES, results/ and runs/ are exact duplicates**

Evidence:
- `outputs/p2_netflix/results/NFLX_FQ1_2025.json` (11K, MD5: 2c3b61481c...)
- `outputs/p2_netflix/runs/20260730T174141Z/results/NFLX_FQ1_2025.json` (11K, same MD5)
- Byte-for-byte identical

Purpose: runs/ serves as version-control archive; results/ is the live symlink/copy.

**macOS duplicate folders:**
- docs/: 74 folders with ' 2' naming (empty, ~500K total)
- outputs/: 108 folders with ' 2' naming
- Harmless (macOS artifact), can be deleted

---

## Section 4 — docs/ File Categorization

**Total: 1,391 files**

| Category | Count | Size | Notes |
|----------|-------|------|-------|
| IR press release | 280 | 150M | Company-authored (PDF/HTML) |
| IR presentation | 210 | 120M | Investor decks |
| Motley Fool transcript | 20 | 15M | Third-party |
| InsiderMonkey transcript | 31 | 20M | Third-party |
| AlphaStreet transcript | 3 | 2M | Third-party |
| Capital IQ (*_Earnings_Call_Transcript.htm) | 54 | 40M | SEC EDGAR standard |
| Other transcript (Benzinga/Globe/unknown) | 120 | 80M | Miscellaneous sources |
| FOMC minutes | 11 | 8M | docs/macro/fomc_minutes/ |
| News digest | 300 | 330M | docs/news/ (pre-earnings) |
| Supplemental/other | 362 | 186M | Company supplements, 10-Q/K excerpts |

**Coverage:** 51 active phase2 issuers (CY{year}-Q{quarter} normalized), 6 retired issuers (legacy), 30+ others (sparse/archived)

**Largest folders:**
- Bank of America (93M), Lenovo (16M), Lululemon (9.2M), McDonald's (3.8M), Goldman Sachs (2.9M)

---

## Section 5 — data/workbook/ Excel File Inventory

**Total: 6 .xlsx files**

| Filename | Size | Date | Current? | Notes |
|----------|------|------|-----------|-------|
| `Master_Data_Phase_3_2026-08-20_synced.xlsx` | 1.1M | Aug 20 | **YES** | Latest, primary (live) |
| `Master_Data_Phase_3_2026-08-20.xlsx` | 1.1M | Aug 20 | NO | Pre-sync backup |
| `Master_Data_CORRECTED_2026-08-14.xlsx` | 709K | Aug 20 | NO | Corrected round 2 |
| `Master_Data_CORRECTED_2026-08-13.xlsx` | 591K | Aug 20 | NO | Corrected round 1 |
| `Master_Data_LOCKED_2026-08-13.xlsx` | 582K | Aug 20 | NO | Locked snapshot |
| `Master_Data_NEW_REPAIRED_2026-08-09.xlsx` | 620K | Aug 20 | NO | Repaired after audit |

**Current Version:** `Master_Data_Phase_3_2026-08-20_synced.xlsx` (latest, synced)

**Not Committed:** File exists locally (SharePoint), not in git repo (per CLAUDE.md)

**Schema (Phase 3):**
- **LLM_Data_Entry** (21 cols) - Company, Ticker, Year, Quarter, Rater, Type, Sentiment Score, Decision, Time (sec), Document Date, Closing Date, Prior Close, Opening Date, Next Day Open, Token Cost, Actual %, Direction, Correct?, Position, Net PL, Notes
- **Human_Data_Entry** (similar + 4 hidden helper cols for XLOOKUP to LLM)
- **Settings** (3 cells: threshold=2.0, cost_bps=10, short_bps=0)
- **Summary** (Accuracy/P&L by rater)
- **Company_List** (XLOOKUP ref, missing phase2 tickers)
- **Efficiency** (effort metrics, new)
- **Charts** (visualizations)

**Known Issues:**
1. Company_List incomplete (phase2 tickers missing)
2. Malformed OOXML (read with lxml recover=True)
3. Never edit via Claude (user forbade programmatic edits after 2 prior misclicks)
4. Token Cost column populated only after 2026-08-20

---

## Section 6 — Duplication

### results/ vs runs/

**Exact duplicates confirmed:**
- Sample: NFLX_FQ1_2025.json (11K, MD5 match)
- Interpretation: results/ is live; runs/ is timestamped archive
- Cost: ~200M shared storage (avoidable via symlinks)

### macOS ' 2' Folders

- docs/: 74 empty/partial copies (~500K)
- outputs/: 108 empty/partial copies
- Harmless; can be deleted

**Total wasted:** ~1-2M (negligible, <0.2% of repo)

---

## Section 7 — Scratch, Superseded, One-Off Files

### Root-Level Debug Scripts (9 files, ALL DEAD)

| File | Size | Status | Purpose |
|------|------|--------|---------|
| `workbook_debug.py` | 1.9K | **[DEAD]** | Debug Human no-match |
| `workbook_debug2.py` | 905B | **[DEAD]** | Debug variant |
| `workbook_debug3.py` | 2.2K | **[DEAD]** | Debug EXTENSION issues |
| `workbook_debug4.py` | 3.8K | **[DEAD]** | Debug price discrepancies |
| `workbook_debug5.py` | 3.6K | **[DEAD]** | Verify frozen counts |
| `workbook_debug6.py` | 1.4K | **[DEAD]** | Debug variant |
| `workbook_audit.py` | 15K | **[DEAD]** | Audit sheet (v1, superseded) |
| `workbook_audit_v2.py` | 15K | **[DEAD]** | Audit v2 |
| `fix_workbook_2026_08_14.py` | 12K | **[STANDALONE]** | One-off correction |

**Pattern:** All ephemeral; can be safely deleted.

### scratch/ Folder (32K, ALL DEAD)

| File | Size | Status | Purpose |
|------|------|--------|---------|
| `extract_pre_sealed.py` | 1.7K | **[DEAD]** | Obsolete pre-sealed logic |
| `pre_sealed_dump.md` | 9.7K | **[DEAD]** | Context dump |
| `extracts/` | ~21K | **[DEAD]** | Pre-sealed artifacts |

**Status:** Remnants of discontinued pre-sealed evaluation phase. Safe to delete.

### Experiments (42 files, ALL LIVE)

All 42 experiment files are active (imported or run regularly). Despite one-off/exploratory nature, they are not dead code.

### Files with Date Stamps

**Workbook:** Master_Data_Phase_3_2026-08-20_synced.xlsx (latest)

**Results:** backtest_equity_extension_2026_08_13/22/24.csv (timestamped snapshots)

**Outputs:** p2_*_ext2026_08_13/ (experimental folders)

**Purpose:** Snapshots/versions during iterative development. Latest versions (highest date) are canonical.

### Summary of Dead Code

**Total reclaimable:** ~50K (4-6% of repo, harmless to keep)

**Safe to delete:**
- workbook_debug*.py (6 files) - ~15K
- workbook_audit*.py (2 files) - ~30K
- scratch/ folder (3 files/dirs) - ~32K

**Recommended action:** Archive or delete these files; no impact on active pipeline.

---

## Appendix: File Type Distribution

| Type | Count | Size | Locations |
|------|-------|------|-----------|
| `.py` (Python) | 105 | 800K | root, eval/, experiments/, phase2/ |
| `.json` (JSON) | 200+ | 150M | outputs/global, manifests/, p2_*/results |
| `.csv` (CSV) | 100+ | 100M | outputs/global/summary |
| `.xlsx` (Excel) | 6 | 3.5M | data/workbook/ |
| `.pdf` (PDF) | 400+ | 500M | docs/ |
| `.html`/`.htm` (HTML) | 200+ | 150M | docs/ |
| `.txt` (Text) | 300+ | 330M | docs/news/ |
| `.png` (PNG) | 30+ | 200M | report_figures/, outputs/ |
| `.md` (Markdown) | 50+ | 1M | root, outputs/ |
| Other (logs, config) | 100+ | 50M | .git/, outputs/*/logs |

**Total: 1.7 GB**

