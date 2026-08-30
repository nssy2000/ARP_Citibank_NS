"""Resolve slug/sector/SEC-registrant metadata for gap combos. Tickers
already registered in triage_docs.TICKER_TO_SLUG reuse their existing
slug/sector (build_manifests.SECTORS) - no re-resolution needed. Brand-new
tickers get a slug derived from their company name and a sector pulled from
yfinance's Ticker.info (free, no LLM).

SEC-registrant status + CIK come from the SEC's public company_tickers.json
(no API key, cached locally) - tickers with a US CIK are Tier-1-eligible
(EDGAR full-text search for the press release); anything else (foreign
listings like ALV.DE, SIE.DE, or unmatched) goes straight to Tier-2 subagent
sourcing for every document type.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "phase2"))

from triage_docs import TICKER_TO_SLUG  # noqa: E402
from build_manifests import SECTORS  # noqa: E402

GAP_COMBOS_PATH = BASE_DIR / "phase2" / "gap_combos.json"
SEC_TICKERS_CACHE = BASE_DIR / "data" / "quantitative" / "sec_company_tickers_cache.json"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
HEADERS = {"User-Agent": "citibank-apr-research bencrowe01@gmail.com"}


def slugify(company: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", company.lower()).strip("_")


def load_sec_tickers() -> dict[str, int]:
    """Returns {TICKER: CIK}, cached locally (SEC's list changes rarely)."""
    if SEC_TICKERS_CACHE.exists():
        raw = json.loads(SEC_TICKERS_CACHE.read_text(encoding="utf-8"))
    else:
        req = urllib.request.Request(SEC_TICKERS_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        SEC_TICKERS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        SEC_TICKERS_CACHE.write_text(json.dumps(raw), encoding="utf-8")
    return {entry["ticker"].upper(): entry["cik_str"] for entry in raw.values()}


def resolve_sector(ticker: str) -> str | None:
    try:
        info = yf.Ticker(ticker).info
    except Exception as exc:
        # Swallowed broadly since yfinance raises a mix of network/parsing
        # errors for both transient blips and genuinely delisted/unknown
        # tickers; distinguishing them would need retry/backoff, out of
        # scope here. Logging the exception type/message at least lets a
        # rerun operator tell "network hiccup, try again" apart from
        # "yfinance doesn't know this symbol" without re-deriving it.
        print(f"  [resolve_sector] {ticker}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None
    sector, industry = info.get("sector"), info.get("industry")
    if sector and industry:
        return f"{sector}/{industry}"
    return sector or industry


def main() -> None:
    combos = json.loads(GAP_COMBOS_PATH.read_text(encoding="utf-8"))
    sec_tickers = load_sec_tickers()

    used_slugs = set(TICKER_TO_SLUG.values())
    slug_by_ticker: dict[str, str] = {}
    sector_by_ticker: dict[str, str | None] = {}
    new_ticker_count = 0
    flagged: list[str] = []

    for key, combo in sorted(combos.items()):
        ticker = combo["ticker"]
        cik = sec_tickers.get(ticker.upper())
        combo["is_sec_registrant"] = cik is not None
        combo["cik"] = cik

        if ticker in TICKER_TO_SLUG:
            combo["slug"] = TICKER_TO_SLUG[ticker]
            combo["sector"] = SECTORS.get(ticker)
            continue

        if ticker in slug_by_ticker:
            combo["slug"] = slug_by_ticker[ticker]
        else:
            base_slug = slugify(combo["company"] or ticker)
            slug = base_slug
            n = 2
            while slug in used_slugs:
                slug = f"{base_slug}_{n}"
                n += 1
            used_slugs.add(slug)
            slug_by_ticker[ticker] = slug
            combo["slug"] = slug
            new_ticker_count += 1

        if combo["sector"] is None:
            if ticker not in sector_by_ticker:
                sector_by_ticker[ticker] = resolve_sector(ticker)
            sector = sector_by_ticker[ticker]
            combo["sector"] = sector
            if sector is None:
                flagged.append(f"{key}: yfinance returned no sector/industry - set manually before Task 3")

    GAP_COMBOS_PATH.write_text(json.dumps(combos, indent=2, sort_keys=True), encoding="utf-8")
    print(f"New tickers resolved: {new_ticker_count} ({sorted(slug_by_ticker.values())})")
    print(f"SEC-registered (Tier-1 eligible for press release): {sum(1 for c in combos.values() if c.get('is_sec_registrant'))}")
    if flagged:
        print(f"\n{len(flagged)} combos need a manual sector before Task 3:")
        for f in flagged:
            print(" ", f)


if __name__ == "__main__":
    main()
