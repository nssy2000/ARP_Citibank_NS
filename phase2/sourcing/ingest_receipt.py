"""Merges a Tier-2 subagent's JSON receipt (see make_wave.py's
RECEIPT_SCHEMA) into gap_combos.json: records documents written, marks the
news digest written, advances status to "sourced" once both are satisfied,
and files any 'unresolved' notes for manual follow-up.

Writes gap_combos.json atomically via phase2/sourcing/checkpoint_io.py's
save_gap_combos() (temp file + os.replace()), shared with
phase2/sourcing/edgar_lookup.py's Tier-1 pass - this is a shared checkpoint
file invoked once per Tier-2 wave receipt (potentially dozens of times
across the plan), so a process kill mid-write must not truncate/corrupt
everything previously on disk.

A malformed receipt entry (missing year/quarter, or a documents_written
item missing path/doc_type) is warned about and skipped rather than
crashing the whole run - crashing would lose every earlier-processed valid
entry in the same receipt too, since gap_combos.json is only saved once at
the end.

Usage: python phase2/sourcing/ingest_receipt.py path/to/receipt.json
   or: echo '<receipt json>' | python phase2/sourcing/ingest_receipt.py -
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from checkpoint_io import GAP_COMBOS_PATH, save_gap_combos


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: ingest_receipt.py <receipt.json | ->")
    raw = sys.stdin.read() if sys.argv[1] == "-" else Path(sys.argv[1]).read_text(encoding="utf-8")
    receipt = json.loads(raw)

    if not isinstance(receipt.get("ticker"), str):
        print("ERROR: receipt missing top-level \"ticker\" string, cannot ingest", file=sys.stderr)
        raise SystemExit(1)
    if not isinstance(receipt.get("combos"), list):
        print("ERROR: receipt missing top-level \"combos\" list, cannot ingest", file=sys.stderr)
        raise SystemExit(1)

    combos = json.loads(GAP_COMBOS_PATH.read_text(encoding="utf-8"))
    ticker = receipt["ticker"]
    updated, unresolved_total, malformed = 0, 0, 0

    for i, entry in enumerate(receipt["combos"]):
        try:
            key = f"{ticker}_{entry['year']}_{entry['quarter']}"
            combo = combos.get(key)
            if combo is None:
                print(f"WARNING: {key} not found in gap_combos.json, skipping", file=sys.stderr)
                continue

            existing_paths = {d["source_pdf"] for d in combo.get("documents", [])}
            for doc in entry.get("documents_written", []):
                path = doc["path"]
                if path in existing_paths:
                    continue
                combo.setdefault("documents", []).append({"doc_type": doc["doc_type"], "source_pdf": path})

            if entry.get("news_digest_written"):
                combo["news_document_written"] = True
            if entry.get("unresolved"):
                combo["notes"] = (combo["notes"] + " Tier2 unresolved: " + "; ".join(entry["unresolved"])).strip()
                unresolved_total += 1

            have_types = {d["doc_type"] for d in combo.get("documents", [])}
            if len(have_types) >= 2 and combo.get("news_document_written"):
                combo["status"] = "sourced"
            updated += 1
        except (KeyError, TypeError) as exc:
            malformed += 1
            print(
                f"WARNING: combos[{i}] for ticker {ticker!r} is malformed "
                f"(missing/invalid field: {exc}), skipping entry: {entry!r}",
                file=sys.stderr,
            )
            continue

    save_gap_combos(combos)
    print(
        f"Ingested receipt for {ticker}: {updated} combos updated, "
        f"{unresolved_total} flagged unresolved, {malformed} entries skipped as malformed"
    )


if __name__ == "__main__":
    main()
