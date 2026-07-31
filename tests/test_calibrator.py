"""§5 calibrator safety properties C1-C5.

C1 is written before the calibrator exists and is the most important test in the
repo: it is the entire safety argument for self-calibration. If a looping agent
can teach the baseline that looping is normal, the mechanism defeats itself and
every other number we publish is meaningless.

These tests use synthetic (action_sim, obs_novelty) streams. They deliberately
do NOT touch the encoder -- the calibrator's safety must hold as pure arithmetic,
independent of what any embedding model happens to output.
"""

from __future__ import annotations

import pytest

from plateau.calibrator import (
    ALPHA,
    CONSERVATIVE_DEFAULT,
    HARD_HI,
    HARD_LO,
    K_SIGMA,
    MIN_SAMPLES,
    NOVELTY_FLOOR,
    Calibrator,
)


def productive(cal: Calibrator, sims, novelty: float = 0.60) -> None:
    """Feed turns that clear the novelty gate, so the baseline actually learns."""
    for sim in sims:
        cal.update(action_sim=sim, obs_novelty=novelty)


# --- C1: the novelty gate holds ---------------------------------------------
# THE test. A stuck agent produces zero-novelty turns. Those turns must not be
# able to move the baseline in any direction, by any amount, ever.


def test_c1_zero_novelty_turns_cannot_move_the_baseline():
    cal = Calibrator()
    productive(cal, [0.30, 0.32, 0.28, 0.31, 0.29, 0.33])

    mu_before, sigma_before, n_before = cal.mu, cal.sigma, cal.n
    ceiling_before = cal.sim_ceiling

    # 100 turns of a perfectly stuck agent: near-identical actions, no new
    # information at all.
    for _ in range(100):
        cal.update(action_sim=0.99, obs_novelty=0.0)

    assert cal.n == n_before, "n moved: a stuck agent was counted as a sample"
    assert cal.mu == mu_before, "mu moved: a stuck agent taught the baseline"
    assert cal.sigma == sigma_before, "sigma moved: a stuck agent widened tolerance"
    assert cal.sim_ceiling == ceiling_before, "the ceiling drifted upward under a loop"


def test_c1_gate_holds_from_a_cold_start():
    """A calibrator that has only ever seen stuck turns must learn nothing."""
    cal = Calibrator()
    for _ in range(100):
        cal.update(action_sim=0.99, obs_novelty=0.0)

    assert cal.n == 0
    assert cal.mu == 0.0
    assert cal.sigma == 0.0
    # Still in warmup, so still refusing to trip (C3).
    assert cal.sim_ceiling == CONSERVATIVE_DEFAULT


def test_c1_gate_is_strict_below_floor_inclusive_at_floor():
    """Boundary: novelty exactly at the floor counts as informative."""
    at_floor = Calibrator()
    at_floor.update(action_sim=0.5, obs_novelty=NOVELTY_FLOOR)
    assert at_floor.n == 1, "novelty == floor must pass the gate"

    below = Calibrator()
    below.update(action_sim=0.5, obs_novelty=NOVELTY_FLOOR - 1e-9)
    assert below.n == 0, "novelty just below floor must be rejected"


@pytest.mark.parametrize("novelty", [0.0, 0.01, 0.05, 0.1, 0.149])
def test_c1_no_sub_floor_novelty_value_can_teach(novelty):
    cal = Calibrator()
    productive(cal, [0.30] * MIN_SAMPLES)
    snapshot = (cal.n, cal.mu, cal.sigma)

    for _ in range(50):
        cal.update(action_sim=0.995, obs_novelty=novelty)

    assert (cal.n, cal.mu, cal.sigma) == snapshot


def test_c1_every_turn_is_logged_even_when_gated():
    """The gate blocks *learning*, not *observability*.

    The sweep needs the per-turn novelty distribution to pick the floor from
    data, so rejected turns must still be recorded.
    """
    cal = Calibrator()
    for _ in range(10):
        cal.update(action_sim=0.99, obs_novelty=0.0)

    assert cal.n == 0, "gate must still block learning"
    assert len(cal.log) == 10, "gated turns must still be logged"
    assert all(record.gated for record in cal.log)
    assert [record.obs_novelty for record in cal.log] == [0.0] * 10


# --- C2: hard clamps hold ----------------------------------------------------


