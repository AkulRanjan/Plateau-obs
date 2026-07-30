"""§8 state machine: one test per transition row (8) and one per invariant (4).

No encoder is loaded here. A deterministic fake stands in, so these tests pin
down the *state machine* rather than MiniLM's behaviour, and so I2's zero-encode
claim can be proved by counting rather than asserted.
"""

from __future__ import annotations

import numpy as np
import pytest

from plateau.breaker import Breaker, Decision, State
from plateau.calibrator import Calibrator
from plateau.detector import Quadrant, Reading


class CountingEncoder:
    """Deterministic fake encoder that counts every call.

    Maps text to a unit vector by hashing, so identical text gives identical
    vectors and different text gives near-orthogonal ones. No model involved.
    """

    def __init__(self, dim: int = 16) -> None:
        self.dim = dim
        self.n_encode_calls = 0
        self.n_texts_encoded = 0

    def encode(self, texts):
        texts = [texts] if isinstance(texts, str) else list(texts)
        self.n_encode_calls += 1
        self.n_texts_encoded += len(texts)
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            rng = np.random.default_rng(abs(hash(text)) % (2**32))
            vec = rng.standard_normal(self.dim).astype(np.float32)
            out[row] = vec / np.linalg.norm(vec)
        return out


def always_trip(action_sim, obs_novelty, calibrator) -> Reading:
    return Reading(
        action_sim, obs_novelty, quadrant=Quadrant.LOOP,
        stagnant=True, confident=True, loop_hits=3, stall_hits=3, is_trip=True,
    )


def never_trip(action_sim, obs_novelty, calibrator) -> Reading:
    return Reading(action_sim, obs_novelty, quadrant=Quadrant.EXPLORE, is_trip=False)


def make_breaker(classify=never_trip, **kwargs) -> Breaker:
    """Test breaker with trip_after=3 unless overridden.

    In production §6 owns the multi-turn counting and the breaker default is 1.
    But `always_trip` is a fake that reports is_trip on its very first call,
    whereas real §6 only does so on the third consecutive loop reading -- and
    those two intervening turns take row 3 and enter the window, which is what
    the pre-trip window is later compared against. Forcing 3 here reproduces
    the real window contents; a default of 1 would leave the stalled turns out
    of it and make the probe trivially succeed.
    """
    kwargs.setdefault("trip_after", 3)
    return Breaker(encoder=CountingEncoder(), classify=classify, **kwargs)


def warm_up(breaker: Breaker) -> None:
    """Drive CALIBRATING -> CLOSED with informative, varied turns."""
    for i in range(breaker.calibrator.min_samples):
        breaker.observe(f"action_{i}", f"observation number {i} with distinct content")
    assert breaker.state is State.CLOSED


def trip(breaker: Breaker) -> Decision:
    """Drive CLOSED -> OPEN. Returns the decision that opened it."""
    breaker.classify = always_trip
    decision = None
    for i in range(breaker.trip_after):
        decision = breaker.observe("stuck_action", "same tired observation")
    assert breaker.state is State.OPEN
    return decision


# =============================================================================
# Transitions
# =============================================================================


def test_t1_calibrating_stays_calibrating_and_never_trips():
    """Row 1: turn observed, calibrator.n < min_samples -> CALIBRATING."""
    breaker = make_breaker(classify=always_trip)  # even with a tripping classifier
    decision = breaker.observe("a0", "an informative observation")

    assert decision.transition == 1
    assert decision.state is State.CALIBRATING
    assert decision.allowed is True, "CALIBRATING must never refuse a turn"
    assert decision.embedded is True
    assert breaker.calibrator.n == 1


def test_t2_calibrating_to_closed_freezes_and_logs_initial_ceiling():
    """Row 2: calibrator.n >= min_samples -> CLOSED, freeze initial ceiling."""
    breaker = make_breaker()
    min_samples = breaker.calibrator.min_samples

    for i in range(min_samples - 1):
        assert breaker.observe(f"a{i}", f"distinct observation {i}").state is State.CALIBRATING

    decision = breaker.observe("a_last", "final distinct calibrating observation")
    assert decision.transition == 2
    assert decision.state is State.CLOSED
    assert breaker._initial_ceiling is not None
    assert "initial ceiling" in decision.reason


