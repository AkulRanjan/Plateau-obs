"""Tests for the LangGraph integration example.

Split deliberately: `PlateauGuard` is plain Python and is tested wherever the
encoder is available, while the graph itself is only exercised where langgraph
is installed. On this machine that is the micromamba `ai` environment, not the
default interpreter, so the graph tests skip rather than fail here.

    micromamba run -n ai python -m pytest tests/test_langgraph_example.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("HF_HUB_OFFLINE", "1")

from examples.langgraph_plateau import (  # noqa: E402
    SCRIPT,
    PlateauGuard,
    scripted_propose,
)


def _guard() -> PlateauGuard:
    pytest.importorskip("sentence_transformers")
    try:
        return PlateauGuard()
    except Exception:  # noqa: BLE001 - weights not downloaded here
        pytest.skip("encoder weights unavailable")


def _drive(guard: PlateauGuard, calls, limit: int = 20):
    """Run the two hooks by hand, exactly as the graph nodes do."""
    from demo.live_world import execute, render_call

    executed, refused = 0, 0
    for tool, args in calls[:limit]:
        action = render_call(tool, args)
        before = guard.before_tool(action)
        if before is not None and not before.allowed:
            refused += 1
            continue
        observation = execute(tool, args).observation
        executed += 1
        guard.after_tool(action, observation)
    return executed, refused


def test_guard_says_nothing_until_the_breaker_opens():
    """before_tool must be free while CLOSED — it is called on every turn."""
    guard = _guard()
    from demo.live_world import execute, render_call

    for tool, args in SCRIPT[:6]:
        action = render_call(tool, args)
        assert guard.before_tool(action) is None
        guard.after_tool(action, execute(tool, args).observation)
    assert guard.state in ("CALIBRATING", "CLOSED")


def test_a_tripped_breaker_embeds_nothing():
    """The cost argument, at the adapter level rather than the agent level."""
    guard = _guard()
    executed, refused = _drive(guard, SCRIPT, limit=20)

    assert refused > 0, "the stall never tripped the breaker"
    assert guard.breaker.encoder.n_encode_calls == executed, (
        "the encoder ran on turns that were never executed"
    )


def test_the_veto_carries_a_reason_and_an_escape():
    """A refusal that does not say why is not usable by the agent above it."""
    guard = _guard()
    from demo.live_world import execute, render_call

    veto = None
    for tool, args in SCRIPT[:20]:
        action = render_call(tool, args)
        decision = guard.before_tool(action)
        if decision is not None and not decision.allowed:
            veto = decision
            break
        guard.after_tool(action, execute(tool, args).observation)

    assert veto is not None, "never got a veto"
    assert veto.reason
    assert "novelty" in veto.message or "Escape" in veto.message


# ---------------------------------------------------------------------------
# the graph itself
# ---------------------------------------------------------------------------

# Not at module level: that would skip the guard tests above too, and those run
# fine without langgraph.
needs_langgraph = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("langgraph") is None,
    reason="langgraph lives in the micromamba ai env, not the default interpreter",
)


@needs_langgraph
def test_the_graph_trips_and_refuses():
    from examples.langgraph_plateau import build_graph

    guard = _guard()
    app = build_graph(scripted_propose, guard, max_turns=18)
    final = app.invoke(
        {"turn": 0, "history": [], "tool": None, "args": {}, "action": "",
         "observation": "", "guard_state": "CALIBRATING", "guard_reason": "",
         "guard_message": "", "executed": True, "done": ""},
        {"recursion_limit": 200},
    )

    refused = [r for r in final["history"] if r["observation"] == "(refused)"]
    executed = [r for r in final["history"] if r["observation"] != "(refused)"]
    assert refused, "the graph never refused a call"
    assert guard.breaker.encoder.n_encode_calls == len(executed)


@needs_langgraph
def test_one_veto_does_not_stop_the_graph_executing_forever():
    """Regression: `executed` was sticky.

    A single veto routed the graph back to `agent` on every subsequent turn, so
    the breaker recovered to HALF_OPEN, wanted to probe, and never got another
    tool call — the run burned its remaining turns proposing actions nobody ran.
    """
    from examples.langgraph_plateau import build_graph

    guard = _guard()
    app = build_graph(scripted_propose, guard, max_turns=18)
    final = app.invoke(
        {"turn": 0, "history": [], "tool": None, "args": {}, "action": "",
         "observation": "", "guard_state": "CALIBRATING", "guard_reason": "",
         "guard_message": "", "executed": True, "done": ""},
        {"recursion_limit": 200},
    )

    history = final["history"]
    first_refusal = next(i for i, r in enumerate(history) if r["observation"] == "(refused)")
    after = history[first_refusal + 1:]
    assert any(r["observation"] != "(refused)" for r in after), (
        "nothing executed after the first veto — the graph stopped running tools"
    )