@pytest.mark.parametrize(
    "sims",
    [
        [1.0] * 40,                       # everything maximally similar
        [0.0] * 40,                       # everything maximally dissimilar
        [0.0, 1.0] * 20,                  # maximum variance -> huge raw sigma
        [1.0, 0.0, 1.0, 0.0, 0.5] * 8,
        [0.999] * 40,
        [-1.0] * 40,                      # cosine's true lower bound
        [-1.0, 1.0] * 20,
    ],
)
def test_c2_sim_ceiling_never_escapes_hard_clamps(sims):
    cal = Calibrator()
    productive(cal, sims)
    assert HARD_LO <= cal.sim_ceiling <= HARD_HI


def test_c2_max_variance_stream_would_exceed_clamp_without_it():
    """Prove the clamp is load-bearing, not decorative.

    An alternating 0/1 stream drives raw mu + k*sigma above HARD_HI. If this
    assertion ever fails, the clamp test above has stopped testing anything.
    """
    cal = Calibrator()
    productive(cal, [0.0, 1.0] * 20)
    raw = cal.mu + K_SIGMA * cal.sigma
    assert raw > HARD_HI, f"raw ceiling {raw} no longer exceeds the clamp"
    assert cal.sim_ceiling == HARD_HI


def test_c2_a_varied_agent_ceiling_is_clearable_by_a_paraphrase():
    """The regime that matters: a heterogeneous agent that then starts looping.

    The old HARD_HI of 0.97 pinned the ceiling above the measured paraphrase
    similarity of 0.8927 for *every* profile, so a reworded loop was invisible by
    construction. It is only defensible for the ceiling to exceed 0.8927 when the
    agent's own normal similarity is already higher than that -- in which case a
    0.89 turn genuinely is less repetitive than its baseline.

    So this asserts the varied case, not all cases: an agent whose actions vary
    must end up with a ceiling a paraphrase can clear.
    """
    PARAPHRASE_SIM = 0.8927
    research = Calibrator()
    productive(research, [0.30, 0.45, 0.22, 0.51, 0.38, 0.29, 0.47, 0.33])
    assert research.sim_ceiling <= PARAPHRASE_SIM, (
        f"ceiling {research.sim_ceiling} blocks a paraphrase at {PARAPHRASE_SIM}"
    )


# --- C3: conservative warmup -------------------------------------------------


def test_c3_ceiling_is_the_default_before_min_samples():
    cal = Calibrator()
    for i in range(MIN_SAMPLES - 1):
        cal.update(action_sim=0.99, obs_novelty=0.60)
        assert cal.n == i + 1
        assert cal.sim_ceiling == CONSERVATIVE_DEFAULT

    cal.update(action_sim=0.99, obs_novelty=0.60)
    assert cal.n == MIN_SAMPLES
    assert cal.is_warm
    assert cal.sim_ceiling != CONSERVATIVE_DEFAULT


def test_c3_warmup_default_errs_toward_not_tripping():
    """A high default means fewer trips, which is the safe direction.

    But not so high that the pattern becomes invisible: the warmup ceiling must
    still sit at or below the measured paraphrase similarity, or an uncalibrated
    detector could never catch a reworded loop. At 0.90 it could not.
    """
    assert CONSERVATIVE_DEFAULT >= 0.60
    assert CONSERVATIVE_DEFAULT <= HARD_HI
    assert CONSERVATIVE_DEFAULT <= 0.8927, "warmup ceiling blocks a measured paraphrase"


# --- C4: task adaptation is real --------------------------------------------


def test_c4_batch_and_research_traces_reach_different_ceilings():
    """The whole justification for self-calibration.

    A batch job legitimately issues near-identical actions turn after turn; a
    research agent's actions vary a lot. If both converge to the same ceiling,
    calibration is doing nothing and a fixed threshold would do as well.
    """
    batch = Calibrator()
    productive(batch, [0.97, 0.96, 0.98, 0.97, 0.95, 0.98, 0.97, 0.96, 0.97, 0.98])

    research = Calibrator()
    productive(research, [0.30, 0.45, 0.22, 0.51, 0.38, 0.29, 0.47, 0.33, 0.41, 0.36])

    assert batch.is_warm and research.is_warm
    assert batch.sim_ceiling > research.sim_ceiling
    # "Measurably" different: a margin far larger than float noise.
    assert batch.sim_ceiling - research.sim_ceiling > 0.10


