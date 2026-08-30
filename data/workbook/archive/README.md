# Workbook Archive

This folder contains superseded versions of the Master Data workbook.
The current version lives one level up at `data/workbook/Master_Data_Phase_34_corrected.xlsx`.

## File history

| Filename | Date | Size | What changed from previous |
|---|---|---|---|
| Master_Data_NEW_REPAIRED_2026-08-09.xlsx | 2026-08-09 | 624 KB | First structurally-repaired version of the workbook after the original `Master_Data_NEW.ods` was found to be malformed OOXML (odfpy/pandas failed with `duplicate attribute`/`ExpatError`). Split into separate `Human_Data_Entry` and `LLM_Data_Entry` tabs with the new schema. Includes the report-date audit fixes applied 2026-08-09 (corrected `AMKBY_FQ1_2025`, `DIS_FQ1_2025`, `PUM.DE_FQ3_2025`, `LNVGY_FQ2_2026`). |
| Master_Data_CORRECTED_2026-08-13.xlsx | 2026-08-13 | 592 KB | Post anchor-correction version. Entry anchor switched from `report_date` (post-announcement close) to `release_date` (8-K Item 2.02 date) for all 82 pre_market events. Exclusion set applied: 35 events removed (25 worksheet contamination, 1 SPOT misattribution, 9 timing unresolved), reducing the graded universe from N=268 to N=233. Headline figures corrected to 65.3% accuracy (62/95 directional), mean net per trade +1.862%. |
| Master_Data_LOCKED_2026-08-13.xlsx | 2026-08-13 | 584 KB | Locked/frozen snapshot taken same day as CORRECTED_2026-08-13. Represents the state at which the anchor correction was considered complete and the dataset was locked for the primary analysis. Minor structural differences from the CORRECTED version (formatting, column locking). |
| Master_Data_CORRECTED_2026-08-14.xlsx | 2026-08-14 | 712 KB | One-day follow-up correction fixing `PUM.DE_FQ1_2026` `outcome_label`/`is_correct` fields that were found wrong after the 2026-08-13 lock. Also adds `evidence_quotes`, `summary`, and `price` fields to prototype_events entries. Largest file in the archive due to additional data columns added during this session. |
| Master_Data_Phase_3_2026-08-20.xlsx | 2026-08-20 | 1.1 MB | Phase 3 schema migration — expanded to cover the full 73-issuer phase2 universe and added the `Efficiency` tab tracking LLM wall-clock time and token cost per document. Blend weights promoted to `DEFAULT_WEIGHTS = (0.80, 0.20, 0.0, 0.0)` (micro/macro/news/quant), thresholds `hold_upper=0.20`/`hold_lower=-0.10`. This version was superseded within hours by `_synced` below after a final sync pass. |
| Master_Data_Phase_3_2026-08-20_synced.xlsx | 2026-08-20 | 1.1 MB | Final synced state after the 2026-08-19 weight promotion was gated artifact-by-artifact: each derived output was reproduced at the old constants before regeneration at the new ones. All summary CSVs, backtest outputs, and workbook metrics reflect `(0.80, 0.20, 0.0, 0.0)` weights with `+0.20/-0.10` thresholds. Superseded by `Master_Data_Phase_34_corrected.xlsx`. |
| **Master_Data_Phase_34_corrected.xlsx** | **2026-08-30** | **855 KB** | **Current version — in `data/workbook/`** (not this archive). Phase 3/4 corrected workbook. |

## Notes

- The `.ods` originals (`Master_Data_NEW.ods` etc.) were the live SharePoint workbook exports and are not committed to this repository — only the `.xlsx` derivatives are present here.
- All versions from CORRECTED_2026-08-13 onward use `release_date` as the entry anchor. Versions before that date used `report_date` and are fully superseded.
- Do not use any archived version for analysis — use the current `Master_Data_Phase_34_corrected.xlsx`.
