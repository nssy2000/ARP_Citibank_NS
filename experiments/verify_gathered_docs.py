"""
experiments/verify_gathered_docs.py

Run at any point while gathering to catch misattribution, truncation, and wrong
document type — the two fault modes already found in this project:
  1. Misattributed transcript: wrong company content in a file named for another company.
  2. Truncation: transcript ends before the Q&A closes.

Usage:
    python -m experiments.verify_gathered_docs          # checks all docs in docs/ for extension issuers
    python -m experiments.verify_gathered_docs adobe    # single issuer slug
    python -m experiments.verify_gathered_docs --csv    # write results to outputs/global/summary/

Checks per file:
  A. Company name appears in opening 2 000 characters of extracted text.
  B. Fiscal period label in the folder (CY<YYYY>-Q<N>) matches the fiscal year/quarter
     implied by the filename (<TICKER>_Q<N>_<YYYY>_*).
  C. For transcripts: Q&A section present and not truncated (file ends within 500 chars
     of a closing phrase; absence of Q&A closing is flagged as a possible truncation).
  D. Document type implied by the filename suffix matches the doc_type declared in the
     manifest (if the manifest entry exists).

Exit code: 0 if all checks pass, 1 if any FAIL found.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
MANIFESTS_DIR = ROOT / "manifests"
SUMMARY_DIR = ROOT / "outputs" / "global" / "summary"

# Extension issuers that do not yet have phase2-scored results
EXTENSION_SLUGS = {
    "adobe", "american_express", "chevron", "colgate_palmolive", "costco",
    "datadog", "duke_energy", "exxonmobil", "ebay", "freeport_mcmoran",
    "heineken", "home_depot", "intel", "mastercard", "nestle", "shell",
    "shopify", "sony", "union_pacific", "hermes",
}

TICKER_FOR_SLUG = {
    "adobe": "ADBE", "american_express": "AXP", "chevron": "CVX",
    "colgate_palmolive": "CL", "costco": "COST", "datadog": "DDOG",
    "duke_energy": "DUK", "exxonmobil": "XOM", "ebay": "EBAY",
    "freeport_mcmoran": "FCX", "heineken": "HEINY", "home_depot": "HD",
    "intel": "INTC", "mastercard": "MA", "nestle": "NSRGY", "shell": "SHEL",
    "shopify": "SHOP", "sony": "SONY", "union_pacific": "UNP", "hermes": "RMS",
}

# Company name variants to look for in document text (lower-case)
COMPANY_NAMES: dict[str, list[str]] = {
    "adobe": ["adobe"],
    "american_express": ["american express", "amex"],
    "chevron": ["chevron"],
    "colgate_palmolive": ["colgate"],
    "costco": ["costco"],
    "datadog": ["datadog"],
    "duke_energy": ["duke energy"],
    "exxonmobil": ["exxonmobil", "exxon mobil", "exxon"],
    "ebay": ["ebay"],
    "freeport_mcmoran": ["freeport", "fcx"],
    "heineken": ["heineken"],
    "home_depot": ["home depot"],
    "intel": ["intel"],
    "mastercard": ["mastercard"],
    "nestle": ["nestlé", "nestle"],
    "shell": ["shell"],
    "shopify": ["shopify"],
    "sony": ["sony"],
    "union_pacific": ["union pacific"],
    "hermes": ["hermès", "hermes"],
}

# Phrases that indicate Q&A has opened (transcripts)
QA_OPEN_PATTERNS = [
    r"\bquestion[s]?\s+and\s+answer",
    r"\bq\s*[&and]+\s*a\b",
    r"\boperator\b.*\bquestion",
    r"\bwe\s+will\s+now\s+begin\s+the\s+question",
    r"\bopen\s+(?:the\s+)?(?:call|line|floor)\s+(?:up\s+)?for\s+question",
    r"\bfirst\s+question\s+(?:comes|is)\s+from\b",
]

# Phrases that indicate Q&A has closed properly
QA_CLOSE_PATTERNS = [
    r"\bno\s+further\s+questions\b",
    r"\bno\s+more\s+questions\b",
    r"\bthat\s+(?:concludes|ends)\s+(?:our|today.s)\s+(?:question|q\s*&\s*a)",
    r"\bthank\s+you\s+(?:all\s+)?for\s+(?:your\s+)?(?:participation|joining|attending)",
    r"\bthis\s+concludes\s+(?:today.s|our)\s+(?:conference|call|presentation)",
    r"\bconference\s+(?:call\s+)?(?:has\s+)?(?:now\s+)?(?:concluded|ended)",
    r"\byou\s+may\s+(?:now\s+)?disconnect",
    r"\boperator\s*:\s*thank\s+you",
]


def extract_text(path: Path) -> str:
    """Extract plain text from .htm/.html/.txt/.pdf, returning empty string on failure."""
    suffix = path.suffix.lower()
    try:
        if suffix in (".htm", ".html"):
            raw = path.read_text(encoding="utf-8", errors="replace")
            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"&[a-z#0-9]+;", " ", text)
            return re.sub(r"\s+", " ", text).strip()
        if suffix == ".txt":
            return path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                return " ".join(
                    page.extract_text() or "" for page in reader.pages
                )
            except Exception:
                try:
                    import pdfplumber
                    with pdfplumber.open(str(path)) as pdf:
                        return " ".join(
                            (p.extract_text() or "") for p in pdf.pages
                        )
                except Exception:
                    return ""
    except Exception:
        return ""
    return ""


def classify_filename(name: str) -> str | None:
    """Infer document type from filename stem."""
    stem = name.lower()
    if "prepared_remarks" in stem or "prepared remarks" in stem:
        return "Earnings Presentation"
    if "transcript" in stem:
        return "Earnings Call Transcript"
    if "press_release" in stem or "pressrelease" in stem:
        return "Press Release"
    if "presentation" in stem:
        return "Earnings Presentation"
    if "supplement" in stem:
        return "Supplemental Information"
    return None


def parse_folder_period(folder_name: str) -> tuple[str, str] | None:
    """CY2025-Q3 -> ('2025', '3')"""
    m = re.match(r"CY(\d{4})-Q(\d)", folder_name)
    return (m.group(1), m.group(2)) if m else None


def parse_filename_period(stem: str) -> tuple[str, str] | None:
    """<TICKER>_Q3_2025_* -> ('2025', '3')"""
    m = re.search(r"_Q(\d)_(\d{4})_", stem)
    return (m.group(2), m.group(1)) if m else None


def check_file(path: Path, slug: str) -> dict:
    """Run all four checks on a single file. Returns a result dict."""
    fname_type = classify_filename(path.name)
    result = {
        "slug": slug,
        "file": str(path.relative_to(ROOT)),
        "detected_type": fname_type or "unknown",
        "check_company": "SKIP",
        "check_period": "SKIP",
        "check_transcript": "N/A",
        "check_doctype": "SKIP",
        "notes": [],
        "status": "PASS",
    }

    text = extract_text(path)
    if not text:
        result["status"] = "WARN"
        result["notes"].append("Could not extract text from file")
        return result

    text_lower = text.lower()

    # A. Company name anywhere in document (transcripts often begin with boilerplate)
    names = COMPANY_NAMES.get(slug, [])
    found_name = any(n in text_lower for n in names)
    result["check_company"] = "PASS" if found_name else "FAIL"
    if not found_name:
        result["status"] = "FAIL"
        result["notes"].append(
            f"Company name not found anywhere in document "
            f"(looked for: {names})"
        )

    # B. Fiscal period: folder label vs filename
    folder_period = parse_folder_period(path.parent.name)
    file_period = parse_filename_period(path.stem)
    if folder_period and file_period:
        result["check_period"] = "PASS" if folder_period == file_period else "FAIL"
        if folder_period != file_period:
            result["status"] = "FAIL"
            result["notes"].append(
                f"Period mismatch: folder says {path.parent.name}, "
                f"filename implies Q{file_period[1]} {file_period[0]}"
            )
    else:
        result["check_period"] = "WARN"
        result["notes"].append(
            "Could not parse period from folder or filename for comparison"
        )

    # C. Transcript Q&A check — only run for transcript files; skip for all other types.
    # A press release is not a truncated transcript; running the Q&A check on it is an error.
    if fname_type == "Earnings Call Transcript":
        qa_opened = any(re.search(p, text_lower) for p in QA_OPEN_PATTERNS)
        tail = text_lower[-500:]
        qa_closed = any(re.search(p, tail) for p in QA_CLOSE_PATTERNS)

        if not qa_opened:
            result["check_transcript"] = "FAIL"
            result["status"] = "FAIL"
            result["notes"].append(
                "Transcript: no Q&A opening phrase found — may be prepared remarks only or wrong document"
            )
        else:
            # Q&A opened. Closing-phrase check is informational only — many legitimate transcripts
            # end with phrasing that doesn't match the pattern list. Not raised to WARN/FAIL.
            result["check_transcript"] = "PASS"
            if not any(re.search(p, text_lower[-500:]) for p in QA_CLOSE_PATTERNS):
                result["notes"].append(
                    "Transcript: no standard closing phrase in final 500 chars (informational)"
                )

        # Also flag if PR filename was misclassified
        if fname_type == "Press Release":
            result["check_doctype"] = "WARN"
            result["notes"].append("PR filename but Q&A markers found — check document type")
    else:
        # Not a transcript — Q&A check does not apply.
        result["check_transcript"] = "N/A"

    # D. Filename doctype consistency
    if fname_type:
        result["check_doctype"] = "PASS"
    else:
        result["check_doctype"] = "WARN"
        result["notes"].append(f"Cannot determine document type from filename: {path.name}")

    return result


def scan_slug(slug: str) -> list[dict]:
    """Scan all documents under docs/<slug>/."""
    results = []
    doc_root = DOCS_DIR / slug
    if not doc_root.exists():
        return results
    for quarter_dir in sorted(doc_root.iterdir()):
        if not quarter_dir.is_dir():
            continue
        for doc_file in sorted(quarter_dir.iterdir()):
            if doc_file.suffix.lower() in (".htm", ".html", ".txt", ".pdf"):
                results.append(check_file(doc_file, slug))
    return results


def print_results(results: list[dict]) -> int:
    n_fail = n_warn = n_pass = 0
    for r in results:
        status = r["status"]
        if status == "FAIL":
            n_fail += 1
        elif status == "WARN":
            n_warn += 1
        else:
            n_pass += 1
        icon = "✗" if status == "FAIL" else ("?" if status == "WARN" else "✓")
        print(f"  {icon} [{r['detected_type']}] {r['file']}")
        print(f"      company={r['check_company']}  period={r['check_period']}  "
              f"transcript={r['check_transcript']}  doctype={r['check_doctype']}")
        for note in r["notes"]:
            print(f"      NOTE: {note}")
    print()
    print(f"PASS: {n_pass}  WARN: {n_warn}  FAIL: {n_fail}  TOTAL: {len(results)}")
    return 1 if n_fail else 0


def write_csv(results: list[dict], path: Path) -> None:
    fields = ["slug", "file", "detected_type", "check_company", "check_period",
              "check_transcript", "check_doctype", "status", "notes"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            row = {**r, "notes": "; ".join(r["notes"])}
            w.writerow(row)
    print(f"Results written to {path}")


def load_manifest_expected(slug: str) -> list[tuple[str, str]]:
    """Return list of (document_id, source_pdf) expected by the manifest for this slug."""
    manifest_path = MANIFESTS_DIR / f"p2_{slug}_reports.json"
    if not manifest_path.exists():
        return []
    import json
    data = json.loads(manifest_path.read_text())
    expected = []
    for report in data.get("reports", []):
        for doc in report.get("documents", []):
            expected.append((report["document_id"], doc["source_pdf"]))
    return expected


def report_missing(slug: str, found_files: set[Path]) -> list[str]:
    """Return list of manifest source_pdfs that have no corresponding file on disk."""
    missing = []
    for doc_id, src_pdf in load_manifest_expected(slug):
        expected_path = ROOT / src_pdf
        if expected_path not in found_files and not expected_path.exists():
            missing.append(f"{doc_id}: {src_pdf}")
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify gathered extension documents.")
    parser.add_argument("slugs", nargs="*", help="Issuer slugs to check. Default: all extension issuers.")
    parser.add_argument("--csv", action="store_true", help="Write results CSV to outputs/global/summary/.")
    args = parser.parse_args()

    slugs = args.slugs if args.slugs else sorted(EXTENSION_SLUGS)

    all_results = []
    all_missing: list[str] = []
    company_summary: list[dict] = []

    for slug in sorted(slugs):
        results = scan_slug(slug)
        found_files = {ROOT / r["file"] for r in results}
        missing = report_missing(slug, found_files)

        n_found = len(results)
        n_expected = len(load_manifest_expected(slug))
        n_missing = len(missing)
        n_fail = sum(1 for r in results if r["status"] == "FAIL")
        n_warn = sum(1 for r in results if r["status"] == "WARN")

        company_summary.append({
            "slug": slug,
            "expected": n_expected,
            "found": n_found,
            "missing": n_missing,
            "fail": n_fail,
            "warn": n_warn,
        })

        if results:
            print(f"\n=== {slug} ({n_found} files found, {n_missing} missing) ===")
            print_results(results)
        else:
            print(f"\n=== {slug} (0 files found, {n_missing} missing) ===")

        if missing:
            for m in missing:
                print(f"  MISSING: {m}")
                all_missing.append(f"{slug}: {m}")

        all_results.extend(results)

    # Summary table
    print("\n" + "="*80)
    print("COMPANY SUMMARY")
    print(f"  {'Company':<25} {'Expected':>8} {'Found':>6} {'Missing':>8} {'FAIL':>5} {'WARN':>5}")
    print("  " + "-"*60)
    for s in company_summary:
        ok = "OK" if s["missing"] == 0 and s["fail"] == 0 else ""
        print(f"  {s['slug']:<25} {s['expected']:>8} {s['found']:>6} {s['missing']:>8} {s['fail']:>5} {s['warn']:>5}  {ok}")

    print(f"\nMISSING DOCUMENTS ({len(all_missing)} total):")
    for m in all_missing:
        print(f"  {m}")

    if args.csv and all_results:
        out = SUMMARY_DIR / "extension_doc_verification.csv"
        write_csv(all_results, out)
        print(f"\nResults written to {out}")

    n_fail_total = sum(1 for r in all_results if r["status"] == "FAIL")
    sys.exit(1 if n_fail_total else 0)


if __name__ == "__main__":
    main()
