"""Every number in the README must exist in metrics.json.

Rule 1 says no number appears in any document unless a script in this repo
produced it and wrote it into metrics.json. Nothing enforced that. The coupling
was duplicated literals -- `0.8927` was typed into the README, the detector
docstring, and three test files independently -- so a real measurement change
broke the tests and left the README quietly wrong, which is the worst of both:
the reader trusts a stale number and the suite is green.

This closes the loop from the document end. It extracts every decimal figure
from README.md and asserts each one appears somewhere in metrics.json, at the
same rounding.

It is deliberately a *containment* check, not a schema:

  - It cannot tell you the number is in the right sentence. It can tell you the
    number is no longer one this repo measures, which is the failure that
    actually happened.
  - Integers are ignored. "six-turn preamble", "144 configurations" and "2019"
    are not all measurements and a containment check over small integers would
    match anything.
  - Figures inside a line marked with the ALLOW comment below are skipped, for
    prose that legitimately quotes an external source (upstream defaults, issue
    numbers, third-party thresholds).

    python scripts/check_readme.py
    python scripts/check_readme.py --verbose

Exit codes:
    0  every figure is backed by metrics.json
    1  at least one is not
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
METRICS = ROOT / "metrics.json"

#: Put this on a README line whose figures come from outside this repo.
ALLOW = "<!-- external -->"

#: Decimal figures only -- see the module docstring.
FIGURE = re.compile(r"(?<![\w.])(\d+\.\d+)(?![\w.])")


def figures_in_readme(text: str) -> dict[str, list[int]]:
    """value -> the 1-based line numbers it appears on."""
    found: dict[str, list[int]] = {}
    in_code = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or ALLOW in line:
            continue
        for value in FIGURE.findall(line):
            found.setdefault(value, []).append(number)
    return found


def numbers_in_metrics(node, out: set[str]) -> set[str]:
    """Every float anywhere in metrics.json, at several roundings.

    The README quotes 0.6667 where metrics.json holds 0.6666666666666666, and
    0.89 where it holds 0.89273. Both are honest renderings of the same
    measurement, so a figure counts as backed if it matches the stored value at
    any rounding from 0 to 6 places.
    """
    if isinstance(node, dict):
        for value in node.values():
            numbers_in_metrics(value, out)
    elif isinstance(node, list):
        for value in node:
            numbers_in_metrics(value, out)
    elif isinstance(node, bool):
        pass
    elif isinstance(node, (int, float)):
        for places in range(7):
            out.add(f"{float(node):.{places}f}")
        out.add(repr(float(node)))
        out.add(str(node))
    elif isinstance(node, str):
        # Numbers embedded in a note string were still produced by a script.
        for value in FIGURE.findall(node):
            out.add(value)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not README.exists() or not METRICS.exists():
        print("cannot find README.md or metrics.json", file=sys.stderr)
        return 1

    doc = json.loads(METRICS.read_text(encoding="utf-8"))
    backed = numbers_in_metrics(doc, set())
    found = figures_in_readme(README.read_text(encoding="utf-8"))

    unbacked = {v: lines for v, lines in found.items() if v not in backed}

    print(f"  README figures checked   {len(found)}")
    print(f"  backed by metrics.json   {len(found) - len(unbacked)}")
    print(f"  metrics.json keys        {', '.join(sorted(doc))}")

    if args.verbose:
        for value, lines in sorted(found.items()):
            mark = "ok  " if value not in unbacked else "MISS"
            print(f"    {mark}  {value:<12} line(s) {lines}")

    if not unbacked:
        print("\n  every README figure traces to a measurement.\n")
        return 0

    print(f"\n  {len(unbacked)} figure(s) appear in the README but in no metrics block:\n")
    for value, lines in sorted(unbacked.items()):
        print(f"    {value:<12} README.md line(s) {lines}")
    print()
    print("  Either the number is stale -- re-read it from metrics.json -- or it")
    print("  was never measured, in which case it must not be in the README.")
    print(f"  If it is genuinely an external figure, mark the line with {ALLOW}.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
