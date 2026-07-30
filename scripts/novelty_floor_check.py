"""Measure the observation-novelty distribution that the novelty floor must separate.

`novelty_floor` is the one dial Plateau deliberately does NOT calibrate, so its
value is load-bearing. It has to sit:

    above  near-duplicate observations   (a healthy poller: "still running, 4m"
                                          then "still running, 9m")
    below  genuinely-new observations    (a healthy batch job: different invoice
                                          each turn)

and comfortably above exactly 0.0, which is what a true loop produces.

If the poller reading lands *above* the floor, pollers false-trip and the honest
answer is the per-tool `idempotent: true` exemption plus a line in limitations --
not quietly moving the floor until the demo passes.

novelty := 1 - cos(obs_t, obs_ref)

Runs offline against the pinned snapshot. Writes to metrics.json under
`novelty_floor_probe`.

    python scripts/novelty_floor_check.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["HF_HUB_OFFLINE"] = "1"

from plateau.encoder import MiniLMEncoder, cosine  # noqa: E402

#: The placeholder under test. Named as a placeholder, not as a finding.
CANDIDATE_FLOOR = 0.15

# The three readings the floor decision hinges on.
# (class, label, obs_a, obs_b)
PRIMARY = [
    (
        "poller",
        "poller: same status, later timestamp",
        "Job still running, 4m elapsed",
        "Job still running, 9m elapsed",
    ),
    (
        "true_loop",
        "true loop: byte-identical observation",
        "Found 4 results: a.md, b.md, c.md, d.md",
        "Found 4 results: a.md, b.md, c.md, d.md",
    ),
    (
        "batch",
        "batch: different record, same format",
        "ACME Corp, Rs 84,200",
        "Vertex Ltd, Rs 19,750",
    ),
]

# n=1 per class is too thin to set a threshold on. These widen each class so the
# decision rests on a spread, not on one lucky string pair.
SUPPORTING = [
    # --- poller / near-duplicate: the dangerous side of the floor ---
    ("poller", "poller: elapsed only", "Waiting for build, 30s elapsed", "Waiting for build, 45s elapsed"),
    ("poller", "poller: pct progress", "Upload 41% complete", "Upload 43% complete"),
    ("poller", "poller: queue depth", "Queue depth: 12 jobs pending", "Queue depth: 11 jobs pending"),
    ("poller", "poller: unchanged status word", "status=RUNNING retries=0", "status=RUNNING retries=1"),
    ("poller", "poller: heartbeat ts", "heartbeat ok at 14:02:11", "heartbeat ok at 14:07:11"),
    # --- true loop: must be at or near exactly zero ---
    ("true_loop", "true loop: identical error", "PermissionError: /etc/shadow", "PermissionError: /etc/shadow"),
    ("true_loop", "true loop: identical empty result", "No results found.", "No results found."),
    # --- batch: the side we must not trip ---
    ("batch", "batch: different invoice rows", "ACME Corp, Rs 84,200, due Aug 12", "Vertex Ltd, Rs 19,750, due Aug 30"),
    ("batch", "batch: different file extracted", "invoice_041: total 84200, vendor ACME", "invoice_042: total 19750, vendor Vertex"),
    ("batch", "batch: different doc summary", "Contract signed 2024-03-01 by R. Mehta, 24 months", "Contract signed 2025-11-14 by S. Iyer, 6 months"),
    ("batch", "batch: different row ids", "row 41: sku=A99 qty=3 status=shipped", "row 42: sku=B12 qty=7 status=pending"),
    # --- genuine progress: research agent learning something new ---
    ("progress", "progress: new subtopic", "Auth tokens expire after 3600s.", "Refresh requires a client secret and rotates the token."),
    ("progress", "progress: unrelated finding", "The config lives in /etc/app.yaml.", "Rate limiting is enforced at the gateway, 100 rps."),
]


def novelty(enc: MiniLMEncoder, a: str, b: str) -> float:
    va, vb = enc.encode([a, b])
    return 1.0 - cosine(va, vb)


def main() -> int:
    enc = MiniLMEncoder().load()
    rows = []
    for cls, label, a, b in PRIMARY + SUPPORTING:
        nov = novelty(enc, a, b)
        rows.append(
            {
                "class": cls,
                "label": label,
                "obs_a": a,
                "obs_b": b,
                "novelty": round(nov, 6),
                "primary": (cls, label, a, b) in [tuple(p) for p in PRIMARY],
            }
        )

    print(f"encoder revision: {enc.revision}")
    print(f"candidate floor : {CANDIDATE_FLOOR}  (placeholder under test)\n")

    print("PRIMARY readings (the three that decide the floor)")
    print(f"{'class':<10} {'label':<40} {'novelty':>8}")
    print("-" * 60)
    for r in rows:
        if r["primary"]:
            print(f"{r['class']:<10} {r['label']:<40} {r['novelty']:>8.4f}")

    print("\nFULL distribution by class")
    print(f"{'class':<10} {'label':<40} {'novelty':>8}")
    print("-" * 60)
    for r in sorted(rows, key=lambda r: (r["class"], r["novelty"])):
        print(f"{r['class']:<10} {r['label']:<40} {r['novelty']:>8.4f}")

    # Per-class envelope. The floor lives in the gap between the top of the
    # near-duplicate classes and the bottom of the informative classes.
    classes: dict[str, list[float]] = {}
    for r in rows:
        classes.setdefault(r["class"], []).append(r["novelty"])
    summary = {
        cls: {
            "n": len(vals),
            "min": round(min(vals), 6),
            "max": round(max(vals), 6),
            "mean": round(sum(vals) / len(vals), 6),
        }
        for cls, vals in sorted(classes.items())
    }

    print("\nper-class envelope")
    print(f"{'class':<10} {'n':>3} {'min':>8} {'mean':>8} {'max':>8}")
    print("-" * 42)
    for cls, s in summary.items():
        print(f"{cls:<10} {s['n']:>3} {s['min']:>8.4f} {s['mean']:>8.4f} {s['max']:>8.4f}")

    # The usable window: strictly above every near-duplicate reading (poller,
    # true_loop) and strictly below every informative reading (batch, progress).
    hold_below = max(classes["poller"] + classes["true_loop"])
    trip_above = min(classes["batch"] + classes["progress"])
    window_lo, window_hi = hold_below, trip_above
    window_width = window_hi - window_lo
    separated = window_width > 0
    survives = separated and window_lo < CANDIDATE_FLOOR < window_hi

    print("\n" + "=" * 60)
    print(f"highest near-duplicate novelty (must be BELOW floor): {hold_below:.4f}")
    print(f"lowest informative novelty     (must be ABOVE floor): {trip_above:.4f}")
    print(f"usable floor window: ({window_lo:.4f}, {window_hi:.4f})  width {window_width:.4f}")
    print(f"classes separated  : {'YES' if separated else 'NO -- classes overlap'}")
    print(f"floor {CANDIDATE_FLOOR} survives : {'YES' if survives else 'NO'}")
    print("=" * 60)
    if not survives and separated:
        mid = (window_lo + window_hi) / 2
        print(f"note: window midpoint is {mid:.4f}; floor is a sweep parameter, not a hand-picked one.")

    path = ROOT / "metrics.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc["novelty_floor_probe"] = {
        "encoder": enc.fingerprint(),
        "candidate_floor": CANDIDATE_FLOOR,
        "candidate_floor_status": "placeholder pending sweep",
        "readings": rows,
        "per_class": summary,
        "highest_near_duplicate": round(hold_below, 6),
        "lowest_informative": round(trip_above, 6),
        "usable_window": [round(window_lo, 6), round(window_hi, 6)],
        "usable_window_width": round(window_width, 6),
        "classes_separated": separated,
        "candidate_floor_survives": survives,
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote -> {path}  (key: novelty_floor_probe)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
