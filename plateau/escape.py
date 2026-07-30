"""§7 -- the escape vector and the messages that carry it.

When the breaker opens it owes the agent two things: why it was stopped, and
what to do instead. A refusal without a route is just a stall with better
logging, which is the complaint in OpenHands #5480 ("Cannot recover from Agent
stuck in loop").

The route is derived, not invented. Plateau already computes observation novelty
for every turn, so it knows which turn in the run produced the most new
information. That turn is the escape vector: the agent is pointed back at the
last thing that actually worked.

Recording starts on turn 0, during CALIBRATING, and never stops
-------------------------------------------------------------
The most informative action in a run very often happens early -- the first broad
search, the first file listing -- long before the breaker is armed. If tracking
only began at CLOSED, the escape vector would systematically point at mediocre
turns and miss the good one. So :meth:`EscapeTracker.record` is called on every
turn in every state.

The no-progress case
--------------------
Sometimes there is no route, because nothing in the run has produced new
information. When even the best turn's novelty is below the floor, the escape
line is **dropped** and replaced by an explicit statement to that effect. Naming
a "best" turn whose novelty is 0.04 would be worse than saying nothing: it
suggests a productive path that does not exist.

Every number in every message is interpolated from live state. Nothing here is
templated with a plausible-looking constant.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from plateau.calibrator import NOVELTY_FLOOR
from plateau.detector import Quadrant, Reading


@dataclass(frozen=True)
class EscapeCandidate:
    """One recorded turn, as a possible thing to go back to."""

    turn_index: int
    action_text: str
    obs_novelty: float
    state: str = ""

    def summary(self) -> str:
        return f"turn {self.turn_index} ({self.action_text})"


@dataclass
class EscapeTracker:
    """Remembers which turn taught the agent the most.

    Args:
        novelty_floor: the fixed floor. A best candidate below it means there is
            no escape route, not a weak one.
    """

    novelty_floor: float = NOVELTY_FLOOR
    candidates: list[EscapeCandidate] = field(default_factory=list)

    # -- recording ------------------------------------------------------------

    def record(
        self, turn_index: int, action_text: str, obs_novelty: float, state: str = ""
    ) -> None:
        """Record one turn. Called in EVERY state, including CALIBRATING."""
        self.candidates.append(
            EscapeCandidate(
                turn_index=turn_index,
                action_text=action_text,
                obs_novelty=obs_novelty,
                state=state,
            )
        )

    # -- the vector -----------------------------------------------------------

    @property
    def best(self) -> EscapeCandidate | None:
        """The highest-novelty turn recorded so far, or None if nothing yet.

        Ties break toward the earlier turn: if two turns were equally
        informative, the earlier one is the safer thing to return to because
        less has been built on top of it.
        """
        if not self.candidates:
            return None
        return max(self.candidates, key=lambda c: (c.obs_novelty, -c.turn_index))

    @property
    def has_route(self) -> bool:
        """True when some recorded turn cleared the floor."""
        best = self.best
        return best is not None and best.obs_novelty >= self.novelty_floor

    # -- messages -------------------------------------------------------------

    def _dials_clause(self, reading: Reading) -> str:
        """Both dial readings, each against the threshold it was compared to.

        There is no thrash floor: THRASH is simply stagnation the detector is
        less confident about, i.e. below the ceiling rather than above it. The
        comparison operator flips with ``confident``; the threshold does not.
        """
        operator = ">=" if reading.confident else "<"
        return (
            f"action_sim {reading.action_sim:.3f} {operator} ceiling "
            f"{reading.sim_ceiling:.3f}; obs_novelty {reading.obs_novelty:.3f} "
            f"< floor {reading.novelty_floor:.2f}"
        )

    def _escape_clause(self) -> str:
        """The route, or the explicit statement that there isn't one."""
        best = self.best
        if best is not None and best.obs_novelty >= self.novelty_floor:
            return (
                f"Escape: {best.summary()} produced the most new information "
                f"in this run (novelty {best.obs_novelty:.3f}). Return to that "
                f"result and build on it instead of re-asking."
            )
        # NO-PROGRESS VARIANT. The escape line is dropped entirely.
        if best is None:
            return (
                "No turns have been recorded yet, so there is no prior result to "
                "return to. The task premise or the tool set needs to change."
            )
        return (
            f"No turn in this run has produced new information: the best of "
            f"{len(self.candidates)} turns reached novelty {best.obs_novelty:.3f}, "
            f"below the floor of {self.novelty_floor:.2f}. There is no productive "
            f"path to return to. The task premise or the tool set needs to change."
        )

    def message(self, reading: Reading) -> str:
        """Build the full message for an OPEN decision.

        Contains, per the tightened I1: the turn index, both dial readings, and
        either an escape vector or the explicit no-progress statement.
        """
        if reading.quadrant is Quadrant.THRASH:
            diagnosis = (
                "Actions keep changing but nothing new is coming back. "
                "Stop widening the search and re-read what has already been returned."
            )
        elif reading.quadrant is Quadrant.LOOP:
            diagnosis = (
                "The same question is being asked repeatedly and the answers are "
                "not new. Change the source or the approach, not the wording."
            )
        else:
            # Reachable only if the breaker is opened on a non-tripping quadrant,
            # which the transition table does not allow. Kept honest rather than
            # raising, so a future bug degrades to a vague message not a crash.
            diagnosis = (
                "Progress has stalled. The readings below did not meet the "
                "criteria for a productive turn."
            )

        return (
            f"[plateau:{reading.quadrant.value}] turn {reading.turn_index}: "
            f"{diagnosis} {self._dials_clause(reading)}. {self._escape_clause()}"
        )

    # -- introspection --------------------------------------------------------

    def snapshot(self) -> dict[str, object]:
        best = self.best
        return {
            "turns_recorded": len(self.candidates),
            "has_route": self.has_route,
            "best_turn_index": best.turn_index if best else None,
            "best_novelty": round(best.obs_novelty, 6) if best else None,
            "novelty_floor": self.novelty_floor,
        }
