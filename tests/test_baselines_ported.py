"""Behavioural tests for the exact-match and lexical ports.

Purpose is diagnostic: when the harness reports a bad number for one of these,
these tests tell us whether the baseline is genuinely blind to that trace shape
or whether we ported it wrong.
"""

from __future__ import annotations

from eval.baselines import BaselineTurn
from eval.baselines.exact_match import (
    ACTION_ERROR_THRESHOLD,
    ACTION_OBSERVATION_THRESHOLD,
    ALTERNATING_PATTERN_THRESHOLD,
    detect as exact_match_detect,
)
from eval.baselines.lexical import (
    MAX_CONSECUTIVE,
    SIMILARITY_THRESHOLD,
    WINDOW_SIZE,
    detect as lexical_detect,
    jaccard_similarity,
)


def t(name: str, obs: str, is_error: bool = False, **kwargs) -> BaselineTurn:
    return BaselineTurn(
        action_name=name, action_input=kwargs, observation=obs, is_error=is_error
    )


# --- exact match (OpenHands) --------------------------------------------------


def test_exact_match_published_defaults():
    assert ACTION_OBSERVATION_THRESHOLD == 4
    assert ACTION_ERROR_THRESHOLD == 3
    assert ALTERNATING_PATTERN_THRESHOLD == 6


def test_exact_match_scenario1_fires_on_identical_action_and_observation():
    turns = [t("search", "No results found.", q="x") for _ in range(6)]
    assert exact_match_detect(turns) == ACTION_OBSERVATION_THRESHOLD - 1


def test_exact_match_scenario1_needs_both_halves_identical():
    """The finding that corrects our deck: differing observations do not fire.

    Same action every turn, different observation every turn -- scenario 1
    requires observations_equal, so it stays silent.
    """
    turns = [t("search", f"result number {i}", q="x") for i in range(10)]
    assert exact_match_detect(turns) is None


def test_exact_match_holds_on_a_healthy_batch_job():
    """A batch job differs in both halves, so this detector correctly holds."""
    turns = [
        t("extract_text", f"invoice_{i}: total {i * 137}, vendor V{i}", f=f"invoice_{i}.pdf")
        for i in range(41, 61)
    ]
    assert exact_match_detect(turns) is None


def test_exact_match_misses_a_paraphrase_loop():
    """The gap Plateau targets: same intent, reworded, nothing learned."""
    turns = [
        t("search_docs", "Nothing relevant found.", q="auth token refresh"),
        t("search_docs", "Nothing relevant found here.", q="refreshing auth tokens"),
        t("search_docs", "No relevant results.", q="how do I refresh a token"),
        t("search_docs", "Nothing found that is relevant.", q="token refresh procedure"),
        t("search_docs", "No results of relevance.", q="refresh the auth token"),
    ]
    assert exact_match_detect(turns) is None


def test_exact_match_scenario2_fires_on_repeated_errors():
    turns = [t("write_file", "PermissionError: /etc/shadow", is_error=True, p="/etc/shadow")
             for _ in range(4)]
    assert exact_match_detect(turns) == ACTION_ERROR_THRESHOLD - 1


def test_exact_match_scenario4_fires_on_an_alternating_pattern():
    """A-B-A-B-A-B: reaches thrash-like behaviour that action-only detectors miss."""
    turns = []
    for _ in range(3):
        turns.append(t("open", "opened", f="a.txt"))
        turns.append(t("close", "closed", f="a.txt"))
    assert exact_match_detect(turns) == ALTERNATING_PATTERN_THRESHOLD - 1


def test_exact_match_never_fires_on_a_short_or_empty_trace():
    assert exact_match_detect([]) is None
    assert exact_match_detect([t("a", "b")]) is None


# --- lexical (agent-loop-detector) -------------------------------------------


def test_lexical_published_defaults():
    assert SIMILARITY_THRESHOLD == 0.85
    assert WINDOW_SIZE == 10
    assert MAX_CONSECUTIVE == 3


def test_lexical_jaccard_matches_upstream_conventions():
    assert jaccard_similarity("", "") == 1.0
    assert jaccard_similarity("a", "") == 0.0
    assert jaccard_similarity("the cat sat", "the cat sat") == 1.0
    assert 0.0 < jaccard_similarity("the cat sat", "the cat stood") < 1.0


def test_lexical_fires_on_identical_observations():
    turns = [t("poll", "Job still running.") for _ in range(5)]
    assert lexical_detect(turns) is not None
    assert lexical_detect(turns) == MAX_CONSECUTIVE - 1


def test_lexical_reads_only_the_observation():
    """Upstream's check(output) never sees the action; varying it changes nothing."""
    same_action = [t("poll", "Job still running.") for _ in range(5)]
    varied_action = [t(f"tool_{i}", "Job still running.") for i in range(5)]
    assert lexical_detect(same_action) == lexical_detect(varied_action)


def test_lexical_misses_a_paraphrase_below_its_threshold():
    """Jaccard at 0.85 is strict: reworded observations fall under it."""
    turns = [
        t("search", "Nothing relevant was found in the documentation."),
        t("search", "No relevant results were located in the docs."),
        t("search", "The documentation contained nothing of relevance."),
        t("search", "Relevant material was absent from the docs."),
    ]
    assert lexical_detect(turns) is None


def test_lexical_holds_on_a_healthy_batch_job():
    turns = [
        t("extract", f"invoice_{i}: total {i * 137}, vendor V{i}") for i in range(41, 61)
    ]
    assert lexical_detect(turns) is None


def test_lexical_never_fires_on_a_short_or_empty_trace():
    assert lexical_detect([]) is None
    assert lexical_detect([t("a", "b")]) is None
