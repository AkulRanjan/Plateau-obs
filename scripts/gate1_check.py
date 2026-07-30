"""Gate 1 -- validate the core premise before building anything on top of it.

Plateau's headline claim is that action similarity and observation novelty are
*separable* dials. The counter-demo depends on one specific combination:

  - near-identical actions must read as near-identical  (paraphrase, and batch)
  - genuinely different observations must read as different

If MiniLM cannot separate those, the four-quadrant model collapses into "one
dial", the batch-job counter-demo stops working, and the headline claim is in
trouble. Better to know that now than at hour 30.

Runs fully offline against the pinned snapshot.

    python scripts/gate1_check.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["HF_HUB_OFFLINE"] = "1"

from plateau.encoder import MiniLMEncoder, cosine, pinned_revision  # noqa: E402

# (label, text_a, text_b, expectation, threshold, direction)
CHECKS = [
    (
        "1. action paraphrase   (same intent, reworded)",
        "search_docs(q='auth token refresh')",
        "search_docs(q='how do I refresh a token')",
        ">= 0.75",
        0.75,
        "high",
    ),
    (
        "2. action batch        (same tool, next item)",
        "extract_text(f='invoice_041.pdf')",
        "extract_text(f='invoice_042.pdf')",
        ">= 0.90",
        0.90,
        "high",
    ),
    (
        "3. observation content (different invoices)",
        "ACME Corp, Rs 84,200, due Aug 12",
        "Vertex Ltd, Rs 19,750, due Aug 30",
        "LOW",
        0.75,
        "low",
    ),
]


def main() -> int:
    rev = pinned_revision()
    if rev is None:
        print("FAIL: encoder not pinned. Run scripts/pin_encoder.py first.")
        return 2

    enc = MiniLMEncoder().load()
    print(f"encoder : {enc.model_id}")
    print(f"revision: {rev}")
    print(f"dim     : {enc._model.get_sentence_embedding_dimension()}  seed: 1337\n")

    results = []
    for label, a, b, expectation, threshold, direction in CHECKS:
        va, vb = enc.encode([a, b])
        sim = cosine(va, vb)
        ok = sim >= threshold if direction == "high" else sim < threshold
        results.append((label, a, b, sim, expectation, ok))

    width = 52
    print(f"{'check':<{width}} {'cos':>7}  {'expect':>8}  verdict")
    print("-" * (width + 30))
    for label, a, b, sim, expectation, ok in results:
        print(f"{label:<{width}} {sim:>7.4f}  {expectation:>8}  {'PASS' if ok else 'FAIL'}")
    print("-" * (width + 30))

    for label, a, b, sim, expectation, ok in results:
        print(f"\n{label}")
        print(f"    A: {a}")
        print(f"    B: {b}")
        print(f"    cos = {sim:.6f}   expected {expectation}")

    # The premise needs the *combination*, not the individual readings: the two
    # action pairs high AND the observation pair low, with real separation.
    action_min = min(r[3] for r in results[:2])
    obs = results[2][3]
    margin = action_min - obs

    print("\n" + "=" * (width + 30))
    print(f"separation margin (min action sim - observation sim) = {margin:.4f}")
    all_ok = all(r[5] for r in results)
    print(f"GATE 1: {'PASS -- premise holds, safe to build on' if all_ok else 'FAIL -- STOP'}")
    print("=" * (width + 30))

    # --- non-gating: where do these readings sit on MiniLM's actual scale? ---
    # MiniLM's cosine range is compressed and shared *format* inflates
    # similarity. Calibration (gate 2) must be designed against the real scale,
    # not against an assumed 0..1 spread, so measure the anchors here.
    scale = [
        ("identical string (novelty floor)",
         "ACME Corp, Rs 84,200, due Aug 12",
         "ACME Corp, Rs 84,200, due Aug 12"),
        ("same format, different content (check 3)",
         "ACME Corp, Rs 84,200, due Aug 12",
         "Vertex Ltd, Rs 19,750, due Aug 30"),
        ("unrelated domains",
         "ACME Corp, Rs 84,200, due Aug 12",
         "the kettle is boiling on the stove"),
        ("different tool entirely",
         "search_docs(q='auth token refresh')",
         "delete_file(path='/tmp/cache.db')"),
    ]
    print("\ncosine scale reference (context, not a gate):")
    scale_readings = []
    for label, a, b in scale:
        va, vb = enc.encode([a, b])
        val = cosine(va, vb)
        scale_readings.append((label, val))
        print(f"    {label:<42} {val:>7.4f}")

    # Determinism: same input, identical bytes. The fingerprint hash is the
    # cross-process check -- run this script twice, compare the two hashes.
    v1 = enc.encode_one("determinism spot check")
    v2 = enc.encode_one("determinism spot check")
    print(f"\nintra-process determinism: {'identical bytes' if v1.tobytes() == v2.tobytes() else 'DIVERGED'}")
    fp = enc.fingerprint()
    print(f"probe_sha256: {fp['probe_sha256']}")
    print(f"encode calls: {enc.n_encode_calls}  texts encoded: {enc.n_texts_encoded}")

    write_metrics(results, scale_readings, margin, all_ok, fp)
    print(f"\nwrote -> {ROOT / 'metrics.json'}  (key: gate1_premise)")

    return 0 if all_ok else 1


def write_metrics(results, scale_readings, margin, all_ok, fingerprint) -> None:
    """Merge Gate 1 readings into metrics.json under 'gate1_premise'.

    Rule 1: no number appears in any document unless a script in this repo
    produced it and wrote it here. Merges rather than overwrites so the §9
    harness can own its own keys in the same file.
    """
    path = ROOT / "metrics.json"
    doc = {}
    if path.exists():
        doc = json.loads(path.read_text(encoding="utf-8"))

    doc["gate1_premise"] = {
        "encoder": fingerprint,
        "checks": [
            {
                "label": label.split(". ", 1)[1].strip(),
                "text_a": a,
                "text_b": b,
                "cosine": round(sim, 6),
                "expected": expectation,
                "passed": ok,
            }
            for label, a, b, sim, expectation, ok in results
        ],
        "scale_reference": {label: round(val, 6) for label, val in scale_readings},
        "separation_margin": round(margin, 6),
        "gate_passed": all_ok,
    }
    path.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
