# Model Arm Gap Spec, remaining items only

## Context

This is the follow-on spec for the model arm of the Citibank Applied Research Project, deadline 1 September 2026. The first spec (8 items, dated 5 August) has been mostly delivered, and `CLAUDE.md` in this repo documents that work under "Model-arm robustness spec (Nigel, 2026-08-05), Tier 1 + Tier 2 deliverables". Read that section before starting anything, because it records locked decisions, corrected figures and known traps that this spec inherits. Five pieces remain, the multi-horizon return matrix, the holding-period curve, the full section ablation, the FinBERT baseline, and the full walk-forward build. Everything else on the original list is done and must not be rebuilt. This file is self-contained, work through it item by item, and where it conflicts with the original 5 August spec, this file and the repo win.

## Repo truth, which overrides the original spec

The original spec was written against stale references. The following are the corrected facts, all verifiable in this repo.

- The dataset is the phase2 track, N=268 events, in `outputs/global/summary/global_outcome_calibration_phase2.csv` (269 lines including header). The original spec said 120 events, that number is dead.
- Deployed blend weights are `blend.DEFAULT_WEIGHTS = (0.55, 0.45, 0.0, 0.0)` for micro, macro, news, quant, promoted 2026-08-05. HOLD thresholds on the blended score are `hold_upper = +0.25`, `hold_lower = -0.05`.
- Two horizon conventions coexist and must never be conflated, per `outputs/global/summary/ext1_freeze_note.md`. P&L and backtest figures use the overnight gap, close of `report_date` to next session open, via `backtest.py`. Calibration and accuracy figures use the 5-day close-to-close window via `eval/outcomes.py` with `window_trading_days=5, exit_on_open=False`.
- The measured break-even round-trip cost is 162.81 bps (`experiments/execution_cost_grid.py`). The original spec's "roughly 113 bps, already computed" could not be verified anywhere and is retired.
- The macro finding is a null with the citable curve in `macro_weight_curve.png` and the paired bootstrap in `macro_ablation_summary.json`. The old "0.466 to 0.443" figure is unverifiable, do not quote it.
- The model's self-reported training cutoff is October 2023, and the recall probe returned 30 of 30 refusals (`recall_probe_log.csv`). Only 2 of 268 events predate the cutoff, so the pre versus post split is degenerate and is reported for completeness only.
- The master workbook is `Master_Data_NEW.ods` and lives outside this repo. Human-arm data arrives via sheet exports, not via any file here.
- The cost assumption is `cost_bps = 10.0` round-trip, `short_borrow_bps = 0.0`, the `backtest.simulate()` defaults, recorded in the freeze note.
- The stable project path on the owner's machine is `C:\Users\bencr\Documents\Citibank APR`. Never use the OneDrive alias path, it hangs.

## Already done, do not rebuild

`bootstrap_stats.py` (all four variants), `experiments/leave_one_out_robustness.py`, `experiments/quote_verification_screen.py`, `experiments/asymmetry_conviction_analysis.py`, `experiments/macro_weight_axis_sweep.py`, `experiments/macro_ablation_analysis.py`, `experiments/execution_cost_grid.py`, `experiments/lm_baseline.py`, `experiments/contamination_audit.py`, `experiments/extension4_conviction_sizing.py`, and `outputs/global/summary/ext1_freeze_note.md`. Their outputs sit in `outputs/global/summary/`. If an item below needs one of these, import or read it, never reimplement it.

## Out of scope, gated on people not code

The human-line halves of Extensions 2, 4, 9 and 1, and the comparative half of the section ablation write-up, all wait on the human arm's reading sessions. Do not attempt them. Build everything below so a human score column can be swapped in later with no code change beyond the column name.

## Practical requirements

