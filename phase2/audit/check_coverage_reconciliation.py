"""Script 5: cross-tabulate combo counts across every parallel directory tree
in the pipeline (roster list, manifests, docs/, outputs/p2_*/results,
outputs/news/p2_*/results, gap_combos.json status, and the final calibration
CSV) and flag anything present in one tree but missing from another. Read-only."""
from __future__ import annotations

import csv

from _common import (
    BASE_DIR,
    Finding,
    OUTPUTS_DIR,
    all_phase2_reports,
    load_gap_combos,
    phase2_manifest_paths,
    print_findings,
)


def run() -> list[Finding]:
    import blend  # PHASE2_ISSUERS roster
    import llm_news
    import quant_layer

    findings: list[Finding] = []

    # --- 1. Roster (PHASE2_ISSUERS in blend.py/llm_news.py/quant_layer.py) vs manifests on disk ---
    manifest_slugs = {p.name[len("p2_"):-len("_reports.json")] for p in phase2_manifest_paths()}
    for label, roster in (("blend.PHASE2_ISSUERS", blend.PHASE2_ISSUERS),
                           ("llm_news.PHASE2_ISSUERS", llm_news.PHASE2_ISSUERS),
                           ("quant_layer.PHASE2_ISSUERS", quant_layer.PHASE2_ISSUERS)):
        roster_set = set(roster)
        phantom = roster_set - manifest_slugs
        for slug in sorted(phantom):
            docs_exist = (BASE_DIR / "docs" / slug).is_dir()
            sev = "HIGH" if docs_exist else "MEDIUM"
            note = "docs/ has sourced files but NO manifest was ever built - scored data is sitting unused" if docs_exist else "no docs/ folder either - roster entry was never onboarded"
            findings.append(Finding(
                sev, "phantom-roster-issuer",
                f"{label} lists 'p2_{slug}' but manifests/p2_{slug}_reports.json does not exist ({note}). "
                f"Any BARE invocation of blend.py/llm_news.py/quant_layer.py/eval.run_eval (no explicit issuer args) "
                f"iterates this list directly via MANIFESTS[issuer] -> load_manifest() and will crash with "
                f"FileNotFoundError on this entry, silently skipping every issuer listed AFTER it in the array.",
            ))
        extra = manifest_slugs - roster_set
        for slug in sorted(extra):
            findings.append(Finding("MEDIUM", "manifest-not-in-roster", f"manifests/p2_{slug}_reports.json exists but 'p2_{slug}' is missing from {label}"))

    # --- 2. manifest document_ids vs scored outputs/p2_*/results/*.json ---
    manifest_ids: dict[str, str] = {}  # document_id -> issuer
    for report in all_phase2_reports():
        manifest_ids[report["document_id"]] = report["issuer"]

    scored_ids: dict[str, str] = {}
    for results_dir in OUTPUTS_DIR.glob("p2_*/results"):
        issuer = results_dir.parent.name
        for f in results_dir.glob("*.json"):
            scored_ids[f.stem] = issuer

    unscored = set(manifest_ids) - set(scored_ids)
    orphaned = set(scored_ids) - set(manifest_ids)
    for doc_id in sorted(unscored):
        findings.append(Finding("MEDIUM", "manifest-not-scored", f"{manifest_ids[doc_id]}/{doc_id}: in manifest but no outputs/{manifest_ids[doc_id]}/results/{doc_id}.json"))
    for doc_id in sorted(orphaned):
        findings.append(Finding("LOW", "orphaned-result", f"{scored_ids[doc_id]}/{doc_id}: scored result exists but no manifest entry references it"))

    # --- 3. scored micro results vs news results ---
    news_ids: dict[str, str] = {}
    for results_dir in OUTPUTS_DIR.glob("news/p2_*/results"):
        issuer = results_dir.parent.name
        for f in results_dir.glob("*_NEWS.json"):
            base_id = f.stem[:-len("_NEWS")]
            news_ids[base_id] = issuer

    missing_news = set(scored_ids) - set(news_ids)
    for doc_id in sorted(missing_news):
        findings.append(Finding("LOW", "no-news-score", f"{scored_ids[doc_id]}/{doc_id}: no news layer score (missing digest or not yet scored)"))

    # --- 4. gap_combos.json status vs actual scored state ---
    gap_combos = load_gap_combos()
    claimed_blended = {k: v for k, v in gap_combos.items() if v.get("status") == "blended"}
    for key, combo in claimed_blended.items():
        ticker = combo.get("ticker", "").split(".")[0]
        year = combo.get("year", "")
        quarter = combo.get("quarter", "")
        expected_prefix = f"{ticker}_"
        hits = [doc_id for doc_id in scored_ids if doc_id.startswith(expected_prefix) and year in doc_id]
        if not hits:
            findings.append(Finding("HIGH", "gap-combo-not-scored", f"gap_combos.json[{key}] status=blended but no matching outputs/p2_*/results/*.json found for ticker={ticker} year={year} quarter={quarter}"))

    # --- 5. calibration CSV row count vs scored count ---
    calib_path = OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration_phase2.csv"
    if calib_path.exists():
        with open(calib_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        calib_ids = {r["document_id"] for r in rows}
        only_in_calib = calib_ids - set(scored_ids)
        only_scored = set(scored_ids) - calib_ids
        findings.append(Finding("INFO", "summary", f"global_outcome_calibration_phase2.csv has {len(rows)} rows ({len(calib_ids)} unique document_ids)"))
        for doc_id in sorted(only_in_calib):
            findings.append(Finding("MEDIUM", "calib-orphan", f"{doc_id}: in calibration CSV but no scored micro result found on disk"))
        for doc_id in sorted(only_scored):
            findings.append(Finding("LOW", "calib-missing", f"{doc_id}: scored micro result exists but has no row in calibration CSV (likely dropped for missing forward_return outcome)"))
    else:
        findings.append(Finding("HIGH", "missing-artifact", f"{calib_path} does not exist"))

    findings.append(Finding(
        "INFO", "summary",
        f"{len(manifest_ids)} manifest document_ids, {len(scored_ids)} scored micro results, "
        f"{len(news_ids)} scored news results, {len(claimed_blended)} gap_combos marked 'blended'",
    ))
    return findings


if __name__ == "__main__":
    print_findings("Script 5: coverage reconciliation across pipeline trees", run())
