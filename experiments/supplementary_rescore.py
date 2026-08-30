"""
Supplementary re-score of the 25 worksheet-contaminated events.

This is a ROBUSTNESS CHECK, not a reinstatement. The 25 events stay excluded
from the main results and N stays at 229. The exclusion rests on a demonstrated
mechanism (build_bundle_text supplied the model with a rater's score, signal
and realised return), so it is not contingent on these numbers.

WORKSHEET_EXCLUDED_DOCUMENT_IDS filtering is active, so the worksheet sections
are absent from the bundle text sent to the model. This was verified before
any calls were made (see commit log).
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from report_pipeline import (
    ReportSpec, SourceDocument, build_bundle_text, build_user_message,
    call_llm, utc_run_id, WORKSHEET_EXCLUDED_DOCUMENT_IDS,
)

SUMMARY_DIR = PROJECT_ROOT / "outputs" / "global" / "summary"
CALIBRATION_CSV = SUMMARY_DIR / "global_outcome_calibration_phase2.csv"
RETURNS_CSV = SUMMARY_DIR / "returns_matrix.csv"
WORKSHEET_FLAGS_CSV = SUMMARY_DIR / "worksheet_leak_flags.csv"

OUT_DIR = SUMMARY_DIR
OUT_RESULTS = OUT_DIR / "supplementary_rescore_25.csv"

HOLD_UPPER = 0.25
HOLD_LOWER = -0.05
BAND = 0.02
COST_BPS = 10.0


def main():
    run_id = utc_run_id()
    print(f"Supplementary re-score — run_id: {run_id}")
    print(f"ROBUSTNESS CHECK ONLY. N=229 main results are unchanged.\n")

    # Load the 25 document_ids
    target_ids = sorted(WORKSHEET_EXCLUDED_DOCUMENT_IDS)
    print(f"Events to re-score: {len(target_ids)}")

    # Load calibration for metadata
    cal = {}
    with open(CALIBRATION_CSV) as f:
        for r in csv.DictReader(f):
            cal[r['document_id']] = r

    # Load returns for grading
    returns = {}
    with open(RETURNS_CSV) as f:
        for r in csv.DictReader(filter(lambda l: not l.startswith('#'), f)):
            returns[r['document_id']] = r

    # Load manifests for report specs
    manifests = {}
    for mf in sorted(PROJECT_ROOT.glob("manifests/p2_*_reports.json")):
        with open(mf) as fh:
            data = json.load(fh)
        for report in data['reports']:
            manifests[report['document_id']] = (data, report)

    # Load human decisions for agreement check
    human_decisions = {}
    human_file = PROJECT_ROOT / "data" / "human" / "human_decisions_export_2026-08-12.csv"
    if human_file.exists():
        # Build event_key -> document_id mapping
        key_to_docid = {}
        for mf in sorted(PROJECT_ROOT.glob("manifests/p2_*_reports.json")):
            with open(mf) as fh:
                mdata = json.load(fh)
            for report in mdata['reports']:
                import re
                m = re.match(r'FQ(\d)\s+(\d{4})', report['fiscal_period'])
                if m:
                    key = f"{report['company']}|{m.group(2)}|Q{m.group(1)}"
                    key_to_docid[key] = report['document_id']

        with open(human_file) as f:
            for r in csv.DictReader(f):
                if r['section'] != 'All': continue
                if r['first_rater_for_event'] != 'YES': continue
                doc_id = key_to_docid.get(r['event_key'])
                if doc_id and doc_id in WORKSHEET_EXCLUDED_DOCUMENT_IDS:
                    human_decisions[doc_id] = r['human_decision'].strip().upper()

    results = []
    for i, doc_id in enumerate(target_ids):
        c = cal.get(doc_id)
        if not c:
            print(f"  SKIP {doc_id}: not in calibration CSV")
            continue

        mdata, report = manifests.get(doc_id, (None, None))
        if not report:
            print(f"  SKIP {doc_id}: not in manifests")
            continue

        spec = ReportSpec(
            issuer=report['issuer'],
            company=report.get('company', c['ticker']),
            ticker=c['ticker'],
            sector=report.get('sector', ''),
            report_type=report.get('report_type', 'Bundled Earnings Report'),
            fiscal_period=report.get('fiscal_period', ''),
            report_date=report['report_date'],
            documents=tuple(
                SourceDocument(doc_type=d['doc_type'], source_pdf=Path(d['source_pdf']))
                for d in report['documents']
            ),
            document_id=doc_id,
        )

        print(f"  [{i+1}/{len(target_ids)}] {doc_id} ...", end="", flush=True)

        try:
            report_text, per_doc_meta, warnings = build_bundle_text(spec)
        except Exception as e:
            print(f" EXTRACTION ERROR: {e}")
            continue

        # Verify worksheet is excluded
        excluded_docs = [m for m in per_doc_meta if m.get('excluded')]
        if not excluded_docs:
            print(f" WARNING: no documents excluded — worksheet may still be present!")

        doc_params = {
            "company": spec.company,
            "ticker": spec.ticker,
            "sector": spec.sector,
            "report_type": spec.report_type,
            "report_date": spec.report_date,
            "fiscal_period": spec.fiscal_period,
            "report_text": report_text,
            "hold_upper": HOLD_UPPER,
            "hold_lower": HOLD_LOWER,
        }
        user_message = build_user_message(doc_params)

        try:
            output = call_llm(
                user_message=user_message,
                doc_params=doc_params,
                report=spec,
                run_id=run_id,
                cached_input=False,
            )
        except Exception as e:
            print(f" LLM ERROR: {e}")
            continue

        result = output["result"]
        cost_log = output["cost_log"]
        new_score = float(result["sentiment"]["score"])
        new_signal = result["signal"]["direction"]

        # Old signal from calibration
        old_signal = c['blend_predicted_signal_default']
        old_micro = float(c['micro_score'])

        # Grade on corrected returns
        ret_row = returns.get(doc_id)
        ret_on = float(ret_row['ret_overnight']) if ret_row else None

        correct = None
        net = None
        if ret_on is not None and new_signal != 'HOLD':
            cost = COST_BPS / 10000
            if new_signal == 'BUY':
                net = ret_on - cost
                if ret_on > BAND: correct = True
                elif ret_on < -BAND: correct = False
            elif new_signal == 'SELL':
                net = -ret_on - cost
                if ret_on < -BAND: correct = True
                elif ret_on > BAND: correct = False

        # Human agreement
        human_d = human_decisions.get(doc_id)
        new_agrees_human = (new_signal == human_d) if human_d else None
        old_agrees_human = (old_signal == human_d) if human_d else None

        results.append({
            'document_id': doc_id,
            'old_micro_score': old_micro,
            'old_signal': old_signal,
            'new_score': new_score,
            'new_signal': new_signal,
            'signal_changed': old_signal != new_signal,
            'ret_overnight': ret_on,
            'correct': correct,
            'net': net,
            'human_decision': human_d,
            'new_agrees_human': new_agrees_human,
            'old_agrees_human': old_agrees_human,
            'tokens': cost_log['total_tokens'],
            'cost': cost_log['estimated_cost_usd'],
            'model': cost_log.get('model', ''),
            'run_id': run_id,
        })

        changed = "CHANGED" if old_signal != new_signal else "same"
        print(f" old={old_signal} new={new_signal} ({changed}) "
              f"score={new_score:.2f} cost=${cost_log['estimated_cost_usd']:.4f}")

    # Write results
    fields = list(results[0].keys()) if results else []
    with open(OUT_RESULTS, 'w', newline='') as f:
        f.write("# Supplementary re-score of 25 worksheet-contaminated events\n")
        f.write(f"# ROBUSTNESS CHECK ONLY — N=229 main results unchanged\n")
        f.write(f"# Run ID: {run_id}\n")
        f.write(f"# Run date: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"# Model: deepseek-v4-flash\n")
        f.write(f"# Worksheet sections EXCLUDED via WORKSHEET_EXCLUDED_DOCUMENT_IDS\n")
        f.write(f"# Grading: pre-registered ±2% raw overnight band on corrected anchor\n")
        f.write(f"#\n")
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow(r)

    # Summary
    n = len(results)
    changed = sum(1 for r in results if r['signal_changed'])
    traded_new = [r for r in results if r['new_signal'] != 'HOLD']
    graded_new = [r for r in results if r['correct'] is not None]
    correct_new = sum(1 for r in graded_new if r['correct'])

    print(f"\n{'='*60}")
    print(f"SUMMARY (supplementary robustness check)")
    print(f"{'='*60}")
    print(f"Re-scored: {n}")
    print(f"Signal changed: {changed}/{n} ({100*changed/n:.0f}%)")
    print(f"Traded (new): {len(traded_new)}")
    print(f"Graded (new): {len(graded_new)}")
    if graded_new:
        print(f"Correct (new): {correct_new}/{len(graded_new)} = {correct_new/len(graded_new):.1%}")
    if traded_new:
        nets_new = [r['net'] for r in traded_new if r['net'] is not None]
        if nets_new:
            import numpy as np
            print(f"Mean net/trade (new): {np.mean(nets_new)*100:+.3f}%")

    # Agreement
    with_human = [r for r in results if r['human_decision'] is not None]
    if with_human:
        new_agree = sum(1 for r in with_human if r['new_agrees_human'])
        old_agree = sum(1 for r in with_human if r['old_agrees_human'])
        print(f"\nAgreement with human arm (n={len(with_human)}):")
        print(f"  Old (contaminated): {old_agree}/{len(with_human)} = {old_agree/len(with_human):.1%}")
        print(f"  New (clean):        {new_agree}/{len(with_human)} = {new_agree/len(with_human):.1%}")

    print(f"\nTotal cost: ${sum(r['cost'] for r in results):.2f}")
    print(f"Wrote {OUT_RESULTS}")


if __name__ == "__main__":
    main()
