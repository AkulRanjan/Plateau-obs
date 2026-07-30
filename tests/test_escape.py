"""§7 escape vector and message variants.

Written after a stale `reading.thrash_floor` reference survived in the THRASH
message branch: the whole suite passed because every breaker fake emitted LOOP,
so the thrash path was never executed. Each variant is now exercised directly.
"""

from __future__ import annotations

from plateau.calibrator import NOVELTY_FLOOR
from plateau.detector import Quadrant, Reading
from plateau.escape import EscapeTracker


def reading(quadrant: Quadrant, novelty: float, sim: float = 0.9, turn: int = 12) -> Reading:
    return Reading(
        action_sim=sim,
        obs_novelty=novelty,
        quadrant=quadrant,
        stagnant=novelty < NOVELTY_FLOOR,
        confident=quadrant in (Quadrant.LOOP, Quadrant.GRIND),
        turn_index=turn,
        sim_ceiling=0.786,
        novelty_floor=NOVELTY_FLOOR,
    )


def tracker_with_a_route() -> EscapeTracker:
    tracker = EscapeTracker()
    tracker.record(0, "list_dir(path='src/')", 0.91, state="CALIBRATING")
    tracker.record(1, "read_file(f='src/auth.py')", 0.62, state="CALIBRATING")
    tracker.record(2, "search_docs(q='token')", 0.04, state="CLOSED")
    return tracker


# --- recording ---------------------------------------------------------------


def test_records_during_calibrating():
    """§7: the most informative action often precedes the breaker being armed."""
    tracker = tracker_with_a_route()
    assert len(tracker.candidates) == 3
    # Turn 1, not turn 0 -- see test_turn_zero_is_excluded_from_the_escape_vector.
    assert tracker.best.turn_index == 1
    assert tracker.best.state == "CALIBRATING"


def test_turn_zero_is_excluded_from_the_escape_vector():
    """Turn 0's novelty is 1.0 by construction, not by merit.

    The window is empty on the first turn, so nothing can be redundant with it.
    Left eligible, turn 0 wins every comparison and the escape vector always
    points at whatever the agent happened to do first, which is not advice.
    """
    tracker = EscapeTracker()
    tracker.record(0, "list_dir(path='src/')", 1.0, state="CALIBRATING")
    tracker.record(1, "read_file(f='auth.py')", 0.62, state="CALIBRATING")
    assert tracker.best.turn_index == 1, "turn 0 must not win on its free novelty"

    # With nothing else recorded, turn 0 is all there is and may be named.
    only_first = EscapeTracker()
    only_first.record(0, "list_dir(path='src/')", 1.0)
    assert only_first.best.turn_index == 0


def test_best_breaks_ties_toward_the_earlier_turn():
    tracker = EscapeTracker()
    tracker.record(3, "a", 0.70)
    tracker.record(7, "b", 0.70)
    assert tracker.best.turn_index == 3


def test_has_route_requires_clearing_the_floor():
    tracker = EscapeTracker()
    tracker.record(0, "a", NOVELTY_FLOOR - 0.01)
    assert not tracker.has_route
    tracker.record(1, "b", NOVELTY_FLOOR)
    assert tracker.has_route


# --- the three message variants ----------------------------------------------


def assert_i1_contract(message: str) -> None:
    """The tightened I1: turn index, both dials, and a route or a no-progress line."""
    assert "turn " in message
    assert "action_sim" in message
    assert "obs_novelty" in message
    assert "ceiling" in message
    assert ("Escape:" in message) or ("no productive path" in message) or (
        "no prior result" in message
    )


def test_loop_variant():
    message = tracker_with_a_route().message(reading(Quadrant.LOOP, 0.0))
    assert "[plateau:loop]" in message
    assert "same question" in message
    assert "Escape:" in message
    assert "turn 1" in message, "must name the most informative eligible turn"
    assert ">= ceiling" in message, "a loop is above the ceiling"
    assert_i1_contract(message)


def test_thrash_variant_renders_without_a_thrash_floor():
    """The path that used to reference a removed attribute."""
    message = tracker_with_a_route().message(reading(Quadrant.THRASH, 0.02, sim=0.41))
    assert "[plateau:thrash]" in message
    assert "Actions keep changing" in message
    assert "< ceiling" in message, "thrash is below the ceiling, not below a floor"
    assert "thrash_floor" not in message
    assert_i1_contract(message)


def test_no_progress_variant_drops_the_escape_line():
    """When nothing cleared the floor there is no route to offer."""
    tracker = EscapeTracker()
    for index in range(5):
        tracker.record(index, f"search_docs(q='attempt {index}')", 0.05)

    message = tracker.message(reading(Quadrant.LOOP, 0.01))
    assert "Escape:" not in message, "must not name a route that does not exist"
    assert "no productive path" in message
    assert "best of 5 turns" in message
    assert "0.050" in message, "the best novelty actually reached must be stated"
    assert_i1_contract(message)


def test_no_progress_variant_with_nothing_recorded():
    message = EscapeTracker().message(reading(Quadrant.LOOP, 0.0))
    assert "no prior result" in message
    assert_i1_contract(message)


# --- numbers come from live state --------------------------------------------


def test_every_number_is_interpolated_not_templated():
    tracker = EscapeTracker()
    tracker.record(4, "grep(pattern='TTL')", 0.7331)
    message = tracker.message(
        reading(Quadrant.LOOP, novelty=0.0123, sim=0.8765, turn=41)
    )
    # Expected strings are formatted the same way the message formats them,
    # rather than hardcoded, so this tests interpolation and not float repr.
    assert "turn 41" in message
    assert f"{0.8765:.3f}" in message
    assert f"{0.0123:.3f}" in message
    assert f"{0.7331:.3f}" in message
    assert "turn 4 " in message or "turn 4)" in message


def test_snapshot_reports_route_state():
    snapshot = tracker_with_a_route().snapshot()
    assert snapshot["turns_recorded"] == 3
    assert snapshot["has_route"] is True
    assert snapshot["best_turn_index"] == 1
    assert snapshot["novelty_floor"] == NOVELTY_FLOOR
