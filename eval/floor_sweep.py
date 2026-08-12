"""Where is the *upper* edge of the novelty floor, and does the floor decide anything?

This is the third sweep in the repository, and it exists because the other two
share a blind spot.

`eval/sweep.py` (576 configs, §6 fixtures) and `scripts/long_trace_sweep.py`
(576 configs, the 16-61 turn classes) both sweep `novelty_floor` over
[0.25, 0.30, 0.35, 0.40], and both report every value in that range usable. The
README draws the honest conclusion -- "neither sweep discriminates" -- and falls
back on `novelty_floor_probe`, which bounds the floor from a 16-observation
sample rather than from end-to-end behaviour.

That agreement is an artifact of the range. A floor of 0.40 is still below the
bottom of the measured batch band's *upper* half, so of course nothing breaks.
This sweep runs the same five axes with the floor pushed to 0.80, which is where
a floor is supposed to start condemning healthy work, and reports the edge.

**What this can say that the other two cannot:**

* the largest floor at which any configuration is still usable,
* the smallest floor at which every configuration false-trips,
* and therefore the actual width of the floor's usable range, rather than
  "all four grid values passed".

**What it cannot say.** It does not re-decide `window_size` -- `long_trace_sweep`
already did, and this sweep reproduces that axis only so the floor's edge is
measured at every window rather than at one hard-coded value. If the floor's
usable range turns out to depend on the window, that is a finding; if it does
not, the floor is independent of the parameter that actually decides the
outcome, and that is a finding too.

Honours the per-tool `idempotent: true` declaration, exactly as
`scripts/long_trace_sweep.py` does and exactly as the shipped breaker does, so
`healthy_poller` is scored as the ordinary negative it is. Whether it *would*
have tripped undeclared is recorded per configuration as
`poller_trips_undeclared`: a poller is genuinely informationally stalled, so
tripping on it is correct behaviour that the declaration exists to suppress, and
that number is the size of the burden the declaration carries.

    python eval/floor_sweep.py
    python eval/floor_sweep.py --fine

Writes metrics.json -> floor_sweep (coarse) and floor_sweep_fine (--fine).
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
from plateau.calibrator import NOVELTY_FLOOR, Calibrator  # noqa: E402
from plateau.detector import (  # noqa: E402
    TRIP_AFTER_LOOP,
    TRIP_AFTER_STALL,
    WINDOW_SIZE,
    Detector,
    PlateauConfig,
)
from plateau.encoder import MiniLMEncoder  # noqa: E402

#: The trace whose idempotent declaration is the thing under observation.
POLLER = "healthy_poller"

AXES = ("novelty_floor", "k_sigma", "trip_after_loop", "trip_after_stall", "window_size")

#: 0.25 is in the grid because it is the committed floor. A sweep that steps
#: 0.20, 0.30, ... cannot say whether the configuration this repository actually
#: ships is usable, which is the first question anyone reading it will have.
NOVELTY_FLOORS = [0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
K_SIGMAS = [0.5, 1.0, 1.5]
TRIP_AFTER_LOOPS = [2, 3, 4]
TRIP_AFTER_STALLS = [4, 6, 8]
#: Reproduced from scripts/long_trace_sweep.py so the floor's edge is measured
#: at every window. This sweep does not re-decide the axis; see module docstring.
WINDOW_SIZES = [8, 12, 16, 24]

#: --fine: the coarse grid steps by 0.10, so whichever floor it reports as the
#: edge is only located to within a tenth. The coarse run puts the edge between
#: 0.40 and 0.60 -- usable at 0.50 for windows 8 and 12, already lost at 0.50 for
#: windows 16 and 24 -- so this resolves that span at 0.02, which is the
#: resolution the width is actually being quoted at. Re-set the range if the
#: coarse edge moves.
FINE_NOVELTY_FLOORS = [round(0.40 + 0.02 * i, 2) for i in range(11)]
FINE_K_SIGMAS = K_SIGMAS
#: Held at the committed default: the coarse sweep reports this axis not
#: load-bearing, so spending fine-grid runtime on it would buy nothing.
FINE_TRIP_AFTER_LOOPS = [TRIP_AFTER_LOOP]
FINE_TRIP_AFTER_STALLS = TRIP_AFTER_STALLS
FINE_WINDOW_SIZES = WINDOW_SIZES


def run_one(encoder, floor, k_sigma, tl, ts, window, *, honour_idempotent=True):
    """Trip turn per trace for one configuration, or None where it never trips."""
    config = PlateauConfig(
        novelty_floor=floor,
        trip_after_loop=tl,
        trip_after_stall=ts,
        window_size=window,
    )
    trips = {}
    for name, (trace, _) in TRACES.items():
        detector = Detector(
            encoder=encoder,
            calibrator=Calibrator(novelty_floor=floor, k_sigma=k_sigma),
            config=config,
        )
        declared = IDEMPOTENT_TOOLS.get(name, frozenset()) if honour_idempotent else ()
        trips[name] = detector.run(trace, idempotent_tools=declared)
    return trips


def main() -> int:
    fine = "--fine" in sys.argv
    floors = FINE_NOVELTY_FLOORS if fine else NOVELTY_FLOORS
    k_sigmas = FINE_K_SIGMAS if fine else K_SIGMAS
    loops = FINE_TRIP_AFTER_LOOPS if fine else TRIP_AFTER_LOOPS
    stalls = FINE_TRIP_AFTER_STALLS if fine else TRIP_AFTER_STALLS
    windows = FINE_WINDOW_SIZES if fine else WINDOW_SIZES
    key = "floor_sweep_fine" if fine else "floor_sweep"

    encoder = MemoEncoder(MiniLMEncoder().load())

    names = list(TRACES)
    positives = [n for n in names if TRACES[n][1]]
    negatives = [n for n in names if not TRACES[n][1]]

    combos = list(itertools.product(floors, k_sigmas, loops, stalls, windows))
    print(f"grid: {len(combos)} configurations over {len(names)} full-length traces")
    print(f"positives (must trip): {positives}")
    print(f"negatives (must hold): {negatives}")
    print(f"idempotent declarations honoured: {sorted(IDEMPOTENT_TOOLS)}\n")

    rows = []
    for floor, k_sigma, tl, ts, window in combos:
        trips = run_one(encoder, floor, k_sigma, tl, ts, window)
        undeclared = run_one(
            encoder, floor, k_sigma, tl, ts, window, honour_idempotent=False
        )
        detected = [n for n in positives if trips[n] is not None]
        false_trips = [n for n in negatives if trips[n] is not None]
        rows.append(
            {
                "novelty_floor": floor,
                "k_sigma": k_sigma,
                "trip_after_loop": tl,
                "trip_after_stall": ts,
                "window_size": window,
                "trips": trips,
                "recall": len(detected) / len(positives),
                "false_trip_rate": len(false_trips) / len(negatives),
                "missed": [n for n in positives if trips[n] is None],
                "false_trips": false_trips,
                "usable": len(detected) == len(positives) and not false_trips,
                "poller_trips_undeclared": undeclared[POLLER] is not None,
            }
        )

    # Per-floor envelope: the headline question is about the floor.
    print(f"{'floor':>6} {'best recall':>12} {'min false-trip':>15} {'usable cfgs':>12}")
    print("-" * 50)
    per_floor = {}
    for floor in floors:
        at = [r for r in rows if r["novelty_floor"] == floor]
        best_recall = max(r["recall"] for r in at)
        min_ft = min(r["false_trip_rate"] for r in at)
        usable = [r for r in at if r["usable"]]
        per_floor[str(floor)] = {
            "best_recall": best_recall,
            "min_false_trip_rate": min_ft,
            "n_usable": len(usable),
            "n_configs": len(at),
        }
        print(f"{floor:>6.2f} {best_recall:>12.2f} {min_ft:>15.2f} {len(usable):>12}")

    usable_rows = [r for r in rows if r["usable"]]
    print()
    print(f"usable configurations (recall 1.00, zero false trips): {len(usable_rows)}")

    # The edge. This is the number the other two sweeps cannot produce.
    usable_floors = sorted({r["novelty_floor"] for r in usable_rows})
    edge = {
        "highest_usable_floor": max(usable_floors) if usable_floors else None,
        "lowest_usable_floor": min(usable_floors) if usable_floors else None,
        "usable_floor_span": (
            round(max(usable_floors) - min(usable_floors), 4) if usable_floors else None
        ),
        "lowest_floor_with_no_usable_config": next(
            (
                f
                for f in floors
                if usable_floors and f > max(usable_floors)
            ),
            None,
        ),
        "swept_floor_range": [min(floors), max(floors)],
    }
    print(
        f"floor edge: usable from {edge['lowest_usable_floor']} to "
        f"{edge['highest_usable_floor']} "
        f"(span {edge['usable_floor_span']}); first floor with nothing usable: "
        f"{edge['lowest_floor_with_no_usable_config']}"
    )

    window = {}
    if usable_rows:
        for axis in AXES:
            values = sorted({r[axis] for r in usable_rows})
            all_values = sorted({r[axis] for r in rows})
            window[axis] = {
                "usable_values": values,
                # Rounded: these are grid coordinates, and 0.48 - 0.40 in binary
                # floating point is 0.07999999999999996, which is not a width
                # anyone should read in a report.
                "width": round(max(values) - min(values), 6),
                "n": len(values),
                "is_load_bearing": len(values) < len(all_values),
            }
        print("\nusable threshold window, per axis:")
        for axis, info in window.items():
            flag = "  <- LOAD-BEARING" if info["is_load_bearing"] else ""
            print(f"    {axis:<18} {info['usable_values']}  width={info['width']}{flag}")
    else:
        print("\nNO configuration in this grid catches every stall without a false trip.")

    # Which positives are unreachable at any setting?
    never = {name: sum(1 for r in rows if name in r["missed"]) for name in positives}
    print("\npositives missed, by configuration count:")
    for name, count in sorted(never.items(), key=lambda kv: -kv[1]):
        flag = "  <-- MISSED IN EVERY CONFIG" if count == len(rows) else ""
        print(f"    {name:<34} {count}/{len(rows)}{flag}")

    false_by_trace: dict[str, int] = {}
    for r in rows:
        for name in r["false_trips"]:
            false_by_trace[name] = false_by_trace.get(name, 0) + 1
    print("\nnegatives false-tripped, by configuration count:")
    for name in negatives:
        print(f"    {name:<34} {false_by_trace.get(name, 0)}/{len(rows)}")

    n_poller_undeclared = sum(1 for r in rows if r["poller_trips_undeclared"])
    print(
        f"\nhealthy_poller would trip undeclared in {n_poller_undeclared}/{len(rows)} "
        f"configurations — the size of the burden the declaration carries."
    )

    # The floor's edge, per window. If the two axes are independent, every row
    # here is the same; if a higher floor buys back a window too short to see the
    # repetition, they are not, and that interaction is the point of sweeping
    # both together rather than one at a time.
    print("\nfloor edge, per window size:")
    edge_by_window = {}
    for w in windows:
        at_usable = sorted(
            {r["novelty_floor"] for r in usable_rows if r["window_size"] == w}
        )
        at_recall = sorted(
            {
                r["novelty_floor"]
                for r in rows
                if r["window_size"] == w and r["recall"] == 1.0
            }
        )
        edge_by_window[str(w)] = {
            "usable_floors": at_usable,
            "highest_usable_floor": max(at_usable) if at_usable else None,
            "floors_reaching_full_recall": at_recall,
            "lowest_floor_at_full_recall": min(at_recall) if at_recall else None,
        }
        print(
            f"    window={w:<3} usable floors {at_usable}  "
            f"full recall from floor {min(at_recall) if at_recall else None}"
        )

    # Is the shipped configuration inside the usable set this sweep measured?
    committed = {
        "novelty_floor": NOVELTY_FLOOR,
        "trip_after_loop": TRIP_AFTER_LOOP,
        "trip_after_stall": TRIP_AFTER_STALL,
        "window_size": WINDOW_SIZE,
    }
    committed_rows = [
        r for r in rows if all(r[axis] == value for axis, value in committed.items())
    ]
    committed_usable = [r for r in committed_rows if r["usable"]]
    committed_status = {
        "config": committed,
        "in_grid": bool(committed_rows),
        "n_rows_at_committed": len(committed_rows),
        "n_usable_at_committed": len(committed_usable),
        "usable_at_every_k_sigma": bool(committed_rows)
        and len(committed_usable) == len(committed_rows),
    }
    if committed_rows:
        print(
            f"\ncommitted defaults {committed}: usable in "
            f"{len(committed_usable)}/{len(committed_rows)} of the swept k_sigma values"
        )
    else:
        print(f"\ncommitted defaults {committed} are not on this grid")

    path = ROOT / "metrics.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc[key] = {
        "encoder": encoder.fingerprint(),
        "question": (
            "where is the upper edge of the novelty floor's usable range, which "
            "neither eval/sweep.py nor scripts/long_trace_sweep.py can see "
            "because both stop at 0.40"
        ),
        "idempotent_declarations_honoured": {
            name: sorted(tools) for name, tools in IDEMPOTENT_TOOLS.items()
        },
        "idempotent_rationale": (
            "a poller is genuinely informationally stalled; tripping on it is "
            "correct and is suppressed by the required idempotent declaration. "
            "poller_trips_undeclared records how often it would have tripped "
            "without it, which is the size of that burden"
        ),
        "grid": {
            "novelty_floor": floors,
            "k_sigma": k_sigmas,
            "trip_after_loop": loops,
            "trip_after_stall": stalls,
            "window_size": windows,
        },
        "positives": positives,
        "negatives": negatives,
        "per_floor": per_floor,
        "n_configs": len(rows),
        "n_usable_configs": len(usable_rows),
        "floor_edge": edge,
        "floor_edge_by_window": edge_by_window,
        "committed_defaults": committed_status,
        "usable_window": window,
        "positives_missed_counts": never,
        "negatives_false_tripped_counts": {
            n: false_by_trace.get(n, 0) for n in negatives
        },
        "poller_trips_undeclared_count": n_poller_undeclared,
        "scope_note": (
            "Run on the 16-61 turn classes in eval/traces.py. Sweeps the same "
            "five axes as scripts/long_trace_sweep.py but pushes novelty_floor "
            "to 0.80 instead of stopping at 0.40. It does not re-decide "
            "window_size; that axis is reproduced so the floor's edge is "
            "measured at every window rather than at one hard-coded value."
        ),
        "results": {
            f"f{r['novelty_floor']}_k{r['k_sigma']}_tl{r['trip_after_loop']}"
            f"_ts{r['trip_after_stall']}_w{r['window_size']}": r
            for r in rows
        },
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote -> {path}  (key: {key})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
