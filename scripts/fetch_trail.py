"""Fetch the TRAIL dataset into the gitignored data/trail/.

TRAIL is gated. Its gate text reads:

    "To avoid contamination and data leakage, you agree to not reshare this
    dataset outside of a gated or private repository on the HF hub."

So this script downloads; it never vendors, and nothing it writes is committed.
`data/trail/` is gitignored and `scripts/trail_comparison.py` puts only
aggregates, span counts and category names into metrics.json.

Gating is `auto`: any logged-in Hugging Face account is approved instantly.

    hf auth login          # once, interactively
    python scripts/fetch_trail.py

Only the span trees and the expert annotations are fetched. The parquet mirrors
under data/ hold the same content in a second encoding and are skipped -- they
are most of the 55 MB download and none of the value.

    python scripts/fetch_trail.py --revision <sha>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATASET_ID = "PatronusAI/TRAIL"

#: Pinned so the trace set is reproducible: an unpinned fetch would silently
#: change what every number downstream was measured on. Same discipline as
#: models/encoder_revision.txt.
DATASET_REVISION = "b424ce63d5973d5dcd7169b1bc3c07ccdee276d1"

ALLOW = [
    "GAIA/*.json",
    "SWE Bench/*.json",
    "processed_annotations_gaia/*.json",
    "processed_annotations_swe_bench/*.json",
]

DEST = ROOT / "data" / "trail"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default=DATASET_REVISION)
    parser.add_argument("--dest", default=str(DEST))
    args = parser.parse_args()

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub is not installed (it ships with sentence-transformers)")
        return 1

    dest = Path(args.dest)
    print(f"dataset  {DATASET_ID}")
    print(f"revision {args.revision}")
    print(f"dest     {dest}")
    print()

    try:
        path = snapshot_download(
            repo_id=DATASET_ID,
            repo_type="dataset",
            revision=args.revision,
            local_dir=str(dest),
            allow_patterns=ALLOW,
        )
    except Exception as exc:  # noqa: BLE001 - the message matters more than the type
        print(f"FAILED: {type(exc).__name__}: {exc}")
        print()
        print("TRAIL is gated. If this is a 401/403, run `hf auth login` and")
        print("accept the terms once at:")
        print(f"    https://huggingface.co/datasets/{DATASET_ID}")
        return 1

    from eval.trail import SPLITS, load_trail, observed_categories

    counts = {}
    for directory, split in SPLITS.items():
        counts[split] = len(list((Path(path) / directory).glob("*.json")))
    total = sum(counts.values())
    print(f"downloaded {total} traces: " + ", ".join(f"{k}={v}" for k, v in counts.items()))

    traces = load_trail(path)
    print(f"loaded     {len(traces)} traces with matching annotations")
    print()
    print("annotated categories present (trace counts):")
    for category, n in observed_categories(traces).items():
        print(f"    {category:<34} {n}")

    manifest = Path(path) / "FETCH.json"
    manifest.write_text(
        json.dumps(
            {
                "dataset_id": DATASET_ID,
                "revision": args.revision,
                "traces": counts,
                "note": "gated dataset; never commit anything under data/trail/",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote -> {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
