"""Record what the §5 calibrator actually converges to on each trace shape.

C4 asserts that a batch trace and a research trace reach *measurably different*
ceilings. That assertion is only meaningful if the actual numbers are on record,
so this writes them to metrics.json rather than leaving them inside a test.

Pure arithmetic, no encoder, no network.

    python scripts/calibrator_profile.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from plateau.calibrator import HARD_HI, HARD_LO, Calibrator  # noqa: E402

# Synthetic action-similarity streams standing in for two trace shapes. Labelled
# synthetic because they are: the real per-class numbers come from the harness
# once TRAIL traces are available.
PROFILES = {
    "batch_tight": [0.97, 0.96, 0.98, 0.97, 0.95, 0.98, 0.97, 0.96, 0.97, 0.98],
    "batch_invoice_gate1": [0.9913] * 10,  # gate 1 measured this pair at 0.9913
    "research_open_ended": [0.30, 0.45, 0.22, 0.51, 0.38, 0.29, 0.47, 0.33, 0.41, 0.36],
    "mixed": [0.30, 0.92, 0.41, 0.88, 0.35, 0.90, 0.44, 0.87, 0.39, 0.91],
}


def profile(sims: list[float], novelty: float = 0.60) -> dict[str, object]:
    cal = Calibrator()
    for sim in sims:
        cal.update(action_sim=sim, obs_novelty=novelty)
    raw = cal.mu + cal.k_sigma * cal.sigma
    return {
        "n_productive": cal.n,
        "mu": round(cal.mu, 6),
        "sigma": round(cal.sigma, 6),
        "raw_ceiling": round(raw, 6),
        "sim_ceiling": round(cal.sim_ceiling, 6),
        "thrash_floor": round(cal.thrash_floor, 6),
        "clamp_engaged": bool(raw > HARD_HI or raw < HARD_LO),
        "own_max_sim_exceeds_ceiling": bool(max(sims) > cal.sim_ceiling),
    }


def main() -> int:
    results = {name: profile(sims) for name, sims in PROFILES.items()}

    print(f"{'profile':<22} {'mu':>8} {'sigma':>8} {'raw':>8} {'ceil':>8} {'thrash':>8} {'clamp':>6}")
    print("-" * 76)
    for name, r in results.items():
        print(
            f"{name:<22} {r['mu']:>8.4f} {r['sigma']:>8.4f} {r['raw_ceiling']:>8.4f} "
            f"{r['sim_ceiling']:>8.4f} {r['thrash_floor']:>8.4f} {str(r['clamp_engaged']):>6}"
        )

    spread = results["batch_tight"]["sim_ceiling"] - results["research_open_ended"]["sim_ceiling"]
    print(f"\nC4 adaptation spread (batch ceiling - research ceiling) = {spread:.4f}")

    pinned = [n for n, r in results.items() if r["own_max_sim_exceeds_ceiling"]]
    print(f"profiles whose own similarity exceeds their ceiling: {pinned or 'none'}")

    path = ROOT / "metrics.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc["calibrator_profile"] = {
        "source": "synthetic action-similarity streams; real per-class values pending harness",
        "novelty_floor_used": Calibrator().novelty_floor,
        "novelty_floor_status": "placeholder pending sweep",
        "hard_clamps": [HARD_LO, HARD_HI],
        "profiles": results,
        "c4_adaptation_spread": round(spread, 6),
        "profiles_pinned_above_ceiling": pinned,
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote -> {path}  (key: calibrator_profile)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
