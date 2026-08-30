import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR / "phase2"))

from gap_report import parse_events, compute_gap  # noqa: E402


def test_parse_events_skips_header_and_incomplete_rows():
    rows = [
        ["Company", "Ticker", "Year", "Quarter"],
        ["Broadcom", "AVGO", "2025", "Q3"],
        ["", "", "", ""],
        ["Costco", "COST", "", ""],
    ]
    events = parse_events(rows)
    assert events == {("AVGO", "2025", "Q3"): "Broadcom"}


def test_parse_events_skips_title_banner_and_header_two_row_preamble():
    # Master_Data_NEW.ods's real Human_Data_Entry/LLM_Data_Entry tabs have a
    # title-banner row above the column-header row (data starts at row 3,
    # per CLAUDE.md) - regression coverage for the off-by-one where only the
    # banner row was skipped and the real header row leaked in as a phantom
    # ("Ticker", "Year", "Quarter") -> "Company" event.
    rows = [
        ["Human Readings – Data Entry", "", "", ""],
        ["Company", "Ticker", "Year", "Quarter"],
        ["Broadcom", "AVGO", "2025", "Q3"],
        ["Costco", "COST", "2025", "Q4"],
    ]
    events = parse_events(rows)
    assert events == {
        ("AVGO", "2025", "Q3"): "Broadcom",
        ("COST", "2025", "Q4"): "Costco",
    }


def test_compute_gap_returns_human_only_combos():
    human = {("AVGO", "2025", "Q3"): "Broadcom", ("AAPL", "2025", "Q3"): "Apple"}
    llm = {("AAPL", "2025", "Q3"): "Apple"}
    assert compute_gap(human, llm) == {("AVGO", "2025", "Q3"): "Broadcom"}