- Run from the repo root. Item C needs `DEEPSEEK_API_KEY` in the environment or `.env`, nothing else makes API calls. Item D needs `torch` and `transformers` installed and one HuggingFace model download, no API key.
- Never overwrite an existing file in `outputs/global/summary/`. New outputs get new names.
- Every new output CSV carries a `run_id` or timestamp column, matching the project convention.
- Commit after each item lands, one item per commit, so a failed item never takes a finished one down with it.

---

## Item A. Multi-horizon return matrix

**Runs without Human Arm Results,** and the finished per-ticker copies are owed to the human arm as a read-only reference.

**Main topic.** One cached CSV of returns at every horizon per event, which Item B and later human-line reruns read instead of touching prices themselves.

**What it does and the goal.** `eval/outcomes.py` returns one number per call at one window. Item B needs overnight, 3, 5 and 10 day returns for all 268 events, raw and excess over SPY, and calling yfinance per horizon per event is slow and produces subtly different numbers wherever a detail differs. Build the matrix once, apply the entry convention in exactly one place, and cache it. Half a day.

**Inputs.** `outputs/global/summary/global_outcome_calibration_phase2.csv` for the event list (`document_id`, `ticker`, `report_date`), `eval/outcomes.py` and `export_sheet_rows.fetch_prices` as the existing price conventions to match, yfinance with `auto_adjust=False`.

**Steps.**

1. Create `eval/return_matrix.py`. Take the 268 events from the phase2 calibration CSV, not from manifests, so the matrix covers exactly the scored universe.
2. For each event, pull one price history per ticker spanning `report_date` minus 5 sessions to plus 25 sessions, `auto_adjust=False`. Step in trading days using the returned history index itself, not calendar days, so holidays cannot silently stretch a window. Do not add new calendar dependencies, the repo resolves trading days through the yfinance index everywhere else.
3. Entry is the close of `report_date`, matching `backtest.py` and `export_sheet_rows.fetch_prices`. Compute `ret_overnight` as that close to the next session's open, exactly the sheet convention. Compute `ret_1d`, `ret_3d`, `ret_5d`, `ret_10d` as that same entry close to the close of the 1st, 3rd, 5th and 10th sessions after entry. Fixing entry at the same close for every horizon is what makes Item B's curve a family of alternative exits on one trade. The drift from the open is recoverable as any horizon return minus the overnight return, so the two stay separable without extra columns.
4. Pull SPY over the same range once and add an excess column per horizon, the stock's return minus SPY's over the identical window.
5. Derive the implied HOLD band at each horizon. The overnight band is plus or minus 2 percent, the group sheet's `Settings!B3` convention. At 1, 3, 5 and 10 days set the band so the share of events whose absolute return falls inside it matches the overnight share, and record the implied band in percent per horizon. This is distinct from `eval/outcomes.py`'s plus or minus 3 percent 5-day outcome thresholds, both exist for different purposes, do not merge them.
6. Events too recent for a full window, GS_FQ2_2026 already lacked a 5-day outcome, get NaN at the missing horizons and a row in a short exceptions log, never a shortened window quietly.
7. Cache to `outputs/global/summary/returns_matrix.csv` with columns `document_id`, `ticker`, `report_date`, `entry_date`, `entry_close`, the five raw returns, the five excess returns, and a `run_id`. Write per-ticker filtered copies to `outputs/global/summary/returns_matrix_by_ticker/` for the human arm, and `implied_hold_bands.csv` beside them.

**Outputs.** `returns_matrix.csv`, `returns_matrix_by_ticker/*.csv`, `implied_hold_bands.csv`, and an exceptions log for incomplete windows.

**Acceptance checks.**

- The matrix's `ret_overnight` reproduces the calibration pipeline's overnight numbers on a spot-checked handful of events, and the matrix's `ret_5d` close-to-close reproduces `forward_return` from the phase2 calibration CSV on events where `window_trading_days` is 5, within float tolerance. If either diverges, the entry convention drifted, stop and fix before anything reads the file.
- Two events verified by hand against a price chart, one pre-market reporter and one after-hours reporter, confirming the entry date resolved differently. Print the two worked examples so a person can eyeball them.
- Exactly one row per calibration event, and every NaN horizon appears in the exceptions log.

