"""Build manifests/p2_<slug>_reports.json for all 28 phase2 issuers, from
coverage_report.json (which files belong to which combo) + report_dates.json
(resolved report_date per combo). Copies source docs into the canonical docs/
tree (new issuers) or a docs/<slug>/phase2/ subtree (the 6 issuers that also
have an existing production manifest, so canonical files are never touched).

Only emits entries for combos with status OK or THIN(1 doc) - the 2 combos
with zero usable docs (BA_2025_Q4, JPM_2026_Q1) are skipped and reported.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from triage_docs import TICKER_TO_SLUG, OVERLAP_ISSUERS  # noqa: E402

COMPANY_NAMES = {
    "ABNB": "Airbnb", "AMZN": "Amazon", "AMD": "AMD", "AAPL": "Apple",
    "BAC": "Bank of America", "BA": "Boeing", "CVS": "CVS Health",
    "SCHW": "Charles Schwab", "C": "Citigroup", "KO": "Coca-Cola",
    "COIN": "Coinbase", "DIS": "Disney", "LLY": "Eli Lilly",
    "GS": "Goldman Sachs", "IBM": "IBM", "JPM": "JPMorgan",
    "LOW": "Lowe's", "LULU": "Lululemon", "AMKBY": "Maersk",
    "MCD": "McDonald's", "META": "Meta", "NFLX": "Netflix", "NKE": "Nike",
    "NVDA": "Nvidia", "TGT": "Target", "TSLA": "Tesla", "UBER": "Uber",
    "WMT": "Walmart",
    "BCS": "Barclays", "F": "Ford", "MSFT": "Microsoft", "PFE": "Pfizer",
    "UAL": "United Airlines",
    "PEP": "PepsiCo", "FDX": "FedEx", "LMT": "Lockheed Martin",
    "NVO": "Novo Nordisk", "HLT": "Hilton", "MC.PA": "LVMH", "MAR": "Marriott",
    "ALV.DE": "Allianz",
    "AVGO": "Broadcom",
    "BKNG": "Booking",
    "CAT": "Caterpillar",
    "CL": "Colgate-Palmolive",
    "CMCSA": "Comcast Corporation",
    "CMG": "Chipotle",
    "COST": "Costco",
    "CRM": "Salesforce",
    "DAL": "Delta Air Lines",
    "DELL": "Dell",
    "EXPE": "Expedia",
    "GIS": "General Mills",
    "GOOGL": "Alphabet",
    "HOOD": "Robinhood Markets",
    "JNJ": "Johnson  Johnson",
    "KHC": "Kraft Heinz",
    "LIN": "Linde",
    "LNVGY": "Lenovo",
    "MET": "Metlife",
    "MU": "Micron",
    "ORCL": "Oracle",
    "PINS": "Pinterest",
    "PLTR": "Palantir",
    "PUM.DE": "Puma",
    "PYPL": "PayPal",
    "RMSP.XC": "Hermes",
    "SBUX": "Starbucks",
    "SIE.DE": "Siemens",
    "SPOT": "Spotify",
    "STAN.L": "Standard Chartered",
    "UNH": "UnitedHealth",
    "V": "Visa",
    "WDAY": "Workday",
}

SECTORS = {
    "ABNB": "Consumer/Travel", "AMZN": "Consumer/Retail-Tech", "AMD": "Technology/Semiconductors",
    "AAPL": "Technology", "BAC": "Financials", "BA": "Industrials", "CVS": "Healthcare/Consumer",
    "SCHW": "Financials", "C": "Financials", "KO": "Consumer Staples", "COIN": "Financials/Crypto",
    "DIS": "Media/Communication Services", "LLY": "Healthcare", "GS": "Financials", "IBM": "Technology",
    "JPM": "Financials", "LOW": "Consumer/Retail", "LULU": "Consumer/Retail", "AMKBY": "Industrials/Shipping",
    "MCD": "Consumer/Retail", "META": "Media/Communication Services", "NFLX": "Media/Communication Services",
    "NKE": "Consumer/Retail", "NVDA": "Technology/Semiconductors", "TGT": "Consumer/Retail",
    "TSLA": "Consumer/Auto", "UBER": "Technology/Transportation", "WMT": "Consumer/Retail",
    "BCS": "Financials", "F": "Consumer/Auto", "MSFT": "Technology",
    "PFE": "Healthcare", "UAL": "Industrials/Airlines",
    "PEP": "Consumer Staples", "FDX": "Industrials/Logistics",
    "LMT": "Industrials/Aerospace-Defense", "NVO": "Healthcare",
    "HLT": "Consumer/Travel", "MC.PA": "Consumer/Luxury", "MAR": "Consumer/Travel",
    "ALV.DE": "Financial Services/Insurance - Diversified",
    "AVGO": "Technology/Semiconductors",
    "BKNG": "Consumer Cyclical/Travel Services",
    "CAT": "Industrials/Farm & Heavy Construction Machinery",
    "CL": "Consumer Defensive/Household & Personal Products",
    "CMCSA": "Communication Services/Telecom Services",
    "CMG": "Consumer Cyclical/Restaurants",
    "COST": "Consumer Defensive/Discount Stores",
    "CRM": "Technology/Software - Application",
    "DAL": "Industrials/Airlines",
    "DELL": "Technology/Computer Hardware",
    "EXPE": "Consumer Cyclical/Travel Services",
    "GIS": "Consumer Defensive/Packaged Foods",
    "GOOGL": "Communication Services/Internet Content & Information",
    "HOOD": "Financial Services/Capital Markets",
    "JNJ": "Healthcare/Drug Manufacturers - General",
    "KHC": "Consumer Defensive/Packaged Foods",
    "LIN": "Basic Materials/Specialty Chemicals",
    "LNVGY": "Technology/Computer Hardware",
    "MET": "Financial Services/Insurance - Life",
    "MU": "Technology/Semiconductors",
    "ORCL": "Technology/Software - Infrastructure",
    "PINS": "Communication Services/Internet Content & Information",
    "PLTR": "Technology/Software - Infrastructure",
    "PUM.DE": "Consumer Cyclical/Footwear & Accessories",
    "PYPL": "Financial Services/Credit Services",
    "RMSP.XC": "Consumer Cyclical/Luxury Goods",
    "SBUX": "Consumer Cyclical/Restaurants",
    "SIE.DE": "Industrials/Specialty Industrial Machinery",
    "SPOT": "Communication Services/Internet Content & Information",
    "STAN.L": "Financial Services/Banks - Diversified",
    "UNH": "Healthcare/Healthcare Plans",
    "V": "Financial Services/Credit Services",
    "WDAY": "Technology/Software - Application",
}

QUARTER_NUM = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}

# Long filings (10-K/10-Q/annual-report equivalents) are excluded from every
# layer by existing project convention (CLAUDE.md: "too financy" feedback,
# too dense) - these filename substrings caught JPM's SEC quarterly/annual
# filings and Maersk's full Annual Report that slipped into the new doc set
# looking like ordinary earnings documents.
EXCLUDE_FILENAME_SUBSTRINGS = ["corp-q1", "corp-q2", "corp-q3", "corp-q4", "corp-10k", "apmm-ar-"]


def is_excluded_long_filing(filename: str) -> bool:
    n = filename.lower()
    return any(s in n for s in EXCLUDE_FILENAME_SUBSTRINGS)


def main() -> None:
    coverage = json.loads((BASE_DIR / "phase2" / "coverage_report.json").read_text(encoding="utf-8"))
    report_dates = json.loads((BASE_DIR / "phase2" / "report_dates.json").read_text(encoding="utf-8"))
    combos = coverage["combos"]

    by_ticker: dict[str, list[dict]] = {}
    for key, entry in combos.items():
        by_ticker.setdefault(entry["ticker"], []).append(entry)

    skipped: list[str] = []
    manifests_written: list[str] = []
    total_reports = 0

    for ticker, entries in by_ticker.items():
        slug = TICKER_TO_SLUG[ticker]
        issuer = f"p2_{slug}"
        company = COMPANY_NAMES[ticker]
        sector = SECTORS[ticker]
        is_overlap = ticker in OVERLAP_ISSUERS

        entries_sorted = sorted(entries, key=lambda e: (e["year"], QUARTER_NUM[e["quarter"]]))
        reports = []

        for entry in entries_sorted:
            key = f"{ticker}_{entry['year']}_{entry['quarter']}"
            if entry["status"] not in ("OK", "THIN(1 doc)"):
                skipped.append(f"{key}: status={entry['status']}, no usable docs")
                continue
            if key not in report_dates:
                skipped.append(f"{key}: no resolved report_date")
                continue
            report_date = report_dates[key]["report_date"]

            usable_docs = [
                d for d in entry["docs"]
                if d.get("extract_ok") and not is_excluded_long_filing(Path(d["path"]).name)
            ]
            if not usable_docs:
                skipped.append(f"{key}: status={entry['status']} but no docs with extract_ok=True")
                continue

            fq = QUARTER_NUM[entry["quarter"]]
            document_id = f"{ticker}_FQ{fq}_{entry['year']}"
            dest_dir = (
                BASE_DIR / "docs" / slug / "phase2" / f"CY{entry['year']}-Q{fq}"
                if is_overlap else
                BASE_DIR / "docs" / slug / f"CY{entry['year']}-Q{fq}"
            )
            dest_dir.mkdir(parents=True, exist_ok=True)

            doc_entries = []
            for d in usable_docs:
                src = BASE_DIR / d["path"]
                dest = dest_dir / src.name
                if not dest.exists():
                    shutil.copy2(src, dest)
                doc_entries.append({
                    "doc_type": d["doc_type"] if d["doc_type"] != "Unknown" else "Earnings Document",
                    "source_pdf": str(dest.relative_to(BASE_DIR)).replace("\\", "/"),
                })

            reports.append({
                "document_id": document_id,
                "issuer": issuer,
                "company": company,
                "ticker": ticker,
                "sector": sector,
                "report_type": "Bundled Earnings Report",
                "fiscal_period": f"FQ{fq} {entry['year']}",
                "report_date": report_date,
                "documents": doc_entries,
            })
            total_reports += 1

        if not reports:
            skipped.append(f"{ticker}: zero reports, no manifest written")
            continue

        manifest_path = BASE_DIR / "manifests" / f"{issuer}_reports.json"
        manifest_path.write_text(
            json.dumps({"issuer": issuer, "reports": reports}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        manifests_written.append(f"{manifest_path.name}: {len(reports)} reports")

    print(f"Wrote {len(manifests_written)} manifests, {total_reports} total report entries:")
    for m in manifests_written:
        print(f"  {m}")
    if skipped:
        print(f"\n{len(skipped)} skipped combos:")
        for s in skipped:
            print(f"  {s}")


if __name__ == "__main__":
    main()
