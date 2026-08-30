"""
backtest.py
Overnight-gap trading backtest for ANY predictor - the LLM or any human rater -
scored identically so they can be compared apples-to-apples.

Strategy modelled: on each earnings print, take the predictor's decision and
trade the overnight gap:
  BUY  -> long into the report_date close, exit next session's OPEN   (profit if gap up)
  SELL -> short into the close, cover at next OPEN                     (profit if gap down)
  HOLD -> no trade, no P&L

Overnight gap% = (next_day_open - report_date_close) / report_date_close
(identical to the group sheet's "Actual % Change" and eval/outcomes.py's
exit_on_open=True overnight metric).

Why this exists: raw 3-class accuracy is the WRONG scorecard for a trading
signal - it penalises a harmless bet-on-a-flat exactly as hard as a bet in the
wrong direction, but in P&L a flat bet is ~breakeven and a wrong-direction bet
is a real loss. This module scores the thing that actually matters: money, net
of transaction costs, with an equity curve, hit rate, drawdown and a
direction-error breakdown.

Predictor-agnostic input: any iterable of Prediction(rater, kind, ticker,
report_date, decision[, prior_close, next_day_open]). Two adapters are provided:
  - llm_predictions()        : the deployed LLM decisions from the calibration CSV
  - load_sheet_predictions() : any CSV/TSV in the group-sheet schema (one row per
                               rater per quarter), so the humans' own BUY/HOLD/SELL
                               calls drop straight in.

Costs: `cost_bps` is the round-trip transaction cost (commission + spread), in
basis points, charged once per trade taken. `short_borrow_bps` is an extra
per-trade charge on SELLs for one night of borrow. Both are configurable; the
CLI prints a sensitivity table across several cost levels.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev

from export_sheet_rows import BASE_DIR, OUTPUTS_DIR, fetch_prices

CALIBRATION_CSV = OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration.csv"
EQUITY_CSV = OUTPUTS_DIR / "global" / "summary" / "backtest_equity.csv"

# Group sheet's material-move threshold (Settings!B3 = 2%) - used ONLY to label the
# direction-error breakdown (correct / flat / wrong), never for P&L.
FLAT_BAND = 0.02


@dataclass(frozen=True)
class Prediction:
    rater: str
    kind: str            # "LM" or "Human"
    ticker: str
    report_date: str     # YYYY-MM-DD
    decision: str        # BUY / HOLD / SELL
    prior_close: float | None = None
    next_day_open: float | None = None
    release_timing: str | None = None  # pre_market / after_hours; looked up from manifest


@dataclass(frozen=True)
class Trade:
    report_date: str
    ticker: str
    decision: str
    position: int        # +1 long, -1 short, 0 flat
    gap: float           # overnight gap return (signed, as a fraction)
    gross: float         # position * gap
    cost: float          # transaction + borrow cost charged (fraction, >= 0)
    net: float           # gross - cost


def _decision_to_position(decision: str) -> int:
    d = decision.strip().upper()
    if d in ("BUY", "UP"):
        return 1
    if d in ("SELL", "DOWN"):
        return -1
    return 0  # HOLD / FLAT / anything else


def overnight_gap(pred: Prediction) -> float | None:
    """Overnight gap return for a prediction. Uses the row's own prices if present
    (human sheet rows carry them); otherwise fetches (cached) from yfinance."""
    prior, nxt = pred.prior_close, pred.next_day_open
    if prior is None or nxt is None:
        timing = pred.release_timing or "after_hours"
        try:
            prior, nxt = fetch_prices(pred.ticker, pred.report_date, timing)
        except Exception:
            return None
    if not prior:
        return None
    return (nxt - prior) / prior


def simulate(preds, cost_bps: float = 10.0, short_borrow_bps: float = 0.0) -> dict:
    """Run the overnight-gap strategy for one predictor. Returns stats + the
    chronological equity curve (compounded net return of $1 with full capital on
    each non-overlapping trade).

    NOTE on reported metrics:
    - ``compounded_total_return_pct``: the final equity curve value expressed as a
      percentage gain.  This assumes sequential full-capital deployment across every
      event in chronological order, which is violated whenever two reporters fall in
      the same week (overlapping positions).  It is also order-dependent: shuffling
      the trade sequence changes the number.  Do NOT quote this as an achievable
      portfolio return.
    - ``summed_total_return_pct``: the simple arithmetic sum of all per-trade net
      returns, expressed as a percentage.  Order-independent, no reinvestment
      assumption, robust to overlapping reporters.  Prefer this and
      ``avg_net_per_trade_pct`` as headline P&L figures.
    - ``t_statistic``: ``mean(nets) / pstdev(nets) * sqrt(N)`` — the per-trade
      information ratio scaled by sqrt(N).  This grows mechanically with sample
      size and is NOT a time-series Sharpe ratio.  Use ``info_ratio_per_trade``
      (the unscaled ``mean/pstdev``) for a size-invariant risk-adjusted measure.
    """
    rows = []
    for p in preds:
        gap = overnight_gap(p)
        if gap is None:
            continue
        pos = _decision_to_position(p.decision)
        gross = pos * gap
        if pos == 0:
            cost = 0.0
        else:
            cost = cost_bps / 1e4 + (short_borrow_bps / 1e4 if pos < 0 else 0.0)
        rows.append(Trade(p.report_date, p.ticker, p.decision.upper(), pos, gap,
                          gross, cost, gross - cost))
    rows.sort(key=lambda t: t.report_date)

    trades = [t for t in rows if t.position != 0]
    equity, eq = [], 1.0
    peak, max_dd = 1.0, 0.0
    for t in rows:                      # walk ALL prints in time order
        eq *= (1.0 + t.net)             # HOLD contributes *1.0 (no change)
        equity.append((t.report_date, t.ticker, t.decision, round(t.gap, 4),
                       round(t.net, 4), round(eq, 4)))
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak)

    nets = [t.net for t in trades]
    wins = sum(1 for t in trades if t.net > 0)
    losses = sum(1 for t in trades if t.net < 0)

    # direction-error breakdown (labels via the group's +/-2% flat band)
    correct = flat = wrong = 0
    correct_pnl = flat_pnl = wrong_pnl = 0.0
    for t in trades:
        if abs(t.gap) < FLAT_BAND:
            flat += 1; flat_pnl += t.net
        elif (t.gap > 0 and t.position > 0) or (t.gap < 0 and t.position < 0):
            correct += 1; correct_pnl += t.net
        else:
            wrong += 1; wrong_pnl += t.net

    n_all = len(rows)
    # t_statistic = mean/pstdev * sqrt(N): the per-trade information ratio scaled by
    # sqrt(N).  Grows mechanically with sample size — NOT a time-series Sharpe.
    # info_ratio_per_trade = mean/pstdev (unscaled), size-invariant risk-adjusted measure.
    _sd = pstdev(nets) if len(nets) > 1 else 0.0
    t_statistic = (mean(nets) / _sd * (len(nets) ** 0.5)) if _sd > 0 else 0.0
    info_ratio_per_trade = (mean(nets) / _sd) if _sd > 0 else 0.0
    return {
        "n_prints": n_all,
        "n_trades": len(trades),
        "hit_rate": round(wins / len(trades), 4) if trades else 0.0,
        "wins": wins, "losses": losses,
        # compounded_total_return_pct: order-dependent equity curve; violates the
        # non-overlapping assumption when same-week reporters overlap.  Kept for
        # continuity but NOT the recommended headline figure.
        "compounded_total_return_pct": round((eq - 1.0) * 100, 2),
        # summed_total_return_pct: arithmetic sum of per-trade net returns (%).
        # Order-independent, no reinvestment assumption; prefer this as headline P&L.
        "summed_total_return_pct": round(sum(nets) * 100, 2) if nets else 0.0,
        "avg_net_per_trade_pct": round(mean(nets) * 100, 4) if nets else 0.0,
        "t_statistic": round(t_statistic, 3),
        "info_ratio_per_trade": round(info_ratio_per_trade, 4),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "breakdown": {
            "correct_direction": {"n": correct, "pnl_pct": round(correct_pnl * 100, 2)},
            "bet_on_flat":       {"n": flat,    "pnl_pct": round(flat_pnl * 100, 2)},
            "wrong_direction":   {"n": wrong,   "pnl_pct": round(wrong_pnl * 100, 2)},
        },
        "equity": equity,
    }


# --------------------------------------------------------------------------- #
# Adapters
# --------------------------------------------------------------------------- #
def _build_timing_lookup() -> dict[str, str]:
    """Build (ticker, report_date) -> release_timing from all manifests on disk.
    Extension issuers (e.g. p2_adobe_ext2026_08_13) share their manifest with the
    base slug (p2_adobe_reports.json) so the lookup covers both frozen and extension.
    """
    lookup: dict[str, str] = {}
    manifests_dir = BASE_DIR / "manifests"
    for mpath in manifests_dir.glob("*.json"):
        try:
            data = json.loads(mpath.read_text(encoding="utf-8"))
        except Exception:
            continue
        timing = (data.get("release_timing") or {}).get("value")
        if not timing:
            continue
        for report in data.get("reports", []):
            ticker = report.get("ticker")
            rdate = report.get("report_date") or report.get("release_date")
            if ticker and rdate:
                lookup[(ticker, rdate)] = timing
    return lookup


def llm_predictions(calibration_csv: Path = CALIBRATION_CSV):
    """Deployed LLM decisions (blend_predicted_signal_default) from the calibration CSV."""
    timing_lookup = _build_timing_lookup()
    with open(calibration_csv, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            timing = timing_lookup.get((r["ticker"], r["report_date"]))
            yield Prediction(
                rater="LLM (DeepSeek)", kind="LM",
                ticker=r["ticker"], report_date=r["report_date"],
                decision=r["blend_predicted_signal_default"],
                release_timing=timing,
            )


def _num(x):
    if x is None:
        return None
    x = str(x).replace("$", "").replace(",", "").strip()
    try:
        return float(x)
    except ValueError:
        return None


def load_sheet_predictions(path: Path, calibration_csv: Path = CALIBRATION_CSV):
    """Load predictions from a CSV/TSV export of the group sheet. Expected columns
    (case-insensitive, extra columns ignored): Ticker, Year, Quarter, Rater,
    Type (Human/LM), Decision (BUY/HOLD/SELL), Prior Close ($), Next Day Open ($).
    Report date is derived by matching (ticker, year, quarter) to the calibration CSV
    if a Report Date column is absent."""
    delim = "\t" if path.suffix.lower() in (".tsv", ".txt") else ","
    # build (ticker, year, quarter) -> report_date from the calibration CSV
    date_lookup = {}
    with open(calibration_csv, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            did = r["document_id"]  # e.g. BA_FQ1_2025
            parts = did.split("_")
            if len(parts) == 3:
                q = parts[1].replace("FQ", "Q"); yr = parts[2]
                date_lookup[(r["ticker"].upper(), yr, q)] = r["report_date"]

    def _norm(s: str) -> str:
        # header matching is whitespace/case-insensitive: the live group sheet's
        # real headers ("PriorClose ($)", "Next DayOpen ($)", "Decision(BUY/HOLD/SELL)",
        # "Type(Human/LLM)") don't space consistently around words/parens, so exact
        # phrase matching silently dropped prior_close/next_day_open/decision on a
        # real export - match by squashing all whitespace instead.
        return "".join(s.lower().split())

    with open(path, encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=delim)
        cols = {_norm(c): c for c in reader.fieldnames or []}

        def get(row, *names):
            for n in names:
                key = _norm(n)
                if key in cols:
                    return row[cols[key]]
            return None

        for row in reader:
            decision = get(row, "decision (buy/hold/sell)", "decision")
            if not decision:
                continue
            ticker = (get(row, "ticker") or "").upper()
            year = get(row, "year"); quarter = get(row, "quarter")
            prior_close = _num(get(row, "prior close ($)", "prior close", "prior_close"))
            next_day_open = _num(get(row, "next day open ($)", "next day open", "next_day_open"))
            rdate = get(row, "report date", "report_date")
            if not rdate and ticker and year and quarter:
                rdate = date_lookup.get((ticker, str(year), str(quarter)))
            if not rdate and year and quarter and prior_close is not None and next_day_open is not None:
                # ticker outside the LLM's 6-issuer/131-quarter calibration set (e.g. a
                # human rater's Nvidia/Amazon/McDonald's calls) - no real report_date to
                # look up, but the row already carries its own prices, so a sortable
                # "YYYY-QN" stand-in is enough for total return/hit rate (equity-curve
                # ordering is the only thing that loses precision here).
                rdate = f"{year}-{quarter}"
            if not rdate:
                continue
            yield Prediction(
                rater=(get(row, "rater") or "Unknown").strip(),
                kind=(get(row, "type (human/lm)", "type (human/llm)", "type") or "Human").strip(),
                ticker=ticker, report_date=rdate, decision=decision,
                prior_close=prior_close, next_day_open=next_day_open,
            )


def by_rater(preds):
    # group case-insensitively (e.g. "ABDUL" vs "Abdul") - matches how the group
    # sheet's own COUNTIF-based Summary dashboard already merges rater names.
    groups: dict[str, list] = {}
    canonical: dict[str, str] = {}
    for p in preds:
        key = p.rater.strip().lower()
        canonical.setdefault(key, p.rater.strip())
        groups.setdefault(key, []).append(p)
    return {canonical[k]: v for k, v in groups.items()}


# --------------------------------------------------------------------------- #
# Baselines
# --------------------------------------------------------------------------- #
def constant_predictions(template, decision: str, rater: str):
    for p in template:
        yield Prediction(rater, "Baseline", p.ticker, p.report_date, decision,
                         p.prior_close, p.next_day_open, p.release_timing)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _print_row(name, s):
    b = s["breakdown"]
    print(f"{name:22} {s['n_trades']:>3}/{s['n_prints']:<3} {s['hit_rate']*100:5.1f}%"
          f" {s['compounded_total_return_pct']:>8.2f} {s['avg_net_per_trade_pct']:>7.3f}"
          f" {s['t_statistic']:>6.2f} {s['max_drawdown_pct']:>6.2f}"
          f"   {b['correct_direction']['n']:>2}/{b['bet_on_flat']['n']:>2}/{b['wrong_direction']['n']:>2}"
          f"  {b['wrong_direction']['pnl_pct']:>7.2f}")


def report(named_stats: dict, cost_bps: float, short_borrow_bps: float):
    print(f"\n=== Overnight-gap backtest  (cost {cost_bps:.0f} bps round-trip"
          f"{f', +{short_borrow_bps:.0f} bps short borrow' if short_borrow_bps else ''}) ===")
    print(f"{'predictor':22} {'trds':>7} {'hit':>6} {'totRet%':>8} {'avg%':>7}"
          f" {'tStat':>6} {'maxDD':>6}   {'C/F/W':>8}  {'wrongP&L':>7}")
    print("-" * 92)
    for name, s in named_stats.items():
        _print_row(name, s)


def write_equity_csv(named_stats: dict, path: Path = EQUITY_CSV):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["rater", "report_date", "ticker", "decision", "gap", "net", "equity"])
        for name, s in named_stats.items():
            for rd, tk, dec, gap, net, eq in s["equity"]:
                w.writerow([name, rd, tk, dec, gap, net, eq])
    print(f"\nWrote equity curve -> {path}")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", type=Path, help="CSV/TSV export of the group sheet "
                    "(adds every human rater to the comparison).")
    ap.add_argument("--cost-bps", type=float, default=10.0,
                    help="Round-trip transaction cost in basis points (default 10).")
    ap.add_argument("--short-borrow-bps", type=float, default=0.0,
                    help="Extra per-night borrow cost on SELL trades (default 0).")
    ap.add_argument("--sensitivity", action="store_true",
                    help="Print total return of the LLM across several cost levels.")
    ap.add_argument("--calibration-csv", type=Path, default=CALIBRATION_CSV,
                    help="Alternate global_outcome_calibration.csv (e.g. a phase2/"
                    "variant-track run) instead of the production default.")
    ap.add_argument("--equity-csv", type=Path, default=EQUITY_CSV,
                    help="Alternate output path for the equity curve CSV, so an "
                    "alternate-track run never overwrites the production one.")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    llm = list(llm_predictions(args.calibration_csv))

    named = {}
    named["LLM (DeepSeek)"] = simulate(llm, args.cost_bps, args.short_borrow_bps)

    if args.sheet:
        for rater, preds in by_rater(load_sheet_predictions(args.sheet, args.calibration_csv)).items():
            # skip an LM row in the sheet - we already score the LLM from the calibration CSV
            if preds and preds[0].kind.upper() in ("LM", "LLM"):
                continue
            named[f"Human: {rater}"] = simulate(preds, args.cost_bps, args.short_borrow_bps)

    # baselines (on the LLM's quarter set, priced the same way)
    named["baseline: always-long"] = simulate(
        list(constant_predictions(llm, "BUY", "always-long")), args.cost_bps, args.short_borrow_bps)
    named["baseline: always-flat"] = simulate(
        list(constant_predictions(llm, "HOLD", "always-flat")), args.cost_bps, args.short_borrow_bps)

    report(named, args.cost_bps, args.short_borrow_bps)
    print("\nlegend: C/F/W = correct-direction / bet-on-a-flat / wrong-direction trades;"
          " wrongP&L = P&L from the wrong-direction bets only.")
    write_equity_csv(named, args.equity_csv)

    if args.sensitivity:
        print("\n=== LLM total return vs round-trip cost ===")
        print(f"{'cost bps':>9} {'totRet%':>9} {'avg%/trade':>11}")
        for c in (0, 5, 10, 20, 30, 50):
            s = simulate(llm, float(c), args.short_borrow_bps)
            print(f"{c:>9} {s['compounded_total_return_pct']:>9.2f} {s['avg_net_per_trade_pct']:>11.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
