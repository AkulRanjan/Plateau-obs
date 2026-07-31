"""§6 (revised) -- the trip predicate and the four quadrant labels.

Plateau reads two things per turn:

    action_sim    how much this action resembles recent actions
    obs_novelty   how much this observation differs from recent observations

**Novelty is the trip axis. Similarity only sets the evidence bar.** That is the
central revision, and it came out of measurement rather than preference: three
genuinely different tools (`read_file`, `grep`, `list_dir`) read `action_sim`
0.7397 against the same window, so MiniLM has no low-similarity region for
tool-call strings at all. A thrash floor of the form ``mu - k*sigma`` was looking
for a region that does not exist, so it is gone -- not patched with a constant.

The predicate::

    stagnant  = obs_novelty < NOVELTY_FLOOR            # the trip axis
    confident = action_sim >= calibrator.sim_ceiling    # the evidence bar

    stagnant and confident  ->  loop_hits += 1, stall_hits += 1
    stagnant only           ->  loop_hits  = 0, stall_hits += 1
    neither                 ->  loop_hits  = 0, stall_hits  = 0

    trip = loop_hits >= TRIP_AFTER_LOOP or stall_hits >= TRIP_AFTER_STALL

An unambiguous loop -- the agent asking the same question and getting the same
non-answer -- trips in 3 turns. A stall the detector is less sure about still
trips, but takes 6. Nothing is missed on the novelty axis; low-confidence
stagnation is merely slower to act on, which is the right bias when the cost of a
false trip is interrupting a working agent.

The four labels, kept because the demo and counter-demo both read them:

                       learned something          learned nothing
                       (novelty >= floor)         (novelty < floor)
    confident           GRIND                      LOOP        <- trips at 3
    (sim >= ceiling)    a batch job. healthy.      the classic stall.

    not confident       EXPLORE                    THRASH      <- trips at 6
    (sim <  ceiling)    open-ended research.       varied actions, no progress.
                        healthy.

There is no MIDDLE category. What used to fall there is now THRASH with a slower
trip, which is the honest reading: an agent that has stopped learning has stopped
learning, whether or not its actions look repetitive.

GRIND is the counter-demo. The invoice batch reads `action_sim` 0.9913, which
clears the ceiling comfortably -- so similarity alone would condemn it. It is
protected by novelty (0.4392) and nothing else. That is the joint design earning
its place, and it is pinned by
``test_batch_protected_by_novelty_not_similarity``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Collection

import numpy as np

from plateau.calibrator import NOVELTY_FLOOR, Calibrator
from plateau.encoder import max_cosine

#: Consecutive unambiguous-loop readings before the breaker trips.
#: PROVISIONAL -- sweep owns it.
TRIP_AFTER_LOOP = 3

#: Consecutive stagnant readings of any confidence before the breaker trips.
#: PROVISIONAL -- sweep owns it.
TRIP_AFTER_STALL = 6

#: Value `action_sim` is pinned to under the novelty_only ablation. Below
#: HARD_LO, so `confident` can never be true.
NOVELTY_ONLY_ACTION_SIM = 0.0

#: How many previous turns each dial is measured against.
#:
#: Both dials are `max_cosine` against this window, so a repetition spaced
#: further apart than `window_size` is structurally invisible: the detector
#: cannot see a loop whose period exceeds its own memory. `plateau.breaker`
#: imports this so the live breaker and the evaluated detector cannot drift.
#:
#: Was hard-coded to 8 and swept by nothing. `metrics.json ->
#: long_trace_sweep` now measures it, and it is **the only load-bearing axis of
#: the five**: 432 of 576 configurations are usable, and all 144 failures are
#: exactly the window_size=8 ones. Every value of novelty_floor, k_sigma,
#: trip_after_loop and trip_after_stall is usable. The four parameters that were
#: swept do not change the outcome; the one that was not swept decides it.
#:
#: The usable set is {12, 16, 24}. 16 is taken rather than 12 because the trace
#: that discriminates cycles 12 phrasings, so a window of exactly 12 sits on the
#: boundary and would be a coincidence of that fixture rather than a margin.
#: STILL PROVISIONAL: no measurement here says what a *real* agent's rewording
#: repertoire is, which is what this value has to exceed. See
#: metrics.json -> trail_comparison.
WINDOW_SIZE = 16


class Quadrant(str, Enum):
    """Every turn gets exactly one. There is no MIDDLE."""

    GRIND = "grind"
    LOOP = "loop"
    EXPLORE = "explore"
    THRASH = "thrash"


#: The two stagnant quadrants. Both trip; they differ only in how many
#: consecutive readings it takes.
STAGNANT_QUADRANTS = frozenset({Quadrant.LOOP, Quadrant.THRASH})


@dataclass(frozen=True)
class Reading:
    """One turn's two dials, its label, and the accumulated evidence."""

    action_sim: float
    obs_novelty: float
    quadrant: Quadrant = Quadrant.EXPLORE
    stagnant: bool = False
    confident: bool = False
    loop_hits: int = 0
    stall_hits: int = 0
    is_trip: bool = False
    turn_index: int = 0
    sim_ceiling: float = 0.0
    novelty_floor: float = NOVELTY_FLOOR