**What to expect.** Infrastructure, not a hypothesis. A handful of mid-2026 events will lack the 10-day horizon, which is fine and logged.

---

## Item B. Extension 2, holding-period curve, model line

**Requires Human Arm Results for the second line only. The model line runs now and is the build.**

**Main topic.** Mean net return per trade against holding period, testing whether the overnight window choice made the result.

**What it does and the goal.** The overnight window was chosen early and reported ever since, so somebody will ask whether the choice drove the finding, and if the signal keeps paying over days the claim upgrades to post-earnings drift. One figure, one line now, the human line drops in when their scores land. One day, after Item A.

**Inputs.** `returns_matrix.csv` from Item A, the phase2 calibration CSV for the deployed signal per event (`blend_predicted_signal_default` column, already cross-checked in earlier work against `blend.blend_scores` with `DEFAULT_WEIGHTS`), the blended score recomputed via `blend.blend_scores(..., DEFAULT_WEIGHTS)` for the rank correlations, `bootstrap_stats.bootstrap_trade_stats` for intervals, `cost_bps = 10.0` from the freeze note.

**Steps.**

1. For each traded event, BUY or SELL only, take the return at each horizon from the matrix, sign it by the signal, and subtract the 10 bps round trip once regardless of holding period, because entry and exit happen once per trade. Follow `backtest.simulate`'s existing SELL convention, and keep `short_borrow_bps = 0.0` as frozen.
2. Average within each horizon, never compound across horizons, they are alternative versions of the same trade. Positions overlap at longer horizons since several companies report in the same fortnight, so if any total appears state plainly it is a sum of independent per-trade returns, not an achievable account balance.
3. Report accuracy per horizon as well, grading the signal against the realised return bucketed by that horizon's implied HOLD band from `implied_hold_bands.csv`. The trap is using the flat 2 percent band at 10 days, which empties the HOLD class and inflates accuracy for reasons unrelated to skill.
4. Add Spearman rank correlation per horizon between the blended score and the raw return, which needs no band and defends the whole curve against objections to the band convention. If the curve has the same shape in both metrics, the band was not driving it.
5. Put a `bootstrap_trade_stats` interval on every mean-net-per-trade point, and offer the clustered-by-week interval as the honest alternative since same-week reporters share a market factor.
6. Take one quarter all the way through by hand and print it, the overnight gap, the position by day 3, day 5, day 10, so the write-up has one concrete worked example.
7. Structure the plotting code to accept a second signal column, so the human line is a rerun not a rewrite.

**Outputs.** `ext2_holding_curve.csv` with per-horizon mean net per trade, accuracy, rank correlation and intervals, `ext2_holding_curve.png`, and the printed worked example.

**Acceptance checks.**

- The overnight point on the curve reconciles with `backtest.simulate`'s existing overnight mean-per-trade at the same cost on the same trade set.
- No compounding anywhere, verified by the absence of any cumulative product across horizons in the code.
- Rank correlation is computed on all 268 events, not just traded ones, since it needs no trade at all, and the accuracy figures state their per-horizon band.

**What to expect.** Either shape is a finding. Decay after overnight says the window choice was right, persistence says drift, and wide intervals crossing zero at long horizons are expected at this sample size and get said plainly.

---

## Item C. Section ablation, full build

**Runs without Human Arm Results.** The human arm's information-set version is a separate experiment, only the comparative write-up needs both.

**Main topic.** Which part of an earnings document carries the signal, measured as accuracy against tokens per section.

**What it does and the goal.** Each qualifying event is scored five ways, press release only, prepared remarks only, guidance passage only, questions and answers only, and the full bundle, to locate the signal relative to token cost. If the press release alone carries most of it, document gathering for any future expansion drops severalfold. This is the most expensive remaining item, roughly 750 or more new API calls plus splitting effort, which is why the availability audit gates it.

