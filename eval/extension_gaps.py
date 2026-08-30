"""Extension overnight gaps — the writer the artefact never had.

`outputs/global/summary/backtest_equity_extension_2026_08_13.csv` carries the 93
extension events' overnight gaps and is read by four experiments
(`lm_baseline_extension`, `finbert_extension`, `section_ablation_extension`,
`walkforward_combined`). Nothing in the repo writes it, so when PR #8 corrected
Duke Energy's `release_timing` from `after_hours` to `pre_market` the 13 Duke
gaps could not follow, and the file began to disagree with the group workbook.

This module derives the gaps the way `eval/return_matrix.py` derives the frozen
set's `ret_overnight`: entry session chosen by the manifest's `release_timing`,
then that session's close to the next session's open, prices from yfinance with
`auto_adjust=False`. It writes a NEW dated file and never touches the 2026_08_13
vintage, which stays as the record.

TWO THINGS THAT ARE NOT LIKE THE FROZEN SET, both measured before this was written:

1. THE ANCHOR IS `report_date`, NOT `release_date`.
   `return_matrix.py` line 315 uses `release_date or report_date`. The extension
   cannot: 13 of the 93 events carry `release_date: "PENDING - source from
   home-exchange announcement"` and 7 more carry null. It was 17 until the four
   Hermes events were resolved to their own datelines on 2026-08-24. Rebuilding on the
   `report_date` anchor reproduces the committed 2026_08_13 file on 89 of 93 rows
   and agrees with the live workbook's `LLM_Data_Entry!P` on 90 of 93. Rebuilding
   on the resolved release dates agrees with the workbook on 75. The extension is
   internally consistent on `report_date`; moving it is a separate decision.
   `--anchor release_date` runs that variant and is not the default.

2. 13 OF THE 17 NON-US EVENTS STILL CARRY A FIRST-OF-MONTH PLACEHOLDER `report_date`.
   Heineken 2024-03-01, Nestle 2024-10-01, Shell 2025-08-01, Sony 2025-11-01 and
   so on. The four Hermes events were corrected on 2026-08-24 to the dateline
   printed on each cited press release; `GATE_REPORT_DATES` pins their old values
   so the gate still rebuilds the 2026-08-13 vintage. Their real release dates
   were established on
   2026-08-13 and live in `non_us_release_timing_extension.csv`, which nothing
   reads. Both arms were built on the placeholder, which is why the extension
   agrees with itself. `--anchor release_date` reads that file.

REPRODUCE FIRST. The script refuses to write until it has rebuilt the committed
2026_08_13 artefact at the constants and timings of that date - Duke
`after_hours`, blend (0.55, 0.45) at (+0.25, -0.05) - and confirmed that the
decision column reproduces on all 93 rows and the gap column on at least 89. The
reference is the committed CSV itself, a file this script never writes.

Usage:
    python -m eval.extension_gaps                      # dated today, report_date anchor
    python -m eval.extension_gaps --suffix 2026_08_22
    python -m eval.extension_gaps --anchor release_date --suffix 2026_08_22_reldate
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from blend import (DEFAULT_HOLD_LOWER, DEFAULT_HOLD_UPPER,  # noqa: E402
                   DEFAULT_WEIGHTS, blend_scores, derive_signal)

SUMMARY = BASE_DIR / "outputs" / "global" / "summary"
ROSTER = SUMMARY / "global_outcome_calibration_extension_2026_08_13.csv"
REFERENCE = SUMMARY / "backtest_equity_extension_2026_08_13.csv"
NON_US = SUMMARY / "non_us_release_timing_extension.csv"
MANIFESTS = BASE_DIR / "manifests"

COST_BPS = 10.0          # Settings!B4, round trip
SHORT_BORROW_BPS = 0.0   # Settings!B5
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# The gate rebuilds the reference at the state of 2026-08-13. Duke's manifest said
# after_hours then; PR #8 corrected it to pre_market on 2026-08-21. The constants
# were master's. None of these three are read by the live path below.
GATE_DUKE_TIMING = "after_hours"
GATE_WEIGHTS = (0.55, 0.45, 0.0, 0.0)
GATE_BAND = (0.25, -0.05)
GATE_MIN_GAP_MATCHES = 89   # measured; the residue is named in the output

# The four Hermes events carried a first-of-month placeholder `report_date` on
# 2026-08-13 and were corrected to each document's own dateline on 2026-08-24.
# The gate rebuilds a 2026-08-13 artefact, so it has to keep using the values that
# artefact was built from - the same reason GATE_DUKE_TIMING pins Duke's superseded
# `release_timing`. Pinning them keeps the guard testing the code path rather than
# the data. Without it the reference lookup, which is keyed on
# (ticker, report_date), misses on all four and the gate aborts.
GATE_REPORT_DATES = {
    "RMS_FQ1_2025": "2025-02-01",
    "RMS_FQ2_2025": "2025-07-01",
    "RMS_FQ3_2025": "2025-10-01",
    "RMS_FQ4_2025": "2026-02-01",
}

# THE ONE PLACE THAT SAYS WHICH VINTAGE IS CURRENT.
# Four experiments read this file - lm_baseline_extension, finbert_extension,
# section_ablation_extension, walkforward_combined - and until now each carried its
# own copy of the filename, so a new vintage meant four edits or none. They import
# this. Point it at a new file in the same commit that writes one.
CURRENT_GAP_FILE = SUMMARY / "backtest_equity_extension_2026_08_24.csv"
LLM_RATER = "LLM (DeepSeek)"


# ── inputs ───────────────────────────────────────────────────────────────────
def load_roster() -> list[dict]:
    with ROSTER.open() as fh:
        return list(csv.DictReader(fh))


def load_reports() -> dict[str, dict]:
    """document_id -> the manifest report entry, plus its issuer's release_timing."""
    out: dict[str, dict] = {}
    for path in glob.glob(str(MANIFESTS / "*.json")):
        data = json.loads(Path(path).read_text())
        timing = (data.get("release_timing") or {}).get("value")
        for rep in data.get("reports", []):
            out[rep["document_id"]] = dict(rep, issuer=data.get("issuer"),
                                           release_timing=timing)
    return out


