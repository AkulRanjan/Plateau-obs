"""TRAIL -> (action, observation) traces: the first non-synthetic evaluation.

Every trace in `eval/traces.py` is hand-written by us, which is the single
biggest weakness in this project's evidence. TRAIL (PatronusAI/TRAIL,
arXiv:2505.08638) is 148 real agent execution traces -- GAIA open-world search
with an OpenDeepResearch agent on o3-mini, and SWE-Bench Lite with a CodeAct
agent on claude-3-7-sonnet -- captured as OpenTelemetry/OpenInference spans and
annotated by four experts with 841 errors against a published taxonomy.

Nothing here reshares TRAIL. The dataset is gated and its terms forbid
redistribution; `data/trail/` is gitignored and only aggregates, span counts and
category *names* ever reach metrics.json.

Two judgement calls
-------------------
Turning an annotated span tree into a labelled `(action, observation)` trace
requires two decisions that are ours, not TRAIL's. Both are parameterised here
and both are serialised into metrics.json so a reader can disagree and recompute
rather than take our word for it.

1. **Which spans are turns** -- see :data:`SPAN_MODES`.
2. **Which error categories mean "should have tripped"** -- see :data:`MAPPINGS`.

The second is the load-bearing one. Plateau detects *information stagnation*:
an agent that keeps acting and stops learning. Most of TRAIL's taxonomy is not
that. `Formatting Errors` and `Instruction Non-compliance` alone account for
~42% of all annotated errors and a loop detector should not fire on them --
those traces are genuine negatives, which is exactly what makes this a real
test rather than a friendly one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

#: Where scripts/fetch_trail.py puts the snapshot. Gitignored.
DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "data" / "trail"

#: Provenance, carried into metrics.json so the numbers name their source.
DATASET_NOTE = {
    "id": "PatronusAI/TRAIL",
    "revision": "b424ce63d5973d5dcd7169b1bc3c07ccdee276d1",
    "paper": "arXiv:2505.08638",
    "licence": "MIT, gated: must not be reshared outside a gated/private HF repo",
    "vendored": False,
}

#: Directory name -> split label. TRAIL ships the raw span trees in these two
#: directories and the expert annotations in `processed_annotations_<split>`.
SPLITS = {
    "GAIA": "gaia",
    "SWE Bench": "swe_bench",
}

#: MiniLM truncates at 256 word-pieces regardless, but a raw span output can be
#: hundreds of kilobytes of scraped HTML, which costs tokenisation time for text
#: the encoder will discard. Cut at a fixed prefix and record the constant.
MAX_TEXT_CHARS = 2000

# --- Judgement call 1: which spans become turns -------------------------------
#
# A TOOL span is unambiguous: the action is the call, the observation is what
# came back. That is precisely Plateau's unit and precisely what the four
# baselines consume.
#
# An LLM span is more arguable. In a CodeAct/CodeAgent loop the model's output
# *is* the action ("Thought: ... Code: ...") and the tool result is the
# observation, so treating an LLM completion as an observation slightly
# overstates how much the environment told the agent. It is included as a second
# mode rather than folded in, because TOOL spans alone leave most GAIA traces
# too short for any multi-turn detector to fire -- and that fact is itself a
# result worth reporting.
SPAN_MODES: dict[str, tuple[str, ...]] = {
    "tool": ("TOOL",),
    "tool+llm": ("TOOL", "LLM"),
}

# --- Judgement call 2: which categories mean "should have tripped" ------------
#
# Leaf categories, verbatim from the taxonomy in
# patronus-ai/trail-benchmark/benchmarking/run_eval.py.

#: "Called the tool excessively" -- the canonical runaway loop, and the only
#: category that unambiguously describes what Plateau exists to catch.
STRICT = frozenset({"Resource Abuse"})

#: Adds the two other "the agent is no longer making progress" categories:
#: progress-monitoring failures, and losing track of state.
PRIMARY = STRICT | frozenset({"Task Orchestration", "Context Handling Failures"})

#: Adds categories where the agent is doing *something*, just not something
#: useful. Deliberately generous -- this is the mapping most favourable to a
#: stagnation detector, and is reported so that favourability is visible.
BROAD = PRIMARY | frozenset({"Goal Deviation", "Poor Information Retrieval"})

MAPPINGS: dict[str, frozenset[str]] = {
    "strict": STRICT,
    "primary": PRIMARY,
    "broad": BROAD,
}

#: The mapping headline numbers are quoted under. Every mapping is measured and
#: written to metrics.json; this one is not privileged by the results, only by
#: being the one the README quotes.
DEFAULT_MAPPING = "primary"


@dataclass(frozen=True)
class TrailTrace:
    """One TRAIL trace, normalised to the shape the harness already consumes."""

    name: str
    split: str
    trace_id: str
    turns: list[tuple[str, str]]
    categories: frozenset[str] = field(default_factory=frozenset)
    n_spans: int = 0

    def should_trip(self, mapping: str = DEFAULT_MAPPING) -> bool:
        return bool(self.categories & MAPPINGS[mapping])


def _walk(span: dict) -> Iterator[dict]:
    """Depth-first over TRAIL's nested `child_spans` tree, parents first."""
    yield span
    for child in span.get("child_spans") or []:
        yield from _walk(child)


