"""§6 fixture pairs -- measure the three canonical readings and record them.

Reports actual action_sim, obs_novelty, and quadrant for:

    1. paraphrase pair, identical results        -> expect loop
    2. invoice batch pair, different records     -> expect grind   (COUNTER-DEMO)
    3. thrash triple, all "not found"            -> expect thrash

A note on why each fixture has a preamble
-----------------------------------------
The quadrant depends on the calibrator's ceiling, which only exists once the
calibrator is warm. A run that is stuck from turn 0 never warms -- its turns are
all gate-rejected -- so it sits on the conservative default. That is not a fixture
artefact, it is a real property worth knowing: the detector needs to have seen
productive work before it can recognise the absence of it.

So each fixture runs a documented productive preamble first, then the pattern
under test. This mirrors the demo narrative: an agent works normally, then stalls.

Writes metrics.json -> detector_fixtures.

    python scripts/detector_fixtures.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["HF_HUB_OFFLINE"] = "1"

from eval.traces import PRODUCTIVE_PREAMBLE  # noqa: E402
from plateau.calibrator import NOVELTY_FLOOR, Calibrator  # noqa: E402
from plateau.detector import Detector, PlateauConfig  # noqa: E402
from plateau.encoder import MiniLMEncoder  # noqa: E402

# A productive preamble: varied actions, each returning genuinely new information.
# This is what a healthy agent looks like, and it is what the calibrator learns
# "normal" from.
#
# Imported, not copied. This module and eval/traces.py each used to carry their
# own byte-identical list, so the §6 fixtures and the long traces could silently
# calibrate against different preambles.
PREAMBLE = PRODUCTIVE_PREAMBLE

FIXTURES = {
    # LENGTHENED. Both this fixture and the counter-demo below ran 2 turns, and
    # turn 0 is not stagnant (novelty 0.8974 -- the non-answer is novel against
    # the *preamble*). So loop_hits peaked at 1 and no threshold in the grid,
    # which starts at trip_after_loop=2, could ever fire. The sweep's "0 usable
    # configurations out of 144" was measuring fixture length, not the design.
    #
    # Both fixtures were lengthened to 6 turns, deliberately together: extending
    # only the positive one buys recall for free and would make the sweep say
    # more than it knows. The counter-demo has to be tested at equal depth.
    #
    # Wordings come from eval.traces._PARAPHRASES, the same pool the 61-turn
    # long trace draws from, rather than being invented here.
    "1_paraphrase_loop": {
        "expect": "loop",
        # Now that it is long enough to trip, it is pinned on the trip turn
        # rather than only on its final label. Turn 0 is not stagnant -- the
        # non-answer is novel against the preamble -- so the first stagnant turn
        # is 1 and TRIP_AFTER_LOOP=3 lands on turn 3.
        "expect_trip": True,
        "expect_trip_turn": 3,
        "note": "same intent reworded, identical results returned",
        "turns": [
            ("search_docs(q='auth token refresh')", "No relevant results found."),
            ("search_docs(q='how do I refresh a token')", "No relevant results found."),
            ("search_docs(q='refreshing auth tokens')", "No relevant results found."),
            ("search_docs(q='token refresh procedure')", "No relevant results found."),
            ("search_docs(q='refresh the auth token')", "No relevant results found."),
            ("search_docs(q='auth refresh flow')", "No relevant results found."),
        ],
    },
    "2_invoice_batch_grind": {
        "expect": "grind",
        # The counter-demo now runs as long as the loop fixture, so "does not
        # trip" is a claim about six turns rather than about two, and is pinned
        # as such.
        "expect_trip": False,
        "note": "COUNTER-DEMO: near-identical actions, genuinely different records",
        # The first two turns are the gate-1 measured pair (action_sim 0.9913,
        # obs_novelty 0.4392) and are kept verbatim. The other four continue the
        # same batch in the same format: a genuinely new record every turn.
        "turns": [
            ("extract_text(f='invoice_041.pdf')", "ACME Corp, Rs 84,200, due Aug 12"),
            ("extract_text(f='invoice_042.pdf')", "Vertex Ltd, Rs 19,750, due Aug 30"),
            ("extract_text(f='invoice_043.pdf')", "Bluewave Systems, Rs 112,400, due Sep 04"),
            ("extract_text(f='invoice_044.pdf')", "Orchid Traders, Rs 47,900, due Sep 18"),
            ("extract_text(f='invoice_045.pdf')", "Northgate Supply, Rs 203,150, due Oct 02"),
            ("extract_text(f='invoice_046.pdf')", "Quanta Metals, Rs 66,325, due Oct 21"),
        ],
    },
    "3a_thrash_identical_errors": {
        # Verdict is the TRIP TURN, not the final label. The trace legitimately
        # starts as thrash and becomes loop: as the same three tools cycle, the
        # window fills with its own repetitions and action_sim climbs past the
        # ceiling. An agent re-running the same three tools really has become
        # repetitive by then, so the label change is correct, not drift.
        "expect": "thrash",
        "expect_trip_turn": 6,
        "note": "REALISTIC unreachable-target case: byte-identical failure string",
        "expect_trip": True,
        "turns": [
            ("read_file(f='deploy/config.yaml')", "Error: not found"),
            ("grep(pattern='deploy_key')", "Error: not found"),
            ("list_dir(path='deploy/')", "Error: not found"),
            ("read_file(f='deploy/keys.json')", "Error: not found"),
            ("grep(pattern='DEPLOY_KEY')", "Error: not found"),
            ("list_dir(path='deploy/secrets/')", "Error: not found"),
            ("read_file(f='deploy/.env')", "Error: not found"),
        ],
    },
    "3b_thrash_varied_errors": {
        "expect": "thrash",
        "note": (
            "KNOWN MISS, documented not tuned away: lexically varied failure "
            "messages read as new information on short-string embeddings"
        ),
        "expect_trip": False,
        "turns": [
            ("read_file(f='deploy/config.yaml')", "Error: file not found"),
            ("grep(pattern='deploy_key')", "Error: no matches found"),
            ("list_dir(path='deploy/')", "Error: directory not found"),
        ],
    },
}


def run_fixture(encoder: MiniLMEncoder, turns, config: PlateauConfig):
    """Warm on the preamble, then evaluate the fixture turns."""
    detector = Detector(
        encoder=encoder,
        calibrator=Calibrator(novelty_floor=config.novelty_floor),
        config=config,
    )
    for action, observation in PREAMBLE:
        detector.evaluate(action, observation)

    warm_state = {
        "is_warm": detector.calibrator.is_warm,
        "n_productive": detector.calibrator.n,
        "turns_to_warm": detector.calibrator.turns_to_warm,
        "mu": round(detector.calibrator.mu, 6),
        "sigma": round(detector.calibrator.sigma, 6),
        "sim_ceiling": round(detector.calibrator.sim_ceiling, 6),
    }

    readings = []
    trip_turn = None
    for index, (action, observation) in enumerate(turns):
        reading = detector.evaluate(action, observation)
        if reading.is_trip and trip_turn is None:
            trip_turn = index
        readings.append(
            {
                "action": action,
                "observation": observation,
                "action_sim": round(reading.action_sim, 6),
                "obs_novelty": round(reading.obs_novelty, 6),
                "quadrant": reading.quadrant.value,
                "stagnant": reading.stagnant,
                "confident": reading.confident,
                "loop_hits": reading.loop_hits,
                "stall_hits": reading.stall_hits,
                "is_trip": reading.is_trip,
                "sim_ceiling": round(reading.sim_ceiling, 6),
            }
        )
    return warm_state, readings, trip_turn, detector


def main() -> int:
    encoder = MiniLMEncoder().load()
    config = PlateauConfig(novelty_floor=NOVELTY_FLOOR)

    print(f"encoder revision : {encoder.revision}")
    print(f"novelty_floor    : {NOVELTY_FLOOR}  (PROVISIONAL, sweep owns it)\n")

    results = {}
    for name, spec in FIXTURES.items():
        warm_state, readings, trip_turn, detector = run_fixture(
            encoder, spec["turns"], config
        )

        # The fixture's verdict is the label on its LAST turn: the pattern is only
        # established once every turn of it has been seen.
        final = readings[-1]
        expect_trip_turn = spec.get("expect_trip_turn")
        if expect_trip_turn is not None:
            # Trip-turn fixtures are judged on when they fire.
            passed = trip_turn == expect_trip_turn
        else:
            passed = final["quadrant"] == spec["expect"]

        print("=" * 78)
        print(f"{name}   expect: {spec['expect']}")
        print(f"  {spec['note']}")
        print(
            f"  calibrator after preamble: warm={warm_state['is_warm']} "
            f"n={warm_state['n_productive']} turns_to_warm={warm_state['turns_to_warm']} "
            f"mu={warm_state['mu']:.4f} sigma={warm_state['sigma']:.4f}"
        )
        print(
            f"  thresholds: sim_ceiling={warm_state['sim_ceiling']:.4f} "
            f"novelty_floor={NOVELTY_FLOOR}"
        )
        print(
            f"  {'turn':<4} {'action_sim':>11} {'obs_novelty':>12} {'quadrant':>9} "
            f"{'stag':>5} {'conf':>5} {'loop':>5} {'stall':>6} {'trip':>6}"
        )
        for i, reading in enumerate(readings):
            print(
                f"  {i:<4} {reading['action_sim']:>11.4f} {reading['obs_novelty']:>12.4f} "
                f"{reading['quadrant']:>9} {str(reading['stagnant']):>5} "
                f"{str(reading['confident']):>5} {reading['loop_hits']:>5} "
                f"{reading['stall_hits']:>6} {str(reading['is_trip']):>6}"
            )
        expect_trip = spec.get("expect_trip")
        trip_ok = True if expect_trip is None else (trip_turn is not None) == expect_trip
        passed = passed and trip_ok
        trajectory = " -> ".join(
            q for i, q in enumerate(r["quadrant"] for r in readings)
            if i == 0 or q != readings[i - 1]["quadrant"]
        )
        print(f"  quadrant trajectory: {trajectory}")
        print(
            f"  trip turn: {trip_turn}   expected: {expect_trip_turn}   "
            f"final quadrant: {final['quadrant']}  ->  {'PASS' if passed else 'FAIL'}"
        )

        results[name] = {
            "expect": spec["expect"],
            "note": spec["note"],
            "calibrator_after_preamble": warm_state,
            "readings": readings,
            "final_quadrant": final["quadrant"],
            "trip_turn": trip_turn,
            "expect_trip": spec.get("expect_trip"),
            "expect_trip_turn": expect_trip_turn,
            "quadrant_trajectory": trajectory,
            "passed": passed,
        }

    print("=" * 78)
    all_pass = all(r["passed"] for r in results.values())
    counter_demo_ok = results["2_invoice_batch_grind"]["passed"]
    print(f"all {len(results)} fixtures: {'PASS' if all_pass else 'FAIL'}")
    print(f"counter-demo (fixture 2 -> grind): {'HOLDS' if counter_demo_ok else 'BROKEN'}")

    path = ROOT / "metrics.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc["detector_fixtures"] = {
        "encoder": encoder.fingerprint(),
        "novelty_floor": NOVELTY_FLOOR,
        "novelty_floor_status": "PROVISIONAL, pending sweep",
        "preamble_turns": len(PREAMBLE),
        "fixtures": results,
        "all_passed": all_pass,
        "counter_demo_holds": counter_demo_ok,
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote -> {path}  (key: detector_fixtures)")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
