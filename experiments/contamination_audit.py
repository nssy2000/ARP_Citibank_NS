"""
experiments/contamination_audit.py
Item 5 of the model-arm spec (Nigel, 2026-08-05): is the model inferring
from the document, or remembering the outcome from training data. Two
probes, both against the deployed micro-layer model (deepseek-chat):

1. Split all N=268 events pre/post the model's SELF-REPORTED training
   cutoff (asked directly, not assumed - the spec's own first step), compare
   accuracy and rank correlation across the split, bootstrap the accuracy
   difference with bootstrap_unpaired_difference (different events per
   group, so the paired variant doesn't apply - same reasoning already used
   for the BUY/SELL recall-gap test in asymmetry_conviction_analysis.py).
   State the confound plainly: pre-cutoff quarters are also earlier
   quarters with a different volatility regime, so this is suggestive, not
   clean.

2. Recall probe: ~30 events, no document attached, asking the model what it
   recalls happening to the stock after that quarter's earnings. Verbatim
   logged. Classified correct-direction / wrong-direction / refused /
   ambiguous (flagged for manual read rather than force-classified).

Uses the raw OpenAI/DeepSeek client directly (report_pipeline.call_llm() is
schema-coupled to the {sentiment,signal,summary,evidence} pipeline output and
would reject a free-text recall answer).

Real API spend: ~31 calls total (1 cutoff-date call + ~30 recall probes),
cheap but real, run only with explicit go-ahead.

Run: python -m experiments.contamination_audit
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from scipy.stats import spearmanr

from backtest import OUTPUTS_DIR
from bootstrap_stats import bootstrap_unpaired_difference

_PHASE2_DIR = Path(__file__).resolve().parent.parent / "phase2"
if str(_PHASE2_DIR) not in sys.path:
    sys.path.insert(0, str(_PHASE2_DIR))
from build_manifests import SECTORS

BASE_DIR = Path(__file__).resolve().parent.parent
PHASE2_CALIBRATION_CSV = OUTPUTS_DIR / "global" / "summary" / "global_outcome_calibration_phase2.csv"
SPLIT_CSV = OUTPUTS_DIR / "global" / "summary" / "contamination_split_table.csv"
SUMMARY_JSON = OUTPUTS_DIR / "global" / "summary" / "contamination_summary.json"
PROBE_LOG_CSV = OUTPUTS_DIR / "global" / "summary" / "recall_probe_log.csv"

MODEL = "deepseek-chat"
RNG_SEED = 20260709
PROBE_SAMPLE_N = 30

REFUSAL_PATTERNS = [
    r"\bi don'?t have\b", r"\bi do not have\b", r"\bcannot recall\b", r"\bcan'?t recall\b",
    r"\bno specific information\b", r"\bno knowledge\b", r"\bnot aware\b",
    r"\bas an ai\b", r"\bi'?m not able to\b", r"\bi am not able to\b",
    r"\bi don'?t recall\b", r"\bi do not recall\b", r"\bunable to (recall|provide|confirm)\b",
    r"\bi have no (specific )?(information|data|knowledge|recollection)\b",
]
UP_WORDS = ["rose", "rallied", "jumped", "surged", "gained", "increased", "climbed",
            "up", "higher", "soared", "beat", "popped", "spiked"]
DOWN_WORDS = ["fell", "dropped", "declined", "slid", "plunged", "tumbled", "down",
              "lower", "sank", "slumped", "missed", "cratered", "slipped"]


def _num(x):
    if x is None or x == "":
        return None
    return float(x)


def get_client() -> OpenAI:
    load_dotenv(dotenv_path=BASE_DIR / ".env")
    api_key = __import__("os").environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set (checked .env and environment)")
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=120.0)


def ask(client: OpenAI, prompt: str, max_tokens: int = 300) -> str:
    resp = client.chat.completions.create(
        model=MODEL, max_tokens=max_tokens, temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


# ---------- Step 0: confirm the model's stated training cutoff ----------

_MONTH_NAMES = ("january|february|march|april|may|june|july|august|september|"
                "october|november|december")


def parse_cutoff_date(verbatim: str) -> str | None:
    """Best-effort extraction of a YYYY-MM date from the model's free-text
    answer. Returns YYYY-MM-01 (first of month) or None if unparseable."""
    m = re.search(r"\b(20\d{2})-(\d{2})\b", verbatim)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"
    m = re.search(rf"\b({_MONTH_NAMES})\s+(20\d{{2}})\b", verbatim, re.IGNORECASE)
    if m:
        month_idx = _MONTH_NAMES.split("|").index(m.group(1).lower()) + 1
        return f"{m.group(2)}-{month_idx:02d}-01"
    m = re.search(r"\b(20\d{2})\b", verbatim)
    if m:
        return f"{m.group(1)}-01-01"
    return None


def confirm_training_cutoff(client: OpenAI) -> tuple[str, str | None]:
    prompt = ("What is your training data's knowledge cutoff date? Answer with the specific "
              "month and year (e.g. 'July 2024'), and nothing else - no caveats, no hedging.")
    verbatim = ask(client, prompt, max_tokens=60)
    parsed = parse_cutoff_date(verbatim)
    return verbatim, parsed


# ---------- Step 1: pre/post split ----------

def load_events(path: Path = PHASE2_CALIBRATION_CSV) -> list[dict]:
    events = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if not r["micro_score"]:
                continue
            events.append({
                "document_id": r["document_id"], "ticker": r["ticker"],
                "report_date": r["report_date"], "outcome_label": r["outcome_label"],
                "blend_predicted_signal_default": r["blend_predicted_signal_default"],
                "blend_correct_default": r["blend_correct_default"] == "True",
                "micro_score": _num(r["micro_score"]), "forward_return": _num(r["forward_return"]),
            })
    return events


def split_by_cutoff(events: list[dict], cutoff_date: str) -> tuple[list[dict], list[dict]]:
    pre = [e for e in events if e["report_date"] < cutoff_date]
    post = [e for e in events if e["report_date"] >= cutoff_date]
    return pre, post


def group_stats(group: list[dict]) -> dict:
    n = len(group)
    if n == 0:
        return {"n": 0, "accuracy": None, "spearman_rho": None, "spearman_p": None}
    correct = [int(e["blend_correct_default"]) for e in group]
    accuracy = sum(correct) / n
    scores = [e["micro_score"] for e in group]
    returns = [e["forward_return"] for e in group]
    rho, p = spearmanr(scores, returns) if n >= 3 else (float("nan"), float("nan"))
    return {"n": n, "accuracy": round(accuracy, 4),
            "spearman_rho": round(float(rho), 4) if rho == rho else None,
            "spearman_p": round(float(p), 4) if p == p else None,
            "correct_flags": correct}


def sector_split(pre: list[dict], post: list[dict]) -> list[dict]:
    sectors = sorted(set(SECTORS.get(e["ticker"], "Unknown") for e in pre + post))
    out = []
    for sector in sectors:
        pre_s = [e for e in pre if SECTORS.get(e["ticker"], "Unknown") == sector]
        post_s = [e for e in post if SECTORS.get(e["ticker"], "Unknown") == sector]
        if not pre_s or not post_s:
            continue
        out.append({
            "sector": sector, "n_pre": len(pre_s), "n_post": len(post_s),
            "accuracy_pre": round(sum(int(e["blend_correct_default"]) for e in pre_s) / len(pre_s), 4),
            "accuracy_post": round(sum(int(e["blend_correct_default"]) for e in post_s) / len(post_s), 4),
        })
    return out


# ---------- Step 2: recall probe ----------

def stratified_sample(events: list[dict], n: int, seed: int = RNG_SEED) -> list[dict]:
    strata: dict[tuple[str, str], list[dict]] = {}
    for e in events:
        sector = SECTORS.get(e["ticker"], "Unknown")
        key = (sector, e["outcome_label"])
        strata.setdefault(key, []).append(e)

    rng = np.random.default_rng(seed)
    for bucket in strata.values():
        rng.shuffle(bucket)

    keys = sorted(strata.keys())
    sample, i = [], 0
    while len(sample) < n and any(strata.values()):
        key = keys[i % len(keys)]
        if strata[key]:
            sample.append(strata[key].pop())
        i += 1
        if i > n * 20:
            break
    return sample


def fiscal_period_label(document_id: str) -> str:
    parts = document_id.split("_")
    if len(parts) >= 3:
        return f"{parts[-2]} {parts[-1]}"
    return document_id


def classify_response(text: str, actual_return: float) -> str:
    lowered = text.lower()
    for pat in REFUSAL_PATTERNS:
        if re.search(pat, lowered):
            return "refused"

    up_hits = sum(1 for w in UP_WORDS if re.search(rf"\b{re.escape(w)}\b", lowered))
    down_hits = sum(1 for w in DOWN_WORDS if re.search(rf"\b{re.escape(w)}\b", lowered))
    if up_hits == 0 and down_hits == 0:
        return "ambiguous_manual_review"
    predicted_up = up_hits > down_hits
    predicted_down = down_hits > up_hits
    if up_hits == down_hits:
        return "ambiguous_manual_review"

    actual_up = actual_return > 0
    if (predicted_up and actual_up) or (predicted_down and not actual_up):
        return "correct_direction"
    return "wrong_direction"


def run_recall_probe(client: OpenAI, events: list[dict]) -> list[dict]:
    rows = []
    for e in events:
        fq = fiscal_period_label(e["document_id"])
        prompt = (
            f"Based on your training knowledge only - I am NOT attaching any document - what do "
            f"you recall about {e['ticker']}'s stock price reaction in the days after its {fq} "
            f"earnings report (reported around {e['report_date']})? If you have no specific "
            f"knowledge of this event, say so explicitly rather than guessing. Keep your answer "
            f"to 2-3 sentences."
        )
        verbatim = ask(client, prompt, max_tokens=200)
        classification = classify_response(verbatim, e["forward_return"])
        rows.append({
            "document_id": e["document_id"], "ticker": e["ticker"], "report_date": e["report_date"],
            "actual_forward_return": e["forward_return"], "outcome_label": e["outcome_label"],
            "prompt": prompt, "verbatim_response": verbatim, "classification": classification,
        })
        print(f"  {e['document_id']:20} -> {classification}")
    return rows


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {path}")


def main() -> int:
    client = get_client()

    print("Step 0: confirming training data cutoff directly from the model...")
    cutoff_verbatim, cutoff_parsed = confirm_training_cutoff(client)
    print(f"  Verbatim: {cutoff_verbatim!r}")
    if cutoff_parsed is None:
        raise RuntimeError(f"Could not parse a cutoff date from: {cutoff_verbatim!r} - "
                            "inspect manually and hardcode if needed.")
    print(f"  Parsed as: {cutoff_parsed}")

    events = load_events()
    print(f"\nLoaded {len(events)} events")
    pre, post = split_by_cutoff(events, cutoff_parsed)
    print(f"Pre-cutoff: {len(pre)} events, post-cutoff: {len(post)} events")

    pre_stats = group_stats(pre)
    post_stats = group_stats(post)
    print(f"\nPre-cutoff:  n={pre_stats['n']}, accuracy={pre_stats['accuracy']}, "
          f"spearman_rho={pre_stats['spearman_rho']} (p={pre_stats['spearman_p']})")
    print(f"Post-cutoff: n={post_stats['n']}, accuracy={post_stats['accuracy']}, "
          f"spearman_rho={post_stats['spearman_rho']} (p={post_stats['spearman_p']})")

    diff = None
    if pre_stats["n"] > 0 and post_stats["n"] > 0:
        diff = bootstrap_unpaired_difference(pre_stats["correct_flags"], post_stats["correct_flags"])
        print(f"\nAccuracy diff (pre - post): {diff['point_diff']:+.4f} "
              f"[{diff['ci_low']:+.4f}, {diff['ci_high']:+.4f}], p={diff['p_value']:.4f}")

    split_rows = [
        {"document_id": e["document_id"], "ticker": e["ticker"], "report_date": e["report_date"],
         "group": "pre" if e["report_date"] < cutoff_parsed else "post",
         "correct": int(e["blend_correct_default"])}
        for e in events
    ]
    write_csv(SPLIT_CSV, split_rows)

    sectors = sector_split(pre, post)

    print("\nStep 2: recall probe on a stratified sample of "
          f"{PROBE_SAMPLE_N} events (no document attached)...")
    sample = stratified_sample(events, PROBE_SAMPLE_N)
    print(f"Sampled {len(sample)} events (stratified by sector x outcome_label)")
    probe_rows = run_recall_probe(client, sample)
    write_csv(PROBE_LOG_CSV, probe_rows)

    probe_counts = {}
    for r in probe_rows:
        probe_counts[r["classification"]] = probe_counts.get(r["classification"], 0) + 1
    print(f"\nRecall probe classification counts: {probe_counts}")

    summary = {
        "training_cutoff_verbatim": cutoff_verbatim,
        "training_cutoff_parsed": cutoff_parsed,
        "pre_cutoff": {k: v for k, v in pre_stats.items() if k != "correct_flags"},
        "post_cutoff": {k: v for k, v in post_stats.items() if k != "correct_flags"},
        "accuracy_diff_pre_minus_post": diff,
        "sector_split": sectors,
        "recall_probe_n": len(sample),
        "recall_probe_counts": probe_counts,
        "confound_caveat": (
            "Pre-cutoff quarters are also earlier quarters with a different volatility regime, "
            "so any pre/post accuracy gap is suggestive rather than a clean contamination test."
        ),
    }
    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote summary -> {SUMMARY_JSON}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
