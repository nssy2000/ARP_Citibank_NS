"""
experiments/leave_one_out_robustness.py
Extension 5 of the model-arm spec (Nigel, 2026-08-05): profit is concentrated
in a small subset of the phase2 backtest's ~268 trades, so this answers "is
the total-return result resting on a handful of lucky calls" with a number
instead of a reassurance.

Three passes, all against the deployed LLM's overnight-gap backtest
(backtest.simulate on the phase2 calibration CSV - NOT the 5-day accuracy
CSV, see CLAUDE.md's two-metrics-do-not-conflate rule):
  - leave-one-ticker-out: drop each company's trades entirely, resimulate.
  - leave-one-quarter-out: drop each CALENDAR quarter of report_date
    (explicitly not fiscal quarter).
  - leave-one-event-out: the top 10 single-event contributors to total
    return, via the commutative-product shortcut (equity is a product of
    (1+net) terms, so dropping event i's contribution to total return is
    eq_full / (1+net_i) - 1, no resimulate needed) for a fast full sweep,
    then a real filtered simulate() only for the top 10 by impact (hit
    rate / avg-per-trade need the real resimulate, the shortcut only gives
    total return).

Run: python -m experiments.leave_one_out_robustness
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import backtest
from bootstrap_stats import bootstrap_trade_stats

PHASE2_CALIBRATION_CSV = backtest.OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration_phase2.csv"
MAIN_CSV = backtest.OUTPUTS_DIR / "global" / "summary" / "leave_one_out_robustness.csv"
FULL_CSV = backtest.OUTPUTS_DIR / "global" / "summary" / "leave_one_out_robustness_full.csv"

TOP_N = 10


def calendar_quarter(report_date: str) -> str:
    dt = datetime.strptime(report_date, "%Y-%m-%d")
    return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"


def _row(scope: str, dropped_key: str, n_dropped: int, full_stats: dict, sub_stats: dict) -> dict:
    return {
        "scope": scope,
        "dropped_key": dropped_key,
        "n_dropped": n_dropped,
        "n_remaining_trades": sub_stats["n_trades"],
        "total_return_pct": sub_stats["compounded_total_return_pct"],
        "delta_total_return_pct": round(sub_stats["compounded_total_return_pct"] - full_stats["compounded_total_return_pct"], 2),
        "avg_net_per_trade_pct": sub_stats["avg_net_per_trade_pct"],
        "hit_rate": sub_stats["hit_rate"],
        "hit_rate_delta": round(sub_stats["hit_rate"] - full_stats["hit_rate"], 4),
    }


def leave_one_ticker_out(preds: list, full_stats: dict) -> list[dict]:
    tickers = sorted({p.ticker for p in preds})
    rows = []
    for t in tickers:
        remaining = [p for p in preds if p.ticker != t]
        n_dropped = sum(1 for p in preds if p.ticker == t)
        sub = backtest.simulate(remaining)
        rows.append(_row("TICKER", t, n_dropped, full_stats, sub))
    return rows


def leave_one_quarter_out(preds: list, full_stats: dict) -> list[dict]:
    quarters = sorted({calendar_quarter(p.report_date) for p in preds})
    rows = []
    for q in quarters:
        remaining = [p for p in preds if calendar_quarter(p.report_date) != q]
        n_dropped = sum(1 for p in preds if calendar_quarter(p.report_date) == q)
        sub = backtest.simulate(remaining)
        rows.append(_row("QUARTER", q, n_dropped, full_stats, sub))
    return rows


def leave_one_event_out_fast(preds: list, full_stats: dict) -> tuple[list[dict], list[dict]]:
    """Returns (top_n_real_rows, full_fast_path_rows). Fast path uses the
    commutative-product shortcut for total_return only; the top N by
    |delta| get a real simulate() for hit_rate/avg_net_per_trade."""
    # full_stats["equity"] rows are (report_date, ticker, decision, gap, net, eq);
    # final row's eq is the compounded product of all (1+net) terms.
    full_eq = full_stats["equity"][-1][-1] if full_stats["equity"] else 1.0

    traded_rows = [r for r in full_stats["equity"] if r[2] != "HOLD"]  # decision index 2
    fast_rows = []
    for report_date, ticker, decision, gap, net, _eq in traded_rows:
        dropped_total_return_pct = round((full_eq / (1.0 + net) - 1.0) * 100, 2)
        delta = round(dropped_total_return_pct - full_stats["compounded_total_return_pct"], 2)
        fast_rows.append({
            "scope": "EVENT", "dropped_key": f"{ticker} {report_date}", "n_dropped": 1,
            "n_remaining_trades": full_stats["n_trades"] - 1,
            "total_return_pct": dropped_total_return_pct,
            "delta_total_return_pct": delta,
            "avg_net_per_trade_pct": "n/a (fast-path)",
            "hit_rate": "n/a (fast-path)",
            "hit_rate_delta": "n/a (fast-path)",
        })

    fast_rows.sort(key=lambda r: abs(r["delta_total_return_pct"]), reverse=True)
    top_n_keys = {r["dropped_key"] for r in fast_rows[:TOP_N]}

    real_rows = []
    for r in fast_rows:
        if r["dropped_key"] not in top_n_keys:
            continue
        ticker, report_date = r["dropped_key"].rsplit(" ", 1)
        remaining = [p for p in preds if not (p.ticker == ticker and p.report_date == report_date)]
        sub = backtest.simulate(remaining)
        real_rows.append(_row("EVENT", r["dropped_key"], 1, full_stats, sub))

    real_rows.sort(key=lambda r: abs(r["delta_total_return_pct"]), reverse=True)
    return real_rows, fast_rows


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["scope", "dropped_key", "n_dropped", "n_remaining_trades",
                  "total_return_pct", "delta_total_return_pct",
                  "avg_net_per_trade_pct", "hit_rate", "hit_rate_delta"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {path}")


def main() -> int:
    preds = list(backtest.llm_predictions(PHASE2_CALIBRATION_CSV))
    full_stats = backtest.simulate(preds)
    print(f"Full sample: {full_stats['n_trades']} trades, "
          f"total return {full_stats['compounded_total_return_pct']:.2f}%, "
          f"hit rate {full_stats['hit_rate']*100:.1f}%")

    full_row = {
        "scope": "FULL", "dropped_key": "(none)", "n_dropped": 0,
        "n_remaining_trades": full_stats["n_trades"],
        "total_return_pct": full_stats["compounded_total_return_pct"],
        "delta_total_return_pct": 0.0,
        "avg_net_per_trade_pct": full_stats["avg_net_per_trade_pct"],
        "hit_rate": full_stats["hit_rate"],
        "hit_rate_delta": 0.0,
    }

    ticker_rows = leave_one_ticker_out(preds, full_stats)
    quarter_rows = leave_one_quarter_out(preds, full_stats)
    event_top_n, event_fast_full = leave_one_event_out_fast(preds, full_stats)

    ticker_sorted = sorted(ticker_rows, key=lambda r: abs(r["delta_total_return_pct"]), reverse=True)
    quarter_sorted = sorted(quarter_rows, key=lambda r: abs(r["delta_total_return_pct"]), reverse=True)

    main_rows = [full_row] + ticker_sorted[:TOP_N] + quarter_sorted[:TOP_N] + event_top_n
    write_csv(MAIN_CSV, main_rows)

    full_rows = [full_row] + ticker_sorted + quarter_sorted + event_fast_full
    write_csv(FULL_CSV, full_rows)

    nets_for_ci = [row[4] for row in full_stats["equity"] if row[2] != "HOLD"]
    ci = bootstrap_trade_stats(nets_for_ci)
    print(f"\nFull-sample total return 90% bootstrap CI: "
          f"{ci['total_return']['point']*100:.2f}% "
          f"[{ci['total_return']['ci_low']*100:.2f}%, {ci['total_return']['ci_high']*100:.2f}%]")

    print(f"\nTop {TOP_N} ticker exclusions by |delta|:")
    for r in ticker_sorted[:TOP_N]:
        print(f"  drop {r['dropped_key']:8} -> total return {r['total_return_pct']:>8.2f}%  "
              f"(delta {r['delta_total_return_pct']:+.2f}pp)")

    print(f"\nTop {TOP_N} single-event contributors by |delta|:")
    for r in event_top_n:
        print(f"  drop {r['dropped_key']:20} -> total return {r['total_return_pct']:>8.2f}%  "
              f"(delta {r['delta_total_return_pct']:+.2f}pp)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
