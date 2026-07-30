"""RETIRED. Kept for the record; superseded by the §6 revision.

This script isolated why fixtures 1 and 3 landed in MIDDLE under the ORIGINAL §6,
which had a `thrash_floor` derived from `mu - k*sigma`. Its finding -- that the
clamp saturated at both ends and the MIDDLE band swallowed everything -- is what
motivated removing the thrash floor entirely and moving the trip axis onto
novelty. See metrics.json -> fixture_diagnosis for the numbers it produced.

It no longer runs: `Calibrator.thrash_floor` and `Quadrant.MIDDLE` are both gone.
Live fixture measurement is now scripts/detector_fixtures.py, and parameter
exploration belongs in eval/sweep.py.

Original docstring follows.
=============================================================================

Why fixtures 1 and 3 fail: is it k_sigma, the clamps, or the fixtures?

Fixtures 1 (paraphrase -> loop) and 3 (thrash) both landed in MIDDLE. This
isolates the cause by sweeping the one parameter that sets the width of the
MIDDLE band -- k_sigma -- and by varying the preamble that sets mu and sigma.

Diagnostic only. Writes metrics.json -> fixture_diagnosis. Changes no defaults.

    python scripts/fixture_diagnosis.py
"""

from __future__ import annotations

raise SystemExit(
    "scripts/fixture_diagnosis.py is RETIRED: it measures Calibrator.thrash_floor "
    "and Quadrant.MIDDLE, both removed by the §6 revision. Its results are "
    "preserved in metrics.json -> fixture_diagnosis. Use "
    "scripts/detector_fixtures.py for live fixture readings."
)

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
from scripts.detector_fixtures import FIXTURES, PREAMBLE  # noqa: E402

# A second preamble: a homogeneous agent doing similar work each turn. Low sigma,
# so the MIDDLE band should be much narrower.
PREAMBLE_HOMOGENEOUS = [
    ("read_file(f='src/auth.py')", "def refresh_token(client_id, secret): expires_in=3600"),
    ("read_file(f='src/config.py')", "TOKEN_TTL=3600, RATE_LIMIT=100, GATEWAY='api.internal'"),
    ("read_file(f='src/models.py')", "class User(Base): id, email, created_at, tenant_id"),
    ("read_file(f='src/api.py')", "@app.post('/login') async def login(body: LoginRequest)"),
    ("read_file(f='src/utils.py')", "def backoff(attempt): return min(2 ** attempt, 60)"),
    ("read_file(f='tests/test_auth.py')", "assert new_secret != old_secret  # line 88"),
]

PREAMBLES = {"heterogeneous": PREAMBLE, "homogeneous": PREAMBLE_HOMOGENEOUS}
K_SIGMAS = [0.5, 1.0, 1.5, 2.0]


def evaluate(encoder, preamble, turns, k_sigma):
    calibrator = Calibrator(novelty_floor=NOVELTY_FLOOR, k_sigma=k_sigma)
    detector = Detector(
        encoder=encoder, calibrator=calibrator, config=PlateauConfig(novelty_floor=NOVELTY_FLOOR)
    )
    for action, observation in preamble:
        detector.evaluate(action, observation)
    band = (calibrator.thrash_floor, calibrator.sim_ceiling)
    readings = [detector.evaluate(a, o) for a, o in turns]
    return band, calibrator, readings[-1]


def main() -> int:
    encoder = MiniLMEncoder().load()
    rows = []

    for preamble_name, preamble in PREAMBLES.items():
        for k_sigma in K_SIGMAS:
            for fixture_name, spec in FIXTURES.items():
                band, calibrator, final = evaluate(
                    encoder, preamble, spec["turns"], k_sigma
                )
                rows.append(
                    {
                        "preamble": preamble_name,
                        "k_sigma": k_sigma,
                        "fixture": fixture_name,
                        "expect": spec["expect"],
                        "got": final.quadrant.value,
                        "passed": final.quadrant.value == spec["expect"],
                        "mu": round(calibrator.mu, 4),
                        "sigma": round(calibrator.sigma, 4),
                        "thrash_floor": round(band[0], 4),
                        "sim_ceiling": round(band[1], 4),
                        "middle_band_width": round(band[1] - band[0], 4),
                        "action_sim": round(final.action_sim, 4),
                        "obs_novelty": round(final.obs_novelty, 4),
                    }
                )

    header = (
        f"{'preamble':<15} {'k':>4} {'fixture':<24} {'expect':>7} {'got':>7} "
        f"{'band':>15} {'a_sim':>7} {'nov':>7}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        band = f"[{row['thrash_floor']:.3f},{row['sim_ceiling']:.3f}]"
        mark = "" if row["passed"] else "  <-- FAIL"
        print(
            f"{row['preamble']:<15} {row['k_sigma']:>4} {row['fixture']:<24} "
            f"{row['expect']:>7} {row['got']:>7} {band:>15} "
            f"{row['action_sim']:>7.4f} {row['obs_novelty']:>7.4f}{mark}"
        )

    print("\nconfigurations where ALL THREE fixtures pass:")
    combos = {}
    for row in rows:
        combos.setdefault((row["preamble"], row["k_sigma"]), []).append(row["passed"])
    winners = [key for key, passes in combos.items() if all(passes)]
    for preamble_name, k_sigma in winners:
        print(f"    preamble={preamble_name}  k_sigma={k_sigma}")
    if not winners:
        print("    NONE")

    print("\nper-fixture pass count across all 8 configurations:")
    for fixture_name in FIXTURES:
        n = sum(1 for row in rows if row["fixture"] == fixture_name and row["passed"])
        print(f"    {fixture_name:<24} {n}/8")

    path = ROOT / "metrics.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc["fixture_diagnosis"] = {
        "purpose": "isolate why fixtures 1 and 3 land in MIDDLE at k_sigma=2.0",
        "note": "diagnostic sweep; changes no defaults",
        "k_sigmas": K_SIGMAS,
        "rows": rows,
        "all_pass_configurations": [
            {"preamble": p, "k_sigma": k} for p, k in winners
        ],
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote -> {path}  (key: fixture_diagnosis)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
