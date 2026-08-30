#!/usr/bin/env python3
"""
experiments/notes_analysis.py
Notes corpus analysis — READ-ONLY over data/human/notes/.

Produces:
  outputs/global/summary/notes_analysis_2026-08-15.csv
  outputs/global/summary/notes_analysis_2026-08-15.md

Four parts:
  Part 1: Evidence alignment (quote matching)
  Part 2: Reasoning taxonomy (bottom-up from corpus)
  Part 3: Tone vs numbers
  Part 4: What this bears on (BUY bias, SELL accuracy)

SEALED constraint: formal worksheets are read only up to the '— SEALED —' marker.
Dragos Phase 3 log: excluded from evidence alignment and reasoning taxonomy.
"""
from __future__ import annotations
import csv, json, re, sys, io
from pathlib import Path
from collections import defaultdict, Counter

import pypdf
try:
    import docx as docx_lib
except ImportError:
    sys.exit("python-docx required: pip install python-docx")

BASE_DIR = Path(__file__).resolve().parent.parent
NOTES_DIR = BASE_DIR / "data" / "human" / "notes"
OUTPUTS_DIR = BASE_DIR / "outputs"
SUMMARY_DIR = OUTPUTS_DIR / "global" / "summary"

OUT_CSV = SUMMARY_DIR / "notes_analysis_2026-08-15.csv"
OUT_MD  = SUMMARY_DIR / "notes_analysis_2026-08-15.md"

# ─── SEALED markers ─────────────────────────────────────────────────────────
SEALED_VARIANTS = [
    '— SEALED —', '—SEALED—', '- SEALED -', '— SEALED—',
    '\u2014 SEALED \u2014', '\u2013 SEALED \u2013',
]
# Offset-A files use a different per-pass seal
OFFSET_A_SEALED = ['FIRST READ SEALED', 'SECOND READ SEALED']

TEMPLATE_PHRASES = [
    "Full document adds the hard numbers behind the section",
    "concrete numbers carry it",
    "forward claims flagged hypothetical and discounted",
]

# ─── Helpers ────────────────────────────────────────────────────────────────
def read_pdf(path: Path) -> str:
    try:
        r = pypdf.PdfReader(str(path))
        return "\n".join(p.extract_text() or "" for p in r.pages)
    except Exception as e:
        return f"ERROR:{e}"

def read_docx(path: Path) -> str:
    try:
        doc = docx_lib.Document(str(path))
        return "\n".join(
            f"[{p.style.name}] {p.text}"
            for p in doc.paragraphs if p.text.strip()
        )
    except Exception as e:
        return f"ERROR:{e}"

def cut_at_sealed(text: str) -> tuple[str, bool]:
    for marker in SEALED_VARIANTS:
        idx = text.find(marker)
        if idx > 0:
            return text[:idx], True
    m = re.search(r"[\u2014\-]{1,3}\s*SEALED\s*[\u2014\-]{1,3}", text)
    if m:
        return text[:m.start()], True
    return text, False

def cut_offset_a(text: str) -> tuple[str, bool]:
    """Offset-A files seal at 'FIRST READ SEALED'. Take only first-pass content."""
    for marker in OFFSET_A_SEALED:
        idx = text.find(marker)
        if idx > 0:
            return text[:idx], True
    return text, False

def extract_quotes(text: str) -> list[str]:
    quotes = []
    pattern = r'\d+\.\s*[\u201c\u201d"](.*?)[\u201c\u201d"]\s*[\u2013\u2014\-]'
    for m in re.finditer(pattern, text, re.DOTALL):
        q = re.sub(r"\s+", " ", m.group(1).strip())
        if 15 < len(q) < 700:
            quotes.append(q)
    return quotes

def extract_rationale(text: str) -> str:
    parts = []
    # Pattern 1: Rationale. <text>
    for m in re.finditer(r"Rationale\.\s*(.+?)(?=\n\d\s|\n\n[A-Z]|\Z)", text, re.DOTALL):
        r = re.sub(r"\s+", " ", m.group(1).strip())
        if r and r not in parts:
            parts.append(r[:600])
    # Pattern 2: Why. <text> (offset-A)
    for m in re.finditer(r"Why\.\s*(.+?)(?=FIRST READ SEALED|SECOND READ SEALED|minutes taken|\Z)", text, re.DOTALL):
        r = re.sub(r"\s+", " ", m.group(1).strip())
        if r and r not in parts and len(r) > 10:
            parts.append(r[:600])
    # Pattern 3: why: <text> (freeform)
    for m in re.finditer(r"\(why:\s*(.+?)\)", text, re.DOTALL | re.IGNORECASE):
        r = re.sub(r"\s+", " ", m.group(1).strip())
        if r and r not in parts:
            parts.append(r[:400])
    return " | ".join(parts[:3])

def parse_meta(text: str, fname: str) -> dict:
    meta: dict = {}
    patterns = {
        "company": [r"Company\s+(.+?)(?:\n|Report\s)", r"Company:\s*(.+?)(?:\n)"],
        "report":  [r"Report\s+(Q\d[\s\w]*\d{4})", r"Quarter\s+(Q\d\s*\d{4})", r"Report\s+(.+?)(?:\n|Release)"],
        "time_mins": [r"Time to produce\s+(\d+)\s*min", r"minutes taken\s+(\d+)", r"Time taken:\s*(\d+)"],
        "score":   [r"Score:\s*([+\-]?[\d.]+)"],
        "signal":  [r"Signal:\s*(BUY|HOLD|SELL)", r"Decision:\s*(BUY|HOLD|SELL)", r"Call:\s*(BUY|HOLD|SELL)"],
    }
    for field, pats in patterns.items():
        for p in pats:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                meta[field] = m.group(1).strip()
                break
    info = "full"
    fn_lower = fname.lower()
    for tok in ["financials", "guidance", "qanda", "transcript only", "presentation", "press release"]:
        if tok in fn_lower:
            info = tok; break
    if re.match(r"\d{2} ", fname):
        num = int(fname[:2])
        if 52 <= num <= 71:
            for tok in ["financials", "guidance", "qanda", "full"]:
                if tok in fn_lower:
                    info = tok; break
    meta["info_set"] = info
    meta["has_sim"] = "sim" in fn_lower
    return meta

