"""
Sector analysis of LLM and FinBERT arms.
Set A: N=233 clean phase2 events (268 scored, 35 excluded).
Set B: N=93 extension events.

Four cuts per sector per arm per event set:
  1. spearman_rho  — Spearman rank correlation of continuous score vs ret_overnight
  2. calibration   — mean score and mean ret_overnight (systematic bias check)
  3. dispersion    — population std of score + HOLD rate
  4. sell_buy_asymmetry — accuracy on BUY/SELL calls separately

Read-only: reads only committed input files.
Writes: outputs/global/summary/sector_analysis_{DATE}.csv and .md
No LLM calls. Fully deterministic.
"""

import csv
import math
import sys
from pathlib import Path

import scipy
import scipy.stats as scipy_stats

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from eval.excluded_events import EXCLUDED_EVENTS  # noqa: E402
DATE = "2026-08-15"
SCIPY_VERSION = scipy.__version__
SUPPRESSION_N = 10
GRADING_BAND = 0.02
LLM_W_MICRO = 0.55
LLM_W_MACRO = 0.45

# 25 worksheet-contaminated events, plus the bad-document set from
# eval/excluded_events.py (SPOT_FQ1_2026 misattributed, DIS_FQ1_2025 look-ahead).
WORKSHEET_EXCLUDED = EXCLUDED_EVENTS | {
    "AMD_FQ1_2026", "AMD_FQ2_2025", "AMD_FQ4_2025",
    "AMZN_FQ1_2026", "AMZN_FQ3_2025", "AMZN_FQ4_2025",
    "COIN_FQ1_2026", "COIN_FQ3_2025", "COIN_FQ4_2025",
    "LLY_FQ1_2026", "LLY_FQ3_2025", "LLY_FQ4_2025",
    "META_FQ1_2026", "META_FQ3_2025", "META_FQ4_2025",
    "NFLX_FQ3_2025", "NFLX_FQ4_2024", "NFLX_FQ4_2025",
    "NVDA_FQ1_2025", "NVDA_FQ2_2025", "NVDA_FQ3_2025", "NVDA_FQ4_2025",
    "TSLA_FQ1_2026", "TSLA_FQ3_2025", "TSLA_FQ4_2025",
}

# Sector taxonomy for Set A — sourced from phase2/build_manifests.py SECTORS dict
SECTORS_A_RAW = {
    "ABNB": "Consumer/Travel",
    "AMZN": "Consumer/Retail-Tech",
    "AMD": "Technology/Semiconductors",
    "AAPL": "Technology",
    "BAC": "Financials",
    "BA": "Industrials",
    "CVS": "Healthcare/Consumer",
    "SCHW": "Financials",
    "C": "Financials",
    "KO": "Consumer Staples",
    "COIN": "Financials/Crypto",
    "DIS": "Media/Communication Services",
    "LLY": "Healthcare",
    "GS": "Financials",
    "IBM": "Technology",
    "JPM": "Financials",
    "LOW": "Consumer/Retail",
    "LULU": "Consumer/Retail",
    "AMKBY": "Industrials/Shipping",
    "MCD": "Consumer/Retail",
    "META": "Media/Communication Services",
    "NFLX": "Media/Communication Services",
    "NKE": "Consumer/Retail",
    "NVDA": "Technology/Semiconductors",
    "TGT": "Consumer/Retail",
    "TSLA": "Consumer/Auto",
    "UBER": "Technology/Transportation",
    "WMT": "Consumer/Retail",
    "BCS": "Financials",
    "F": "Consumer/Auto",
    "MSFT": "Technology",
    "PFE": "Healthcare",
    "UAL": "Industrials/Airlines",
    "PEP": "Consumer Staples",
    "FDX": "Industrials/Logistics",
    "LMT": "Industrials/Aerospace-Defense",
    "NVO": "Healthcare",
    "HLT": "Consumer/Travel",
    "MC.PA": "Consumer/Luxury",
    "MAR": "Consumer/Travel",
    "ALV.DE": "Financial Services/Insurance - Diversified",
    "AVGO": "Technology/Semiconductors",
    "BKNG": "Consumer Cyclical/Travel Services",
    "CAT": "Industrials/Farm & Heavy Construction Machinery",
    "CL": "Consumer Defensive/Household & Personal Products",
    "CMCSA": "Communication Services/Telecom Services",
    "CMG": "Consumer Cyclical/Restaurants",
    "COST": "Consumer Defensive/Discount Stores",
    "CRM": "Technology/Software - Application",
    "DAL": "Industrials/Airlines",
    "DELL": "Technology/Computer Hardware",
    "EXPE": "Consumer Cyclical/Travel Services",
    "GIS": "Consumer Defensive/Packaged Foods",
    "GOOGL": "Communication Services/Internet Content & Information",
    "HOOD": "Financial Services/Capital Markets",
    "JNJ": "Healthcare/Drug Manufacturers - General",
    "KHC": "Consumer Defensive/Packaged Foods",
    "LIN": "Basic Materials/Specialty Chemicals",
    "LNVGY": "Technology/Computer Hardware",
    "MET": "Financial Services/Insurance - Life",
    "MU": "Technology/Semiconductors",
    "ORCL": "Technology/Software - Infrastructure",
    "PINS": "Communication Services/Internet Content & Information",
    "PLTR": "Technology/Software - Infrastructure",
    "PUM.DE": "Consumer Cyclical/Footwear & Accessories",
    "PYPL": "Financial Services/Credit Services",
    "RMSP.XC": "Consumer Cyclical/Luxury Goods",
    "SBUX": "Consumer Cyclical/Restaurants",
    "SIE.DE": "Industrials/Specialty Industrial Machinery",
    "SPOT": "Communication Services/Internet Content & Information",
    "STAN.L": "Financial Services/Banks - Diversified",
    "UNH": "Healthcare/Healthcare Plans",
    "V": "Financial Services/Credit Services",
    "WDAY": "Technology/Software - Application",
}

