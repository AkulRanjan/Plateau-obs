"""§8 -- the four-state circuit breaker.

CALIBRATING -> CLOSED -> OPEN -> HALF_OPEN -> CLOSED

Implements exactly the eight transitions tabled in §8 and nothing else. In
particular there is **no OPEN -> CLOSED path that skips the probe**: recovery is
earned by an evaluated probe or not at all (invariant I3).

Two design points from §8 that are easy to get wrong and are enforced by tests:

* **The probe is judged on novelty alone.** Action similarity is not consulted.
  We tripped because the agent stopped learning; learning again is the only
  evidence that matters. An agent that recovers by re-running a similar action
  against a newly-fixed environment must be allowed to recover.
* **The calibrator survives recovery.** Transition 7 clears the window only.
  Resetting the learned baseline on every trip would throw away the task
  adaptation that justifies the mechanism, and would let a flapping agent
  repeatedly reset itself into the conservative warmup default.

While OPEN the breaker performs **zero** embedding work (invariant I2). That is
the cost argument: a tripped breaker is free, so leaving it tripped is cheap.

Separation of concerns: this module owns state, the window, and the encoder. It
does **not** decide what counts as a trip -- that is §6's four-quadrant
classifier, injected as `classify`. The seam exists so the state machine can be
tested against a fake classifier without depending on §6.
"""

from __future__ import annotations

import dataclasses
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol, Sequence

import numpy as np

from plateau.calibrator import Calibrator
from plateau.detector import Quadrant, Reading
from plateau.encoder import max_cosine
from plateau.escape import EscapeTracker

# --- Fixed parameters (§5). ---------------------------------------------------
#: §6 (revised) owns the multi-turn accumulation, because TRIP_AFTER_LOOP and
#: TRIP_AFTER_STALL apply to two different conditions and one counter cannot
#: express both. The breaker therefore opens on the first reading whose is_trip
#: is True, and this degenerates to 1. It stays a parameter so a test can force
#: multi-reading behaviour when exercising row 3.
TRIP_AFTER = 1
WINDOW_SIZE = 8
COOLDOWN_TURNS = 1

# --- UNSPECIFIED IN §5/§8. Provisional; awaiting a decision. ------------------
# §8 transition 8 uses both of these but neither appears in §5's fixed-parameter
# table. These values were chosen, not measured or specified, and are flagged the
# same way novelty_floor is: they do not count as design until confirmed.
BACKOFF = 2.0
MAX_COOLDOWN = 8


class State(str, Enum):
    """The four states. No others exist."""

    CALIBRATING = "CALIBRATING"
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class Classifier(Protocol):
    """§6's four-quadrant classifier. Injected, not implemented here."""

    def __call__(
        self, action_sim: float, obs_novelty: float, calibrator: Calibrator
    ) -> Reading: ...


@dataclass(frozen=True)
class Decision:
    """What the breaker decided about one turn.

    Attributes:
        message: the §7 message. On an OPEN decision this carries the turn index,
            both dial readings, and either an escape vector or the explicit
            no-progress statement (invariant I1, tightened).
    """

    allowed: bool
    state: State
    reason: str = ""
    message: str = ""
    reading: Reading | None = None
    is_probe: bool = False
    embedded: bool = False
    transition: int = 0


@dataclass
class _WindowEntry:
    action_text: str
    action_vec: np.ndarray
    obs_vec: np.ndarray


