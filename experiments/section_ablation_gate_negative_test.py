"""Negative test for the section_ablation_rethreshold gate.

A gate that has only ever been run against a good reference is not evidence. This
breaks the reference on purpose, one fault at a time, and proves the gate refuses.

The fourth case is the one this test exists for. The gate originally read the live
summary - the same file the script writes - so promoting the constants moved its own
reference and it failed 37 fields on every run thereafter. Pointing GATE_REFERENCE
back at the live summary must be caught, not silently tolerated.

Usage:
  python -m experiments.section_ablation_gate_negative_test
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import section_ablation_rethreshold as sar  # noqa: E402


def perturb_a_field(src: Path, dst: Path) -> None:
    """Move one committed count by one. Nothing else changes."""
    lines = src.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("full_bundle,four_arm,"):
            f = line.split(",")
            f[3] = str(int(f[3]) + 1)          # trades_overnight
            lines[i] = ",".join(f)
            break
    else:
        raise SystemExit("could not find the row to perturb")
    dst.write_text("\n".join(lines) + "\n")


def restate_the_constants(src: Path, dst: Path) -> None:
    """Claim the reference was built at constants it was not built at."""
    dst.write_text(src.read_text().replace(
        "# hold_upper: 0.25, hold_lower: -0.05", "# hold_upper: 0.15, hold_lower: -0.15", 1))


def main() -> int:
    rows, _ = sar.read_rows(sar.IN_RESULTS)
    real = sar.GATE_REFERENCE
    tmp = Path(tempfile.mkdtemp(prefix="gatetest-"))
    cases = []

    good = tmp / "good.csv"
    shutil.copy(real, good)
    cases.append(("the untouched reference", good, None))

    bad = tmp / "one_field_moved.csv"
    perturb_a_field(good, bad)
    cases.append(("one committed count moved by one", bad, "do not reproduce"))

    cases.append(("the reference missing altogether", tmp / "absent.csv", "is missing"))

    lying = tmp / "constants_restated.csv"
    restate_the_constants(good, lying)
    cases.append(("the reference claiming other constants", lying, "does not state the constants"))

    cases.append(("the gate pointed back at the file the script writes",
                  sar.OUT_SUMMARY, "does not state the constants"))

    failures = []
    for name, ref, expect in cases:
        sar.GATE_REFERENCE = ref
        try:
            sar.gate(rows)
            got = None
        except SystemExit as e:
            got = str(e)
        if expect is None:
            status = "passes" if got is None else "MISSED"
            if got is not None:
                failures.append(f"{name}: the gate refused a good reference - {got[:120]}")
        elif got is None:
            status = "MISSED"
            failures.append(f"{name}: the gate accepted it")
        elif expect not in got:
            status = "MISSED"
            failures.append(f"{name}: refused, but not for the stated reason - {got[:120]}")
        else:
            status = "caught"
        print(f"  [{status:>6}] {name}")
        if got and status == "caught":
            print(f"           -> {got.strip().splitlines()[-1][:140]}")

    sar.GATE_REFERENCE = real
    shutil.rmtree(tmp, ignore_errors=True)
    print()
    if failures:
        print(f"{len(failures)} CASE(S) NOT HANDLED:")
        for f in failures:
            print("   -", f)
        return 1
    print(f"all {len(cases) - 1} gate faults bite, and the good reference still passes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
