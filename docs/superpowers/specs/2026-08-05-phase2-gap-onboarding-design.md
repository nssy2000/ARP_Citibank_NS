# Phase2 human/LLM gap onboarding — token-efficient sourcing design

**Date:** 2026-08-05
**Status:** Approved, ready for implementation plan

## Problem

The live "Human vs LLM" sheet (`Master_Data_NEW.ods`) has 325 non-empty human prediction rows (286 unique ticker/year/quarter combos) against only 162 LLM-scored rows (162 unique combos). The gap is 138 combos.

This gap is not just "a few more quarters on issuers we already track" — the pattern that previously burned through tokens fast even at ~20 quarters. Of the 138 gap combos, only ~20 are new quarters on the 41 tickers phase2 already covers. The remaining ~118 combos span **39 entirely new tickers**, including 9 international names with thin or no SEC/EDGAR footprint (ALV.DE, PUM.DE, SIE.DE, STAN.L, RMSP.XC, HEINY, LNVGY, NSRGY, SONY). Each new ticker needs a manifest built from scratch plus sourced documents for the micro layer (press release, presentation, transcript) and the news layer (pre-earnings expectations digest) — before any scoring can happen.

We are not settled on the final micro/macro/news/quant blend weighting (see CLAUDE.md's Known gaps), so all 4 layers should be sourced/scored for each gap combo, not just micro+news, to keep future weight-sweep experiments valid across the full N.

Past attempts at this (filling ~20 quarters, micro+news only) exhausted the session's token budget quickly. Root cause: document discovery (web search, page fetches, PDF/transcript reads) was done inline in the main conversation, so every fetched page's raw bytes landed in the orchestrating context. The fix is architectural: move discovery/download work out of the main context entirely.

## Scope

**All 138 gap combos, all 39 new tickers, in one onboarding effort** (including the 9 international names) — user chose the full pass over deferring international/thin-coverage tickers, to close the human/LLM gap completely rather than leave a known residual.

## Layer cost profile (why the plan treats layers differently)

- **Quant** (`quant_layer.py`) — pure yfinance arithmetic, zero LLM cost, zero sourcing. Runs directly once a report_date is known. Never earns blend weight either way.
- **Macro** (`llm_macro.py`) — one LLM score per FOMC meeting, cached and reused across every company/quarter after that meeting. No new sourcing needed for a new ticker; only needs its report_date to fall correctly relative to existing cached meeting scores.
- **Micro** (`report_pipeline.py` / `run_reports.py`) — needs sourced documents (press release + presentation + transcript) per quarter, bundled into one DeepSeek API call. Document *discovery* is the expensive part; the scoring call itself is a DeepSeek API cost, not a Claude Code session token cost.
- **News** (`llm_news.py`) — needs a pre-earnings market-expectations digest per quarter, sourced from free outlets, every article dated strictly before `report_date`. Same discovery-is-expensive profile as micro.

So the token-sensitive work is document *discovery and download* for micro + news, specifically. Quant and macro are non-issues once report_date is resolved.

## Architecture

### 1. Gap inventory (`phase2/gap_report.py`, new)

Parses `Master_Data_NEW.ods` (via the documented `lxml.etree.fromstring(..., recover=True, huge_tree=True)` approach on raw `content.xml` — pandas/odfpy fail on this file) and diffs `Human_Data_Entry` against `LLM_Data_Entry` on `(ticker, year, quarter)`.

Output: `phase2/gap_combos.json`, one entry per gap combo:

```json
{
  "ticker": "AVGO",
  "company": "Broadcom",
  "year": "2025",
  "quarter": "Q3",
  "status": "not_started",
  "report_date": null,
  "is_sec_registrant": null,
  "notes": ""
}
```

`status` is the resumability checkpoint: `not_started → report_date_resolved → manifest_built → micro_sourced → news_sourced → quant_done → macro_done → scored → blended`. Every later stage reads and updates this file. Re-running `gap_report.py` is free (no LLM/API calls) and safe to do any time — it only refreshes the diff, it doesn't clobber progress on combos already in flight (matches on ticker/year/quarter, preserves existing status).

### 2. Report-date resolution

Reuse `resolve_report_dates.py` + `fix_report_dates_from_human_prices.py` unchanged — cross-validate against the human sheet's own typed Prior Close / Next Day Open pair using raw (non-adjusted) price history, per the two known failure modes already documented in CLAUDE.md (positional nearest-date drift, adjusted-price mismatch). Apply the existing `FYE_BASE_YEAR_OFFSET` override table for fiscal-year-offset tickers where relevant.

Populates `report_date` and advances `status` to `report_date_resolved` in `gap_combos.json`.

### 3. Quant + macro — run directly, no agent dispatch

For every combo with a resolved `report_date`: run `quant_layer.py` and `llm_macro.py` directly (existing bare CLI, no new code). No sourcing step exists for these two layers. Advances `status` through `quant_done`/`macro_done`.

International tickers with poor yfinance coverage: if `quant_layer.py` can't resolve a symbol, log and leave that combo's quant sub-score as the existing missing-data handling (does not block micro/news/macro scoring or blending).

### 4. Micro + news sourcing — the token-sensitive stage

Two-tier discovery, applied per combo:

**Tier 1 — scripted, deterministic, zero LLM tokens.** Extend `build_manifests.py`/`triage_docs.py`'s existing pattern with an EDGAR full-text-search API + company IR RSS lookup for SEC-registered US tickers only (~30 of the 39 new tickers). Produces candidate URLs for press release/presentation/transcript and pre-earnings news items. Writes directly into the manifest and `docs/<issuer>/CY<FY>-Q<FQ>/` on a confident match.

**Tier 2 — background subagent, isolated context.** Used for: anything Tier 1 couldn't confidently resolve, and all 9 international tickers unconditionally (no EDGAR footprint). Dispatched as `Agent` calls (general-purpose, web-enabled, cheap/fast model since this is discovery work not deep reasoning), run in the background, batched in waves of ~5-8 tickers in parallel. Each agent call is self-contained: given a ticker, company name, and list of (year, quarter, report_date) combos, it searches, downloads, and writes source documents into `docs/<issuer>/CY<FY>-Q<FQ>/` following the existing filename/folder convention, updates the manifest, and returns **only a short receipt** (files written, doc count per combo, any combos it couldn't resolve) — never raw page/PDF content — back to the orchestrating session. This is the specific fix for the prior token-burn failure mode: raw fetched bytes now stay inside the subagent's isolated context instead of the main conversation's.

