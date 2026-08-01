"""Plateau inside a LangGraph agent.

The claim this file exists to support: attaching Plateau to an existing agent is
a hook, not a rewrite. Everything below is an ordinary LangGraph `StateGraph`.
The Plateau part is one small class and two nodes, and the agent logic does not
know it is being watched.

    micromamba run -n ai python examples/langgraph_plateau.py            # scripted, instant
    micromamba run -n ai python examples/langgraph_plateau.py --ollama   # a real llama3.1:8b

Deliberately NOT part of the demo path. `demo/run_demo.sh` neither imports nor
needs this, so nothing here can break what goes on stage.

WHY TWO HOOKS AND NOT ONE
-------------------------
Plateau judges a turn from BOTH halves — the action and the observation it
produced — and the observation only exists after the tool has run. So while the
breaker is CLOSED the tool runs and the completed turn is scored; once OPEN the
breaker vetoes before execution, at zero embedding cost. That is the same split
as `demo/live_agent.py`, and the same shape as a Strands BeforeToolCall /
AfterToolCall pair or a LangChain callback pair. Any framework that lets you
run code around a tool call can host it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Annotated, Any, TypedDict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from demo.live_world import TASK, TOOL_SCHEMA, execute, render_call  # noqa: E402


# ---------------------------------------------------------------------------
# the adapter — the only Plateau-aware code in this file
# ---------------------------------------------------------------------------


class PlateauGuard:
    """Two hooks around a tool call. Framework-agnostic on purpose.

    `before_tool` is cheap: while the breaker is not OPEN it does nothing at
    all, and when it is OPEN it answers without embedding anything. `after_tool`
    is where the encoder runs, on turns that actually happened.
    """

    def __init__(self, breaker: Any | None = None) -> None:
        if breaker is None:
            from plateau.breaker import Breaker
            from plateau.calibrator import Calibrator
            from plateau.detector import Detector, PlateauConfig
            from plateau.encoder import MiniLMEncoder

            encoder = MiniLMEncoder().load()
            calibrator = Calibrator()
            detector = Detector(
                encoder=encoder, calibrator=calibrator, config=PlateauConfig()
            )
            breaker = Breaker(
                encoder=encoder, classify=detector.classify, calibrator=calibrator
            )
        self.breaker = breaker

    @property
    def state(self) -> str:
        return self.breaker.state.value

    def before_tool(self, action: str):
        """Ask permission. Returns None when the breaker has no opinion yet.

        Only consulted while OPEN — that is what makes a tripped breaker free.
        """
        if self.breaker.state.value != "OPEN":
            return None
        return self.breaker.observe(action, "")

    def after_tool(self, action: str, observation: str):
        """Score the completed turn. This is the call that embeds."""
        return self.breaker.observe(action, observation)


# ---------------------------------------------------------------------------
# an ordinary LangGraph agent
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    """Nothing Plateau-specific except the three `guard_*` keys it writes."""

    turn: int
    history: Annotated[list[dict], lambda a, b: a + b]
    tool: str | None
    args: dict
    action: str
    observation: str
    guard_state: str
    guard_reason: str
    guard_message: str
    executed: bool
    done: str


def build_graph(propose, guard: PlateauGuard, max_turns: int = 20):
    """Wire the graph. Four nodes; two of them are the guard."""
    from langgraph.graph import END, START, StateGraph

    def agent(state: AgentState) -> dict:
        """Pick the next tool call. Knows nothing about any breaker."""
        tool, args = propose(state)
        return {
            "turn": state["turn"] + 1,
            "tool": tool,
            "args": args,
            "action": render_call(tool, args) if tool else "",
            "done": "" if tool else "the model gave a final answer",
        }

    def guard_before(state: AgentState) -> dict:
        """Hook 1. Veto before the tool runs, once the breaker is open."""
        decision = guard.before_tool(state["action"])
        if decision is None or decision.allowed:
            # `executed` must be reset on every allowed turn. Leaving it sticky
            # meant one veto routed the graph back to `agent` forever: the
            # breaker recovered to HALF_OPEN, wanted to probe, and never got
            # another tool call. The run then burned its remaining turns
            # proposing actions nobody executed.
            return {"guard_state": guard.state, "executed": True}
        return {
            "guard_state": decision.state.value,
            "guard_reason": decision.reason,
            "guard_message": decision.message,
            "executed": False,
            # The refusal is fed back as context, which is the whole point:
            # the agent is told WHY and where the last new information was.
            "history": [{"turn": state["turn"], "action": state["action"],
                         "observation": "(refused)", "state": decision.state.value,
                         "reason": decision.reason}],
        }

    def tools(state: AgentState) -> dict:
        observation = execute(state["tool"], state["args"]).observation
        return {"observation": observation, "executed": True}

    def guard_after(state: AgentState) -> dict:
        """Hook 2. Score the completed turn — the call that embeds."""
        decision = guard.after_tool(state["action"], state["observation"])
        reading = decision.reading
        return {
            "guard_state": decision.state.value,
            "guard_reason": decision.reason if not decision.allowed else "",
            "guard_message": decision.message if not decision.allowed else "",
            "history": [{
                "turn": state["turn"], "action": state["action"],
                "observation": state["observation"], "state": decision.state.value,
                "allowed": decision.allowed,
                "action_sim": round(reading.action_sim, 3) if reading else None,
                "obs_novelty": round(reading.obs_novelty, 3) if reading else None,
                "quadrant": reading.quadrant.value if reading else None,
                "reason": decision.reason if not decision.allowed else "",
            }],
        }

    def after_agent(state: AgentState) -> str:
        if state["done"] or state["turn"] >= max_turns:
            return END
        return "guard_before"

    def after_guard_before(state: AgentState) -> str:
        # Vetoed turns skip execution entirely — no tool call, no embedding.
        return "agent" if state["executed"] is False else "tools"

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_node("guard_before", guard_before)
    graph.add_node("tools", tools)
    graph.add_node("guard_after", guard_after)

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", after_agent, {END: END, "guard_before": "guard_before"})
    graph.add_conditional_edges("guard_before", after_guard_before, {"agent": "agent", "tools": "tools"})
    graph.add_edge("tools", "guard_after")
    graph.add_conditional_edges(
        "guard_after", lambda s: END if s["turn"] >= max_turns else "agent",
        {END: END, "agent": "agent"},
    )
    return graph.compile()


# ---------------------------------------------------------------------------
# two ways to drive it
# ---------------------------------------------------------------------------

#: The scripted stall: a real survey, then the same dead end forever. Identical
#: in shape to demo/live_agent.py's SURVEY plus the loop the model falls into,
#: so this runs in a second with no model server and no variance.
SCRIPT: list[tuple[str, dict]] = [
    ("list_dir", {"path": "docs"}),
    ("read_file", {"path": "docs/auth.md"}),
    ("read_file", {"path": "docs/runbook.md"}),
    ("read_file", {"path": "config/app.yaml"}),
    ("search_docs", {"query": "where is the client secret stored"}),
    ("read_file", {"path": "docs/permissions.md"}),
] + [("vault_get", {"path": "app/oauth"})] * 20


def scripted_propose(state: AgentState) -> tuple[str | None, dict]:
    index = min(state["turn"], len(SCRIPT) - 1)
    return SCRIPT[index]


def ollama_propose_factory(model: str = "llama3.1:8b"):
    """A real model, through langchain_ollama, with the same tools."""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    from langchain_ollama import ChatOllama

    llm = ChatOllama(model=model, temperature=0, seed=1337).bind_tools(
        [t["function"] for t in TOOL_SCHEMA]
    )
    system = SystemMessage(
        "You are an autonomous engineering agent. Call exactly one tool per turn. "
        "Survey the repository before attempting any privileged operation."
    )

    def propose(state: AgentState) -> tuple[str | None, dict]:
        messages: list[Any] = [system, HumanMessage(TASK)]
        for row in state["history"]:
            messages.append(AIMessage(row["action"]))
            messages.append(HumanMessage(row["observation"]))
        reply = llm.invoke(messages)
        calls = getattr(reply, "tool_calls", None) or []
        if not calls:
            return None, {}
        return calls[0]["name"], calls[0].get("args") or {}

    return propose


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama", action="store_true", help="use a real llama3.1:8b")
    parser.add_argument("--max-turns", type=int, default=16)
    args = parser.parse_args()

    guard = PlateauGuard()
    propose = ollama_propose_factory() if args.ollama else scripted_propose
    app = build_graph(propose, guard, max_turns=args.max_turns)

    final = app.invoke(
        {"turn": 0, "history": [], "tool": None, "args": {}, "action": "",
         "observation": "", "guard_state": "CALIBRATING", "guard_reason": "",
         "guard_message": "", "executed": True, "done": ""},
        {"recursion_limit": 200},
    )

    print(f"\n  task: {TASK}\n")
    for row in final["history"]:
        dials = ""
        if row.get("action_sim") is not None:
            dials = f"  sim {row['action_sim']:.2f}  nov {row['obs_novelty']:.2f}  {row['quadrant']}"
        mark = "REFUSED " if row["observation"] == "(refused)" else ""
        print(f"  {row['turn']:>3}  {row['state']:<11} {mark}{row['action']}{dials}")
        if row.get("reason"):
            print(f"       -> {row['reason']}")

    executed = [r for r in final["history"] if r["observation"] != "(refused)"]
    refused = [r for r in final["history"] if r["observation"] == "(refused)"]
    print(f"\n  {len(executed)} executed, {len(refused)} refused, "
          f"breaker {guard.state}")
    if guard.breaker.encoder is not None:
        print(f"  encoder calls: {guard.breaker.encoder.n_encode_calls} "
              f"(nothing was embedded on the {len(refused)} refused turns)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