**Inputs.** Source documents under `docs/<slug>/` and the cached extracted text under `outputs/p2_<slug>/extracted/*.txt`, the manifests in `manifests/p2_*_reports.json`, `report_pipeline.py` for extraction and `call_llm`, the prompt in `prompts/`, the overnight ground truth from Item A's matrix, `DEEPSEEK_API_KEY`.

**Steps.**

1. Availability audit first, and it gates everything downstream. For each of the 268 events, inspect the cached extracted text and classify whether the four components are separately identifiable, press release, prepared remarks, guidance passage, questions and answers. Many events hold a single transcript file or a press release only, so the achieved five-arm sample is unknown until this runs. Write `section_availability_audit.csv` with one row per event and a status per component, and state the achieved N before promising anything.
2. Write the four section boundary definitions, one sentence each, into the header block of the audit script and echo them into the audit CSV's metadata, before any splitting. Flag them in the console output for Nigel and the pipeline owner to confirm. Do not adjust a boundary after runs begin.
3. Split each qualifying document's extracted text into four section files under `outputs/p2_<slug>/sections/<document_id>/`. Regex on headings where transcripts are consistent, and where they are not, mark the event `manual` in the audit rather than guessing a boundary, since a wrong split silently contaminates two arms at once.
4. Run five independent `call_llm` calls per qualifying event through the existing prompt and schema, one per section plus the full bundle, logging prediction, tokens and cost per arm with a `run_id`, into a new output tree, never into the production `outputs/p2_<slug>/results/` files.
5. Grade all five arms against the same overnight move and the same plus or minus 2 percent band from the matrix, so nothing differs between arms except the prompt contents. Report the 5-day grading as a secondary table for comparability with the deployed accuracy figures, since grading is free once predictions exist.
6. Include only events where all five arms exist. Comparing arms drawn from different subsets is not a comparison. State the final per-arm N prominently.
7. Estimate cost before the full run by running five events end to end and extrapolating from the logged tokens. At this pipeline's observed costs, 102 full-document calls cost about $1.49, so the full ablation should land in the low tens of dollars at worst, but confirm from the pilot rather than assuming.

**Outputs.** `section_availability_audit.csv`, the split section files, `section_ablation_results.csv` with one row per event per arm, `section_accuracy_vs_tokens.png` with one point per arm, and a pooled four-row table of accuracy and cost by component with a one-line implication for future document gathering.

**Acceptance checks.**

- The results file contains only complete five-arm events and its N matches the audit's qualifying count.
- The boundary definitions were written and echoed before the first scoring call, verifiable from timestamps.
- Every call logged tokens and cost, and the full-bundle arm's accuracy is sanity-checked against the deployed pipeline's accuracy on the same events, expecting them close since it is the same prompt on the same text.

**What to expect.** Written down before running so it counts as a tested prediction, expect the guidance passage and press release to carry more than their token share and prepared remarks least. Expect per-company cells to be uninformative, only the pooled table is a result. Expect the achieved five-arm N to be well below 268, and if it comes back very small, report the audit itself as the finding and cut the thinnest arm per the cut order.

---

## Item D. FinBERT baseline, the deferred half of the frontier

**Runs without Human Arm Results,** unless the human arm is later added to the frontier as a point, which needs their minutes.

**Main topic.** Whether a small free sentiment model matches the LLM on accuracy, completing the cost-accuracy frontier.

**What it does and the goal.** The Loughran-McDonald half is done in `experiments/lm_baseline.py` with its dev and eval split already defined. FinBERT was deferred for its torch dependency. Score the same extracted text with FinBERT, push it through the identical grading, and finish the three-way frontier the original design specified. One day including environment setup.

**Inputs.** `experiments/lm_baseline.py` as the pattern to mirror, `outputs/global/summary/lm_baseline_dev_thresholds.json` and its split definition, the cached extracted text per event, the phase2 calibration CSV, the API cost ledger `api_cost_ledger.csv` for the model arm's cost point.

