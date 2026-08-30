"""Script 7: confirm the derived summary artifacts (calibration CSV, backtest
equity CSV, cost ledger) actually reflect the current on-disk state (N=268,
current default weights) rather than a stale pre-Task-9 snapshot, and
reconcile the cost ledger's micro-layer rows against actual scored results
per issuer. Read-only."""
from __future__ import annotations

import csv
import subprocess
from pathlib import Path

from _common import BASE_DIR, Finding, OUTPUTS_DIR, print_findings

TASK9_COMMIT = "e616111"  # "Mark plan Task 9 complete: phase2 eval+backtest rerun at N=268"


def _commit_timestamp(rev: str) -> float:
    out = subprocess.run(
        ["git", "log", "-1", "--format=%ct", rev], cwd=BASE_DIR,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def run() -> list[Finding]:
    findings: list[Finding] = []

    try:
        task9_ts = _commit_timestamp(TASK9_COMMIT)
    except Exception as exc:
        findings.append(Finding("LOW", "git-lookup-failed", f"could not resolve commit {TASK9_COMMIT}: {exc}"))
        task9_ts = None

    summary_dir = OUTPUTS_DIR / "global" / "summary"
    for fname in ("global_outcome_calibration_phase2.csv", "backtest_equity_phase2.csv"):
        path = summary_dir / fname
        if not path.exists():
            findings.append(Finding("HIGH", "missing-artifact", f"{path} does not exist"))
            continue
        with open(path, newline="", encoding="utf-8") as fh:
            row_count = sum(1 for _ in fh) - 1
        mtime = path.stat().st_mtime
        note = ""
        if task9_ts is not None and mtime < task9_ts - 60:
            note = " -- WARNING: file mtime predates the Task 9 completion commit; may be stale"
            findings.append(Finding("HIGH", "stale-artifact", f"{fname}: mtime is older than Task 9's completion commit ({TASK9_COMMIT}){note}"))
        findings.append(Finding("INFO", "artifact-state", f"{fname}: {row_count} data rows"))

    calib_path = summary_dir / "global_outcome_calibration_phase2.csv"
    if calib_path.exists():
        with open(calib_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if len(rows) != 268:
            findings.append(Finding(
                "MEDIUM", "n-mismatch",
                f"global_outcome_calibration_phase2.csv has {len(rows)} rows, CLAUDE.md/plan Task 9 claims N=268",
            ))

    # Cost ledger reconciliation: micro-layer document_ids per issuer vs
    # outputs/p2_*/results/*.json document_ids per issuer.
    ledger_path = summary_dir / "api_cost_ledger.csv"
    if not ledger_path.exists():
        findings.append(Finding("HIGH", "missing-artifact", f"{ledger_path} does not exist"))
        return findings

    with open(ledger_path, newline="", encoding="utf-8") as fh:
        ledger_rows = list(csv.DictReader(fh))
    ledger_micro: dict[str, set[str]] = {}
    for row in ledger_rows:
        if row["layer"] == "micro":
            ledger_micro.setdefault(row["issuer"], set()).add(row["document_id"])

    scored: dict[str, set[str]] = {}
    for results_dir in OUTPUTS_DIR.glob("p2_*/results"):
        issuer = results_dir.parent.name
        scored[issuer] = {f.stem for f in results_dir.glob("*.json")}

    all_issuers = set(ledger_micro) | set(scored)
    for issuer in sorted(all_issuers):
        in_results_not_ledger = scored.get(issuer, set()) - ledger_micro.get(issuer, set())
        in_ledger_not_results = ledger_micro.get(issuer, set()) - scored.get(issuer, set())
        for doc_id in sorted(in_results_not_ledger):
            findings.append(Finding("LOW", "cost-ledger-gap", f"{issuer}/{doc_id}: scored result exists but no micro-layer row in api_cost_ledger.csv (run build_cost_ledger.py to refresh)"))
        for doc_id in sorted(in_ledger_not_results):
            findings.append(Finding("LOW", "cost-ledger-orphan", f"{issuer}/{doc_id}: micro-layer cost row exists but no matching scored result on disk"))

    dup_run_ids = {}
    for row in ledger_rows:
        if row["layer"] != "micro":
            continue
        key = (row["issuer"], row["document_id"])
        dup_run_ids.setdefault(key, []).append(row["run_id"])
    for key, run_ids in dup_run_ids.items():
        if len(run_ids) > 1:
            findings.append(Finding(
                "MEDIUM", "duplicate-cost-rows",
                f"{key[0]}/{key[1]}: {len(run_ids)} micro-layer cost rows (run_ids={run_ids}) - "
                f"was this document re-scored (re-billed) more than once? See run_reports.py's lack of "
                f"skip-if-already-scored caching, self-documented as a caveat in phase2/sourcing/run_gap_pipeline.py.",
            ))

    findings.append(Finding("INFO", "summary", f"cost ledger: {len(ledger_rows)} total rows, {sum(len(v) for v in ledger_micro.values())} micro-layer document_ids across {len(ledger_micro)} issuers"))
    return findings


if __name__ == "__main__":
    print_findings("Script 7: derived artifact freshness + cost ledger reconciliation", run())
