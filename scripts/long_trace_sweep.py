"""The parameter sweep, run on traces long enough for the parameters to matter.

`eval/sweep.py` sweeps the same five axes over the §6 fixtures, and that sweep
cannot decide `window_size`: the longest fixture is 7 turns, so a window of 8 and
a window of 24 hold identical contents and every window value comes back
"usable" for want of anything to disagree about. Reporting that as a result
would repeat, in a new place, exactly the mistake the two-turn fixtures made.

This runs the same grid over eval/traces.TRACES -- 16 to 61 turns, three
positives and two negatives -- where the window is the difference between seeing
a repetition and not seeing it.

Honours the per-tool `idempotent: true` declaration, because the sweep is asking
what the shipped system can be configured to do, and the declaration is part of
the shipped system. The undeclared number is in metrics.json ->
long_trace_comparison, reported side by side.

    python scripts/long_trace_sweep.py

Writes metrics.json -> long_trace_sweep.
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

from eval.sweep import MemoEncoder  # noqa: E402
from eval.traces import IDEMPOTENT_TOOLS, TRACES  # noqa: E402
from plateau.calibrator import Calibrator  # noqa: E402
from plateau.detector import Detector, PlateauConfig  # noqa: E402
from plateau.encoder import MiniLMEncoder  # noqa: E402

NOVELTY_FLOORS = [0.25, 0.30, 0.35, 0.40]
K_SIGMAS = [0.5, 1.0, 1.5, 2.0]
TRIP_AFTER_LOOPS = [2, 3, 4]
TRIP_AFTER_STALLS = [4, 6, 8]
WINDOW_SIZES = [8, 12, 16, 24]


def run_one(encoder, config: PlateauConfig, k_sigma: float) -> dict[str, int | None]:
    trips = {}
    for name, (trace, _) in TRACES.items():
        detector = Detector(
            encoder=encoder,
            calibrator=Calibrator(novelty_floor=config.novelty_floor, k_sigma=k_sigma),
            config=config,
        )
        trips[name] = detector.run(
            trace, idempotent_tools=IDEMPOTENT_TOOLS.get(name, frozenset())
        )
    return trips


def main() -> int:
    encoder = MemoEncoder(MiniLMEncoder().load())

    positives = [n for n, (_, should) in TRACES.items() if should]
    negatives = [n for n, (_, should) in TRACES.items() if not should]

    grid = list(
        itertools.product(
            NOVELTY_FLOORS, K_SIGMAS, TRIP_AFTER_LOOPS, TRIP_AFTER_STALLS, WINDOW_SIZES
        )
    )
    print(f"sweeping {len(grid)} configurations over {len(TRACES)} traces")
    print(f"  positives {positives}")
    print(f"  negatives {negatives}")
    print()

    per_config = {}
    for f, k, tl, ts, w in grid:
        config = PlateauConfig(
            novelty_floor=f, trip_after_loop=tl, trip_after_stall=ts, window_size=w
        )
        trips = run_one(encoder, config, k)
        detected = [n for n in positives if trips[n] is not None]
        false_trips = [n for n in negatives if trips[n] is not None]
        per_config[f"f{f}_k{k}_tl{tl}_ts{ts}_w{w}"] = {
            "novelty_floor": f,
            "k_sigma": k,
            "trip_after_loop": tl,
            "trip_after_stall": ts,
            "window_size": w,
            "trip_turn": trips,
            "recall": round(len(detected) / len(positives), 4),
            "false_trip_rate": round(len(false_trips) / len(negatives), 4),
            "missed": [n for n in positives if trips[n] is None],
            "false_trips": false_trips,
            "usable": len(detected) == len(positives) and not false_trips,
            "mean_turns_to_detection": (
                round(sum(trips[n] for n in detected) / len(detected), 2)
                if detected
                else None
            ),
        }

    usable = [k for k, v in per_config.items() if v["usable"]]
    axes = (
        "novelty_floor", "k_sigma", "trip_after_loop", "trip_after_stall", "window_size"
    )
    window = {}
    for axis in axes:
        values = sorted({per_config[k][axis] for k in usable})
        window[axis] = {
            "usable_values": values,
            "width": (max(values) - min(values)) if values else 0,
            "n_usable_values": len(values),
        }

    # Which axes actually decide the outcome. An axis whose every value survives
    # is not a knob the design depends on; an axis where only some values
    # survive is load-bearing and has to be defended.
    decisive = {
        axis: {
            "all_values": sorted({per_config[k][axis] for k in per_config}),
            "usable_values": window[axis]["usable_values"],
            "is_load_bearing": len(window[axis]["usable_values"])
            < len({per_config[k][axis] for k in per_config}),
        }
        for axis in axes
    }

    print(f"usable configurations: {len(usable)}/{len(per_config)} "
          f"({100 * len(usable) / len(per_config):.1f}%)")
    print()
    print("per-axis usable window:")
    for axis in axes:
        w = window[axis]
        flag = "  <- LOAD-BEARING" if decisive[axis]["is_load_bearing"] else ""
        print(f"    {axis:<18} usable={w['usable_values']} "
              f"of {decisive[axis]['all_values']}{flag}")

    misses: dict[str, int] = {}
    for v in per_config.values():
        for name in v["missed"]:
            misses[name] = misses.get(name, 0) + 1
    falses: dict[str, int] = {}
    for v in per_config.values():
        for name in v["false_trips"]:
            falses[name] = falses.get(name, 0) + 1

    print()
    print("positives missed, by configuration count:")
    for name, n in sorted(misses.items()):
        print(f"    {name:<34} {n}/{len(per_config)}")
    print("negatives false-tripped, by configuration count:")
    for name, n in sorted(falses.items()) or [("none", 0)]:
        print(f"    {name:<34} {n}/{len(per_config)}")

    fastest = None
    if usable:
        fastest = min(
            usable, key=lambda k: per_config[k]["mean_turns_to_detection"] or 1e9
        )
        print()
        print(f"fastest usable configuration: {fastest}")
        print(f"    mean turns to detection {per_config[fastest]['mean_turns_to_detection']}")
        print(f"    trip turns {per_config[fastest]['trip_turn']}")

    summary = {
        "n_configs": len(per_config),
        "n_usable_configs": len(usable),
        "usable_fraction": round(len(usable) / len(per_config), 4),
        "usable_percent": round(100 * len(usable) / len(per_config), 1),
        "ground_truth": {n: should for n, (_, should) in TRACES.items()},
        "usable_window": window,
        "axis_is_load_bearing": decisive,
        "missed_by_config_count": misses,
        "false_tripped_by_config_count": falses,
        "fastest_usable_config": fastest,
        "usable_config_keys": usable,
        "scope_note": (
            "Run on the 16-61 turn classes in eval/traces.py, not the §6 "
            "fixtures: the longest fixture is 7 turns, so a fixture sweep "
            "cannot distinguish a window of 8 from a window of 24 and would "
            "report every window value usable for want of evidence. Honours "
            "the per-tool `idempotent: true` declaration; the undeclared "
            "numbers are in long_trace_comparison."
        ),
    }

    path = ROOT / "metrics.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc["long_trace_sweep"] = {
        "encoder": encoder.fingerprint(),
        "grid": {
            "novelty_floor": NOVELTY_FLOORS,
            "k_sigma": K_SIGMAS,
            "trip_after_loop": TRIP_AFTER_LOOPS,
            "trip_after_stall": TRIP_AFTER_STALLS,
            "window_size": WINDOW_SIZES,
        },
        "summary": summary,
        "results": per_config,
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote -> {path}  (key: long_trace_sweep)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
