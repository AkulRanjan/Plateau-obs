r"""Parameter sweep over the §6 fixtures: five axes, 576 combinations.

NOVELTY_FLOOR x K_SIGMA x TRIP_AFTER_LOOP x TRIP_AFTER_STALL x WINDOW_SIZE.
Reports pass/fail, turns-to-warm and trip turn for each combination.

Two things to know before quoting a number from this sweep:

1. It used to report "0 usable configurations out of 144", which measured
   fixture length rather than the design. Fixtures 1 and 2 were two turns long
   and could not trip at any setting. Both are six turns now -- both, so that
   lengthening the positive one does not buy recall for free.

2. **It still cannot decide `window_size`.** The longest fixture is 7 turns, so
   a window of 8 and a window of 24 hold identical contents, and every window
   value comes back usable for want of anything to disagree about. That axis is
   decided by scripts/long_trace_sweep.py, on 16-61 turn traces, where it turns
   out to be the only load-bearing parameter of the five.

    python -m eval.sweep

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

import numpy as np  # noqa: E402

from plateau.calibrator import Calibrator  # noqa: E402
from plateau.detector import Detector, PlateauConfig  # noqa: E402
from plateau.encoder import MiniLMEncoder  # noqa: E402
from scripts.detector_fixtures import FIXTURES, PREAMBLE  # noqa: E402


# Ground truth per fixture: should the detector trip on it or not?
# 1 and 3a are genuine stalls. 2 is a healthy batch job. 3b is a stall the
# design is documented as missing, so it is scored separately and excluded from
# both recall and the false-trip rate.
SHOULD_TRIP = {
    "1_paraphrase_loop": True,
    "2_invoice_batch_grind": False,
    "3a_thrash_identical_errors": True,
    "3b_thrash_varied_errors": None,   # documented known miss
}


def summarise(results: dict, fixture_names) -> dict:
    """Reduce the grid to recall, false-trip rate, and the usable window.

    The usable window is the set of parameter combinations that catch every
    stall and false-trip on nothing. Its *width* is a first-class result: a
    design that only works at one knife-edge setting is not a design, it is a
    coincidence.
    """
    positives = [n for n in fixture_names if SHOULD_TRIP.get(n) is True]
    negatives = [n for n in fixture_names if SHOULD_TRIP.get(n) is False]

    per_config = {}
    for key, row in results.items():
        detected = [n for n in positives if row[n]["trip_turn"] is not None]
        false_trips = [n for n in negatives if row[n]["trip_turn"] is not None]
        per_config[key] = {
            "novelty_floor": row["novelty_floor"],
            "k_sigma": row["k_sigma"],
            "trip_after_loop": row["trip_after_loop"],
            "trip_after_stall": row["trip_after_stall"],
            "window_size": row["window_size"],
            "recall": len(detected) / len(positives) if positives else None,
            "detected": detected,
            "missed": [n for n in positives if n not in detected],
            "false_trips": len(false_trips),
            "false_trip_rate": len(false_trips) / len(negatives) if negatives else None,
            "usable": len(detected) == len(positives) and not false_trips,
        }

    usable = [k for k, v in per_config.items() if v["usable"]]
    recalls = sorted({v["recall"] for v in per_config.values() if v["recall"] is not None})

    # Per-parameter usable range, so the window has a width per axis rather than
    # a single opaque count.
    axes = (
        "novelty_floor", "k_sigma", "trip_after_loop", "trip_after_stall",
        "window_size",
    )
    window = {}
    for axis in axes:
        values = sorted({per_config[k][axis] for k in usable})
        window[axis] = {
            "usable_values": values,
            "width": (max(values) - min(values)) if values else 0,
            "n_usable_values": len(values),
        }

    return {
        "ground_truth": SHOULD_TRIP,
        "n_configs": len(per_config),
        "n_usable_configs": len(usable),
        "usable_fraction": len(usable) / len(per_config) if per_config else 0.0,
        # Quoted as a percentage in the README; recorded so that figure is
        # backed by a measurement rather than by arithmetic done in prose.
        "usable_percent": (
            round(100 * len(usable) / len(per_config), 1) if per_config else 0.0
        ),
        "distinct_recall_values": recalls,
        "max_recall_observed": max(recalls) if recalls else None,
        "usable_window": window,
        "usable_config_keys": usable,
        "per_config": per_config,
    }


def report_summary(summary: dict) -> None:
    print("\n" + "=" * 78)
    print("SWEEP SUMMARY")
    print("=" * 78)
    print(f"configs evaluated        : {summary['n_configs']}")
    print(f"usable configs           : {summary['n_usable_configs']} "
          f"({summary['usable_fraction'] * 100:.1f}%)")
    print(f"distinct recall values   : {summary['distinct_recall_values']}")
    print(f"max recall observed      : {summary['max_recall_observed']}")

    if summary["n_usable_configs"] == 0:
        print("\nNO USABLE CONFIGURATION EXISTS in this grid.")
        print("A config is usable only if it catches every stall AND false-trips")
        print("on nothing. Since no config reaches recall 1.0, the usable")
        print("threshold window is EMPTY and its width is undefined.")
    else:
        print("\nusable threshold window, per axis:")
        for axis, info in summary["usable_window"].items():
            print(
                f"    {axis:<18} values={info['usable_values']} "
                f"width={info['width']}"
            )

    # Which positives are never caught, in any configuration?
    never = {}
    for key, config in summary["per_config"].items():
        for name in config["missed"]:
            never[name] = never.get(name, 0) + 1
    total = summary["n_configs"]
    if never:
        print("\npositives missed, by configuration count:")
        for name, count in sorted(never.items()):
            flag = "  <-- MISSED IN EVERY CONFIG" if count == total else ""
            print(f"    {name:<32} {count}/{total}{flag}")


class MemoEncoder:
    """Sweep-local embedding memo.

    The sweep replays the same handful of fixture strings once per
    configuration, and the grid is now 576 configurations, so the same text is
    embedded hundreds of times for an identical result. This caches by exact
    text.

    It lives here and NOT inside MiniLMEncoder on purpose: that class's
    ``n_encode_calls`` / ``n_texts_encoded`` counters are how the breaker's
    zero-encode invariant (I2) is proved by counting rather than asserted, and a
    memo inside the encoder would silently invalidate that proof.
    """

    def __init__(self, encoder: MiniLMEncoder) -> None:
        self._encoder = encoder
        self._cache: dict[str, np.ndarray] = {}

    def encode(self, texts):
        texts = [texts] if isinstance(texts, str) else list(texts)
        missing = [t for t in dict.fromkeys(texts) if t not in self._cache]
        if missing:
            for text, vec in zip(missing, self._encoder.encode(missing)):
                self._cache[text] = vec
        return np.stack([self._cache[t] for t in texts])

    def fingerprint(self) -> dict:
        return self._encoder.fingerprint()


def run_one(
    encoder,
    turns,
    novelty_floor: float,
    k_sigma: float,
    trip_after_loop: int,
    trip_after_stall: int,
    window_size: int,
) -> dict:
    config = PlateauConfig(
        novelty_floor=novelty_floor,
        trip_after_loop=trip_after_loop,
        trip_after_stall=trip_after_stall,
        window_size=window_size,
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
    encoder = MemoEncoder(MiniLMEncoder().load())

    # Sweep grid.
    novelty_floors = [0.25, 0.30, 0.35, 0.40]
    k_sigmas = [0.5, 1.0, 1.5, 2.0]
    trip_after_loops = [2, 3, 4]
    trip_after_stalls = [4, 6, 8]
    # ADDED AXIS. Both dials are max_cosine against the last `window_size`
    # turns, so a repetition spaced further apart than the window is
    # structurally invisible -- the detector cannot see a loop whose period
    # exceeds its own memory. This was hard-coded to 8 and justified by no
    # measurement in this repo, which made it the one parameter the sweep was
    # not entitled to conclude anything about.
    window_sizes = [8, 12, 16, 24]

    fixture_names = list(FIXTURES.keys())
    n_configs = (
        len(novelty_floors) * len(k_sigmas) * len(trip_after_loops)
        * len(trip_after_stalls) * len(window_sizes)
    )

    print(
        f"Sweeping {len(novelty_floors)} floors × {len(k_sigmas)} k_sigmas × "
        f"{len(trip_after_loops)} loops × {len(trip_after_stalls)} stalls × "
        f"{len(window_sizes)} windows = {n_configs} combinations"
    )
    print()

    results = {}
    for f, k, tl, ts, w in itertools.product(
        novelty_floors, k_sigmas, trip_after_loops, trip_after_stalls, window_sizes
    ):
        key = f"f{f}_k{k}_tl{tl}_ts{ts}_w{w}"
        row = {
            "novelty_floor": f, "k_sigma": k, "trip_after_loop": tl,
            "trip_after_stall": ts, "window_size": w,
        }
        for name in fixture_names:
            row[name] = run_one(encoder, FIXTURES[name]["turns"], f, k, tl, ts, w)
        results[key] = row

    # Print summary table.
    header = (
        f"{'floor':>5} {'k_s':>4} {'tl':>3} {'ts':>3} {'w':>3}"
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
        print(
            f"{row['novelty_floor']:>5.2f} {row['k_sigma']:>4.1f} "
            f"{row['trip_after_loop']:>3} {row['trip_after_stall']:>3} "
            f"{row['window_size']:>3}{cells}"
        )

    summary = summarise(results, fixture_names)
    report_summary(summary)

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
            "window_size": window_sizes,
        },
        "summary": summary,
        "results": results,
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote -> {path}  (key: sweep)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
