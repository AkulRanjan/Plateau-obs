"""Exact-args debounce baseline.

=============================================================================
PROVENANCE
-----------------------------------------------------------------------------
Implemented from the specification published at:
    https://dev.to/aws/how-to-prevent-ai-agent-reasoning-loops-from-wasting-tokens-2652

Cross-referenced against:
    aws-samples/sample-why-agents-fail @ 08beccadbf753b699465234e52c0a48e087c6606
    where the hook is REFERENCED BUT NOT SHIPPED.

No code was copied, because there is no upstream source to copy. This is an
independent implementation of a published specification, written to the
published parameters. Licence of the referenced repository: MIT-0.

DISCREPANCY, recorded rather than reconciled: the technical approach cites this
as a `DebounceHook` in `aws-samples/sample-why-agents-fail`. That repository
contains no such class, and states its absence outright at
`stop-ai-agents-wasting-tokens/03-reasoning-loops-demo/images/
generate_ambiguous_feedback.py:5`:

    "SUCCESS/FAILED states + LimitToolCounts hard ceiling). No DebounceHook."

What that repository does ship is `LimitToolCounts`, a per-tool call-count cap,
which is a different mechanism and is ported separately as the step-cap family.
See THIRD_PARTY_NOTICES.md.
=============================================================================

Mechanism, per the published specification:

    key         = (tool_use["name"], json.dumps(tool_use["input"]))
    window_size = 3
    block when the key appears >= 2 times in the window

This is exact-string matching on the serialised arguments. It catches a verbatim
repeat of the same call and nothing else: change one character of one argument
and the key changes.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Sequence

from eval.baselines._turn import BaselineTurn

# --- Published defaults. Not tuned, not weakened. ----------------------------
WINDOW_SIZE = 3
BLOCK_AT_COUNT = 2


def make_key(action_name: str, action_input: object) -> str:
    """Build the debounce key exactly as the published specification states.

    ``json.dumps`` is called without ``sort_keys``, matching the published
    spec verbatim. That makes the key sensitive to dict insertion order, so two
    semantically identical argument dicts built in different orders produce
    different keys. That is a real property of the published design and is left
    intact -- correcting it would make this a different detector than the one
    being compared against.
    """
    return f"{action_name}|{json.dumps(action_input)}"


def detect(
    turns: Sequence[BaselineTurn],
    window_size: int = WINDOW_SIZE,
    block_at_count: int = BLOCK_AT_COUNT,
) -> int | None:
    """Return the 0-indexed turn at which the debounce would block, else None.

    Args:
        turns: the trace, in order.
        window_size: how many recent keys are retained.
        block_at_count: occurrences of a key within the window that trigger a block.

    Returns:
        Index of the blocking turn, or None if the detector never fires.
    """
    window: deque[str] = deque(maxlen=window_size)

    for index, turn in enumerate(turns):
        key = make_key(turn.action_name, turn.action_input)
        # The current call counts toward its own occurrence total, matching the
        # published behaviour of blocking the call that completes the repeat.
        window.append(key)
        if window.count(key) >= block_at_count:
            return index

    return None
