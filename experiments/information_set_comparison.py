"""
Information-set comparison: human arm by information set vs model arm section ablation.

Human arm: reads from data/workbook/Master_Data_CORRECTED_2026-08-14.xlsx
  Human_Data_Entry sheet, column AS (index 44) "Information Set".
  Re-priced returns used where available (columns AH/AI), else original (columns Q/R).

Model arm: reads from:
  - outputs/global/summary/section_ablation_summary.csv (Set A, N=119)
  - outputs/global/summary/section_ablation_extension_summary.csv (Set B, N=56)

Metrics computed:
  - coverage_accuracy = n_correct / n_graded  (|ret| > 2%; HOLD = wrong)
  - selectivity_accuracy = n_correct / n_called_and_graded
      where n_called_and_graded = BUY+SELL decisions where |ret| > 0.02
      n_correct = BUY with UP outcome OR SELL with DOWN outcome among called+graded
  - coverage_floor = max(n_graded_UP, n_graded_DOWN) / n_graded
  - selectivity_floor = max(n_called_graded_UP, n_called_graded_DOWN) / n_called_and_graded
      floor and accuracy share the same denominator (n_called_and_graded)
  - mean_net_per_trade = mean net P&L for all BUY+SELL decisions (n_calls_all)

NOTE: The human n_calls column stores n_called_and_graded (the selectivity denominator).
n_calls_all (raw BUY+SELL count) is reported in the notes column for reference.
The model arm n_calls = all BUY+SELL trades (including flat outcomes), which differs
from the human denominator — cross-arm selectivity comparisons must note this.

Read-only: reads only committed input files.
Writes: outputs/global/summary/information_set_comparison_{DATE}.csv and .md
No LLM calls. Fully deterministic.
"""

import csv
import io
import math
import statistics
import sys
from pathlib import Path

import openpyxl

BASE_DIR = Path(__file__).resolve().parent.parent
DATE = "2026-08-15"
GRADING_BAND = 0.02
ROUND_TRIP_COST = 0.001  # 10bps in fraction


# ---------------------------------------------------------------------------
# Load human arm from workbook
# ---------------------------------------------------------------------------
def load_human_arm():
    """Returns list of dicts with one entry per Human_Data_Entry row."""
    wb_path = BASE_DIR / "data" / "workbook" / "Master_Data_CORRECTED_2026-08-14.xlsx"
    wb = openpyxl.load_workbook(wb_path, read_only=True, data_only=True)
    ws = wb["Human_Data_Entry"]

    rows = list(ws.iter_rows(min_row=3, values_only=True))
    events = []
    for r in rows:
        if r[0] is None:
            continue
        info_set = r[44]  # column AS — "Information Set"
        if info_set is None:
            continue

        decision = r[9]   # BUY/HOLD/SELL
        time_mins = r[10]  # Time (mins)

        # Return: use re-priced where available, else original
        repriced_ret = r[33]   # Re-priced % change
        actual_ret = r[16]     # Actual % change
        ret = repriced_ret if repriced_ret is not None else actual_ret

        repriced_dir = r[34]   # Re-priced direction
        actual_dir = r[17]     # Actual Direction
        direction = repriced_dir if repriced_dir is not None else actual_dir

        repriced_net = r[36]   # Re-priced net P&L
        actual_net = r[20]     # Net P&L
        net = repriced_net if repriced_net is not None else actual_net

        events.append({
            "info_set": info_set,
            "decision": decision,
            "time_mins": time_mins,
            "ret": ret,
            "direction": direction,
            "net": net,
        })

    return events