@dataclass
class PlateauConfig:
    """Detector configuration, including the two ablation switches.

    Attributes:
        novelty_floor: the fixed floor, and the calibration gate. See §5.
        trip_after_loop: consecutive unambiguous-loop readings before tripping.
        trip_after_stall: consecutive stagnant readings before tripping.
        action_only: **ablation.** Pins ``obs_novelty`` to 0.0, so every turn
            reads as stagnant and only the similarity dial carries information --
            i.e. what every shipped repetition detector already does. Its purpose
            is to *fail*: it must trip on the healthy invoice batch, and the full
            detector must not.
        novelty_only: **ablation.** Pins ``action_sim`` to 0.0, so ``confident``
            is never true and only the ``stall_hits`` path can fire. Isolates what
            the similarity dial contributes. If this matches full Plateau on
            everything except turns-to-detection, that is the honest finding and
            it belongs in the README.
    """

    novelty_floor: float = NOVELTY_FLOOR
    trip_after_loop: int = TRIP_AFTER_LOOP
    trip_after_stall: int = TRIP_AFTER_STALL
    window_size: int = WINDOW_SIZE
    action_only: bool = False
    novelty_only: bool = False

    def __post_init__(self) -> None:
        if self.action_only and self.novelty_only:
            raise ValueError(
                "action_only and novelty_only are mutually exclusive ablations"
            )

    @property
    def label(self) -> str:
        if self.action_only:
            return "plateau_action_only"
        if self.novelty_only:
            return "plateau_novelty_only"
        return "plateau"


def quadrant(stagnant: bool, confident: bool) -> Quadrant:
    """Label a reading from the two predicates."""
    if stagnant:
        return Quadrant.LOOP if confident else Quadrant.THRASH
    return Quadrant.GRIND if confident else Quadrant.EXPLORE