def load_non_us() -> dict[str, str]:
    """document_id -> resolved release date, from the 2026-08-13 capture sheet."""
    if not NON_US.exists():
        return {}
    lines = [ln for ln in NON_US.read_text().splitlines() if not ln.startswith("#")]
    return {r["document_id"]: r["release_date"] for r in csv.DictReader(lines)
            if ISO.match(r["release_date"])}


def fetch_histories(tickers) -> dict[str, pd.DataFrame]:
    hist = {}
    for t in sorted(tickers):
        h = yf.Ticker(t).history(start="2022-12-01", end="2026-09-01", auto_adjust=False)
        if h.empty:
            raise SystemExit(f"no price history for {t}")
        h = h.copy()
        h.index = pd.to_datetime(h.index).tz_localize(None)
        hist[t] = h
        print(f"    {t:9s} {len(h):4d} sessions  {h.index.min().date()}..{h.index.max().date()}")
    return hist


# ── the gap ──────────────────────────────────────────────────────────────────
def entry_index(hist: pd.DataFrame, anchor: str, release_timing: str) -> int | None:
    """The same rule as eval/return_matrix.py::_find_entry_idx."""
    if release_timing is None:
        raise ValueError(f"release_timing is None for anchor {anchor}")
    if release_timing == "intraday":
        raise ValueError(f"release_timing is 'intraday' for anchor {anchor}")
    d = pd.Timestamp(anchor)
    if release_timing == "pre_market":
        mask = hist.index < d
        return int(np.nonzero(mask)[0][-1]) if mask.any() else None
    mask = hist.index >= d
    return int(np.argmax(mask)) if mask.any() else None


def overnight_gap(hist, anchor, timing):
    i = entry_index(hist, anchor, timing)
    if i is None or i + 1 >= len(hist):
        return None, None, None
    close = float(hist.iloc[i]["Close"])
    nxt_open = float(hist.iloc[i + 1]["Open"])
    if close == 0:
        return None, None, None
    return (nxt_open - close) / close, str(hist.index[i].date()), str(hist.index[i + 1].date())


def anchor_for(rep: dict, non_us: dict, mode: str) -> str:
    if mode == "report_date":
        return rep["report_date"]
    if rep["document_id"] in non_us:
        return non_us[rep["document_id"]]
    rd = str(rep.get("release_date") or "")
    return rd if ISO.match(rd) else rep["report_date"]