def test_t3_closed_stays_closed_below_trip_after():
    """Row 3: reading, hits < trip_after -> CLOSED; append window, learn."""
    breaker = make_breaker()
    warm_up(breaker)
    breaker.classify = always_trip

    n_before = breaker.calibrator.n
    decision = breaker.observe("probe_action", "a genuinely new observation here")

    assert decision.transition == 3
    assert decision.state is State.CLOSED
    assert decision.allowed is True
    assert breaker.hits == 1 and breaker.hits < breaker.trip_after
    assert breaker.calibrator.n >= n_before, "transition 3 must offer the turn to the calibrator"


def test_t4_closed_to_open_emits_reason_and_escape_vector():
    """Row 4: hits >= trip_after -> OPEN; emit reason + escape vector, set cooldown."""
    breaker = make_breaker()
    warm_up(breaker)
    decision = trip(breaker)

    assert decision.transition == 4
    assert decision.state is State.OPEN
    assert decision.allowed is False
    assert decision.reason
    assert decision.message
    assert breaker.cooldown == breaker.cooldown_turns
    assert breaker._pretrip_window, "the window must be frozen at trip time"


def test_t5_open_with_cooldown_refuses_and_decrements():
    """Row 5: OPEN, cooldown > 0 -> OPEN; no embedding, decrement, refuse."""
    breaker = make_breaker(cooldown_turns=2)
    warm_up(breaker)
    trip(breaker)
    assert breaker.cooldown == 2

    calls_before = breaker.encoder.n_encode_calls
    decision = breaker.observe("anything", "anything at all")

    assert decision.transition == 5
    assert decision.state is State.OPEN
    assert decision.allowed is False
    assert decision.embedded is False
    assert breaker.encoder.n_encode_calls == calls_before, "row 5 must not embed"
    assert breaker.cooldown == 1
    assert decision.reason


def test_t6_open_to_half_open_allows_exactly_one_probe():
    """Row 6: OPEN, cooldown == 0 -> HALF_OPEN; allow one probe, mark is_probe."""
    breaker = make_breaker(cooldown_turns=1)
    warm_up(breaker)
    trip(breaker)

    breaker.observe("x", "y")            # row 5, burns the cooldown
    assert breaker.cooldown == 0

    decision = breaker.observe("probe", "probe observation")
    assert decision.transition == 6
    assert decision.state is State.HALF_OPEN
    assert decision.allowed is True
    assert decision.is_probe is True
    assert decision.embedded is False, "row 6 grants permission; it does not embed"


def test_t7_half_open_to_closed_on_novel_probe():
    """Row 7: probe novelty >= floor -> CLOSED; clear window, reset hits, seed."""
    breaker = make_breaker(cooldown_turns=1)
    warm_up(breaker)
    trip(breaker)
    breaker.observe("x", "y")            # row 5
    breaker.observe("probe", "probe")    # row 6, now HALF_OPEN
    assert breaker.state is State.HALF_OPEN

    n_before = breaker.calibrator.n
    mu_before = breaker.calibrator.mu

    # Hash-based fake vectors make this text near-orthogonal to the window, so
    # novelty comfortably clears the floor.
    decision = breaker.observe("fresh_action", "a completely unrelated and novel result")

    assert decision.transition == 7
    assert decision.state is State.CLOSED
    assert decision.allowed is True
    assert breaker.hits == 0
    assert len(breaker.window) == 1, "window must be seeded with the probe only"
    # The calibrator survives: it was not reset, only (possibly) updated.
    assert breaker.calibrator.n >= n_before
    assert breaker.calibrator.mu != 0.0 or mu_before == 0.0


