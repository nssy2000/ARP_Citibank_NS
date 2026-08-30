"""Builds/updates manifests/p2_<slug>_reports.json from gap_combos.json
entries with status "sourced" or later. For tickers with an existing
manifest (extra quarters on an already-onboarded issuer), appends new report
entries rather than overwriting. For brand-new tickers, creates the manifest
fresh.
"""
from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GAP_COMBOS_PATH = BASE_DIR / "phase2" / "gap_combos.json"
MANIFESTS_DIR = BASE_DIR / "manifests"

QUARTER_NUM = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
READY_STATUSES = {"sourced", "scored", "blended"}


def main() -> None:
    combos = json.loads(GAP_COMBOS_PATH.read_text(encoding="utf-8"))
    by_slug: dict[str, list[dict]] = {}
    for c in combos.values():
        if c["status"] in READY_STATUSES:
            by_slug.setdefault(c["slug"], []).append(c)

    written = []
    for slug, entries in sorted(by_slug.items()):
        manifest_path = MANIFESTS_DIR / f"p2_{slug}_reports.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"issuer": f"p2_{slug}", "reports": []}
        existing_ids = {r["document_id"] for r in manifest["reports"]}

        for c in sorted(entries, key=lambda c: (c["year"], c["quarter"])):
            fq = QUARTER_NUM[c["quarter"]]
            document_id = f"{c['ticker']}_FQ{fq}_{c['year']}"
            if document_id in existing_ids:
                continue
            manifest["reports"].append({
                "document_id": document_id,
                "issuer": f"p2_{slug}",
                "company": c["company"],
                "ticker": c["ticker"],
                "sector": c.get("sector") or "Unclassified",
                "report_type": "Bundled Earnings Report",
                "fiscal_period": f"FQ{fq} {c['year']}",
                "report_date": c["report_date"],
                "documents": c["documents"],
            })
        manifest["reports"].sort(key=lambda r: (r["fiscal_period"].split()[-1], r["fiscal_period"].split()[0]))
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        written.append(f"p2_{slug}: {len(manifest['reports'])} total reports")

    print(f"Wrote/updated {len(written)} manifests:")
    for w in written:
        print(" ", w)


if __name__ == "__main__":
    main()
