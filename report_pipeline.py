from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"
OUTPUTS_DIR = BASE_DIR / "outputs"
ENV_FILE = BASE_DIR / ".env"
PROMPT_TEMPLATE_FILE = PROMPTS_DIR / "llm_analysis_prompt_template.md"

DEEPSEEK_INPUT_PRICE_PER_M = 0.27
DEEPSEEK_CACHED_PRICE_PER_M = 0.07
DEEPSEEK_OUTPUT_PRICE_PER_M = 1.10

MIN_EXTRACTED_TEXT_CHARS = 2000
SPEAKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9 .,&'()/:-]{2,}:")
SPEAKER_TITLE_PATTERN = re.compile(
    r"\b(Co-CEO|Chief Financial Officer|Chief Executive Officer|Vice President|Director|Operator)\b"
)
PAGE_NUMBER_PATTERN = re.compile(r"^\d+$")

load_dotenv(dotenv_path=ENV_FILE)


@dataclass(frozen=True)
class SourceDocument:
    doc_type: str
    source_pdf: Path
    pub_date: str | None = None


BUNDLE_SECTION_HEADERS = {
    "Press Release": "PRESS RELEASE",
    "Earnings Presentation": "EARNINGS PRESENTATION",
    "Earnings Call Transcript": "EARNINGS CALL TRANSCRIPT",
}

# Events excluded from scoring due to worksheet contamination.
# These 25 events had human-rater blind sentiment worksheets (containing the
# rater's score, signal, and realised price returns) fed to the LLM via
# build_bundle_text().  The contamination is per-document_id, not per-doc_type:
# "Earnings Document" also labels legitimate press releases, financial summaries,
# and interim reports that must not be excluded.
# Decision logged: outputs/global/summary/worksheet_exclusion_decision.md
# Added 2026-08-12.
WORKSHEET_EXCLUDED_DOCUMENT_IDS = frozenset({
    "AMD_FQ1_2026", "AMD_FQ2_2025", "AMD_FQ4_2025",
    "AMZN_FQ1_2026", "AMZN_FQ3_2025", "AMZN_FQ4_2025",
    "COIN_FQ1_2026", "COIN_FQ3_2025", "COIN_FQ4_2025",
    "LLY_FQ1_2026", "LLY_FQ3_2025", "LLY_FQ4_2025",
    "META_FQ1_2026", "META_FQ3_2025", "META_FQ4_2025",
    "NFLX_FQ3_2025", "NFLX_FQ4_2024", "NFLX_FQ4_2025",
    "NVDA_FQ1_2025", "NVDA_FQ2_2025", "NVDA_FQ3_2025", "NVDA_FQ4_2025",
    "TSLA_FQ1_2026", "TSLA_FQ3_2025", "TSLA_FQ4_2025",
})

# Source-PDF filenames that are human-rater worksheets, used to filter the
# specific contaminated documents within the 25 excluded events.  The worksheet
# filenames follow a pattern: the rater's name or a generic "numbers" sheet
# with post-event content.  This filter is applied per-document within
# build_bundle_text(), not per-event, so non-worksheet documents in the same
# event are still included.
_WORKSHEET_FILENAME_MARKERS = (
    "David Eji", "Dragos", "Nigel", "Anna", "Abdul", "Meriem",
    "blind_sentiment", "Blind Sentiment", "Blind_Sentiment",
)


def _is_worksheet_document(doc_source_pdf: str, document_id: str,
                           doc_type: str = "") -> bool:
    """Return True if this specific document is a human-rater worksheet.

    Only checks documents belonging to the 25 excluded events.  Within those
    events, identifies the worksheet by filename pattern (case-insensitive)
    or by doc_type == "Earnings Document" as a fallback.
    """
    if document_id not in WORKSHEET_EXCLUDED_DOCUMENT_IDS:
        return False
    source_lower = str(doc_source_pdf).lower()
    for marker in _WORKSHEET_FILENAME_MARKERS:
        if marker.lower() in source_lower:
            return True
    # Fallback: any "Earnings Document" in a contaminated event is the worksheet
    if doc_type == "Earnings Document":
        return True
    return False


