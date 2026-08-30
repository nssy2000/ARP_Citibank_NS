"""Shared atomic-write helper for phase2/gap_combos.json.

gap_combos.json is a shared checkpoint file mutated by multiple sourcing
scripts (phase2/sourcing/edgar_lookup.py's Tier-1 scripted pass,
phase2/sourcing/ingest_receipt.py's Tier-2 subagent-receipt merges,
potentially dozens of times across the plan). A process kill mid-write must
not truncate/corrupt everything previously on disk, so writes go through a
temp file in the same directory + fsync + os.replace(), never a direct
write_text().
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GAP_COMBOS_PATH = BASE_DIR / "phase2" / "gap_combos.json"


def save_gap_combos(combos: dict) -> None:
    """Writes gap_combos.json atomically: serialize to a temp file in the
    same directory, flush+close, then os.replace() over the real path. A
    direct write_text() can leave the file truncated/corrupted if the
    process is killed mid-write, which would lose not just this run's
    progress but everything previously on disk."""
    data = json.dumps(combos, indent=2, sort_keys=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=GAP_COMBOS_PATH.parent,
        prefix=GAP_COMBOS_PATH.name + ".",
        suffix=".tmp",
        delete=False,
    )
    try:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, GAP_COMBOS_PATH)