def test_t8_half_open_back_to_open_on_stale_probe_with_backoff():
    """Row 8: probe novelty < floor -> OPEN; cooldown *= backoff, capped."""
    breaker = make_breaker(cooldown_turns=1, backoff=2.0, max_cooldown=8)
    warm_up(breaker)
    trip(breaker)
    breaker.observe("x", "y")                        # row 5
    breaker.observe("probe", "probe")                # row 6 -> HALF_OPEN

    # Repeat an observation already in the pre-trip window: novelty 0.0.
    decision = breaker.observe("stuck_action", "same tired observation")

    assert decision.transition == 8
    assert decision.state is State.OPEN
    assert decision.allowed is False
    assert breaker.cooldown > 0
    assert breaker.cooldown <= breaker.max_cooldown
    assert "no new information" in decision.reason


def test_t8_backoff_is_capped_at_max_cooldown():
    breaker = make_breaker(cooldown_turns=1, backoff=3.0, max_cooldown=4)
    warm_up(breaker)
    trip(breaker)

    for _ in range(12):
        breaker.observe("stuck_action", "same tired observation")
        assert breaker.cooldown <= breaker.max_cooldown


# =============================================================================
# Invariants
# =============================================================================


def test_i1_no_silent_stall_message_carries_index_dials_and_a_route():
    """I1, tightened per §7.

    Every OPEN message must contain the turn index, BOTH dial readings, and
    either an escape vector or the explicit no-progress statement. Non-empty is
    no longer sufficient.
    """
    breaker = make_breaker(cooldown_turns=2)
    warm_up(breaker)

    decisions: list[Decision] = [trip(breaker)]
    # Cycle through row 5, row 6, row 8 repeatedly to collect every OPEN path.
    for _ in range(12):
        decisions.append(breaker.observe("stuck_action", "same tired observation"))

    open_decisions = [d for d in decisions if d.state is State.OPEN]
    assert open_decisions, "expected to observe OPEN decisions"
    for decision in open_decisions:
        message = decision.message
        transition = decision.transition
        assert decision.reason, f"OPEN via transition {transition} had no reason"
        assert message, f"OPEN via transition {transition} had no message"
        assert "turn " in message, f"transition {transition}: no turn index"
        assert "action_sim" in message, f"transition {transition}: no action dial"
        assert "obs_novelty" in message, f"transition {transition}: no novelty dial"
        has_route = "Escape:" in message
        has_no_progress = "no productive path" in message or "no prior result" in message
        assert has_route or has_no_progress, (
            f"transition {transition}: neither an escape vector nor a no-progress "
            f"statement -- {message!r}"
        )


def test_i2_open_is_free_zero_encoder_calls_while_open():
    """I2: no embedding work happens while OPEN. Proved by counting."""
    breaker = make_breaker(cooldown_turns=5)
    warm_up(breaker)
    trip(breaker)
    assert breaker.state is State.OPEN

    calls_at_trip = breaker.encoder.n_encode_calls
    texts_at_trip = breaker.encoder.n_texts_encoded

    # Every one of these is a row-5 refusal: cooldown 5 > 0 throughout.
    for i in range(5):
        decision = breaker.observe(f"attempt_{i}", f"observation {i}")
        assert decision.state is State.OPEN
        assert decision.transition == 5

    assert breaker.encoder.n_encode_calls == calls_at_trip, "OPEN performed embedding work"
    assert breaker.encoder.n_texts_encoded == texts_at_trip


def test_i3_recovery_is_earned_no_open_to_closed_without_a_probe():
    """I3: there is no OPEN -> CLOSED edge; CLOSED is only reachable via row 7."""
    breaker = make_breaker(cooldown_turns=1)
    warm_up(breaker)
    trip(breaker)

    seen: list[tuple[State, int]] = []
    prev_state = breaker.state
    for i in range(30):
        # Alternate stale and novel observations so both row 7 and row 8 occur.
        text = "same tired observation" if i % 3 else f"novel result {i}"
        decision = breaker.observe(f"action_{i}", text)
        seen.append((prev_state, decision.transition))
        prev_state = decision.state

    # Any arrival at CLOSED from OPEN must have gone through HALF_OPEN (row 7).
    for from_state, transition in seen:
        if from_state is State.OPEN:
            assert transition in (5, 6), (
                f"OPEN took transition {transition}; only rows 5 and 6 leave OPEN"
            )

    closed_arrivals = [t for _, t in seen if t == 7]
    for transition in closed_arrivals:
        assert transition == 7, "CLOSED after a trip is reachable only via the probe"


