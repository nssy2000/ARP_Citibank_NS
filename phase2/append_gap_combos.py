"""One-time-per-batch migration: append gap_combos.json's combos into
triage_docs.TARGET_COMBOS/TICKER_TO_SLUG, build_manifests.py's
COMPANY_NAMES/SECTORS, and PHASE2_ISSUERS in blend.py/llm_news.py/quant_layer.py.

Idempotent via gap_combos.json's "appended" flag - safe to rerun after adding
more combos to gap_combos.json; already-appended combos are skipped. Also
idempotent within a single rerun that follows a partial failure (e.g. a crash
after triage_docs.py was written but before gap_combos.json's "appended" flag
was persisted): every insertion, including TARGET_COMBOS, checks whether its
content is already present before splicing, so rerunning never duplicates a
tuple/entry.

Aborts with no changes written if any anchor string this script splices
around has moved since this script was written - never silently corrupts a
file. If that happens, re-locate the anchor by hand and update the constant
below. All file writes for a given run are computed and syntax-validated
(compile()) in memory first and only hit disk after every touched file has
succeeded - a failure partway through (bad anchor, broken splice, a value
from gap_combos.json that doesn't escape cleanly) aborts before anything is
written, rather than leaving some files updated and others not. This matters
most for blend.py/llm_news.py/quant_layer.py, whose PHASE2_ISSUERS lists must
stay in 3-way sync.
"""
from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
GAP_COMBOS_PATH = BASE_DIR / "phase2" / "gap_combos.json"
TRIAGE_DOCS_PATH = BASE_DIR / "phase2" / "triage_docs.py"
BUILD_MANIFESTS_PATH = BASE_DIR / "phase2" / "build_manifests.py"
PHASE2_ISSUERS_FILES = [BASE_DIR / "blend.py", BASE_DIR / "llm_news.py", BASE_DIR / "quant_layer.py"]


def splice_before(text: str, anchor: str, insertion: str, label: str) -> str:
    count = text.count(anchor)
    if count != 1:
        raise SystemExit(f"Aborting: expected exactly 1 occurrence of the {label} anchor, found {count}.")
    return text.replace(anchor, insertion + anchor, 1)


def block_between(text: str, start_marker: str, end_marker: str, label: str) -> str:
    """Like splice_before, this only trusts markers that occur exactly once -
    a missing marker would otherwise raise an unguarded IndexError, and a
    duplicated one would otherwise silently resolve against the first
    occurrence instead of aborting."""
    start_count = text.count(start_marker)
    if start_count != 1:
        raise SystemExit(f"Aborting: expected exactly 1 occurrence of the {label} start marker, found {start_count}.")
    after_start = text.split(start_marker, 1)[1]
    end_count = after_start.count(end_marker)
    if end_count != 1:
        raise SystemExit(f"Aborting: expected exactly 1 occurrence of the {label} end marker (after the start marker), found {end_count}.")
    return after_start.split(end_marker, 1)[0]


def check_compiles(text: str, path: Path) -> None:
    """Guard against a splice that's syntactically well-formed on its own but
    produces broken Python once inserted (or a value from gap_combos.json
    that doesn't escape the way we expect) - abort rather than write invalid
    source that would break every downstream import."""
    try:
        compile(text, str(path), "exec")
    except SyntaxError as exc:
        raise SystemExit(f"Aborting: spliced content for {path} does not compile: {exc}")


