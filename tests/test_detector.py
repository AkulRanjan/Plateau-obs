"""§6 (revised) predicate, the four fixtures, and the two ablations.

These tests use the real MiniLM encoder, because the fixtures are claims about
what the *embeddings* do, not just about arithmetic. The measured values live in
metrics.json -> detector_fixtures; the assertions here pin the behaviour that
depends on them.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("HF_HUB_OFFLINE", "1")

from plateau.calibrator import Calibrator  # noqa: E402
from plateau.detector import (  # noqa: E402
    TRIP_AFTER_LOOP,
    TRIP_AFTER_STALL,
    Detector,
    PlateauConfig,
    Quadrant,
    quadrant,
)
from plateau.encoder import MiniLMEncoder  # noqa: E402
from scripts.detector_fixtures import FIXTURES, PREAMBLE  # noqa: E402


@pytest.fixture(scope="module")
def encoder():
    return MiniLMEncoder().load()


def warmed(encoder, config: PlateauConfig | None = None) -> Detector:
    """A detector that has seen the productive preamble.

    It ends up calibrated in every configuration except ``action_only``. That
    ablation pins novelty to 0.0, so the §5 gate rejects *every* turn and the
    calibrator can never warm -- see
    ``test_action_only_ablation_can_never_calibrate``. It therefore operates
    permanently on the conservative default ceiling, which is the honest
    consequence of being blind to the observation half.
    """
    config = config or PlateauConfig()
    detector = Detector(
        encoder=encoder,
        calibrator=Calibrator(novelty_floor=config.novelty_floor),
        config=config,
    )
    for action, observation in PREAMBLE:
        detector.evaluate(action, observation)
    if not config.action_only:
        assert detector.calibrator.is_warm
    return detector


def run(detector: Detector, turns):
    return [detector.evaluate(a, o) for a, o in turns]


#: A genuine batch job: a different record every turn. Repeating the *same* two
#: records would be a loop, not a batch, and would correctly trip.
BATCH_TRACE = [
    (
        f"extract_text(f='invoice_{n:03d}.pdf')",
        f"{vendor}, Rs {amount:,}, due {due}",
    )
    for n, vendor, amount, due in [
        (41, "ACME Corp", 84200, "Aug 12"),
        (42, "Vertex Ltd", 19750, "Aug 30"),
        (43, "Bluewave Systems", 132400, "Sep 03"),
        (44, "Orchid Traders", 7310, "Aug 19"),
        (45, "Northgate Supply", 48900, "Sep 11"),
        (46, "Quanta Metals", 221050, "Aug 25"),
        (47, "Sunreef Logistics", 15600, "Sep 07"),
        (48, "Peregrine Foods", 63475, "Aug 28"),
        (49, "Ironwood Timber", 98120, "Sep 15"),
        (50, "Calyx Chemicals", 34890, "Aug 21"),
    ]
]


# --- the predicate -----------------------------------------------------------


def test_quadrant_is_a_pure_two_by_two_with_no_middle():
    assert quadrant(stagnant=True, confident=True) is Quadrant.LOOP
    assert quadrant(stagnant=True, confident=False) is Quadrant.THRASH
    assert quadrant(stagnant=False, confident=True) is Quadrant.GRIND
    assert quadrant(stagnant=False, confident=False) is Quadrant.EXPLORE
    assert len(Quadrant) == 4, "MIDDLE should no longer exist"


def test_provisional_trip_thresholds():
    assert TRIP_AFTER_LOOP == 3    # PROVISIONAL, sweep owns it
    assert TRIP_AFTER_STALL == 6   # PROVISIONAL, sweep owns it
    assert TRIP_AFTER_STALL > TRIP_AFTER_LOOP, (
        "a less diagnostic stall must take longer to trip, not less"
    )


def test_calibrator_has_no_thrash_floor():
    """Removed after measurement: MiniLM has no low-similarity region for tools."""
    assert not hasattr(Calibrator(), "thrash_floor")


# --- the four fixtures -------------------------------------------------------


def test_fixture_1_paraphrase_reads_loop(encoder):
    detector = warmed(encoder)
    readings = run(detector, FIXTURES["1_paraphrase_loop"]["turns"])

    # Index 1 is the gate-1 measured pair, kept pinned where it has always been:
    # 'auth token refresh' against 'how do I refresh a token'. The fixture is
    # now six turns rather than two, so this is no longer readings[-1].
    assert readings[1].action_sim == pytest.approx(0.8927, abs=5e-4)
    assert readings[1].obs_novelty == pytest.approx(0.0, abs=1e-6)

    final = readings[-1]
    assert final.quadrant is Quadrant.LOOP
    assert final.stagnant and final.confident
    assert final.obs_novelty == pytest.approx(0.0, abs=1e-6)


def test_fixture_1_now_trips_where_it_used_to_be_too_short_to(encoder):
    """The fixture-length artifact, pinned so it cannot come back.

    At two turns this could not trip at any parameter setting: turn 0 is not
    stagnant, so loop_hits peaked at 1 against a grid starting at 2. The sweep
    reported that as '0 usable configurations out of 144' -- a statement about
    trace length wearing the costume of a statement about the design.
    """
    detector = warmed(encoder)
    readings = run(detector, FIXTURES["1_paraphrase_loop"]["turns"])

    assert not readings[0].stagnant, "turn 0 is novel against the preamble"
    trips = [i for i, r in enumerate(readings) if r.is_trip]
    assert trips, "a paraphrase loop must be able to trip"
    assert trips[0] == FIXTURES["1_paraphrase_loop"]["expect_trip_turn"]
    assert trips[0] == TRIP_AFTER_LOOP


def test_fixture_2_invoice_batch_reads_grind(encoder):
    detector = warmed(encoder)
    readings = run(detector, FIXTURES["2_invoice_batch_grind"]["turns"])

    # The gate-1 measured pair, as above: invoice_041 against invoice_042.
    assert readings[1].action_sim == pytest.approx(0.9913, abs=5e-4)
    assert readings[1].obs_novelty == pytest.approx(0.4392, abs=5e-4)

    final = readings[-1]
    assert final.quadrant is Quadrant.GRIND
    assert not final.is_trip, "the counter-demo must not trip"


def test_the_counter_demo_holds_for_as_long_as_the_loop_fixture_runs(encoder):
    """Both fixtures were lengthened together, deliberately.

    Lengthening only the positive one would have bought recall for free and made
    the sweep claim more than it knows. This pins the symmetry: the batch job
    survives exactly as many turns as the paraphrase loop needs to trip.
    """
    loop_turns = FIXTURES["1_paraphrase_loop"]["turns"]
    batch_turns = FIXTURES["2_invoice_batch_grind"]["turns"]
    assert len(batch_turns) == len(loop_turns)

    readings = run(warmed(encoder), batch_turns)
    assert not any(r.is_trip for r in readings)
    assert all(r.quadrant is Quadrant.GRIND for r in readings[1:])
    # Every turn clears the floor on its own merits, not by a hair.
    assert all(r.obs_novelty > readings[0].novelty_floor for r in readings)


def test_batch_protected_by_novelty_not_similarity(encoder):
    """The joint design earning its place.

    The invoice batch reads action_sim 0.9913, which clears the ceiling -- so the
    similarity dial alone *condemns* it. It survives only because its observation
    novelty (0.4392) is above the floor. Remove either half of that and the
    counter-demo breaks:

      * `confident` is True, so similarity offers no protection whatsoever;
      * pin novelty to 0.0 (the action_only ablation) and it trips.
    """
    detector = warmed(encoder)
    final = run(detector, FIXTURES["2_invoice_batch_grind"]["turns"])[-1]

    # Similarity does NOT protect it: the batch is above the ceiling.
    assert final.confident is True
    assert final.action_sim >= final.sim_ceiling
    # Novelty is the only thing keeping it out of LOOP.
    assert final.stagnant is False
    assert final.obs_novelty >= final.novelty_floor
    assert final.quadrant is Quadrant.GRIND

    # Prove the counterfactual rather than asserting it: same trace, novelty
    # blinded, and the verdict flips to a trip.
    ablated = warmed(encoder, PlateauConfig(action_only=True))
    ablated_final = run(ablated, FIXTURES["2_invoice_batch_grind"]["turns"])[-1]
    assert ablated_final.quadrant is Quadrant.LOOP
    assert ablated_final.stagnant is True


def test_fixture_3a_identical_errors_trips_at_turn_6(encoder):
    """The realistic unreachable-target case."""
    detector = warmed(encoder)
    readings = run(detector, FIXTURES["3a_thrash_identical_errors"]["turns"])

    trip_turns = [i for i, r in enumerate(readings) if r.is_trip]
    assert trip_turns, "identical failure strings must eventually trip"
    assert trip_turns[0] == 6

    # stall_hits reaches its threshold on exactly that turn.
    assert readings[6].stall_hits == TRIP_AFTER_STALL
    # Every stagnant turn read novelty of exactly zero.
    assert all(r.obs_novelty == pytest.approx(0.0, abs=1e-6) for r in readings[1:])
    # The label legitimately migrates thrash -> loop as the window fills with
    # the agent's own repetitions.
    labels = [r.quadrant for r in readings]
    assert Quadrant.THRASH in labels and Quadrant.LOOP in labels


def test_fixture_3b_varied_errors_is_a_known_miss(encoder):
    """DOCUMENTED LIMITATION, not a bug to tune away.

    Lexically varied failure messages read as new information on short-string
    embeddings, so an agent failing in differently-worded ways evades detection.
    This test exists to keep the miss honest and visible: if it ever starts
    passing, the limitation section needs updating.
    """
    detector = warmed(encoder)
    readings = run(detector, FIXTURES["3b_thrash_varied_errors"]["turns"])

    assert not any(r.is_trip for r in readings), "3b is expected to MISS"
    novelties = [r.obs_novelty for r in readings]
    assert novelties[0] == pytest.approx(0.8055, abs=5e-4)
    assert novelties[1] == pytest.approx(0.4430, abs=5e-4)
    assert novelties[2] == pytest.approx(0.2114, abs=5e-4)
    # Only the third reading falls below the floor at all.
    assert sum(1 for n in novelties if n < detector.config.novelty_floor) == 1


# --- the two ablations -------------------------------------------------------


def test_action_only_ablation_trips_on_the_healthy_batch(encoder):
    """The ablation's entire purpose is to fail where full Plateau succeeds."""
    full = warmed(encoder)
    assert full.run(BATCH_TRACE) is None, "full Plateau must not trip on a batch job"

    ablated = warmed(encoder, PlateauConfig(action_only=True))
    trip_turn = ablated.run(BATCH_TRACE)
    assert trip_turn is not None, (
        "action_only must trip on the batch -- that failure is the measurement"
    )