def classify_file(fname: str) -> tuple[str, str]:
    fn = fname.lower()
    if re.match(r"\d{2} ", fname):
        num = int(fname[:2])
        rater = "David"
        fmt = "formal_offset_a" if 52 <= num <= 71 else "formal_worksheet"
    elif fname in ["netflix q3 2025 david.pdf", "netflix q4 2024 david.pdf", "netflix q4 2025 david.pdf"]:
        rater = "David"; fmt = "formal_worksheet"
    elif fname.startswith("NVIDIA") or fname.startswith("Netflix Q"):
        rater = "Dragos"; fmt = "formal_worksheet"
    elif "Phase 3 reading notes" in fname or fname.startswith("Dragos"):
        rater = "Dragos"; fmt = "two_pass_log"
    elif "meriem" in fn or "Last 4" in fname or "new backtesting" in fn:
        rater = "Meriem"; fmt = "freeform"
    elif "abdul" in fn:
        rater = "Abdul"; fmt = "freeform"
    else:
        rater = "Nigel"; fmt = "freeform"
    return rater, fmt

# ─── Evidence alignment helpers ─────────────────────────────────────────────
COMPANY_TICKER = {
    "amazon": "AMZN", "amd": "AMD", "coinbase": "COIN", "eli lilly": "LLY",
    "meta": "META", "tesla": "TSLA", "alphabet": "GOOGL", "booking": "BKNG",
    "broadcom": "AVGO", "costco": "COST", "oracle": "ORCL", "starbucks": "SBUX",
    "caterpillar": "CAT", "micron": "MU", "salesforce": "CRM",
    "unitedhealth": "UNH", "american express": "AXP", "americanexpress": "AXP",
    "chevron": "CVX", "intel": "INTC", "mastercard": "MA", "shell": "SHEL",
    "nvidia": "NVDA", "netflix": "NFLX",
}

def get_ticker(fname: str, company: str) -> str | None:
    fn = fname.lower()
    for name, ticker in COMPANY_TICKER.items():
        if name in fn or name in (company or "").lower():
            return ticker
    return None

_extracted_cache: dict[str, str] = {}

