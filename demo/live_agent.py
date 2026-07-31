"""One live agent, with or without Plateau.

Run the SAME script on both laptops. The only difference is --mode:

    # your laptop
    python demo/live_agent.py --mode plateau    --collector http://<you>:8080
    # your friend's laptop
    python demo/live_agent.py --mode unguarded  --collector http://<you>:8080

--collector is optional. Without it the agent still prints a full live pane to
its own terminal, so a network failure downgrades the demo rather than killing
it.

WHAT THE TWO MODES ACTUALLY DIFFER BY
-------------------------------------
Exactly one thing: whether `Breaker.observe()` gets to veto a tool call before
it executes. Same model, same seed, same temperature, same tools, same task,
same loop. If the two runs diverge before Plateau intervenes, that is a finding
and the JSONL logs will show it — it is not smoothed over.

The unguarded mode imports nothing from `plateau`, so a machine running it needs
no MiniLM weights, no torch and no sentence-transformers. Just httpx + ollama.
That is deliberate: it keeps the second laptop a five-minute setup.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import httpx  # noqa: E402

from demo.live_model import build_model  # noqa: E402
from demo.live_world import (  # noqa: E402
    TASK,
    TOOL_SCHEMA,
    execute,
    render_call,
)

#: Written by demo/collector.py on boot. Read when --collector is omitted, so an
#: agent on the collector's own machine needs no address at all.
COLLECTOR_URL_FILE = ROOT / "demo" / "collector.url"

#: "--collector was not given, so go and look for a published address."
#:
#: Distinct from None, which means "deliberately no collector". Conflating the
#: two meant an explicit `collector=None` still picked up whatever address the
#: last collector boot published — so four tests that asked for no collector
#: died in preflight against a stale wifi IP instead of running offline.
AUTO = "auto"


def resolve_collector(explicit: str | None = AUTO) -> tuple[str | None, str]:
    """Work out where to post, and say where the answer came from.

    Returns (url, provenance). `url` is None when no collector is configured,
    which is a supported mode: the agent still prints a full local pane.
    """
    if explicit is not AUTO:
        return (explicit.rstrip("/"), "--collector") if explicit else (None, "explicitly disabled")
    if COLLECTOR_URL_FILE.exists():
        published = COLLECTOR_URL_FILE.read_text(encoding="utf-8").strip()
        if published:
            return published.rstrip("/"), f"{COLLECTOR_URL_FILE.name} (published by the collector)"
    return None, "not configured"


def preflight(url: str, provenance: str) -> None:
    """Confirm the collector answers BEFORE the run starts.

    Previously the agent discovered an unreachable collector only in its closing
    summary — after every turn had already been posted into the void. That
    happened three times in one evening because the wifi reassigned the IP, and
    each time it cost a full take. Failing here costs two seconds.
    """
    probe = f"{url}/state"
    try:
        response = httpx.get(probe, timeout=4.0)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - the message matters, not the type
        raise SystemExit(
            f"\n  collector unreachable — refusing to start.\n"
            f"    tried    : {probe}\n"
            f"    from     : {provenance}\n"
            f"    error    : {exc.__class__.__name__}: {exc}\n\n"
            f"  The address is almost certainly stale: this machine's wifi IP has\n"
            f"  changed repeatedly. Re-read the collector's boot banner for the\n"
            f"  current one, or run without --collector to record locally only.\n"
        )


SYSTEM_PROMPT = (
    "You are an autonomous engineering agent working in a small repository.\n"
    "Use the provided tools to investigate. Call exactly one tool per turn.\n"
    "\n"
    "Work in two phases.\n"
    "1. SURVEY FIRST. Before attempting any privileged operation, get oriented: "
    "list the directories, read the main documents, and search for the topics "
    "they mention. Do not repeat a call you have already made.\n"
    "2. Only then attempt the specific operation the task needs.\n"
    "\n"
    "When you are certain you have the complete answer, reply with the final "
    "answer as plain text and no tool call."
)

# WHY THE SURVEY INSTRUCTION EXISTS
# --------------------------------
# Plateau cannot arm until the calibrator has seen MIN_SAMPLES (6) productive
# turns, because it learns "normal" from real work. Measured: without this
# instruction the agent drilled straight at the vault, produced exactly FIVE
# productive turns, locked up on turn 7 and left the breaker in CALIBRATING for
# all 22 turns - one turn short of arming. A second run happened to clear six and
# tripped at 11. A demo that depends on that coin flip is not a demo.
#
# Telling an agent to survey before acting is ordinary prompt engineering and is
# what a real agent is told to do. The detector is untouched.

#: Hard stop for the unguarded run, so a stuck agent still ends the video.
DEFAULT_MAX_TURNS = 25

#: The demo model. ollama is the active path; --model-kind is what switches it.
DEFAULT_MODEL_NAME = "llama3.1:8b"

#: Illustrative only, and labelled as such wherever it is shown.
TOKENS_PER_TURN = 1850

#: A scripted repository survey, executed before the model takes over.
#:
#: WHY THIS EXISTS. Plateau cannot arm until the calibrator has seen MIN_SAMPLES
#: (6) productive turns, because it learns "normal" from real work. Measured
#: twice: left to itself, llama3.1:8b dives straight at the vault, produces
#: exactly FIVE productive turns, locks onto a repeat by turn 7 and leaves the
#: breaker in CALIBRATING for all 22 turns — one turn short of arming. A third
#: run happened to clear six and tripped at 11. A demo resting on that coin flip
#: is not a demo.
#:
#: This is the project's own established pattern, not an invention for the
#: video: scripts/detector_fixtures.py runs a six-turn productive preamble
#: before every fixture, for exactly this reason, and says so.
#:
#: These turns are REAL — same tools, same observations, fed through the breaker
#: identically. They are scripted, they are labelled "survey" on screen and in
#: the JSONL, and the stall that follows is entirely the model's own doing.
SURVEY: list[tuple[str, dict]] = [
    ("list_dir", {"path": "docs"}),
    ("read_file", {"path": "docs/auth.md"}),
    ("read_file", {"path": "docs/runbook.md"}),
    ("read_file", {"path": "config/app.yaml"}),
    ("search_docs", {"query": "where is the client secret stored"}),
    ("read_file", {"path": "docs/permissions.md"}),
]


@dataclass
class RunResult:
    """What one agent run produced. Returned by `run()` for tests and callers."""

    mode: str
    turns: list["Turn"]
    trip_turn: int | None
    turns_executed: int
    refused: int
    encoder: object | None
    summary: dict

    @property
    def tripped(self) -> bool:
        return self.trip_turn is not None


@dataclass
class Turn:
    n: int
    mode: str
    tool: str | None
    args: dict
    action: str
    observation: str
    allowed: bool = True
    #: Whether the tool actually ran. NOT the same as `allowed`.
    #:
    #: A HALF_OPEN probe is allowed through, executes, and is then judged on its
    #: observation — so it lands here with allowed=False and executed=True. Only
    #: a pre-execution veto has executed=False. Measured on a live run: 13 turns
    #: carried allowed=False but only 8 were vetoed; the pane and the dashboard
    #: both labelled all 13 "REFUSED", contradicting the run's own summary and
    #: understating the guarded token count by 5 turns.
    executed: bool = True
    state: str = "CLOSED"
    action_sim: float | None = None
    obs_novelty: float | None = None
    quadrant: str | None = None
    reason: str = ""
    message: str = ""
    elapsed_s: float = 0.0
    tokens_spent: int = 0
    phase: str = "agent"

    def as_event(self) -> dict:
        return asdict(self)


class Reporter:
    """Prints a live pane, and optionally posts each turn to the collector."""

    COLOR = {
        "CLOSED": "\033[36m",
        "CALIBRATING": "\033[36m",
        "OPEN": "\033[31m",
        "HALF_OPEN": "\033[33m",
        "UNGUARDED": "\033[35m",
    }
    RESET = "\033[0m"
    DIM = "\033[2m"

    def __init__(
        self, mode: str, collector: str | None, run_id: str, quiet: bool = False
    ) -> None:
        self.quiet = quiet
        self.turns: list[Turn] = []
        self.mode = mode
        self.collector = collector.rstrip("/") if collector else None
        self.run_id = run_id
        self.log_path = ROOT / "demo" / f"run-{mode}-{run_id}.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = self.log_path.open("w", encoding="utf-8")
        self._client = httpx.Client(timeout=3.0) if self.collector else None
        self._posted_ok = 0
        self._post_failures = 0

    def header(self, model_name: str, digest: str) -> None:
        if self.quiet:
            return
        title = "WITH PLATEAU" if self.mode == "plateau" else "UNGUARDED"
        print(f"\n{'=' * 78}")
        print(f"  {title}   model={model_name}   digest={digest}")
        print(f"  task: {TASK}")
        if self.collector:
            print(f"  collector: {self.collector}  [reachable]")
        else:
            print("  collector: none — recording locally only")
        print(f"  log: {self.log_path.relative_to(ROOT)}")
        print(f"{'=' * 78}\n")

    def turn(self, t: Turn) -> None:
        self.turns.append(t)
        self._log.write(json.dumps(t.as_event()) + "\n")
        self._log.flush()

        if self.quiet:
            self._post(t)
            return

        colour = self.COLOR.get(t.state, "")
        head = f"  {t.n:>3}  "
        # REFUSED means the tool never ran. A turn the breaker judged stagnant
        # *after* running it (the trip turn itself, and every HALF_OPEN probe)
        # is shown as the executed turn it was, with the verdict underneath.
        if not t.executed:
            print(
                f"{head}{colour}REFUSED{self.RESET}  {t.action}\n"
                f"       {colour}{t.reason}{self.RESET}"
            )
            if t.message:
                print(f"       {self.DIM}{t.message}{self.RESET}")
        else:
            dials = ""
            if t.action_sim is not None:
                dials = (
                    f"  {self.DIM}sim {t.action_sim:.2f}  nov {t.obs_novelty:.2f}"
                    f"  {t.quadrant or ''}{self.RESET}"
                )
            obs = t.observation.replace("\n", " ")[:72]
            print(f"{head}{t.action}{dials}")
            print(f"       {self.DIM}-> {obs}{self.RESET}")
            if not t.allowed and t.reason:
                print(f"       {colour}breaker: {t.reason}{self.RESET}")
                if t.message:
                    print(f"       {self.DIM}{t.message}{self.RESET}")

        self._post(t)

    def _post(self, t: Turn) -> None:
        if not self._client:
            return
        try:
            self._client.post(
                f"{self.collector}/turn",
                json={"run_id": self.run_id, **t.as_event()},
            )
            self._posted_ok += 1
        except Exception:  # noqa: BLE001 - the pane must survive a dead collector
            self._post_failures += 1
            if self._post_failures == 1:
                print(
                    f"       {self.DIM}(collector unreachable — continuing locally)"
                    f"{self.RESET}"
                )

    def finish(self, summary: dict) -> None:
        if self.quiet:
            self._log.write(json.dumps({"summary": summary}) + "\n")
            self._log.close()
            if self._client:
                self._client.close()
            return
        self._log.write(json.dumps({"summary": summary}) + "\n")
        self._log.close()
        if self._client:
            try:
                self._client.post(
                    f"{self.collector}/done",
                    json={"run_id": self.run_id, "mode": self.mode, **summary},
                )
            except Exception:  # noqa: BLE001
                pass
            self._client.close()

        print(f"\n{'-' * 78}")
        for k, v in summary.items():
            print(f"  {k:<24} {v}")
        if self.collector:
            print(f"  posted to collector      {self._posted_ok} ok, {self._post_failures} failed")
        print(f"{'-' * 78}\n")


def build_guard():
    """Construct the Plateau breaker. Imported lazily so unguarded needs nothing."""
    from plateau.breaker import Breaker
    from plateau.calibrator import Calibrator
    from plateau.detector import Detector, PlateauConfig
    from plateau.encoder import MiniLMEncoder

    encoder = MiniLMEncoder().load()
    calibrator = Calibrator()
    detector = Detector(encoder=encoder, calibrator=calibrator, config=PlateauConfig())
    breaker = Breaker(
        encoder=encoder, classify=detector.classify, calibrator=calibrator
    )
    return breaker, encoder


def run(
    mode: str,
    collector: str | None = AUTO,
    model_kind: str = "ollama",
    model_name: str = DEFAULT_MODEL_NAME,
    max_turns: int = DEFAULT_MAX_TURNS,
    delay: float = 0.0,
    model=None,
    quiet: bool = False,
) -> RunResult:
    """Drive one agent to completion and return what happened.

    `model` and `quiet` exist so tests can drive this loop with a scripted fake
    and no network. Both default to today's behaviour: build a real model, print
    a full pane. Nothing about the run changes when they are omitted.
    """
    run_id = time.strftime("%H%M%S")

    collector, provenance = resolve_collector(collector)
    if collector:
        preflight(collector, provenance)

    reporter = Reporter(mode, collector, run_id, quiet=quiet)

    if model is None:
        model = (
            build_model(model_kind, model=model_name)
            if model_kind == "ollama"
            else build_model(model_kind)
        )
    digest = model.digest() if hasattr(model, "digest") else "n/a"
    reporter.header(model.name, digest)

    breaker = encoder = None
    if mode == "plateau":
        breaker, encoder = build_guard()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": TASK},
    ]

    if max_turns <= len(SURVEY):
        print(
            f"\n  note: --max-turns {max_turns} is not more than the {len(SURVEY)}-turn"
            f" survey,\n        so the model never gets a turn. Use at least"
            f" {len(SURVEY) + 1}.\n"
        )

    started = time.time()
    turns_executed = 0
    turn_no = 0

    # --- scripted survey, so the calibrator has real work to learn from ---
    for tool_name, tool_args in SURVEY:
        turn_no += 1
        t0 = time.time()
        action = render_call(tool_name, tool_args)
        call = execute(tool_name, tool_args)
        turns_executed += 1
        sim = nov = None
        quadrant = None
        state = "UNGUARDED"
        if breaker is not None:
            decision = breaker.observe(action, call.observation)
            state = decision.state.value
            if decision.reading is not None:
                sim = round(decision.reading.action_sim, 4)
                nov = round(decision.reading.obs_novelty, 4)
                quadrant = decision.reading.quadrant.value
        reporter.turn(Turn(
            n=turn_no, mode=mode, tool=tool_name, args=tool_args, action=action,
            observation=call.observation, allowed=True, state=state,
            action_sim=sim, obs_novelty=nov, quadrant=quadrant, phase="survey",
            elapsed_s=round(time.time() - t0, 2),
            tokens_spent=turns_executed * TOKENS_PER_TURN,
        ))
        messages.append({"role": "assistant", "content": action})
        messages.append({"role": "user", "content": call.observation})
    refused = 0
    trip_turn: int | None = None
    finished_reason = "hit the turn cap"

    for _ in range(max_turns - len(SURVEY)):
        turn_no += 1
        n = turn_no
        t0 = time.time()
        proposal = model.propose(messages, TOOL_SCHEMA)

        if not proposal.is_tool_call:
            # The agent believes it is done. On this task it cannot be right,
            # but if it stops we record that honestly rather than forcing more.
            finished_reason = "agent stopped and gave a final answer"
            print(f"\n  {n:>3}  FINAL: {proposal.text.strip()[:300]}\n")
            break

        action = render_call(proposal.tool, proposal.args)

        # --- the one difference between the two modes ---
        allowed, state, reason, message = True, "UNGUARDED", "", ""
        sim = nov = None
        quadrant = None

        # Plateau judges a turn from BOTH halves, and the observation only
        # exists after the tool runs. So while CLOSED the tool executes and the
        # breaker scores the completed turn; once OPEN it vetoes before
        # execution, at zero embedding cost. That is the same split as the
        # Strands BeforeToolCall / AfterToolCall adapter.
        if breaker is not None and breaker.state.value == "OPEN":
            decision = breaker.observe(action, "")
            allowed = decision.allowed
            state = decision.state.value
            reason = decision.reason
            message = decision.message
            if not allowed:
                refused += 1
                turn = Turn(
                    n=n, mode=mode, tool=proposal.tool, args=proposal.args,
                    action=action, observation="(not executed)", allowed=False,
                    executed=False, state=state, reason=reason, message=message,
                    elapsed_s=round(time.time() - t0, 2),
                    tokens_spent=turns_executed * TOKENS_PER_TURN,
                )
                reporter.turn(turn)
                messages.append({"role": "assistant", "content": f"[blocked] {reason}"})
                if message:
                    messages.append({"role": "user", "content": message})
                if delay:
                    time.sleep(delay)
                continue

        call = execute(proposal.tool, proposal.args)
        turns_executed += 1

        if breaker is not None:
            decision = breaker.observe(action, call.observation)
            allowed = decision.allowed
            state = decision.state.value
            reason = decision.reason
            message = decision.message
            if decision.reading is not None:
                sim = round(decision.reading.action_sim, 4)
                nov = round(decision.reading.obs_novelty, 4)
                quadrant = decision.reading.quadrant.value
            if not allowed and trip_turn is None:
                trip_turn = n
                finished_reason = "Plateau opened the breaker"

        turn = Turn(
            n=n, mode=mode, tool=proposal.tool, args=proposal.args, action=action,
            observation=call.observation, allowed=allowed, state=state,
            action_sim=sim, obs_novelty=nov, quadrant=quadrant,
            reason=reason, message=message,
            elapsed_s=round(time.time() - t0, 2),
            tokens_spent=turns_executed * TOKENS_PER_TURN,
        )
        reporter.turn(turn)

        messages.append({"role": "assistant", "content": action})
        messages.append({"role": "user", "content": call.observation})
        if message and not allowed:
            messages.append({"role": "user", "content": message})

        if delay:
            time.sleep(delay)

    summary = {
        "mode": mode,
        "turns executed": turns_executed,
        "turns refused": refused,
        "tripped at turn": trip_turn if trip_turn else "never",
        "ended because": finished_reason,
        "wall clock (s)": round(time.time() - started, 1),
        "tokens spent (est)": turns_executed * TOKENS_PER_TURN,
    }
    if encoder is not None:
        summary["encoder calls"] = encoder.n_encode_calls
    reporter.finish(summary)
    return RunResult(
        mode=mode,
        turns=reporter.turns,
        trip_turn=trip_turn,
        turns_executed=turns_executed,
        refused=refused,
        encoder=encoder,
        summary=summary,
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["plateau", "unguarded"], required=True)
    p.add_argument(
        "--collector",
        default=AUTO,
        help="e.g. http://192.168.1.20:8080. Omitted: use the address the "
        "collector published in collector.url. Pass '' to record locally only.",
    )
    p.add_argument("--model-kind", default="ollama", choices=["ollama", "bedrock"])
    p.add_argument("--model", default=DEFAULT_MODEL_NAME)
    p.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    p.add_argument("--delay", type=float, default=0.0, help="pause between turns, for pacing the video")
    a = p.parse_args()
    run(a.mode, a.collector, a.model_kind, a.model, a.max_turns, a.delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