def test_action_only_ablation_can_never_calibrate(encoder):
    """A consequence of the ablation worth recording.

    Pinning novelty to 0.0 means every turn fails the §5 novelty gate, so the
    calibrator receives no samples at all and stays on the conservative default
    forever. Being blind to the observation half costs you the ability to
    calibrate, not just the ability to see stagnation.
    """
    ablated = warmed(encoder, PlateauConfig(action_only=True))
    assert ablated.calibrator.n == 0
    assert not ablated.calibrator.is_warm
    assert ablated.calibrator.turns_to_warm is None
    assert ablated.calibrator.sim_ceiling == ablated.calibrator.conservative_default
    assert all(record.gated for record in ablated.calibrator.log)


def test_full_plateau_holds_across_a_long_batch_run(encoder):
    """The counter-demo at length: 10 distinct records, no trip, all grind."""
    detector = warmed(encoder)
    readings = run(detector, BATCH_TRACE)

    assert not any(r.is_trip for r in readings)
    assert detector.loop_hits == 0 and detector.stall_hits == 0
    # Every turn after the first reads as grind: repetitive action, real content.
    assert all(r.quadrant is Quadrant.GRIND for r in readings[1:])


def test_novelty_only_ablation_can_never_be_confident(encoder):
    """Pinning action_sim below HARD_LO leaves only the stall_hits path."""
    detector = warmed(encoder, PlateauConfig(novelty_only=True))
    readings = run(detector, FIXTURES["3a_thrash_identical_errors"]["turns"])

    assert all(not r.confident for r in readings)
    assert all(r.loop_hits == 0 for r in readings)
    assert all(r.quadrant in (Quadrant.THRASH, Quadrant.EXPLORE) for r in readings)


