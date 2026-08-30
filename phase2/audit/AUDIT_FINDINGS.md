# Phase2 pipeline audit — findings (2026-08-09)

Audit of the completed 9-task gap-onboarding plan (N=161 → N=268). Read-only
scripts under `phase2/audit/check_*.py` (run via `python phase2/audit/check_*.py`
from repo root); raw per-script output is reproducible by rerunning them. Every
finding below was manually re-verified against the actual codebase/data before
being included — several of the scripts' own raw hits turned out to be false
positives from the audit tooling itself (noted where relevant) and were dropped
or downgraded rather than reported at face value.

## CRITICAL

### 1. News-digest date leakage: 12 combos have source articles 62–365 days after report_date
The News layer's entire premise is that every source article predates
`report_date` (CLAUDE.md > Architecture > News; this is the exact bug class an
earlier version had and was supposedly fixed). `check_news_leakage.py` found 47
combos with at least one source-article date on/after `report_date`, but 35 of
those are only 1–3 days after (almost certainly a publish-date/timezone
rounding artifact for a same-day after-hours release, not real leakage — see
Note below). The other **12 have gaps of 2 months to a full year** and look
like genuine leakage or quarter mislabeling:

| document_id | report_date | leaked source date | gap |
|---|---|---|---|
| `p2_lenovo/LNVGY_FQ2_2026` | 2025-01-30 | 2026-01-30 | 365d |
| `p2_starbucks/SBUX_FQ3_2025` | 2025-07-29 | 2026-07-28 | 364d |
| `p2_nike/NKE_FQ3_2025` | 2025-03-20 | 2025-09-30 | 194d |
| `p2_nike/NKE_FQ2_2025` | 2024-12-19 | 2025-06-26 | 189d |
| `p2_unitedhealth/UNH_FQ4_2025` | 2026-01-26 | 2026-07-31 | 186d |
| `p2_nike/NKE_FQ1_2025` | 2024-10-01 | 2025-03-20 | 170d |
| `p2_disney/DIS_FQ3_2025` | 2025-08-05 | 2025-11-13 | 100d |
| `p2_nvidia/NVDA_FQ4_2025` | 2025-11-19 | 2026-02-25 | 98d |
| `p2_nvidia/NVDA_FQ2_2025` | 2025-05-28 | 2025-08-27 | 91d |
| `p2_nvidia/NVDA_FQ1_2025` | 2025-02-26 | 2025-05-28 | 91d |
| `p2_nvidia/NVDA_FQ3_2025` | 2025-08-27 | 2025-11-19 | 84d |
| `p2_general_mills/GIS_FQ3_2026` | 2026-03-18 | 2026-06-05 | 79d |
| `p2_workday/WDAY_FQ2_2025` | 2025-08-21 | 2025-10-31 | 71d |
| `p2_dell/DELL_FQ4_2025` | 2026-02-26 | 2026-04-29 | 62d |

