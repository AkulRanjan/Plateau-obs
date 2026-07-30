"""OpenHands `StuckDetector` exact-match baseline.

=============================================================================
PROVENANCE
-----------------------------------------------------------------------------
Ported from:
    OpenHands/software-agent-sdk @ 4b132eddb6cf414841439a46ce42ed2cd66a628a
    openhands-sdk/openhands/sdk/conversation/stuck_detector.py  (StuckDetector)
    openhands-sdk/openhands/sdk/conversation/types.py           (thresholds)
Licence: MIT

Re-implemented rather than copied: upstream's `_event_eq` dispatches on
OpenHands `Event` subclasses (`ActionEvent`, `ObservationEvent`,
`AgentErrorEvent`, `MessageEvent`) and reads `ConversationState`, none of which
exist outside that SDK. The *equality semantics* are reproduced faithfully.

`_event_eq` at :276 compares, for actions: `source`, `thought`, `action`,
`tool_name` — deliberately ignoring `tool_call_id`, `llm_response_id`,
`action_id`. For observations: `source`, `observation`, `tool_name`. So it is
exact equality over content with volatile identifiers excluded. Our
`BaselineTurn` carries the content fields and no identifiers, so plain equality
on (name, input) and (observation) is the faithful analogue.

Published defaults (`StuckDetectionThresholds`), used unmodified — no strawman:
    action_observation   = 4
    action_error         = 3
    monologue            = 3   (not applicable: needs message events)
    alternating_pattern  = 6
    MAX_EVENTS_TO_SCAN_FOR_STUCK_DETECTION = 20

IMPORTANT, and contrary to our own pitch deck: this detector reads **both
halves** of a turn. Scenario 1 requires `actions_equal` AND `observations_equal`.
It will therefore *not* fire on a healthy batch job whose observations differ.
See THIRD_PARTY_NOTICES.md, "Corrections to our own pitch materials".

Scenarios implemented here (3 of upstream's 5):
    1. repeating action-observation   -- both halves identical, N times
    2. repeating action-error         -- same action, all errors, N times
    4. alternating action-observation -- an A-B-A-B pattern

Not implemented, and why:
    3. agent monologue        -- requires MessageEvents (agent chatter without
                                user input). Our trace shape has no message
                                events, so this scenario cannot fire either way.
    5. context-window errors -- upstream's own implementation is a stub that
                                returns False (`_is_stuck_context_window_error`
                                at :265). Porting it would add nothing.
Both omissions can only make this baseline fire *less*, never more, so they do
not flatter Plateau. Recorded here so the omission is visible in the results.
=============================================================================
"""

from __future__ import annotations

import json
from typing import Sequence

from eval.baselines._turn import BaselineTurn

# --- Published defaults ------------------------------------------------------
ACTION_OBSERVATION_THRESHOLD = 4
ACTION_ERROR_THRESHOLD = 3
ALTERNATING_PATTERN_THRESHOLD = 6
MAX_EVENTS_TO_SCAN = 20


def _action_key(turn: BaselineTurn) -> str:
    """Action identity, mirroring `_event_eq`'s action comparison."""
    return f"{turn.action_name}|{json.dumps(turn.action_input, sort_keys=True)}"


def _observation_key(turn: BaselineTurn) -> str:
    """Observation identity, mirroring `_event_eq`'s observation comparison."""
    return f"{turn.action_name}|{turn.observation}"


def _stuck_repeating_action_observation(window: Sequence[BaselineTurn], threshold: int) -> bool:
    """Scenario 1: same action AND same observation, `threshold` times."""
    if len(window) < threshold:
        return False
    recent = window[-threshold:]
    actions_equal = all(_action_key(t) == _action_key(recent[0]) for t in recent)
    observations_equal = all(
        _observation_key(t) == _observation_key(recent[0]) for t in recent
    )
    return actions_equal and observations_equal


def _stuck_repeating_action_error(window: Sequence[BaselineTurn], threshold: int) -> bool:
    """Scenario 2: same action, and every observation is an error."""
    if len(window) < threshold:
        return False
    recent = window[-threshold:]
    actions_equal = all(_action_key(t) == _action_key(recent[0]) for t in recent)
    return actions_equal and all(t.is_error for t in recent)


def _stuck_alternating(window: Sequence[BaselineTurn], threshold: int) -> bool:
    """Scenario 4: an A-B-A-B pattern over the last `threshold` turns.

    Upstream compares `last_actions[i]` with `last_actions[i + 2]` and likewise
    for observations, across the window.
    """
    if len(window) < threshold:
        return False
    recent = window[-threshold:]
    for i in range(len(recent) - 2):
        if _action_key(recent[i]) != _action_key(recent[i + 2]):
            return False
        if _observation_key(recent[i]) != _observation_key(recent[i + 2]):
            return False
    # A-B-A-B requires the two alternating halves to actually differ.
    return _action_key(recent[0]) != _action_key(recent[1])


def detect(
    turns: Sequence[BaselineTurn],
    action_observation_threshold: int = ACTION_OBSERVATION_THRESHOLD,
    action_error_threshold: int = ACTION_ERROR_THRESHOLD,
    alternating_pattern_threshold: int = ALTERNATING_PATTERN_THRESHOLD,
    max_events_to_scan: int = MAX_EVENTS_TO_SCAN,
) -> int | None:
    """Return the 0-indexed turn at which `is_stuck()` would first return True.

    Evaluated incrementally: at each turn, run the scenarios over the trailing
    scan window, exactly as upstream calls `is_stuck()` once per step.
    """
    for index in range(len(turns)):
        window = turns[max(0, index + 1 - max_events_to_scan) : index + 1]

        if _stuck_repeating_action_observation(window, action_observation_threshold):
            return index
        if _stuck_repeating_action_error(window, action_error_threshold):
            return index
        if _stuck_alternating(window, alternating_pattern_threshold):
            return index

    return None