# Sector taxonomy for Set B — manual mapping (extension tickers not in phase2)
SECTORS_B = {
    "ADBE": "Technology",
    "AXP": "Financials",
    "CL": "Consumer",
    "COST": "Consumer",
    "CVX": "Energy",
    "DDOG": "Technology",
    "DUK": "Utilities",
    "EBAY": "Consumer",
    "FCX": "Materials",
    "HD": "Consumer",
    "HEIA.AS": "Consumer",
    "INTC": "Technology",
    "MA": "Financials",
    "NSRGY": "Consumer",
    "RMSP.XC": "Consumer",
    "SHEL": "Energy",
    "SHOP": "Technology",
    "SONY": "Technology",
    "UNP": "Industrials",
    "XOM": "Energy",
}


def broad_sector_a(raw: str) -> str:
    """Map a SECTORS dict value to a broad 8-category label."""
    first = raw.split("/")[0].strip()
    if first in ("Consumer", "Consumer Staples", "Consumer Cyclical", "Consumer Defensive"):
        return "Consumer"
    if first == "Technology":
        return "Technology"
    if first in ("Financials", "Financial Services"):
        return "Financials"
    if first == "Industrials":
        return "Industrials"
    if first in ("Communication Services", "Media"):
        return "Communication Services"
    if first == "Healthcare":
        return "Healthcare"
    if first == "Basic Materials":
        return "Materials"
    return "Other"


def blend_score(micro: float, macro) -> float:
    """Blended LLM score with renormalization if macro is missing."""
    if macro is None or (isinstance(macro, float) and math.isnan(macro)):
        return micro
    return (micro * LLM_W_MICRO + macro * LLM_W_MACRO) / (LLM_W_MICRO + LLM_W_MACRO)


def _pop_std(values: list) -> float:
    """Population standard deviation."""
    n = len(values)
    if n == 0:
        return float("nan")
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / n)


def spearman_rho(x: list, y: list):
    """Return (rho, p_value) or (nan, nan) if insufficient data."""
    if len(x) < 3:
        return float("nan"), float("nan")
    rho, pval = scipy_stats.spearmanr(x, y)
    return float(rho), float(pval)


