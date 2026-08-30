"""Shared helpers for the phase2 audit scripts (phase2/audit/check_*.py).

Read-only: nothing in this package writes to manifests/, docs/, outputs/, or
phase2/report_dates.json. Each check_*.py script is independently runnable
and prints its own findings; run_all.py aggregates them into one report.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

MANIFESTS_DIR = BASE_DIR / "manifests"
DOCS_DIR = BASE_DIR / "docs"
OUTPUTS_DIR = BASE_DIR / "outputs"


def phase2_manifest_paths() -> list[Path]:
    return sorted(MANIFESTS_DIR.glob("p2_*_reports.json"))


def load_raw_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def all_phase2_reports() -> list[dict]:
    """Every report entry across every p2_*_reports.json manifest, with the
    manifest's issuer slug attached (raw dicts, not report_pipeline.ReportSpec,
    so a malformed entry can't crash the whole audit)."""
    reports = []
    for path in phase2_manifest_paths():
        data = load_raw_manifest(path)
        for entry in data.get("reports", []):
            entry = dict(entry)
            entry["_manifest_path"] = str(path)
            reports.append(entry)
    return reports


def load_gap_combos() -> dict:
    path = BASE_DIR / "phase2" / "gap_combos.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


class Finding:
    def __init__(self, severity: str, category: str, message: str):
        assert severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
        self.severity = severity
        self.category = category
        self.message = message

    def __str__(self) -> str:
        return f"[{self.severity}] {self.category}: {self.message}"


def print_findings(title: str, findings: list[Finding]) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")
    if not findings:
        print("  (none)")
        return
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    for f in sorted(findings, key=lambda f: order[f.severity]):
        print(" ", f)
