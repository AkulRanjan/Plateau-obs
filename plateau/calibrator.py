"""§5 -- self-calibrating action-similarity baseline.

The principle: calibrate the dial that is task-dependent (action similarity),
hold fixed the one that is not (the novelty floor). A batch job and an
open-ended research agent have genuinely different "normal" action similarity,
so a single fixed similarity threshold must either miss loops on one or
false-trip on the other. Novelty does not have that problem -- "learned nothing"
means the same thing on every task -- so it stays fixed.

The danger this creates is obvious and is the thing to defend: an adaptive
baseline can be taught. A looping agent emits high-similarity turns; if those
turns updated the baseline, the baseline would learn that looping is normal and
the detector would talk itself out of tripping.

The defence is to anchor every update on information gain. A turn may only
teach the baseline if it produced new information. A stuck agent produces none
by definition, so it cannot move the baseline -- not slowly, not at all. That is
property C1 and it is enforced by the first branch of :meth:`Calibrator.update`.

Three further guards sit behind the gate:

* a conservative warmup -- before ``MIN_SAMPLES`` productive turns the ceiling
  is a high fixed default, so an uncalibrated detector errs toward not tripping;
* hard clamps -- the ceiling is confined to ``[0.55, 0.97]`` whatever the
  statistics say, so no input stream can drive it to a degenerate value;
* bounded drift -- once warm, updates are EWMA with a fixed ``ALPHA``, so a
  single turn can move the baseline by at most ``ALPHA`` of the residual.

This module is pure arithmetic. It holds no encoder reference and performs no
I/O, so its safety properties are independent of what any embedding model
happens to output.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Fixed parameters (§5). Never calibrated. --------------------------------

#: Minimum observation novelty for a turn to be allowed to teach the baseline.
#:
#: PLACEHOLDER, PENDING SWEEP. This value was chosen, not measured, and by rule 1
#: it does not count as a result until eval/sweep.py produces it from data.
#: scripts/novelty_floor_check.py records the distribution it has to separate
#: (metrics.json -> novelty_floor_probe).
NOVELTY_FLOOR = 0.15

#: Productive turns required before the learned ceiling is trusted at all.
MIN_SAMPLES = 6

#: Ceiling is mu + K_SIGMA * sigma.
K_SIGMA = 2.0

#: EWMA weight once warm. Bounds per-turn movement (C5).
ALPHA = 0.1

#: Ceiling used during warmup. High on purpose: errs toward not tripping.
CONSERVATIVE_DEFAULT = 0.90

#: Hard clamps on the similarity ceiling. Load-bearing, not decorative --
#: a maximum-variance input stream drives the raw value past HARD_HI.
HARD_LO = 0.55
HARD_HI = 0.97

#: Hard clamps on the thrash floor.
THRASH_LO = 0.05
THRASH_HI = 0.50


def clamp(value: float, lo: float, hi: float) -> float:
    """Confine ``value`` to ``[lo, hi]``."""
    return lo if value < lo else hi if value > hi else value


@dataclass(frozen=True)
class CalibrationRecord:
    """One observed turn, whether or not it was allowed to teach the baseline.

    §5 requires ``obs_novelty`` to be logged for *every* turn from day one,
    including during CALIBRATING and including turns the gate rejects. The sweep
    needs the per-trace-class novelty distribution in order to choose the floor
    from data rather than from assertion, and it can only do that if the
    rejected turns were kept.
    """

    turn_index: int
    action_sim: float
    obs_novelty: float
    gated: bool
    n_after: int
    mu_after: float
    sigma_after: float
    sim_ceiling_after: float
    thrash_floor_after: float


@dataclass
class Calibrator:
    """Learns this agent's normal action similarity, from productive turns only.

    Attributes:
        n: count of turns that passed the novelty gate. Not the turn count.
        mu: running mean action similarity over productive turns.
        log: every turn seen, gated or not.
    """

    novelty_floor: float = NOVELTY_FLOOR
    min_samples: int = MIN_SAMPLES
    k_sigma: float = K_SIGMA
    alpha: float = ALPHA
    conservative_default: float = CONSERVATIVE_DEFAULT
    hard_lo: float = HARD_LO
    hard_hi: float = HARD_HI
    thrash_lo: float = THRASH_LO
    thrash_hi: float = THRASH_HI

    n: int = 0
    mu: float = 0.0

    #: Welford's sum of squared deviations, used while n <= min_samples.
    _m2: float = 0.0
    #: EWMA variance, seeded from the Welford variance at the phase switch.
    _var_ewma: float | None = None
    #: Turns observed, gated or not. Distinct from n.
    _turns_seen: int = 0

    log: list[CalibrationRecord] = field(default_factory=list)

    # -- the gate -------------------------------------------------------------

    def update(self, action_sim: float, obs_novelty: float) -> None:
        """Observe one turn, and learn from it only if it taught us something.

        Args:
            action_sim: similarity of this turn's action to recent actions.
            obs_novelty: novelty of this turn's observation, ``1 - cos``.
        """
        turn_index = self._turns_seen
        self._turns_seen += 1

        # THE GATE (C1). Non-negotiable: only turns that produced new
        # information are allowed to teach the baseline what normal looks like.
        # A stuck agent produces no new information, so it cannot move mu,
        # sigma, or n -- which is what stops it teaching the detector that
        # being stuck is normal.
        gated = obs_novelty < self.novelty_floor
        if not gated:
            self.n += 1
            if self.n <= self.min_samples:
                self._welford_update(action_sim)
            else:
                self._ewma_update(action_sim)

        # Logged either way. The gate blocks learning, not observability.
        self.log.append(
            CalibrationRecord(
                turn_index=turn_index,
                action_sim=action_sim,
                obs_novelty=obs_novelty,
                gated=gated,
                n_after=self.n,
                mu_after=self.mu,
                sigma_after=self.sigma,
                sim_ceiling_after=self.sim_ceiling,
                thrash_floor_after=self.thrash_floor,
            )
        )

    # -- estimators -----------------------------------------------------------

    def _welford_update(self, x: float) -> None:
        """Exact running mean/variance for the first ``min_samples`` samples.

        Welford rather than EWMA during warmup because with n<=6 an EWMA is
        still dominated by its initial value and would understate the spread.
        """
        delta = x - self.mu
        self.mu += delta / self.n
        self._m2 += delta * (x - self.mu)

    def _ewma_update(self, x: float) -> None:
        """Bounded-drift update once warm (C5).

        Seeds its variance from the Welford estimate on the first call so the
        phase switch is continuous.
        """
        if self._var_ewma is None:
            self._var_ewma = self._welford_variance()

        residual = x - self.mu
        # mu moves by exactly alpha * residual, so |dmu| <= alpha * |x - mu|.
        self.mu += self.alpha * residual
        # EWMA variance uses the pre-update residual, the standard form.
        self._var_ewma = (1.0 - self.alpha) * self._var_ewma + self.alpha * residual * residual

    def _welford_variance(self) -> float:
        """Sample variance (ddof=1). Zero until there are two samples."""
        if self.n < 2:
            return 0.0
        return self._m2 / (self.n - 1)

    @property
    def sigma(self) -> float:
        """Standard deviation of action similarity over productive turns."""
        var = self._var_ewma if self._var_ewma is not None else self._welford_variance()
        return var**0.5 if var > 0.0 else 0.0

    @property
    def is_warm(self) -> bool:
        """True once enough productive turns exist to trust the learned dials."""
        return self.n >= self.min_samples

    # -- the two dials --------------------------------------------------------

    @property
    def sim_ceiling(self) -> float:
        """Action similarity at or above which a turn reads as repetitive."""
        if not self.is_warm:
            return self.conservative_default
        raw = self.mu + self.k_sigma * self.sigma
        return clamp(raw, self.hard_lo, self.hard_hi)

    @property
    def thrash_floor(self) -> float:
        """Action similarity at or below which a turn reads as thrashing.

        Returns 0.0 during warmup: cosine similarity cannot fall below a floor
        of zero in a way that trips, so thrash detection is disabled until the
        baseline is trustworthy (C3).
        """
        if not self.is_warm:
            return 0.0
        return clamp(self.mu - self.k_sigma * self.sigma, self.thrash_lo, self.thrash_hi)

    # -- introspection --------------------------------------------------------

    @property
    def turns_seen(self) -> int:
        """Total turns observed, including gate-rejected ones."""
        return self._turns_seen

    def novelty_series(self) -> list[float]:
        """Per-turn observation novelty, in order. Consumed by the sweep."""
        return [record.obs_novelty for record in self.log]

    def snapshot(self) -> dict[str, float | int | bool]:
        """Current state, for metrics.json and for the CLOSED-transition log."""
        return {
            "n": self.n,
            "turns_seen": self._turns_seen,
            "mu": self.mu,
            "sigma": self.sigma,
            "is_warm": self.is_warm,
            "sim_ceiling": self.sim_ceiling,
            "thrash_floor": self.thrash_floor,
            "novelty_floor": self.novelty_floor,
        }
