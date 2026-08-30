"""
Per-section attribution check (Control A) and source provenance sweep (Control B).

Control A: Splits each extracted text into sections by '=== ... ===' headers,
counts issuer vs other-issuer name mentions per 1000 words within each section,
and flags sections where:
  - The issuer's own name/ticker is absent (0 mentions) while another issuer is present
  - OR another issuer's mentions exceed the own issuer's mentions within that section

Control B: Scans all manifests and extracted texts for Insider Monkey and
Globe and Mail sourced documents.

Usage:
    python -m experiments.section_attribution_check
"""

import csv
import json
import os
import re
from collections import defaultdict
from datetime import datetime


BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAL_CSV = os.path.join(BASE, "outputs", "global", "summary",
                       "global_outcome_calibration_phase2.csv")
ATTR_CSV = os.path.join(BASE, "outputs", "global", "summary",
                        "company_attribution_check.csv")
OUT_SECTION = os.path.join(BASE, "outputs", "global", "summary",
                           "section_attribution_check.csv")
OUT_PROVENANCE = os.path.join(BASE, "outputs", "global", "summary",
                              "source_provenance_sweep.csv")
MANIFESTS_DIR = os.path.join(BASE, "manifests")


def build_issuer_names():
    """Build issuer -> (company_name, ticker, [search_terms]) from manifests."""
    mapping = {}
    for f in sorted(os.listdir(MANIFESTS_DIR)):
        if not f.startswith("p2_") or not f.endswith("_reports.json"):
            continue
        with open(os.path.join(MANIFESTS_DIR, f)) as fh:
            data = json.load(fh)
        issuer = f.replace("_reports.json", "")
        reports = data.get("reports", [])
        if not reports:
            continue
        r = reports[0]
        company = data.get("company_name", r.get("company", ""))
        ticker = r.get("ticker", "")

        # Build search terms: company name, ticker, and common variants
        terms = set()
        if company:
            terms.add(company.lower())
            # Also add without common suffixes/prefixes
            for variant in [company]:
                terms.add(variant.lower())
        if ticker:
            terms.add(ticker.lower())

        mapping[issuer] = {
            "company": company,
            "ticker": ticker,
            "terms": terms,
        }

    # Add expanded search terms for companies that need them
    expansions = {
        "p2_airbnb": ["airbnb"],
        "p2_alphabet": ["alphabet", "google", "googl"],
        "p2_amazon": ["amazon", "amzn", "aws"],
        "p2_apple": ["apple", "aapl"],
        "p2_bank_of_america": ["bank of america", "bac", "bofa"],
        "p2_boeing": ["boeing", "ba"],
        "p2_booking_holdings": ["booking", "bkng", "booking holdings"],
        "p2_broadcom": ["broadcom", "avgo"],
        "p2_caterpillar": ["caterpillar", "cat"],
        "p2_charles_schwab": ["charles schwab", "schwab", "schw"],
        "p2_chipotle": ["chipotle", "cmg"],
        "p2_citigroup": ["citigroup", "citi", "citibank"],
        "p2_coca_cola": ["coca-cola", "coca cola", "coke", "ko"],
        "p2_coinbase": ["coinbase", "coin"],
        "p2_comcast_corporation": ["comcast", "cmcsa", "nbcuniversal"],
        "p2_cvs_health": ["cvs health", "cvs"],
        "p2_dell": ["dell", "dell technologies"],
        "p2_delta_air_lines": ["delta air lines", "delta air", "delta airlines", "dal"],
        "p2_disney": ["disney", "walt disney", "dis"],
        "p2_eli_lilly": ["eli lilly", "lilly", "lly"],
        "p2_expedia": ["expedia", "expe"],
        "p2_fedex": ["fedex", "fdx"],
        "p2_ford": ["ford motor", "ford"],
        "p2_general_mills": ["general mills", "gis"],
        "p2_goldman_sachs": ["goldman sachs", "goldman", "gs"],
        "p2_hilton": ["hilton", "hlt"],
        "p2_ibm": ["ibm"],
        "p2_johnson_johnson": ["johnson & johnson", "johnson and johnson",
                                "j&j", "jnj"],
        "p2_jpm": ["jpmorgan", "jp morgan", "jpm", "j.p. morgan", "chase"],
        "p2_kraft_heinz": ["kraft heinz", "kraft", "khc"],
        "p2_lenovo": ["lenovo", "lnvgy"],
        "p2_linde": ["linde", "lin"],
        "p2_lockheed_martin": ["lockheed martin", "lockheed", "lmt"],
        "p2_lowes": ["lowe's", "lowes", "low"],
        "p2_lululemon": ["lululemon", "lulu"],
        "p2_lvmh": ["lvmh", "mc.pa", "louis vuitton"],
        "p2_maersk": ["maersk", "amkby", "a.p. moller"],
        "p2_marriott": ["marriott", "mar"],
        "p2_mcdonalds": ["mcdonald's", "mcdonalds", "mcd"],
        "p2_meta": ["meta platforms", "meta", "facebook"],
        "p2_metlife": ["metlife", "met"],
        "p2_micron": ["micron", "mu"],
        "p2_microsoft": ["microsoft", "msft"],
        "p2_netflix": ["netflix", "nflx"],
        "p2_nike": ["nike", "nke"],
        "p2_novo_nordisk": ["novo nordisk", "novo", "nvo"],
        "p2_nvidia": ["nvidia", "nvda"],
        "p2_oracle": ["oracle", "orcl"],
        "p2_palantir": ["palantir", "pltr"],
        "p2_paypal": ["paypal", "pypl"],
        "p2_pepsico": ["pepsico", "pepsi", "pep"],
        "p2_pfizer": ["pfizer", "pfe"],
        "p2_pinterest": ["pinterest", "pins"],
        "p2_puma": ["puma", "pum.de"],
        "p2_robinhood_markets": ["robinhood", "hood"],
        "p2_salesforce": ["salesforce", "crm"],
        "p2_siemens": ["siemens", "sie.de"],
        "p2_spotify": ["spotify", "spot"],
        "p2_standard_chartered": ["standard chartered", "stan.l"],
        "p2_starbucks": ["starbucks", "sbux"],
        "p2_target": ["target", "tgt"],
        "p2_tesla": ["tesla", "tsla"],
        "p2_uber": ["uber"],
        "p2_united_airlines": ["united airlines", "ual"],
        "p2_unitedhealth": ["unitedhealth", "unitedhealthcare", "unh", "optum"],
        "p2_visa": ["visa"],
        "p2_walmart": ["walmart", "wal-mart", "wmt"],
        "p2_workday": ["workday", "wday"],
        "p2_colgate_palmolive": ["colgate-palmolive", "colgate", "cl"],
        "p2_costco": ["costco", "cost"],
        "p2_allianz": ["allianz", "alv.de"],
    }

    for issuer, extra_terms in expansions.items():
        if issuer in mapping:
            for t in extra_terms:
                mapping[issuer]["terms"].add(t.lower())

    return mapping


