"""
experiments/extension4_conviction_sizing.py
Extension 4 of the model-arm spec (Nigel, 2026-08-05), model-side half only
(the human-line half waits on Nigel's team's reading sessions regardless).

Question: does sizing each trade in proportion to the model's own conviction
(|blended score|) beat flat sizing? If a high-conviction call really is more
likely to be right, betting more on it should make more money; if it doesn't,
that's a deployment finding too, not a failure.

Score = the DEPLOYED BLENDED score (blend.DEFAULT_WEIGHTS), recomputed per
event from the calibration CSV's raw layer scores - same locked convention as
Item 6 (experiments/asymmetry_conviction_analysis.py), not micro alone.

Two books, both run over the identical N=268 event set and identical prices:
  - flat  : backtest.simulate() UNMODIFIED - every trade at the same notional.
            This is the existing, already-reported N=268 backtest number and
            doubles as a sanity check that this script's event/price loading
            matches backtest.py's own llm_predictions() adapter exactly.
  - sized : size_i = |score_i| / mean(|score| across TRADED events only).
            Dividing by the mean is what keeps the sized book scale-invariant
            (average size 1.0x) - without it, "conviction sizing" is just a
            bigger book and wins on total return by construction, telling you
            nothing about whether conviction carries information. That's the
            spec's own named trap.
    Normalization population choice: the mean is taken over events that
    actually traded (position != 0), not all 268 scored events, because
    sizing only has meaning for trades placed - a HOLD event's score doesn't
    contribute notional to the book either way. This is a modeling choice,
    stated explicitly rather than left implicit.

Per-trade math (not a backtest.simulate() edit - see the module docstring's
"less invasive" note): cost_bps is a percentage-of-notional fee, so scaling a
trade's notional by size_i scales both its gross P&L and its cost by size_i
in lockstep: net_sized_i = size_i * net_flat_i. Equity still compounds
sequentially (eq *= (1 + net_i)) exactly as backtest.simulate() does; a
size_i above 1.0x is implicitly leveraged relative to the flat book, which is
the mechanism by which "bet more on high conviction" expresses itself here.

Look-ahead note: normalizing by a full-sample statistic (mean |score| across
the whole traded set, computed with hindsight over all 268 events) is itself
mild look-ahead - small at this N, but stated rather than glossed over,
matching how every other look-ahead risk in this project has been handled
(e.g. the Extension 1 freeze note, the news-digest leakage fixes).

Run: python -m experiments.extension4_conviction_sizing
"""
from __future__ import annotations

import csv
from pathlib import Path
from statistics import mean, median, pstdev, quantiles

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from backtest import OUTPUTS_DIR, Prediction, _decision_to_position, overnight_gap, simulate
from blend import DEFAULT_WEIGHTS, blend_scores, derive_signal
from bootstrap_stats import bootstrap_paired_difference, bootstrap_trade_stats

PHASE2_CALIBRATION_CSV = OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration_phase2.csv"
RESULTS_CSV = OUTPUTS_DIR / "global" / "summary" / "ext4_conviction_sizing.csv"
DIST_PNG = OUTPUTS_DIR / "global" / "summary" / "ext4_score_distribution.png"


def _num(x):
    if x is None or x == "":
        return None
    return float(x)


def load_events(path: Path = PHASE2_CALIBRATION_CSV) -> list[dict]:
    events = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            micro = _num(r["micro_score"])
            if micro is None:
                continue  # micro is the anchor layer, never missing in practice
            macro = _num(r["macro_score"])
            news = _num(r["news_score"])
            quant = _num(r["quant_score"])
            score = blend_scores(micro, macro, news, quant, weights=DEFAULT_WEIGHTS)
            decision = derive_signal(score)
            if decision != r["blend_predicted_signal_default"]:
                raise AssertionError(
                    f"{r['document_id']}: recomputed decision {decision} != "
                    f"CSV blend_predicted_signal_default {r['blend_predicted_signal_default']}"
                )
            events.append({
                "document_id": r["document_id"], "ticker": r["ticker"],
                "report_date": r["report_date"], "decision": decision, "score": score,
            })
    return events


def score_distribution(events: list[dict]) -> dict:
    abs_scores = sorted(abs(e["score"]) for e in events)
    q = quantiles(abs_scores, n=4)
    return {
        "n": len(abs_scores), "mean": mean(abs_scores), "median": median(abs_scores),
        "stdev": pstdev(abs_scores), "min": abs_scores[0], "max": abs_scores[-1],
        "q1": q[0], "q3": q[2],
    }


def plot_score_distribution(events: list[dict], stats: dict, path: Path = DIST_PNG):
    abs_scores = [abs(e["score"]) for e in events]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(abs_scores, bins=20, color="#2b6cb0", alpha=0.75, edgecolor="white")
    ax.axvline(stats["mean"], color="black", linestyle="-", linewidth=1.5,
                label=f"mean={stats['mean']:.3f}")
    ax.axvline(stats["median"], color="black", linestyle="--", linewidth=1.2,
                label=f"median={stats['median']:.3f}")
    ax.set_xlabel("|blended score| (0 = neutral, 1 = max conviction)")
    ax.set_ylabel("n events")
    ax.set_title(f"Distribution of |blended score|, N={stats['n']} phase2 events")
    ax.legend()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Wrote chart -> {path}")


