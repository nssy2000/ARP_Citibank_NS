# Workbook correction notes

## Original price basis (superseded)

The source workbook `Master_Data_NEW_REPAIRED_2026-08-09.xlsx` uses the close of
`report_date` as the entry price uniformly for all events. This convention is wrong
for approximately 82 pre_market events: for those events, the 8-K Item 2.02 was filed
before market open, so the relevant entry price is the open on `release_date` (the filing
date), not the close on that same day. Using the close-on-release_date convention for
pre_market events inflates the measured overnight move, because the close already reflects
the announced results.

## Section C re-pricing block (invalid)

The Section C re-pricing section of the source workbook selected measurement windows by
observed price movement (choosing whichever window showed the largest move). This is
selection bias: windows are chosen because they moved, not because they are the correct
entry/exit point. Any accuracy or P&L figures derived from Section C are not valid and
must not be used.

## Corrected basis

The corrected entry anchor is `release_date` from the EDGAR 8-K Item 2.02 filing date,
with the following timing rule:

- **pre_market** events (8-K filed before market open): entry close = close on the
  preceding trading day; entry open = open on `release_date`.
- **after_hours** events (8-K filed after market close): entry close = close on
  `release_date`; entry open = open on the next trading day.

The timing classification is inferred from the relationship between `entry_date` and
`report_date` in `returns_matrix.csv`: if `entry_date < report_date` then pre_market;
if `entry_date == report_date` then after_hours.

**Date correction established**: 2026-08-12. Source: `item_e_handoff.md`,
`returns_matrix.csv`, `retracted_findings_2026-08-12.md`.

## What changed

- **`Master_Data_LOCKED_2026-08-13.xlsx`**: Human_Data_Entry prices unchanged.
  LLM_Data_Entry updated to corrected figures. New sheets appended. A banner in
  Human_Data_Entry A1 notes that the human arm prices remain on the superseded basis.

- **`Master_Data_CORRECTED_2026-08-13.xlsx`**: Human_Data_Entry prices corrected
  for all events where `correctable=TRUE` in `workbook_human_prices_corrected.csv`.
  Events marked `correctable=FALSE` (human-only events not in the LLM returns_matrix)
  retain original prices; manual verification against EDGAR is required. LLM_Data_Entry
  updated. New sheets appended.

After opening either file in Excel, force a full recalculation with **Ctrl+Alt+F9**
before circulating. LibreOffice cannot evaluate XLOOKUP and will show #NAME? errors —
this does not indicate file corruption.