After each wave completes, `gap_combos.json` is checkpointed (`micro_sourced`/`news_sourced`) so a stop mid-run (budget, time, interruption) loses nothing — the next session's wave dispatch just filters on `status`.

News-sourcing carries the existing hard rule forward unchanged: every source article dated strictly before `report_date` (the documented leakage bug this project already fixed once).

### 5. Score

For every combo with `micro_sourced`/`news_sourced` status: run `run_reports.py` (micro) and `llm_news.py` (news) as-is. These are DeepSeek API calls, not Claude Code session tokens — this stage was never the bottleneck and can run in bulk without special batching.

### 6. Blend + eval

Once a ticker's combos are fully scored across all 4 layers: `blend.py <issuer>` per new issuer. Once all 138 gap combos are scored: rerun `eval.run_eval --output-suffix phase2` and `backtest.py` (already an outstanding item independent of this gap-fill, per CLAUDE.md's Blend section — this work should land after, not instead of, that rerun).

## Out of scope

- `Company_List` tab in `Master_Data_NEW.ods` doesn't list the 39 new tickers yet, so its `Ticker` `XLOOKUP` will blank for them. This is a sheet-owner fix (already flagged in CLAUDE.md's Known gaps), not something this pipeline touches — sheet edits stay manual/paste-ready per the project's existing "never drive the live sheet" rule.
- Settling on a validated blend weighting (separate outstanding item, also in CLAUDE.md's Known gaps).
- The 22 phase2 combos with unresolvable report_dates and other pre-existing thin-coverage gaps documented in CLAUDE.md — unrelated to this human/LLM gap-fill, not addressed here.

## Guardrails

- Main/orchestrating session never reads sourced document content directly — only file paths, doc counts, and status from subagent receipts and `gap_combos.json`.
- Wave size capped (~5-8 tickers) so a single dispatch batch stays bounded and checkpointed progress is fine-grained.
- Tier 1 (scripted EDGAR/IR lookup) is tried before Tier 2 (agent dispatch) wherever it can apply, to minimize the number of tickers that need open-ended agent web search at all.
- `gap_combos.json` is the single resumability source of truth — safe to stop and resume this effort across multiple sessions without re-deriving state.
