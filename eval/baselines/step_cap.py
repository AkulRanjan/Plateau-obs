"""LangGraph recursion-limit baseline.

=============================================================================
PROVENANCE
-----------------------------------------------------------------------------
Ported from:
    langchain-ai/langgraph @ 41341457342327166d72fc11952ab28fb61ec0bf
    libs/langgraph/langgraph/pregel/_loop.py       (the step/stop arithmetic)
    libs/langgraph/langgraph/errors.py             (GraphRecursionError)
    libs/langgraph/langgraph/_internal/_config.py  (DEFAULT_RECURSION_LIMIT)
Licence: MIT

The arithmetic below is a faithful re-implementation of the upstream check, not
copied code -- upstream's version is entangled with checkpointer and channel
state that has no meaning outside a Pregel graph.

Verified at that commit, by reading the source:

  _loop.py:1701, :1961   self.stop = self.step + self.config["recursion_limit"] + 1
  _loop.py:607           if self.step > self.stop:  ->  status = "out_of_steps"
  _loop.py:301-302       self.step = 0 ; self.stop = 0   (at construction)
  errors.py:67           class GraphRecursionError(RecursionError)

CONFIRMED: the check performs NO comparison of action or observation content.
`self.step` and `self.stop` are plain integers threaded through
`prepare_next_tasks`. A grep across `_loop.py` and `_algo.py` for
similarity / jaccard / levenshtein / embed / cosine / content comparison returns
nothing; the single "deduplicate" hit is last-write-wins merging of channel
writes, which is state reconciliation and not turn comparison.

So this detector cannot distinguish a productive long run from a stuck one. It
counts supersteps and stops. That is its entire mechanism, and it is the reason
it belongs in the comparison: it is the honest floor.

DISCREPANCY, recorded rather than reconciled
-----------------------------------------------------------------------------
The instruction for this port specified a default of 25. The source at the
commit above ships:

    DEFAULT_RECURSION_LIMIT = int(getenv("LANGGRAPH_DEFAULT_RECURSION_LIMIT", "10007"))

i.e. **10007**, environment-overridable -- not 25. A `git log -S` over the
shallow clone did not reach a revision where it was 25, so this file does not
claim upstream "changed" it; it claims only what the source says at this commit.
25 is widely documented for LangGraph and is retained as the harness default per
instruction, but the source-verified value is recorded here and exercised by the
harness alongside it.

This is load-bearing for the evaluation: at a limit of 10007 this detector never
fires on any trace of realistic length, so its detection_turn_index is None
everywhere and its recall is zero by construction. At 25 it fires blindly at a
fixed offset regardless of what the agent is doing. Both facts belong in the
results table, and neither is a strawman -- they are what the published defaults
actually produce.
=============================================================================
"""

from __future__ import annotations

from typing import Sequence

from eval.baselines._turn import BaselineTurn

#: Harness default, per instruction, and the value in LangGraph's public docs.
RECURSION_LIMIT_DOCUMENTED = 25

#: Source-verified default at langgraph @ 41341457, env-overridable upstream.
RECURSION_LIMIT_SOURCE = 10007

#: Upstream's initial step counter (`_loop.py:301`).
INITIAL_STEP = 0


def detect(
    turns: Sequence[BaselineTurn],
    recursion_limit: int = RECURSION_LIMIT_DOCUMENTED,
    initial_step: int = INITIAL_STEP,
) -> int | None:
    """Return the 0-indexed turn at which LangGraph would raise, else None.

    Reproduces upstream's arithmetic exactly, including its off-by-two relative
    to a naive "stop after N steps" reading: with ``stop = step + limit + 1``
    and a trip condition of ``step > stop``, steps ``initial_step`` through
    ``limit + 1`` all pass, so the trip lands on step ``limit + 2``.

    One caveat on the mapping, stated because it affects the results table:
    upstream counts **supersteps**, not tool calls. A superstep may execute
    several nodes in parallel, so a superstep is not in general one agent turn.
    This maps one trace turn to one superstep, which is the most favourable
    reading for the baseline -- any other mapping makes it fire later, not
    earlier.

    Args:
        turns: the trace, in order.
        recursion_limit: the configured limit.
        initial_step: starting step counter.

    Returns:
        Index of the turn on which the limit is exceeded, or None.
    """
    if recursion_limit < 1:
        # main.py:2563 -- upstream raises ValueError for this.
        raise ValueError("recursion_limit must be at least 1")

    stop = initial_step + recursion_limit + 1

    for index in range(len(turns)):
        step = initial_step + index
        if step > stop:
            return index

    return None
