"""All detectors over all four full-length trace classes.

The §6 fixtures are 2-7 turns and can only validate classification. These traces
are 30-61 turns, so turns-to-detection and false-trip rate are meaningful.

SCOPE NOTE: the four trace classes in eval/traces.py were defined here, not
handed down in §9, and they are hand-written rather than captured. They are a
stand-in so detection can be measured at all — the non-synthetic traces come
from TRAIL, which is gated and downloaded by a human. Replace or extend the
classes and this script re-runs unchanged.

Writes metrics.json -> long_trace_comparison.

    python scripts/long_trace_comparison.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["HF_HUB_OFFLINE"] = "1"

from eval.baselines import BaselineTurn  # noqa: E402
from eval.baselines.exact_args import detect as exact_args_detect  # noqa: E402
from eval.baselines.exact_match import detect as exact_match_detect  # noqa: E402
from eval.baselines.lexical import detect as lexical_detect  # noqa: E402
from eval.baselines.step_cap import (  # noqa: E402
    RECURSION_LIMIT_DOCUMENTED,
    RECURSION_LIMIT_SOURCE,
    detect as step_cap_detect,
)
from eval.traces import TRACES  # noqa: E402
from plateau.calibrator import Calibrator  # noqa: E402
from plateau.detector import Detector, PlateauConfig  # noqa: E402
from plateau.encoder import MiniLMEncoder  # noqa: E402


def as_baseline_turns(trace):
    return [
        BaselineTurn(
            action_name=action.split("(")[0],
            action_input={"raw": action},
            observation=observation,
            is_error=observation.lower().startswith("error"),
        )
        for action, observation in trace
    ]


def plateau_run(encoder, trace, config: PlateauConfig) -> int | None:
    detector = Detector(
        encoder=encoder,
        calibrator=Calibrator(novelty_floor=config.novelty_floor),
        config=config,
    )
    return detector.run(trace)


def main() -> int:
    encoder = MiniLMEncoder().load()

    detectors = {
        "plateau": lambda t: plateau_run(encoder, t, PlateauConfig()),
        "plateau_action_only": lambda t: plateau_run(
            encoder, t, PlateauConfig(action_only=True)
        ),
        "plateau_novelty_only": lambda t: plateau_run(
            encoder, t, PlateauConfig(novelty_only=True)
        ),
        "exact_match": lambda t: exact_match_detect(as_baseline_turns(t)),
        "exact_args": lambda t: exact_args_detect(as_baseline_turns(t)),
        "lexical": lambda t: lexical_detect(as_baseline_turns(t)),
        "step_cap_25": lambda t: step_cap_detect(
            as_baseline_turns(t), recursion_limit=RECURSION_LIMIT_DOCUMENTED
        ),
        "step_cap_10007": lambda t: step_cap_detect(
            as_baseline_turns(t), recursion_limit=RECURSION_LIMIT_SOURCE
        ),
    }

    names = list(TRACES)
    print(f"trace lengths: " + ", ".join(f"{n}={len(TRACES[n][0])}" for n in names))
    print(f"ground truth : " + ", ".join(f"{n}={'TRIP' if TRACES[n][1] else 'HOLD'}" for n in names))
    print()

    header = f"{'detector':<22}" + "".join(f"{n[:20]:>22}" for n in names)
    print(header)
    print("-" * len(header))

    results = {}
    for label, run in detectors.items():
        row = {}
        cells = ""
        for name in names:
            trace, should_trip = TRACES[name]
            trip = run(trace)
            row[name] = trip
            if should_trip:
                mark = "ok" if trip is not None else "MISS"
            else:
                mark = "FALSE-TRIP" if trip is not None else "ok"
            cells += f"{(str(trip) if trip is not None else '---') + ' ' + mark:>22}"
        print(f"{label:<22}{cells}")

        positives = [n for n in names if TRACES[n][1]]
        negatives = [n for n in names if not TRACES[n][1]]
        detected = [n for n in positives if row[n] is not None]
        false_trips = [n for n in negatives if row[n] is not None]
        results[label] = {
            "detection_turn_index": row,
            "recall": len(detected) / len(positives),
            "false_trip_rate": len(false_trips) / len(negatives),
            "missed": [n for n in positives if row[n] is None],
            "false_trips": false_trips,
            "mean_turns_to_detection": (
                round(sum(row[n] for n in detected) / len(detected), 2) if detected else None
            ),
        }

    print()
    summary = f"{'detector':<22}{'recall':>8}{'false-trip':>12}{'mean TTD':>10}"
    print(summary)
    print("-" * len(summary))
    for label, r in results.items():
        ttd = "-" if r["mean_turns_to_detection"] is None else f"{r['mean_turns_to_detection']:.1f}"
        print(f"{label:<22}{r['recall']:>8.2f}{r['false_trip_rate']:>12.2f}{ttd:>10}")

    print()
    perfect = [
        label for label, r in results.items()
        if r["recall"] == 1.0 and r["false_trip_rate"] == 0.0
    ]
    print(f"recall 1.00 with zero false trips: {perfect or 'NONE'}")

    path = ROOT / "metrics.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc["long_trace_comparison"] = {
        "encoder": encoder.fingerprint(),
        "scope_note": (
            "trace classes are hand-written and defined in eval/traces.py, not "
            "handed down in §9; non-synthetic traces come from TRAIL (gated, "
            "human-downloaded, never committed)"
        ),
        "traces": {
            name: {"turns": len(TRACES[name][0]), "should_trip": TRACES[name][1]}
            for name in names
        },
        "detectors": results,
        "perfect_detectors": perfect,
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote -> {path}  (key: long_trace_comparison)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