# ---------------------------------------------------------------------------
# Compute human-arm metrics per information set
# ---------------------------------------------------------------------------
def human_metrics(events: list, info_set: str) -> dict:
    group = [e for e in events if e["info_set"] == info_set]
    n = len(group)
    if n == 0:
        return {}

    # Decision mix
    n_buy = sum(1 for e in group if e["decision"] == "BUY")
    n_hold = sum(1 for e in group if e["decision"] == "HOLD")
    n_sell = sum(1 for e in group if e["decision"] == "SELL")

    buy_share = n_buy / n
    hold_share = n_hold / n
    sell_share = n_sell / n

    # Reading time
    times = [e["time_mins"] for e in group if e["time_mins"] is not None]
    mean_time = statistics.mean(times) if times else None
    median_time = statistics.median(times) if times else None
    total_time = sum(times) if times else None

    # Grading: |ret| > GRADING_BAND
    graded = [e for e in group if e["ret"] is not None and abs(e["ret"]) > GRADING_BAND]
    n_graded = len(graded)

    # Correct = BUY & UP, or SELL & DOWN (among graded)
    n_correct = 0
    n_graded_up = 0
    n_graded_down = 0
    for e in graded:
        up = e["direction"] == "UP" or (e["direction"] is None and e["ret"] is not None and e["ret"] > GRADING_BAND)
        down = e["direction"] == "DOWN" or (e["direction"] is None and e["ret"] is not None and e["ret"] < -GRADING_BAND)
        if up:
            n_graded_up += 1
        if down:
            n_graded_down += 1
        if e["decision"] == "BUY" and up:
            n_correct += 1
        elif e["decision"] == "SELL" and down:
            n_correct += 1

    # Coverage accuracy (suppressed if n_graded < 10)
    coverage_acc = n_correct / n_graded if n_graded >= 10 else None
    coverage_floor = max(n_graded_up, n_graded_down) / n_graded if n_graded > 0 else None
    suppressed_cov = n_graded < 10

    # Calls: all BUY or SELL decisions (used for mean_net only)
    calls = [e for e in group if e["decision"] in ("BUY", "SELL")]
    n_calls_all = len(calls)

    # Called AND graded: BUY/SELL decisions where |ret| > GRADING_BAND
    # This is the denominator for selectivity_accuracy and selectivity_floor.
    calls_graded = [
        e for e in calls
        if e["ret"] is not None and abs(e["ret"]) > GRADING_BAND
    ]
    n_called_graded = len(calls_graded)

    # Selectivity accuracy: correct / called_and_graded (suppressed if n_called_graded < 10)
    selectivity_acc = n_correct / n_called_graded if n_called_graded >= 10 else None
    suppressed_sel = n_called_graded < 10

    # Selectivity floor: majority direction among called+graded events only.
    # Same denominator as selectivity_accuracy.
    n_cg_up = sum(
        1 for e in calls_graded
        if e["direction"] == "UP" or
           (e["direction"] is None and e["ret"] is not None and e["ret"] > GRADING_BAND)
    )
    n_cg_down = sum(
        1 for e in calls_graded
        if e["direction"] == "DOWN" or
           (e["direction"] is None and e["ret"] is not None and e["ret"] < -GRADING_BAND)
    )
    sel_floor = max(n_cg_up, n_cg_down) / n_called_graded if n_called_graded > 0 else None

    # Mean net per trade: uses all BUY+SELL decisions (n_calls_all), suppressed if < 10
    nets = [e["net"] for e in calls if e["net"] is not None]
    n_trades = len(nets)
    mean_net = statistics.mean(nets) if len(nets) >= 10 else None
    suppressed_net = n_trades < 10

    suppressed_parts = []
    if suppressed_cov:
        suppressed_parts.append("coverage_accuracy")
    if suppressed_sel:
        suppressed_parts.append("selectivity_accuracy")
    if suppressed_net:
        suppressed_parts.append("mean_net_per_trade")

    return {
        "information_set": info_set,
        "arm": "human",
        "model_arm_name": "",
        "model_set": "",
        "n_readings": n,
        "mean_time_mins": round(mean_time, 1) if mean_time is not None else "",
        "median_time_mins": float(median_time) if median_time is not None else "",
        "total_time_mins": round(total_time) if total_time is not None else "",
        "buy_share": round(buy_share, 3),
        "hold_share": round(hold_share, 3),
        "sell_share": round(sell_share, 3),
        "n_graded": n_graded,
        "n_correct_coverage": n_correct,
        "coverage_accuracy": round(coverage_acc, 3) if coverage_acc is not None else "",
        "coverage_floor": round(coverage_floor, 3) if coverage_floor is not None else "",
        # n_calls = n_called_and_graded (BUY+SELL where |ret|>2%), the selectivity denominator.
        # n_calls_all (all BUY+SELL regardless of outcome) reported in notes.
        "n_calls": n_called_graded,
        "n_correct_selectivity": n_correct,
        "selectivity_accuracy": round(selectivity_acc, 3) if selectivity_acc is not None else "",
        "selectivity_floor": round(sel_floor, 3) if sel_floor is not None else "",
        "n_trades": n_trades,
        "mean_net_per_trade": round(mean_net, 6) if mean_net is not None else "",
        "suppressed": ",".join(suppressed_parts) if suppressed_parts else "none",
        "notes": _human_notes(info_set, n_calls_all),
    }