class Breaker:
    """The §8 state machine.

    Args:
        encoder: anything with ``encode(list[str]) -> ndarray``. Held so that
            embedding can be *skipped* while OPEN, which is what makes I2
            testable with a counting mock.
        classify: §6's classifier.
        calibrator: §5 calibrator. Survives recovery by design.
    """

    def __init__(
        self,
        encoder,
        classify: Classifier,
        calibrator: Calibrator | None = None,
        trip_after: int = TRIP_AFTER,
        window_size: int = WINDOW_SIZE,
        cooldown_turns: int = COOLDOWN_TURNS,
        backoff: float = BACKOFF,
        max_cooldown: int = MAX_COOLDOWN,
    ) -> None:
        self.encoder = encoder
        self.classify = classify
        self.calibrator = calibrator if calibrator is not None else Calibrator()

        self.trip_after = trip_after
        self.window_size = window_size
        self.cooldown_turns = cooldown_turns
        self.backoff = backoff
        self.max_cooldown = max_cooldown

        self.state = State.CALIBRATING
        self.hits = 0
        self.cooldown = 0
        self.turn_index = 0
        self.window: deque[_WindowEntry] = deque(maxlen=window_size)

        #: §7. Records every turn in every state, including CALIBRATING, because
        #: the most informative action often precedes the breaker being armed.
        self.escape = EscapeTracker(novelty_floor=self.calibrator.novelty_floor)

        #: Frozen at trip time. The probe is judged against this, not against a
        #: window the probe itself has already modified.
        self._pretrip_window: list[_WindowEntry] = []
        self._initial_ceiling: float | None = None
        self.transitions: list[int] = []
        self.trip_count = 0

        #: Set at trip time (transition 4), read while OPEN. I1 requires both to
        #: be non-empty whenever the state is OPEN.
        self._open_reason: str = ""
        self._open_message: str = ""
        self._open_reading: Reading | None = None

    # -- helpers --------------------------------------------------------------

    @property
    def novelty_floor(self) -> float:
        """The fixed floor. Owned by the calibrator, never recalibrated."""
        return self.calibrator.novelty_floor

    def _embed_turn(self, action_text: str, observation_text: str):
        vecs = self.encoder.encode([action_text, observation_text])
        return vecs[0], vecs[1]

    def _dials(self, action_vec, obs_vec, window: Sequence[_WindowEntry]):
        action_sim = max_cosine(action_vec, [entry.action_vec for entry in window])
        obs_sim = max_cosine(obs_vec, [entry.obs_vec for entry in window])
        return action_sim, 1.0 - obs_sim

    def _record(self, transition: int) -> None:
        self.transitions.append(transition)

    def _stamp(self, reading: Reading) -> Reading:
        """Put the breaker's turn index on a reading.

        The §6 detector only advances its own counter inside `evaluate()`. When
        the breaker drives classification directly the detector never sees a
        turn boundary, so its index stays at 0 and every §7 message would claim
        "turn 0". The breaker owns the authoritative counter, so it stamps.
        """
        return dataclasses.replace(reading, turn_index=self.turn_index)

    # -- the machine ----------------------------------------------------------

    def observe(self, action_text: str, observation_text: str) -> Decision:
        """Feed one turn through the state machine.

        Returns a :class:`Decision`. When ``allowed`` is False the caller must
        not execute the action; ``reason`` and ``escape_vector`` explain why.
        """
        # --- transitions 5 and 6: OPEN. No embedding happens here at all. ---
        if self.state is State.OPEN:
            if self.cooldown > 0:
                # Transition 5: still cooling down. Refuse, do not embed.
                self.cooldown -= 1
                self._record(5)
                return Decision(
                    allowed=False,
                    state=State.OPEN,
                    reason=self._open_reason,
                    message=self._open_message,
                    reading=self._open_reading,
                    embedded=False,
                    transition=5,
                )
            # Transition 6: cooldown spent. Allow exactly one probe.
            self.state = State.HALF_OPEN
            self._record(6)
            return Decision(
                allowed=True,
                state=State.HALF_OPEN,
                reason="cooldown elapsed; allowing one probe",
                message=self._open_message,
                reading=self._open_reading,
                is_probe=True,
                embedded=False,
                transition=6,
            )

        # --- everything below embeds ---
        action_vec, obs_vec = self._embed_turn(action_text, observation_text)

        # --- transitions 7 and 8: HALF_OPEN, evaluating the probe ---
        if self.state is State.HALF_OPEN:
            # Judged against the PRE-TRIP window, on novelty alone. action_sim is
            # computed only to feed the calibrator on success -- it plays no part
            # in the pass/fail decision.
            action_sim, probe_novelty = self._dials(action_vec, obs_vec, self._pretrip_window)

            probe_reading = self._stamp(
                self.classify(action_sim, probe_novelty, self.calibrator)
            )
            # §7: the probe is a turn like any other and is recorded.
            self.escape.record(
                turn_index=self.turn_index,
                action_text=action_text,
                obs_novelty=probe_novelty,
                state=State.HALF_OPEN.value,
            )
            self.turn_index += 1

            if probe_novelty >= self.novelty_floor:
                # Transition 7: recovered. Clear the window, seed with the probe,
                # reset hits. The calibrator is deliberately NOT reset.
                self.state = State.CLOSED
                self.hits = 0
                self.window.clear()
                self.window.append(
                    _WindowEntry(action_text=action_text, action_vec=action_vec, obs_vec=obs_vec)
                )
                self.cooldown = 0
                self.calibrator.update(action_sim=action_sim, obs_novelty=probe_novelty)
                # §8 row 7 resets hits. §6 holds the real counters, so clear
                # those too or a stale loop_hits re-trips on the next turn (I4).
                reset = getattr(self.classify, "__self__", None)
                if reset is not None and hasattr(reset, "reset_hits"):
                    reset.reset_hits()
                self._record(7)
                return Decision(
                    allowed=True,
                    state=State.CLOSED,
                    reason=f"probe produced new information (novelty {probe_novelty:.3f})",
                    reading=probe_reading,
                    is_probe=True,
                    embedded=True,
                    transition=7,
                )

            # Transition 8: probe learned nothing. Back to OPEN, longer cooldown.
            self.state = State.OPEN
            self.cooldown = min(
                int(round(max(self.cooldown, 1) * self.backoff)), self.max_cooldown
            )
            self._open_reading = probe_reading
            self._open_reason = (
                f"probe produced no new information "
                f"(novelty {probe_novelty:.3f} < floor {self.novelty_floor})"
            )
            self._open_message = self.escape.message(probe_reading)
            self._record(8)
            return Decision(
                allowed=False,
                state=State.OPEN,
                reason=self._open_reason,
                message=self._open_message,
                reading=probe_reading,
                is_probe=True,
                embedded=True,
                transition=8,
            )

        # --- transitions 1-4: CALIBRATING and CLOSED ---
        action_sim, obs_novelty = self._dials(action_vec, obs_vec, self.window)
        reading = self._stamp(self.classify(action_sim, obs_novelty, self.calibrator))

        # §7: record BEFORE any state decision, so CALIBRATING turns count. The
        # most informative action in a run is often one of the first.
        self.escape.record(
            turn_index=self.turn_index,
            action_text=action_text,
            obs_novelty=obs_novelty,
            state=self.state.value,
        )
        self.turn_index += 1

        if self.state is State.CALIBRATING:
            # Transition 1: learn, never trip.
            self.calibrator.update(action_sim=action_sim, obs_novelty=obs_novelty)
            self.window.append(
                _WindowEntry(action_text=action_text, action_vec=action_vec, obs_vec=obs_vec)
            )
            if self.calibrator.n >= self.calibrator.min_samples:
                # Transition 2: warm. Freeze and log the initial ceiling.
                self.state = State.CLOSED
                self._initial_ceiling = self.calibrator.sim_ceiling
                self._record(2)
                return Decision(
                    allowed=True,
                    state=State.CLOSED,
                    reason=f"calibrated; initial ceiling {self._initial_ceiling:.4f}",
                    reading=reading,
                    embedded=True,
                    transition=2,
                )
            self._record(1)
            return Decision(
                allowed=True,
                state=State.CALIBRATING,
                reason="calibrating",
                reading=reading,
                embedded=True,
                transition=1,
            )

        # CLOSED
        if reading.is_trip:
            self.hits += 1
        else:
            self.hits = 0

        if self.hits >= self.trip_after:
            # Transition 4: open. Freeze the window, emit reason + §7 message.
            self._pretrip_window = list(self.window)
            self._open_reason = (
                f"loop_hits={reading.loop_hits} stall_hits={reading.stall_hits} "
                f"({reading.quadrant.value}); "
                f"action_sim {reading.action_sim:.3f} vs ceiling "
                f"{self.calibrator.sim_ceiling:.3f}, novelty {reading.obs_novelty:.3f} "
                f"vs floor {self.novelty_floor}"
            )
            self._open_reading = reading
            self._open_message = self.escape.message(reading)
            self.state = State.OPEN
            self.cooldown = self.cooldown_turns
            self.trip_count += 1
            self._record(4)
            return Decision(
                allowed=False,
                state=State.OPEN,
                reason=self._open_reason,
                message=self._open_message,
                reading=reading,
                embedded=True,
                transition=4,
            )

        # Transition 3: stay closed. Append, learn (gated), track.
        self.calibrator.update(action_sim=action_sim, obs_novelty=obs_novelty)
        self.window.append(
            _WindowEntry(action_text=action_text, action_vec=action_vec, obs_vec=obs_vec)
        )
        self._record(3)
        return Decision(
            allowed=True,
            state=State.CLOSED,
            reason="",
            reading=reading,
            embedded=True,
            transition=3,
        )
