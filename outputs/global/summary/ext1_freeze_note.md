# Extension 1 freeze note (retrospective, not pre-registered)

**Dated 2026-08-10.**

This note freezes the settings behind every "deployed default" figure quoted in this project's write-up, as a defined point that later work (the expansion companies, and any quarter that reports after today) can be scored against as a genuinely blind set.

**Caveat, stated up front and not optional:** all 268 events in the current phase2 track have already been run and seen before this note was written. This is **retrospective validation**, not a pre-registered freeze - the settings below were chosen with the full dataset in view (see `CLAUDE.md`'s own account of the 2026-08-05 weight promotion, which was made after seeing the P&L sweep's in-sample result). Nothing here should be presented as a blind, pre-registered walk-forward. It is a dated snapshot of what "the deployed model" means, so that anything scored after this date is comparable against a fixed target rather than a moving one.

## Frozen settings

- **Blend weights** (micro, macro, news, quant): `(0.55, 0.45, 0.0, 0.0)` — `blend.DEFAULT_WEIGHTS`.
- **HOLD thresholds**: `hold_upper = +0.25`, `hold_lower = -0.05` — `blend.DEFAULT_HOLD_UPPER` / `blend.DEFAULT_HOLD_LOWER`.
- **Cost assumption**: `cost_bps = 10.0` round-trip, `short_borrow_bps = 0.0` — `backtest.simulate()` defaults.
- **Horizon** (do not conflate the two, per `CLAUDE.md`'s own rule):
  - P&L / backtest figures (total return, Sharpe, trade count, avg/trade): **overnight**, close of `report_date` to next session's open (`backtest.py`'s `overnight_gap()`).
  - Calibration / accuracy figures (the bare "accuracy" percentage, LOOCV, weight sweeps): **5-day close-to-close** (`eval/outcomes.py`'s `fetch_forward_return(window_trading_days=5, exit_on_open=False)`).

## What this note is for

Any new event scored after 2026-08-10 against these exact frozen settings can be described as an out-of-sample check against a fixed target, distinct from the in-sample N=268 track. It does not by itself constitute a walk-forward validation (Extension 1's full rolling-window build, see the spec) - that remains out of scope for this build pass. It only records what "frozen" means so a future pass can compare against it honestly.
