"""Every detector against real agent traces. Writes metrics.json -> trail_comparison.

This is the first number in the project that is about real agent behaviour.
Everything else -- the §6 fixtures, the sweep, the five long-trace classes -- is
hand-written by us, which means it can only ever confirm what we already
believed when we wrote it.

Mirrors scripts/long_trace_comparison.py exactly: same detector registry, same
recall / false-trip / turns-to-detection, so the synthetic and real tables are
directly comparable. What it adds is honesty machinery around the two judgement
calls in eval/trail.py -- results are reported for every span mode and every
category mapping, not just the flattering one.

    hf auth login
    python scripts/fetch_trail.py
    python scripts/trail_comparison.py

Nothing from data/trail/ is written into metrics.json except aggregate counts,
span counts and category names. The dataset is gated and must not be reshared.
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
from eval.trail import (  # noqa: E402
    DATASET_NOTE,
    RAW_TO_CANONICAL,
    REPAIRED,
    DEFAULT_MAPPING,
    MAPPINGS,
    MAX_TEXT_CHARS,
    SPAN_MODES,
    load_trail,
    observed_categories,
)
from plateau.calibrator import Calibrator  # noqa: E402
from plateau.detector import Detector, PlateauConfig  # noqa: E402
from plateau.encoder import MiniLMEncoder  # noqa: E402

#: A detector that needs `trip_after_stall` consecutive stagnant turns cannot
#: fire on a trace shorter than that, so including such traces would report
#: trace length as detector recall -- the exact mistake the §6 sweep made with
#: its two-turn fixtures. Traces below this are counted and excluded, and the
#: count is published.
MIN_TURNS = 8


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


def build_detectors(encoder):
    return {
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


def score(trips: dict[str, int | None], labels: dict[str, bool]) -> dict:
    """Recall / false-trip / mean turns-to-detection over one set of traces."""
    positives = [n for n, should in labels.items() if should]
    negatives = [n for n, should in labels.items() if not should]
    detected = [n for n in positives if trips[n] is not None]
    false_trips = [n for n in negatives if trips[n] is not None]
    return {
        "n_positive": len(positives),
        "n_negative": len(negatives),
        "recall": round(len(detected) / len(positives), 4) if positives else None,
        "false_trip_rate": (
            round(len(false_trips) / len(negatives), 4) if negatives else None
        ),
        "n_detected": len(detected),
        "n_false_trips": len(false_trips),
        "mean_turns_to_detection": (
            round(sum(trips[n] for n in detected) / len(detected), 2)
            if detected
            else None
        ),
    }


def main() -> int:
    encoder = MiniLMEncoder().load()
    detectors = build_detectors(encoder)

    results: dict[str, dict] = {}
    corpus: dict[str, dict] = {}

    for mode in SPAN_MODES:
        traces = load_trail(mode=mode)
        if not traces:
            print("no TRAIL traces found -- run scripts/fetch_trail.py first")
            return 1

        usable = {n: t for n, t in traces.items() if len(t.turns) >= MIN_TURNS}
        corpus[mode] = {
            "n_traces": len(traces),
            "n_usable": len(usable),
            "n_excluded_too_short": len(traces) - len(usable),
            "min_turns_required": MIN_TURNS,
            "turns_per_trace": {
                "min": min((len(t.turns) for t in traces.values()), default=0),
                "median": sorted(len(t.turns) for t in traces.values())[
                    len(traces) // 2
                ],
                "max": max((len(t.turns) for t in traces.values()), default=0),
            },
            "by_split": {
                split: sum(1 for t in usable.values() if t.split == split)
                for split in sorted({t.split for t in traces.values()})
            },
        }

        print(f"\n{'=' * 78}\nspan mode: {mode}\n{'=' * 78}")
        print(
            f"{len(traces)} traces, {len(usable)} with >= {MIN_TURNS} turns "
            f"({len(traces) - len(usable)} excluded as too short to trip)"
        )
        if not usable:
            print("nothing long enough to evaluate in this mode")
            results[mode] = {}
            continue

        # One pass per detector over the usable traces; the labels change with
        # the mapping but the trips do not, so detectors run once.
        trips = {
            label: {n: run(t.turns) for n, t in usable.items()}
            for label, run in detectors.items()
        }

        per_mapping = {}
        for mapping in MAPPINGS:
            labels = {n: t.should_trip(mapping) for n, t in usable.items()}
            splits = sorted({t.split for t in usable.values()})
            rows = {}
            for label in detectors:
                rows[label] = {
                    "all": score(trips[label], labels),
                    **{
                        split: score(
                            {
                                n: trips[label][n]
                                for n in usable
                                if usable[n].split == split
                            },
                            {n: labels[n] for n in usable if usable[n].split == split},
                        )
                        for split in splits
                    },
                }
            per_mapping[mapping] = {
                "categories": sorted(MAPPINGS[mapping]),
                "n_positive": sum(labels.values()),
                "n_negative": len(labels) - sum(labels.values()),
                "detectors": rows,
                "perfect_detectors": [
                    label
                    for label, r in rows.items()
                    if r["all"]["recall"] == 1.0 and r["all"]["false_trip_rate"] == 0.0
                ],
            }

            marker = "  <- quoted in the README" if mapping == DEFAULT_MAPPING else ""
            print(f"\nmapping '{mapping}'{marker}")
            print(
                f"  positives {sum(labels.values())}, "
                f"negatives {len(labels) - sum(labels.values())}"
            )
            head = f"  {'detector':<22}{'recall':>8}{'false-trip':>12}{'mean TTD':>10}"
            print(head)
            print("  " + "-" * (len(head) - 2))
            for label, r in rows.items():
                a = r["all"]
                ttd = "-" if a["mean_turns_to_detection"] is None else f"{a['mean_turns_to_detection']:.1f}"
                rec = "-" if a["recall"] is None else f"{a['recall']:.2f}"
                fal = "-" if a["false_trip_rate"] is None else f"{a['false_trip_rate']:.2f}"
                print(f"  {label:<22}{rec:>8}{fal:>12}{ttd:>10}")
            print(f"  recall 1.00 with zero false trips: "
                  f"{per_mapping[mapping]['perfect_detectors'] or 'NONE'}")

        results[mode] = per_mapping

    categories = observed_categories(load_trail(mode="tool"))

    path = ROOT / "metrics.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc["trail_comparison"] = {
        "encoder": encoder.fingerprint(),
        "dataset": DATASET_NOTE,
        "scope_note": (
            "REAL agent traces, not hand-written: GAIA via OpenDeepResearch on "
            "o3-mini, SWE-Bench Lite via CodeAct on claude-3-7-sonnet, captured "
            "as OpenInference spans and annotated by four experts. The two "
            "judgement calls -- which spans are turns, and which error "
            "categories mean 'should have tripped' -- are ours, not TRAIL's, "
            "and every variant of both is reported here rather than only the "
            "one that flatters us."
        ),
        "max_text_chars": MAX_TEXT_CHARS,
        "span_modes": {k: list(v) for k, v in SPAN_MODES.items()},
        "mappings": {k: sorted(v) for k, v in MAPPINGS.items()},
        "default_mapping": DEFAULT_MAPPING,
        "observed_categories": categories,
        "raw_to_canonical": dict(sorted(RAW_TO_CANONICAL.items())),
        "repaired_source_files": dict(REPAIRED),
        "corpus": corpus,
        "results": results,
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote -> {path}  (key: trail_comparison)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
