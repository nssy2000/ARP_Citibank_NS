"""Script 3: read-only rerun of the human-price date cross-validation
(phase2/fix_report_dates_from_human_prices.py's logic, without the final
`report_dates.json` write). Persists the unresolved/ambiguous list to
phase2/audit/report_date_audit.json so the "22 unresolvable combos" claim in
CLAUDE.md has a checked-in artifact backing it, and cross-checks whether any
currently-scored (outputs/p2_*/results/) combo rests on an unresolved or
low-confidence date. Read-only against report_dates.json/manifests/outputs."""
from __future__ import annotations

import json
from collections import Counter

from _common import BASE_DIR, Finding, OUTPUTS_DIR, print_findings

sys_path_marker = None  # keep flake8 quiet about import order below

import importlib.util
import sys

_MODULE_PATH = BASE_DIR / "phase2" / "fix_report_dates_from_human_prices.py"
_spec = importlib.util.spec_from_file_location("_fix_report_dates_ro", _MODULE_PATH)
_fixmod = importlib.util.module_from_spec(_spec)
sys.modules["_fix_report_dates_ro"] = _fixmod
_spec.loader.exec_module(_fixmod)  # safe: only defines functions behind __main__ guard, no import-time side effects


def _scored_tickers_and_periods() -> set[str]:
    """(ticker, year, quarter)-ish keys currently backed by a real scored
    result, derived from outputs/p2_*/results/*.json filenames
    (TICKER_FQ<n>_<year>.json)."""
    keys = set()
    for results_dir in OUTPUTS_DIR.glob("p2_*/results"):
        for f in results_dir.glob("*.json"):
            keys.add(f.stem)
    return keys


def run() -> list[Finding]:
    findings: list[Finding] = []

    report_dates = json.loads(_fixmod.REPORT_DATES_PATH.read_text(encoding="utf-8"))
    human_prices = json.loads(_fixmod.HUMAN_PRICES_PATH.read_text(encoding="utf-8"))

    unresolved: list[str] = []
    ambiguous: list[str] = []
    disagreements: list[str] = []
    no_human_data: list[str] = []
    updated_from_current: list[str] = []

    for key in sorted(report_dates.keys()):
        if key not in human_prices:
            no_human_data.append(key)
            continue
        entries = human_prices[key]
        prior_close, next_day_open, unanimous = _fixmod.consensus_price(entries)
        ticker = key.split("_")[0]
        old_date = report_dates[key]["report_date"]

        if unanimous:
            matches = _fixmod.find_report_date(ticker, prior_close, next_day_open)
        else:
            distinct_pairs = sorted({(round(e["prior_close"], 2), round(e["next_day_open"], 2)) for e in entries})
            pair_matches = {pair: _fixmod.find_report_date(ticker, pair[0], pair[1]) for pair in distinct_pairs}
            validating = {pair: m for pair, m in pair_matches.items() if m}
            if len(validating) == 1:
                (prior_close, next_day_open), matches = next(iter(validating.items()))
                disagreements.append(f"{key}: raters disagreed {distinct_pairs}, only {(prior_close, next_day_open)} validates")
            else:
                disagreements.append(f"{key}: raters disagree {distinct_pairs}, no unique validator")
                matches = _fixmod.find_report_date(ticker, prior_close, next_day_open)

        if len(matches) == 0:
            unresolved.append(f"{key}: no trading day matches human price ${prior_close}->${next_day_open} (current report_date={old_date})")
        elif len(matches) > 1:
            ambiguous.append(f"{key}: {len(matches)} candidate dates {matches} (current report_date={old_date})")
        elif matches[0] != old_date:
            updated_from_current.append(f"{key}: on-disk report_date={old_date} but human-price validation says {matches[0]} - report_dates.json is STALE")

    scored = _scored_tickers_and_periods()

    for u in unresolved:
        key = u.split(":")[0]
        ticker = key.split("_")[0]
        hits = [s for s in scored if s.startswith(ticker + "_")]
        sev = "HIGH" if hits else "MEDIUM"
        findings.append(Finding(sev, "date-unresolved", u + (f" -- SCORED under {hits}" if hits else " -- not currently scored")))

    for a in ambiguous:
        findings.append(Finding("MEDIUM", "date-ambiguous", a))

    for s in updated_from_current:
        findings.append(Finding("HIGH", "date-stale", s))

    for d in disagreements:
        findings.append(Finding("LOW", "rater-price-disagreement", d))

    findings.append(Finding(
        "INFO", "summary",
        f"{len(human_prices)} combos with human price data: "
        f"{len(unresolved)} unresolved, {len(ambiguous)} ambiguous, {len(updated_from_current)} stale-on-disk, "
        f"{len(no_human_data)} with no human price data at all",
    ))

    audit_out = {
        "unresolved": unresolved,
        "ambiguous": ambiguous,
        "stale_on_disk": updated_from_current,
        "disagreements": disagreements,
        "no_human_data": no_human_data,
    }
    out_path = BASE_DIR / "phase2" / "audit" / "report_date_audit.json"
    out_path.write_text(json.dumps(audit_out, indent=2), encoding="utf-8")
    findings.append(Finding("INFO", "artifact", f"wrote {out_path.relative_to(BASE_DIR)}"))

    return findings


if __name__ == "__main__":
    print_findings("Script 3: report_date cross-validation (read-only rerun)", run())