def build(roster, reports, hist, non_us, mode, weights, band, duke_timing=None,
          report_dates=None):
    """One row per event: decision at `weights`/`band`, gap on `mode`'s anchor.

    `report_dates` pins `report_date` for named events, so the gate can rebuild a
    past vintage after the manifest has moved on. It replaces the entry rather
    than editing it, leaving `reports` as loaded.
    """
    rows, exceptions = [], []
    for r in roster:
        doc = r["document_id"]
        rep = reports[doc]
        if report_dates and doc in report_dates:
            rep = dict(rep, report_date=report_dates[doc])
        timing = rep["release_timing"]
        if duke_timing and rep["issuer"] == "p2_duke_energy":
            timing = duke_timing
        anchor = anchor_for(rep, non_us, mode)

        def num(key):
            v = r[key]
            return float(v) if v not in ("", None) else None

        blended = blend_scores(num("micro_score"), num("macro_score"),
                               num("news_score"), num("quant_score"), weights)
        decision = derive_signal(blended, band[0], band[1])
        gap, entry_date, exit_date = overnight_gap(hist[rep["ticker"]], anchor, timing)
        if gap is None:
            exceptions.append(dict(document_id=doc, ticker=rep["ticker"], anchor=anchor,
                                   reason="no session pair resolved"))
            continue
        h = hist[rep["ticker"]]
        i = entry_index(h, anchor, timing)
        entry_flat = float(h.iloc[i]["Open"]) == float(h.iloc[i]["Close"])
        if gap == 0.0 or entry_flat:
            exceptions.append(dict(
                document_id=doc, ticker=rep["ticker"], anchor=anchor,
                reason=("entry close == next open" if gap == 0.0 else "")
                       + ("; " if gap == 0.0 and entry_flat else "")
                       + ("entry session open == close" if entry_flat else "")
                       + " - the vendor series does not move across this window, so the "
                         "gap is a stale quote rather than a measured reaction"))
        rows.append(dict(document_id=doc, rater="LLM (DeepSeek)", report_date=rep["report_date"],
                         ticker=rep["ticker"], decision=decision, gap=round(gap, 4),
                         entry_date=entry_date, exit_date=exit_date, anchor=anchor,
                         release_timing=timing))
    # chronological, like the 2026_08_13 vintage: `equity` is a running product and
    # is only readable as a curve if the rows are in time order.
    rows.sort(key=lambda r: (r["report_date"], r["ticker"]))
    return rows, exceptions


def with_equity(rows, decision_of):
    """net and the running equity product, per arm. Matches the committed file."""
    out, equity = [], 1.0
    for r in rows:
        d = decision_of(r)
        pos = {"BUY": 1, "SELL": -1, "HOLD": 0}[d]
        net = pos * r["gap"] - (COST_BPS / 1e4 if pos else 0.0)
        if pos < 0:
            net -= SHORT_BORROW_BPS / 1e4
        equity *= 1 + net
        out.append(dict(r, decision=d, net=round(net, 6), equity=round(equity, 7)))
    return out