def _human_notes(info_set: str, n_calls_all: int = 0) -> str:
    # n_calls_all = raw BUY+SELL count (before grading filter); included for reference.
    notes = {
        "full": f"Re-priced returns used where available (295/420 rows); n_calls_all={n_calls_all}",
        "transcript only": f"No direct model equivalent; model never ran a transcript-only arm; n_calls_all={n_calls_all}",
        "financials": f"No direct model equivalent; model cannot mechanically isolate financial tables; n_calls_all={n_calls_all}",
        "guidance": f"No direct model equivalent; model cannot isolate a guidance-only section; n_calls_all={n_calls_all}",
        "qanda": f"Comparable to model qa_only arm; different events; n_calls_all={n_calls_all}",
        "presentation only": f"No direct model equivalent; n_graded=14 (borderline); interpret with caution; n_calls_all={n_calls_all}",
        "press release document only": f"Comparable to model press_release arm; different events; n_called_graded=9 selectivity suppressed (n<10); n_calls_all={n_calls_all}",
    }
    return notes.get(info_set, "")


# ---------------------------------------------------------------------------
# Load model arm from section ablation files
# ---------------------------------------------------------------------------
def load_model_arm():
    """Returns list of dicts (one per arm × set combination)."""
    ablation_a = BASE_DIR / "outputs" / "global" / "summary" / "section_ablation_summary.csv"
    ablation_b = BASE_DIR / "outputs" / "global" / "summary" / "section_ablation_extension_summary.csv"

    rows = []

    # Set A
    with open(ablation_a, newline="", encoding="utf-8") as f:
        lines = [l for l in f if not l.startswith("#") and l.strip()]
    reader = csv.DictReader(io.StringIO("".join(lines)))
    for row in reader:
        if row.get("label") != "four_arm":
            continue
        arm = row["arm"]
        n_events = int(row["n_events"])
        trades = int(row["trades_overnight"])
        correct = int(row["correct_overnight"])
        acc = float(row["accuracy_overnight"]) if row["accuracy_overnight"] else None

        rows.append({
            "information_set": arm,
            "arm": "model",
            "model_arm_name": arm,
            "model_set": "Set_A_N119",
            "n_readings": n_events,
            "mean_time_mins": "",
            "median_time_mins": "",
            "total_time_mins": "",
            "buy_share": "",
            "hold_share": "",
            "sell_share": "",
            "n_graded": trades,
            "n_correct_coverage": correct,
            "coverage_accuracy": round(acc, 3) if acc is not None else "",
            "coverage_floor": "",
            "n_calls": trades,
            "n_correct_selectivity": correct,
            "selectivity_accuracy": round(acc, 3) if acc is not None else "",
            "selectivity_floor": "",
            "n_trades": "",
            "mean_net_per_trade": "",
            "suppressed": "none",
            "notes": _model_notes(arm),
        })

    # Set B
    with open(ablation_b, newline="", encoding="utf-8") as f:
        lines = [l for l in f if not l.startswith("#") and l.strip()]
    reader = csv.DictReader(io.StringIO("".join(lines)))
    for row in reader:
        if row.get("set") != "four_arm":
            continue
        arm = row["arm"]
        n_events = int(row["n_events"])
        trades = int(row["trades"])
        correct = int(row["correct"])
        acc = float(row["accuracy"]) if row["accuracy"] else None

        rows.append({
            "information_set": arm,
            "arm": "model",
            "model_arm_name": arm,
            "model_set": "Set_B_N56",
            "n_readings": n_events,
            "mean_time_mins": "",
            "median_time_mins": "",
            "total_time_mins": "",
            "buy_share": "",
            "hold_share": "",
            "sell_share": "",
            "n_graded": trades,
            "n_correct_coverage": correct,
            "coverage_accuracy": round(acc, 3) if acc is not None else "",
            "coverage_floor": "",
            "n_calls": trades,
            "n_correct_selectivity": correct,
            "selectivity_accuracy": round(acc, 3) if acc is not None else "",
            "selectivity_floor": "",
            "n_trades": "",
            "mean_net_per_trade": "",
            "suppressed": "none",
            "notes": _model_notes_b(arm),
        })

    return rows


