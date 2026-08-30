# JPM_FQ1_2025: Why price-based window selection fails

## The error

A diagnostic script used price patterns to determine `release_date` for
events where the field had not yet been built. The logic:

```python
open_gap = abs((rdate_open - prior_close) / prior_close)
overnight = abs((next_open - rdate_close) / rdate_close)

if overnight > open_gap * 2:
    release_date = next_trading_day   # "eve" pattern
else:
    release_date = report_date        # "day-of" pattern
```

For JPM_FQ1_2025, this classified the event as "day-of" (release on
2025-04-10) when the actual release was 2025-04-11.

## What happened

JPM_FQ1_2025 has `report_date = 2025-04-10`. JPM actually released Q1 2025
results pre-market on **2025-04-11** (Friday) at approximately 7:00 AM ET.
The EDGAR 8-K Item 2.02 filing is `jpm-20250411.htm` (accession
0000019617-25-000332), filed 2025-04-11.

But on 2025-04-09, the US announced a 90-day tariff pause. The broad market
rallied sharply, and JPM ran from a $212.50 open to a $234.34 close — a
+10.3% intraday move with no company-specific news.

## The price table

```
Date         Open       Close      Note
2025-04-08   $223.52    $216.87
2025-04-09   $212.50    $234.34    Tariff-pause rally (+10.3% intraday)
2025-04-10   $230.00    $227.11    report_date (no JPM news this day)
2025-04-11   $226.31    $236.20    Actual earnings release (pre-market)
```

## Why the classifier failed

The classifier compared:
- `|open_gap|` on 2025-04-10: |(230.00 - 234.34) / 234.34| = 1.85%
- `|overnight|` from 2025-04-10 close to 2025-04-11 open:
  |(226.31 - 227.11) / 227.11| = 0.35%

Since `|open_gap| > |overnight|`, the classifier concluded the earnings
reaction was at the 4/10 open (i.e., report_date was the day-of). In
reality, the open gap on 4/10 was the tariff rally **unwinding** — a
market-wide move, not an earnings reaction — and the actual earnings gap
(4/11 open vs 4/10 close = -0.35%) was suppressed by the same market
turbulence.

## The lesson

The classifier selected the measurement window by checking which window
contained the larger move. This is classification by outcome: it asks "where
did the price move?" and assigns the window accordingly. When a market-wide
event (tariff pause) produces a larger move than the earnings event, the
classifier points at the wrong day.

This failed on JPMorgan Chase, the most canonical pre-market reporter in the
dataset. The correct anchor — `release_date = 2025-04-11` from the EDGAR 8-K
Item 2.02 filing — is a documented fact that does not depend on which window
moved more.

## Resolution

`release_date` is now built from the EDGAR 8-K Item 2.02 filing date for
every US event, with zero price input in the resolution path. The price-based
diagnostic was never committed and no graded output was contaminated.

## The corrected window still does not contain the move

Under the verified anchor (`release_date = 2025-04-11`), the corrected window
is:

```
Entry:  2025-04-10 close  = $227.11
Exit:   2025-04-11 open   = $226.31
Gap:    -0.35%
```

JPM released at ~07:00 ET on 4/11, 2.5 hours before the 09:30 open. The open
at $226.31 barely moved from the prior close. The earnings reaction was
absorbed **during the session**: open $226.31 → high $238.58 → close $236.20
(+4.37% intraday). The overnight close-to-open gap captured almost none of it.

This is not unique to JPM. Across all 136 pre_market events:

| Metric | |overnight gap|| |close-to-close| |
|---|---|---|
| Mean | 3.16% | 4.02% |
| Median | 2.64% | 3.23% |
| Exceeds ±2% band | 59% of events | 66% of events |
| Which is larger | 40% of events | 60% of events |

The overnight gap systematically underestimates the earnings reaction for
pre-market reporters by a factor of ~1.27x on average. In 60% of events the
close-to-close move is larger than the gap, meaning the session extends or
reverses the pre-market reaction. The gap captures the pre-market pricing
(which for liquid large-caps is efficient but not complete), while the session
adds the full analyst-hours repricing.

This is a **structural limitation of the overnight close-to-open convention
for pre-market reporters**, not an anchor error. The ±2% raw band is
pre-registered and stays. The limitation belongs in the methodology: the
overnight gap is a noisier measure of the earnings reaction for BMO reporters
than for AMC reporters, and 136/229 clean events (59%) are BMO.

## Robustness note: raw versus excess grading

In turbulent months (April 2025, October 2025), roughly one event in six
would flip its grade if measured on excess-over-SPY returns rather than raw
returns, because market-wide moves exceed the ±2% band independently of any
company-specific news. The raw band conflates market-wide moves with
company-specific ones during market stress. Pre-registered band retained;
this is a stated limitation.

| Month | Events | Raw/excess disagree | Rate |
|---|---|---|---|
| 2025-04 | 19 | 3 | 16% |
| 2025-10 | 30 | 5 | 17% |
| All other | 205 | 7 | 3% |