class Detector:
    """Owns the encoder, the window, the calibrator, and the hit counters.

    §6 owns the multi-turn accumulation, because the two thresholds
    (``TRIP_AFTER_LOOP`` and ``TRIP_AFTER_STALL``) apply to two different
    conditions and a single counter cannot express that. The breaker therefore
    opens on ``Reading.is_trip`` rather than counting for itself.
    """

    def __init__(
        self,
        encoder,
        calibrator: Calibrator | None = None,
        config: PlateauConfig | None = None,
        window_size: int | None = None,
    ) -> None:
        self.encoder = encoder
        self.config = config or PlateauConfig()
        self.calibrator = calibrator if calibrator is not None else Calibrator(
            novelty_floor=self.config.novelty_floor
        )
        # The config owns the window so the sweep can vary it; the kwarg stays
        # as an explicit per-instance override for callers that build a Detector
        # without a config.
        window_size = (
            self.config.window_size if window_size is None else window_size
        )
        self.window_size = window_size
        self._action_vecs: deque[np.ndarray] = deque(maxlen=window_size)
        self._obs_vecs: deque[np.ndarray] = deque(maxlen=window_size)
        self._turn_index = 0

        self.loop_hits = 0
        self.stall_hits = 0
        self.readings: list[Reading] = []

    # -- dials ----------------------------------------------------------------

    def dials(self, action_vec, obs_vec) -> tuple[float, float]:
        """Compute (action_sim, obs_novelty) against the current window.

        On the first turn the window is empty, so ``max_cosine`` returns 0.0:
        similarity 0.0 and novelty 1.0. A run starts maximally novel, which is
        correct -- nothing has been seen yet to be redundant with.
        """
        action_sim = max_cosine(action_vec, self._action_vecs)
        # Float error on an identical pair can push cosine a hair above 1.0 and
        # report novelty as -0.0000, which is noise in every log and report.
        obs_novelty = max(0.0, 1.0 - max_cosine(obs_vec, self._obs_vecs))
        return self._apply_ablation(action_sim, obs_novelty)

    def _apply_ablation(self, action_sim: float, obs_novelty: float):
        if self.config.action_only:
            # Blind to the observation half: everything reads as stagnant.
            return action_sim, 0.0
        if self.config.novelty_only:
            # Blind to the action half: `confident` can never be true.
            return NOVELTY_ONLY_ACTION_SIM, obs_novelty
        return action_sim, obs_novelty

    # -- the predicate --------------------------------------------------------

    def classify(
        self,
        action_sim: float,
        obs_novelty: float,
        calibrator: Calibrator,
        idempotent: bool = False,
    ) -> Reading:
        """Apply the §6 predicate and advance the hit counters.

        Called once per turn -- by :meth:`evaluate`, or by the breaker as its §6
        seam. Calling it twice for one turn would double-count.

        ``idempotent`` is the declaration the caller makes about the *tool*, not
        about this turn. A tool that legitimately returns near-identical
        observations -- a poller, a clock, a status endpoint -- is
        informationally stalled by construction, and the measured novelty
        distribution shows pollers (0.0067-0.2311) overlapping the loop band, so
        no floor can separate the two. The turn is still embedded, still
        labelled, and still enters the window; it simply carries **no evidence
        either way**, so the counters are neither advanced nor reset.

        This is a burden on the caller, not a detection. Plateau does not solve
        the poller case -- it requires the tool author to declare it.
        """
        action_sim, obs_novelty = self._apply_ablation(action_sim, obs_novelty)

        stagnant = obs_novelty < self.config.novelty_floor
        confident = action_sim >= calibrator.sim_ceiling

        if idempotent:
            pass  # No evidence in either direction. Hold, do not reset.
        elif stagnant and confident:
            self.loop_hits += 1
            self.stall_hits += 1
        elif stagnant:
            self.loop_hits = 0
            self.stall_hits += 1
        else:
            self.loop_hits = 0
            self.stall_hits = 0

        is_trip = (
            self.loop_hits >= self.config.trip_after_loop
            or self.stall_hits >= self.config.trip_after_stall
        )

        return Reading(
            action_sim=action_sim,
            obs_novelty=obs_novelty,
            quadrant=quadrant(stagnant, confident),
            stagnant=stagnant,
            confident=confident,
            loop_hits=self.loop_hits,
            stall_hits=self.stall_hits,
            is_trip=is_trip,
            turn_index=self._turn_index,
            sim_ceiling=calibrator.sim_ceiling,
            novelty_floor=self.config.novelty_floor,
        )

    def reset_hits(self) -> None:
        """Clear accumulated evidence. Called by the breaker on §8 transition 7."""
        self.loop_hits = 0
        self.stall_hits = 0

    # -- standalone entry point -----------------------------------------------

    def evaluate(
        self,
        action_text: str,
        observation_text: str,
        idempotent: bool = False,
    ) -> Reading:
        """Embed one turn, read both dials, label it, advance the window.

        One encoder call per turn: both halves go through in a single batch.
        """
        vecs = self.encoder.encode([action_text, observation_text])
        action_vec, obs_vec = vecs[0], vecs[1]

        action_sim, obs_novelty = self.dials(action_vec, obs_vec)
        reading = self.classify(
            action_sim, obs_novelty, self.calibrator, idempotent=idempotent
        )

        # The gate applies here too: only informative turns teach the baseline.
        self.calibrator.update(action_sim=action_sim, obs_novelty=obs_novelty)

        self._action_vecs.append(action_vec)
        self._obs_vecs.append(obs_vec)
        self._turn_index += 1
        self.readings.append(reading)
        return reading

    def run(self, turns, idempotent_tools: Collection[str] = ()) -> int | None:
        """Evaluate a whole trace. Returns the 0-indexed trip turn, or None.

        Matches the baselines' ``detect(turns) -> int | None`` contract so the
        harness can treat Plateau and the ported detectors identically.

        ``idempotent_tools`` names the tools whose turns carry no evidence -- see
        :meth:`classify`. The tool name is the action string up to its first
        ``(``, the same convention the baseline adapter uses.
        """
        idempotent_tools = frozenset(idempotent_tools)
        for action_text, observation_text in turns:
            idempotent = action_text.split("(")[0] in idempotent_tools
            if self.evaluate(
                action_text, observation_text, idempotent=idempotent
            ).is_trip:
                return self._turn_index - 1
        return None

    # -- introspection --------------------------------------------------------

    def quadrant_counts(self) -> dict[str, int]:
        counts = {q.value: 0 for q in Quadrant}
        for reading in self.readings:
            counts[reading.quadrant.value] += 1
        return counts

    def snapshot(self) -> dict[str, object]:
        return {
            "variant": self.config.label,
            "turns": self._turn_index,
            "loop_hits": self.loop_hits,
            "stall_hits": self.stall_hits,
            "quadrants": self.quadrant_counts(),
            "calibrator": self.calibrator.snapshot(),
        }
