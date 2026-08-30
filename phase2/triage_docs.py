"""Phase 2 coverage triage: match the 104 human-evaluated company+quarter combos
against files in OneDrive_2026-07-18/Phase 2/<Company>/**, and report what's
usable, what's thin, and what's missing entirely. Read-only, no LLM calls."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))



MIN_FILE_BYTES = 15_000  # rough proxy for MIN_EXTRACTED_TEXT_CHARS without opening the file


def quick_extract_check(path: Path) -> tuple[bool, int, str | None]:
    """File-size-only proxy for "this doc has real content" - no file open/read
    at all, so it can't be slowed or hung by OneDrive on-demand hydration or by
    parsing huge PDFs. Real extraction (pypdf + pdfplumber fallback, exact char
    counts) happens for real during the actual report_pipeline run (--dry-run
    step) - triage only needs a rough presence/size signal, not exact chars."""
    try:
        size = path.stat().st_size
        return size >= MIN_FILE_BYTES, size, None
    except Exception as exc:  # noqa: BLE001
        return False, 0, str(exc)[:200]

DOCS_ROOT = BASE_DIR / "OneDrive_2026-07-18" / "Phase 2"

# (company_display, ticker, year, quarter) - the 104 combos humans evaluated,
# pulled from Data Entry rows where Type == "Human".
TARGET_COMBOS = [
    ("AMD", "AMD", 2025, "Q2"), ("AMD", "AMD", 2025, "Q4"), ("AMD", "AMD", 2026, "Q1"),
    ("Airbnb", "ABNB", 2025, "Q2"), ("Airbnb", "ABNB", 2025, "Q3"), ("Airbnb", "ABNB", 2025, "Q4"), ("Airbnb", "ABNB", 2026, "Q1"),
    ("Amazon", "AMZN", 2025, "Q3"), ("Amazon", "AMZN", 2025, "Q4"), ("Amazon", "AMZN", 2026, "Q1"),
    ("Apple", "AAPL", 2025, "Q3"), ("Apple", "AAPL", 2025, "Q4"), ("Apple", "AAPL", 2026, "Q1"),
    ("Bank of America", "BAC", 2025, "Q1"), ("Bank of America", "BAC", 2025, "Q2"), ("Bank of America", "BAC", 2025, "Q3"), ("Bank of America", "BAC", 2025, "Q4"),
    ("Boeing", "BA", 2025, "Q1"), ("Boeing", "BA", 2025, "Q2"), ("Boeing", "BA", 2025, "Q3"), ("Boeing", "BA", 2025, "Q4"),
    ("CVS Health", "CVS", 2026, "Q1"),
    ("Charles Schwab", "SCHW", 2025, "Q1"), ("Charles Schwab", "SCHW", 2025, "Q2"), ("Charles Schwab", "SCHW", 2025, "Q3"), ("Charles Schwab", "SCHW", 2025, "Q4"), ("Charles Schwab", "SCHW", 2026, "Q1"),
    ("Citigroup", "C", 2025, "Q1"), ("Citigroup", "C", 2025, "Q2"), ("Citigroup", "C", 2025, "Q3"), ("Citigroup", "C", 2025, "Q4"),
    ("Coca-Cola", "KO", 2025, "Q2"), ("Coca-Cola", "KO", 2025, "Q4"), ("Coca-Cola", "KO", 2026, "Q1"),
    ("Coinbase", "COIN", 2025, "Q3"), ("Coinbase", "COIN", 2025, "Q4"), ("Coinbase", "COIN", 2026, "Q1"),
    ("Disney", "DIS", 2025, "Q1"), ("Disney", "DIS", 2025, "Q3"), ("Disney", "DIS", 2025, "Q4"),
    ("Eli Lilly", "LLY", 2025, "Q3"), ("Eli Lilly", "LLY", 2025, "Q4"), ("Eli Lilly", "LLY", 2026, "Q1"),
    ("Goldman Sachs", "GS", 2025, "Q1"), ("Goldman Sachs", "GS", 2025, "Q2"), ("Goldman Sachs", "GS", 2025, "Q3"), ("Goldman Sachs", "GS", 2025, "Q4"), ("Goldman Sachs", "GS", 2026, "Q1"), ("Goldman Sachs", "GS", 2026, "Q2"),
    ("IBM", "IBM", 2025, "Q2"), ("IBM", "IBM", 2025, "Q4"), ("IBM", "IBM", 2026, "Q1"),
    ("JPMorgan", "JPM", 2025, "Q1"), ("JPMorgan", "JPM", 2025, "Q2"), ("JPMorgan", "JPM", 2025, "Q3"), ("JPMorgan", "JPM", 2025, "Q4"), ("JPMorgan", "JPM", 2026, "Q1"),
    ("Lowe's", "LOW", 2025, "Q1"), ("Lowe's", "LOW", 2025, "Q2"), ("Lowe's", "LOW", 2025, "Q3"), ("Lowe's", "LOW", 2025, "Q4"), ("Lowe's", "LOW", 2026, "Q1"),
    ("Lululemon", "LULU", 2025, "Q3"), ("Lululemon", "LULU", 2025, "Q4"), ("Lululemon", "LULU", 2026, "Q1"),
    ("Maersk", "AMKBY", 2025, "Q1"), ("Maersk", "AMKBY", 2025, "Q2"), ("Maersk", "AMKBY", 2025, "Q3"), ("Maersk", "AMKBY", 2025, "Q4"),
    ("McDonald's", "MCD", 2024, "Q4"), ("McDonald's", "MCD", 2025, "Q4"), ("McDonald's", "MCD", 2026, "Q1"),
    ("Meta", "META", 2025, "Q3"), ("Meta", "META", 2025, "Q4"), ("Meta", "META", 2026, "Q1"),
    ("Netflix", "NFLX", 2024, "Q4"), ("Netflix", "NFLX", 2025, "Q1"), ("Netflix", "NFLX", 2025, "Q2"), ("Netflix", "NFLX", 2025, "Q3"), ("Netflix", "NFLX", 2025, "Q4"), ("Netflix", "NFLX", 2026, "Q1"),
    ("Nike", "NKE", 2025, "Q1"), ("Nike", "NKE", 2025, "Q2"), ("Nike", "NKE", 2025, "Q3"),
    ("Nvidia", "NVDA", 2025, "Q1"), ("Nvidia", "NVDA", 2025, "Q2"), ("Nvidia", "NVDA", 2025, "Q3"), ("Nvidia", "NVDA", 2025, "Q4"),
    ("Target", "TGT", 2025, "Q1"), ("Target", "TGT", 2025, "Q2"), ("Target", "TGT", 2025, "Q3"), ("Target", "TGT", 2026, "Q1"),
    ("Tesla", "TSLA", 2025, "Q3"), ("Tesla", "TSLA", 2025, "Q4"), ("Tesla", "TSLA", 2026, "Q1"),
    ("Uber", "UBER", 2025, "Q1"), ("Uber", "UBER", 2025, "Q2"), ("Uber", "UBER", 2025, "Q4"), ("Uber", "UBER", 2026, "Q1"),
    ("Walmart", "WMT", 2025, "Q1"), ("Walmart", "WMT", 2025, "Q2"), ("Walmart", "WMT", 2025, "Q3"), ("Walmart", "WMT", 2025, "Q4"), ("Walmart", "WMT", 2026, "Q1"),
    # Second batch (humans now at 132 predictions vs the original 104) - 5 brand-new
    # tickers plus one more quarter each for two issuers already onboarded above.
    ("Barclays", "BCS", 2025, "Q2"), ("Barclays", "BCS", 2025, "Q3"), ("Barclays", "BCS", 2026, "Q1"),
    ("Ford", "F", 2025, "Q2"), ("Ford", "F", 2025, "Q4"), ("Ford", "F", 2026, "Q1"),
    ("Microsoft", "MSFT", 2025, "Q1"), ("Microsoft", "MSFT", 2025, "Q2"), ("Microsoft", "MSFT", 2026, "Q1"),
    ("Pfizer", "PFE", 2025, "Q1"), ("Pfizer", "PFE", 2025, "Q2"), ("Pfizer", "PFE", 2025, "Q4"), ("Pfizer", "PFE", 2026, "Q1"),
    ("United Airlines", "UAL", 2025, "Q1"), ("United Airlines", "UAL", 2025, "Q2"), ("United Airlines", "UAL", 2025, "Q3"), ("United Airlines", "UAL", 2025, "Q4"),
    # Third batch - 33 combos humans scored with no manifest entry anywhere: 6
    # brand-new tickers (no OneDrive folder to scan - documents hand-sourced from
    # the web, manifests hand-authored, see manifests/p2_pepsico_reports.json etc.)
    # plus 3 older CVS Health quarters on an already-onboarded ticker.
    ("PepsiCo", "PEP", 2023, "Q1"), ("PepsiCo", "PEP", 2023, "Q2"), ("PepsiCo", "PEP", 2023, "Q3"), ("PepsiCo", "PEP", 2023, "Q4"),
    ("PepsiCo", "PEP", 2024, "Q1"), ("PepsiCo", "PEP", 2024, "Q2"), ("PepsiCo", "PEP", 2024, "Q3"), ("PepsiCo", "PEP", 2024, "Q4"),
    ("PepsiCo", "PEP", 2025, "Q1"), ("PepsiCo", "PEP", 2025, "Q2"), ("PepsiCo", "PEP", 2025, "Q3"), ("PepsiCo", "PEP", 2025, "Q4"),
    ("PepsiCo", "PEP", 2026, "Q1"), ("PepsiCo", "PEP", 2026, "Q2"),
    ("FedEx", "FDX", 2026, "Q1"), ("FedEx", "FDX", 2026, "Q2"), ("FedEx", "FDX", 2026, "Q3"), ("FedEx", "FDX", 2026, "Q4"),
    ("Lockheed Martin", "LMT", 2025, "Q1"), ("Lockheed Martin", "LMT", 2025, "Q2"), ("Lockheed Martin", "LMT", 2025, "Q3"), ("Lockheed Martin", "LMT", 2025, "Q4"),
    ("Novo Nordisk", "NVO", 2025, "Q1"), ("Novo Nordisk", "NVO", 2025, "Q2"), ("Novo Nordisk", "NVO", 2025, "Q3"), ("Novo Nordisk", "NVO", 2025, "Q4"),
    ("Hilton", "HLT", 2025, "Q1"), ("Hilton", "HLT", 2025, "Q2"),
    ("LVMH", "MC.PA", 2025, "Q2"), ("LVMH", "MC.PA", 2025, "Q4"),
    ("CVS Health", "CVS", 2025, "Q2"), ("CVS Health", "CVS", 2025, "Q3"), ("CVS Health", "CVS", 2025, "Q4"),
    # Fourth batch - human/LLM gap-fill onboarding (see
    # docs/superpowers/specs/2026-08-05-phase2-gap-onboarding-design.md).
    # Docs hand-sourced via EDGAR/IR lookup + background subagent web search,
    # not from an OneDrive drop - see phase2/gap_combos.json for provenance.
    ("Allianz", "ALV.DE", 2025, "Q1"),
    ("Allianz", "ALV.DE", 2025, "Q2"),
    ("Allianz", "ALV.DE", 2025, "Q3"),
    ("Allianz", "ALV.DE", 2025, "Q4"),
    ("Broadcom", "AVGO", 2025, "Q3"),
    ("Broadcom", "AVGO", 2025, "Q4"),
    ("Broadcom", "AVGO", 2026, "Q1"),
    ("Booking Holdings", "BKNG", 2025, "Q1"),
    ("Booking", "BKNG", 2025, "Q2"),
    ("Booking", "BKNG", 2025, "Q3"),
    ("Booking", "BKNG", 2025, "Q4"),
    ("Caterpillar", "CAT", 2025, "Q2"),
    ("Caterpillar", "CAT", 2025, "Q3"),
    ("Caterpillar", "CAT", 2025, "Q4"),
    ("Colgate-Palmolive", "CL", 2025, "Q3"),
    ("Colgate-Palmolive", "CL", 2025, "Q4"),
    ("Colgate-Palmolive", "CL", 2026, "Q1"),
    ("Colgate-Palmolive", "CL", 2026, "Q2"),
    ("Comcast Corporation", "CMCSA", 2025, "Q1"),
    ("Comcast Corporation", "CMCSA", 2025, "Q2"),
    ("Comcast Corporation", "CMCSA", 2025, "Q4"),
    ("Comcast Corporation", "CMCSA", 2026, "Q1"),
    ("Chipotle", "CMG", 2025, "Q1"),
    ("Chipotle", "CMG", 2025, "Q2"),
    ("Chipotle", "CMG", 2025, "Q3"),
    ("Chipotle", "CMG", 2025, "Q4"),
    ("Costco", "COST", 2025, "Q4"),
    ("Costco", "COST", 2026, "Q1"),
    ("Costco", "COST", 2026, "Q2"),
    ("Salesforce", "CRM", 2026, "Q2"),
    ("Salesforce", "CRM", 2026, "Q3"),
    ("Salesforce", "CRM", 2026, "Q4"),
    ("Delta Air Lines", "DAL", 2025, "Q1"),
    ("Delta Air Lines", "DAL", 2025, "Q2"),
    ("Delta Air Lines", "DAL", 2025, "Q3"),
    ("Delta Air Lines", "DAL", 2025, "Q4"),
    ("Dell", "DELL", 2025, "Q1"),
    ("Dell", "DELL", 2025, "Q2"),
    ("Dell", "DELL", 2025, "Q3"),
    ("Dell", "DELL", 2025, "Q4"),
    ("Expedia", "EXPE", 2025, "Q1"),
    ("Expedia", "EXPE", 2025, "Q2"),
    ("Expedia", "EXPE", 2025, "Q4"),
    ("Expedia", "EXPE", 2026, "Q1"),
    ("General Mills", "GIS", 2026, "Q2"),
    ("General Mills", "GIS", 2026, "Q3"),
    ("General Mills", "GIS", 2026, "Q4"),
    ("Alphabet", "GOOGL", 2025, "Q3"),
    ("Alphabet", "GOOGL", 2025, "Q4"),
    ("Alphabet", "GOOGL", 2026, "Q1"),
    ("Robinhood Markets", "HOOD", 2025, "Q1"),
    ("Robinhood Markets", "HOOD", 2025, "Q2"),
    ("Robinhood Markets", "HOOD", 2025, "Q3"),
    ("Robinhood Markets", "HOOD", 2026, "Q1"),
    ("Johnson  Johnson", "JNJ", 2025, "Q1"),
    ("Johnson  Johnson", "JNJ", 2025, "Q2"),
    ("Johnson  Johnson", "JNJ", 2025, "Q3"),
    ("Kraft Heinz", "KHC", 2024, "Q4"),
    ("Kraft Heinz", "KHC", 2025, "Q1"),
    ("Kraft Heinz", "KHC", 2026, "Q1"),
    ("Linde", "LIN", 2025, "Q2"),
    ("Linde", "LIN", 2025, "Q3"),
    ("Linde", "LIN", 2026, "Q1"),
    ("Lenovo", "LNVGY", 2026, "Q1"),
    ("Lenovo", "LNVGY", 2026, "Q2"),
    ("Lenovo", "LNVGY", 2026, "Q3"),
    ("Lenovo", "LNVGY", 2026, "Q4"),
    ("Metlife", "MET", 2023, "Q1"),
    ("Metlife", "MET", 2023, "Q2"),
    ("Metlife", "MET", 2023, "Q3"),
    ("Metlife", "MET", 2023, "Q4"),
    ("Metlife", "MET", 2024, "Q1"),
    ("Metlife", "MET", 2024, "Q2"),
    ("Metlife", "MET", 2024, "Q3"),
    ("Metlife", "MET", 2024, "Q4"),
    ("Metlife", "MET", 2025, "Q1"),
    ("Metlife", "MET", 2025, "Q2"),
    ("Metlife", "MET", 2025, "Q3"),
    ("Metlife", "MET", 2025, "Q4"),
    ("Metlife", "MET", 2026, "Q1"),
    ("Micron", "MU", 2025, "Q4"),
    ("Micron", "MU", 2026, "Q1"),
    ("Micron", "MU", 2026, "Q2"),
    ("Oracle", "ORCL", 2026, "Q1"),
    ("Oracle", "ORCL", 2026, "Q2"),
    ("Oracle", "ORCL", 2026, "Q3"),
    ("Pinterest", "PINS", 2024, "Q4"),
    ("Pinterest", "PINS", 2025, "Q4"),
    ("Pinterest", "PINS", 2026, "Q1"),
    ("Palantir", "PLTR", 2025, "Q1"),
    ("Palantir", "PLTR", 2025, "Q2"),
    ("Palantir", "PLTR", 2025, "Q3"),
    ("Palantir", "PLTR", 2025, "Q4"),
    ("Puma", "PUM.DE", 2025, "Q1"),
    ("Puma", "PUM.DE", 2025, "Q3"),
    ("Puma", "PUM.DE", 2025, "Q4"),
    ("Puma", "PUM.DE", 2026, "Q1"),
    ("PayPal", "PYPL", 2025, "Q1"),
    ("PayPal", "PYPL", 2025, "Q2"),
    ("PayPal", "PYPL", 2025, "Q3"),
    ("PayPal", "PYPL", 2026, "Q1"),
    ("Hermes", "RMSP.XC", 2025, "Q1"),
    ("Hermes", "RMSP.XC", 2025, "Q2"),
    ("Hermes", "RMSP.XC", 2025, "Q3"),
    ("Hermes", "RMSP.XC", 2025, "Q4"),
    ("Starbucks", "SBUX", 2025, "Q3"),
    ("Starbucks", "SBUX", 2025, "Q4"),
    ("Starbucks", "SBUX", 2026, "Q1"),
    ("Siemens", "SIE.DE", 2025, "Q4"),
    ("Siemens", "SIE.DE", 2026, "Q1"),
    ("Siemens", "SIE.DE", 2026, "Q2"),
    ("Spotify", "SPOT", 2025, "Q2"),
    ("Spotify", "SPOT", 2025, "Q3"),
    ("Spotify", "SPOT", 2025, "Q4"),
    ("Spotify", "SPOT", 2026, "Q1"),
    ("Standard Chartered", "STAN.L", 2025, "Q1"),
    ("Standard Chartered", "STAN.L", 2025, "Q2"),
    ("Standard Chartered", "STAN.L", 2025, "Q3"),
    ("Standard Chartered", "STAN.L", 2025, "Q4"),
    ("UnitedHealth", "UNH", 2025, "Q2"),
    ("UnitedHealth", "UNH", 2025, "Q3"),
    ("UnitedHealth", "UNH", 2025, "Q4"),
    ("Visa", "V", 2025, "Q1"),
    ("Visa", "V", 2025, "Q2"),
    ("Visa", "V", 2025, "Q3"),
    ("Visa", "V", 2026, "Q1"),
    ("Workday", "WDAY", 2025, "Q1"),
    ("Workday", "WDAY", 2025, "Q2"),
    ("Workday", "WDAY", 2025, "Q3"),
    ("Workday", "WDAY", 2025, "Q4"),
]

TICKER_TO_FOLDER = {
    "ABNB": "Airbnb", "AMZN": "Amazon", "AMD": "AMD", "AAPL": "Apple",
    "BAC": "bank of america", "BA": "Boeing", "CVS": "CVS Health",
    "SCHW": "Charles Schwab", "C": "Citigroup", "KO": "Coca-Cola",
    "COIN": "Coin Base", "DIS": "Disney", "LLY": "Eli Lilly",
    "GS": "Goldman Sachs", "IBM": "IBM", "JPM": "JPMC Documents",
    "LOW": "Lowe's", "LULU": "Lululemon", "AMKBY": "Maersk",
    "MCD": "McDonald's", "META": "META", "NFLX": "Netflix", "NKE": "Nike",
    "NVDA": "Nvidia", "TGT": "Target", "TSLA": "Tesla", "UBER": "Uber",
    "WMT": "Walmart",
    "BCS": "Barclays", "F": "Ford", "MSFT": "Microsoft", "PFE": "Pfizer",
    "UAL": "United Airlines",
}

TICKER_TO_SLUG = {
    "ABNB": "airbnb", "AMZN": "amazon", "AMD": "amd", "AAPL": "apple",
    "BAC": "bank_of_america", "BA": "boeing", "CVS": "cvs_health",
    "SCHW": "charles_schwab", "C": "citigroup", "KO": "coca_cola",
    "COIN": "coinbase", "DIS": "disney", "LLY": "eli_lilly",
    "GS": "goldman_sachs", "IBM": "ibm", "JPM": "jpm",
    "LOW": "lowes", "LULU": "lululemon", "AMKBY": "maersk",
    "MCD": "mcdonalds", "META": "meta", "NFLX": "netflix", "NKE": "nike",
    "NVDA": "nvidia", "TGT": "target", "TSLA": "tesla", "UBER": "uber",
    "WMT": "walmart",
    "BCS": "barclays", "F": "ford", "MSFT": "microsoft", "PFE": "pfizer",
    "UAL": "united_airlines",
    "PEP": "pepsico", "FDX": "fedex", "LMT": "lockheed_martin",
    "NVO": "novo_nordisk", "HLT": "hilton", "MC.PA": "lvmh",
    "ALV.DE": "allianz",
    "AVGO": "broadcom",
    "BKNG": "booking_holdings",
    "CAT": "caterpillar",
    "CL": "colgate_palmolive",
    "CMCSA": "comcast_corporation",
    "CMG": "chipotle",
    "COST": "costco",
    "CRM": "salesforce",
    "DAL": "delta_air_lines",
    "DELL": "dell",
    "EXPE": "expedia",
    "GIS": "general_mills",
    "GOOGL": "alphabet",
    "HOOD": "robinhood_markets",
    "JNJ": "johnson_johnson",
    "KHC": "kraft_heinz",
    "LIN": "linde",
    "LNVGY": "lenovo",
    "MET": "metlife",
    "MU": "micron",
    "ORCL": "oracle",
    "PINS": "pinterest",
    "PLTR": "palantir",
    "PUM.DE": "puma",
    "PYPL": "paypal",
    "RMSP.XC": "hermes",
    "SBUX": "starbucks",
    "SIE.DE": "siemens",
    "SPOT": "spotify",
    "STAN.L": "standard_chartered",
    "UNH": "unitedhealth",
    "V": "visa",
    "WDAY": "workday",
}

# The 6 tickers above have no OneDrive folder to scan at all (no drop for
# brand-new issuers) - deliberately absent from TICKER_TO_FOLDER so this
# script's scan doesn't emit noisy "MISSING FOLDER" lines for them; their
# manifests are hand-authored directly (see phase2/build_manifests.py's
# NEW_TICKER_MANIFESTS note) rather than discovered by this triage pass.

OVERLAP_ISSUERS = {"BAC", "BA", "DIS", "JPM", "NFLX", "TGT"}

EXTRACTABLE_SUFFIXES = {".pdf", ".html"}

# quarter+year patterns seen in these filenames/paths, cascaded most-specific first
QY_PATTERNS = [
    ("qy4", re.compile(r"q([1-4])[\s_-]*(?:fy)?(20\d{2})", re.IGNORECASE)),   # "q1 2026", "Q1-2026", "q1-fy2025"
    ("qy2", re.compile(r"q([1-4])[\s_-]*(?:fy)?(\d{2})(?!\d)", re.IGNORECASE)),  # "q1-25", "q1-fy25"
    ("yq", re.compile(r"([1-4])q[\s_-]*(\d{2})(?!\d)", re.IGNORECASE)),     # "1Q25", "1Q 25"
    ("yq4", re.compile(r"(20\d{2})[\s_-]*q([1-4])", re.IGNORECASE)),       # "2025-Q1", swapped order
]

ISO_DATE_PATTERN = re.compile(r"(20\d{2})[-_](\d{1,2})[-_](\d{1,2})")
MONTH_NAME_DATE_PATTERN = re.compile(
    r"(20\d{2})-([a-zA-Z]+)-(\d{1,2})|(\d{1,2})-([a-zA-Z]+)-(20\d{2})"
)
FOLDER_Q_PATTERN = re.compile(r"(?:^|[\\/])Q([1-4])(?:[\\/]|$)")

# Bare "Q<N>" subfolders with no year anywhere in the path (filenames like
# "Press-Release.pdf" with no date/quarter token) can't be resolved by regex
# alone - the ticker's fiscal year for that quarter has to be supplied. Boeing's
# Q4 folder (Press-Release.pdf, Presentation.pdf, Transcript.pdf, no year token
# in any filename) is the one case found so far; unlike Q1-Q3's filenames
# ("1Q25-Presentation.pdf") which embed the quarter+year directly.
FOLDER_ONLY_QUARTER_YEAR_OVERRIDES: dict[tuple[str, str], int] = {
    ("BA", "Q4"): 2025,
}

# Filenames with no quarter/date token regex can parse at all, resolved by
# reading the actual PDF content (opening-page date/fiscal-quarter line).
# BCS's "Sellside-Analyst-Meeting-Transcript.pdf" -> "Barclays PLC Q1 2026
# Results, 13 May 2026". MSFT's 3 "cdn-dynmedia-1.microsoft.com*.pdf" files ->
# fiscal-quarter labels read directly off each transcript's own title line
# (Microsoft's "FY<N> Q<N>" convention matches this project's Year/Quarter
# columns directly, confirmed against the target combos below).
FILENAME_QY_OVERRIDES: dict[tuple[str, str], tuple[str, int]] = {
    ("BCS", "Sellside-Analyst-Meeting-Transcript.pdf"): ("Q1", 2026),
    ("MSFT", "cdn-dynmedia-1.microsoft.com.pdf"): ("Q1", 2026),        # FY26 Q1, 29-Oct-2025 call
    ("MSFT", "cdn-dynmedia-1.microsoft.com (1).pdf"): ("Q2", 2025),    # FY25 Q2, 29-Jan-2025 call
    ("MSFT", "cdn-dynmedia-1.microsoft.com (2).pdf"): ("Q1", 2025),    # FY25 Q1, 30-Oct-2024 call
}

# Files present in a company's folder but not actually that company's document
# (drop-in mistake in the source drop) - excluded outright rather than assigned
# to any combo. "260505-1q-2026-earnings-release.pdf" under Microsoft/ is
# actually HSBC Holdings' Q1 2026 earnings release (verified by PDF content),
# not a Microsoft document at all.
EXCLUDE_MISFILED: dict[str, set[str]] = {
    "MSFT": {"260505-1q-2026-earnings-release.pdf"},
}


def infer_quarter_year(relpath: str, ticker: str | None = None) -> tuple[str, int] | None:
    text = relpath.replace("\\", "/")
    for label, pat in QY_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        g1, g2 = m.groups()
        if label in ("qy4", "qy2"):
            q, y = g1, g2
            year = int(y) if len(y) == 4 else 2000 + int(y)
            return f"Q{q}", year
        if label == "yq":
            q, yy = g1, g2
            return f"Q{q}", 2000 + int(yy)
        if label == "yq4":
            y, q = g1, g2
            return f"Q{q}", int(y)

    # bare Q<N> subfolder (e.g. "Q1/2025prqtr1rslt.pdf") - quarter from folder,
    # year from any 4-digit 20xx token anywhere in the path.
    fm = FOLDER_Q_PATTERN.search(text)
    if fm:
        ym = re.search(r"20\d{2}", text)
        if ym:
            return f"Q{fm.group(1)}", int(ym.group(0))
        quarter = f"Q{fm.group(1)}"
        if ticker is not None and (ticker, quarter) in FOLDER_ONLY_QUARTER_YEAR_OVERRIDES:
            return quarter, FOLDER_ONLY_QUARTER_YEAR_OVERRIDES[(ticker, quarter)]
    return None


def infer_iso_date(relpath: str) -> str | None:
    """Best-effort real calendar date extraction, for filenames that carry a
    release date but no explicit quarter token (used as a chronological-order
    fallback, not a primary match)."""
    text = relpath.replace("\\", "/")
    m = ISO_DATE_PATTERN.search(text)
    if m:
        y, mo, d = m.groups()
        try:
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        except ValueError:
            pass
    m = MONTH_NAME_DATE_PATTERN.search(text)
    if m:
        months = {name.lower(): i for i, name in enumerate(
            ["january", "february", "march", "april", "may", "june", "july",
             "august", "september", "october", "november", "december"], start=1)}
        if m.group(1):
            y, mon, d = m.group(1), m.group(2), m.group(3)
        else:
            d, mon, y = m.group(4), m.group(5), m.group(6)
        mon_num = months.get(mon.lower())
        if mon_num:
            try:
                return f"{int(y):04d}-{mon_num:02d}-{int(d):02d}"
            except ValueError:
                pass
    return None


def classify_doc_type(name: str) -> str:
    n = name.lower()
    if "press" in n or "press-release" in n or "prqtr" in n or n.startswith("0000"):
        return "Press Release"
    if "presentation" in n or "psqtr" in n:
        return "Earnings Presentation"
    if "transcript" in n or "call" in n:
        return "Earnings Call Transcript"
    if "supplement" in n or "supp" in n or "fsqtr" in n:
        return "Supplemental Information"
    if "predictions" in n or "summary" in n:
        return "Other (rater notes, not a source doc)"
    return "Unknown"


def main() -> None:
    report: dict[str, dict] = {}
    unmatched_files: dict[str, list[str]] = {}
    date_inferred_notes: list[str] = []

    for ticker, folder in TICKER_TO_FOLDER.items():
        print(f"[{ticker}] scanning {folder} ...", flush=True)
        company_dir = DOCS_ROOT / folder
        by_qy: dict[tuple[str, int], list[Path]] = {}
        dated_leftovers: list[tuple[str, Path]] = []  # (iso_date, file) - quarter unknown
        if not company_dir.exists():
            unmatched_files[ticker] = [f"MISSING FOLDER: {company_dir}"]
            continue
        for f in company_dir.rglob("*"):
            if not f.is_file():
                continue
            if f.name in EXCLUDE_MISFILED.get(ticker, set()):
                continue
            relpath = str(f.relative_to(company_dir))
            qy = FILENAME_QY_OVERRIDES.get((ticker, f.name)) or infer_quarter_year(relpath, ticker)
            if qy is None:
                iso = infer_iso_date(relpath)
                if iso and f.suffix.lower() in EXTRACTABLE_SUFFIXES:
                    dated_leftovers.append((iso, f))
                else:
                    unmatched_files.setdefault(ticker, []).append(relpath)
                continue
            by_qy.setdefault(qy, []).append(f)

        # Chronological-order fallback: some filenames carry a real release date
        # but no explicit quarter token (e.g. Target/Lowe's/Uber transcripts named
        # by date only). Sort those leftovers by date and zip them, in order,
        # against this ticker's target combos that regex-matching left empty -
        # both lists are naturally in fiscal-quarter order, so position-matching
        # is a reasonable heuristic. Flagged "date_inferred" for manual spot-check.
        missing_combos_sorted = sorted(
            [(y, q) for c, tk, y, q in TARGET_COMBOS if tk == ticker and (q, y) not in by_qy],
            key=lambda yq: (yq[0], yq[1]),
        )
        dated_leftovers.sort(key=lambda t: t[0])
        inferred_qy_for_file: dict[Path, tuple[str, int]] = {}
        for (year, quarter), (iso, f) in zip(missing_combos_sorted, dated_leftovers):
            inferred_qy_for_file[f] = (quarter, year)
            date_inferred_notes.append(f"{ticker} {year}{quarter} <- {f.name} (dated {iso})")
        for f, qy in inferred_qy_for_file.items():
            by_qy.setdefault(qy, []).append(f)
        leftover_unused = [f for _, f in dated_leftovers if f not in inferred_qy_for_file]
        for f in leftover_unused:
            unmatched_files.setdefault(ticker, []).append(str(f.relative_to(company_dir)) + " (dated, unassigned)")

        for company, tk, year, quarter in [c for c in TARGET_COMBOS if c[1] == ticker]:
            key = f"{ticker}_{year}_{quarter}"
            files = by_qy.get((quarter, year), [])
            entry = {"company": company, "ticker": ticker, "year": year, "quarter": quarter, "docs": []}
            for f in files:
                suffix = f.suffix.lower()
                doc_info = {
                    "path": str(f.relative_to(BASE_DIR)),
                    "doc_type": classify_doc_type(f.name),
                    "extractable": suffix in EXTRACTABLE_SUFFIXES,
                    "date_inferred": f in inferred_qy_for_file,
                }
                if suffix in EXTRACTABLE_SUFFIXES:
                    ok, size, err = quick_extract_check(f)
                    doc_info["file_bytes"] = size
                    doc_info["extract_ok"] = ok
                    if err:
                        doc_info["extract_error"] = err
                entry["docs"].append(doc_info)
            entry["n_docs"] = len(files)
            entry["n_extractable_ok"] = sum(1 for d in entry["docs"] if d.get("extract_ok"))
            entry["status"] = (
                "MISSING" if not files else
                "THIN(1 doc)" if entry["n_extractable_ok"] == 1 else
                "OK" if entry["n_extractable_ok"] >= 2 else
                "UNUSABLE(extraction failed)"
            )
            report[key] = entry

    out_path = BASE_DIR / "phase2" / "coverage_report.json"
    out_path.write_text(json.dumps({
        "combos": report,
        "unmatched_files": unmatched_files,
        "date_inferred_notes": date_inferred_notes,
    }, indent=2), encoding="utf-8")

    statuses = {}
    for v in report.values():
        statuses[v["status"]] = statuses.get(v["status"], 0) + 1
    print(f"Total target combos: {len(report)}")
    for status, count in sorted(statuses.items()):
        print(f"  {status}: {count}")
    print(f"\nDate-inferred (chronological fallback, spot-check these) - {len(date_inferred_notes)}:")
    for note in date_inferred_notes:
        print(f"  {note}")
    print(f"\nFull report: {out_path}")
    print(f"Unmatched (unparsed) files per ticker: {sum(len(v) for v in unmatched_files.values())} total")


if __name__ == "__main__":
    main()
