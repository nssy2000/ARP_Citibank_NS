# backtest_equity_extension_2026_08_24.csv

Written by `eval/extension_gaps.py` on 2026-08-20.

- blend weights `(0.8, 0.2, 0.0, 0.0)`, band `(+0.2, -0.1)` - read from `blend.py`, never hard-coded here
- entry anchor: `report_date`; entry session chosen by the manifest's `release_timing`; gap = entry close -> next session open
- cost 10.0 bps round trip, short borrow 0.0 bps
- 93 events x 3 arms
- keyed on `document_id` (added 2026-08-24); consumers must join on it,
  not on `(ticker, report_date)`, which moves when an anchor is corrected
- 1 exception(s), listed in `backtest_equity_extension_exceptions_2026_08_24.csv`

Supersedes `backtest_equity_extension_2026_08_13.csv`, which stays as the
record and which this script reproduces at that date's constants before it
is allowed to write. The CSV carries no comment header on purpose: its four
consumers pass the handle straight to `csv.DictReader`.