def main() -> None:
    combos = json.loads(GAP_COMBOS_PATH.read_text(encoding="utf-8"))
    pending = {k: v for k, v in combos.items() if not v.get("appended") and v.get("slug")}
    if not pending:
        print("Nothing to append (all resolved combos already appended, or none have a slug yet - run resolve_gap_tickers.py first).")
        return

    # Every file's new content is computed and validated here first; nothing
    # in this dict gets written to disk until every touched file has
    # succeeded (see the write loop at the end) - all-or-nothing for the
    # whole run, not per file.
    pending_writes: dict[Path, str] = {}

    # 1+2. triage_docs.py: TARGET_COMBOS (every pending combo not already
    # present - see idempotency note above) + TICKER_TO_SLUG (new tickers
    # only).
    triage_text = TRIAGE_DOCS_PATH.read_text(encoding="utf-8")

    sorted_pending = sorted(pending.values(), key=lambda c: (c["ticker"], c["year"], c["quarter"]))
    new_combo_tuples = [
        f'({json.dumps(c["company"])}, {json.dumps(c["ticker"])}, {int(c["year"])}, {json.dumps(c["quarter"])}),'
        for c in sorted_pending
    ]
    new_combo_tuples = [t for t in new_combo_tuples if t not in triage_text]
    if new_combo_tuples:
        combo_lines = "\n".join(f"    {t}" for t in new_combo_tuples)
        batch_comment = (
            "    # Fourth batch - human/LLM gap-fill onboarding (see\n"
            "    # docs/superpowers/specs/2026-08-05-phase2-gap-onboarding-design.md).\n"
            "    # Docs hand-sourced via EDGAR/IR lookup + background subagent web search,\n"
            "    # not from an OneDrive drop - see phase2/gap_combos.json for provenance.\n"
        )
        triage_text = splice_before(triage_text, "]\n\nTICKER_TO_FOLDER = {", batch_comment + combo_lines + "\n", "TARGET_COMBOS")

    existing_slug_block = block_between(triage_text, "TICKER_TO_SLUG = {", "}\n\n# The 6 tickers above", "TICKER_TO_SLUG")
    # One combo per brand-new ticker. When several pending combos share a
    # ticker with differing company-name text across quarters (e.g. BKNG had
    # "Booking Holdings" for Q1 vs "Booking" for Q2-Q4), whichever sorts last
    # wins here, by design - COMPANY_NAMES/SECTORS/TICKER_TO_SLUG are
    # per-ticker, not per-quarter, so there's exactly one slot for a company
    # that in practice is described the same way either way.
    new_ticker_combos = {c["ticker"]: c for c in pending.values() if f'"{c["ticker"]}":' not in existing_slug_block}
    if new_ticker_combos:
        slug_lines = "\n".join(f'    {json.dumps(t)}: {json.dumps(c["slug"])},' for t, c in sorted(new_ticker_combos.items()))
        triage_text = splice_before(triage_text, "}\n\n# The 6 tickers above", slug_lines + "\n", "TICKER_TO_SLUG")
    check_compiles(triage_text, TRIAGE_DOCS_PATH)
    pending_writes[TRIAGE_DOCS_PATH] = triage_text

    # 3. build_manifests.py: COMPANY_NAMES + SECTORS, new tickers only.
    bm_text = BUILD_MANIFESTS_PATH.read_text(encoding="utf-8")
    if new_ticker_combos:
        company_lines = "\n".join(f'    {json.dumps(t)}: {json.dumps(c["company"])},' for t, c in sorted(new_ticker_combos.items()))
        bm_text = splice_before(bm_text, "}\n\nSECTORS = {", company_lines + "\n", "COMPANY_NAMES")
        sector_lines = "\n".join(f'    {json.dumps(t)}: {json.dumps(c["sector"] or "Unclassified")},' for t, c in sorted(new_ticker_combos.items()))
        bm_text = splice_before(bm_text, "}\n\nQUARTER_NUM = {", sector_lines + "\n", "SECTORS")
    check_compiles(bm_text, BUILD_MANIFESTS_PATH)
    pending_writes[BUILD_MANIFESTS_PATH] = bm_text

    # 4. PHASE2_ISSUERS in blend.py / llm_news.py / quant_layer.py - new
    # slugs only. Computed and validated for all 3 files before any of them
    # is staged for writing, so the 3-way sync those lists depend on can't
    # be broken by one file succeeding and another failing.
    new_slugs = sorted({c["slug"] for c in new_ticker_combos.values()})
    if new_slugs:
        for path in PHASE2_ISSUERS_FILES:
            text = path.read_text(encoding="utf-8")
            existing_block = block_between(text, "PHASE2_ISSUERS = [", "\n]\nMANIFESTS.update({", f"PHASE2_ISSUERS in {path.name}")
            missing = [s for s in new_slugs if f'"{s}"' not in existing_block]
            if not missing:
                continue
            lines = "    " + ", ".join(json.dumps(s) for s in missing) + ",\n"
            text = splice_before(text, "]\nMANIFESTS.update({", lines, f"PHASE2_ISSUERS in {path.name}")
            check_compiles(text, path)
            pending_writes[path] = text

    for path, text in pending_writes.items():
        path.write_text(text, encoding="utf-8")

    for key in pending:
        combos[key]["appended"] = True
    GAP_COMBOS_PATH.write_text(json.dumps(combos, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Appended {len(pending)} combos to TARGET_COMBOS ({len(new_ticker_combos)} brand-new tickers: {sorted(new_ticker_combos.keys())})")
    print("Review before committing: git diff phase2/triage_docs.py phase2/build_manifests.py blend.py llm_news.py quant_layer.py")


if __name__ == "__main__":
    main()