**Steps.**

1. Install `torch` CPU build and `transformers`, add both to `requirements.txt`. Load `ProsusAI/finbert` from HuggingFace, one download, no API key.
2. Create `experiments/finbert_baseline.py` mirroring `lm_baseline.py`'s structure, and reuse its exact dev and eval split, earliest 20 percent of the 268 events by `report_date` as dev, the rest as eval. Do not define a new split, the point is that every baseline faces identical conditions.
3. Chunk each document's extracted text to FinBERT's 512-token limit, score each chunk, and average chunk sentiment weighted by chunk token length, so a two-sentence chunk does not count as a full page.
4. Map the averaged score to BUY, HOLD and SELL with thresholds fitted on the dev split only, frozen, then applied to the eval split. The trap is fitting on the events being scored, which hands the cheap arm an advantage the model never had.
5. Grade through the identical evaluation as `lm_baseline.py`, same events, same 5-day outcome labels, so nothing differs but the scorer.
6. Assemble the frontier. Accuracy against cost per document with one point each for Loughran-McDonald, FinBERT, the deployed model from the ledger, and the majority-class HOLD baseline as a horizontal reference. Bootstrap intervals on each accuracy. State plainly that model API cost and local compute time are different currencies and any conversion is an assumption.

**Outputs.** `finbert_dev_thresholds.json`, `finbert_eval_results.csv`, `frontier_table.csv`, `frontier.png`.

**Acceptance checks.**

- The eval split event list is byte-identical to `lm_baseline.py`'s, verifiable by comparing the document id sets.
- Chunk weighting is by token length, checked on one long document by hand.
- The existing LM result reproduces unchanged in the frontier table, 0.3785 on n=214 against the model's 0.3972 and majority-class 0.4252, since this item adds a point rather than re-running the old ones.

**What to expect.** Expect FinBERT to land between the word list and the model, and possibly uncomfortably close to the model. The majority-class baseline already beats both existing arms on this metric, that honest shape stays in the write-up, and if FinBERT matches the model the argument shifts explicitly to the structured output and screened evidence quotes, which no baseline produces.

---

## Item E. Extension 1, full walk-forward validation

**Requires Human Arm Results for the human line only. The model version runs now.**

**Main topic.** Whether the result survives when settings are fitted only on the past and applied only to the future.

**What it does and the goal.** Every threshold in use was chosen with all 268 events in view, so the objection is that the settings were tuned to the answer. The freeze note of 2026-08-10 already exists and stands. What remains is the rolling build. One honest complication the original spec did not foresee, all 268 events predate the freeze, so the two-window headline, fit pre-freeze and report post-freeze, has an empty second window until the expansion names or post-August quarters report. Build the function so that headline runs the moment post-freeze events exist, and deliver the rolling retrospective version now, labelled as such. Three to four days, the most expensive code item left.

**Inputs.** The phase2 calibration CSV for scores, dates and outcomes, `blend.blend_scores` with `DEFAULT_WEIGHTS`, `backtest.simulate` for P&L per slice, `bootstrap_stats` for the pooled interval, the freeze note for what frozen means.

**Steps.**