def test_c4_hard_clamp_pins_a_tight_batch_job_above_its_own_ceiling():
    """Records a real consequence of HARD_HI, found while writing C4.

    A tightly-consistent batch job (invoice extraction: mu ~= 0.97, sigma ~= 0.01)
    has a raw ceiling of mu + 2*sigma ~= 0.988, which HARD_HI clamps down to
    0.97. Its own normal action similarity therefore sits *above* its ceiling, so
    the similarity dial reads "repetitive" on every single turn and contributes
    nothing on this trace class.

    This is not a bug in the calibrator -- the clamp is doing exactly what §5
    says. It is a load-bearing fact about the counter-demo: on the invoice batch
    the entire burden of not-tripping falls on the novelty dial. Gate 1 measured
    that batch action similarity at 0.9913, well above HARD_HI, so this is the
    real operating regime and not a synthetic edge case.

    If this test ever starts failing, the clamp or K_SIGMA changed and the
    counter-demo's safety margin needs re-deriving.
    """
    batch = Calibrator()
    batch_sims = [0.97, 0.96, 0.98, 0.97, 0.95, 0.98, 0.97, 0.96]
    productive(batch, batch_sims)

    raw_ceiling = batch.mu + batch.k_sigma * batch.sigma
    assert raw_ceiling > HARD_HI, "clamp is not engaged; premise of this test changed"
    assert batch.sim_ceiling == HARD_HI
    assert max(batch_sims) > batch.sim_ceiling, (
        "batch similarity no longer exceeds its clamped ceiling -- "
        "re-derive which dial carries the counter-demo"
    )


# --- C5: bounded drift -------------------------------------------------------


def test_c5_single_update_movement_is_bounded_by_alpha():
    cal = Calibrator()
    productive(cal, [0.30] * MIN_SAMPLES)
    assert cal.is_warm

    for target in (1.0, 0.0, 0.75, -1.0):
        for _ in range(20):
            mu_before = cal.mu
            cal.update(action_sim=target, obs_novelty=0.60)
            moved = abs(cal.mu - mu_before)
            bound = ALPHA * abs(target - mu_before)
            assert moved <= bound + 1e-12, f"mu moved {moved}, bound {bound}"


def test_c5_no_unbounded_ratchet_under_sustained_pressure():
    """1000 maximally-similar productive turns must not run mu away."""
    cal = Calibrator()
    productive(cal, [0.30] * MIN_SAMPLES)
    for _ in range(1000):
        cal.update(action_sim=1.0, obs_novelty=0.60)

    assert cal.mu <= 1.0 + 1e-9
    assert HARD_LO <= cal.sim_ceiling <= HARD_HI


def test_c5_drift_is_reversible():
    """Calibration must be able to come back down, not just ratchet up."""
    cal = Calibrator()
    productive(cal, [0.30] * MIN_SAMPLES)
    baseline = cal.mu

    for _ in range(100):
        cal.update(action_sim=0.95, obs_novelty=0.60)
    assert cal.mu > baseline

    for _ in range(200):
        cal.update(action_sim=0.30, obs_novelty=0.60)
    assert cal.mu == pytest.approx(0.30, abs=0.02)


# --- determinism (rule 3) ----------------------------------------------------


def test_calibrator_is_deterministic():
    stream = [(0.3, 0.6), (0.9, 0.0), (0.45, 0.7), (0.99, 0.05), (0.5, 0.9)] * 10

    def run():
        cal = Calibrator()
        for sim, nov in stream:
            cal.update(action_sim=sim, obs_novelty=nov)
        return (cal.n, cal.mu, cal.sigma, cal.sim_ceiling)

    assert run() == run()


def test_fixed_parameters_match_the_spec():
    """§5 fixes these and they are never calibrated. Guard against silent drift."""
    # 0.25, the only grid value inside the measured usable window
    # (0.2311, 0.2572) from metrics.json -> novelty_floor_probe. It was 0.30,
    # which sat above the bottom of the batch band and read 3 of 5 measured
    # batch observations as stagnant.
    assert NOVELTY_FLOOR == 0.25
    assert MIN_SAMPLES == 6
    assert K_SIGMA == 1.0          # PROVISIONAL, moved into the sweep
    assert ALPHA == 0.1
    assert (HARD_LO, HARD_HI) == (0.60, 0.92)
    # The old 0.97 sat so far above every measured profile that the ceiling
    # clamped there universally and no paraphrase could ever clear it.
    assert HARD_HI < 0.97, "regression to the ceiling that hid paraphrase loops"