@dataclass(frozen=True)
class ReportSpec:
    issuer: str
    company: str
    ticker: str
    sector: str
    report_type: str
    fiscal_period: str
    report_date: str
    documents: tuple[SourceDocument, ...]
    document_id: str

    @property
    def output_stem(self) -> str:
        return sanitize_filename(self.document_id)

    @property
    def primary_source_pdf(self) -> Path:
        return self.documents[0].source_pdf


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    page_count: int
    extracted_characters: int
    warnings: list[str]
    extractor_used: str


def report_metadata(report: ReportSpec) -> dict[str, Any]:
    return {
        "issuer": report.issuer,
        "company": report.company,
        "ticker": report.ticker,
        "sector": report.sector,
        "report_type": report.report_type,
        "fiscal_period": report.fiscal_period,
        "report_date": report.report_date,
        "documents": [
            {"doc_type": doc.doc_type, "source_pdf": str(doc.source_pdf), "pub_date": doc.pub_date}
            for doc in report.documents
        ],
        "document_id": report.document_id,
    }


def load_prompt_sections(prompt_file: Path = PROMPT_TEMPLATE_FILE) -> tuple[str, str]:
    template_text = prompt_file.read_text(encoding="utf-8")
    fenced_blocks = [
        block.strip()
        for index, block in enumerate(template_text.split("```"))
        if index % 2 == 1
    ]
    if len(fenced_blocks) < 2:
        raise ValueError(
            f"Expected at least two fenced code blocks in {prompt_file}"
        )
    return fenced_blocks[0], fenced_blocks[1]


SYSTEM_PROMPT, USER_MESSAGE_TEMPLATE = load_prompt_sections()


class PromptPack:
    """One loaded prompt file, so a run can pin which prompt version it used."""

    def __init__(self, prompt_file: Path = PROMPT_TEMPLATE_FILE):
        self.path = prompt_file
        self.name = prompt_file.name
        self.system_prompt, self.user_template = load_prompt_sections(prompt_file)


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return sanitized.strip("_") or "document"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def json_dumps_line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True) + "\n"


def _resolve_path(path: Path) -> Path:
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return path


def _assert_no_future_documents(report_date: str, documents: tuple[SourceDocument, ...], document_id: str) -> None:
    for doc in documents:
        if doc.pub_date is not None and doc.pub_date > report_date:
            raise ValueError(
                f"{document_id} includes future document {doc.source_pdf.name}: "
                f"pub_date={doc.pub_date} report_date={report_date}"
            )


def load_manifest(manifest_path: Path) -> list[ReportSpec]:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    reports = raw["reports"] if isinstance(raw, dict) else raw
    loaded_reports = []

    for entry in reports:
        documents = tuple(
            SourceDocument(
                doc_type=doc["doc_type"],
                source_pdf=_resolve_path(Path(doc["source_pdf"])),
                pub_date=doc.get("pub_date"),
            )
            for doc in entry["documents"]
        )
        _assert_no_future_documents(entry["report_date"], documents, entry["document_id"])
        loaded_reports.append(
            ReportSpec(
                issuer=entry["issuer"],
                company=entry["company"],
                ticker=entry["ticker"],
                sector=entry["sector"],
                report_type=entry["report_type"],
                fiscal_period=entry["fiscal_period"],
                report_date=entry["report_date"],
                documents=documents,
                document_id=entry["document_id"],
            )
        )

    return loaded_reports


def build_user_message(params: dict[str, Any], template: str | None = None) -> str:
    placeholder_map = {
        "COMPANY": params["company"],
        "TICKER": params["ticker"],
        "SECTOR": params["sector"],
        "REPORT_TYPE": params["report_type"],
        "REPORT_DATE": params["report_date"],
        "FISCAL_PERIOD": params["fiscal_period"],
        "REPORT_TEXT": params["report_text"],
        "HOLD_UPPER": params["hold_upper"],
        "HOLD_LOWER": params["hold_lower"],
    }

    user_message = template if template is not None else USER_MESSAGE_TEMPLATE
    for key, value in placeholder_map.items():
        user_message = user_message.replace(f"{{{{{key}}}}}", str(value))
    return user_message


