"""§6 fixture pairs -- measure the three canonical readings and record them.

Reports actual action_sim, obs_novelty, and quadrant for:

    1. paraphrase pair, identical results        -> expect loop
    2. invoice batch pair, different records     -> expect grind   (COUNTER-DEMO)
    3. thrash triple, all "not found"            -> expect thrash

A note on why each fixture has a preamble
-----------------------------------------
The quadrant depends on the calibrator's ceiling and thrash floor, and those only
exist once the calibrator is warm. A run that is stuck from turn 0 never warms --
its turns are all gate-rejected -- so the breaker never arms and every reading is
MIDDLE. That is not a fixture artefact, it is a real property worth knowing: the
detector needs to have seen productive work before it can recognise the absence
of it.

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

from plateau.calibrator import NOVELTY_FLOOR, Calibrator  # noqa: E402
from plateau.detector import Detector, PlateauConfig  # noqa: E402
from plateau.encoder import MiniLMEncoder  # noqa: E402

# A productive preamble: varied actions, each returning genuinely new information.
# This is what a healthy agent looks like, and it is what the calibrator learns
# "normal" from.
PREAMBLE = [
    ("list_dir(path='src/')", "src/: auth.py, config.py, models.py, utils.py, api.py"),
    ("read_file(f='src/auth.py')", "def refresh_token(client_id, secret): expires_in=3600"),
    ("grep(pattern='TOKEN_TTL')", "src/config.py:14: TOKEN_TTL = 3600  # seconds"),
    ("read_file(f='src/config.py')", "TOKEN_TTL=3600, RATE_LIMIT=100, GATEWAY='api.internal'"),
    ("run_tests(suite='auth')", "12 passed, 1 failed: test_refresh_rotates_secret"),
    ("read_file(f='tests/test_auth.py')", "assert new_secret != old_secret  # line 88"),
]

FIXTURES = {
    "1_paraphrase_loop": {
        "expect": "loop",
        "note": "same intent reworded, identical results returned",
        "turns": [
            ("search_docs(q='auth token refresh')", "No relevant results found."),
            ("search_docs(q='how do I refresh a token')", "No relevant results found."),
        ],
    },
    "2_invoice_batch_grind": {
        "expect": "grind",
        "note": "COUNTER-DEMO: near-identical actions, genuinely different records",
        "turns": [
            ("extract_text(f='invoice_041.pdf')", "ACME Corp, Rs 84,200, due Aug 12"),
            ("extract_text(f='invoice_042.pdf')", "Vertex Ltd, Rs 19,750, due Aug 30"),
        ],
    },
    "3_thrash_triple": {
        "expect": "thrash",
        "note": "three different tools, none of them finding anything",
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
        "thrash_floor": round(detector.calibrator.thrash_floor, 6),
    }

    readings = []
    for action, observation in turns:
        reading = detector.evaluate(action, observation)
        readings.append(
            {
                "action": action,
                "observation": observation,
                "action_sim": round(reading.action_sim, 6),
                "obs_novelty": round(reading.obs_novelty, 6),
                "quadrant": reading.quadrant.value,
                "is_trip": reading.is_trip,
                "sim_ceiling": round(reading.sim_ceiling, 6),
                "thrash_floor": round(reading.thrash_floor, 6),
            }
        )
    return warm_state, readings, detector


def main() -> int:
    encoder = MiniLMEncoder().load()
    config = PlateauConfig(novelty_floor=NOVELTY_FLOOR)

    print(f"encoder revision : {encoder.revision}")
    print(f"novelty_floor    : {NOVELTY_FLOOR}  (PROVISIONAL, sweep owns it)\n")

    results = {}
    for name, spec in FIXTURES.items():
        warm_state, readings, detector = run_fixture(encoder, spec["turns"], config)

        # The fixture's verdict is the label on its LAST turn: the pattern is only
        # established once every turn of it has been seen.
        final = readings[-1]
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
            f"thrash_floor={warm_state['thrash_floor']:.4f} "
            f"novelty_floor={NOVELTY_FLOOR}"
        )
        print(f"  {'turn':<4} {'action_sim':>11} {'obs_novelty':>12} {'quadrant':>10} {'trip':>6}")
        for i, reading in enumerate(readings):
            print(
                f"  {i:<4} {reading['action_sim']:>11.4f} {reading['obs_novelty']:>12.4f} "
                f"{reading['quadrant']:>10} {str(reading['is_trip']):>6}"
            )
        print(f"  VERDICT: {final['quadrant']}  ->  {'PASS' if passed else 'FAIL'}")

        results[name] = {
            "expect": spec["expect"],
            "note": spec["note"],
            "calibrator_after_preamble": warm_state,
            "readings": readings,
            "final_quadrant": final["quadrant"],
            "passed": passed,
        }

    print("=" * 78)
    all_pass = all(r["passed"] for r in results.values())
    counter_demo_ok = results["2_invoice_batch_grind"]["passed"]
    print(f"all three fixtures: {'PASS' if all_pass else 'FAIL'}")
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