def _model_notes(arm: str) -> str:
    notes = {
        "full_bundle": "Selectivity = correct/trades (graded correct / all BUY+SELL calls including flat outcomes)",
        "press_release": "Model press_release arm; different events from human press release doc only",
        "prepared_remarks": "No direct human equivalent; model prepared_remarks = transcript minus Q&A",
        "qa_only": "Model qa_only arm; different events from human qanda",
    }
    return notes.get(arm, "")


def _model_notes_b(arm: str) -> str:
    notes = {
        "full_bundle": "Set B (extension events); same arm definition as Set A",
        "press_release": "Set B (extension events)",
        "prepared_remarks": "Set B (extension events)",
        "qa_only": "Set B (extension events)",
    }
    return notes.get(arm, "")


# ---------------------------------------------------------------------------
# Write CSV
# ---------------------------------------------------------------------------
HEADER_COMMENTS = f"""# Information set comparison: human arm by information set vs model arm section ablation
# Generated: {DATE}
# Source (human): data/workbook/Master_Data_CORRECTED_2026-08-14.xlsx, Human_Data_Entry sheet
# Source (model Set A, N=119): outputs/global/summary/section_ablation_summary.csv, run 20260812T131110Z
# Source (model Set B, N=56): outputs/global/summary/section_ablation_extension_summary.csv, run 20260813T234207Z
# Source (model paired diffs): outputs/global/summary/section_ablation_paired_diffs.csv
# Source (model cost): outputs/global/summary/section_ablation_cost_per_correct.csv
#
# Definitions:
#   coverage_accuracy = n_correct / n_graded
#     where n_graded = rows with |actual_overnight_return| > 0.02
#     and n_correct = rows where decision is BUY and outcome is UP, or decision is SELL and outcome is DOWN
#     (outcome direction derived from re-priced return where available, else original return)
#     Outcome UP = ret > 0.02, Outcome DOWN = ret < -0.02
#   coverage_floor = max(n_graded_UP, n_graded_DOWN) / n_graded  (majority-class baseline)
#     coverage_floor and coverage_accuracy share denominator n_graded.
#
#   Human selectivity_accuracy = n_correct / n_called_and_graded
#     where n_called_and_graded = BUY+SELL decisions where |ret| > 0.02 (called events with graded outcomes)
#     n_correct = BUY with UP outcome OR SELL with DOWN outcome, among called+graded events only
#   Human selectivity_floor = max(n_called_graded_UP, n_called_graded_DOWN) / n_called_and_graded
#     floor and accuracy share the same denominator (n_called_and_graded).
#     n_called_graded_UP/DOWN = directional counts among called+graded events only.
#
#   NOTE: n_calls (human) = n_called_and_graded, the selectivity denominator.
#   The raw BUY+SELL count (regardless of outcome) is stored in the notes column as n_calls_all.
#
#   Model selectivity_accuracy = correct / trades from the section ablation files
#     where trades = all BUY+SELL calls (including flat/ungraded outcomes)
#     correct = graded correct (matched direction AND |ret|>2%)
#   Model n_calls = trades (all BUY+SELL, NOT filtered to |ret|>2%).
#   CROSS-ARM DENOMINATOR MISMATCH: human n_calls = called+graded; model n_calls = all trades.
#   Cross-arm selectivity comparisons examine the pattern only; denominators differ.
#
#   mean_net_per_trade = mean of re-priced Net P&L (or original) for all BUY+SELL decisions
#     Net P&L: BUY -> ret - 0.001, SELL -> -ret - 0.001, HOLD -> 0 (10bps round-trip cost)
#
# Grading band: +-2% raw overnight return (pre-registered)
# Suppression threshold: coverage suppressed if n_graded < 10; selectivity suppressed if n_called_and_graded < 10
#
# IMPORTANT: Section-level reads (transcript only, qanda, financials, guidance, presentation only,
#   press release document only) are a DIFFERENT experiment from full-document reads.
#   They cover different events, different raters, and different reading sessions.
#   Do not pool them with the full-document group or with each other for accuracy estimation.
#
# IMPORTANT: Human and model sessions cover DIFFERENT events.
#   The cross-arm comparison (human vs model) is of the PATTERN (flat vs differentiated),
#   not a direct head-to-head on the same events.
#
# Column definitions:
#   information_set: label for the information set read
#   arm: human or model
#   model_arm_name: model arm label where applicable (else blank)
#   model_set: which model event set (Set_A_N119, Set_B_N56, or blank)
#   n_readings: total rows in the human arm for this information set
#   mean_time_mins: mean reading time in minutes (human arm only)
#   median_time_mins: median reading time in minutes (human arm only)
#   total_time_mins: total reading time in minutes (human arm only)
#   buy_share: fraction of decisions that are BUY
#   hold_share: fraction of decisions that are HOLD
#   sell_share: fraction of decisions that are SELL
#   n_graded: rows with |ret| > 2% (human) or n_events (model); coverage denominator
#   n_correct_coverage: correct directional predictions among graded events
#   coverage_accuracy: n_correct_coverage / n_graded (suppressed if n_graded < 10)
#   coverage_floor: max(n_graded_UP, n_graded_DOWN) / n_graded; same denominator as coverage_accuracy
#   n_calls: BUY+SELL decisions where |ret|>2% (human, = n_called_and_graded, selectivity denominator)
#            OR all BUY+SELL trades (model). See cross-arm denominator mismatch note above.
#   n_correct_selectivity: correct directional predictions among called+graded events
#   selectivity_accuracy: n_correct_selectivity / n_calls (suppressed if n_calls < 10)
#   selectivity_floor: max(called_graded_UP, called_graded_DOWN) / n_calls; same denominator as selectivity_accuracy
#   n_trades: BUY+SELL calls with non-None net P&L (= n_calls_all for human, used for mean_net only)
#   mean_net_per_trade: mean net P&L per trade (suppressed if n_trades < 10)
#   suppressed: which metrics are suppressed due to small n
#   notes: additional notes; human rows include n_calls_all (raw BUY+SELL count before grading filter)
"""

