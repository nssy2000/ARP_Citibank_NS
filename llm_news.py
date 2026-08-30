"""
llm_news.py
Route B news layer - scores a locally-stored pre-earnings market-expectations
digest per company/quarter with the same prompt structure,
REPORT_TYPE="Pre-Earnings Market Expectations Digest".

Digests are fetched ahead of time via web search across free outlets, strictly
from articles dated BEFORE each report_date (source URLs + publish dates
recorded inline for auditability) - this window is intentional, not
incidental: an earlier "earnings date and following" window let post-earnings
stock-reaction language leak into the digest text, which would have let the
news layer partially read the answer it's meant to predict. Digests are
stored as plain text under docs/news/<issuer>/<document_id>.txt - this script
only reads that local text and calls the LLM, same local-first split as
llm_macro.py. Digests are plain synthesized text, not raw PDF/HTML, so
they're read directly rather than routed through extract_doc_text's PDF/HTML
extraction pipeline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from report_pipeline import (
    BASE_DIR,
    OUTPUTS_DIR,
    ReportSpec,
    SourceDocument,
    build_doc_params,
    build_user_message,
    call_llm,
    load_manifest,
    utc_run_id,
)

NEWS_RESULTS_DIR = OUTPUTS_DIR / "news"

MANIFESTS = {
    "boeing": BASE_DIR / "manifests" / "boeing_reports.json",
    "jpm": BASE_DIR / "manifests" / "jpm_reports.json",
    "netflix": BASE_DIR / "manifests" / "netflix_reports.json",
    "bank_of_america": BASE_DIR / "manifests" / "bank_of_america_reports.json",
    "disney": BASE_DIR / "manifests" / "disney_reports.json",
    "target": BASE_DIR / "manifests" / "target_reports.json",
}

# Phase 2: separate human-comparison track, see blend.py's identical block for
# the "p2_" prefix rationale (avoids eval.run_eval._base_issuer()'s fold).
PHASE2_ISSUERS = [
    "airbnb", "amazon", "amd", "apple", "cvs_health", "charles_schwab",
    "citigroup", "coca_cola", "coinbase", "eli_lilly", "goldman_sachs",
    "ibm", "lowes", "lululemon", "maersk", "mcdonalds", "meta", "nike",
    "nvidia", "tesla", "uber", "walmart",
    "bank_of_america", "boeing", "disney", "jpm", "netflix", "target",
    "barclays", "ford", "microsoft", "pfizer", "united_airlines",
    "pepsico", "fedex", "lockheed_martin", "novo_nordisk", "hilton", "lvmh",
    "marriott",
    "allianz", "alphabet", "booking_holdings", "broadcom", "caterpillar", "chipotle", "colgate_palmolive", "comcast_corporation", "costco", "dell", "delta_air_lines", "expedia", "general_mills", "johnson_johnson", "kraft_heinz", "lenovo", "linde", "metlife", "micron", "oracle", "palantir", "paypal", "pinterest", "puma", "robinhood_markets", "salesforce", "siemens", "spotify", "standard_chartered", "starbucks", "unitedhealth", "visa", "workday",
]
MANIFESTS.update({
    f"p2_{name}": BASE_DIR / "manifests" / f"p2_{name}_reports.json"
    for name in PHASE2_ISSUERS
})


def _news_doc_path(issuer: str, document_id: str) -> Path:
    return BASE_DIR / "docs" / "news" / issuer / f"{document_id}.txt"


def _news_report_spec(base_report: ReportSpec) -> ReportSpec:
    news_path = _news_doc_path(base_report.issuer, base_report.document_id)
    return ReportSpec(
        issuer=base_report.issuer,
        company=base_report.company,
        ticker=base_report.ticker,
        sector=base_report.sector,
        report_type="Pre-Earnings Market Expectations Digest",
        fiscal_period=base_report.fiscal_period,
        report_date=base_report.report_date,
        documents=(SourceDocument(doc_type="News Article", source_pdf=news_path),),
        document_id=f"{base_report.document_id}_NEWS",
    )


def score_news_for_report(
    base_report: ReportSpec,
    hold_upper: float = 0.15,
    hold_lower: float = -0.15,
    model: str = "deepseek-chat",
) -> dict[str, Any] | None:
    news_path = _news_doc_path(base_report.issuer, base_report.document_id)
    if not news_path.exists():
        return None

    results_dir = NEWS_RESULTS_DIR / base_report.issuer / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    report = _news_report_spec(base_report)
    result_path = results_dir / f"{report.output_stem}.json"
    if result_path.exists():
        return json.loads(result_path.read_text(encoding="utf-8"))

    news_text = news_path.read_text(encoding="utf-8")
    doc_params = build_doc_params(report, news_text, hold_upper=hold_upper, hold_lower=hold_lower)
    user_message = build_user_message(doc_params)
    llm_output = call_llm(user_message, doc_params, report, utc_run_id(), cached_input=False, model=model)

    payload = {
        "document_id": report.document_id,
        "base_document_id": base_report.document_id,
        "issuer": base_report.issuer,
        "sentiment": llm_output["result"]["sentiment"],
        "signal": llm_output["result"]["signal"],
        "cost_log": llm_output["cost_log"],
    }
    result_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def score_all_news(issuer: str, **kwargs: Any) -> list[dict[str, Any]]:
    manifest_path = MANIFESTS[issuer]
    reports = [r for r in load_manifest(manifest_path) if r.issuer.lower() == issuer.lower()]
    results = []
    for report in reports:
        result = score_news_for_report(report, **kwargs)
        if result is not None:
            results.append(result)
    return results


def get_news_score(issuer: str, document_id: str) -> dict[str, Any] | None:
    manifest_path = MANIFESTS.get(issuer)
    if manifest_path is None:
        return None  # issuer has no news-layer manifest registered - no digests, no news score
    reports = [r for r in load_manifest(manifest_path) if r.document_id == document_id]
    if not reports:
        return None
    return score_news_for_report(reports[0])


def main() -> int:
    # bare `python llm_news.py` (no args) scores every phase2 issuer - phase2 is
    # the only active track; pass explicit issuer names to touch the retired
    # pre-phase2 production issuers. Matches blend.py's / quant_layer.py's
    # identical bare-CLI convention.
    default_issuers = [f"p2_{name}" for name in PHASE2_ISSUERS]
    total_cost = 0.0
    for issuer in sys.argv[1:] or default_issuers:
        print(f"\n=== {issuer} ===")
        try:
            results = score_all_news(issuer)
        except Exception as exc:
            print(f"  SKIPPED {issuer}: {exc}")
            continue
        for result in results:
            print(f"{result['document_id']}: {result['signal']['direction']} (score {result['sentiment']['score']})")
            total_cost += result["cost_log"]["estimated_cost_usd"]
    print(f"\nTotal news scoring cost: ${total_cost:.5f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
