"""Aggregate per-call cost logs already written by run_reports.py/llm_macro.py/llm_news.py
into one append-only ledger. Read-only over existing artifacts - makes no LLM calls, so it
is safe to re-run any time (e.g. after future scoring runs) to refresh the ledger.
"""

from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# phase2 is the only active track (pre-phase2 production issuers retired) -
# output folder layout is identical (just p2_-prefixed), so no other code
# here needs to change.
from llm_news import PHASE2_ISSUERS

ISSUERS = [f"p2_{name}" for name in PHASE2_ISSUERS]
FIELDNAMES = [
    "layer",
    "issuer",
    "document_id",
    "run_id",
    "timestamp",
    "model",
    "input_tokens",
    "cache_hit_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost_usd",
]


def _row(layer: str, issuer: str, cl: dict) -> dict:
    return {
        "layer": layer,
        "issuer": issuer,
        "document_id": cl.get("document_id", ""),
        "run_id": cl.get("run_id", ""),
        "timestamp": cl.get("timestamp", ""),
        "model": cl.get("model", ""),
        "input_tokens": cl.get("input_tokens", cl.get("prompt_tokens", "")),
        "cache_hit_tokens": cl.get("cache_hit_tokens", ""),
        "output_tokens": cl.get("output_tokens", ""),
        "total_tokens": cl.get("total_tokens", ""),
        "estimated_cost_usd": float(cl.get("estimated_cost_usd", 0.0) or 0.0),
    }


def build_ledger() -> list[dict]:
    rows: list[dict] = []

    for issuer in ISSUERS:
        csv_path = BASE_DIR / "outputs" / issuer / "summary" / f"{issuer}_first_run_summary.csv"
        if not csv_path.exists():
            continue
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("status") != "success":
                    continue
                rows.append(_row("micro", issuer, row))

    # Extension scan: outputs/p2_*_ext{date}/ directories (e.g. p2_*_ext2026_08_13)
    # Build a set of already-seen (layer, issuer, document_id) keys to avoid duplicates.
    seen_keys: set[tuple] = {(r["layer"], r["issuer"], r["document_id"]) for r in rows}
    for ext_dir in sorted(BASE_DIR.glob("outputs/p2_*_ext*/")):
        ext_issuer = ext_dir.name  # e.g. p2_sony_ext2026_08_13
        csv_path = ext_dir / "summary" / f"{ext_issuer}_first_run_summary.csv"
        if not csv_path.exists():
            continue
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("status") != "success":
                    continue
                key = ("micro_ext", ext_issuer, row.get("document_id", ""))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                rows.append(_row("micro_ext", ext_issuer, row))

    for f in sorted(glob.glob(str(BASE_DIR / "outputs" / "macro" / "results" / "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        rows.append(_row("macro", "macro", d.get("cost_log", d)))

    for issuer in ISSUERS:
        for f in sorted(glob.glob(str(BASE_DIR / "outputs" / "news" / issuer / "results" / "*.json"))):
            d = json.load(open(f, encoding="utf-8"))
            rows.append(_row("news", issuer, d.get("cost_log", d)))

    rows.sort(key=lambda r: (r["layer"], r["issuer"], r["document_id"]))
    return rows


def main() -> None:
    rows = build_ledger()
    out_path = BASE_DIR / "outputs" / "global" / "summary" / "api_cost_ledger.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    total = sum(r["estimated_cost_usd"] for r in rows)
    by_layer: dict[str, float] = {}
    for r in rows:
        by_layer[r["layer"]] = by_layer.get(r["layer"], 0.0) + r["estimated_cost_usd"]

    print(f"Wrote {out_path} ({len(rows)} rows)")
    print(f"Total cost: ${total:.4f}")
    for layer, cost in sorted(by_layer.items()):
        print(f"  {layer}: ${cost:.4f}")


if __name__ == "__main__":
    main()