def to_predictions(events: list[dict]) -> list[Prediction]:
    return [Prediction(rater="LLM (DeepSeek)", kind="LM", ticker=e["ticker"],
                        report_date=e["report_date"], decision=e["decision"])
            for e in events]


def simulate_sized(events: list[dict], cost_bps: float = 10.0, short_borrow_bps: float = 0.0) -> dict:
    """Replicates backtest.simulate()'s net-return math with a per-trade size
    multiplier (net_sized = size * net_flat). See module docstring for why
    this isn't a backtest.simulate() signature change."""
    raw = []
    for e in events:
        pred = Prediction(rater="LLM (DeepSeek)", kind="LM", ticker=e["ticker"],
                           report_date=e["report_date"], decision=e["decision"])
        gap = overnight_gap(pred)
        if gap is None:
            continue
        pos = _decision_to_position(e["decision"])
        raw.append({**e, "gap": gap, "pos": pos})

    traded = [r for r in raw if r["pos"] != 0]
    mean_abs_score = mean(abs(r["score"]) for r in traded)

    rows = []
    sizes = []
    for r in raw:
        pos, gap = r["pos"], r["gap"]
        if pos == 0:
            size, gross, cost, net = 0.0, 0.0, 0.0, 0.0
        else:
            size = abs(r["score"]) / mean_abs_score
            sizes.append(size)
            gross = pos * gap * size
            cost = (cost_bps / 1e4 + (short_borrow_bps / 1e4 if pos < 0 else 0.0)) * size
            net = gross - cost
        rows.append({**r, "size": size, "gross": gross, "cost": cost, "net": net})
    rows.sort(key=lambda r: r["report_date"])

    trades = [r for r in rows if r["pos"] != 0]
    equity, eq = [], 1.0
    peak, max_dd = 1.0, 0.0
    for r in rows:
        eq *= (1.0 + r["net"])
        equity.append((r["report_date"], r["ticker"], r["decision"], round(r["gap"], 4),
                       round(r["size"], 4), round(r["net"], 4), round(eq, 4)))
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak)

    nets = [r["net"] for r in trades]
    wins = sum(1 for r in trades if r["net"] > 0)
    losses = sum(1 for r in trades if r["net"] < 0)
    _sd_sized = pstdev(nets) if len(nets) > 1 else 0.0
    t_statistic = (mean(nets) / _sd_sized * (len(nets) ** 0.5)) if _sd_sized > 0 else 0.0

    return {
        "n_prints": len(rows), "n_trades": len(trades),
        "hit_rate": round(wins / len(trades), 4) if trades else 0.0,
        "wins": wins, "losses": losses,
        "compounded_total_return_pct": round((eq - 1.0) * 100, 2),
        "total_return_pct": round((eq - 1.0) * 100, 2),  # backward-compat alias
        "avg_net_per_trade_pct": round(mean(nets) * 100, 4) if nets else 0.0,
        "t_statistic": round(t_statistic, 3),
        "sharpe_per_trade": round(t_statistic, 3),  # backward-compat alias
        "max_drawdown_pct": round(max_dd * 100, 2),
        "mean_abs_score_norm": mean_abs_score,
        "size_min": min(sizes), "size_max": max(sizes), "size_mean": mean(sizes),
        "equity": equity, "trade_nets": nets,
        "document_order": [r["document_id"] for r in trades],
    }


