"""Parameter sweep for NOVELTY_FLOOR × K_SIGMA × TRIP_AFTER_LOOP × TRIP_AFTER_STALL.

Scans the four provisional parameters across all four fixtures and reports
pass/fail, turns-to-warm, and trip turn for each combination.

    .venv\Scripts\python -m eval.sweep

Writes metrics.json -> sweep.
"""

from __future__ import annotations

import itertools
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["HF_HUB_OFFLINE"] = "1"

from plateau.calibrator import Calibrator  # noqa: E402
from plateau.detector import Detector, PlateauConfig  # noqa: E402
from plateau.encoder import MiniLMEncoder  # noqa: E402
from scripts.detector_fixtures import FIXTURES, PREAMBLE  # noqa: E402


def run_one(
    encoder: MiniLMEncoder,
    turns,
    novelty_floor: float,
    k_sigma: float,
    trip_after_loop: int,
    trip_after_stall: int,
) -> dict:
    config = PlateauConfig(
        novelty_floor=novelty_floor,
        trip_after_loop=trip_after_loop,
        trip_after_stall=trip_after_stall,
    )
    cal = Calibrator(
        novelty_floor=novelty_floor,
        k_sigma=k_sigma,
    )
    detector = Detector(encoder=encoder, calibrator=cal, config=config)
    for a, o in PREAMBLE:
        detector.evaluate(a, o)

    trip_turn = None
    for index, (a, o) in enumerate(turns):
        reading = detector.evaluate(a, o)
        if reading.is_trip and trip_turn is None:
            trip_turn = index

    return {
        "trip_turn": trip_turn,
        "turns_to_warm": detector.calibrator.turns_to_warm,
        "is_warm": detector.calibrator.is_warm,
        "sim_ceiling": round(detector.calibrator.sim_ceiling, 4),
        "mu": round(detector.calibrator.mu, 4),
        "sigma": round(detector.calibrator.sigma, 4),
        "n_productive": detector.calibrator.n,
        "gate_rejection_rate": (
            sum(1 for r in detector.calibrator.log if r.gated) / len(detector.calibrator.log)
            if detector.calibrator.log
            else 0.0
        ),
    }


def main() -> int:
    encoder = MiniLMEncoder().load()

    # Sweep grid.
    novelty_floors = [0.25, 0.30, 0.35, 0.40]
    k_sigmas = [0.5, 1.0, 1.5, 2.0]
    trip_after_loops = [2, 3, 4]
    trip_after_stalls = [4, 6, 8]

    fixture_names = list(FIXTURES.keys())

    print(
        f"Sweeping {len(novelty_floors)} floors × {len(k_sigmas)} k_sigmas × "
        f"{len(trip_after_loops)} loops × {len(trip_after_stalls)} stalls = "
        f"{len(novelty_floors) * len(k_sigmas) * len(trip_after_loops) * len(trip_after_stalls)} combinations"
    )
    print()

    results = {}
    for f, k, tl, ts in itertools.product(
        novelty_floors, k_sigmas, trip_after_loops, trip_after_stalls
    ):
        key = f"f{f}_k{k}_tl{tl}_ts{ts}"
        row = {"novelty_floor": f, "k_sigma": k, "trip_after_loop": tl, "trip_after_stall": ts}
        for name in fixture_names:
            row[name] = run_one(encoder, FIXTURES[name]["turns"], f, k, tl, ts)
        results[key] = row

    # Print summary table.
    header = (
        f"{'floor':>5} {'k_s':>4} {'tl':>3} {'ts':>3}"
        + "".join(f" {name[:10]:>10}" for name in fixture_names)
    )
    print(header)
    print("-" * len(header))
    for key, row in results.items():
        cells = "".join(
            f" {str(v['trip_turn']):>10}" if v['trip_turn'] is not None else f" {'---':>10}"
            for name, v in row.items()
            if name in fixture_names
        )
        floor_v = row['novelty_floor']
        k_v = row['k_sigma']
        tl_v = row['trip_after_loop']
        ts_v = row['trip_after_stall']
        print(
            f"{floor_v:>5.2f} {k_v:>4.1f} "
            f"{tl_v:>3} {ts_v:>3}{cells}"
        )

    # Write to metrics.json
    path = ROOT / "metrics.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc["sweep"] = {
        "encoder": encoder.fingerprint(),
        "grid": {
            "novelty_floor": novelty_floors,
            "k_sigma": k_sigmas,
            "trip_after_loop": trip_after_loops,
            "trip_after_stall": trip_after_stalls,
        },
        "results": results,
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote -> {path}  (key: sweep)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
