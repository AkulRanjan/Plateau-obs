"""Six-baseline comparison across all four fixtures.

Runs full Plateau, action_only, novelty_only, and the four ported baselines
on every fixture and produces a uniform results table.

    .venv\Scripts\python scripts/baseline_comparison.py

Writes metrics.json -> baseline_comparison.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["HF_HUB_OFFLINE"] = "1"

from plateau.calibrator import Calibrator  # noqa: E402
from plateau.detector import Detector, PlateauConfig  # noqa: E402
from plateau.encoder import MiniLMEncoder  # noqa: E402
from scripts.detector_fixtures import FIXTURES, PREAMBLE  # noqa: E402

from eval.baselines import BaselineTurn  # noqa: E402
from eval.baselines.exact_args import detect as exact_args_detect  # noqa: E402
from eval.baselines.step_cap import detect as step_cap_detect  # noqa: E402
from eval.baselines.exact_match import detect as exact_match_detect  # noqa: E402
from eval.baselines.lexical import detect as lexical_detect  # noqa: E402


def parse_action(action_text: str) -> tuple[str, dict]:
    """Parse 'read_file(f='deploy/config.yaml')' into ('read_file', {'f': '...'})."""
    m = re.match(r"(\w+)\((.*)\)", action_text)
    if not m:
        return action_text, {}
    name = m.group(1)
    argstr = m.group(2)
    if not argstr.strip():
        return name, {}
    try:
        # Build a dict from kwargs string like "f='deploy/config.yaml'"
        # Use the Python parser by wrapping in a call expression.
        parsed = ast.parse(f"f({argstr})", mode="eval")
        assert isinstance(parsed.body, ast.Call)
        kwargs = {}
        for kw in parsed.body.keywords:
            if isinstance(kw.value, ast.Constant):
                kwargs[kw.arg] = kw.value.value
            elif isinstance(kw.value, ast.Str):
                kwargs[kw.arg] = kw.value.s
            else:
                kwargs[kw.arg] = str(kw.value)
        return name, kwargs
    except Exception:
        return name, {"raw": argstr}


def to_baseline_turns(turns) -> list[BaselineTurn]:
    result = []
    for action_text, observation_text in turns:
        name, kwargs = parse_action(action_text)
        is_error = observation_text.startswith("Error:")
        result.append(BaselineTurn(
            action_name=name,
            action_input=kwargs,
            observation=observation_text,
            is_error=is_error,
        ))
    return result


def run_plateau_variant(encoder, turns, config: PlateauConfig):
    detector = Detector(
        encoder=encoder,
        calibrator=Calibrator(novelty_floor=config.novelty_floor),
        config=config,
    )
    for a, o in PREAMBLE:
        detector.evaluate(a, o)
    # Reset hits accumulated during preamble so the fixture starts clean.
    detector.reset_hits()
    trip_turn = None
    for index, (a, o) in enumerate(turns):
        reading = detector.evaluate(a, o)
        if reading.is_trip and trip_turn is None:
            trip_turn = index
    return trip_turn


def main() -> int:
    encoder = MiniLMEncoder().load()

    plateau_variants = [
        ("plateau", PlateauConfig()),
        ("plateau_action_only", PlateauConfig(action_only=True)),
        ("plateau_novelty_only", PlateauConfig(novelty_only=True)),
    ]

    baseline_detectors = [
        ("exact_args", lambda turns: exact_args_detect(to_baseline_turns(turns))),
        ("step_cap_25", lambda turns: step_cap_detect(to_baseline_turns(turns))),
        ("exact_match", lambda turns: exact_match_detect(to_baseline_turns(turns))),
        ("lexical", lambda turns: lexical_detect(to_baseline_turns(turns))),
    ]

    fixture_names = list(FIXTURES.keys())

    # Column widths
    fw = max(len(n) for n in fixture_names) + 2

    print("=" * 100)
    print(f"{'detector':<24} " + "".join(f"{n:<{fw}}" for n in fixture_names))
    print("-" * 100)

    results = {}

    for label, config in plateau_variants:
        row = {}
        for name in fixture_names:
            trip = run_plateau_variant(encoder, FIXTURES[name]["turns"], config)
            row[name] = trip
        results[label] = row
        cells = " ".join(f"{str(v):<{fw-1}}" if v is not None else f"{'---':<{fw-1}}" for v in row.values())
        print(f"{label:<24} {cells}")

    for label, detect_fn in baseline_detectors:
        row = {}
        for name in fixture_names:
            try:
                trip = detect_fn(FIXTURES[name]["turns"])
            except Exception as exc:
                trip = f"ERR({exc})"
            row[name] = trip
        results[label] = row
        cells = " ".join(f"{str(v):<{fw-1}}" if v is not None else f"{'---':<{fw-1}}" for v in row.values())
        print(f"{label:<24} {cells}")

    print("=" * 100)

    # Write to metrics.json
    path = ROOT / "metrics.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc["baseline_comparison"] = {
        "encoder": encoder.fingerprint(),
        "fixtures": fixture_names,
        "results": results,
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote -> {path}  (key: baseline_comparison)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
