"""
llm_macro.py
Route A macro layer - scores each 2025 FOMC minutes release with the same
prompt structure as the core (micro) call, REPORT_TYPE="FOMC Minutes".

Macro sentiment is entity-agnostic: the same minutes reading applies to every
company whose report_date falls in that meeting's window, so each meeting is
scored once and cached under outputs/macro/results/, never re-called per
company. get_macro_score_for_date() maps a company's report_date to the most
recent FOMC minutes that were already public by that date (no look-ahead).
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
    extract_doc_text,
    utc_run_id,
)

MACRO_MANIFEST = BASE_DIR / "manifests" / "macro_fomc.json"
MACRO_RESULTS_DIR = OUTPUTS_DIR / "macro" / "results"


def load_macro_manifest() -> list[dict[str, Any]]:
    raw = json.loads(MACRO_MANIFEST.read_text(encoding="utf-8"))
    return raw["meetings"]


def _meeting_report_spec(meeting: dict[str, Any]) -> ReportSpec:
    return ReportSpec(
        issuer="macro",
        company="Federal Open Market Committee",
        ticker="FOMC",
        sector="Monetary Policy",
        report_type="FOMC Minutes",
        fiscal_period=meeting["meeting_dates"],
        report_date=meeting["minutes_release_date"],
        documents=(
            SourceDocument(
                doc_type="FOMC Minutes",
                source_pdf=(BASE_DIR / meeting["source_html"]).resolve(),
            ),
        ),
        document_id=meeting["document_id"],
    )


def score_meeting(
    meeting: dict[str, Any],
    hold_upper: float = 0.15,
    hold_lower: float = -0.15,
    model: str = "deepseek-chat",
) -> dict[str, Any]:
    MACRO_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report = _meeting_report_spec(meeting)
    result_path = MACRO_RESULTS_DIR / f"{report.output_stem}.json"
    if result_path.exists():
        return json.loads(result_path.read_text(encoding="utf-8"))

    extraction = extract_doc_text(report.documents[0].source_pdf)
    doc_params = build_doc_params(report, extraction.text, hold_upper=hold_upper, hold_lower=hold_lower)
    user_message = build_user_message(doc_params)
    llm_output = call_llm(user_message, doc_params, report, utc_run_id(), cached_input=False, model=model)

    payload = {
        "document_id": report.document_id,
        "meeting_dates": meeting["meeting_dates"],
        "minutes_release_date": meeting["minutes_release_date"],
        "sentiment": llm_output["result"]["sentiment"],
        "signal": llm_output["result"]["signal"],
        "cost_log": llm_output["cost_log"],
    }
    result_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def score_all_meetings(**kwargs: Any) -> list[dict[str, Any]]:
    return [score_meeting(meeting, **kwargs) for meeting in load_macro_manifest()]


def get_macro_score_for_date(report_date: str) -> dict[str, Any] | None:
    meetings = load_macro_manifest()
    eligible = [m for m in meetings if m["minutes_release_date"] <= report_date]
    if not eligible:
        return None
    latest = max(eligible, key=lambda m: m["minutes_release_date"])
    return score_meeting(latest)


def main() -> int:
    results = score_all_meetings()
    for result in results:
        print(
            f"{result['document_id']}: {result['signal']['direction']} "
            f"(score {result['sentiment']['score']})"
        )
    total_cost = sum(r["cost_log"]["estimated_cost_usd"] for r in results if "cost_log" in r)
    print(f"\nTotal macro scoring cost: ${total_cost:.5f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