def build_doc_params(
    report: ReportSpec,
    report_text: str,
    hold_upper: float,
    hold_lower: float,
) -> dict[str, Any]:
    return {
        "company": report.company,
        "ticker": report.ticker,
        "sector": report.sector,
        "report_type": report.report_type,
        "report_date": report.report_date,
        "fiscal_period": report.fiscal_period,
        "report_text": report_text,
        "hold_upper": hold_upper,
        "hold_lower": hold_lower,
    }


def _extract_text_with_pypdf(pdf_path: Path) -> tuple[list[str], int]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    return page_texts, len(reader.pages)


def _extract_text_with_pdfplumber(pdf_path: Path) -> tuple[list[str], int]:
    import pdfplumber

    with pdfplumber.open(str(pdf_path)) as pdf:
        page_texts = [(page.extract_text() or "").strip() for page in pdf.pages]
        return page_texts, len(pdf.pages)


def _extract_text_from_html(html_path: Path) -> tuple[list[str], int]:
    from html.parser import HTMLParser

    class _TextExtractor(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self._skip = False
            self.chunks: list[str] = []

        def handle_starttag(self, tag: str, attrs: list) -> None:
            if tag in ("script", "style", "noscript"):
                self._skip = True

        def handle_endtag(self, tag: str) -> None:
            if tag in ("script", "style", "noscript"):
                self._skip = False

        def handle_data(self, data: str) -> None:
            if not self._skip:
                text = data.strip()
                if text:
                    self.chunks.append(text)

    parser = _TextExtractor()
    parser.feed(html_path.read_text(encoding="utf-8", errors="replace"))
    text = "\n".join(parser.chunks)
    return [text], 1


def _normalize_margin_candidate(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def _identify_repeated_margin_lines(page_texts: list[str]) -> tuple[set[str], set[str]]:
    start_counter: Counter[str] = Counter()
    end_counter: Counter[str] = Counter()

    for page_text in page_texts:
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        if not lines:
            continue
        for line in lines[:2]:
            start_counter[_normalize_margin_candidate(line)] += 1
        for line in lines[-2:]:
            end_counter[_normalize_margin_candidate(line)] += 1

    repeated_starts = {line for line, count in start_counter.items() if count >= 2}
    repeated_ends = {line for line, count in end_counter.items() if count >= 2}
    return repeated_starts, repeated_ends


def _merge_wrapped_lines(page_texts: list[str]) -> str:
    repeated_starts, repeated_ends = _identify_repeated_margin_lines(page_texts)
    merged_blocks: list[str] = []
    paragraph = ""

    for page_text in page_texts:
        raw_lines = page_text.splitlines()
        filtered_lines: list[str] = []

        for index, raw_line in enumerate(raw_lines):
            line = raw_line.strip()
            if not line:
                filtered_lines.append("")
                continue

            normalized_line = _normalize_margin_candidate(line)
            if index < 2 and normalized_line in repeated_starts:
                continue
            if len(raw_lines) - index <= 2 and normalized_line in repeated_ends:
                continue
            if PAGE_NUMBER_PATTERN.match(line):
                continue

            filtered_lines.append(re.sub(r"\s+", " ", line))

        for line in filtered_lines:
            if not line:
                if paragraph:
                    merged_blocks.append(paragraph.strip())
                    paragraph = ""
                continue

            if SPEAKER_PATTERN.match(line):
                if paragraph:
                    merged_blocks.append(paragraph.strip())
                paragraph = line
                continue

            if not paragraph:
                paragraph = line
                continue

            if paragraph.endswith("-"):
                paragraph = paragraph[:-1] + line
            else:
                paragraph = f"{paragraph} {line}"

        if paragraph:
            merged_blocks.append(paragraph.strip())
            paragraph = ""

    normalized_text = "\n\n".join(block for block in merged_blocks if block)
    normalized_text = normalized_text.replace("\r\n", "\n").replace("\r", "\n")
    normalized_text = re.sub(r"\n{3,}", "\n\n", normalized_text)
    return normalized_text.strip()


def extract_doc_text(pdf_path: Path) -> ExtractionResult:
    warnings: list[str] = []

    # ".htm" is the conventional SEC EDGAR exhibit extension (e.g. EX-99.1
    # filings) and is byte-for-byte the same format as ".html" - both route
    # through the same lenient stdlib HTMLParser, which tolerates a leading
    # non-tag text line (some sourced files carry a "Source: <url>" first
    # line for provenance) as harmless extra text, not a parse error.
    if pdf_path.suffix.lower() in (".html", ".htm"):
        page_texts, page_count = _extract_text_from_html(pdf_path)
        extractor_used = "html.parser"
        cleaned_text = _merge_wrapped_lines(page_texts)
        extracted_characters = len(cleaned_text)
        if extracted_characters < MIN_EXTRACTED_TEXT_CHARS:
            raise ValueError(
                f"Extracted text from {pdf_path.name} is too short ({extracted_characters} characters)"
            )
        if "Earnings Call" not in cleaned_text and "Earnings Call Transcripts" not in cleaned_text:
            warnings.append("missing_keyword:Earnings Call")
        return ExtractionResult(
            text=cleaned_text,
            page_count=page_count,
            extracted_characters=extracted_characters,
            warnings=warnings,
            extractor_used=extractor_used,
        )

    if pdf_path.suffix.lower() == ".txt":
        # Already-plain text (e.g. a web-sourced transcript saved as .txt) -
        # no markup to strip, just normalize whitespace the same way the
        # PDF/HTML paths do before the length/keyword checks.
        raw_text = pdf_path.read_text(encoding="utf-8", errors="replace")
        cleaned_text = _merge_wrapped_lines([raw_text])
        extractor_used = "plain_text"
        extracted_characters = len(cleaned_text)
        if extracted_characters < MIN_EXTRACTED_TEXT_CHARS:
            raise ValueError(
                f"Extracted text from {pdf_path.name} is too short ({extracted_characters} characters)"
            )
        if "Earnings Call" not in cleaned_text and "Earnings Call Transcripts" not in cleaned_text:
            warnings.append("missing_keyword:Earnings Call")
        return ExtractionResult(
            text=cleaned_text,
            page_count=1,
            extracted_characters=extracted_characters,
            warnings=warnings,
            extractor_used=extractor_used,
        )

    extractor_used = "pypdf"
    page_texts, page_count = _extract_text_with_pypdf(pdf_path)
    pypdf_text_length = len("".join(page_texts).strip())

    need_fallback = pypdf_text_length < MIN_EXTRACTED_TEXT_CHARS or not any(
        page_texts
    )

    if need_fallback:
        fallback_page_texts, fallback_page_count = _extract_text_with_pdfplumber(pdf_path)
        fallback_text_length = len("".join(fallback_page_texts).strip())
        if fallback_text_length > pypdf_text_length:
            page_texts = fallback_page_texts
            page_count = fallback_page_count
            extractor_used = "pdfplumber"
    else:
        fallback_page_texts, _ = _extract_text_with_pdfplumber(pdf_path)
        page_texts = [
            fallback_page_texts[index]
            if not page_text.strip() and index < len(fallback_page_texts)
            else page_text
            for index, page_text in enumerate(page_texts)
        ]

    if page_count == 0:
        raise ValueError(f"No pages found in PDF: {pdf_path}")

    cleaned_text = _merge_wrapped_lines(page_texts)
    extracted_characters = len(cleaned_text)

    if extracted_characters < MIN_EXTRACTED_TEXT_CHARS:
        raise ValueError(
            f"Extracted text from {pdf_path.name} is too short ({extracted_characters} characters)"
        )

    if "Earnings Call" not in cleaned_text and "Earnings Call Transcripts" not in cleaned_text:
        warnings.append("missing_keyword:Earnings Call")
    has_speaker_labels = any(
        SPEAKER_PATTERN.match(block) for block in cleaned_text.split("\n\n")
    )
    has_speaker_titles = bool(SPEAKER_TITLE_PATTERN.search(cleaned_text))
    if not has_speaker_labels and not has_speaker_titles:
        warnings.append("missing_pattern:speaker_labels")

    return ExtractionResult(
        text=cleaned_text,
        page_count=page_count,
        extracted_characters=extracted_characters,
        warnings=warnings,
        extractor_used=extractor_used,
    )


def build_bundle_text(report: ReportSpec) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Extracts each source document and concatenates them into one labeled text
    block for a single LLM call per quarter. A sub-document that fails extraction
    (e.g. trips MIN_EXTRACTED_TEXT_CHARS) is dropped with a warning rather than
    failing the whole bundle - a partial bundle is still a usable signal."""
    sections: list[str] = []
    per_doc_meta: list[dict[str, Any]] = []
    combined_warnings: list[str] = []

    for doc in report.documents:
        if _is_worksheet_document(doc.source_pdf, report.document_id, doc.doc_type):
            combined_warnings.append(
                f"{doc.doc_type}: excluded (human-rater worksheet, "
                f"document_id {report.document_id} in "
                f"WORKSHEET_EXCLUDED_DOCUMENT_IDS)"
            )
            per_doc_meta.append({
                "doc_type": doc.doc_type,
                "source_pdf": str(doc.source_pdf),
                "excluded": True,
                "reason": "worksheet_contamination",
            })
            continue
        header = BUNDLE_SECTION_HEADERS.get(doc.doc_type, doc.doc_type.upper())
        try:
            extraction = extract_doc_text(doc.source_pdf)
        except ValueError as exc:
            combined_warnings.append(f"{doc.doc_type}: extraction_failed: {exc}")
            per_doc_meta.append({"doc_type": doc.doc_type, "source_pdf": str(doc.source_pdf), "error": str(exc)})
            continue

        sections.append(f"=== {header} ===\n\n{extraction.text}")
        per_doc_meta.append(
            {
                "doc_type": doc.doc_type,
                "source_pdf": str(doc.source_pdf),
                "page_count": extraction.page_count,
                "extracted_characters": extraction.extracted_characters,
                "extractor_used": extraction.extractor_used,
                "warnings": extraction.warnings,
            }
        )
        # The transcript-oriented "Earnings Call" keyword / speaker-label checks
        # inside extract_doc_text always trip on press releases and slide decks,
        # so only surface them for the doc type they're actually meaningful for.
        if doc.doc_type == "Earnings Call Transcript":
            combined_warnings.extend(f"{doc.doc_type}: {warning}" for warning in extraction.warnings)

    if not sections:
        raise ValueError(f"All source documents failed extraction for {report.document_id}")

    combined_text = "\n\n".join(sections)
    return combined_text, per_doc_meta, combined_warnings


def strip_json_fences(raw_text: str) -> str:
    clean_text = raw_text.strip()
    if clean_text.startswith("```"):
        parts = clean_text.split("```")
        if len(parts) > 1:
            clean_text = parts[1]
        if clean_text.startswith("json"):
            clean_text = clean_text[4:]
        clean_text = clean_text.strip()
    return clean_text


def derive_signal(score: float, hold_upper: float, hold_lower: float) -> str:
    if score > hold_upper:
        return "BUY"
    if score < hold_lower:
        return "SELL"
    return "HOLD"


def validate_result(result: dict[str, Any]) -> None:
    missing = [key for key in ("sentiment", "signal", "summary", "evidence") if key not in result]
    if missing:
        raise ValueError(f"LLM response missing required keys: {missing}")
    float(result["sentiment"]["score"])


def cache_hit_tokens(usage: Any, cached_input: bool) -> int:
    # DeepSeek reports actual cache hits in usage; trust that over the
    # batch-order guess when it is present.
    reported = getattr(usage, "prompt_cache_hit_tokens", None)
    if reported is not None:
        return int(reported)
    return usage.prompt_tokens if cached_input else 0


def call_llm(
    user_message: str,
    doc_params: dict[str, Any],
    report: ReportSpec,
    run_id: str,
    cached_input: bool = False,
    model: str = "deepseek-chat",
    system_prompt: str | None = None,
    prompt_name: str = PROMPT_TEMPLATE_FILE.name,
    max_attempts: int = 3,
) -> dict[str, Any]:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set in the environment or .env")

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=120.0)
    start_time = time.time()

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=4096,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            )
            raw_text = response.choices[0].message.content or ""
            result = json.loads(strip_json_fences(raw_text))
            validate_result(result)
            break
        except Exception as exc:
            last_error = exc
            if attempt == max_attempts:
                raise RuntimeError(
                    f"LLM call failed after {max_attempts} attempts: {last_error}"
                ) from last_error
            time.sleep(2**attempt)

    elapsed = time.time() - start_time

    # Recompute the signal from the score so the score-to-signal mapping is
    # deterministic, rather than trusting the model's own arithmetic. The
    # model's stated direction is kept and any disagreement is flagged.
    score = float(result["sentiment"]["score"])
    derived = derive_signal(score, doc_params["hold_upper"], doc_params["hold_lower"])
    model_stated = result["signal"]["direction"]
    result["signal"]["direction"] = derived
    result["signal"]["model_stated_direction"] = model_stated
    result["signal"]["signal_mismatch"] = model_stated != derived

    hit_tokens = cache_hit_tokens(response.usage, cached_input)
    miss_tokens = response.usage.prompt_tokens - hit_tokens

    cost_log = {
        "run_id": run_id,
        "timestamp": utc_timestamp(),
        "status": "success",
        "document_id": report.document_id,
        "issuer": report.issuer,
        "company": report.company,
        "ticker": report.ticker,
        "fiscal_period": report.fiscal_period,
        "report_date": report.report_date,
        "source_pdf": str(report.primary_source_pdf),
        "model": response.model,
        "prompt": prompt_name,
        "input_tokens": response.usage.prompt_tokens,
        "cache_hit_tokens": hit_tokens,
        "output_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
        "cached_input": cached_input,
        "estimated_cost_usd": round(
            (miss_tokens * DEEPSEEK_INPUT_PRICE_PER_M / 1_000_000)
            + (hit_tokens * DEEPSEEK_CACHED_PRICE_PER_M / 1_000_000)
            + (
                response.usage.completion_tokens
                * DEEPSEEK_OUTPUT_PRICE_PER_M
                / 1_000_000
            ),
            6,
        ),
        "latency_seconds": round(elapsed, 2),
        "attempts": attempt,
        "signal": result["signal"]["direction"],
        "signal_mismatch": result["signal"]["signal_mismatch"],
        "sentiment_score": score,
        "hold_upper": doc_params["hold_upper"],
        "hold_lower": doc_params["hold_lower"],
    }

    return {"result": result, "cost_log": cost_log}


def ensemble_llm(
    user_message: str,
    doc_params: dict[str, Any],
    report: ReportSpec,
    run_id: str,
    n_runs: int,
    model: str = "deepseek-chat",
    system_prompt: str | None = None,
    prompt_name: str = PROMPT_TEMPLATE_FILE.name,
) -> dict[str, Any]:
    """Run the same document n times and predict from the mean score.

    Repeated calls hit DeepSeek's prompt cache, so the extra runs are cheap.
    The mean smooths run-to-run wobble on borderline documents and the final
    signal is derived from the mean score with the same fixed thresholds.
    """
    outputs = []
    for index in range(n_runs):
        output = call_llm(
            user_message,
            doc_params,
            report,
            run_id,
            cached_input=index > 0,
            model=model,
            system_prompt=system_prompt,
            prompt_name=prompt_name,
        )
        output["cost_log"]["ensemble_run_index"] = index + 1
        outputs.append(output)

    scores = [out["cost_log"]["sentiment_score"] for out in outputs]
    signals = [out["cost_log"]["signal"] for out in outputs]
    mean_score = round(sum(scores) / n_runs, 3)
    final_signal = derive_signal(
        mean_score, doc_params["hold_upper"], doc_params["hold_lower"]
    )

    # First run's full output is kept as the representative result, with the
    # ensemble aggregate written over the headline score and signal.
    result = outputs[0]["result"]
    result["sentiment"]["score"] = mean_score
    result["signal"]["direction"] = final_signal
    result["ensemble"] = {
        "n_runs": n_runs,
        "scores": scores,
        "signals": signals,
        "mean_score": mean_score,
        "score_range": round(max(scores) - min(scores), 3),
        "signal_agreement": len(set(signals)) == 1,
    }

    cost_log = dict(outputs[0]["cost_log"])
    cost_log["sentiment_score"] = mean_score
    cost_log["signal"] = final_signal
    cost_log["ensemble_runs"] = n_runs
    cost_log["estimated_cost_usd"] = round(
        sum(out["cost_log"]["estimated_cost_usd"] for out in outputs), 6
    )
    cost_log["latency_seconds"] = round(
        sum(out["cost_log"]["latency_seconds"] for out in outputs), 2
    )

    return {
        "result": result,
        "cost_log": cost_log,
        "run_logs": [out["cost_log"] for out in outputs],
    }


def consistency_check(
    user_message: str,
    doc_params: dict[str, Any],
    report: ReportSpec,
    run_id: str,
    n_runs: int,
    model: str = "deepseek-chat",
    system_prompt: str | None = None,
    prompt_name: str = PROMPT_TEMPLATE_FILE.name,
) -> dict[str, Any]:
    signals = []
    scores = []
    cost_logs = []

    for index in range(n_runs):
        output = call_llm(
            user_message,
            doc_params,
            report,
            run_id,
            cached_input=True,
            model=model,
            system_prompt=system_prompt,
            prompt_name=prompt_name,
        )
        signals.append(output["result"]["signal"]["direction"])
        scores.append(output["result"]["sentiment"]["score"])
        cost_log = dict(output["cost_log"])
        cost_log["consistency_run_index"] = index + 1
        cost_logs.append(cost_log)

    summary = {
        "run_id": run_id,
        "document_id": report.document_id,
        "n_runs": n_runs,
        "signals": signals,
        "scores": scores,
        "signal_agreement": len(set(signals)) == 1,
        "score_range": round(max(scores) - min(scores), 3),
        "total_cost_usd": round(sum(item["estimated_cost_usd"] for item in cost_logs), 6),
    }
    return {"summary": summary, "cost_logs": cost_logs}


def build_result_payload(
    raw_result: dict[str, Any],
    report: ReportSpec,
    cost_log: dict[str, Any],
    extraction_target: Path,
    extraction_meta: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    payload = dict(raw_result)
    model_document_id = payload.get("document_id")
    payload["document_id"] = report.document_id
    if model_document_id and model_document_id != report.document_id:
        payload["model_document_id"] = model_document_id

    payload["report_metadata"] = report_metadata(report)
    payload["run_meta"] = {
        "run_id": cost_log["run_id"],
        "timestamp": cost_log["timestamp"],
        "model": cost_log["model"],
        "prompt": cost_log.get("prompt"),
        "cached_input": cost_log["cached_input"],
        "source_pdf": str(report.primary_source_pdf),
        "extracted_text_path": str(extraction_target),
    }
    if extraction_meta is not None:
        payload["extraction_meta"] = extraction_meta
    if warnings:
        payload["extraction_warnings"] = warnings
    return payload