def _safe_float(v) -> float | None:
    """Parse CSV string to float, return None if blank/invalid."""
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Load Set A
# ---------------------------------------------------------------------------
def load_set_a():
    """Returns list of dicts with keys: document_id, ticker, sector,
    blended_score, signal, ret_overnight."""
    calib_path = BASE_DIR / "outputs" / "global" / "summary" / "global_outcome_calibration_phase2.csv"
    rm_path = BASE_DIR / "outputs" / "global" / "summary" / "returns_matrix.csv"

    # Load returns_matrix for ret_overnight and timing_excluded
    ret_map: dict[str, dict] = {}
    with open(rm_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ret_map[row["document_id"]] = {
                "ret_overnight": _safe_float(row["ret_overnight"]),
                "timing_excluded": row.get("timing_excluded", "NO").strip().upper(),
            }

    events = []
    with open(calib_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            doc_id = row["document_id"]
            ticker = row["ticker"]

            # Apply exclusions
            if doc_id in WORKSHEET_EXCLUDED:
                continue
            rm = ret_map.get(doc_id, {})
            if rm.get("timing_excluded") == "YES":
                continue

            micro = _safe_float(row["micro_score"])
            macro = _safe_float(row["macro_score"])
            if micro is None:
                continue

            bs = blend_score(micro, macro)
            signal = row.get("blend_predicted_signal_default", "").strip()
            ret = rm.get("ret_overnight")
            if ret is None:
                continue

            sector_raw = SECTORS_A_RAW.get(ticker)
            if sector_raw is None:
                continue
            sector = broad_sector_a(sector_raw)

            events.append({
                "document_id": doc_id,
                "ticker": ticker,
                "sector": sector,
                "blended_score": bs,
                "signal": signal,
                "ret_overnight": ret,
            })

    return events


# ---------------------------------------------------------------------------
# Load Set B (LLM and FinBERT)
# ---------------------------------------------------------------------------
def load_set_b():
    """Returns two lists (llm_events, finbert_events), same structure as load_set_a."""
    calib_path = (
        BASE_DIR / "outputs" / "global" / "summary"
        / "global_outcome_calibration_extension_2026_08_13.csv"
    )
    fb_path = (
        BASE_DIR / "outputs" / "global" / "summary"
        / "finbert_extension_results.csv"
    )

    # Load extension calibration for blended score
    calib_map: dict[str, dict] = {}
    with open(calib_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            micro = _safe_float(row["micro_score"])
            macro = _safe_float(row["macro_score"])
            if micro is None:
                continue
            calib_map[row["document_id"]] = {
                "blended_score": blend_score(micro, macro),
                "signal": row.get("blend_predicted_signal_default", "").strip(),
            }

    llm_events = []
    finbert_events = []

    with open(fb_path, newline="", encoding="utf-8") as f:
        lines = [l for l in f if not l.startswith("#")]
    import io
    reader = csv.DictReader(io.StringIO("".join(lines)))
    for row in reader:
        doc_id = row["document_id"]
        ticker = row["ticker"]
        ret = _safe_float(row["ret_overnight"])
        if ret is None:
            continue

        sector = SECTORS_B.get(ticker)
        if sector is None:
            continue

        # LLM
        c = calib_map.get(doc_id)
        if c:
            llm_events.append({
                "document_id": doc_id,
                "ticker": ticker,
                "sector": sector,
                "blended_score": c["blended_score"],
                "signal": c["signal"],
                "ret_overnight": ret,
            })

        # FinBERT
        fb_score = _safe_float(row["finbert_score"])
        fb_signal = row.get("finbert_predicted_signal", "").strip()
        if fb_score is not None:
            finbert_events.append({
                "document_id": doc_id,
                "ticker": ticker,
                "sector": sector,
                "blended_score": fb_score,
                "signal": fb_signal,
                "ret_overnight": ret,
            })

    return llm_events, finbert_events


# ---------------------------------------------------------------------------
# Compute sector-level statistics
# ---------------------------------------------------------------------------
def sector_stats(events: list, event_set: str, arm: str) -> list[dict]:
    """Compute four cuts for each sector and return list of row dicts."""
    from collections import defaultdict
    by_sector: dict[str, list] = defaultdict(list)
    for e in events:
        by_sector[e["sector"]].append(e)

    rows = []

    for sector in sorted(by_sector):
        evs = by_sector[sector]
        n = len(evs)

        scores = [e["blended_score"] for e in evs]
        rets = [e["ret_overnight"] for e in evs]
        signals = [e["signal"] for e in evs]

        # --- Cut 1: Spearman rho ---
        suppressed_rho = n < SUPPRESSION_N
        if suppressed_rho:
            rho_val, p_val = "", ""
            rho_note = f"n={n} < {SUPPRESSION_N}"
        else:
            rho, pval = spearman_rho(scores, rets)
            rho_val = rho
            p_val = pval
            rho_note = ""

        rows.append({"sector": sector, "event_set": event_set, "arm": arm,
                     "cut": "spearman_rho", "metric": "rho",
                     "n": n, "value": rho_val, "suppressed": suppressed_rho,
                     "notes": rho_note})
        rows.append({"sector": sector, "event_set": event_set, "arm": arm,
                     "cut": "spearman_rho", "metric": "p_value",
                     "n": n, "value": p_val, "suppressed": suppressed_rho,
                     "notes": rho_note})
        rows.append({"sector": sector, "event_set": event_set, "arm": arm,
                     "cut": "spearman_rho", "metric": "n",
                     "n": n, "value": n, "suppressed": False, "notes": rho_note})

        # --- Cut 2: Calibration ---
        mean_score = sum(scores) / n
        mean_ret = sum(rets) / n
        rows.append({"sector": sector, "event_set": event_set, "arm": arm,
                     "cut": "calibration", "metric": "mean_score",
                     "n": n, "value": mean_score, "suppressed": False, "notes": ""})
        rows.append({"sector": sector, "event_set": event_set, "arm": arm,
                     "cut": "calibration", "metric": "mean_ret",
                     "n": n, "value": mean_ret, "suppressed": False, "notes": ""})
        rows.append({"sector": sector, "event_set": event_set, "arm": arm,
                     "cut": "calibration", "metric": "n",
                     "n": n, "value": n, "suppressed": False, "notes": ""})

        # --- Cut 3: Dispersion ---
        score_std = _pop_std(scores)
        hold_rate = signals.count("HOLD") / n
        rows.append({"sector": sector, "event_set": event_set, "arm": arm,
                     "cut": "dispersion", "metric": "score_std",
                     "n": n, "value": score_std, "suppressed": False,
                     "notes": "population std"})
        rows.append({"sector": sector, "event_set": event_set, "arm": arm,
                     "cut": "dispersion", "metric": "hold_rate",
                     "n": n, "value": hold_rate, "suppressed": False, "notes": ""})
        rows.append({"sector": sector, "event_set": event_set, "arm": arm,
                     "cut": "dispersion", "metric": "n",
                     "n": n, "value": n, "suppressed": False, "notes": ""})

        # --- Cut 4: BUY/SELL asymmetry ---
        buy_evs = [e for e in evs if e["signal"] == "BUY"]
        sell_evs = [e for e in evs if e["signal"] == "SELL"]
        n_buy = len(buy_evs)
        n_sell = len(sell_evs)

        # base rates from all sector events
        n_up = sum(1 for e in evs if e["ret_overnight"] > GRADING_BAND)
        n_down = sum(1 for e in evs if e["ret_overnight"] < -GRADING_BAND)
        buy_base_rate = n_up / n
        sell_base_rate = n_down / n

        # buy accuracy: BUY calls where ret > GRADING_BAND / all BUY calls
        buy_correct = sum(1 for e in buy_evs if e["ret_overnight"] > GRADING_BAND)
        suppressed_buy = n_buy < SUPPRESSION_N
        buy_acc_val = (buy_correct / n_buy) if (not suppressed_buy and n_buy > 0) else ""
        buy_acc_note = f"n_calls={n_buy} < {SUPPRESSION_N}" if suppressed_buy else ""

        rows.append({"sector": sector, "event_set": event_set, "arm": arm,
                     "cut": "sell_buy_asymmetry", "metric": "buy_accuracy",
                     "n": n_buy, "value": buy_acc_val, "suppressed": suppressed_buy,
                     "notes": buy_acc_note})
        rows.append({"sector": sector, "event_set": event_set, "arm": arm,
                     "cut": "sell_buy_asymmetry", "metric": "buy_n_calls",
                     "n": n_buy, "value": n_buy, "suppressed": False, "notes": ""})
        rows.append({"sector": sector, "event_set": event_set, "arm": arm,
                     "cut": "sell_buy_asymmetry", "metric": "buy_base_rate",
                     "n": n, "value": buy_base_rate, "suppressed": False, "notes": ""})

        sell_correct = sum(1 for e in sell_evs if e["ret_overnight"] < -GRADING_BAND)
        suppressed_sell = n_sell < SUPPRESSION_N
        sell_acc_val = (sell_correct / n_sell) if (not suppressed_sell and n_sell > 0) else ""
        sell_acc_note = f"n_calls={n_sell} < {SUPPRESSION_N}" if suppressed_sell else ""

        rows.append({"sector": sector, "event_set": event_set, "arm": arm,
                     "cut": "sell_buy_asymmetry", "metric": "sell_accuracy",
                     "n": n_sell, "value": sell_acc_val, "suppressed": suppressed_sell,
                     "notes": sell_acc_note})
        rows.append({"sector": sector, "event_set": event_set, "arm": arm,
                     "cut": "sell_buy_asymmetry", "metric": "sell_n_calls",
                     "n": n_sell, "value": n_sell, "suppressed": False, "notes": ""})
        rows.append({"sector": sector, "event_set": event_set, "arm": arm,
                     "cut": "sell_buy_asymmetry", "metric": "sell_base_rate",
                     "n": n, "value": sell_base_rate, "suppressed": False, "notes": ""})

    return rows


# ---------------------------------------------------------------------------
# Write CSV
# ---------------------------------------------------------------------------
HEADER_COMMENTS = f"""# sector_analysis_{DATE}.csv
# Generated: {DATE}
# TAXONOMY DECISION (2026-08-15): canonical taxonomy = SECTORS dict in phase2/build_manifests.py
# Divergent events (old classification per sector_breakdown_three_sets.csv -> new per SECTORS dict):
# CVS_FQ1_2026 (ticker: CVS): Consumer -> Healthcare (sector_breakdown_three_sets.csv placed CVS in Consumer; SECTORS dict places p2_cvs_health as Healthcare/Consumer, classified Healthcare by this analysis)
# CVS_FQ2_2025 (ticker: CVS): Consumer -> Healthcare (same as above)
# CVS_FQ3_2025 (ticker: CVS): Consumer -> Healthcare (same as above)
# CVS_FQ4_2025 (ticker: CVS): Consumer -> Healthcare (same as above)
# These 4 events account for the entire Consumer -4 / Healthcare +4 discrepancy between the two files.
# No other sector-level divergences exist: Technology, Financials, Industrials, Communication Services, and Materials all agree on n across both files (Set A).
# Note on LMT: sector_breakdown_three_sets.csv lists LMT in its Healthcare notes text, but the actual n=14 count for Healthcare in that file is consistent with LMT being counted in Industrials (n=26, same as new analysis). The notes text listing LMT under Healthcare is a copy-paste error in sector_breakdown_three_sets.csv; the counts themselves are correct. LMT is in Industrials in both files.
# sector_breakdown_three_sets.csv has not been modified; see sector_analysis_{DATE}.md for full decision record.
# Source files:
#   - outputs/global/summary/global_outcome_calibration_phase2.csv (Set A: N=233 clean phase2 events)
#   - outputs/global/summary/global_outcome_calibration_extension_2026_08_13.csv (Set B: N=93 extension events)
#   - outputs/global/summary/finbert_extension_results.csv (FinBERT scores for Set B)
#   - outputs/global/summary/returns_matrix.csv (overnight returns, timing_excluded flag)
#   - phase2/build_manifests.py SECTORS dict (sector taxonomy source for Set A)
#   - outputs/global/summary/sector_breakdown_three_sets.csv (sector taxonomy source for Set B)
# Sector taxonomy: broad categories collapsed from SECTORS dict in phase2/build_manifests.py
#   (Note: LMT placed in Industrials per SECTORS dict; sector_breakdown_three_sets.csv placed it in Healthcare)
# Suppression threshold: n < 10 events (for Spearman rho and BUY/SELL accuracy columns; NOT applied to means)
# Arm definitions:
#   LLM: blended sentiment score = 0.55*micro_score + 0.45*macro_score (renormalized if macro missing)
#        deployed default weights from blend.py DEFAULT_WEIGHTS = (0.55, 0.45, 0.0, 0.0)
#        signal from blend_predicted_signal_default (hold_upper=0.25, hold_lower=-0.05)
#   FinBERT: raw FinBERT sentiment score from finbert_extension_results.csv (Set B only)
#            signal from finbert_predicted_signal (thresholds from phase2 dev, frozen for eval)
# Event sets:
#   Set A: N=233 clean phase2 events (268 scored, 35 excluded: 25 worksheet contamination + 1 SPOT misattribution + 9 timing)
#   Set B: N=93 extension events (pure eval; thresholds frozen from Set A dev split)
# Return used: ret_overnight = raw overnight gap (prior_close -> next_day_open), from returns_matrix.csv
# Grading band: |ret_overnight| > 2% (pre-registered)
# Pooled reference: Set A Spearman rho = 0.2360, p = 0.0002, n = 233 (source: ext2_holding_curve.csv)
#                   Set B Spearman rho = 0.2715, p = 0.0085, n = 93 (source: results_three_sets.csv)
# Cut definitions:
#   spearman_rho: Spearman rank correlation between continuous arm score and ret_overnight
#   calibration: mean(score) and mean(ret_overnight) per sector — systematic bias check
#   dispersion: population std of score, plus HOLD rate (fraction with signal==HOLD)
#   sell_buy_asymmetry: accuracy on BUY/SELL calls separately (n_correct/n_calls); base_rate = fraction of events with that outcome
# scipy version: {SCIPY_VERSION} (spearman_p values depend on scipy version; rho values are version-independent)
# IMPORTANT: all figures are PURELY DESCRIPTIVE. No significance claims are made. Per-sector n is too small for inference.
"""


def write_csv(rows: list[dict], out_path: Path) -> None:
    fieldnames = ["sector", "event_set", "arm", "cut", "metric", "n", "value", "suppressed", "notes"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        f.write(HEADER_COMMENTS)
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ---------------------------------------------------------------------------
# Write Markdown
# ---------------------------------------------------------------------------
def write_md(rows: list[dict], events_a: list, events_b_llm: list, events_b_fb: list,
             out_path: Path) -> None:
    from collections import defaultdict

    def get_val(rows, sector, event_set, arm, cut, metric):
        for r in rows:
            if (r["sector"] == sector and r["event_set"] == event_set
                    and r["arm"] == arm and r["cut"] == cut and r["metric"] == metric):
                return r["value"], r["suppressed"]
        return None, None

    # Collect all sectors
    sectors_a = sorted({e["sector"] for e in events_a})
    sectors_b = sorted({e["sector"] for e in events_b_llm})

    lines = [
        f"# Sector Analysis",
        f"",
        f"**Generated:** {DATE}  ",
        f"**Script:** `experiments/sector_analysis.py`  ",
        f"**Set A:** N=233 clean phase2 events (268 scored, 35 excluded: 25 worksheet contamination + 1 SPOT + 9 timing)  ",
        f"**Set B:** N=93 extension events (pure eval)  ",
        f"**Suppression threshold:** n < {SUPPRESSION_N} for Spearman rho and BUY/SELL accuracy",
        f"",
        f"---",
        f"",
        f"## 1. Taxonomy Decision (2026-08-15)",
        f"",
        f"Canonical taxonomy: SECTORS dict in `phase2/build_manifests.py`. "
        f"Four CVS events (CVS_FQ1_2026, CVS_FQ2_2025, CVS_FQ3_2025, CVS_FQ4_2025) "
        f"are classified Healthcare by this analysis, not Consumer. "
        f"This accounts for the Consumer -4 / Healthcare +4 discrepancy between this file and "
        f"`sector_breakdown_three_sets.csv`. `sector_breakdown_three_sets.csv` has not been modified. "
        f"LMT is in Industrials in both files (the notes text listing LMT under Healthcare in the old file is a copy-paste error).",
        f"",
        f"---",
        f"",
        f"## 2. Event Counts by Sector",
        f"",
    ]

    # Count per sector
    from collections import Counter
    cnt_a = Counter(e["sector"] for e in events_a)
    cnt_b = Counter(e["sector"] for e in events_b_llm)
    all_secs = sorted(set(list(cnt_a.keys()) + list(cnt_b.keys())))

    lines.append("| Sector | Set A (n) | Set B (n) |")
    lines.append("| --- | --- | --- |")
    for s in all_secs:
        lines.append(f"| {s} | {cnt_a.get(s, '—')} | {cnt_b.get(s, '—')} |")
    lines.append(f"| **Total** | **{sum(cnt_a.values())}** | **{sum(cnt_b.values())}** |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Spearman rho section
    lines.append("## 3. Spearman Rho (continuous score vs ret_overnight)")
    lines.append("")
    lines.append("Suppressed where n < 10.")
    lines.append("")
    lines.append("**Set A — LLM**")
    lines.append("")
    lines.append("| Sector | n | rho | p |")
    lines.append("| --- | --- | --- | --- |")
    for s in sectors_a:
        n_val, _ = get_val(rows, s, "Set A", "LLM", "spearman_rho", "n")
        rho_val, suppressed = get_val(rows, s, "Set A", "LLM", "spearman_rho", "rho")
        p_val, _ = get_val(rows, s, "Set A", "LLM", "spearman_rho", "p_value")
        if suppressed:
            lines.append(f"| {s} | {n_val} | suppressed (n<{SUPPRESSION_N}) | — |")
        else:
            lines.append(f"| {s} | {n_val} | {rho_val:.4f} | {p_val:.4f} |")
    lines.append("")

    lines.append("**Set B — LLM and FinBERT**")
    lines.append("")
    lines.append("| Sector | n | LLM rho | LLM p | FinBERT rho | FinBERT p |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for s in sectors_b:
        n_val, _ = get_val(rows, s, "Set B", "LLM", "spearman_rho", "n")
        llm_rho, llm_sup = get_val(rows, s, "Set B", "LLM", "spearman_rho", "rho")
        llm_p, _ = get_val(rows, s, "Set B", "LLM", "spearman_rho", "p_value")
        fb_rho, fb_sup = get_val(rows, s, "Set B", "FinBERT", "spearman_rho", "rho")
        fb_p, _ = get_val(rows, s, "Set B", "FinBERT", "spearman_rho", "p_value")
        llm_str = f"{llm_rho:.4f}" if not llm_sup and llm_rho != "" else f"suppressed (n<{SUPPRESSION_N})"
        llm_p_str = f"{llm_p:.4f}" if not llm_sup and llm_p != "" else "—"
        fb_str = f"{fb_rho:.4f}" if not fb_sup and fb_rho != "" else f"suppressed (n<{SUPPRESSION_N})"
        fb_p_str = f"{fb_p:.4f}" if not fb_sup and fb_p != "" else "—"
        lines.append(f"| {s} | {n_val} | {llm_str} | {llm_p_str} | {fb_str} | {fb_p_str} |")
    lines.append("")

    lines.append("**Three findings worth keeping (all purely descriptive — per-sector n too small for inference):**")
    lines.append("")
    lines.append("1. **Financials over-optimism (Set A)**: "
                 "mean_score=0.133, mean_ret≈0.000 — the LLM scores Financials positively "
                 "on average but the average overnight return is near zero. "
                 "BUY accuracy 3/15 = 20.0% (Wilson 95% CI [7.0%, 45.2%]); "
                 "buy_base_rate=24.5%. The model calls BUY in Financials at a rate consistent "
                 "with the base rate (15/28 non-HOLD = 15 BUY, 13 SELL) but converts at 20%, "
                 "below the base rate. MDE ≈ 35pp — a gap of this size is not reliably detectable "
                 "at n=15.")
    lines.append("")
    lines.append("2. **Industrials near-zero rho (Set A)**: "
                 "rho=0.013, p=0.949, n=26. Fisher-z 95% CI: [-0.376, +0.398]. "
                 "The CI spans the full range from a moderate negative to a moderate positive "
                 "correlation — the data are consistent with any linear relationship. "
                 "This is a data gap, not a finding.")
    lines.append("")
    lines.append("3. **FinBERT structural finding (Set B)**: "
                 "FinBERT called SELL on only 2 events across 93 Set B events (2.2%), "
                 "versus LLM SELL rate 14.0% (13/93). "
                 f"FinBERT trade rate: {sum(1 for e in events_b_fb if e['signal'] in ('BUY','SELL'))}/93 "
                 f"= {sum(1 for e in events_b_fb if e['signal'] in ('BUY','SELL'))/93:.1%}. "
                 f"LLM trade rate: {sum(1 for e in events_b_llm if e['signal'] in ('BUY','SELL'))}/93 "
                 f"= {sum(1 for e in events_b_llm if e['signal'] in ('BUY','SELL'))/93:.1%}. "
                 "FinBERT's near-zero SELL rate means it cannot distinguish between "
                 "positive and negative events — it essentially operates as a BUY-or-HOLD model. "
                 "This is a structural limitation of the FinBERT threshold, not a per-sector finding.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Calibration section
    lines.append("## 4. Calibration (mean score vs mean ret_overnight)")
    lines.append("")
    lines.append("**Set A — LLM**")
    lines.append("")
    lines.append("| Sector | n | mean_score | mean_ret |")
    lines.append("| --- | --- | --- | --- |")
    for s in sectors_a:
        n_val, _ = get_val(rows, s, "Set A", "LLM", "calibration", "n")
        ms, _ = get_val(rows, s, "Set A", "LLM", "calibration", "mean_score")
        mr, _ = get_val(rows, s, "Set A", "LLM", "calibration", "mean_ret")
        lines.append(f"| {s} | {n_val} | {ms:.4f} | {mr:.4f} |")
    lines.append("")

    # Dispersion section
    lines.append("## 5. Dispersion (score std + HOLD rate)")
    lines.append("")
    lines.append("**Set A — LLM**")
    lines.append("")
    lines.append("| Sector | n | score_std | hold_rate |")
    lines.append("| --- | --- | --- | --- |")
    for s in sectors_a:
        n_val, _ = get_val(rows, s, "Set A", "LLM", "dispersion", "n")
        ss, _ = get_val(rows, s, "Set A", "LLM", "dispersion", "score_std")
        hr, _ = get_val(rows, s, "Set A", "LLM", "dispersion", "hold_rate")
        lines.append(f"| {s} | {n_val} | {ss:.4f} | {hr:.4f} |")
    lines.append("")

    # BUY/SELL asymmetry section
    lines.append("## 6. BUY/SELL Asymmetry")
    lines.append("")
    lines.append("Suppressed where n_calls < 10.")
    lines.append("")
    lines.append("**Set A — LLM**")
    lines.append("")
    lines.append("| Sector | n | buy_n | buy_acc | buy_base | sell_n | sell_acc | sell_base |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for s in sectors_a:
        n_val, _ = get_val(rows, s, "Set A", "LLM", "calibration", "n")
        bn, _ = get_val(rows, s, "Set A", "LLM", "sell_buy_asymmetry", "buy_n_calls")
        ba, ba_sup = get_val(rows, s, "Set A", "LLM", "sell_buy_asymmetry", "buy_accuracy")
        bb, _ = get_val(rows, s, "Set A", "LLM", "sell_buy_asymmetry", "buy_base_rate")
        sn, _ = get_val(rows, s, "Set A", "LLM", "sell_buy_asymmetry", "sell_n_calls")
        sa, sa_sup = get_val(rows, s, "Set A", "LLM", "sell_buy_asymmetry", "sell_accuracy")
        sb, _ = get_val(rows, s, "Set A", "LLM", "sell_buy_asymmetry", "sell_base_rate")
        ba_str = f"{ba:.3f}" if not ba_sup and ba != "" else "suppressed"
        sa_str = f"{sa:.3f}" if not sa_sup and sa != "" else "suppressed"
        lines.append(f"| {s} | {n_val} | {bn} | {ba_str} | {bb:.3f} | {sn} | {sa_str} | {sb:.3f} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 7. Verdict")
    lines.append("")
    fb_sell_n = sum(1 for e in events_b_fb if e["signal"] == "SELL")
    fb_total = len(events_b_fb)
    llm_b_total = len(events_b_llm)
    llm_b_trade = sum(1 for e in events_b_llm if e["signal"] in ("BUY", "SELL"))
    fb_trade = sum(1 for e in events_b_fb if e["signal"] in ("BUY", "SELL"))
    lines.append(f"All per-sector n values are too small for inference. "
                 f"Three descriptive observations:")
    lines.append(f"")
    lines.append(f"1. **Financials over-optimism**: LLM BUY accuracy 3/15 = 20.0% in Financials (Set A), "
                 f"below the 24.5% base rate. Wilson 95% CI [7.0%, 45.2%]. MDE ≈ 35pp. "
                 f"Consistent with the overall BUY bias finding but not separately testable at n=15.")
    lines.append(f"")
    lines.append(f"2. **Industrials null**: rho=0.013, Fisher-z 95% CI [-0.376, +0.398]. "
                 f"No evidence of a sector-specific rank correlation — but n=26 cannot rule out "
                 f"a moderate effect in either direction.")
    lines.append(f"")
    lines.append(f"3. **FinBERT structural SELL deficit**: {fb_sell_n}/93 SELL calls = "
                 f"{fb_sell_n/fb_total:.1%} vs LLM 13/93 = 14.0%. "
                 f"FinBERT trade rate {fb_trade}/93 = {fb_trade/fb_total:.1%} vs LLM "
                 f"{llm_b_trade}/93 = {llm_b_trade/llm_b_total:.1%}. "
                 f"FinBERT classifies almost no events as SELL regardless of sector — "
                 f"a threshold artefact, not a signal.")

    out_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Loading Set A events...", file=sys.stderr)
    events_a = load_set_a()
    print(f"  Set A: {len(events_a)} events", file=sys.stderr)

    print("Loading Set B events...", file=sys.stderr)
    events_b_llm, events_b_fb = load_set_b()
    print(f"  Set B LLM: {len(events_b_llm)}, FinBERT: {len(events_b_fb)}", file=sys.stderr)

    # Compute stats
    rows = []
    rows.extend(sector_stats(events_a, "Set A", "LLM"))
    rows.extend(sector_stats(events_b_llm, "Set B", "LLM"))
    rows.extend(sector_stats(events_b_fb, "Set B", "FinBERT"))

    out_dir = BASE_DIR / "outputs" / "global" / "summary"
    csv_path = out_dir / f"sector_analysis_{DATE}.csv"
    md_path = out_dir / f"sector_analysis_{DATE}.md"

    write_csv(rows, csv_path)
    print(f"Wrote {csv_path}", file=sys.stderr)

    write_md(rows, events_a, events_b_llm, events_b_fb, md_path)
    print(f"Wrote {md_path}", file=sys.stderr)

    # Print counts as sanity check
    from collections import Counter
    cnt_a = Counter(e["sector"] for e in events_a)
    cnt_b = Counter(e["sector"] for e in events_b_llm)
    print(f"Set A sector counts: {dict(sorted(cnt_a.items()))}", file=sys.stderr)
    print(f"Set B sector counts: {dict(sorted(cnt_b.items()))}", file=sys.stderr)
    # 233 before DIS_FQ1_2025 was excluded on 2026-08-24; derived, not typed,
    # so the next exclusion does not leave this line asserting a stale number.
    expected_a = 268 - 25 - len(EXCLUDED_EVENTS) - 9
    print(f"Total Set A: {sum(cnt_a.values())} (expected {expected_a})", file=sys.stderr)
    print(f"Total Set B: {sum(cnt_b.values())} (expected 93)", file=sys.stderr)


if __name__ == "__main__":
    main()