def test_novelty_only_still_catches_identical_errors_but_slower(encoder):
    """Isolates what the similarity dial contributes: turns-to-detection."""
    turns = FIXTURES["3a_thrash_identical_errors"]["turns"]

    full_trip = warmed(encoder).run(turns)
    novelty_only_trip = warmed(encoder, PlateauConfig(novelty_only=True)).run(turns)

    assert full_trip is not None and novelty_only_trip is not None
    # Without the similarity dial the loop_hits shortcut is unavailable, so
    # detection can only ever be at or later than full Plateau's.
    assert novelty_only_trip >= full_trip


def test_ablations_are_mutually_exclusive():
    with pytest.raises(ValueError):
        PlateauConfig(action_only=True, novelty_only=True)


def test_config_labels_are_distinct():
    assert PlateauConfig().label == "plateau"
    assert PlateauConfig(action_only=True).label == "plateau_action_only"
    assert PlateauConfig(novelty_only=True).label == "plateau_novelty_only"


# --- the window, and the declaration ------------------------------------------


def test_window_size_is_owned_by_the_config_and_reaches_the_deques(encoder):
    """It was a bare constructor kwarg swept by nothing. The sweep owns it now."""
    detector = Detector(encoder=encoder, config=PlateauConfig(window_size=16))
    assert detector.window_size == 16
    assert detector._obs_vecs.maxlen == 16
    assert detector._action_vecs.maxlen == 16


