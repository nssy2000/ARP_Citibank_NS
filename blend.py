"""
blend.py
Combines the scored layers (micro = company earnings bundle, macro = nearest
already-public FOMC minutes, news = coverage digest, quant = deterministic
yfinance numeric signal) into a single blended sentiment score and
BUY/HOLD/SELL signal.

Weights are still evaluated in eval/calibrate.py, but the default below keeps
the pooled-N=24 LOOCV winner from outputs/global/summary for the three text
layers - 0.8/0.0/0.2 (micro/macro/news) - and adds the quant layer at weight
0.0 by default. Holding quant at 0.0 means the DEFAULT blend is byte-for-byte
unchanged from before the quant layer existed; whether quant earns weight is
decided by the LOOCV ablation in eval/, not by hand-setting it here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

from report_pipeline import BASE_DIR, OUTPUTS_DIR, load_manifest

DEFAULT_WEIGHTS = (0.80, 0.20, 0.0, 0.0)  # (micro, macro, news, quant)

# Canonical sentiment-score thresholds (asymmetric) - the values eval/calibrate.py,
# backtest.py, and the deployed default actually use everywhere. Defined here
# (not in eval/calibrate.py) because eval/calibrate.py already imports from this
# module - defining them there and importing back would be circular.
DEFAULT_HOLD_UPPER = 0.20
DEFAULT_HOLD_LOWER = -0.10

MANIFESTS = {
    "boeing": BASE_DIR / "manifests" / "boeing_reports.json",
    "jpm": BASE_DIR / "manifests" / "jpm_reports.json",
    "netflix": BASE_DIR / "manifests" / "netflix_reports.json",
    "bank_of_america": BASE_DIR / "manifests" / "bank_of_america_reports.json",
    "disney": BASE_DIR / "manifests" / "disney_reports.json",
    "target": BASE_DIR / "manifests" / "target_reports.json",
}

# Phase 2: separate human-comparison track, see quant_layer.py's identical block
# for the "p2_" prefix rationale (avoids eval.run_eval._base_issuer()'s fold).
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


class BlendResult(NamedTuple):
    document_id: str
    micro_score: float
    macro_score: float | None
    news_score: float | None
    quant_score: float | None
    weights: tuple[float, float, float, float]
    blended_score: float
    signal: str


def blend_scores(
    micro_score: float,
    macro_score: float | None,
    news_score: float | None,
    quant_score: float | None = None,
    weights: tuple[float, float, float, float] = DEFAULT_WEIGHTS,
) -> float:
    """Weighted sum of the layer scores. A missing macro/news/quant score
    (e.g. not yet fetched for that quarter) drops out of the sum and its
    weight is redistributed proportionally across the remaining layers,
    rather than silently treating a missing layer as neutral (0.0)."""
    w_micro, w_macro, w_news, w_quant = weights
    components = [(micro_score, w_micro)]
    if macro_score is not None:
        components.append((macro_score, w_macro))
    if news_score is not None:
        components.append((news_score, w_news))
    if quant_score is not None:
        components.append((quant_score, w_quant))

    total_weight = sum(weight for _, weight in components)
    if total_weight == 0:
        raise ValueError("Total weight across available layers is zero")

    return sum(score * weight for score, weight in components) / total_weight


def derive_signal(blended_score: float, hold_upper: float = DEFAULT_HOLD_UPPER, hold_lower: float = DEFAULT_HOLD_LOWER) -> str:
    if blended_score > hold_upper:
        return "BUY"
    if blended_score < hold_lower:
        return "SELL"
    return "HOLD"


def _load_micro_score(issuer: str, document_id: str) -> float:
    result_path = OUTPUTS_DIR / issuer / "results" / f"{document_id}.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    return payload["sentiment"]["score"]


def blend_document(
    issuer: str,
    document_id: str,
    weights: tuple[float, float, float, float] = DEFAULT_WEIGHTS,
    hold_upper: float = DEFAULT_HOLD_UPPER,
    hold_lower: float = DEFAULT_HOLD_LOWER,
) -> BlendResult:
    import llm_macro
    import llm_news
    import quant_layer

    reports = [r for r in load_manifest(MANIFESTS[issuer]) if r.document_id == document_id]
    if not reports:
        raise ValueError(f"No manifest entry for {issuer}/{document_id}")
    report = reports[0]

    micro_score = _load_micro_score(issuer, document_id)

    macro_result = llm_macro.get_macro_score_for_date(report.report_date)
    macro_score = macro_result["sentiment"]["score"] if macro_result else None

    news_result = llm_news.get_news_score(issuer, document_id)
    news_score = news_result["sentiment"]["score"] if news_result else None

    quant_result = quant_layer.get_quant_score(issuer, document_id)
    quant_score = quant_result["sentiment"]["score"] if quant_result else None

    blended = blend_scores(micro_score, macro_score, news_score, quant_score, weights)
    signal = derive_signal(blended, hold_upper, hold_lower)

    return BlendResult(
        document_id=document_id,
        micro_score=micro_score,
        macro_score=macro_score,
        news_score=news_score,
        quant_score=quant_score,
        weights=weights,
        blended_score=round(blended, 4),
        signal=signal,
    )


def blend_issuer(issuer: str, **kwargs) -> list[BlendResult]:
    reports = [r for r in load_manifest(MANIFESTS[issuer]) if r.issuer.lower() == issuer.lower()]
    return [blend_document(issuer, report.document_id, **kwargs) for report in reports]


if __name__ == "__main__":
    import sys

    # Hand-computed sanity check: micro=0.4, macro=0.2, news=-0.2, quant=0.5,
    # weights=0.80/0.20/0.0/0.0 (current DEFAULT_WEIGHTS, promoted 2026-08-19 - see CLAUDE.md)
    # expected = 0.4*0.80 + 0.2*0.20 + (-0.2)*0.0 + 0.5*0.0 = 0.32 + 0.04 = 0.36
    check = blend_scores(0.4, 0.2, -0.2, 0.5, DEFAULT_WEIGHTS)
    assert abs(check - 0.36) < 1e-9, f"Sanity check failed: got {check}, expected 0.36"
    print(f"Sanity check passed: blend_scores(0.4, 0.2, -0.2, 0.5) = {check}")

    # bare `python blend.py` (no args) blends every phase2 issuer - phase2 is the
    # only active track; pass an explicit issuer to touch the retired
    # pre-phase2 production issuers.
    default_issuers = [f"p2_{name}" for name in PHASE2_ISSUERS]
    for issuer in sys.argv[1:] or default_issuers:
        print(f"\n=== {issuer} ===")
        try:
            results = blend_issuer(issuer)
        except Exception as exc:
            print(f"  SKIPPED {issuer}: {exc}")
            continue
        for result in results:
            print(
                f"{result.document_id}: micro={result.micro_score} macro={result.macro_score} "
                f"news={result.news_score} quant={result.quant_score} "
                f"-> blended={result.blended_score} ({result.signal})"
            )
