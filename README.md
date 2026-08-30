# Applied Research Project — LLM-powered earnings signal

This repository contains the model arm of a Citibank Applied Research Project dissertation
submitted in September 2026. The project tests whether a large language model (DeepSeek)
can produce directionally correct BUY/HOLD/SELL predictions for individual stocks from
their quarterly earnings materials, and whether those predictions carry a tradeable
overnight price signal.

The pipeline reads a document bundle for each company/quarter event (press release,
investor presentation, and earnings call transcript), scores it with an LLM, blends the
result with a macro layer (FOMC minutes) and a quantitative layer (price momentum, EPS
surprise), then grades predictions against the actual overnight gap on the report date.
All 232 clean events in the published universe span 71 phase-2 issuers from 2023 to 2026.

### A note on the earnings call transcripts

The model arm scored a document bundle for each event, comprising the issuer's press
release, its investor presentation and the earnings call transcript. The press releases
and presentations are in this repository. The transcripts are not, because most were
obtained from commercial providers whose terms do not permit redistribution.

Every excluded transcript is listed in `docs/TRANSCRIPT_SOURCES.md` with the company,
fiscal quarter and source, so the corpus can be reconstructed by anyone with access to
those providers. The full corpus is held locally and can be made available to
examiners on request.

Nothing else has been withheld. The scoring outputs, the analysis code, the price data
and the workbook are all present, so every figure in the report can be traced to its
source without the transcripts themselves.

---

## Deployed configuration for the published results

All headline figures in the dissertation use these constants, hard-coded in `blend.py`:

| Parameter | Value |
|---|---|
| Blend weights (micro / macro / news / quant) | 0.80 / 0.20 / 0.00 / 0.00 |
| Signal threshold — upper (BUY) | +0.20 |
| Signal threshold — lower (SELL) | −0.10 |
| Clean event universe | N = 232 |
| Grading band (overnight \|return\| threshold) | ±2% (pre-registered) |
| Transaction cost assumption | 10 bps round-trip |

**Superseded values:** any file or comment referencing weights 0.55/0.45, thresholds
±0.25, accuracy 65.3%, or N = 233 predates the regime promoted on 2026-08-19 and the
DIS_FQ1_2025 exclusion ruled on 2026-08-24. Those figures are retained for audit
purposes but should not be cited.

---

## Verify a headline figure

| Claim | File | Field |
|---|---|---|
| Selectivity 62.4% (68/109) | `outputs/global/summary/item_e_walkforward.json` | `in_sample_deployed.accuracy` |
| Mean net per trade +1.796% | `outputs/global/summary/item_e_walkforward.json` | `in_sample_deployed.mean_net_pct` |
| Spearman ρ = 0.2288 (\|score\| vs \|return\|) | `outputs/global/summary/asymmetry_rank_correlation.csv` | `spearman_rho` |
| BUY/SELL recall gap p = 0.004 | `outputs/global/summary/asymmetry_recall_gap_test.csv` | `p_value_ztest` |
| Rank correlation by horizon | `outputs/global/summary/ext2_holding_curve.csv` | `rank_correlation` column |
| Per-event scoring records | `outputs/p2_<issuer>/results/<TICKER>_FQ<N>_<YEAR>.json` | one file per event |

The per-event JSON contains the blended score, signal, LLM summary, evidence quotes,
report date, and the price pair used to compute the overnight gap.

---

## Folder guide

```
.
├── docs/                   Source documents fed to the pipeline
│   ├── <issuer>/           One folder per company; contents are IR press releases,
│   │   └── CY<Y>-Q<Q>/    investor presentations, and supplemental filings.
│   ├── macro/fomc_minutes/ Federal Reserve FOMC minutes (public domain)
│   └── TRANSCRIPT_SOURCES.md  Full list of excluded transcripts with vendor/quarter
│
├── outputs/                All scored and derived outputs
│   ├── global/summary/     Canonical headline files: item_e_walkforward.json,
│   │                       global_outcome_calibration_phase2.csv, backtest_equity.csv,
│   │                       ext2_holding_curve.csv, asymmetry_rank_correlation.csv,
│   │                       asymmetry_recall_gap_test.csv, api_cost_ledger.csv
│   ├── p2_<issuer>/        Per-issuer micro-layer outputs
│   │   ├── results/        Canonical scored JSONs (one per event)
│   │   ├── extracted/      Cached plain-text extracts (speeds rescoring)
│   │   ├── logs/           API call logs
│   │   └── summary/        Per-issuer summary statistics
│   ├── macro/results/      FOMC macro scores (cached, reused across all issuers)
│   └── quant/              Quantitative layer scores (weight = 0 in deployed config)
│
├── data/
│   ├── workbook/           Master data workbook
│   │   ├── Master_Data_Phase_34_corrected.xlsx   Current version
│   │   └── archive/        Five superseded workbook versions with provenance README
│   ├── human/
│   │   ├── human_decisions_export_2026-08-12.csv Human rater decisions (all events)
│   │   └── notes/          Rater reading notes (PDFs, one per rater/event)
│   ├── quantitative/       yfinance price cache and FRED macro cache
│   └── timing/             Non-US issuer release-timing classification
│
├── humans/                 Individual rater scoring worksheets (PDFs, named by rater)
│
├── experiments/            Analysis and validation scripts (42 files)
│   │                       Covers: robustness checks (Tier 1), extensions (Tier 2),
│   │                       weight/threshold sweeps, section ablation, FinBERT and
│   │                       Loughran–McDonald baselines, contamination audit
│   └── (see individual file headers for inputs and outputs)
│
├── eval/                   Calibration and evaluation modules
│   ├── run_eval.py         Threshold search and LOOCV across the phase-2 universe
│   ├── calibrate.py        Threshold tuning logic
│   ├── outcomes.py         Ground-truth labelling (forward return fetching)
│   └── excluded_events.py  Definitive list of 36 excluded events with reasons
│
├── phase2/                 Pipeline build infrastructure
│   ├── build_manifests.py  Generate per-issuer document manifests from docs/
│   ├── resolve_report_dates.py  Map fiscal quarters to real report dates
│   ├── export_rows.py      Export LLM decisions to group workbook TSV format
│   └── audit/              Eight consistency-check scripts (dates, leakage, coverage)
│
├── manifests/              Per-issuer document lists (98 JSON files, p2_<slug>_reports.json)
│
├── prompts/                LLM prompt template (llm_analysis_prompt_template.md)
│
├── figures/                Generated figures F1–F22 (PNG and PDF, all dissertation figures)
│
├── report_figures/         Final polished versions submitted with the dissertation
│
└── tests/                  Unit tests (phase2/test_gap_report.py)
```

