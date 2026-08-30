# Model Arm State — 2026-08-11

## What was built today

### Item A: Multi-horizon return matrix
`eval/return_matrix.py` → `outputs/global/summary/returns_matrix.csv` (268 events,
5 horizons: overnight/1d/3d/5d/10d, raw + SPY excess). Per-ticker copies in
`returns_matrix_by_ticker/`. Implied HOLD bands in `implied_hold_bands.csv`. Holiday
assertion passes all 268 events. Zero NaN.

### Task 1: Worksheet leakage triage
25 of 268 events (9.3%) confirmed contaminated — human-rater sentiment worksheets
(scores, signals, realised returns) fed verbatim to the LLM via `build_bundle_text()`.
Look-ahead component (realised returns in input) is the more severe concern.
Agreement rate on the 25 worksheet events: 18/25 = 72%, significantly above chance
(p=0.0013). Clean-group comparison pending human data export.
Files: `worksheet_leak_flags.csv`, `worksheet_leak_triage.md`.

### Task 2: Cross-company attribution sweep
1 confirmed misattribution (SPOT_FQ1_2026 = Parker-Hannifin in Spotify slot).
26 low-mention false positives from conservative name matching.
File: `company_attribution_check.csv`.

### Tasks 3–4: Amended section boundaries + revised achievable N
Strict Q&A transition precedence (FactSet header > transition phrase, no
`[Operator Instructions]` fallback). Proportional split check (prepared remarks
≥ 10% of transcript) catches 53 partial truncations. 100-word absolute floor kept
as belt-and-braces. Known recoverable losses documented (WDAY boilerplate x3,
NFLX/InsiderMonkey formatting x6).

Four-arm N = 124 (after proportional check + exclusions).
Two-arm N = 210 (full bundle vs PR only).
Files: `section_availability_audit_amended.csv`, `revised_achievable_n.md`.

### Compounded total return finding
`backtest.simulate()` compounds via `eq *= (1+net)` (line 122). The +1243.64%
headline is order-dependent and not an achievable balance because positions overlap
across same-week reporters. Mean net per trade with a `bootstrap_trade_stats`
interval is the correct headline P&L metric. Compounded figures appear in CLAUDE.md,
`execution_cost_grid.py`, `ext9_cost_grid.csv`, `ext4_conviction_sizing.csv`,
`leave_one_out_robustness*.csv`. `phase2_equity_curve_FIXED.csv` is a stale orphan
with the same construction plus a corrupted AMKBY date. No outputs changed yet —
pending editorial pass.

### Timing field plumbing
`release_timing` field added to all 73 manifests. `fetch_prices`,
`eval/outcomes.py`, and `eval/return_matrix.py` accept `release_timing` parameter.
`pre_market` shifts entry to prior-session close. `intraday` and `unknown` raise
(force exclusion). `None` raises (pipeline refuses to run without classification).
`PRE_MARKET_ISSUERS` deprecated.

### Release timing map (EDGAR)
Populated from EDGAR 8-K Item 2.02 acceptance timestamps, cross-verified against
public earnings calendars:

| Value | Count |
|---|---|
| `pre_market` | 30 |
| `after_hours` | 34 |
| `null` (non-US, pending) | 9 |

**Nine unresolved non-US issuers** (no EDGAR filing):
ALV.DE, BCS, LNVGY, MC.PA, AMKBY, NVO, PUM.DE, SIE.DE, STAN.L.
Left null — user hand-sourcing from home-exchange announcements.

**LMT** — set back to null. All 4 events had 8-K acceptance times of 11:31–12:25
ET (mid-session). Classification as pre_market was based on "public calendars"
without naming the source. Unresolved pending manual verification of actual press
release timestamp.

**JPM** — confirmed pre_market. EDGAR + public calendars consistent. Price
cross-check agrees (open_gap > overnight on both sampled events).

**Zero timing-changed issuers** — no issuer's events disagree.

### Price cross-check finding
31/58 sampled pre_market events show |open_gap| > |overnight| (53% agreement).
The disagreements reveal that `report_date` is inconsistently defined across
manifests — set to the eve of earnings for some issuers (CAT, CMCSA, GS, LLY,
UNH, WMT, JNJ) and the morning of for others (BAC, BA, KO, CVS, TGT, SPOT).
For "eve" events, the current close→next-open convention already captures the
reaction correctly. The anchor fix must use a factual `release_date` from the 8-K
filing date, not per-event price-based classification.

## Blockers

- **Task 5 (section ablation)**: script built (`experiments/section_ablation.py`),
  blocked on valid `DEEPSEEK_API_KEY` in `.env` (current key expired, 401 error).
  Four-arm N=124, two-arm N=210, estimated ~668 API calls.
- **Anchor correction**: pending `release_date` field per event (from 8-K filing
  date), uniform rule per timing value. 9 non-US issuers + LMT unresolved.
- **Worksheet leak decision**: 25 events pending user decision on re-score vs exclude.
- **Human agreement data**: pending `human_data_entry_export.csv` for clean-group
  agreement rate.

## Not started
- Item B (holding-period curve) — blocked on Item A being finalised post-anchor.
- Item D (FinBERT baseline) — independent, not started.
- Item E (walk-forward validation) — last, user go-ahead required.