**Nvidia is the standout: all 4 of its scored quarters leak, each by almost
exactly one quarter (84–98 days).** That pattern — not random noise, a
consistent ~1-quarter offset — is the same failure signature as the
already-documented NFLX transcript mislabeling bug (CLAUDE.md > Known bugs
fixed: "NFLX_FQ1_2025/FQ2_2025's transcript documents actually contained the
FQ3/FQ4 2025 calls"). Strong suspicion: `docs/news/p2_nvidia/NVDA_FQ*.txt`
digests are quarter-shifted the same way. Nike's 3 quarters show the same
~170–194 day pattern (closer to 2 quarters). Starbucks and Lenovo look like a
plain year-typo (day/month match, year off by one) rather than a quarter
shift. **Recommend: manually re-read these 12 digest files against their
stated report_date before trusting their news-layer score; the news layer's
sentiment for these 12 combos may currently be scoring the wrong quarter's
market expectations, or reading genuine post-earnings reaction language.**

*Note on the other 35 (1–3 day) hits:* almost certainly not real leakage —
most report_dates are the earnings-call date itself, and financial-media
recap/analysis pieces published the next calendar day (or the next day in a
different timezone) is normal and doesn't necessarily contain reaction
language. Not worth digest rewrites without more evidence, but the checker's
same-day tolerance could be widened to ±1–2 days in a future version to cut
this noise.

## HIGH

### 2. `outputs/global/summary/backtest_equity_phase2.csv` is a stale, orphaned artifact — not the current N=268 backtest
This file exists, is named to match the "_phase2" canonical-output convention
CLAUDE.md documents for `global_outcome_calibration_phase2.csv`, and would be
the obvious file to reach for — but it's stale: 39 distinct tickers, last row
dated 2026-07-13, file mtime **2026-07-30** (over a week before the Task 9
rerun). `backtest.py`'s actual default output path
(`EQUITY_CSV = OUTPUTS_DIR/"global"/"summary"/"backtest_equity.csv"`,
[backtest.py:46](backtest.py:46)) has **no** `_phase2` suffix — so the
documented Task 9 command (`python backtest.py --calibration-csv
outputs/global/summary/global_outcome_calibration_phase2.csv`, no
`--equity-csv` override) correctly wrote the current N=268 results (71
tickers, 804 rows, mtime 2026-08-09 11:48:04, one minute before the Task 9
commit) to the **unsuffixed** `backtest_equity.csv`. The `_phase2`-suffixed
file is a leftover from some earlier one-off run with an explicit
`--equity-csv` override and nobody has been updating it since.
**Recommend: delete `backtest_equity_phase2.csv` (or clearly mark it
superseded) so nobody — human or future Claude session — grabs it by the
naming convention and reports stale (pre-gap-onboarding) P&L numbers.**

### 3. 3 issuers in the canonical roster (`PHASE2_ISSUERS`) have no manifest — silent coverage gap + a crash landmine
`blend.py`, `llm_news.py`, and `quant_layer.py` all list `colgate_palmolive`,
`costco`, and `hermes` in their `PHASE2_ISSUERS` array (kept in sync per
CLAUDE.md's own "Known bugs fixed" note), but none of the three has a
`manifests/p2_*_reports.json`:
- **`colgate_palmolive`**: `docs/colgate_palmolive/` has 4 quarters of already-sourced press releases (CY2025-Q3 through CY2026-Q2) sitting unused — never built into a manifest, never scored.
- **`costco`**: same — `docs/costco/` has 3 quarters (CY2025-Q4 through CY2026-Q2) sourced and unused.
- **`hermes`**: no `docs/` folder at all — never actually onboarded, just a roster entry.

Beyond the missing coverage: `blend.py`'s and `llm_news.py`'s `__main__`
(bare invocation, no issuer args — `python llm_news.py` is literally the
documented "score all phase2 pre-fetched news digests" command in CLAUDE.md)
and `quant_layer.py`'s `__main__` all loop `for issuer in sys.argv[1:] or
default_issuers` and call `load_manifest(MANIFESTS[issuer])` directly with no
try/except. Hitting `colgate_palmolive` (or the other two) throws
`FileNotFoundError` and **kills the whole run, silently skipping every issuer
listed after it in the array** (roughly 30 issuers, alphabetically from
`comcast_corporation` onward). This didn't bite the actual Task 8/9 runs
because `run_gap_pipeline.py` always passes explicit `p2_<slug>` args, never
invokes bare — but it's a live landmine for the next bare rerun (e.g. if a new
FOMC minutes or news digest needs picking up later and someone runs the
documented bare command). **Recommend: either build manifests for
colgate_palmolive/costco (docs are already there) and drop hermes from the
roster, or wrap the bare-loop body in try/except so one missing manifest
doesn't kill the batch.**

### 4. 33 of 203 human-priced combos don't validate against `fix_report_dates_from_human_prices.py`'s cross-check
`check_report_dates.py` reran that script's logic read-only (no write) and
found 33 combos (of 268 currently-scored, all with human price data on file)
where no trading day matches the human-typed (Prior Close, Next Day Open)
pair within 2¢ tolerance — full list persisted to
[phase2/audit/report_date_audit.json](report_date_audit.json). This doesn't
by itself prove `report_date` is wrong (the human rater could have mistyped a
price, or a dividend/split could shift the raw-price match) — but it's 33,
not the "22 unresolvable" CLAUDE.md documents, and none of the current 22 vs
33 overlap has been reconciled. 4 of these (`CL_2025_Q3/Q4`, `CL_2026_Q1/Q2`
— Colgate-Palmolive) tie directly back to Finding #3's missing manifest.
**Recommend: manually spot-check a handful (start with the ones with the
largest price mismatch) against the actual earnings-date calendar.**

5 further combos are *ambiguous* (multiple trading days match): `BAC_2025_Q2`,
`F_2025_Q2`, `LNVGY_2026_Q2`, `PUM.DE_2026_Q1`, `V_2025_Q3` — each currently
resolved by "nearest to the existing estimate," unreviewed.

## MEDIUM

### 5. `blend.py`'s `blend_document()`/`blend_issuer()` still default to the ±0.15 threshold trap
[blend.py:110](blend.py:110) defaults `hold_upper=0.15, hold_lower=-0.15` —
the exact stale-threshold trap CLAUDE.md says was fixed in `export_rows.py`,
still present in `blend.py`'s own function. **Confirmed not currently
consumed by anything that persists to disk**: `eval/run_eval.py` recomputes
signals independently via `eval.calibrate.derive_signal` +
`DEFAULT_HOLD_UPPER/LOWER` (0.25/-0.05, verified correct — see Clean below),
and `run_gap_pipeline.py`'s `python blend.py <issuer>` subprocess call is only
for its side effect of populating `outputs/*/results/` caches, its stdout is
never parsed. No production numbers are affected today, but it's a landmine
for the next person who imports `blend_document()`/`blend_issuer()` directly
expecting canonical thresholds.

### 6. 2 undocumented news-digest gaps beyond the ones CLAUDE.md lists
CLAUDE.md's "Known gaps" names exactly 2 no-digest exceptions (Maersk
Q1/Q4 2025, Netflix Q4 2024) — `check_coverage_reconciliation.py` confirms
the Maersk two, but also found **`p2_boeing/BA_FQ4_2025`** and
**`p2_kraft_heinz/KHC_FQ1_2026`** scored on the micro layer with no matching
news score, neither mentioned anywhere. Either source digests for these two
or add them to the documented exception list.

## Clean / verified correct (no action needed)

- **`check_manifest_docs.py`**: all 627 document references across all 71
  phase2 manifests exist on disk, none are 0 bytes, and no two combos share
  byte-identical document content. No missing/duplicated source files.
- **`check_blend_consistency.py`**: `blend.DEFAULT_WEIGHTS` = `(0.55, 0.45,
  0.0, 0.0)` and `eval.calibrate.DEFAULT_HOLD_UPPER/LOWER` = `(0.25, -0.05)`
  both match what CLAUDE.md documents. Recomputing 30 randomly sampled rows of
  `global_outcome_calibration_phase2.csv` from raw layer scores against these
  values reproduced the CSV's `blend_predicted_signal_default` column exactly
  (0 mismatches) — the calibration CSV genuinely reflects the current default
  weighting, contrary to CLAUDE.md's caveat that it "still reflects the OLD
  weights... until rerun" (that caveat is itself now stale; Task 9's rerun did
  regenerate it, mtime 2026-08-09 11:47, 71 seconds before the Task 9 commit).
- **`check_gap_sourcing.py`** (the fabrication smell-test, the thing this audit
  was originally most worried about): checked all 301 documents across the
  130 gap-onboarding combos. **No document failed both the company-name check
  and the ticker check** — i.e. nothing looks like completely unrelated
  content. 222 "flagged" hits are almost entirely explained by
  `extract_doc_text()`'s "Earnings Call" keyword check firing on Press
  Releases and Earnings Presentations (a check meant for transcripts, not
  doc-type-aware) — expected, not a fabrication signal. The genuinely
  fabrication-relevant subagent placeholder problem that Task 6's plan notes
  describe appears to have been caught before the final manifests were built.
  Only mild residual interest: `p2_spotify/SPOT_2025_Q2` and `SPOT_2025_Q3`
  press releases are unusually short (3043/3442 chars) — worth a 30-second
  human glance, not alarming.
- **`check_artifact_freshness.py`** cost-ledger reconciliation: no duplicate
  micro-layer cost rows found (i.e. no evidence any document was actually
  re-billed by `run_reports.py`'s lack of caching, despite that being a real
  structural risk self-documented in `run_gap_pipeline.py`'s own comments).
  6 minor `cost-ledger-gap` entries (Hilton x2, JPM x4) where a scored result
  has no ledger row — harmless, just means `build_cost_ledger.py` hasn't been
  rerun since those were scored; rerun it to refresh.

## False positives from the audit tooling itself (reported for transparency, not action items)
- `check_coverage_reconciliation.py`'s gap-combo cross-check initially
  flagged 12 combos (Allianz, Puma, Siemens, Standard Chartered — all
  dotted European tickers) as "not scored." This was the audit script's own
  bug: it stripped `.DE`/`.L` suffixes before matching but the pipeline's
  actual `document_id`s keep the suffix (e.g. `ALV.DE_FQ1_2025`, not
  `ALV_FQ1_2025`). Manually verified all 12 have real scored results on disk
  — not a pipeline bug, just a bad string match in this checker.
- `check_artifact_freshness.py`'s mtime-vs-commit staleness check flagged
  `global_outcome_calibration_phase2.csv` as stale using too tight a
  tolerance (60s) against commit time — the file's actual mtime is 71 seconds
  before the Task 9 commit, i.e. genuinely fresh (see Clean section above).
  The *other* half of that same finding, about `backtest_equity_phase2.csv`,
  turned out to be real (Finding #2) once checked against what commit
  `666d786` actually touched — worth keeping the check, just fix its
  threshold/reference point if reused.