1. Write one function in `experiments/walkforward_validation.py` taking a training cutoff date and a test span, filtering events by `report_date`, fitting on training events only, then scoring the test span with those settings frozen. Everything else calls this function, nothing reimplements it.
2. Refit the HOLD thresholds only, `hold_upper` and `hold_lower` on the blended score, holding `DEFAULT_WEIGHTS` fixed. Re-deriving weights on 40 events is unstable and the earlier phase2 weight sweep already showed this dataset cannot support combinatorial weight search, PSR near zero and a LOOCV sign flip, so thresholds-only is the locked choice, not an option.
3. Fit thresholds on the training slice by the same criterion the deployed thresholds were chosen by, and record in the output which criterion that was, checking `CLAUDE.md` and the sweep scripts for the deployed convention rather than inventing one. If the deployed criterion cannot be pinned down, use directional accuracy on the training slice and say so in the output metadata.
4. Rolling version. Start the training window at roughly the first 40 percent of events by `report_date` with a floor of 40 events, step forward one calendar quarter, refit thresholds, score the next quarter's events out of sample, and stitch the slices into one out-of-sample record.
5. Log per window the fitted thresholds, training count, test count, trade count, hit rate and mean net return. The trap is a threshold refitted on a thin slice going degenerate, so wide that nearly everything is HOLD and accuracy looks fine because no calls are made. A collapsing trade count is how that shows up and it is invisible unless logged, so assert loudly if any window's trade count falls below a handful.
6. Report the pooled out-of-sample figures, accuracy on the 5-day convention and mean net per trade on the overnight convention, per the two-horizon rule, each with a bootstrap interval, alongside the in-sample equivalents for contrast.
7. Implement the two-window headline as a callable path, fit on events dated on or before 2026-08-10 and score events after it, and have it exit cleanly reporting zero post-freeze events for now. That path becomes live in September with no code change.
8. Label every output retrospective validation. The freeze note's caveat is not optional and the write-up must not present any of this as pre-registered.

**Outputs.** `ext1_walkforward_windows.csv`, `ext1_walkforward_oos_curve.csv` and `.png`, `ext1_walkforward_pooled.json` with in-sample versus out-of-sample side by side, and the dormant two-window path documented in the script header.

**Acceptance checks.**

- Running the function with the training cutoff after all events reproduces the full-sample deployed figures exactly, confirming the wrapper matches the production path.
- No test event's `report_date` precedes its window's training cutoff, asserted in code.
- The per-window log exists, and any degenerate window is flagged in the console output rather than silently included.

**What to expect.** Around eight windows of a dozen or so test events each, too thin to read individually, so the stitched record and pooled figure are the result and the per-window table is a diagnostic. Expect the out-of-sample figures to be worse than in-sample, that is the honest point of the exercise, and expect wide intervals.

---

## Sequencing

1. Item A first, it unblocks Item B and its per-ticker copies are owed to the human arm.
2. Item C's availability audit in parallel with A, it costs nothing and its result sizes the biggest remaining job. Pause after the audit for boundary confirmation from Nigel and the pipeline owner before splitting or scoring.
3. Item B immediately after A.
4. Item D any time, it is independent of everything else.
5. Item C's runs once boundaries are confirmed, section calls cost pennies but run the five-event pilot first.
6. Item E last among the builds, it is the longest and depends on nothing here.
7. Nothing new starts after 25 August, that week is writing.

## Cut order if time slips

1. Reduce Item E's rolling granularity, fewer and larger windows, keeping the pooled out-of-sample figure and the dormant two-window path.
2. Cut the thinnest section arm in Item C if the audit shows poor availability, and if availability is very poor report the audit itself as the finding.
3. Item D last, the frontier already has one cheap baseline and the majority-class reference, so the argument survives without FinBERT, thinner.

## Things not to do

- Do not rebuild anything on the already-done list, import or read it.
- Do not fit any threshold on the events it is scored on, in the FinBERT mapping, the implied bands, or the walk-forward refits.
- Do not compare arms drawn from different event subsets, in the ablation or the frontier.
- Do not compound returns across horizons or present any long-horizon total as an achievable balance.
- Do not present the walk-forward as pre-registered, or the two-window headline as available before post-freeze events exist.
- Do not conflate the overnight P&L convention with the 5-day accuracy convention, the freeze note defines which figure uses which.
- Do not quote the retired figures, 120 events, 113 bps break-even, or the 0.466 to 0.443 macro pair. The repo's own numbers replace all three.
- Do not write into production output files, new outputs get new names beside them.
- Do not touch `Master_Data_NEW.ods` or anything under `humans/`, those belong to the human arm.