def test_explicit_window_kwarg_still_overrides_the_config(encoder):
    """The breaker and older callers build detectors without a config."""
    detector = Detector(
        encoder=encoder, config=PlateauConfig(window_size=16), window_size=4
    )
    assert detector.window_size == 4


def test_breaker_and_detector_share_one_window_constant():
    """If these two drift, the live demo behaves differently from every number
    in metrics.json and nothing else in the suite would notice."""
    from plateau import breaker as breaker_module
    from plateau.detector import WINDOW_SIZE

    assert breaker_module.WINDOW_SIZE is WINDOW_SIZE


def test_a_loop_longer_than_the_window_is_invisible(encoder):
    """The measured reason Plateau missed the varied-wording paraphrase class.

    Both dials are max_cosine against the last `window_size` turns, so a
    repetition whose period exceeds the window can never be compared against its
    own earlier occurrence. This is a structural limit, not a threshold that
    could be tuned around.
    """
    from eval.traces import RUNAWAY_PARAPHRASE_LOOP_VARIED_WORDING, _DEAD_END_PHRASINGS

    cycling = RUNAWAY_PARAPHRASE_LOOP_VARIED_WORDING
    period = len(_DEAD_END_PHRASINGS)

    short = Detector(
        encoder=encoder, config=PlateauConfig(window_size=period - 4)
    ).run(cycling)
    long = Detector(
        encoder=encoder, config=PlateauConfig(window_size=period + 4)
    ).run(cycling)

    assert short is None, f"a {period - 4}-turn window cannot see a {period}-turn cycle"
    assert long is not None, f"a {period + 4}-turn window can"


def test_idempotent_turns_carry_no_evidence(encoder):
    """A declared-idempotent tool must not accumulate stall evidence."""
    polling = [
        ("check_build_status(job='deploy-4471')", f"Job still running, {i * 30 + 30}s elapsed")
        for i in range(20)
    ]

    undeclared = warmed(encoder).run(polling)
    declared = warmed(encoder).run(polling, idempotent_tools={"check_build_status"})

    assert undeclared is not None, "the poller false trip is real without the declaration"
    assert declared is None, "declaring it idempotent must hold the breaker closed"


def test_the_declaration_holds_counters_rather_than_resetting_them(encoder):
    """Hold, not reset: a poll interleaved into a real stall must not wipe the
    evidence gathered either side of it."""
    detector = warmed(encoder)
    for action, observation in FIXTURES["3a_thrash_identical_errors"]["turns"][:3]:
        detector.evaluate(action, observation)
    before = detector.stall_hits
    assert before > 0

    detector.evaluate(
        "check_build_status(job='x')", "Job still running, 30s elapsed", idempotent=True
    )
    assert detector.stall_hits == before


def test_the_declaration_is_per_tool_not_per_trace(encoder):
    """Only the named tool is exempt; other tools in the same trace are not."""
    detector = warmed(encoder)
    trace = [("grep(pattern='x')", "Error: not found")] * 8
    assert detector.run(trace, idempotent_tools={"check_build_status"}) is not None