def count_mentions(text, terms):
    """Count mentions of any term from `terms` in `text` (case-insensitive).
    Uses word-boundary matching to avoid partial matches."""
    text_lower = text.lower()
    total = 0
    for term in terms:
        # Use word boundary regex for accurate counting
        pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
        total += len(pattern.findall(text_lower))
    return total


def word_count(text):
    """Count words in text."""
    return len(text.split())


def split_sections(text):
    """Split extracted text into sections by '=== ... ===' headers.
    Returns list of (header, section_text) tuples."""
    pattern = re.compile(r'^(=== .+ ===)$', re.MULTILINE)
    parts = pattern.split(text)

    sections = []
    # parts[0] is text before first header (usually empty)
    i = 1
    while i < len(parts):
        header = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        sections.append((header, body))
        i += 2

    return sections


def issuer_from_slug(slug):
    """Extract issuer slug from an output path like outputs/p2_spotify/..."""
    return slug


def run_control_a():
    """Per-section attribution check."""
    print("=== Control A: Per-section attribution check ===")

    issuer_names = build_issuer_names()

    # Read calibration CSV for event list
    events = []
    with open(CAL_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            events.append(row)

    run_id = f"section_attr_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    results = []
    flag_count = 0
    flagged_events = set()

    # Ambiguous short terms that should be excluded from "other issuer" matching
    # when they're too common as regular English words
    AMBIGUOUS_TERMS = {
        "f", "c", "v", "met", "cat", "low", "mar", "mu",
        "delta", "visa", "ford", "target", "chase", "novo",
        "linde", "oracle", "uber", "hood", "meta",
        "cost",  # Costco ticker, but "cost" is ubiquitous in financial docs
        "dis",   # Disney ticker, but common word
        "gis",   # General Mills ticker, but GIS is a common acronym
        "lin",   # Linde ticker, but common word fragment
        "ba",    # Boeing ticker, but common word/abbreviation
        "dal",   # Delta ticker
        "gs",    # Goldman ticker
        "ko",    # Coca-Cola ticker
        "cl",    # Colgate ticker, but common abbreviation
        "hlt",   # Hilton ticker
    }

    for event in events:
        issuer = event["issuer"]
        doc_id = event["document_id"]
        ticker = event["ticker"]

        # Find extracted text
        ext_path = os.path.join(BASE, "outputs", issuer, "extracted",
                                f"{doc_id}.txt")
        if not os.path.exists(ext_path):
            continue

        with open(ext_path) as f:
            full_text = f.read()

        sections = split_sections(full_text)
        if not sections:
            continue

        own_info = issuer_names.get(issuer)
        if not own_info:
            continue

        own_terms = own_info["terms"]

        for header, body in sections:
            wc = word_count(body)
            if wc < 10:  # Skip trivially short sections
                continue

            own_count = count_mentions(body, own_terms)
            own_per_1k = round(own_count / wc * 1000, 2) if wc > 0 else 0

            # Check all other issuers
            best_other_issuer = ""
            best_other_per_1k = 0.0
            best_other_count = 0

            for other_issuer, other_info in issuer_names.items():
                if other_issuer == issuer:
                    continue

                # Filter out ambiguous short terms for other-issuer matching
                safe_terms = set()
                for t in other_info["terms"]:
                    if t.lower() not in AMBIGUOUS_TERMS:
                        safe_terms.add(t)

                if not safe_terms:
                    continue

                other_count = count_mentions(body, safe_terms)
                if other_count > 0:
                    other_per_1k = round(other_count / wc * 1000, 2)
                    if other_per_1k > best_other_per_1k:
                        best_other_per_1k = other_per_1k
                        best_other_issuer = other_issuer
                        best_other_count = other_count

            # Flag conditions
            flagged = False
            flag_reason = ""

            if own_count == 0 and best_other_count > 0:
                flagged = True
                flag_reason = (f"own_absent; other '{best_other_issuer}' "
                               f"has {best_other_per_1k}/1k")
            elif best_other_per_1k > own_per_1k and best_other_count > 0:
                flagged = True
                flag_reason = (f"other_exceeds_own; '{best_other_issuer}' "
                               f"{best_other_per_1k}/1k > own {own_per_1k}/1k")

            if flagged:
                flag_count += 1
                flagged_events.add(doc_id)

            results.append({
                "document_id": doc_id,
                "section_header": header,
                "own_mentions_per_1k": own_per_1k,
                "top_other_issuer": best_other_issuer,
                "top_other_mentions_per_1k": best_other_per_1k,
                "flagged": flagged,
                "flag_reason": flag_reason,
                "run_id": run_id,
            })

    # Write output
    fieldnames = ["document_id", "section_header", "own_mentions_per_1k",
                  "top_other_issuer", "top_other_mentions_per_1k",
                  "flagged", "flag_reason", "run_id"]
    with open(OUT_SECTION, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Positive control check
    spot_flagged = any(r["document_id"] == "SPOT_FQ1_2026" and r["flagged"]
                       for r in results)

    print(f"\nResults written to {OUT_SECTION}")
    print(f"Total sections analyzed: {len(results)}")
    print(f"Sections flagged: {flag_count}")
    print(f"Unique events with flagged sections: {len(flagged_events)}")
    print(f"\nPositive control (SPOT_FQ1_2026 transcript): "
          f"{'PASS - flagged' if spot_flagged else 'FAIL - not flagged'}")

    # Print flagged sections
    print(f"\n--- Flagged sections ---")
    for r in results:
        if r["flagged"]:
            print(f"  {r['document_id']} | {r['section_header']} | "
                  f"own={r['own_mentions_per_1k']}/1k | "
                  f"{r['top_other_issuer']}={r['top_other_mentions_per_1k']}/1k | "
                  f"{r['flag_reason']}")

    return results, spot_flagged


def run_control_b():
    """Source provenance sweep for Insider Monkey and Globe and Mail."""
    print("\n\n=== Control B: Source provenance sweep ===")

    publisher_patterns = {
        "Insider Monkey": ["insider monkey", "insidermonkey", "insider_monkey"],
        "Globe and Mail": ["globe and mail", "theglobeandmail", "globeandmail",
                           "globe_and_mail"],
    }

    results = []

    # 1. Check manifest source_pdf paths
    for f in sorted(os.listdir(MANIFESTS_DIR)):
        if not f.startswith("p2_") or not f.endswith("_reports.json"):
            continue
        with open(os.path.join(MANIFESTS_DIR, f)) as fh:
            data = json.load(fh)

        for report in data.get("reports", []):
            doc_id = report.get("document_id", "")
            for doc in report.get("documents", []):
                src = doc.get("source_pdf", "")
                src_lower = src.lower()
                for pub_name, patterns in publisher_patterns.items():
                    if any(p in src_lower for p in patterns):
                        results.append({
                            "document_id": doc_id,
                            "doc_type": doc.get("doc_type", ""),
                            "source_pdf": os.path.basename(src),
                            "publisher": pub_name,
                            "detection_source": "manifest_filename",
                        })

    # 2. Check extracted text for source attribution lines
    ext_hits = []
    for issuer_dir in sorted(os.listdir(os.path.join(BASE, "outputs"))):
        ext_dir = os.path.join(BASE, "outputs", issuer_dir, "extracted")
        if not os.path.isdir(ext_dir):
            continue
        for txt_file in sorted(os.listdir(ext_dir)):
            if not txt_file.endswith(".txt"):
                continue
            doc_id = txt_file.replace(".txt", "")
            fpath = os.path.join(ext_dir, txt_file)

            # Already found in manifest? Just check for Globe and Mail in text
            # since it might not be in the filename
            with open(fpath) as fh:
                content = fh.read()

            content_lower = content.lower()
            for pub_name, patterns in publisher_patterns.items():
                if any(p in content_lower for p in patterns):
                    # Check if already captured from manifest
                    already = any(
                        r["document_id"] == doc_id and r["publisher"] == pub_name
                        for r in results
                    )
                    if not already:
                        ext_hits.append({
                            "document_id": doc_id,
                            "doc_type": "(detected in extracted text)",
                            "source_pdf": "(see extracted text)",
                            "publisher": pub_name,
                            "detection_source": "extracted_text",
                        })

    results.extend(ext_hits)

    # Write output
    fieldnames = ["document_id", "doc_type", "source_pdf", "publisher",
                  "detection_source"]
    with open(OUT_PROVENANCE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Counts
    im_manifest = sum(1 for r in results
                      if r["publisher"] == "Insider Monkey"
                      and r["detection_source"] == "manifest_filename")
    im_text = sum(1 for r in results
                  if r["publisher"] == "Insider Monkey"
                  and r["detection_source"] == "extracted_text")
    gm_manifest = sum(1 for r in results
                      if r["publisher"] == "Globe and Mail"
                      and r["detection_source"] == "manifest_filename")
    gm_text = sum(1 for r in results
                  if r["publisher"] == "Globe and Mail"
                  and r["detection_source"] == "extracted_text")

    print(f"\nResults written to {OUT_PROVENANCE}")
    print(f"\nInsider Monkey:")
    print(f"  In manifest filenames: {im_manifest} documents")
    print(f"  In extracted text only: {im_text} documents")
    print(f"  Total: {im_manifest + im_text}")
    print(f"\nGlobe and Mail:")
    print(f"  In manifest filenames: {gm_manifest} documents")
    print(f"  In extracted text only: {gm_text} documents")
    print(f"  Total: {gm_manifest + gm_text}")

    # List all
    print(f"\n--- All detected documents ---")
    for r in sorted(results, key=lambda x: (x["publisher"], x["document_id"])):
        print(f"  {r['publisher']} | {r['document_id']} | "
              f"{r['doc_type']} | {r['source_pdf']} | "
              f"via {r['detection_source']}")

    return results


if __name__ == "__main__":
    os.chdir(BASE)
    section_results, spot_ok = run_control_a()
    provenance_results = run_control_b()