FIELDNAMES = [
    "information_set", "arm", "model_arm_name", "model_set",
    "n_readings", "mean_time_mins", "median_time_mins", "total_time_mins",
    "buy_share", "hold_share", "sell_share",
    "n_graded", "n_correct_coverage", "coverage_accuracy", "coverage_floor",
    "n_calls", "n_correct_selectivity", "selectivity_accuracy", "selectivity_floor",
    "n_trades", "mean_net_per_trade",
    "suppressed", "notes",
]

# Order for human arm rows in output
HUMAN_ORDER = [
    "full", "transcript only", "financials", "guidance",
    "qanda", "presentation only", "press release document only",
]

# Order for model arm rows
MODEL_ORDER = ["full_bundle", "press_release", "qa_only", "prepared_remarks"]


def write_csv(human_rows: dict, model_rows: list, out_path: Path) -> None:
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        f.write(HEADER_COMMENTS)
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

        for info_set in HUMAN_ORDER:
            if info_set in human_rows:
                writer.writerow(human_rows[info_set])

        # Model rows: Set A first, then Set B, grouped by arm
        set_a = [r for r in model_rows if r["model_set"] == "Set_A_N119"]
        set_b = [r for r in model_rows if r["model_set"] == "Set_B_N56"]

        for arm in MODEL_ORDER:
            for r in set_a:
                if r["model_arm_name"] == arm:
                    writer.writerow(r)
            for r in set_b:
                if r["model_arm_name"] == arm:
                    writer.writerow(r)


