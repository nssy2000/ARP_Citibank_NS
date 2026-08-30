"""Tier-1 scripted sourcing: for SEC-registered gap tickers, locate the
earnings-release 8-K's EX-99.1 exhibit (the near-universal press-release
exhibit convention) via EDGAR's submissions API, and download it. Zero LLM
tokens - deterministic filing lookup only.

Exhibit discovery reads the filing's own detail index page (the
"-index.htm" page, not the bare accession directory listing) and parses its
"Document Format Files" table for the row whose SEC-assigned Type column is
exactly EX-99.1. This is more reliable than pattern-matching the exhibit's
filename, which is an unenforced convention - some filers name it
"exhibit991q...", others omit "ex"/"99" from the filename entirely.

Rerunning this script is idempotent: any combo that already has a
"Press Release" document is skipped outright, so a rerun only touches the
combos still missing one. Progress is persisted after every combo so one
bad combo's exception can't lose earlier results.

Presentation and transcript documents are NOT reliably on EDGAR (rarely
filed as exhibits, never as full transcripts) - those, the news digest, and
anything this script can't confidently resolve stay Tier-2 (background
subagent web search), regardless of SEC-registrant status.
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import date
from pathlib import Path

from lxml import html as lxml_html

from checkpoint_io import GAP_COMBOS_PATH, save_gap_combos

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DOCS_ROOT = BASE_DIR / "docs"

HEADERS = {"User-Agent": "citibank-apr-research bencrowe01@gmail.com"}
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
QUARTER_NUM = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def find_earnings_8k_filing(cik: int, report_date: date) -> dict | None:
    """Returns {"accno_nodash", "accno_dashed", "filed"} for the single 8-K
    (item 2.02, Results of Operations) filed within 5 days of report_date.
    None if zero or multiple candidates (ambiguous - leave for Tier 2)."""
    data = fetch_json(EDGAR_SUBMISSIONS_URL.format(cik=cik))
    recent = data["filings"]["recent"]
    candidates = []
    for i, form in enumerate(recent["form"]):
        if form != "8-K":
            continue
        if "2.02" not in recent.get("items", [""])[i]:
            continue
        filed = date.fromisoformat(recent["filingDate"][i])
        if abs((filed - report_date).days) > 5:
            continue
        accno_dashed = recent["accessionNumber"][i]
        candidates.append({
            "accno_nodash": accno_dashed.replace("-", ""),
            "accno_dashed": accno_dashed,
            "filed": filed.isoformat(),
        })
    return candidates[0] if len(candidates) == 1 else None


def find_ex99_1_url(cik: int, accno_nodash: str, accno_dashed: str) -> tuple[str | None, bool]:
    """Fetches the filing's detail index page (the "-index.htm" page) and
    parses its "Document Format Files" table for the row whose Type column
    is exactly EX-99.1 (case-insensitive; EX-99.2/99.3/etc. are excluded).

    Returns (url_or_None, table_found). table_found=False is a stronger,
    more specific signal than table_found=True with url=None: the page
    fetched fine but had no Document Format Files / tableFile table at all,
    which points at a genuine parser regression (SEC markup change, or the
    wrong page fetched) rather than a filing that legitimately lacks an
    EX-99.1 exhibit. Callers should surface these two cases separately
    rather than folding both into one generic "skipped" bucket."""
    index_page_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/{accno_nodash}/"
        f"{accno_dashed}-index.htm"
    )
    tree = lxml_html.fromstring(fetch_text(index_page_url))
    tables = tree.xpath('//table[@summary="Document Format Files"]')
    if not tables:
        tables = tree.xpath('//table[contains(concat(" ", @class, " "), " tableFile ")]')
    if not tables:
        print(
            "WARNING: no Document Format Files table found on "
            f"{index_page_url} - page structure may have changed"
        )
        return None, False
    for table in tables:
        for row in table.xpath(".//tr"):
            cells = row.xpath("./td")
            if len(cells) < 4:
                continue
            if cells[3].text_content().strip().upper() != "EX-99.1":
                continue
            hrefs = cells[2].xpath(".//a/@href")
            if not hrefs:
                continue
            href = hrefs[0]
            if href.startswith("/ix?doc="):
                href = href[len("/ix?doc="):]
            return "https://www.sec.gov" + href, True
    return None, True


def has_press_release(combo: dict) -> bool:
    return any(d.get("doc_type") == "Press Release" for d in combo.get("documents", []))


def process_combo(key: str, combo: dict) -> tuple[str, str]:
    """Attempts Tier-1 resolution for one combo, mutating it in place on
    success. Returns (status, message) with status "resolved", "skipped",
    or "structure_warning" (the index page had no Document Format Files
    table at all - a likely parser regression, distinct from a filing that
    legitimately has no EX-99.1 exhibit)."""
    report_date = date.fromisoformat(combo["report_date"])
    filing = find_earnings_8k_filing(combo["cik"], report_date)
    if filing is None:
        return "skipped", f"{key}: no unambiguous 8-K (item 2.02) within 5 days of {report_date}"

    index_dir_url = (
        f"https://www.sec.gov/Archives/edgar/data/{combo['cik']}/{filing['accno_nodash']}/"
    )
    doc_url, table_found = find_ex99_1_url(combo["cik"], filing["accno_nodash"], filing["accno_dashed"])
    if not table_found:
        return "structure_warning", (
            f"{key}: WARNING no Document Format Files table found on the index page "
            f"for {index_dir_url} - page structure may have changed"
        )
    if doc_url is None:
        return "skipped", f"{key}: 8-K found ({index_dir_url}) but no EX-99.1 exhibit in it"

    fq = QUARTER_NUM[combo["quarter"]]
    dest_dir = DOCS_ROOT / combo["slug"] / f"CY{combo['year']}-Q{fq}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "press_release.htm"
    dest_path.write_bytes(fetch_bytes(doc_url))

    combo.setdefault("documents", []).append({
        "doc_type": "Press Release",
        "source_pdf": str(dest_path.relative_to(BASE_DIR)).replace("\\", "/"),
    })
    combo["notes"] = (
        combo["notes"] + f" Tier1: press release from {doc_url} (filed {filing['filed']})."
    ).strip()
    return "resolved", key


def main() -> None:
    combos = json.loads(GAP_COMBOS_PATH.read_text(encoding="utf-8"))
    targets = {
        k: c for k, c in combos.items()
        if c.get("is_sec_registrant")
        and c.get("report_date")
        and c["status"] == "report_date_resolved"
        and not has_press_release(c)
    }
    print(f"{len(targets)} SEC-registered combos with a resolved report_date and no Press Release yet")

    resolved, skipped, structure_warnings = 0, [], []
    for key, combo in sorted(targets.items()):
        try:
            status, msg = process_combo(key, combo)
        except Exception as exc:  # noqa: BLE001 - one bad combo must not kill the run
            skipped.append(f"{key}: error: {exc}")
        else:
            if status == "resolved":
                resolved += 1
                save_gap_combos(combos)  # persist incrementally so progress survives a later crash
            elif status == "structure_warning":
                structure_warnings.append(msg)
            else:
                skipped.append(msg)
        finally:
            time.sleep(0.15)  # SEC's fair-use rate-limit guidance, once per combo regardless of outcome

    save_gap_combos(combos)
    print(f"Tier-1 resolved press releases for {resolved} combos")
    print(f"{len(skipped)} need Tier-2 (subagent) for at least the press release:")
    for s in skipped:
        print(" ", s)
    if structure_warnings:
        print(
            f"\n{len(structure_warnings)} combo(s) hit a DISTINCT warning, not counted in the "
            "ordinary Tier-2 skip total above: the EDGAR index page fetched fine but had no "
            "Document Format Files table at all, which points at a parser regression (SEC "
            "markup change, or the wrong page fetched) rather than a filing that legitimately "
            "lacks an EX-99.1 exhibit:"
        )
        for s in structure_warnings:
            print(" ", s)
    print("\nEven Tier-1-resolved combos still need Tier-2 for presentation + transcript + news digest.")


if __name__ == "__main__":
    main()
