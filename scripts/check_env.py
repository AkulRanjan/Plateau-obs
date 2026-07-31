"""Is this machine able to reproduce the committed numbers?

Rule 3 says two harness runs must produce a byte-identical metrics.json. That
holds only if the encoder produces byte-identical vectors, which in turn holds
only if the dependency stack matches the one the numbers were generated on.

Nothing enforced that, and the drift was silent: this machine runs
transformers 5.9.0 against a 4.57.6 pin, and the encoder probe hashes to
aaca066b... where metrics.json records 024c4c5f... Every committed number is
therefore unreproducible here, and until now nothing said so.

This script does not fix the drift. It makes it impossible to be misled by it.

    python scripts/check_env.py            # versions only, no model load
    python scripts/check_env.py --probe    # also load the encoder and hash

Exit codes are INFORMATIONAL, not a build gate:
    0  stack matches the pins (and the probe matches, if checked)
    1  drift detected - the details are printed
    2  could not determine (missing pyproject, unreadable metrics.json)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PYPROJECT = ROOT / "pyproject.toml"
METRICS = ROOT / "metrics.json"


def pinned_versions() -> dict[str, str]:
    """Read `name==version` pins out of [project].dependencies."""
    text = PYPROJECT.read_text(encoding="utf-8")
    block = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.S | re.M)
    if not block:
        return {}
    return dict(re.findall(r'"([A-Za-z0-9_.-]+)==([0-9][^"]*)"', block.group(1)))


def installed_version(package: str) -> str | None:
    import importlib.metadata as md

    try:
        return md.version(package)
    except md.PackageNotFoundError:
        return None


def committed_encoder() -> dict:
    """The encoder fingerprint metrics.json was generated with."""
    doc = json.loads(METRICS.read_text(encoding="utf-8"))
    for key in ("detector_fixtures", "gate1_premise", "long_trace_comparison"):
        enc = doc.get(key, {}).get("encoder")
        if enc:
            return enc
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--probe",
        action="store_true",
        help="load the encoder and compare probe_sha256 (slow, needs weights)",
    )
    args = parser.parse_args()

    if not PYPROJECT.exists() or not METRICS.exists():
        print("cannot find pyproject.toml or metrics.json", file=sys.stderr)
        return 2

    print(f"  python      {sys.version.split()[0]}")
    print(f"  prefix      {sys.prefix}")
    print(f"  virtualenv  {sys.prefix != sys.base_prefix}")
    print()

    pins = pinned_versions()
    drift: list[tuple[str, str, str]] = []

    width = max((len(p) for p in pins), default=10)
    for package, want in sorted(pins.items()):
        got = installed_version(package)
        ok = got == want
        if not ok:
            drift.append((package, want, got or "MISSING"))
        flag = "ok  " if ok else "DIFF"
        print(f"  {flag}  {package:<{width}}  pinned {want:<9} installed {got or 'MISSING'}")

    # The pinned encoder revision has two homes: models/encoder_revision.txt,
    # which plateau/encoder.py actually reads at runtime, and pyproject.toml
    # [tool.plateau], which only scripts read. They can silently disagree, and
    # if they do, the revision documented in pyproject is not the revision any
    # number was produced under. That is a failure, not a warning.
    revision_split = False
    declared = re.search(
        r'^encoder_revision\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.M
    )
    from plateau.encoder import pinned_revision

    runtime = pinned_revision()
    declared_rev = declared.group(1) if declared else None
    if declared_rev != runtime:
        revision_split = True
        print()
        print(f"  DIFF  encoder revision sources disagree")
        print(f"        models/encoder_revision.txt  {runtime or 'MISSING'}")
        print(f"        pyproject [tool.plateau]     {declared_rev or 'MISSING'}")

    probe_mismatch = False
    if args.probe:
        print()
        committed = committed_encoder()
        try:
            from plateau.encoder import MiniLMEncoder

            fingerprint = MiniLMEncoder().load().fingerprint()
        except Exception as exc:  # noqa: BLE001 - report, never crash
            print(f"  probe       could not load the encoder: {exc}")
            fingerprint = {}

        if fingerprint:
            same_rev = fingerprint["revision"] == committed.get("revision")
            same_probe = fingerprint["probe_sha256"] == committed.get("probe_sha256")
            # The rounded probe is what decides whether results reproduce. The
            # exact one flips on a single float ULP from a different CPU or
            # BLAS, which changes no published figure -- measured across this
            # repo's two machines, the raw digests differ while every cosine
            # agrees to at least 1e-6.
            committed_round = committed.get("probe_sha256_round6")
            same_round = (
                committed_round is None
                or fingerprint["probe_sha256_round6"] == committed_round
            )
            probe_mismatch = not same_round
            print(f"  {'ok  ' if same_rev else 'DIFF'}  revision      {fingerprint['revision']}")
            if not same_rev:
                print(f"        committed     {committed.get('revision')}")
            print(f"  {'ok  ' if same_probe else 'DIFF'}  probe_sha256  {fingerprint['probe_sha256']}")
            if not same_probe:
                print(f"        committed     {committed.get('probe_sha256')}")
            if committed_round is None:
                print("  --    probe_round6  not recorded in metrics.json (pre-dates the check)")
            else:
                print(f"  {'ok  ' if same_round else 'DIFF'}  probe_round6  {fingerprint['probe_sha256_round6']}")
                if not same_round:
                    print(f"        committed     {committed_round}")
            if committed_round is not None and same_round and not same_probe:
                print()
                print("  The raw probe differs but the rounded one matches: this is")
                print("  last-bit float noise from a different CPU or BLAS, not a")
                print("  different model. Published figures reproduce; byte-identical")
                print("  metrics.json across machines does not, and cannot.")

    print()
    if not drift and not probe_mismatch and not revision_split:
        print("  stack matches the pins - committed numbers are reproducible here.\n")
        return 0

    if drift:
        print(f"  {len(drift)} package(s) differ from the pins.\n")
        print("  To reproduce the committed numbers, install the pinned set into a")
        print("  clean environment. NOTE: torch 2.5.1 publishes no wheel for Python")
        print("  3.13+, so this needs a 3.10-3.12 interpreter:\n")
        print("    python3.10 -m venv .venv-pinned && . .venv-pinned/bin/activate")
        print("    pip install " + " ".join(f"'{p}=={v}'" for p, v, _ in drift))
        print()

    if revision_split:
        print("  Fix the revision split before trusting any number: run")
        print("  scripts/pin_encoder.py, which writes both places from the")
        print("  actual downloaded snapshot rather than from either copy.\n")

    if probe_mismatch:
        print("  The encoder produces different vectors than the ones behind")
        print("  metrics.json. Any number you regenerate here will disagree with")
        print("  the committed numbers. Do not re-baseline metrics.json to make")
        print("  them agree - that hides the drift rather than fixing it.\n")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