def _clip(text: str) -> str:
    text = " ".join(str(text).split())
    return text[:MAX_TEXT_CHARS]


def _tool_turn(attrs: dict) -> tuple[str, str] | None:
    name = attrs.get("tool.name")
    if not name:
        return None
    raw = attrs.get("input.value")
    args = ""
    if raw:
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            positional = parsed.get("args") or []
            keyword = parsed.get("kwargs") or {}
            args = ", ".join(
                [_clip(a) for a in positional]
                + [f"{k}={_clip(v)}" for k, v in keyword.items()]
            )
        except (json.JSONDecodeError, AttributeError, TypeError):
            args = _clip(raw)
    return f"{name}({args})", _clip(attrs.get("output.value") or "")


def _llm_turn(attrs: dict) -> tuple[str, str] | None:
    output = attrs.get("llm.output_messages.0.message.content")
    if not output:
        return None
    # The action half is the tail of what the model was last told -- the closest
    # available stand-in for "what the agent was trying to do on this step".
    prompt = ""
    for index in range(32):
        content = attrs.get(f"llm.input_messages.{index}.message.content")
        if content is None:
            break
        prompt = content
    model = attrs.get("llm.model_name", "llm")
    return f"{model}({_clip(prompt)})", _clip(output)


def spans_to_turns(trace: dict, mode: str = "tool") -> list[tuple[str, str]]:
    """Flatten a TRAIL span tree into `(action, observation)` pairs."""
    kinds = SPAN_MODES[mode]
    turns: list[tuple[str, str]] = []
    for root in trace.get("spans") or []:
        for span in _walk(root):
            attrs = span.get("span_attributes") or {}
            kind = attrs.get("openinference.span.kind")
            if kind not in kinds:
                continue
            turn = _tool_turn(attrs) if kind == "TOOL" else _llm_turn(attrs)
            if turn is not None and turn[1]:
                turns.append(turn)
    return turns


def count_spans(trace: dict) -> int:
    return sum(1 for root in trace.get("spans") or [] for _ in _walk(root))


def load_trail(
    root: Path | str = DEFAULT_ROOT, mode: str = "tool"
) -> dict[str, TrailTrace]:
    """Load every TRAIL trace found under `root`.

    Returns `name -> TrailTrace`, where the name is `<split>/<trace hash>`. A
    trace whose annotation file is missing is skipped rather than silently
    treated as error-free: an absent label is not a negative label.
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(
            f"{root} does not exist. TRAIL is gated and is never committed -- "
            f"run `python scripts/fetch_trail.py` after `hf auth login`."
        )
    if mode not in SPAN_MODES:
        raise ValueError(f"unknown span mode {mode!r}; expected one of {list(SPAN_MODES)}")

    out: dict[str, TrailTrace] = {}
    for directory, split in SPLITS.items():
        trace_dir = root / directory
        ann_dir = root / f"processed_annotations_{split}"
        if not trace_dir.is_dir():
            continue
        for path in sorted(trace_dir.glob("*.json")):
            ann_path = ann_dir / path.name
            if not ann_path.is_file():
                continue
            trace = json.loads(path.read_text(encoding="utf-8"))
            annotation = json.loads(ann_path.read_text(encoding="utf-8"))
            categories = frozenset(
                e["category"]
                for e in (annotation.get("errors") or [])
                if e.get("category")
            )
            name = f"{split}/{path.stem}"
            out[name] = TrailTrace(
                name=name,
                split=split,
                trace_id=trace.get("trace_id", path.stem),
                turns=spans_to_turns(trace, mode=mode),
                categories=categories,
                n_spans=count_spans(trace),
            )
    return out


def observed_categories(traces: dict[str, TrailTrace]) -> dict[str, int]:
    """Every annotated category present, with trace counts.

    Written into metrics.json so the mapping above can be audited against what
    the data actually contains rather than against the published taxonomy.
    """
    counts: dict[str, int] = {}
    for trace in traces.values():
        for category in trace.categories:
            counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