---

## Naming conventions

**`p2_` prefix** — all phase-2 manifests, output folders, and issuer slugs carry this
prefix (e.g. `manifests/p2_nvidia_reports.json`, `outputs/p2_nvidia/`). The six folders
without this prefix (`outputs/bank_of_america/`, `outputs/boeing/`, `outputs/disney/`,
`outputs/jpm/`, `outputs/netflix/`, `outputs/target/`) are the retired pre-phase-2
pipeline used to develop and validate the approach; they should not be cited.

**`FQ1_2025` vs `CY2025-Q1`** — result filenames use the issuer's fiscal quarter
(`TICKER_FQ1_2025.json`); source document folders under `docs/` use the calendar year
of the fiscal period being reported (`CY2025-Q1/`). These refer to the same quarter.

**`ext1`, `ext2`, `ext4`, `ext9`** — extension numbers from the model-arm robustness
specification (see `Model_Arm_Gap_Spec.md`). `ext2` is the holding-period curve,
`ext4` is conviction sizing, `ext9` is the execution-cost grid.

**Timestamped variants** — files named `*_extension_2026_08_22.csv` or `*_2026_08_13*`
are snapshots from earlier weight/threshold regimes. The unsuffixed files (e.g.
`backtest_equity.csv`, `global_outcome_calibration_phase2.csv`) are current.

---

## Reproduce the headline figures

```bash
# Install dependencies
pip install -r requirements.txt

# Re-blend scores at the deployed constants (reads already-scored results from outputs/)
python blend.py <issuer>                          # one issuer
# or for all phase-2 issuers, pass each p2_ slug

# Recompute calibration CSV and walkforward JSON
python -m eval.run_eval --output-suffix phase2

# Recompute P&L backtest
python backtest.py --calibration-csv outputs/global/summary/global_outcome_calibration_phase2.csv

# Recompute asymmetry and conviction analysis
python experiments/asymmetry_conviction_analysis.py

# Recompute holding-period curve
python experiments/holding_period_curve.py
```

To rescore events from source documents (requires a DeepSeek API key in `.env` as
`DEEPSEEK_API_KEY=...`):

```bash
python run_reports.py --issuer p2_nvidia      # score one issuer's micro layer
python llm_macro.py                           # score FOMC minutes (cached, idempotent)
```

---

## Root-level reference files

| File | What it is |
|---|---|
| `README.md` | This file |
| `handoff.md` | Session-to-session development state notes; describes pipeline decisions and the phase-2 build history |
| `NEW_VS_OLD_report.md` | Figure-by-figure reconciliation of results across the two weight/threshold regimes (0.55/0.45 → 0.80/0.20); identifies which claims changed and which broke |
| `Model_Arm_Gap_Spec.md` | Working specification for the five remaining model-arm robustness items (multi-horizon return matrix, holding-period curve, section ablation, FinBERT baseline, walk-forward build) |
| `repo_inventory.md` | Directory and file audit generated at the time of publication: file counts, sizes, Python file status (live / standalone / dead), output file provenance |
| `PUSH_CHECKLIST.md` | Preparation log documenting what was excluded from this repository before publication and why (transcripts, internal debug scripts, macOS artifacts) |
| `verify_all.txt` | Manual verification log: cross-checks between computed figures and workbook entries, run during the 2026-08-13 corrections pass |
| `Methodology_Deck.pptx` | Presentation slides describing the pipeline methodology |