# ── the gate ─────────────────────────────────────────────────────────────────
def gate(roster, reports, hist, non_us) -> None:
    ref = {(r["ticker"], r["report_date"]): r for r in
           csv.DictReader(REFERENCE.open()) if r["rater"] == "LLM (DeepSeek)"}
    rows, _ = build(roster, reports, hist, non_us, "report_date",
                    GATE_WEIGHTS, GATE_BAND, duke_timing=GATE_DUKE_TIMING,
                    report_dates=GATE_REPORT_DATES)
    dec_ok = gaps_ok = 0
    dec_bad, gap_bad = [], []
    for r in rows:
        c = ref.get((r["ticker"], r["report_date"]))
        if c is None:
            dec_bad.append((r["document_id"], "not in the reference"))
            continue
        if c["decision"] == r["decision"]:
            dec_ok += 1
        else:
            dec_bad.append((r["document_id"], r["decision"], c["decision"]))
        # the reference stores 4 dp; allow one unit in the last place for vendor drift
        if abs(r["gap"] - float(c["gap"])) <= 1.01e-4:
            gaps_ok += 1
        else:
            gap_bad.append((r["document_id"], r["gap"], float(c["gap"])))
    print(f"  gate: decisions reproduce {dec_ok}/{len(rows)}, "
          f"gaps reproduce {gaps_ok}/{len(rows)} within one unit of the 4th decimal")
    for x in gap_bad:
        print(f"        gap residue {x[0]}: rebuilt {x[1]} vs committed {x[2]}")
    for x in dec_bad:
        print(f"        DECISION residue {x}")
    if dec_ok != len(rows):
        raise SystemExit("aborted: the decision column does not reproduce at the "
                         "2026-08-13 constants, so this code path cannot be trusted "
                         "to replace the artefact")
    if gaps_ok < GATE_MIN_GAP_MATCHES:
        raise SystemExit(f"aborted: only {gaps_ok} gaps reproduce, expected at least "
                         f"{GATE_MIN_GAP_MATCHES}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suffix", default=date.today().strftime("%Y_%m_%d"))
    ap.add_argument("--anchor", choices=("report_date", "release_date"), default="report_date")
    args = ap.parse_args()

    out_csv = SUMMARY / f"backtest_equity_extension_{args.suffix}.csv"
    exc_csv = SUMMARY / f"backtest_equity_extension_exceptions_{args.suffix}.csv"
    if out_csv.resolve() == REFERENCE.resolve():
        raise SystemExit("refusing to overwrite the 2026_08_13 vintage; pick another suffix")

    roster = load_roster()
    reports = load_reports()
    non_us = load_non_us()
    missing = [r["document_id"] for r in roster if r["document_id"] not in reports]
    if missing:
        raise SystemExit(f"{len(missing)} roster events have no manifest entry: {missing[:5]}")
    print(f"roster {len(roster)} events; {len(non_us)} non-US release dates resolved")
    print("  fetching price history")
    hist = fetch_histories({reports[r["document_id"]]["ticker"] for r in roster})

    print("\nreproduce first, against the committed 2026_08_13 artefact")
    gate(roster, reports, hist, non_us)

    print(f"\nbuilding at blend {DEFAULT_WEIGHTS} band "
          f"(+{DEFAULT_HOLD_UPPER}, {DEFAULT_HOLD_LOWER}), anchor = {args.anchor}")
    rows, exceptions = build(roster, reports, hist, non_us, args.anchor,
                             DEFAULT_WEIGHTS, (DEFAULT_HOLD_UPPER, DEFAULT_HOLD_LOWER))
    arms = [("LLM (DeepSeek)", lambda r: r["decision"]),
            ("baseline: always-long", lambda r: "BUY"),
            ("baseline: always-flat", lambda r: "HOLD")]
    # No comment header. The four consumers hand this file straight to
    # csv.DictReader, so a leading "#" line would become the column row and every
    # gap would be dropped by their `except (ValueError, KeyError): pass`. The
    # provenance goes in a sidecar instead.
    with out_csv.open("w", newline="") as fh:
        w = csv.writer(fh)
        # document_id is appended, not inserted, so any positional reader of the
        # first seven columns keeps working. The four consumers join on it: the
        # calibration roster is a frozen 2026-08-13 artefact whose report_date
        # column still holds the first-of-month placeholders, so a date-keyed join
        # drops every event whose anchor has since been corrected.
        w.writerow(["rater", "report_date", "ticker", "decision", "gap", "net",
                    "equity", "document_id"])
        for name, fn in arms:
            for r in with_equity(rows, fn):
                w.writerow([name, r["report_date"], r["ticker"], r["decision"],
                            r["gap"], r["net"], r["equity"], r["document_id"]])
    prov = out_csv.with_suffix(".provenance.md")
    prov.write_text(
        f"# {out_csv.name}\n\n"
        f"Written by `eval/extension_gaps.py` on {date.today()}.\n\n"
        f"- blend weights `{DEFAULT_WEIGHTS}`, band `(+{DEFAULT_HOLD_UPPER}, "
        f"{DEFAULT_HOLD_LOWER})` - read from `blend.py`, never hard-coded here\n"
        f"- entry anchor: `{args.anchor}`; entry session chosen by the manifest's "
        f"`release_timing`; gap = entry close -> next session open\n"
        f"- cost {COST_BPS} bps round trip, short borrow {SHORT_BORROW_BPS} bps\n"
        f"- {len(rows)} events x {len(arms)} arms\n"
        f"- keyed on `document_id` (added 2026-08-24); consumers must join on it,\n"
        f"  not on `(ticker, report_date)`, which moves when an anchor is corrected\n"
        f"- {len(exceptions)} exception(s), listed in `{exc_csv.name}`\n\n"
        f"Supersedes `backtest_equity_extension_2026_08_13.csv`, which stays as the\n"
        f"record and which this script reproduces at that date's constants before it\n"
        f"is allowed to write. The CSV carries no comment header on purpose: its four\n"
        f"consumers pass the handle straight to `csv.DictReader`.\n")
    with exc_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["document_id", "ticker", "anchor", "reason"])
        w.writeheader()
        w.writerows(exceptions)
    print(f"wrote {out_csv.name}  ({len(rows)} events x {len(arms)} arms)")
    print(f"wrote {prov.name}")
    print(f"wrote {exc_csv.name}  ({len(exceptions)} exception(s))")
    for e in exceptions:
        print(f"    {e['document_id']:16s} {e['reason']}")
    print("\nRE-RUN THESE, they all read the gap file: lm_baseline_extension, "
          "finbert_extension, section_ablation_extension, walkforward_combined")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
