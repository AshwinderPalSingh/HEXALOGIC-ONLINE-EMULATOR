"""smell_check.py — Regression check for suspiciously perfect validation results.

Flags any comparison table where ALL rows show 0.000% error as a methodology smell.
This prevents the circular-validation problem from silently recurring.

Usage:
    python3 validation/independent_check/smell_check.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

RESULTS_CSV = Path(__file__).resolve().parent / "results.csv"
RESULTS_JSON = Path(__file__).resolve().parent / "results.json"


def check_csv(path: Path) -> tuple[bool, list[str]]:
    """Returns (has_smell, messages)."""
    if not path.exists():
        return False, [f"No results file at {path}"]

    messages = []
    rows = list(csv.DictReader(open(path)))

    if not rows:
        return False, ["No data rows in CSV"]

    # Check 1: All PENDING — not a smell, just incomplete
    pending_count = sum(1 for r in rows if "[PENDING" in str(r.get("keil_cycles", "")))
    if pending_count == len(rows):
        messages.append(
            f"INFO: All {len(rows)} rows have [PENDING_KEIL_DATA]. "
            "Comparison is incomplete — no independent validation yet."
        )
        return False, messages

    # Check 2: All errors are exactly 0.000%
    error_values = []
    for r in rows:
        err = r.get("error_pct", "")
        if "[PENDING" in err:
            continue
        try:
            error_values.append(float(err.replace("%", "")))
        except ValueError:
            continue

    if error_values and all(e == 0.0 for e in error_values):
        messages.append(
            f"⚠ METHODOLOGY SMELL: All {len(error_values)} compared rows show "
            "exactly 0.000% error. This is suspicious and may indicate "
            "self-referential validation (checking code against itself). "
            "Verify that the 'expected' values come from an independent source "
            "(Keil µVision, physical hardware, or a separate implementation)."
        )
        return True, messages

    # Check 3: Some errors present, check if they're unrealistically small
    if error_values:
        max_err = max(abs(e) for e in error_values)
        avg_err = sum(abs(e) for e in error_values) / len(error_values)
        messages.append(
            f"OK: {len(error_values)} rows compared. "
            f"Max error = {max_err:.4f}%, Avg error = {avg_err:.4f}%."
        )
        if max_err < 0.001 and len(error_values) > 2:
            messages.append(
                "NOTE: All errors are below 0.001%. While possible for an "
                "interpretive ISS, verify the oracle is truly independent."
            )

    return False, messages


def main():
    print("=" * 60)
    print("Validation Smell Check")
    print("=" * 60)
    print()

    has_smell, messages = check_csv(RESULTS_CSV)

    for msg in messages:
        print(f"  {msg}")

    print()
    if has_smell:
        print("RESULT: ⚠ SMELL DETECTED — review validation methodology")
        sys.exit(1)
    else:
        print("RESULT: ✓ No methodology smell detected")
        print("  (This does NOT mean validation is complete —")
        print("   check for [PENDING_KEIL_DATA] placeholders.)")
        sys.exit(0)


if __name__ == "__main__":
    main()
