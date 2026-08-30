"""Copy resolved report_date values from phase2/report_dates.json into
phase2/gap_combos.json, advancing status to "report_date_resolved". Run
after resolve_report_dates.py + fix_report_dates_from_human_prices.py."""
from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
GAP_COMBOS_PATH = BASE_DIR / "gap_combos.json"
REPORT_DATES_PATH = BASE_DIR / "report_dates.json"


def main() -> None:
    combos = json.loads(GAP_COMBOS_PATH.read_text(encoding="utf-8"))
    report_dates = json.loads(REPORT_DATES_PATH.read_text(encoding="utf-8"))

    updated = 0
    missing = []
    malformed = []
    for key, combo in combos.items():
        entry = report_dates.get(key)
        if entry is None:
            missing.append(key)
            continue
        if "report_date" not in entry or "confidence" not in entry:
            malformed.append(key)
            continue
        combo["report_date"] = entry["report_date"]
        combo["report_date_confidence"] = entry["confidence"]
        if combo["status"] == "not_started":
            combo["status"] = "report_date_resolved"
        updated += 1

    GAP_COMBOS_PATH.write_text(json.dumps(combos, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Synced report_date for {updated} combos")
    if missing:
        print(f"{len(missing)} combos missing from report_dates.json (make sure Task 3 ran first):")
        for m in missing:
            print(" ", m)
    if malformed:
        print(f"{len(malformed)} combos have a report_dates.json entry missing 'report_date'/'confidence' keys:")
        for m in malformed:
            print(" ", m)


if __name__ == "__main__":
    main()
