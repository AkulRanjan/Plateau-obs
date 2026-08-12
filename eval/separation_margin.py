"""How much room is there between a healthy trace and a trip? Measured, per trace.

`eval/floor_sweep.py` reports a usable novelty-floor range. A range like that
reads like a working design, and on its own it overstates one. This script
exists to produce the part that qualifies it.

Three things it measures:

1. **Whether the distributions overlap, and by how much headroom.** Whether the
   per-turn observation novelty of a healthy batch job and of a reworded stall
   separate at all is a property of the floor, not a fixed fact, so this reports
   it rather than asserting it. `headroom_to_floor` is the number to read: the
   healthy trace's *minimum* novelty minus the floor. Negative means at least one
   healthy turn already reads as stagnant, and the design is relying on the
   counter rather than on the threshold.

2. **Consecutive-run margin.** What keeps the healthy batch alive when headroom
   is negative is not the floor but the *counter*: tripping needs N consecutive
   sub-floor readings, and the batch's sub-floor readings are not consecutive
   enough to accumulate. The margin is
   `trip_after_stall - longest_consecutive_stagnant_run`. That number, not the
   floor range, is how close a healthy trace sits to a false trip.

3. **Which negatives are held by margin and which by declaration.** These are
   different safety stories and averaging them hides the weaker one.
   `healthy_invoice_batch` survives on the counter margin above.
   `healthy_poller` does not survive on anything measurable -- it is stagnant by
   construction and is held up entirely by its `idempotent: true` declaration.
   Its margin is reported, and it is negative: that negative number is the
   README's claim that the declaration is a burden rather than a capability,
   expressed as a quantity.

A design whose safety rests on a counter margin of a couple of turns is a
different claim from one whose safety rests on separated distributions, and the
README should say which one this is.

The floor, window and trip thresholds are **imported from the shipped
constants**, not restated here. An earlier probe in this repository hard-coded a
candidate value, the code moved on, and the recorded verdict silently came to
refer to a number that no longer existed. `--floor X` probes a candidate value
instead, and records both it and the committed one.

    python eval/separation_margin.py
    python eval/separation_margin.py --floor 0.48

Writes metrics.json -> separation_margin.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["HF_HUB_OFFLINE"] = "1"

from eval.traces import IDEMPOTENT_TOOLS, PREAMBLE_LENGTH, TRACES  # noqa: E402
from plateau.calibrator import NOVELTY_FLOOR, Calibrator  # noqa: E402
from plateau.detector import (  # noqa: E402
    TRIP_AFTER_LOOP,
    TRIP_AFTER_STALL,
    WINDOW_SIZE,
    Detector,
    PlateauConfig,
)
from plateau.encoder import MiniLMEncoder  # noqa: E402

#: The trace held up by its declaration rather than by any measured margin.
POLLER = "healthy_poller"


def longest_run(flags) -> int:
    longest = current = 0
    for flag in flags:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    return longest


def profile(encoder, name, trace, floor):
    detector = Detector(
        encoder=encoder,
        calibrator=Calibrator(novelty_floor=floor),
        config=PlateauConfig(
            novelty_floor=floor,
            trip_after_loop=TRIP_AFTER_LOOP,
            trip_after_stall=TRIP_AFTER_STALL,
            window_size=WINDOW_SIZE,
        ),
    )
    declared = IDEMPOTENT_TOOLS.get(name, frozenset())
    trip_turn = None
    for index, (action, observation) in enumerate(trace):
        idempotent = action.split("(")[0] in declared
        reading = detector.evaluate(action, observation, idempotent=idempotent)
        if reading.is_trip and trip_turn is None:
            trip_turn = index

    readings = detector.readings[PREAMBLE_LENGTH:]
    novelties = sorted(r.obs_novelty for r in readings)
    flags = [r.stagnant for r in readings]
    run = longest_run(flags)
    return {
        "turns_after_preamble": len(readings),
        "novelty_min": round(min(novelties), 6),
        # How far the closest turn of this trace sits from reading as stagnant.
        # Negative means at least one turn already does.
        "headroom_to_floor": round(min(novelties) - floor, 6),
        # The same quantity as a magnitude, for traces that are already under the
        # floor. Recorded separately because a negative number cannot be quoted
        # in prose and still be found by scripts/check_readme.py, which matches
        # unsigned figures -- and "sits 0.00059 below the floor" is the sentence
        # anyone would actually write.
        "distance_below_floor": round(max(0.0, floor - min(novelties)), 6),
        "novelty_p10": round(novelties[max(0, int(len(novelties) * 0.10))], 6),
        "novelty_median": round(statistics.median(novelties), 6),
        "novelty_max": round(max(novelties), 6),
        "stagnant_turns": sum(flags),
        "stagnant_fraction": round(sum(flags) / len(flags), 4),
        "longest_consecutive_stagnant_run": run,
        "consecutive_margin_to_trip": TRIP_AFTER_STALL - run,
        "trip_turn": trip_turn,
        "held_by": "declaration" if declared else "margin",
        "idempotent_tools": sorted(declared),
    }


def main() -> int:
    floor = NOVELTY_FLOOR
    if "--floor" in sys.argv:
        floor = float(sys.argv[sys.argv.index("--floor") + 1])

    encoder = MiniLMEncoder().load()

    committed = " (the committed default)" if floor == NOVELTY_FLOOR else ""
    print(f"floor under test: {floor}{committed}")
    if floor != NOVELTY_FLOOR:
        print(f"committed plateau.calibrator.NOVELTY_FLOOR is {NOVELTY_FLOOR}")
    print(
        f"trip_after_loop={TRIP_AFTER_LOOP}  trip_after_stall={TRIP_AFTER_STALL}  "
        f"window_size={WINDOW_SIZE}\n"
    )

    results = {}
    header = (
        f"{'trace':<34}{'min':>8}{'median':>8}{'max':>8}{'headroom':>10}"
        f"{'stagnant':>10}{'run':>6}{'margin':>8}{'held by':>13}"
    )
    print(header)
    print("-" * len(header))
    for name, (trace, should_trip) in TRACES.items():
        p = profile(encoder, name, trace, floor)
        p["should_trip"] = should_trip
        results[name] = p
        margin = "-" if should_trip else f"{p['consecutive_margin_to_trip']}"
        held = "-" if should_trip else p["held_by"]
        print(
            f"{name:<34}{p['novelty_min']:>8.4f}{p['novelty_median']:>8.4f}"
            f"{p['novelty_max']:>8.4f}{p['headroom_to_floor']:>+10.4f}"
            f"{str(p['stagnant_turns']) + '/' + str(p['turns_after_preamble']):>10}"
            f"{p['longest_consecutive_stagnant_run']:>6}{margin:>8}{held:>13}"
        )

    # The headline qualifier: do the healthy and stalled distributions overlap?
    healthy = [n for n, (_, s) in TRACES.items() if not s and n != POLLER]
    stalled = [n for n, (_, s) in TRACES.items() if s]
    overlaps = []
    for h in healthy:
        for s in stalled:
            if results[h]["novelty_min"] < results[s]["novelty_median"]:
                overlaps.append(
                    {
                        "healthy": h,
                        "stalled": s,
                        "healthy_min": results[h]["novelty_min"],
                        "stalled_median": results[s]["novelty_median"],
                    }
                )

    print()
    if overlaps:
        print("DISTRIBUTIONS OVERLAP — the floor is not a separating threshold:")
        for o in overlaps:
            print(
                f"    {o['healthy']} min {o['healthy_min']:.4f} sits BELOW "
                f"{o['stalled']} median {o['stalled_median']:.4f}"
            )
    else:
        print("Distributions are cleanly separated at this floor.")

    # Only traces actually held by a margin can have a tightest margin. Folding
    # the declaration-held poller in here would report its (negative) run as if
    # it were the design's safety margin, which is the opposite of the finding.
    by_margin = {
        n: r
        for n, r in results.items()
        if not r["should_trip"] and r["held_by"] == "margin"
    }
    tightest_name = min(
        by_margin, key=lambda n: by_margin[n]["consecutive_margin_to_trip"]
    )
    tightest = by_margin[tightest_name]

    print()
    print(
        f"headroom to the floor, healthy traces (novelty_min - {floor}):"
    )
    for name in healthy + [POLLER]:
        if name in results:
            head = results[name]["headroom_to_floor"]
            note = "  <- already reads as stagnant" if head < 0 else ""
            print(f"    {name:<34}{head:>+10.4f}{note}")

    print()
    print(
        f"TIGHTEST MARGIN-HELD TRACE: {tightest_name} — "
        f"{tightest['stagnant_fraction'] * 100:.0f}% of its turns already read as "
        f"'learned nothing',"
    )
    print(
        f"    and its longest consecutive run is "
        f"{tightest['longest_consecutive_stagnant_run']}, against a threshold of "
        f"{TRIP_AFTER_STALL}."
    )
    print(
        f"    It holds by {tightest['consecutive_margin_to_trip']} consecutive "
        f"turns, not by a novelty margin."
    )

    poller = results.get(POLLER)
    if poller is not None:
        print()
        print(
            f"DECLARATION-HELD TRACE: {POLLER} — longest consecutive stagnant run "
            f"{poller['longest_consecutive_stagnant_run']} against a threshold of "
            f"{TRIP_AFTER_STALL},"
        )
        print(
            f"    i.e. a margin of {poller['consecutive_margin_to_trip']}. It has "
            f"no margin at all; it is held up entirely by its"
        )
        print(
            f"    `idempotent: true` declaration on {poller['idempotent_tools']}. "
            f"Remove that and it trips."
        )

    path = ROOT / "metrics.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc["separation_margin"] = {
        "encoder": encoder.fingerprint(),
        "floor_under_test": floor,
        "committed_floor": NOVELTY_FLOOR,
        "floor_is_committed_default": floor == NOVELTY_FLOOR,
        "trip_after_loop": TRIP_AFTER_LOOP,
        "trip_after_stall": TRIP_AFTER_STALL,
        "window_size": WINDOW_SIZE,
        "traces": results,
        "distribution_overlaps": overlaps,
        "tightest_margin_held_trace": tightest_name,
        "tightest_consecutive_margin": tightest["consecutive_margin_to_trip"],
        "tightest_headroom_to_floor": tightest["headroom_to_floor"],
        "tightest_distance_below_floor": tightest["distance_below_floor"],
        "healthy_traces_already_stagnant": sorted(
            n
            for n, r in results.items()
            if not r["should_trip"] and r["headroom_to_floor"] < 0
        ),
        "declaration_held_traces": sorted(
            n
            for n, r in results.items()
            if not r["should_trip"] and r["held_by"] == "declaration"
        ),
        "poller_consecutive_margin": (
            poller["consecutive_margin_to_trip"] if poller else None
        ),
        "finding": (
            f"at floor {floor} the healthy and stalled novelty distributions "
            + ("overlap" if overlaps else "do not overlap")
            + f", but {tightest_name} clears the floor by only "
            f"{tightest['headroom_to_floor']}, so the usable floor range is not a "
            "separation margin: what keeps it alive is the consecutive-run "
            f"counter, with a margin of {tightest['consecutive_margin_to_trip']} "
            f"turns. The poller is not kept alive by any margin at all -- its own "
            f"run is {poller['longest_consecutive_stagnant_run'] if poller else 'n/a'} "
            f"against a threshold of {TRIP_AFTER_STALL} -- only by its "
            "idempotent declaration"
        ),
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote -> {path}  (key: separation_margin)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