# ---------------------------------------------------------------------------
# Write Markdown
# ---------------------------------------------------------------------------
def write_md(human_rows: dict, model_rows: list, out_path: Path) -> None:
    lines = [
        f"# Information-Set Comparison: Human vs Model Arm",
        f"",
        f"**Generated:** {DATE}  ",
        f"**Script:** `experiments/information_set_comparison.py`  ",
        f"**Source (human):** `data/workbook/Master_Data_CORRECTED_2026-08-14.xlsx` Human_Data_Entry  ",
        f"**Source (model):** `outputs/global/summary/section_ablation_summary.csv` (Set A), "
        f"`section_ablation_extension_summary.csv` (Set B)  ",
        f"**Grading band:** ±2% raw overnight (pre-registered)",
        f"",
        f"---",
        f"",
        f"## Caveats",
        f"",
        f"- Section-level reads (transcript only, qanda, financials, guidance, presentation only, "
        f"press release document only) are a **different experiment** from full-document reads. "
        f"They cover different events, different raters, and different reading sessions. "
        f"Do not pool them with each other or with the full group.",
        f"",
        f"- Human and model sessions cover **different events**. The cross-arm comparison "
        f"examines the **pattern** (flat vs differentiated across information sets), "
        f"not a head-to-head on the same events.",
        f"",
        f"- Re-priced returns used where available for the human arm.",
        f"",
        f"---",
        f"",
        f"## 1. Human Arm by Information Set",
        f"",
        f"| Information Set | n | Mean Time (min) | Median Time | Buy% | Hold% | Sell% | n_graded | Coverage Acc | n_calls | Selectivity Acc | Mean Net/Trade |",
        f"| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for info_set in HUMAN_ORDER:
        r = human_rows.get(info_set, {})
        if not r:
            continue
        cov_acc = r["coverage_accuracy"]
        sel_acc = r["selectivity_accuracy"]
        mean_net = r["mean_net_per_trade"]
        cov_str = f"{cov_acc:.3f}" if cov_acc != "" else "suppressed"
        sel_str = f"{sel_acc:.3f}" if sel_acc != "" else "suppressed"
        net_str = f"{mean_net:.6f}" if mean_net != "" else "suppressed"
        lines.append(
            f"| {info_set} | {r['n_readings']} | {r['mean_time_mins']} | {r['median_time_mins']} | "
            f"{r['buy_share']:.1%} | {r['hold_share']:.1%} | {r['sell_share']:.1%} | "
            f"{r['n_graded']} | {cov_str} | {r['n_calls']} | {sel_str} | {net_str} |"
        )
    lines.append("")

    lines.append("### Observations")
    lines.append("")
    lines.append("- **Selectivity denominator**: n_calls here is n_called_and_graded (BUY+SELL decisions "
                 "where |ret|>2%), NOT the raw BUY+SELL count. Raw counts are in the notes column "
                 "(n_calls_all). This ensures selectivity_floor and selectivity_accuracy share the same "
                 "denominator. The model arm uses all trades (including flat outcomes) as denominator — "
                 "cross-arm selectivity comparisons are pattern-only; denominators differ.")
    lines.append("")
    lines.append("- **Transcript anomaly**: transcript-only mean reading time 33.5 min vs full 29.8 min. "
                 "Transcript-only sessions read one section that is longer and denser than an average section "
                 "of the full bundle. The full-bundle time includes all sections in one sitting; some "
                 "raters may have read the transcript last and been more efficient.")
    lines.append("")
    lines.append("- **Guidance coverage accuracy 15.0%** (n_graded=20): below the 55% coverage floor. "
                 "Guidance notes contain forward-looking language with high forecast uncertainty — "
                 "the guidance alone does not predict the overnight direction reliably.")
    lines.append("")
    lines.append("- **Presentation only coverage 64.3%** (n_graded=14, borderline): above the 57.1% floor. "
                 "n_graded=14 is marginal. Interpret with caution.")
    lines.append("")
    lines.append("- **Press release doc only selectivity suppressed** (n_called_graded=9, below threshold of 10). "
                 "n_calls_all=11 but only 9 of those calls have a graded outcome (|ret|>2%). "
                 "Coverage accuracy 46.7% (n_graded=15) is reportable.")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 2. Model Arm Section Ablation")
    lines.append("")
    lines.append("| Arm | Set | n_events | Trades | Correct | Selectivity Acc |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for arm in MODEL_ORDER:
        for r in model_rows:
            if r["model_arm_name"] == arm:
                lines.append(
                    f"| {arm} | {r['model_set']} | {r['n_readings']} | {r['n_calls']} | "
                    f"{r['n_correct_selectivity']} | {r['selectivity_accuracy']} |"
                )
    lines.append("")

    lines.append("### Cross-arm pattern comparison")
    lines.append("")
    lines.append("Both human and model arms show flat accuracy across information sets — "
                 "no single section reliably raises or lowers accuracy by more than a few pp "
                 "within the detectable range (MDE ≈ ±12pp paired, ±20pp unpaired).")
    lines.append("")
    lines.append("Model Item C (section ablation, Set A four-arm, N=119):")
    set_a_accs = {r["model_arm_name"]: r["selectivity_accuracy"]
                  for r in model_rows if r["model_set"] == "Set_A_N119"}
    if set_a_accs:
        vals = [v for v in set_a_accs.values() if v != ""]
        lines.append(f"- Range: {min(vals):.1%}–{max(vals):.1%} across four arms "
                     f"(full_bundle {set_a_accs.get('full_bundle','?')}, "
                     f"press_release {set_a_accs.get('press_release','?')}, "
                     f"qa_only {set_a_accs.get('qa_only','?')}, "
                     f"prepared_remarks {set_a_accs.get('prepared_remarks','?')})")
    lines.append("")
    lines.append("Model Item C (Set B, N=56):")
    set_b_accs = {r["model_arm_name"]: r["selectivity_accuracy"]
                  for r in model_rows if r["model_set"] == "Set_B_N56"}
    if set_b_accs:
        vals = [v for v in set_b_accs.values() if v != ""]
        lines.append(f"- Range: {min(vals):.1%}–{max(vals):.1%} across four arms")
    lines.append("")

    # Cost note
    lines.append("### Cost note")
    lines.append("")
    lines.append("From `section_ablation_cost_per_correct.csv` (four_arm N=119, overnight grading):")
    lines.append("")
    lines.append("| Arm | Cost per correct call |")
    lines.append("| --- | --- |")
    lines.append("| full_bundle | $0.036 |")
    lines.append("| prepared_remarks | $0.021 |")
    lines.append("| qa_only | $0.023 |")
    lines.append("| press_release | $0.023 |")
    lines.append("")
    lines.append("prepared_remarks costs 42% less per correct call than full_bundle "
                 "at comparable accuracy (33.8% vs 36.8%).")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 3. Comparable Pairs")
    lines.append("")
    lines.append("| Human information set | Model arm | Human sel. acc | Model sel. acc (Set A) | Model sel. acc (Set B) |")
    lines.append("| --- | --- | --- | --- | --- |")
    hqa = human_rows.get("qanda", {})
    mqa_a = next((r for r in model_rows if r["model_arm_name"] == "qa_only" and r["model_set"] == "Set_A_N119"), {})
    mqa_b = next((r for r in model_rows if r["model_arm_name"] == "qa_only" and r["model_set"] == "Set_B_N56"), {})
    lines.append(f"| qanda | qa_only | {hqa.get('selectivity_accuracy', '?')} | "
                 f"{mqa_a.get('selectivity_accuracy', '?')} | {mqa_b.get('selectivity_accuracy', '?')} |")
    hpr = human_rows.get("press release document only", {})
    mpr_a = next((r for r in model_rows if r["model_arm_name"] == "press_release" and r["model_set"] == "Set_A_N119"), {})
    mpr_b = next((r for r in model_rows if r["model_arm_name"] == "press_release" and r["model_set"] == "Set_B_N56"), {})
    lines.append(f"| press release document only | press_release | {hpr.get('selectivity_accuracy', '?')} | "
                 f"{mpr_a.get('selectivity_accuracy', '?')} | {mpr_b.get('selectivity_accuracy', '?')} |")
    hfull = human_rows.get("full", {})
    mfull_a = next((r for r in model_rows if r["model_arm_name"] == "full_bundle" and r["model_set"] == "Set_A_N119"), {})
    mfull_b = next((r for r in model_rows if r["model_arm_name"] == "full_bundle" and r["model_set"] == "Set_B_N56"), {})
    lines.append(f"| full | full_bundle | {hfull.get('selectivity_accuracy', '?')} | "
                 f"{mfull_a.get('selectivity_accuracy', '?')} | {mfull_b.get('selectivity_accuracy', '?')} |")
    lines.append("")
    lines.append("Human and model comparisons are across **different events** — pattern comparison only.")
    lines.append("")
    lines.append("**Denominator note**: human selectivity uses n_called_and_graded (BUY+SELL where |ret|>2%); "
                 "model selectivity uses all trades (BUY+SELL including flat outcomes). "
                 "Human n_calls_all (raw BUY+SELL count) is in the notes column of the CSV. "
                 "This mismatch means the human selectivity figures are not directly comparable to model figures "
                 "in magnitude — the cross-arm comparison is of pattern (flat vs differentiated) only.")
    lines.append("")
    lines.append("**Impact on Item C comparison (section ablation)**: "
                 "Human full selectivity on the corrected denominator is "
                 f"{hfull.get('selectivity_accuracy', '?')} (n_called_graded={hfull.get('n_calls', '?')}), "
                 f"vs model full_bundle Set A {mfull_a.get('selectivity_accuracy', '?')} "
                 f"and Set B {mfull_b.get('selectivity_accuracy', '?')}. "
                 "The human figure exceeds the model on the corrected denominator, reversing the direction "
                 "of the comparison from the prior (all-calls) denominator. "
                 "The denominator definitions differ, so this is not a clean head-to-head.")

    out_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Loading human arm from workbook...", file=sys.stderr)
    all_events = load_human_arm()
    total = len(all_events)
    print(f"  {total} human data rows loaded", file=sys.stderr)

    # Compute per-information-set metrics
    info_sets = ["full", "transcript only", "financials", "guidance",
                 "qanda", "presentation only", "press release document only"]
    human_rows = {}
    for info_set in info_sets:
        m = human_metrics(all_events, info_set)
        if m:
            human_rows[info_set] = m
            print(f"  {info_set}: n={m['n_readings']}", file=sys.stderr)

    print("Loading model arm from ablation files...", file=sys.stderr)
    model_rows = load_model_arm()
    print(f"  {len(model_rows)} model arm rows", file=sys.stderr)

    out_dir = BASE_DIR / "outputs" / "global" / "summary"
    csv_path = out_dir / f"information_set_comparison_{DATE}.csv"
    md_path = out_dir / f"information_set_comparison_{DATE}.md"

    write_csv(human_rows, model_rows, csv_path)
    print(f"Wrote {csv_path}", file=sys.stderr)

    write_md(human_rows, model_rows, md_path)
    print(f"Wrote {md_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