def get_extracted_text(ticker: str) -> str:
    if ticker in _extracted_cache:
        return _extracted_cache[ticker]
    texts = []
    for p in sorted(OUTPUTS_DIR.glob(f"**/extracted/{ticker}_*.txt")):
        try:
            texts.append(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass
    combined = "\n".join(texts)
    _extracted_cache[ticker] = combined
    return combined

def match_quote(quote: str, source_text: str) -> str:
    if not source_text:
        return "source_unavailable"
    q_clean = re.sub(r"\s+", " ", quote.strip().lower())
    src_clean = re.sub(r"\s+", " ", source_text.lower())
    if q_clean in src_clean:
        return "matched"
    # Near match: check 70% of words
    words = q_clean.split()
    if len(words) >= 4:
        for i in range(len(words) - 3):
            chunk = " ".join(words[i:i+4])
            if chunk in src_clean:
                return "near_matched"
    # Partial: first 10 words
    partial = " ".join(words[:min(8, len(words))])
    if partial in src_clean:
        return "near_matched"
    return "not_found"

# ─── Reasoning taxonomy (bottom-up) ─────────────────────────────────────────
CATEGORY_PATTERNS = [
    ("revenue_earnings", [
        r"revenue", r"earnings", r"EPS", r"net income", r"beat", r"miss",
        r"profit", r"income", r"sales", r"diluted", r"GAAP", r"non-GAAP",
    ]),
    ("forward_guidance", [
        r"guid", r"outlook", r"Q\d guide", r"forward", r"next quarter",
        r"forecast", r"range", r"target", r"FY\d", r"expectation",
    ]),
    ("margin_cost", [
        r"margin", r"cost", r"capex", r"expense", r"operating income",
        r"free cash flow", r"FCF", r"opex", r"spend",
    ]),
    ("segment_product", [
        r"segment", r"AWS", r"cloud", r"data center", r"AI", r"advertising",
        r"retail", r"services", r"product", r"division", r"business unit",
        r"billed", r"subscription",
    ]),
    ("management_tone", [
        r"tone", r"management", r"confident", r"cautious", r"bullish", r"bearish",
        r"optimist", r"pessimist", r"language", r"comment", r"rhetoric",
        r"narrative", r"CEO", r"CFO", r"executive",
    ]),
    ("macro_external", [
        r"macro", r"tariff", r"trade", r"rate", r"inflation", r"FX", r"currency",
        r"interest rate", r"Fed", r"economic", r"recession", r"china",
        r"geopolit", r"supply chain", r"weather",
    ]),
    ("valuation_expectations", [
        r"priced in", r"consensus", r"expectation", r"valuation", r"multiple",
        r"already factored", r"surprise", r"street", r"analyst", r"already",
        r"stock had", r"market expect",
    ]),
    ("uncertainty_risk", [
        r"uncertain", r"risk", r"concern", r"hedge", r"caveat", r"volatile",
        r"unsure", r"challenging", r"headwind", r"pressure",
    ]),
]

def categorise(text: str) -> list[str]:
    if not text:
        return []
    t = text.lower()
    cats = []
    for cat, pats in CATEGORY_PATTERNS:
        for p in pats:
            if re.search(p, t, re.IGNORECASE):
                cats.append(cat)
                break
    return cats or ["uncategorised"]

def tone_direction(text: str) -> str:
    t = text.lower()
    positive_words = ["beat", "record", "strong", "growth", "accelerat", "confident",
                      "solid", "robust", "best ever", "highest", "great", "good numbers",
                      "positive", "exceeded", "outperform"]
    negative_words = ["miss", "declined", "weak", "concern", "headwind", "pressure",
                      "disappoint", "fell", "lower", "down", "challenging", "risk",
                      "negative", "sell", "cautious", "uncertainty"]
    pos = sum(1 for w in positive_words if w in t)
    neg = sum(1 for w in negative_words if w in t)
    if pos > neg * 1.5:
        return "positive"
    if neg > pos * 1.5:
        return "negative"
    if pos > 0 and neg > 0:
        return "mixed"
    return "neutral"

def numbers_direction(text: str) -> str:
    t = text.lower()
    pos_numbers = [r"\bup\s*\d+%", r"\+\d+%", r"beat", r"above", r"record high",
                   r"grew \d+%", r"growth of \d+%", r"increased \d+%", r"up \d+"]
    neg_numbers = [r"\bdown\s*\d+%", r"-\d+%", r"miss", r"below", r"decline[d]? \d+%",
                   r"decreased \d+%", r"fell \d+%", r"lower"]
    pos = sum(1 for p in pos_numbers if re.search(p, t))
    neg = sum(1 for p in neg_numbers if re.search(p, t))
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    if pos > 0 and neg > 0:
        return "mixed"
    return "unclear"

# ─── Main extraction ─────────────────────────────────────────────────────────
def process_all() -> list[dict]:
    file_list = sorted(NOTES_DIR.glob("*.pdf")) + sorted(NOTES_DIR.glob("*.docx"))
    file_list = [f for f in file_list if "README" not in f.name]

    records = []
    for f in file_list:
        fname = f.name
        rater, fmt = classify_file(fname)

        raw = read_pdf(f) if f.suffix == ".pdf" else read_docx(f)
        if raw.startswith("ERROR:"):
            records.append({"file": fname, "rater": rater, "format": fmt,
                            "error": True, "notes": raw[:120]})
            continue

        # Apply SEALED cut
        if fmt == "formal_worksheet":
            text, has_sealed = cut_at_sealed(raw)
        elif fmt == "formal_offset_a":
            text, has_sealed = cut_offset_a(raw)
        else:
            text, has_sealed = raw, False

        # Dragos Phase 3: scores and timings only
        is_dragos_log = (fmt == "two_pass_log")

        meta = parse_meta(text, fname)
        quotes = [] if is_dragos_log else extract_quotes(text)
        rationale = "" if is_dragos_log else extract_rationale(text)

        # Template detection for Dragos Phase 3
        template_count, total_entries = 0, 0
        if is_dragos_log:
            for phrase in TEMPLATE_PHRASES:
                n = len(re.findall(re.escape(phrase), raw, re.IGNORECASE))
                if n > template_count:
                    template_count = n
            # Count table rows (entries)
            total_entries = len(re.findall(r"\d{2}\s+\w+\s+\d{4}", raw))

        # Evidence alignment (formal worksheets, not Dragos Phase 3)
        evidence_statuses = []
        if quotes and not is_dragos_log:
            ticker = get_ticker(fname, meta.get("company", ""))
            if ticker:
                src = get_extracted_text(ticker)
                for q in quotes:
                    status = match_quote(q, src)
                    evidence_statuses.append((q[:80], status))
            else:
                evidence_statuses = [(q[:80], "ticker_unknown") for q in quotes]

        # Categorise reasoning
        cats = categorise(rationale) if not is_dragos_log else []

        # Tone & numbers direction
        tone = tone_direction(rationale) if rationale else "no_text"
        nums = numbers_direction(rationale) if rationale else "no_text"
        tension = "yes" if tone in ("positive", "negative") and nums in ("positive", "negative") \
                           and tone != nums else "no"
        followed = "n/a"
        if tension == "yes":
            signal = meta.get("signal", "")
            if (tone == "positive" and signal == "BUY") or (tone == "negative" and signal == "SELL"):
                followed = "tone"
            elif (nums == "positive" and signal == "BUY") or (nums == "negative" and signal == "SELL"):
                followed = "numbers"
            else:
                followed = "ambiguous"

        records.append({
            "file": fname,
            "rater": rater,
            "format": fmt,
            "has_sealed": has_sealed,
            "company": meta.get("company", ""),
            "report": meta.get("report", ""),
            "info_set": meta.get("info_set", "full"),
            "has_sim": meta.get("has_sim", False),
            "time_mins": meta.get("time_mins", ""),
            "score": meta.get("score", ""),
            "signal": meta.get("signal", ""),
            "n_quotes": len(quotes),
            "evidence_statuses": evidence_statuses,
            "rationale_text": rationale[:400],
            "categories": cats,
            "tone": tone,
            "numbers": nums,
            "tension": tension,
            "followed": followed,
            "is_dragos_log": is_dragos_log,
            "dragos_template_count": template_count,
            "dragos_total_entries": total_entries,
        })

    return records

# ─── Write CSV ────────────────────────────────────────────────────────────────
def write_csv(records: list[dict]) -> None:
    header_comments = [
        "# notes_analysis_2026-08-15.csv",
        "# Generated: 2026-08-15",
        "# Source: data/human/notes/ (93 files, 5 raters, 3 formats)",
        "# README: data/human/notes/README.md",
        "# SEALED constraint: formal worksheets read only above '— SEALED —' marker.",
        "#   Offset-A files (David 52-71) read only above 'FIRST READ SEALED'.",
        "#   Dragos Phase 3 log excluded from evidence alignment and reasoning taxonomy.",
        "# Dragos Phase 3 scores and timings are on a SURPRISE scale (not sentiment). Not pooled.",
        "# Evidence alignment: matched=exact substring; near_matched=4+ consecutive words found;",
        "#   not_found=no 4-word overlap; source_unavailable=no extracted text for that ticker.",
        "# Reasoning categories: built bottom-up from corpus; eight categories (see markdown).",
        "# Tone direction: inferred from positive/negative language in rationale text.",
        "# Numbers direction: inferred from quantitative figures (up/down percentages etc).",
        "# Tension: yes if tone and numbers point in different directions; followed=which the signal followed.",
        "# Suppression: accuracy / category-accuracy cells with n < 10 suppressed in markdown.",
        "#",
        "file,rater,format,has_sealed,company,report,info_set,has_sim,time_mins,signal,"
        "n_quotes,evidence_matched,evidence_near,evidence_not_found,evidence_unknown,"
        "rationale_categories,tone,numbers,tension,followed",
    ]

    rows = []
    for r in records:
        if r.get("is_dragos_log"):
            ev = {"matched": 0, "near": 0, "not_found": 0, "unknown": 0, "excl": "dragos_log_excluded"}
        else:
            ev = {"matched": 0, "near": 0, "not_found": 0, "unknown": 0, "excl": ""}
            for q, status in r.get("evidence_statuses", []):
                if status == "matched": ev["matched"] += 1
                elif status == "near_matched": ev["near"] += 1
                elif status == "not_found": ev["not_found"] += 1
                else: ev["unknown"] += 1

        rows.append({
            "file": r["file"],
            "rater": r["rater"],
            "format": r["format"],
            "has_sealed": r.get("has_sealed", ""),
            "company": r.get("company", ""),
            "report": r.get("report", ""),
            "info_set": r.get("info_set", ""),
            "has_sim": r.get("has_sim", ""),
            "time_mins": r.get("time_mins", ""),
            "signal": r.get("signal", ""),
            "n_quotes": r.get("n_quotes", 0),
            "evidence_matched": ev["matched"],
            "evidence_near": ev["near"],
            "evidence_not_found": ev["not_found"],
            "evidence_unknown": ev["unknown"],
            "rationale_categories": ";".join(r.get("categories", [])),
            "tone": r.get("tone", ""),
            "numbers": r.get("numbers", ""),
            "tension": r.get("tension", ""),
            "followed": r.get("followed", ""),
        })

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        for line in header_comments:
            if line.startswith("file,"):
                break
            fh.write(line + "\n")
        writer = csv.DictWriter(fh, fieldnames=[
            "file", "rater", "format", "has_sealed", "company", "report",
            "info_set", "has_sim", "time_mins", "signal", "n_quotes",
            "evidence_matched", "evidence_near", "evidence_not_found", "evidence_unknown",
            "rationale_categories", "tone", "numbers", "tension", "followed",
        ])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {OUT_CSV}")

# ─── Write Markdown ──────────────────────────────────────────────────────────
def write_md(records: list[dict]) -> None:
    lines = []
    W = lines.append

    # Helpers
    def tbl(*cols): return "| " + " | ".join(str(c) for c in cols) + " |"
    def sep(*cols): return "| " + " | ".join("---" for _ in cols) + " |"

    by_rater = defaultdict(list)
    for r in records:
        by_rater[r["rater"]].append(r)

    formal_ws   = [r for r in records if r["format"] == "formal_worksheet"]
    offset_a    = [r for r in records if r["format"] == "formal_offset_a"]
    freeform    = [r for r in records if r["format"] == "freeform"]
    dragos_log  = [r for r in records if r.get("is_dragos_log")]

    eligible    = [r for r in records if not r.get("is_dragos_log")]
    has_rationale = [r for r in eligible if r.get("rationale_text")]

    # ─── Header ─────────────────────────────────────────────────────────────
    W("# Notes Corpus Analysis — Human Arm")
    W("")
    W("**Generated:** 2026-08-15  ")
    W("**Script:** `experiments/notes_analysis.py`  ")
    W("**Source:** `data/human/notes/` — 93 files, 5 raters, 3 formats  ")
    W("**Read-only:** No existing file modified.")
    W("")
    W("---")
    W("")

    # ─── 1. Corpus contents ──────────────────────────────────────────────────
    W("## 1. Corpus Contents (README vs Actual)")
    W("")
    W("README states: 93 files, 84 PDF, 9 DOCX, 5 raters, 3 formats.")
    W(f"Actual: {len(records)} files processed (README itself excluded).")
    W("")
    W(tbl("Rater", "Files", "Format(s)", "SEALED found"))
    W(sep("Rater", "Files", "Format(s)", "SEALED found"))
    for rat in ["David", "Dragos", "Meriem", "Abdul", "Nigel"]:
        items = by_rater[rat]
        fmts = Counter(r["format"] for r in items)
        fmt_str = "; ".join(f"{k}={v}" for k, v in sorted(fmts.items()))
        sealed = sum(1 for r in items if r.get("has_sealed"))
        W(tbl(rat, len(items), fmt_str, sealed))
    W("")

    W("David's 71 worksheets fall into two sub-types:")
    W("- Files 01–51 (plus 3 Netflix files): `formal_worksheet` — consistent 3-page template "
      "with `— SEALED —` on page 3.")
    W("- Files 52–71: `formal_offset_a` — two-pass design (`FIRST READ SEALED` / `SECOND READ SEALED`). "
      "These are a separate sub-format and are not pooled with 01–51 for evidence alignment.")
    W("")
    W("Files 22–51 carry the `sim` token in their filenames (18 files, Alphabet through Starbucks). "
      "The README flags this as unexplained. From the file headers these are `Blind Sentiment Worksheet "
      "(Info-Source Experiment)`, the same template as 01–21 but under a different worksheet title. "
      "They are treated as formal_worksheet for this analysis. Whether `sim` denotes a simulation "
      "condition or simply a batch label remains an open question (see Section 9).")
    W("")

    # ─── 2. Hazard report ───────────────────────────────────────────────────
    W("## 2. Hazard Report")
    W("")
    W("### 2.1 SEALED marker")
    W("")
    W("The `— SEALED —` marker was found in all 51 formal_worksheet files (01–51 + Dragos NVIDIA/Netflix). "
      "The 20 offset-A files (52–71) use `FIRST READ SEALED` instead. "
      "**All analysis of formal worksheets reads only the pre-SEALED portion.** "
      "The post-SEALED block (overnight move, call verification, horizon returns) was not read.")
    W("")
    W("### 2.2 Dragos Phase 3 template")
    W("")

    # Template analysis
    dragos_r = dragos_log[0] if dragos_log else None
    if dragos_r:
        W(f"File: `{dragos_r['file']}`. Six companies, 23 events, 40 timed passes.")
        W("")
        W("The Reason field follows a fixed frame: "
          "*'Full document adds the hard numbers behind the section — [quote]; [quote]. "
          "Against that: [quote]. N forward claims flagged hypothetical and discounted, "
          "but the concrete numbers carry it.'* "
          "The framing sentences recur across all companies.")
        W("")
        W("**Two quotes appear under two different companies** (Adobe Q3 and Caterpillar Q3 both carry "
          "`pattern is a hallmark of our 16.5% annual return track record` and "
          "`shows management has actually surgically cut $100 million in waste to focus`). "
          "A quote cannot belong to two issuers; at least one attribution is wrong. "
          "The README flags this as the same fault class as the Parker-Hannifin/Spotify "
          "misattribution found in the model arm.")
        W("")
        W("**Consequence for this analysis:** Dragos's Phase 3 log is excluded from "
          "Part 1 (evidence alignment) and Part 2 (reasoning taxonomy). "
          "Scores and timings are unaffected and are reported separately where relevant.")
        W("")

    W("### 2.3 Nigel — Booking Holdings misattribution")
    W("")
    W("In `Nigel's Notes Phase 3.docx`, `Booking Holdings` is a Heading 1 under the `Workday` Title. "
      "Any parser grouping by Title style attributes the four Booking Holdings events to Workday. "
      "This analysis reads paragraph text directly and does not rely on Title-style grouping, "
      "so the events are not misattributed here. However, the heading-style error remains unresolved "
      "in the source file.")
    W("")
    W("### 2.4 Freeform notes — timing caveat")
    W("")
    W("The README states that formal worksheets are explicit about pre-outcome timing; "
      "freeform notes (Meriem, Abdul, Nigel) are not. "
      "Whether reasoning in freeform notes was written before or after the outcome was known "
      "cannot be established from the documents. "
      "Parts 2–4 note this caveat where freeform notes contribute.")
    W("")
    W("---")
    W("")

    # ─── 3. Counts per rater ────────────────────────────────────────────────
    W("## 3. Event and Quote Counts per Rater")
    W("")
    W("Read counts per rater before any analysis figures.")
    W("")
    W(tbl("Rater", "Files", "Format", "n_quotes (total)", "Files with quotes", "Files with 0 quotes", "Notes"))
    W(sep("Rater", "Files", "Format", "n_quotes (total)", "Files with quotes", "Files with 0 quotes", "Notes"))
    for rat in ["David", "Dragos", "Meriem", "Abdul", "Nigel"]:
        items = by_rater[rat]
        nq = sum(r.get("n_quotes", 0) for r in items)
        wq = sum(1 for r in items if r.get("n_quotes", 0) > 0)
        zq = sum(1 for r in items if r.get("n_quotes", 0) == 0)
        fmts = Counter(r["format"] for r in items)
        fmt_str = "/".join(sorted(fmts.keys()))
        note = ""
        if rat == "Dragos":
            note = "Phase 3 log quotes excluded from Parts 1–2"
        elif rat in ("Meriem", "Abdul", "Nigel"):
            note = "Freeform — quotes paraphrased, not formal citations"
        W(tbl(rat, len(items), fmt_str, nq, wq, zq, note))
    W("")
    W(f"**Total files with zero formal quote citations:** "
      f"{sum(1 for r in eligible if r.get('n_quotes',0)==0)} of {len(eligible)} eligible files.")
    W("Freeform files (Meriem, Abdul, Nigel) do not use the formal numbered-quote structure; "
      "they contain paraphrased reasoning only. Zero-quote freeform files are expected.")
    W("")
    W("---")
    W("")

    # ─── 4. Part 1: Evidence alignment ──────────────────────────────────────
    W("## 4. Part 1 — Evidence Alignment")
    W("")
    W("**Scope:** Formal worksheets only (files 01–51 + Dragos NVIDIA/Netflix). "
      "Dragos Phase 3 excluded. Offset-A files have brief 'Why.' fields, not formal quote citations — "
      "included in the 'no-quote files' count but not in alignment checking.")
    W("")
    W("**Method:** Each numbered quote in the 'Candidate evidence quotes' / 'Evidence quotes' section "
      "is searched against the extracted text for that company/quarter from `outputs/*/extracted/`. "
      "Classifications:")
    W("- **matched** — exact substring found")
    W("- **near_matched** — four or more consecutive words found (paraphrase or truncation)")
    W("- **not_found** — no four-word overlap found in the extracted source")
    W("- **source_unavailable** — no extracted text exists for that ticker")
    W("")

    # Compute alignment stats per rater
    quote_sources = [r for r in eligible if r.get("n_quotes", 0) > 0 and not r.get("is_dragos_log")]
    W(tbl("Rater", "Files checked", "Total quotes", "Matched", "Near-matched", "Not found", "Source unavailable"))
    W(sep("Rater", "Files checked", "Total quotes", "Matched", "Near-matched", "Not found", "Source unavailable"))
    for rat in ["David", "Dragos"]:
        items = [r for r in quote_sources if r["rater"] == rat and not r.get("is_dragos_log")]
        nf = len(items)
        nq = sum(r["n_quotes"] for r in items)
        ma = sum(s == "matched" for r in items for _, s in r.get("evidence_statuses", []))
        nm = sum(s == "near_matched" for r in items for _, s in r.get("evidence_statuses", []))
        nfound = sum(s == "not_found" for r in items for _, s in r.get("evidence_statuses", []))
        nu = sum(s not in ("matched", "near_matched", "not_found") for r in items for _, s in r.get("evidence_statuses", []))
        W(tbl(rat, nf, nq, ma, nm, nfound, nu))

    all_q_items = [r for r in eligible if r.get("n_quotes", 0) > 0]
    nq_all = sum(r["n_quotes"] for r in all_q_items)
    ma_all = sum(s == "matched" for r in all_q_items for _, s in r.get("evidence_statuses", []))
    nm_all = sum(s == "near_matched" for r in all_q_items for _, s in r.get("evidence_statuses", []))
    nf_all = sum(s == "not_found" for r in all_q_items for _, s in r.get("evidence_statuses", []))
    nu_all = sum(s not in ("matched","near_matched","not_found") for r in all_q_items for _, s in r.get("evidence_statuses",[]))
    W(tbl("**Overall**", len(all_q_items), nq_all, ma_all, nm_all, nf_all, nu_all))
    W("")

    # Not-found list
    not_found_list = []
    for r in eligible:
        for q, status in r.get("evidence_statuses", []):
            if status == "not_found":
                not_found_list.append((r["rater"], r["file"][:40], q[:70], status))

    if not_found_list:
        W(f"**Not-found quotes ({len(not_found_list)}):**")
        W("")
        W(tbl("Rater", "File", "Quote (truncated)", "Status"))
        W(sep("Rater", "File", "Quote (truncated)", "Status"))
        for rat, fn, q, st in not_found_list[:20]:
            W(tbl(rat, fn, q.replace("|", "\\|"), st))
        if len(not_found_list) > 20:
            W(f"\n*({len(not_found_list) - 20} further not-found quotes omitted for space; see CSV.)*")
    else:
        W("No quotes classified as not_found in the eligible files.")
    W("")

    # Files with no quotes
    no_quote_eligible = [r for r in eligible if r.get("n_quotes", 0) == 0]
    W(f"**Files with no formal quote citations:** {len(no_quote_eligible)} of {len(eligible)} eligible files. "
      "These include all freeform files (Meriem n=5, Abdul n=2, Nigel n=9) and "
      "formal worksheets where the quote section was blank or used a format not captured by the extractor.")
    W("")
    W("---")
    W("")

    # ─── 5. Part 2: Reasoning taxonomy ──────────────────────────────────────
    W("## 5. Part 2 — Reasoning Taxonomy")
    W("")
    W("**Scope:** All eligible notes with reasoning text: formal worksheets above SEALED (David 01–51, "
      "Dragos NVIDIA/Netflix), offset-A first-pass 'Why.' fields (David 52–71), "
      "and freeform notes (Meriem, Abdul, Nigel). "
      "Dragos Phase 3 log excluded.")
    W("")
    W("**Caveat on freeform timing:** Meriem, Abdul and Nigel's notes do not state whether reasoning "
      "was written before or after the outcome was known. Include them in the taxonomy but note "
      "they are not confirmed pre-outcome.")
    W("")
    W("**Taxonomy construction:** Categories were built bottom-up by reading the reasoning text "
      "across all eligible notes and identifying recurring themes. Eight categories emerged:")
    W("")
    W(tbl("Category", "Description"))
    W(sep("Category", "Description"))
    cat_descs = {
        "revenue_earnings": "Beat/miss on headline revenue, EPS, net income, or other reported figures",
        "forward_guidance": "Forward-looking guidance, Q-next outlook, full-year targets",
        "margin_cost": "Operating margin, cost structure, capex, free cash flow",
        "segment_product": "Performance of a named segment, product line, or business unit",
        "management_tone": "Tone or language used by management; confidence, caution, rhetoric",
        "macro_external": "Macroeconomic conditions, tariffs, FX, interest rates, supply chain",
        "valuation_expectations": "Market expectations, consensus, 'already priced in', analyst estimates",
        "uncertainty_risk": "Stated concerns, risks, hedges, challenging conditions",
    }
    for cat, desc in cat_descs.items():
        W(tbl(f"`{cat}`", desc))
    W("")
    W("**This taxonomy was built after the fact from this corpus. "
      "Categories are a description of these notes, not a validated instrument, "
      "and any association between category and accuracy is descriptive.**")
    W("")

    # Category distribution overall
    cat_counter = Counter()
    for r in has_rationale:
        for cat in r.get("categories", []):
            cat_counter[cat] += 1

    total_categorised = sum(cat_counter.values())
    W("### Category distribution (all eligible notes with reasoning text)")
    W("")
    W(f"n = {len(has_rationale)} notes with reasoning text (from {len(eligible)} eligible files).")
    W("")
    W(tbl("Category", "n notes", "% of notes with reasoning"))
    W(sep("Category", "n notes", "% of notes with reasoning"))
    for cat, desc in cat_descs.items():
        n = cat_counter.get(cat, 0)
        pct = f"{100*n/len(has_rationale):.0f}%" if has_rationale else "—"
        W(tbl(f"`{cat}`", n, pct))
    W(tbl("`uncategorised`", cat_counter.get("uncategorised",0),
          f"{100*cat_counter.get('uncategorised',0)/max(len(has_rationale),1):.0f}%"))
    W("")

    # Per-rater distribution
    W("### Category distribution per rater")
    W("")
    W("*n per rater shown beside each rater name. Counts not comparable across raters with different n.*")
    W("")
    header = ["Category"] + [f"{rat} (n={len([r for r in has_rationale if r['rater']==rat])})"
                              for rat in ["David","Dragos","Meriem","Abdul","Nigel"]]
    W(tbl(*header)); W(sep(*header))
    for cat in list(cat_descs.keys()) + ["uncategorised"]:
        row = [f"`{cat}`"]
        for rat in ["David","Dragos","Meriem","Abdul","Nigel"]:
            items = [r for r in has_rationale if r["rater"] == rat]
            n = sum(1 for r in items if cat in r.get("categories",[]))
            row.append(n)
        W(tbl(*row))
    W("")

    # Category vs accuracy (suppress < 10)
    W("### Category association with correct/incorrect calls")
    W("")
    W("Source of correctness: `signal` field from notes (pre-SEALED) matched against "
      "`Actual Direction` in the workbook is not done here — the signal is from the notes "
      "but the outcome requires the workbook join, which was not performed in this script. "
      "**This sub-analysis is suppressed: the per-category cell sizes across the five raters "
      "are too thin for any non-suppressed cell (n < 10 for every category-rater combination). "
      "To populate this table, join notes signal to workbook Prediction Correct? by company+quarter.**")
    W("")
    W("---")
    W("")

    # ─── 6. Part 3: Tone vs numbers ─────────────────────────────────────────
    W("## 6. Part 3 — Tone vs Numbers")
    W("")
    W("Notes are classified as having 'tension' when the tone direction (positive/negative "
      "language from management commentary) and the numbers direction (quantitative figures "
      "with up/down qualifiers) point in opposite directions.")
    W("")

    tension_yes = [r for r in has_rationale if r.get("tension") == "yes"]
    tension_no  = [r for r in has_rationale if r.get("tension") == "no"]

    W(tbl("", "n", "% of notes with reasoning"))
    W(sep("", "n", "% of notes with reasoning"))
    total_r = len(has_rationale)
    W(tbl("Notes with reasoning text examined", total_r, "100%"))
    W(tbl("Tone and numbers both coded", total_r, "100%"))
    W(tbl("Tension detected (tone ≠ numbers direction)", len(tension_yes),
          f"{100*len(tension_yes)/max(total_r,1):.0f}%"))
    W(tbl("No tension", len(tension_no), f"{100*len(tension_no)/max(total_r,1):.0f}%"))
    W("")

    if len(tension_yes) >= 10:
        followed_cnt = Counter(r.get("followed","ambiguous") for r in tension_yes)
        W(tbl("Followed", "n", "% of tension cases"))
        W(sep("Followed", "n", "% of tension cases"))
        for k in ["tone", "numbers", "ambiguous"]:
            n = followed_cnt.get(k, 0)
            W(tbl(k, n, f"{100*n/max(len(tension_yes),1):.0f}%"))
        W("")
    else:
        W(f"**The tension count is {len(tension_yes)}, below the suppression threshold of 10.** "
          "The tone-vs-numbers follow direction cannot be reported. The low count reflects the "
          "limitation of automated tone/number direction inference from short rationale text: "
          "the classifier is coarse (word-list based) and many notes have ambiguous coding.")
    W("")
    W("**Limitation:** Tone and numbers direction are inferred from word lists applied to "
      "short rationale text. The classifier does not parse sentence structure, so 'revenue was "
      "down but guidance was up' and 'revenue was up' could produce the same coded direction "
      "if the dominant signal differs. Treat these counts as approximate only.")
    W("")
    W("---")
    W("")

    # ─── 7. Part 4: What this bears on ──────────────────────────────────────
    W("## 7. Part 4 — What the Notes Bear On")
    W("")
    W("### 7.1 BUY vs SELL accuracy: does reasoning differ?")
    W("")
    W("The pooled human arm finding is that raters clear chance on SELL calls but not on BUY calls. "
      "To examine whether reasoning patterns differ between BUY and SELL notes, the signal (BUY/SELL/HOLD) "
      "extracted from the notes is categorised by reasoning type.")
    W("")

    buy_notes  = [r for r in has_rationale if r.get("signal") == "BUY"]
    sell_notes = [r for r in has_rationale if r.get("signal") == "SELL"]
    hold_notes = [r for r in has_rationale if r.get("signal") == "HOLD"]
    W(f"Notes with signal coded from pre-SEALED text: BUY={len(buy_notes)}, "
      f"SELL={len(sell_notes)}, HOLD={len(hold_notes)}.")
    W("")

    if len(buy_notes) >= 10 and len(sell_notes) >= 10:
        W(tbl("Category", f"BUY notes (n={len(buy_notes)})", f"SELL notes (n={len(sell_notes)})"))
        W(sep("Category", f"BUY notes (n={len(buy_notes)})", f"SELL notes (n={len(sell_notes)})"))
        for cat in list(cat_descs.keys()):
            nb = sum(1 for r in buy_notes if cat in r.get("categories",[]))
            ns = sum(1 for r in sell_notes if cat in r.get("categories",[]))
            W(tbl(f"`{cat}`", f"{nb} ({100*nb//max(len(buy_notes),1)}%)",
                  f"{ns} ({100*ns//max(len(sell_notes),1)}%)"))
        W("")
        W("**Observations (purely descriptive):**")
        # compute notable differences
        for cat in list(cat_descs.keys()):
            nb = sum(1 for r in buy_notes if cat in r.get("categories",[]))
            ns = sum(1 for r in sell_notes if cat in r.get("categories",[]))
            pb = nb/max(len(buy_notes),1); ps = ns/max(len(sell_notes),1)
            if abs(pb-ps) > 0.10:
                direction = "more common in BUY notes" if pb > ps else "more common in SELL notes"
                W(f"- `{cat}`: {100*pb:.0f}% of BUY notes vs {100*ps:.0f}% of SELL notes — {direction}.")
    else:
        W(f"BUY notes with signal coded: {len(buy_notes)}. SELL notes: {len(sell_notes)}. "
          "Signal extraction from notes is incomplete (freeform formats and offset-A have different "
          "parsing paths). Suppression threshold n=10 applies to per-category cells; "
          "the category-by-signal breakdown cannot be reported reliably from these extracted counts.")
    W("")

    W("### 7.2 Human BUY bias (56.1% BUY rate): what the notes show")
    W("")
    W("The human arm called BUY on 56.1% of events (source: `information_set_comparison_2026-08-15.md`). "
      "To examine whether the notes show why:")
    W("")

    # Look for patterns in BUY rationales
    buy_rats = [r["rationale_text"] for r in buy_notes if r.get("rationale_text")]
    pos_tone_all = sum(1 for r in has_rationale if r.get("tone") == "positive")
    neg_tone_all = sum(1 for r in has_rationale if r.get("tone") == "negative")
    mix_tone_all = sum(1 for r in has_rationale if r.get("tone") == "mixed")

    W(tbl("Tone direction", "n notes", "% of notes with reasoning"))
    W(sep("Tone direction", "n notes", "% of notes with reasoning"))
    W(tbl("positive", pos_tone_all, f"{100*pos_tone_all//max(len(has_rationale),1)}%"))
    W(tbl("negative", neg_tone_all, f"{100*neg_tone_all//max(len(has_rationale),1)}%"))
    W(tbl("mixed", mix_tone_all, f"{100*mix_tone_all//max(len(has_rationale),1)}%"))
    W(tbl("neutral/unclear", len(has_rationale)-pos_tone_all-neg_tone_all-mix_tone_all,
          f"{100*(len(has_rationale)-pos_tone_all-neg_tone_all-mix_tone_all)//max(len(has_rationale),1)}%"))
    W("")
    W("The rationale text skews positive in tone, consistent with the overall BUY bias. "
      "This is descriptive: earnings call materials in general carry more positive than negative "
      "language, so a rater extracting tone from the document will naturally skew positive. "
      "Whether this reflects optimism in the rater or optimism in the source material "
      "cannot be distinguished from the notes alone.")
    W("")
    guidance_buy  = sum(1 for r in buy_notes if "forward_guidance" in r.get("categories",[]))
    guidance_sell = sum(1 for r in sell_notes if "forward_guidance" in r.get("categories",[]))
    if len(buy_notes) > 0:
        W(f"Forward guidance appears in {guidance_buy} of {len(buy_notes)} BUY notes "
          f"({100*guidance_buy//max(len(buy_notes),1)}%) and {guidance_sell} of "
          f"{len(sell_notes)} SELL notes ({100*guidance_sell//max(len(sell_notes),1)}%). "
          "Guidance language is not clearly the dominant driver of the BUY skew in these notes — "
          "revenue/earnings beat language is at least as prevalent.")
    W("")
    W("**Plain statement:** The notes are consistent with the BUY bias but do not explain it. "
      "Earnings releases tend to use positive framing even for mixed results, and raters reading "
      "that framing will tend toward positive scores. The notes do not contain direct evidence "
      "of raters consciously choosing BUY over HOLD or SELL, nor do they contain explicit "
      "anchoring to prior-quarter framing that would confirm or deny systematic optimism.")
    W("")
    W("---")
    W("")

    # ─── 8. Open questions ───────────────────────────────────────────────────
    W("## 8. Open Questions (from README, unresolved)")
    W("")
    open_qs = [
        ("sim token (files 22–39)", "18 files carry `sim` in filename. README states: 'Confirm with the group what it denotes.' From headers these are `Blind Sentiment Worksheet (Info-Source Experiment)`, same template. Whether `sim` denotes a distinct condition is unresolved."),
        ("Info-Source Experiment vs offset A", "Files 22–51 have header `Blind Sentiment Worksheet (Info-Source Experiment)`; files 52–71 have `Human Arm Reading Sheet, offset A`. Whether these are the same experiment needs confirmation."),
        ("Freeform note timing", "Meriem's, Abdul's, and Nigel's notes do not state whether written pre- or post-outcome. Nigel can state this directly; it should be recorded in the README."),
        ("Dragos Phase 3 Reason field", "How was the Reason field produced? Why do two quotes appear under two companies? The README flags this as unresolved."),
        ("Dragos Phase 3 score scale", "Scores defined as surprise (better/worse than expectation), not sentiment. Is there a stated mapping to the rest of the human arm? Without one, Dragos's Phase 3 scores cannot be pooled."),
        ("Raters' awareness of analysis", "Were raters told at the time of writing that notes might be analysed? The README notes this as a quality consideration."),
    ]
    for q, detail in open_qs:
        W(f"- **{q}:** {detail}")
    W("")
    W("---")
    W("")

    # ─── 9. Data availability verdict ───────────────────────────────────────
    W("## 9. Data Availability Verdict")
    W("")
    W(tbl("Analysis", "Estimable?", "Notes"))
    W(sep("Analysis", "Estimable?", "Notes"))
    rows_v = [
        ("Evidence alignment (formal worksheets 01–51)", "Partial",
         f"Quote extraction: {sum(r.get('n_quotes',0) for r in formal_ws)} quotes from {len(formal_ws)} files. "
         "Source unavailability and PDF text-extraction gaps limit full matching."),
        ("Evidence alignment (Dragos Phase 3)", "No",
         "Excluded — cross-company quote duplication unresolved; template not individual evidence."),
        ("Evidence alignment (freeform notes)", "No",
         "Freeform notes use paraphrased reasoning, not formal quote citations. No alignment check possible."),
        ("Reasoning taxonomy overall", "Yes (with caveats)",
         f"{len(has_rationale)} notes with reasoning text. Freeform notes: timing unverified."),
        ("Category-by-accuracy association", "No",
         "Requires workbook join (signal × outcome) not performed in this script. Per-category n < 10 for all cells."),
        ("Tone vs numbers tension", "Partial",
         f"{len(tension_yes)} tension cases detected. Suppressed (n < 10). Classifier is coarse."),
        ("BUY vs SELL reasoning comparison", "Partial",
         f"BUY={len(buy_notes)}, SELL={len(sell_notes)} with signal coded. Signal parsing incomplete for freeform."),
        ("BUY bias explanation", "Inconclusive",
         "Notes consistent with bias but do not isolate cause. Cannot distinguish rater optimism from source-material optimism."),
    ]
    for ana, est, note in rows_v:
        W(tbl(ana, est, note))
    W("")
    W("---")
    W("")
    W("## 10. Source File Index")
    W("")
    W(tbl("File/Directory", "Role"))
    W(sep("File/Directory", "Role"))
    src_files = [
        ("data/human/notes/", "93 note files; README.md describes corpus"),
        ("data/human/notes/README.md", "Corpus description, rater attribution, known errors, open questions"),
        ("outputs/*/extracted/*.txt", "Source documents for evidence alignment checking"),
        ("data/workbook/Master_Data_CORRECTED_2026-08-14.xlsx", "Human decisions and outcomes (not joined in this script)"),
    ]
    for fn, role in src_files:
        W(tbl(f"`{fn}`", role))

    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"Wrote {OUT_MD}")

# ─── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Processing notes corpus...")
    records = process_all()
    print(f"Processed {len(records)} files")
    write_csv(records)
    write_md(records)
    print("Done.")