def write_results_csv(flat: dict, sized: dict, dist: dict, path: Path = RESULTS_CSV):
    fields = ["book", "n_trades", "n_prints", "hit_rate", "compounded_total_return_pct",
              "avg_net_per_trade_pct", "t_statistic", "max_drawdown_pct",
              "wins", "losses", "size_min", "size_max", "size_mean",
              "mean_abs_score_norm", "score_dist_mean", "score_dist_median",
              "score_dist_stdev", "score_dist_min", "score_dist_max",
              "score_dist_q1", "score_dist_q3"]
    rows = []
    for name, s in (("flat", flat), ("sized", sized)):
        rows.append({
            "book": name, "n_trades": s["n_trades"], "n_prints": s["n_prints"],
            "hit_rate": s["hit_rate"], "compounded_total_return_pct": s["compounded_total_return_pct"],
            "avg_net_per_trade_pct": s["avg_net_per_trade_pct"],
            "t_statistic": s["t_statistic"], "max_drawdown_pct": s["max_drawdown_pct"],
            "wins": s["wins"], "losses": s["losses"],
            "size_min": s.get("size_min", 1.0), "size_max": s.get("size_max", 1.0),
            "size_mean": s.get("size_mean", 1.0),
            "mean_abs_score_norm": s.get("mean_abs_score_norm", ""),
            "score_dist_mean": round(dist["mean"], 4), "score_dist_median": round(dist["median"], 4),
            "score_dist_stdev": round(dist["stdev"], 4), "score_dist_min": round(dist["min"], 4),
            "score_dist_max": round(dist["max"], 4), "score_dist_q1": round(dist["q1"], 4),
            "score_dist_q3": round(dist["q3"], 4),
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {path}")


def main() -> int:
    events = load_events()
    print(f"Loaded {len(events)} events, decisions cross-checked against "
          f"blend_predicted_signal_default (locked decision, matches Item 6's convention)")

    dist = score_distribution(events)
    print(f"\n|score| distribution (N={dist['n']}): mean={dist['mean']:.4f} "
          f"median={dist['median']:.4f} stdev={dist['stdev']:.4f} "
          f"min={dist['min']:.4f} max={dist['max']:.4f} "
          f"IQR=[{dist['q1']:.4f}, {dist['q3']:.4f}]")
    plot_score_distribution(events, dist)

    flat_preds = to_predictions(events)
    flat = simulate(flat_preds, cost_bps=10.0, short_borrow_bps=0.0)
    print(f"\nFlat book:  n_trades={flat['n_trades']}/{flat['n_prints']}  "
          f"total_return={flat['compounded_total_return_pct']:+.2f}%  hit_rate={flat['hit_rate']*100:.1f}%  "
          f"t_stat={flat['t_statistic']:.3f}  max_dd={flat['max_drawdown_pct']:.2f}%")

    sized = simulate_sized(events, cost_bps=10.0, short_borrow_bps=0.0)
    print(f"Sized book: n_trades={sized['n_trades']}/{sized['n_prints']}  "
          f"total_return={sized['compounded_total_return_pct']:+.2f}%  hit_rate={sized['hit_rate']*100:.1f}%  "
          f"t_stat={sized['t_statistic']:.3f}  max_dd={sized['max_drawdown_pct']:.2f}%  "
          f"(size range {sized['size_min']:.3f}x-{sized['size_max']:.3f}x, mean {sized['size_mean']:.3f}x, "
          f"norm mean|score|={sized['mean_abs_score_norm']:.4f})")

    write_results_csv(flat, sized, dist)

    # paired bootstrap on mean-net-per-trade (flat vs sized, same trades,
    # joined by ticker+report_date) - see bootstrap_stats.py's paired-vs-unpaired note
    flat_sim = simulate(flat_preds, cost_bps=10.0, short_borrow_bps=0.0)
    flat_net_by_doc = {}
    doc_by_ticker_date = {(e["ticker"], e["report_date"]): e["document_id"] for e in events}
    for row in flat_sim["equity"]:
        rd, tk, dec, gap, net, eq = row
        if dec.upper() in ("BUY", "SELL"):
            did = doc_by_ticker_date.get((tk, rd))
            if did:
                flat_net_by_doc[did] = net
    sized_net_by_doc = dict(zip(sized["document_order"], sized["trade_nets"]))
    common = [d for d in sized["document_order"] if d in flat_net_by_doc]
    flat_paired = [flat_net_by_doc[d] for d in common]
    sized_paired = [sized_net_by_doc[d] for d in common]
    if len(common) == len(sized["document_order"]):
        paired = bootstrap_paired_difference(sized_paired, flat_paired)
        print(f"\nPaired bootstrap (sized - flat) mean-net-per-trade, n={paired['n']}: "
              f"diff={paired['point_diff']*100:+.4f}pp  "
              f"CI=[{paired['ci_low']*100:+.4f}pp, {paired['ci_high']*100:+.4f}pp]  "
              f"p={paired['p_value']:.4f}")
        # Save paired bootstrap to CSV
        paired_csv = OUTPUTS_DIR / "global" / "summary" / "ext4_paired_bootstrap.csv"
        with open(paired_csv, "w", newline="") as pf:
            pw = csv.writer(pf)
            pw.writerow(["metric", "value"])
            pw.writerow(["n_paired_trades", paired["n"]])
            pw.writerow(["point_diff_pct", f"{paired['point_diff']*100:+.4f}"])
            pw.writerow(["ci_low_pct", f"{paired['ci_low']*100:+.4f}"])
            pw.writerow(["ci_high_pct", f"{paired['ci_high']*100:+.4f}"])
            pw.writerow(["p_value", f"{paired['p_value']:.4f}"])
        print(f"  Saved -> {paired_csv}")
    else:
        print(f"\nSkipped paired bootstrap: joined {len(common)}/{len(sized['document_order'])} trades "
              "(ticker/date collision in the join key) - see CSV for the point comparison only.")

    flat_total_return = bootstrap_trade_stats(list(flat_net_by_doc.values()))
    print(f"\nFlat total-return bootstrap:  point={flat_total_return['total_return']['point']*100:+.2f}%  "
          f"CI=[{flat_total_return['total_return']['ci_low']*100:+.2f}%, "
          f"{flat_total_return['total_return']['ci_high']*100:+.2f}%]")
    sized_total_return = bootstrap_trade_stats(sized["trade_nets"])
    print(f"Sized total-return bootstrap: point={sized_total_return['total_return']['point']*100:+.2f}%  "
          f"CI=[{sized_total_return['total_return']['ci_low']*100:+.2f}%, "
          f"{sized_total_return['total_return']['ci_high']*100:+.2f}%]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
