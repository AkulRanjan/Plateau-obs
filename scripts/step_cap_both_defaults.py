"""Step 4 -- run the LangGraph step-cap baseline at BOTH published defaults.

The 10007 row having recall zero by construction is a finding, not a footnote:
LangGraph's shipped default cannot fire on any trace of realistic length, so a
comparison that quietly used 25 would overstate what the incumbent actually does
in production.

Exact citations, read at langchain-ai/langgraph @
41341457342327166d72fc11952ab28fb61ec0bf (MIT):

    symbol                     file                                        line
    DEFAULT_RECURSION_LIMIT    libs/langgraph/langgraph/_internal/_config.py  32
      = int(getenv("LANGGRAPH_DEFAULT_RECURSION_LIMIT", "10007"))
    (its use as the default)   libs/langgraph/langgraph/_internal/_config.py 335
      recursion_limit=DEFAULT_RECURSION_LIMIT
    self.stop = self.step + self.config["recursion_limit"] + 1
                               libs/langgraph/langgraph/pregel/_loop.py     1701
                               libs/langgraph/langgraph/pregel/_loop.py     1961
    if self.step > self.stop:  libs/langgraph/langgraph/pregel/_loop.py      607
    class GraphRecursionError(RecursionError)
                               libs/langgraph/langgraph/errors.py             67

Writes metrics.json -> step_cap_both_defaults.

    python scripts/step_cap_both_defaults.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.baselines import BaselineTurn  # noqa: E402
from eval.baselines.step_cap import (  # noqa: E402
    RECURSION_LIMIT_DOCUMENTED,
    RECURSION_LIMIT_SOURCE,
    detect,
)

CITATIONS = {
    "DEFAULT_RECURSION_LIMIT": {
        "file": "libs/langgraph/langgraph/_internal/_config.py",
        "line": 32,
        "source": 'DEFAULT_RECURSION_LIMIT = int(getenv("LANGGRAPH_DEFAULT_RECURSION_LIMIT", "10007"))',
    },
    "default_applied_to_config": {
        "file": "libs/langgraph/langgraph/_internal/_config.py",
        "line": 335,
        "source": "recursion_limit=DEFAULT_RECURSION_LIMIT,",
    },
    "stop_bound": {
        "file": "libs/langgraph/langgraph/pregel/_loop.py",
        "line": "1701, 1961",
        "source": 'self.stop = self.step + self.config["recursion_limit"] + 1',
    },
    "trip_check": {
        "file": "libs/langgraph/langgraph/pregel/_loop.py",
        "line": 607,
        "source": "if self.step > self.stop:",
    },
    "exception": {
        "file": "libs/langgraph/langgraph/errors.py",
        "line": 67,
        "source": "class GraphRecursionError(RecursionError):",
    },
}

#: Representative trace lengths. 61 is the demo's runaway length.
TRACE_LENGTHS = [10, 25, 30, 61, 200]

ROWS = [
    ("step_cap_langgraph_25", RECURSION_LIMIT_DOCUMENTED, "primary; LangGraph's documented default"),
    ("step_cap_langgraph_10007", RECURSION_LIMIT_SOURCE, "source default at 41341457; env-overridable"),
]


def main() -> int:
    print("LangGraph recursion limit, both published defaults")
    print("commit 41341457342327166d72fc11952ab28fb61ec0bf (MIT)\n")

    print("exact citations:")
    for name, cite in CITATIONS.items():
        print(f"  {name}")
        print(f"    {cite['file']}:{cite['line']}")
        print(f"    {cite['source']}")
    print()

    header = f"{'baseline':<26} {'limit':>7} " + " ".join(f"{n:>7}" for n in TRACE_LENGTHS)
    print(header)
    print("-" * len(header))

    results = {}
    for label, limit, note in ROWS:
        detections = {}
        for length in TRACE_LENGTHS:
            turns = [BaselineTurn(action_name="t", action_input={"i": i}) for i in range(length)]
            detections[length] = detect(turns, recursion_limit=limit)
        cells = " ".join(
            f"{'none' if detections[n] is None else detections[n]:>7}" for n in TRACE_LENGTHS
        )
        print(f"{label:<26} {limit:>7} {cells}")

        fires_ever = any(v is not None for v in detections.values())
        results[label] = {
            "recursion_limit": limit,
            "note": note,
            "detection_turn_index_by_trace_length": {
                str(k): v for k, v in detections.items()
            },
            "fires_on_any_tested_length": fires_ever,
            "recall_zero_by_construction": not fires_ever,
        }

    print()
    for label, row in results.items():
        if row["recall_zero_by_construction"]:
            print(
                f"FINDING: {label} never fires at any tested trace length "
                f"(max {max(TRACE_LENGTHS)} turns). Its recall is zero by "
                f"construction, not by weak performance."
            )

    path = ROOT / "metrics.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc["step_cap_both_defaults"] = {
        "upstream": "langchain-ai/langgraph",
        "commit": "41341457342327166d72fc11952ab28fb61ec0bf",
        "licence": "MIT",
        "citations": CITATIONS,
        "off_by_two_note": (
            "stop = step + limit + 1 and the trip is step > stop, so steps 0..limit+1 "
            "all pass and the trip lands on step limit+2"
        ),
        "superstep_note": (
            "recursion_limit counts supersteps, not tool calls; one turn is mapped to "
            "one superstep, the most favourable reading for the baseline"
        ),
        "trace_lengths_tested": TRACE_LENGTHS,
        "rows": results,
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote -> {path}  (key: step_cap_both_defaults)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
