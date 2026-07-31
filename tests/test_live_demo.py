"""Tests for the live two-agent demo — the thing that actually goes on stage.

This stack had zero coverage while being the most-watched code in the project.
Everything here is network-free: the world's tools are pure functions, and the
agent loop is driven by a scripted fake model rather than ollama.

The properties pinned here are the ones that broke, or nearly broke, in
practice. Each test says which.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("HF_HUB_OFFLINE", "1")

from demo import collector as collector_mod  # noqa: E402
from demo.live_agent import SURVEY, RunResult, run  # noqa: E402
from demo.live_model import Proposal  # noqa: E402
from demo.live_world import (  # noqa: E402
    NO_RESULTS,
    TOOL_SCHEMA,
    TOOLS,
    _DOC_INDEX,
    execute,
    grep,
    list_dir,
    read_file,
    render_call,
    search_docs,
    vault_get,
)


# --------------------------------------------------------------------------
# the world
# --------------------------------------------------------------------------


def test_every_doc_index_keyword_answers_something():
    """No indexed keyword may fall through to the non-answer."""
    for keywords, _expected in _DOC_INDEX:
        for keyword in keywords:
            answer = search_docs(query=f"tell me about {keyword}")
            assert answer != NO_RESULTS, f"{keyword!r} fell through to the non-answer"


def test_every_doc_index_entry_is_reachable():
    """Matching is first-wins, so a later entry whose keywords are all claimed by
    an earlier one would be dead: a documented topic the agent could never
    surface, and one fewer productive turn available to warm the calibrator.

    Every entry is currently reachable. One keyword is shadowed — `expires_at`
    is caught by the earlier `expire` — but its entry still answers via
    `session`, so nothing is lost. This test exists to catch the case where a
    future entry has *no* unshadowed keyword left.
    """
    for index, (keywords, expected) in enumerate(_DOC_INDEX):
        reachable = [
            k for k in keywords if search_docs(query=f"tell me about {k}") == expected
        ]
        assert reachable, (
            f"_DOC_INDEX entry {index} is unreachable — every one of its keywords "
            f"{list(keywords)} is claimed by an earlier entry, so this topic can "
            f"never be surfaced"
        )


def test_unknown_query_returns_the_constant_non_answer():
    for query in ("zzzz", "unrelated nonsense", "", "what is the capital of France"):
        assert search_docs(query=query) == NO_RESULTS


def test_non_answer_is_byte_identical_across_calls():
    """THE load-bearing property of the whole demo.

    Plateau trips because novelty collapses to ~0, and novelty collapses only
    because the non-answer is the SAME STRING every time. If someone 'improves'
    these tools by varying the wording, novelty stops collapsing, the breaker
    never opens, and the demo dies silently with no test failing.

    This is not hypothetical: metrics.json -> long_trace_comparison measures
    differently-worded non-answers at 0.4366-1.0112 novelty, none of which fall
    below the 0.30 floor.
    """
    answers = {search_docs(query=f"unmatched query {i}") for i in range(12)}
    assert answers == {NO_RESULTS}

    greps = {grep(pattern=f"nonexistent-pattern-{i}") for i in range(12)}
    assert greps == {NO_RESULTS}

    # And the two tools must agree, since the loop mixes them.
    assert search_docs(query="zzz") == grep(pattern="zzz") == NO_RESULTS


def test_vault_always_denies():
    """The wall. If this ever succeeds the task becomes solvable and there is
    no stall to detect."""
    for path in ("app/oauth", "app/oauth/client_secret", "", "anything"):
        observation = vault_get(path=path)
        assert observation.startswith("PermissionError")


def test_read_file_missing_path_errors_without_raising():
    observation = read_file(path="does/not/exist.md")
    assert observation.startswith("Error")


def test_list_dir_missing_path_errors_without_raising():
    assert list_dir(path="nope").startswith("Error")


def test_execute_never_raises_on_bad_input():
    """A tool crash would kill the run mid-demo. Every path returns a string."""
    assert execute("no_such_tool", {}).observation.startswith("Error")
    assert execute("read_file", {"wrong_kwarg": 1}).observation.startswith("Error")
    assert isinstance(execute("search_docs", {"query": "refresh"}).observation, str)


def test_tool_schema_matches_the_implemented_tools():
    """A schema/implementation mismatch shows up as the model calling something
    that does not exist, mid-run."""
    schema_names = {t["function"]["name"] for t in TOOL_SCHEMA}
    assert schema_names == set(TOOLS)


def test_render_call_is_stable_for_the_same_call():
    """Plateau embeds this string. If it were unstable — dict ordering, say —
    action similarity would be noise."""
    a = render_call("search_docs", {"query": "x", "extra": "y"})
    b = render_call("search_docs", {"extra": "y", "query": "x"})
    assert a == b


# --------------------------------------------------------------------------
# the survey preamble
# --------------------------------------------------------------------------


def test_survey_calls_are_all_valid():
    for tool_name, tool_args in SURVEY:
        assert tool_name in TOOLS
        assert not execute(tool_name, tool_args).observation.startswith("Error")


def test_survey_observations_are_distinct():
    """Cheap proxy for 'productive', with no encoder needed. Identical survey
    observations could not possibly warm the calibrator."""
    observations = [execute(name, args).observation for name, args in SURVEY]
    assert len(set(observations)) == len(observations)


@pytest.mark.parametrize("_", [0])
def test_survey_warms_the_calibrator(_):
    """The property that makes the trip reproducible.

    Plateau cannot arm until the calibrator has seen MIN_SAMPLES productive
    turns. Left to itself the model produced exactly FIVE and the breaker stayed
    in CALIBRATING for all 22 turns — twice. The survey exists to guarantee six.

    Needs the real encoder; skipped when the weights are absent.
    """
    pytest.importorskip("sentence_transformers")
    from plateau.calibrator import MIN_SAMPLES, Calibrator
    from plateau.encoder import MiniLMEncoder

    try:
        encoder = MiniLMEncoder().load()
    except Exception:  # noqa: BLE001 - weights not downloaded on this machine
        pytest.skip("encoder weights unavailable")

    from plateau.detector import Detector, PlateauConfig

    calibrator = Calibrator()
    detector = Detector(encoder=encoder, calibrator=calibrator, config=PlateauConfig())

    for tool_name, tool_args in SURVEY:
        detector.evaluate(render_call(tool_name, tool_args), execute(tool_name, tool_args).observation)

    assert calibrator.n >= MIN_SAMPLES, (
        f"the survey produced only {calibrator.n} productive turns; the breaker "
        f"needs {MIN_SAMPLES} to leave CALIBRATING and the demo will not trip"
    )
    assert calibrator.is_warm


# --------------------------------------------------------------------------
# the agent loop, driven by a fake model
# --------------------------------------------------------------------------


class ScriptedModel:
    """A model that plays a fixed sequence. No ollama, no network."""

    def __init__(self, calls: list[tuple[str, dict]]) -> None:
        self.name = "scripted"
        self._calls = calls
        self.i = 0

    def digest(self) -> str:
        return "scripted"

    def propose(self, messages, tools) -> Proposal:
        tool, args = self._calls[min(self.i, len(self._calls) - 1)]
        self.i += 1
        return Proposal(tool=tool, args=args, text="")


#: A stall: the same call, over and over, returning the same non-answer.
STALL = [("grep", {"pattern": "nonexistent-thing"})] * 24


def _run(mode: str, calls, max_turns: int = 22) -> RunResult:
    return run(
        mode=mode,
        collector=None,
        model_kind="ollama",
        model_name="unused",
        max_turns=max_turns,
        delay=0.0,
        model=ScriptedModel(calls),
        quiet=True,
    )


def test_guarded_run_trips_on_a_stall():
    pytest.importorskip("sentence_transformers")
    try:
        result = _run("plateau", STALL)
    except Exception:  # noqa: BLE001
        pytest.skip("encoder weights unavailable")

    assert result.tripped, "the breaker never opened on a pure stall"
    assert result.refused > 0, "the breaker opened but never refused a call"


def test_unguarded_run_does_not_trip_on_the_same_input():
    """The comparison the entire demo rests on: identical input, one difference."""
    result = _run("unguarded", STALL)
    assert not result.tripped
    assert result.refused == 0
    assert result.turns_executed == 22


def test_no_embedding_work_while_open():
    """Invariant I3, and the cost argument.

    A tripped breaker must be free. Measured live at 15 encoder calls across 22
    turns; here we assert the weaker, stable form — encoder calls stop advancing
    once the breaker has opened.
    """
    pytest.importorskip("sentence_transformers")
    try:
        result = _run("plateau", STALL)
    except Exception:  # noqa: BLE001
        pytest.skip("encoder weights unavailable")

    assert result.tripped
    assert result.encoder is not None
    assert result.encoder.n_encode_calls < result.summary["turns executed"] + result.refused, (
        "the encoder ran on every turn including refused ones; "
        "a tripped breaker is supposed to cost nothing"
    )


def test_agent_stops_when_the_model_gives_a_final_answer():
    """A model that stops must end the run, not be forced to keep calling."""

    class Stopper(ScriptedModel):
        def propose(self, messages, tools):
            return Proposal(tool=None, args={}, text="Here is the answer.")

    result = run(
        mode="unguarded", collector=None, model_kind="ollama", model_name="unused",
        max_turns=22, delay=0.0, model=Stopper([]), quiet=True,
    )
    # Only the survey ran; the model declined its first turn.
    assert result.turns_executed == len(SURVEY)


# --------------------------------------------------------------------------
# the collector
# --------------------------------------------------------------------------


@pytest.fixture()
def live_collector():
    """A real collector on an ephemeral port."""
    for mode in ("plateau", "unguarded"):
        collector_mod._STATE[mode] = {"turns": [], "done": None, "summary": {}}

    server = ThreadingHTTPServer(("127.0.0.1", 0), collector_mod.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _post(url: str, path: str, payload: dict) -> int:
    request = urllib.request.Request(
        url + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status


def _state(url: str) -> dict:
    with urllib.request.urlopen(url + "/state", timeout=5) as response:
        return json.loads(response.read())


def test_refused_means_the_tool_never_ran(tmp_path, monkeypatch):
    """`allowed` and `executed` are different questions, and the demo shows both.

    A HALF_OPEN probe is allowed through, runs, and is judged on the observation
    it produced — so it is recorded allowed=False, executed=True. Measured on a
    live 25-turn run: 13 turns carried allowed=False but only 8 were vetoed. The
    pane called all 13 "REFUSED" and the dashboard's token counter skipped the
    5 that had really run, so the screen disagreed with the run's own summary.
    """
    pytest.importorskip("sentence_transformers")
    try:
        result = _run("plateau", STALL)
    except Exception:  # noqa: BLE001
        pytest.skip("encoder weights unavailable")

    assert result.tripped
    vetoed = [t for t in result.turns if not t.executed]
    judged = [t for t in result.turns if t.executed and not t.allowed]

    assert len(vetoed) == result.refused, (
        "`turns refused` in the summary must equal the turns that never ran"
    )
    assert all(t.observation == "(not executed)" for t in vetoed)
    assert judged, "expected at least the trip turn to have run and then been judged"
    assert all(t.observation != "(not executed)" for t in judged)
    executed_rows = [t for t in result.turns if t.executed]
    assert len(executed_rows) == result.summary["turns executed"]


def test_an_explicit_no_collector_is_not_overridden_by_the_published_file(tmp_path):
    """`collector=None` means none — not "go and read collector.url".

    Conflating "argument omitted" with "explicitly none" meant a stale published
    address killed runs that had asked for no collector at all.
    """
    from demo import live_agent

    stale = tmp_path / "collector.url"
    stale.write_text("http://192.0.2.1:9999\n", encoding="utf-8")  # TEST-NET-1, unroutable
    original = live_agent.COLLECTOR_URL_FILE
    live_agent.COLLECTOR_URL_FILE = stale
    try:
        assert live_agent.resolve_collector(None)[0] is None
        assert live_agent.resolve_collector("")[0] is None
        # Omitted still means "use what the collector published".
        assert live_agent.resolve_collector()[0] == "http://192.0.2.1:9999"
        assert live_agent.resolve_collector(live_agent.AUTO)[0] == "http://192.0.2.1:9999"
        # An explicit address always wins, and is normalised.
        assert live_agent.resolve_collector("http://x:1/")[0] == "http://x:1"
    finally:
        live_agent.COLLECTOR_URL_FILE = original


def test_collector_records_and_resets(live_collector):
    assert _post(live_collector, "/turn", {"mode": "unguarded", "n": 1}) == 200
    assert _post(live_collector, "/turn", {"mode": "unguarded", "n": 2}) == 200
    assert _post(live_collector, "/turn", {"mode": "plateau", "n": 1}) == 200

    state = _state(live_collector)
    assert len(state["unguarded"]["turns"]) == 2
    assert len(state["plateau"]["turns"]) == 1

    _post(live_collector, "/reset", {"mode": "unguarded"})
    state = _state(live_collector)
    assert state["unguarded"]["turns"] == []
    assert len(state["plateau"]["turns"]) == 1, "reset must not touch the other pane"


def test_collector_rejects_an_unknown_mode(live_collector):
    with pytest.raises(Exception):
        _post(live_collector, "/turn", {"mode": "nonsense", "n": 1})


def test_collector_serves_the_dashboard(live_collector):
    with urllib.request.urlopen(live_collector + "/", timeout=5) as response:
        body = response.read().decode()
    assert response.status == 200
    assert "UNGUARDED" in body and "WITH PLATEAU" in body


def test_dashboard_states_that_token_figures_are_illustrative(live_collector):
    """The cost numbers are arithmetic over an assumption. Saying so is not
    optional, and it is easy to lose in a redesign."""
    with urllib.request.urlopen(live_collector + "/", timeout=5) as response:
        body = response.read().decode()
    assert "ILLUSTRATIVE" in body


# --------------------------------------------------------------------------
# the model seam, and the one-command runner
# --------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Records the calls made, answers from a fixed payload."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.gets: list[str] = []
        self.posts: list[tuple[str, dict]] = []

    def get(self, url, **_kw):
        self.gets.append(url)
        return _FakeResponse(self.payload)

    def post(self, url, json=None, **_kw):
        self.posts.append((url, json or {}))
        return _FakeResponse(self.payload)


TAGS = {
    "models": [
        {"name": "nomic-embed-text:latest", "digest": "0a109f422b47", "details": {}},
        {
            "name": "llama3.1:8b",
            "model": "llama3.1:8b",
            "digest": "46e0c10c039e01911933deadbeef",
            "details": {"quantization_level": "Q4_K_M"},
        },
    ]
}


def test_ollama_digest_is_a_real_digest():
    """The RUNBOOK asks two laptops to compare this string before recording.

    It read /api/show, which has no `digest` key, so it fell through to
    details.parent_model — empty for every non-derived model — and the banner
    printed `digest=` on both machines. Two blanks compare equal, which is the
    worst possible way to fail a determinism check.
    """
    from demo.live_model import OllamaModel

    model = OllamaModel(model="llama3.1:8b")
    model._client = _FakeClient(TAGS)
    digest = model.digest()

    assert digest.startswith("46e0c10c039e")
    assert "Q4_K_M" in digest, "quantisation differing under the same tag must be visible"
    assert model._client.gets == ["http://localhost:11434/api/tags"]


def test_ollama_digest_says_so_when_the_model_is_missing():
    from demo.live_model import OllamaModel

    model = OllamaModel(model="mistral:7b")
    model._client = _FakeClient(TAGS)
    assert "not pulled" in model.digest()


RUN_DEMO = ROOT / "demo" / "run_demo.sh"


def test_run_demo_script_is_executable_and_valid():
    import shutil
    import subprocess

    assert RUN_DEMO.exists(), "the one-command runner is what gets typed on stage"
    assert os.access(RUN_DEMO, os.X_OK), "run_demo.sh must be chmod +x"
    bash = shutil.which("bash")
    if bash:
        assert subprocess.run([bash, "-n", str(RUN_DEMO)]).returncode == 0


def test_run_demo_defaults_to_ollama_and_needs_no_aws():
    """--model-kind ollama is the default and must stay the default.

    Bedrock is best-effort: nothing about it may be required to run the demo.
    """
    body = RUN_DEMO.read_text(encoding="utf-8")
    assert 'MODEL_KIND="ollama"' in body

    # Prose may discuss AWS; the executable lines may not touch it.
    code = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
    for aws_ism in ("aws ", "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT", "boto3", "sts "):
        assert aws_ism not in code, f"the runner must not require {aws_ism!r}"


# --------------------------------------------------------------------------
# what the dashboard needs in the payload
# --------------------------------------------------------------------------


def test_turns_carry_the_calibration_snapshot():
    """The dashboard draws the ceiling and the warmup meter from these.

    Before they existed the only way to see the learned ceiling was to parse it
    back out of a formatted reason string, which is not something a UI should
    ever do.
    """
    pytest.importorskip("sentence_transformers")
    try:
        result = _run("plateau", STALL)
    except Exception:  # noqa: BLE001
        pytest.skip("encoder weights unavailable")

    from plateau.calibrator import MIN_SAMPLES, NOVELTY_FLOOR

    judged = [t for t in result.turns if t.calibrated_n is not None]
    assert judged, "no turn carried a calibration snapshot"
    for turn in judged:
        assert turn.min_samples == MIN_SAMPLES
        assert turn.novelty_floor == NOVELTY_FLOOR
        assert 0.0 <= turn.sim_ceiling <= 1.0

    # It only ever grows, and it reaches the arming threshold.
    counts = [t.calibrated_n for t in judged]
    assert counts == sorted(counts), "calibrated_n went backwards"
    assert max(counts) >= MIN_SAMPLES


def test_unguarded_turns_carry_no_calibration_snapshot():
    """The unguarded agent has no calibrator, and must not imply it has one."""
    result = _run("unguarded", STALL)
    assert all(t.calibrated_n is None and t.sim_ceiling is None for t in result.turns)


def test_dashboard_reads_executed_not_allowed_for_cost(live_collector):
    """Guards the bug that understated the guarded pane's token count.

    A HALF_OPEN probe runs and is then judged, so counting `allowed` skips real
    work that really happened.
    """
    with urllib.request.urlopen(live_collector + "/", timeout=5) as response:
        body = response.read().decode()
    assert "t.executed !== false" in body
    assert "t.allowed !== false" not in body, (
        "cost must be counted from what ran, not from what was allowed"
    )


def test_dashboard_shows_the_evidence_panels(live_collector):
    """The panels that make the trip explainable rather than assertive."""
    with urllib.request.urlopen(live_collector + "/", timeout=5) as response:
        body = response.read().decode()
    for marker in ("CALIBRATING", "HALF_OPEN", "BREAKER OPEN", "ENCODER CALLS",
                   "action sim", "obs novelty", "digest"):
        assert marker in body, f"dashboard lost its {marker!r} panel"
