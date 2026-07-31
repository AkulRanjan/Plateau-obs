"""The TRAIL normaliser, tested against a hand-built span tree.

TRAIL is gated and is never committed, so these tests build a miniature trace in
the same shape rather than reading data/trail/. That is the point: the loader's
contract can be pinned on any machine, including one that has never downloaded
the dataset, and a schema change shows up here rather than as a silently empty
results table.

The fixture's structure is copied from a real trace
(GAIA/0035f455b3ff2295167a844f04d85d34.json): a nested `child_spans` tree with
`span_attributes` carrying OpenInference keys.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.trail import (
    BROAD,
    canonical_category,
    DEFAULT_MAPPING,
    MAPPINGS,
    MAX_TEXT_CHARS,
    PRIMARY,
    SPAN_MODES,
    STRICT,
    count_spans,
    load_trail,
    observed_categories,
    spans_to_turns,
)


def llm_span(span_id, prompt, completion):
    return {
        "span_id": span_id,
        "span_attributes": {
            "openinference.span.kind": "LLM",
            "llm.model_name": "o3-mini",
            "llm.input_messages.0.message.content": prompt,
            "llm.output_messages.0.message.content": completion,
        },
        "child_spans": [],
    }


def tool_span(span_id, name, args, output):
    return {
        "span_id": span_id,
        "span_attributes": {
            "openinference.span.kind": "TOOL",
            "tool.name": name,
            "input.value": json.dumps({"args": args, "kwargs": {}}),
            "output.value": output,
        },
        "child_spans": [],
    }


@pytest.fixture
def trace():
    """A root with an un-kinded chain in the middle, as TRAIL really nests."""
    return {
        "trace_id": "abc123",
        "spans": [
            {
                "span_id": "root",
                "span_attributes": {},
                "child_spans": [
                    llm_span("s1", "find the fish", "Thought: search for it"),
                    {
                        "span_id": "step1",
                        "span_attributes": {"openinference.span.kind": "CHAIN"},
                        "child_spans": [
                            tool_span("s2", "search", ["clownfish"], "No results."),
                            tool_span("s3", "search", ["clown fish"], "No results."),
                        ],
                    },
                ],
            }
        ],
    }


def test_walk_reaches_every_nested_span(trace):
    """A flat count would report 1; the tree really holds 5."""
    assert count_spans(trace) == 5


def test_tool_mode_takes_only_tool_spans(trace):
    turns = spans_to_turns(trace, mode="tool")
    assert [action for action, _ in turns] == [
        "search(clownfish)",
        "search(clown fish)",
    ]
    assert all(observation == "No results." for _, observation in turns)


def test_tool_llm_mode_keeps_trace_order(trace):
    """The LLM span is first in the tree and must stay first in the turns."""
    turns = spans_to_turns(trace, mode="tool+llm")
    assert len(turns) == 3
    assert turns[0][1] == "Thought: search for it"
    assert turns[0][0].startswith("o3-mini(")
    assert [a for a, _ in turns[1:]] == ["search(clownfish)", "search(clown fish)"]


def test_every_declared_span_mode_is_usable(trace):
    for mode in SPAN_MODES:
        assert spans_to_turns(trace, mode=mode), mode


def test_unknown_span_mode_is_rejected(tmp_path):
    (tmp_path / "GAIA").mkdir()
    with pytest.raises(ValueError, match="unknown span mode"):
        load_trail(tmp_path, mode="everything")


def test_spans_without_an_output_are_not_turns():
    """A span that produced nothing is not an observation of anything."""
    empty = {
        "spans": [
            {
                "span_id": "r",
                "span_attributes": {},
                "child_spans": [tool_span("s", "search", ["x"], "")],
            }
        ]
    }
    assert spans_to_turns(empty, mode="tool") == []


def test_long_text_is_clipped():
    """A span output can be hundreds of kB of scraped HTML."""
    big = {
        "spans": [
            {
                "span_id": "r",
                "span_attributes": {},
                "child_spans": [tool_span("s", "fetch", ["u"], "x" * 50_000)],
            }
        ]
    }
    (_, observation), = spans_to_turns(big, mode="tool")
    assert len(observation) == MAX_TEXT_CHARS


def test_malformed_input_value_does_not_crash_the_loader():
    """Real traces carry input.value that is not always the documented JSON."""
    span = tool_span("s", "search", ["x"], "ok")
    span["span_attributes"]["input.value"] = "not json at all {["
    bad = {"spans": [{"span_id": "r", "span_attributes": {}, "child_spans": [span]}]}
    (action, _), = spans_to_turns(bad, mode="tool")
    assert action.startswith("search(")


# --- the ground-truth mapping ------------------------------------------------


def test_mappings_are_strictly_nested():
    """strict < primary < broad. A trace positive under strict must stay
    positive under broad, or the sensitivity analysis is not a spectrum."""
    assert STRICT < PRIMARY < BROAD


def test_default_mapping_is_one_of_the_declared_mappings():
    assert DEFAULT_MAPPING in MAPPINGS


def test_formatting_errors_are_never_a_stagnation_label():
    """Formatting and instruction-compliance errors are ~42% of TRAIL's
    annotations. A loop detector must not be credited for catching them, so no
    mapping may include them -- those traces are our negatives."""
    for name, categories in MAPPINGS.items():
        assert canonical_category("Formatting Errors") not in categories, name
        assert canonical_category("Instruction Non-compliance") not in categories, name


# --- category canonicalisation ------------------------------------------------


def test_real_category_variants_collapse_to_one_leaf():
    """The pinned revision holds 31 distinct strings for ~17 leaves. Exact
    matching silently drops 8 labelled traces, which would read as a slightly
    better false-trip rate and nothing else. Every string below is one that
    actually appears in the data."""
    groups = [
        ["Task Orchestration", "Task Orchestration Errors", "Task Orchestration Error"],
        ["Context Handling Failures", "Context Handling Failure"],
        ["Goal Deviation", "Goal deviation"],
        ["Poor Information Retrieval", "Poor Information retrieval"],
        ["Tool Selection Errors", "Tool Selection"],
        ["Formatting Errors", "Formatting Error"],
        ["Language-only", "Language-Only"],
        ["Incorrect Problem Identification", " Incorrect Problem Identification"],
        ["Instruction Non-compliance", "Instruction Non-Compliance",
         "Instruction non complience"],
    ]
    for variants in groups:
        canonical = {canonical_category(v) for v in variants}
        assert len(canonical) == 1, f"{variants} -> {canonical}"


def test_canonicalisation_does_not_merge_distinct_leaves():
    """Depluralising must not collapse two real categories into one."""
    distinct = [
        "Resource Abuse", "Resource Exhaustion", "Resource Not Found",
        "Task Orchestration", "Context Handling Failures", "Goal Deviation",
        "Poor Information Retrieval", "Tool Selection Errors", "Tool-related",
        "Formatting Errors", "Instruction Non-compliance",
    ]
    canonical = [canonical_category(c) for c in distinct]
    assert len(set(canonical)) == len(distinct), sorted(canonical)


def test_the_stagnation_mappings_survive_canonicalisation():
    """Each mapping must still match the real strings it is meant to select."""
    assert canonical_category("Resource Abuse") in MAPPINGS["strict"]
    assert canonical_category("Task Orchestration Errors") in MAPPINGS["primary"]
    assert canonical_category("Context Handling Failure") in MAPPINGS["primary"]
    assert canonical_category("Goal deviation") in MAPPINGS["broad"]
    assert canonical_category("Goal deviation") not in MAPPINGS["primary"]


# --- end-to-end over a fake snapshot -----------------------------------------


def write_snapshot(root: Path, trace: dict, categories: list[str]) -> None:
    (root / "GAIA").mkdir(parents=True)
    (root / "processed_annotations_gaia").mkdir(parents=True)
    (root / "GAIA" / "deadbeef.json").write_text(json.dumps(trace), encoding="utf-8")
    (root / "processed_annotations_gaia" / "deadbeef.json").write_text(
        json.dumps({"errors": [{"category": c} for c in categories]}),
        encoding="utf-8",
    )


def test_load_trail_labels_from_the_annotation(tmp_path, trace):
    write_snapshot(tmp_path, trace, ["Resource Abuse", "Formatting Errors"])
    loaded = load_trail(tmp_path)
    assert list(loaded) == ["gaia/deadbeef"]
    got = loaded["gaia/deadbeef"]
    assert got.split == "gaia"
    assert got.trace_id == "abc123"
    assert got.should_trip("strict") is True
    assert got.should_trip("primary") is True


def test_a_formatting_only_trace_is_a_negative(tmp_path, trace):
    write_snapshot(tmp_path, trace, ["Formatting Errors"])
    got = load_trail(tmp_path)["gaia/deadbeef"]
    assert got.should_trip("strict") is False
    assert got.should_trip("broad") is False


def test_a_trace_with_no_annotation_file_is_skipped_not_labelled_negative(
    tmp_path, trace
):
    """An absent label is not a negative label."""
    (tmp_path / "GAIA").mkdir(parents=True)
    (tmp_path / "processed_annotations_gaia").mkdir(parents=True)
    (tmp_path / "GAIA" / "orphan.json").write_text(json.dumps(trace), encoding="utf-8")
    assert load_trail(tmp_path) == {}


def test_observed_categories_counts_traces_not_errors(tmp_path, trace):
    write_snapshot(tmp_path, trace, ["Goal Deviation", "Goal Deviation"])
    assert observed_categories(load_trail(tmp_path)) == {
        canonical_category("Goal Deviation"): 1
    }


def test_missing_root_names_the_fetch_script(tmp_path):
    with pytest.raises(FileNotFoundError, match="fetch_trail"):
        load_trail(tmp_path / "nope")