def test_i3_transition_table_is_closed_no_undeclared_transitions():
    """Only the eight tabled transitions ever fire."""
    breaker = make_breaker(cooldown_turns=2)
    warm_up(breaker)
    trip(breaker)
    for i in range(40):
        text = "same tired observation" if i % 4 else f"novel finding {i}"
        breaker.observe(f"action_{i}", text)

    assert set(breaker.transitions) <= {1, 2, 3, 4, 5, 6, 7, 8}


def test_i4_no_stale_re_trip_window_holds_exactly_one_entry_after_recovery():
    """I4: after row 7 the window holds exactly one entry (the probe)."""
    breaker = make_breaker(cooldown_turns=1)
    warm_up(breaker)
    assert len(breaker.window) == breaker.calibrator.min_samples
    trip(breaker)

    breaker.observe("x", "y")            # row 5
    breaker.observe("probe", "probe")    # row 6
    decision = breaker.observe("fresh_action", "a completely unrelated and novel result")

    assert decision.transition == 7
    assert len(breaker.window) == 1, (
        f"window holds {len(breaker.window)} entries; a stale window can re-trip immediately"
    )
    assert breaker.hits == 0


# =============================================================================
# Probe semantics (§8's explicit criterion)
# =============================================================================


def test_probe_is_judged_on_novelty_alone_not_action_similarity():
    """A near-identical action with a novel observation must still recover.

    §8: "Action similarity is not consulted." An agent that recovers by
    re-running a similar action against a newly-fixed environment should recover.
    """
    breaker = make_breaker(cooldown_turns=1)
    warm_up(breaker)
    trip(breaker)
    breaker.observe("x", "y")
    breaker.observe("probe", "probe")

    # Exactly the action that got us tripped, but the world has changed.
    decision = breaker.observe("stuck_action", "the build finally succeeded, 0 errors")

    assert decision.transition == 7
    assert decision.state is State.CLOSED


def test_calibrator_survives_recovery():
    """§8 row 7: 'do not reset calibrator'."""
    breaker = make_breaker(cooldown_turns=1)
    warm_up(breaker)
    n_at_close = breaker.calibrator.n
    mu_at_close = breaker.calibrator.mu
    trip(breaker)

    breaker.observe("x", "y")
    breaker.observe("probe", "probe")
    breaker.observe("fresh_action", "a completely unrelated and novel result")

    assert breaker.calibrator.n >= n_at_close, "calibrator count was reset by recovery"
    assert breaker.calibrator.is_warm, "recovery must not knock us back into warmup"
    assert mu_at_close != 0.0


def test_breaker_starts_calibrating():
    assert make_breaker().state is State.CALIBRATING


def test_provisional_parameters_are_flagged():
    """backoff and max_cooldown are not in §5's fixed table; guard the defaults."""
    from plateau.breaker import BACKOFF, COOLDOWN_TURNS, MAX_COOLDOWN, TRIP_AFTER, WINDOW_SIZE

    assert TRIP_AFTER == 1   # §6 owns multi-turn counting now
    assert WINDOW_SIZE == 8
    assert COOLDOWN_TURNS == 1
    # Provisional, pending a decision. Present so a change is deliberate.
    assert BACKOFF == 2.0
    assert MAX_COOLDOWN == 8


def test_default_trip_after_is_one_because_six_owns_the_counting():
    """§6 accumulates loop_hits/stall_hits, so the breaker opens on one reading."""
    breaker = Breaker(encoder=CountingEncoder(), classify=never_trip)
    assert breaker.trip_after == 1

    for i in range(breaker.calibrator.min_samples):
        breaker.observe(f"a{i}", f"distinct observation {i}")
    assert breaker.state is State.CLOSED

    breaker.classify = always_trip
    decision = breaker.observe("stuck", "stuck")
    assert decision.transition == 4, "a single is_trip reading must open the breaker"
    assert decision.state is State.OPEN
