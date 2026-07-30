"""§6 -- the two dials and the four-quadrant classifier.

Plateau reads two things per turn and nothing else:

    action_sim    how much this action resembles recent actions
    obs_novelty   how much this observation differs from recent observations

The claim the whole project rests on is that these are *separable*: near-identical
actions can accompany genuinely different observations. Gate 1 measured that
directly (batch actions 0.9913, batch observations 0.5608 similar) and recorded it
in metrics.json.

Crossing the two dials gives five labels. Every turn gets one, because the demo
and counter-demo both read the label, not just the trip decision:

                       learned something          learned nothing
                       (novelty >= floor)         (novelty < floor)
    repetitive action   GRIND                      LOOP        <- trips
    (sim >= ceiling)    a batch job. healthy.      the classic stall.

    varied action       EXPLORE                    THRASH       <- trips
    (sim <= thrash)     open-ended research.       the expensive one.
                        healthy.

    neither             MIDDLE -- never trips, in either column.

GRIND is the counter-demo: repeating yourself while still learning is a batch
job, and no shipped detector can tell it from a stall because they all read only
one half of the turn. THRASH is the one no shipped detector can reach at all,
because reaching it requires noticing that *varied* actions are producing nothing.

DERIVATION NOTE
---------------
The §6 text was not available when this was written. The dial semantics, the five
labels, and "the middle band never trips" are as instructed. The **boundary
conditions** below are derived from the §5 calibrator's two published dials
(``sim_ceiling`` and ``thrash_floor``) and the fixed ``novelty_floor``, because
those are the only thresholds in the design. If §6 specifies different
boundaries -- hysteresis, a different comparison operator, a separate
grind-specific threshold -- this is the file to correct, and the fixture readings
in metrics.json -> detector_fixtures should be re-derived.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from plateau.calibrator import NOVELTY_FLOOR, Calibrator
from plateau.encoder import max_cosine


class Quadrant(str, Enum):
    """Every turn gets exactly one of these."""

    GRIND = "grind"
    LOOP = "loop"
    EXPLORE = "explore"
    THRASH = "thrash"
    MIDDLE = "middle"


#: The two quadrants that open the breaker. GRIND and EXPLORE are healthy;
#: MIDDLE is a deliberate miss (see `quadrant`).
TRIPPING_QUADRANTS = frozenset({Quadrant.LOOP, Quadrant.THRASH})


@dataclass(frozen=True)
class Reading:
    """One turn's two dials plus its verdict.

    Attributes:
        action_sim: max cosine of this action against the window.
        obs_novelty: ``1 - max cosine`` of this observation against the window.
        quadrant: the label. Every turn has one.
        is_trip: whether this reading counts toward opening the breaker.
        turn_index: 0-indexed position in the run.
        sim_ceiling: the ceiling in force when this reading was taken.
        thrash_floor: the thrash floor in force when this reading was taken.
        novelty_floor: the floor in force when this reading was taken.
    """

    action_sim: float
    obs_novelty: float
    quadrant: Quadrant = Quadrant.MIDDLE
    is_trip: bool = False
    turn_index: int = 0
    sim_ceiling: float = 0.0
    thrash_floor: float = 0.0
    novelty_floor: float = NOVELTY_FLOOR


@dataclass
class PlateauConfig:
    """Detector configuration.

    Attributes:
        novelty_floor: the fixed floor. Also the calibration gate; see §5.
        action_only: **ablation switch.** Forces the ``obs_novelty`` term to 0.0,
            reducing Plateau to an action-similarity detector -- i.e. what every
            shipped repetition detector already does. Its purpose is to *fail*:
            with novelty pinned at 0.0 a healthy batch job reads as a stall, so
            the ablation trips on the counter-demo and the full detector does
            not. That contrast is the measurement.
    """

    novelty_floor: float = NOVELTY_FLOOR
    action_only: bool = False


def quadrant(
    action_sim: float,
    obs_novelty: float,
    calibrator: Calibrator,
    config: PlateauConfig | None = None,
) -> Quadrant:
    """Label one reading.

    Boundaries are inclusive at the thresholds: a reading exactly at the ceiling
    counts as repetitive, and one exactly at the floor counts as having learned
    something. Ties resolve toward *not* tripping wherever that choice exists,
    which is the same bias as §5's conservative warmup.
    """
    config = config or PlateauConfig()

    repetitive = action_sim >= calibrator.sim_ceiling
    varied = action_sim <= calibrator.thrash_floor
    learning = obs_novelty >= config.novelty_floor

    # A degenerate calibrator could in principle satisfy both; ceiling above
    # floor is asserted by C2, so `repetitive` wins and this stays unreachable.
    if repetitive:
        return Quadrant.GRIND if learning else Quadrant.LOOP
    if varied:
        return Quadrant.EXPLORE if learning else Quadrant.THRASH

    # MIDDLE: a DELIBERATE MISS, not an oversight.
    #
    # Between thrash_floor and sim_ceiling the action stream is neither
    # repetitive nor varied enough for either signal to mean anything. Tripping
    # here would mean tripping on ordinary work, which is exactly the false-
    # positive every incumbent has filed as an open bug (OpenHands #5355). We
    # accept the miss: a genuine stall drifts toward one of the two extremes and
    # gets caught on a later turn, one turn later at worst. Recall is the price
    # and the sweep publishes it.
    return Quadrant.MIDDLE


class Detector:
    """Owns the encoder, the window, and the calibrator; produces Readings.

    The breaker consumes ``classify`` as its §6 seam. ``evaluate`` is the
    standalone entry point used by the fixtures and the harness, and computes the
    dials itself.
    """

    def __init__(
        self,
        encoder,
        calibrator: Calibrator | None = None,
        config: PlateauConfig | None = None,
        window_size: int = 8,
    ) -> None:
        self.encoder = encoder
        self.config = config or PlateauConfig()
        self.calibrator = calibrator if calibrator is not None else Calibrator(
            novelty_floor=self.config.novelty_floor
        )
        self.window_size = window_size
        self._action_vecs: deque[np.ndarray] = deque(maxlen=window_size)
        self._obs_vecs: deque[np.ndarray] = deque(maxlen=window_size)
        self._turn_index = 0
        self.readings: list[Reading] = []

    # -- dials ----------------------------------------------------------------

    def dials(self, action_vec, obs_vec) -> tuple[float, float]:
        """Compute (action_sim, obs_novelty) against the current window.

        On the first turn the window is empty, so ``max_cosine`` returns 0.0:
        similarity 0.0 and novelty 1.0. A run therefore starts maximally novel,
        which is correct -- nothing has been seen yet to be redundant with.
        """
        action_sim = max_cosine(action_vec, self._action_vecs)
        obs_sim = max_cosine(obs_vec, self._obs_vecs)
        obs_novelty = 1.0 - obs_sim

        if self.config.action_only:
            # THE ABLATION. Pin novelty at 0.0 so the detector can only ever see
            # the action half. Everything then reads as "learned nothing".
            obs_novelty = 0.0

        return action_sim, obs_novelty

    # -- the §6 seam consumed by the breaker ----------------------------------

    def classify(
        self, action_sim: float, obs_novelty: float, calibrator: Calibrator
    ) -> Reading:
        """Label a reading whose dials were computed elsewhere (the breaker)."""
        if self.config.action_only:
            obs_novelty = 0.0
        label = quadrant(action_sim, obs_novelty, calibrator, self.config)
        return Reading(
            action_sim=action_sim,
            obs_novelty=obs_novelty,
            quadrant=label,
            is_trip=label in TRIPPING_QUADRANTS,
            turn_index=self._turn_index,
            sim_ceiling=calibrator.sim_ceiling,
            thrash_floor=calibrator.thrash_floor,
            novelty_floor=self.config.novelty_floor,
        )

    # -- standalone entry point -----------------------------------------------

    def evaluate(self, action_text: str, observation_text: str) -> Reading:
        """Embed one turn, read both dials, label it, and advance the window.

        One encoder call per turn: both halves go through in a single batch.
        """
        vecs = self.encoder.encode([action_text, observation_text])
        action_vec, obs_vec = vecs[0], vecs[1]

        action_sim, obs_novelty = self.dials(action_vec, obs_vec)
        reading = self.classify(action_sim, obs_novelty, self.calibrator)

        # Gate applies here too: only informative turns teach the baseline.
        self.calibrator.update(action_sim=action_sim, obs_novelty=obs_novelty)

        self._action_vecs.append(action_vec)
        self._obs_vecs.append(obs_vec)
        self._turn_index += 1
        self.readings.append(reading)
        return reading

    # -- introspection --------------------------------------------------------

    def quadrant_counts(self) -> dict[str, int]:
        counts = {q.value: 0 for q in Quadrant}
        for reading in self.readings:
            counts[reading.quadrant.value] += 1
        return counts

    def snapshot(self) -> dict[str, object]:
        return {
            "turns": self._turn_index,
            "action_only": self.config.action_only,
            "quadrants": self.quadrant_counts(),
            "calibrator": self.calibrator.snapshot(),
        }
