"""Behavioural tests for the ported baselines.

These pin down what each baseline actually does, so that when the harness
reports a bad number for one of them we can tell the difference between "the
baseline is genuinely blind to this" and "we ported it wrong".
"""

from __future__ import annotations

import pytest

from eval.baselines import BaselineTurn
from eval.baselines.exact_args import (
    BLOCK_AT_COUNT,
    WINDOW_SIZE,
    detect as exact_args_detect,
    make_key,
)
from eval.baselines.step_cap import (
    RECURSION_LIMIT_DOCUMENTED,
    RECURSION_LIMIT_SOURCE,
    detect as step_cap_detect,
)


def turn(name: str, **kwargs) -> BaselineTurn:
    return BaselineTurn(action_name=name, action_input=kwargs)


# --- exact-args debounce -----------------------------------------------------


def test_exact_args_published_defaults():
    assert WINDOW_SIZE == 3
    assert BLOCK_AT_COUNT == 2


def test_exact_args_blocks_a_verbatim_repeat():
    turns = [
        turn("search_docs", q="auth token refresh"),
        turn("search_docs", q="auth token refresh"),
    ]
    assert exact_args_detect(turns) == 1


def test_exact_args_misses_a_paraphrase():
    """The gap Plateau exists to close: same intent, different string."""
    turns = [
        turn("search_docs", q="auth token refresh"),
        turn("search_docs", q="refreshing auth tokens"),
        turn("search_docs", q="how do I refresh a token"),
        turn("search_docs", q="token refresh procedure"),
    ]
    assert exact_args_detect(turns) is None


def test_exact_args_holds_on_a_batch_job():
    """A healthy batch job must not be blocked: each key is distinct."""
    turns = [turn("extract_text", f=f"invoice_{i:03d}.pdf") for i in range(41, 61)]
    assert exact_args_detect(turns) is None


def test_exact_args_window_lets_a_slow_repeat_escape():
    """With window_size 3, a repeat spaced further apart is not seen."""
    turns = [
        turn("a", x=1),
        turn("b", x=1),
        turn("c", x=1),
        turn("a", x=1),  # the earlier "a" has already left the window
    ]
    assert exact_args_detect(turns) is None


def test_exact_args_key_is_insertion_order_sensitive():
    """Documents a real property of the published spec (no sort_keys)."""
    assert make_key("t", {"a": 1, "b": 2}) != make_key("t", {"b": 2, "a": 1})


def test_exact_args_never_fires_on_an_empty_or_single_trace():
    assert exact_args_detect([]) is None
    assert exact_args_detect([turn("only", x=1)]) is None


# --- LangGraph recursion limit ----------------------------------------------


def test_step_cap_records_both_defaults():
    assert RECURSION_LIMIT_DOCUMENTED == 25
    assert RECURSION_LIMIT_SOURCE == 10007


def test_step_cap_reproduces_upstream_off_by_two():
    """stop = step + limit + 1, trip when step > stop, so the trip is at limit+2."""
    limit = 5
    turns = [turn("t", i=i) for i in range(20)]
    assert step_cap_detect(turns, recursion_limit=limit) == limit + 2


def test_step_cap_documented_default_fires_at_a_fixed_offset():
    turns = [turn("t", i=i) for i in range(61)]
    assert step_cap_detect(turns) == RECURSION_LIMIT_DOCUMENTED + 2


def test_step_cap_source_default_never_fires_on_a_realistic_trace():
    """At 10007 the detector is inert on any trace we will ever evaluate."""
    turns = [turn("t", i=i) for i in range(61)]
    assert step_cap_detect(turns, recursion_limit=RECURSION_LIMIT_SOURCE) is None


def test_step_cap_is_blind_to_content():
    """Identical and maximally-varied traces of equal length trip identically.

    This is the point of including it: it is a pure counter.
    """
    identical = [turn("same", x=1) for _ in range(40)]
    varied = [turn(f"tool_{i}", x=i) for i in range(40)]
    assert step_cap_detect(identical) == step_cap_detect(varied)


def test_step_cap_does_not_fire_on_a_short_trace():
    turns = [turn("t", i=i) for i in range(5)]
    assert step_cap_detect(turns) is None


def test_step_cap_rejects_an_invalid_limit():
    with pytest.raises(ValueError):
        step_cap_detect([turn("t")], recursion_limit=0)
