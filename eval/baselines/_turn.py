"""Minimal turn shape shared by the ported baselines.

PROVISIONAL. §9 owns the real trace schema and has not been received yet. This
carries only the three fields the baselines actually read, so that porting is
not blocked on the schema. When §9 lands, this adapts to it rather than the
other way round.

Every baseline exposes the same entry point:

    detect(turns) -> int | None

returning the 0-indexed turn at which the detector would have fired, or None if
it never fires over the whole trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BaselineTurn:
    """One agent turn, reduced to what a repetition detector can see.

    Attributes:
        action_name: the tool name.
        action_input: the tool arguments, JSON-serialisable.
        observation: the tool result rendered to text.
        is_error: whether the tool call returned an error status.
    """

    action_name: str
    action_input: Any = field(default_factory=dict)
    observation: str = ""
    is_error: bool = False
