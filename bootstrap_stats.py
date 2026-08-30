"""
bootstrap_stats.py
Shared bootstrap/resampling infra for the model-arm robustness items. Nothing
downstream should implement its own resampling loop - import from here so every
CI/interval in the write-up comes from the same convention.

Four functions:
  - bootstrap_trade_stats: point estimate + percentile interval for a single
    arm's total return, mean/trade, hit rate and t_statistic, all drawn from
    ONE shared resample stream so the four numbers stay mutually consistent
    within a draw (never resample each statistic separately - that lets them
    tell inconsistent stories about the same draw).
  - bootstrap_paired_difference: for a same-length, same-event-order pair of
    arrays (e.g. macro-on-correct vs macro-off-correct on identical events) -
    resamples the per-event difference directly, which is far tighter than
    two overlapping single-arm intervals at this sample size.
  - bootstrap_unpaired_difference: for two DIFFERENT sets of events (e.g.
    BUY-truth events vs SELL-truth events) - resamples each group
    independently since there's no natural pairing between them.
  - bootstrap_clustered_by_week: resamples whole ISO (year, week) clusters of
    report dates rather than individual events, since same-week reporters
    share a market factor and aren't independent draws. Wider than the plain
    interval by construction - that's the honest number, not a bug.

Total return uses the log-space product trick (np.expm1(np.log1p(x).sum())),
matching experiments/pnl_weight_threshold_sweep.py's total_return_from_net()
convention. The ``t_statistic`` field (mean/pstdev * sqrt(N)) matches
backtest.py's convention; it is NOT a time-series Sharpe ratio.
RNG_SEED matches the project's existing sweep-script convention.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Callable, Sequence

import numpy as np

RNG_SEED = 20260709
DEFAULT_N_RESAMPLES = 10_000
DEFAULT_CI = (5, 95)


def _total_return(net_matrix: np.ndarray) -> np.ndarray:
    """net_matrix: (n_resamples, n_trades). Order-invariant product-of-(1+net)
    total return per resample row, in log-space for stability."""
    return np.expm1(np.log1p(net_matrix).sum(axis=1))


def _t_statistic(net_matrix: np.ndarray) -> np.ndarray:
    """Per-resample-row t-statistic: mean/pstdev * sqrt(N), matching backtest.py's
    ``t_statistic`` formula exactly.  This is NOT a time-series Sharpe ratio — it
    grows mechanically with sqrt(N).  Rows with zero variance or fewer than 2
    trades score 0.0 (same convention as backtest.simulate)."""
    n = net_matrix.shape[1]
    if n < 2:
        return np.zeros(net_matrix.shape[0])
    mean = net_matrix.mean(axis=1)
    std = net_matrix.std(axis=1, ddof=0)
    t_stat = np.zeros_like(mean)
    nonzero = std > 0
    t_stat[nonzero] = mean[nonzero] / std[nonzero] * np.sqrt(n)
    return t_stat


# Keep old name as an alias so external callers are not broken
_sharpe = _t_statistic


def bootstrap_trade_stats(
    net_returns: Sequence[float],
    n_resamples: int = DEFAULT_N_RESAMPLES,
    seed: int = RNG_SEED,
    ci: tuple[float, float] = DEFAULT_CI,
) -> dict:
    """Point estimate + percentile CI for total return, mean/trade, hit rate
    and t_statistic (mean/pstdev*sqrt(N)), all drawn from one shared
    (n_resamples, n) index matrix so the four stats stay internally consistent
    within each resample.

    NOTE: ``t_statistic`` is mean/pstdev * sqrt(N) — a per-trade information
    ratio scaled by sqrt(N).  It grows mechanically with sample size and is
    NOT a time-series Sharpe ratio.
    """
    net = np.asarray(list(net_returns), dtype=float)
    n = len(net)
    if n == 0:
        raise ValueError("bootstrap_trade_stats: empty net_returns")

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_resamples, n))
    res = net[idx]  # (n_resamples, n)

    total_return = _total_return(res)
    mean_per_trade = res.mean(axis=1)
    hit_rate = (res > 0).mean(axis=1)
    t_stat = _t_statistic(res)

    def _point_ci(point_val, dist):
        lo, hi = np.percentile(dist, ci)
        return {"point": float(point_val), "ci_low": float(lo), "ci_high": float(hi)}

    return {
        "n": n,
        "n_resamples": n_resamples,
        "seed": seed,
        "ci_bounds": ci,
        "total_return": _point_ci(_total_return(net[None, :])[0], total_return),
        "mean_per_trade": _point_ci(net.mean(), mean_per_trade),
        "hit_rate": _point_ci((net > 0).mean(), hit_rate),
        "t_statistic": _point_ci(_t_statistic(net[None, :])[0], t_stat),
        # Backward-compatibility alias so existing code reading ["sharpe"] still works
        "sharpe": _point_ci(_t_statistic(net[None, :])[0], t_stat),
    }


def bootstrap_paired_difference(
    values_a: Sequence[float],
    values_b: Sequence[float],
    stat_fn: Callable[[np.ndarray], np.ndarray] = None,
    n_resamples: int = DEFAULT_N_RESAMPLES,
    seed: int = RNG_SEED,
    ci: tuple[float, float] = DEFAULT_CI,
) -> dict:
    """values_a/values_b MUST be same length and same event order (paired).
    Resamples the per-event difference (a[i]-b[i]) directly with one shared
    index stream - far more powerful than two overlapping single-arm
    intervals at small n, since event-to-event variation cancels out.

    stat_fn defaults to mean (e.g. accuracy = mean of a 0/1 correctness
    array). It's applied to the resampled diff array itself, not to a and b
    separately, so it must accept a (n_resamples, n) matrix and return a
    (n_resamples,) vector - the default does exactly that."""
    a = np.asarray(list(values_a), dtype=float)
    b = np.asarray(list(values_b), dtype=float)
    if a.shape != b.shape:
        raise ValueError(f"bootstrap_paired_difference: shape mismatch {a.shape} vs {b.shape}")
    n = len(a)
    if n == 0:
        raise ValueError("bootstrap_paired_difference: empty input")

    diff = a - b
    if stat_fn is None:
        stat_fn = lambda m: m.mean(axis=1)

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_resamples, n))
    res = diff[idx]  # (n_resamples, n)
    dist = stat_fn(res)

    point = float(diff.mean())
    lo, hi = np.percentile(dist, ci)
    # two-sided p-value: fraction of the resampled distribution on the far
    # side of zero from the point estimate, doubled (standard bootstrap
    # percentile convention), capped at 1.0
    if point >= 0:
        p_one_sided = float((dist <= 0).mean())
    else:
        p_one_sided = float((dist >= 0).mean())
    p_value = min(1.0, 2 * p_one_sided)

    return {
        "n": n,
        "n_resamples": n_resamples,
        "seed": seed,
        "ci_bounds": ci,
        "point_diff": point,
        "ci_low": float(lo),
        "ci_high": float(hi),
        "p_value": p_value,
    }


def bootstrap_unpaired_difference(
    group_a: Sequence[float],
    group_b: Sequence[float],
    stat_fn: Callable[[np.ndarray], np.ndarray] = None,
    n_resamples: int = DEFAULT_N_RESAMPLES,
    seed: int = RNG_SEED,
    ci: tuple[float, float] = DEFAULT_CI,
) -> dict:
    """For two DIFFERENT sets of events with no natural pairing (e.g.
    BUY-truth events vs SELL-truth events). Resamples each group
    independently n_resamples times, then differences the per-draw
    statistics. stat_fn defaults to mean, applied per-group per-draw."""
    a = np.asarray(list(group_a), dtype=float)
    b = np.asarray(list(group_b), dtype=float)
    n_a, n_b = len(a), len(b)
    if n_a == 0 or n_b == 0:
        raise ValueError("bootstrap_unpaired_difference: empty group")

    if stat_fn is None:
        stat_fn = lambda m: m.mean(axis=1)

    rng = np.random.default_rng(seed)
    idx_a = rng.integers(0, n_a, size=(n_resamples, n_a))
    idx_b = rng.integers(0, n_b, size=(n_resamples, n_b))
    dist_a = stat_fn(a[idx_a])
    dist_b = stat_fn(b[idx_b])
    dist_diff = dist_a - dist_b

    point = float(a.mean() - b.mean())
    lo, hi = np.percentile(dist_diff, ci)
    if point >= 0:
        p_one_sided = float((dist_diff <= 0).mean())
    else:
        p_one_sided = float((dist_diff >= 0).mean())
    p_value = min(1.0, 2 * p_one_sided)

    return {
        "n_a": n_a,
        "n_b": n_b,
        "n_resamples": n_resamples,
        "seed": seed,
        "ci_bounds": ci,
        "point_diff": point,
        "ci_low": float(lo),
        "ci_high": float(hi),
        "p_value": p_value,
    }


def bootstrap_clustered_by_week(
    events: Sequence[dict],
    value_fn: Callable[[list[dict]], dict],
    report_date_key: str = "report_date",
    n_resamples: int = DEFAULT_N_RESAMPLES,
    seed: int = RNG_SEED,
    ci: tuple[float, float] = DEFAULT_CI,
) -> dict:
    """Groups events by ISO (year, week) of report_date_key, then resamples
    WHOLE CLUSTERS with replacement (not individual events), since events
    reporting the same week share a market factor and aren't independent.
    value_fn takes the flattened resampled event list and returns a dict of
    scalar stats (e.g. lambda evs: bootstrap_trade_stats-style point calc) -
    kept generic since callers may want total_return/hit_rate/mean-per-trade
    or something else entirely.

    Not vectorized (ragged cluster sizes per draw) - a plain Python loop over
    n_resamples is fine here since n is small (~130-270 events)."""
    clusters: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for e in events:
        dt = datetime.strptime(e[report_date_key], "%Y-%m-%d")
        iso_year, iso_week, _ = dt.isocalendar()
        clusters[(iso_year, iso_week)].append(e)

    cluster_list = list(clusters.values())
    n_clusters = len(cluster_list)
    if n_clusters == 0:
        raise ValueError("bootstrap_clustered_by_week: no events")

    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n_resamples):
        picks = rng.integers(0, n_clusters, size=n_clusters)
        flat = [e for i in picks for e in cluster_list[i]]
        draws.append(value_fn(flat))

    point = value_fn(list(events))
    keys = point.keys()
    out = {"n_events": len(events), "n_clusters": n_clusters,
           "n_resamples": n_resamples, "seed": seed, "ci_bounds": ci}
    for k in keys:
        dist = np.array([d[k] for d in draws], dtype=float)
        lo, hi = np.percentile(dist, ci)
        out[k] = {"point": float(point[k]), "ci_low": float(lo), "ci_high": float(hi)}
    return out


if __name__ == "__main__":
    # sanity check: a paired difference of an array against itself must be
    # exactly zero with a p-value of 1.0
    sample = [0.01, -0.02, 0.015, 0.0, -0.005, 0.03, -0.01, 0.02]
    same = bootstrap_paired_difference(sample, sample)
    assert abs(same["point_diff"]) < 1e-12, same
    assert same["p_value"] == 1.0, same
    print("Sanity check passed: bootstrap_paired_difference(x, x) == 0, p=1.0")

    stats = bootstrap_trade_stats(sample)
    print(f"bootstrap_trade_stats sanity: total_return point={stats['total_return']['point']:.4f}, "
          f"hit_rate point={stats['hit_rate']['point']:.4f}")
