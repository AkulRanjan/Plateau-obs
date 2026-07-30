"""Two-pane terminal demo: a repetition detector vs Plateau, on the same trace.

    python demo/demo.py              # both scenes
    python demo/demo.py --scene loop # headline only
    python demo/demo.py --scene batch
    python demo/demo.py --no-anim    # no delays, for recording stills

Scene 1, the headline: a coding agent works for six turns, then spends 55 more
rewording one search that never answers. The exact-match baseline burns all 61
turns. Plateau trips, hands back an escape vector, cools down, probes, recovers.

Scene 2, the counter-demo: 61 turns of invoice extraction. Actions are
near-identical (0.9913 measured at gate 1) but every record differs. Plateau
holds. Its own action-only ablation -- the same detector with the observation
half blinded, which is what every shipped repetition detector sees -- trips.

WHAT IS MEASURED AND WHAT IS ASSUMED
------------------------------------
Measured here, live: every quadrant, dial reading, trip turn, and encoder call.
Turns saved is measured.

Assumed: the token-per-turn figures in COST_MODEL. They are stated on screen and
are NOT a result. Pricing is real -- Claude Opus 5 at $5/$25 per million input
/output tokens -- but tokens per turn depends entirely on the agent, so the
dollar figure is illustrative arithmetic over a stated assumption, not a
measurement of anything this repository ran.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("HF_HUB_OFFLINE", "1")

# Windows consoles default to cp1252, which cannot encode the box-drawing
# characters this demo uses. Reconfigure rather than degrade the output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from eval.baselines import BaselineTurn  # noqa: E402
from eval.baselines.exact_match import detect as exact_match_detect  # noqa: E402
from eval.traces import (  # noqa: E402
    HEALTHY_INVOICE_BATCH,
    PREAMBLE_LENGTH,
    RUNAWAY_PARAPHRASE_LOOP,
)
from plateau.breaker import Breaker, State  # noqa: E402
from plateau.calibrator import Calibrator  # noqa: E402
from plateau.detector import Detector, PlateauConfig, Quadrant  # noqa: E402
from plateau.encoder import MiniLMEncoder  # noqa: E402

# --- cost model: ASSUMPTIONS, not measurements -------------------------------
# Pricing is published (Claude Opus 5, $5/$25 per 1M input/output tokens).
# Everything else here is a stated assumption about a hypothetical agent.
COST_MODEL = {
    "model": "claude-opus-5",
    "usd_per_1m_input": 5.00,
    "usd_per_1m_output": 25.00,
    # A turn re-sends the accumulated context, so input grows with turn index.
    "input_tokens_base": 1800,
    "input_tokens_growth_per_turn": 220,
    "output_tokens_per_turn": 320,
}


def turn_cost_usd(turn_index: int) -> float:
    """Illustrative cost of one agent turn under the stated assumptions."""
    inp = (
        COST_MODEL["input_tokens_base"]
        + COST_MODEL["input_tokens_growth_per_turn"] * turn_index
    )
    out = COST_MODEL["output_tokens_per_turn"]
    return (
        inp / 1_000_000 * COST_MODEL["usd_per_1m_input"]
        + out / 1_000_000 * COST_MODEL["usd_per_1m_output"]
    )


# --- terminal helpers --------------------------------------------------------
PANE = 46
GAP = "   "

C = {
    "reset": "\033[0m", "dim": "\033[2m", "bold": "\033[1m",
    "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
    "blue": "\033[34m", "magenta": "\033[35m", "cyan": "\033[36m",
    "grey": "\033[90m",
}

QUADRANT_COLOR = {
    Quadrant.GRIND: "cyan",
    Quadrant.EXPLORE: "green",
    Quadrant.LOOP: "red",
    Quadrant.THRASH: "yellow",
}


def supports_colour() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if sys.platform == "win32":
        try:
            import colorama  # noqa: F401
        except ImportError:
            os.system("")  # enables VT100 on modern Windows terminals
    return sys.stdout.isatty()


USE_COLOUR = supports_colour()


def paint(text: str, colour: str) -> str:
    if not USE_COLOUR or colour not in C:
        return text
    return f"{C[colour]}{text}{C['reset']}"


def visible_len(text: str) -> int:
    """Length ignoring ANSI escapes, so padding stays correct."""
    out, i = 0, 0
    while i < len(text):
        if text[i] == "\033":
            while i < len(text) and text[i] != "m":
                i += 1
            i += 1
        else:
            out += 1
            i += 1
    return out


def cell(text: str, width: int = PANE) -> str:
    pad = width - visible_len(text)
    return text + " " * max(0, pad)


def clip(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def rule(char: str = "─") -> str:
    print(paint(char * (PANE * 2 + len(GAP)), "grey"))


def headers(left: str, right: str) -> None:
    print(cell(paint(left, "bold")) + GAP + cell(paint(right, "bold")))
    print(
        cell(paint("─" * PANE, "grey"))
        + GAP
        + cell(paint("─" * PANE, "grey"))
    )


@dataclass
class Row:
    left: str = ""
    right: str = ""


def emit(row: Row, delay: float) -> None:
    print(cell(row.left) + GAP + cell(row.right))
    if delay:
        time.sleep(delay)


# --- scene 1: the headline ---------------------------------------------------


def scene_loop(encoder: MiniLMEncoder, delay: float) -> dict:
    trace = RUNAWAY_PARAPHRASE_LOOP
    print()
    print(paint("  SCENE 1 — a stall no repetition detector can see", "bold"))
    print(
        paint(
            f"  {len(trace)} turns. Six productive, then 55 rewordings of one "
            f"search that never answers.",
            "grey",
        )
    )
    print(
        paint(
            "  Every action string is unique, so exact matching has nothing to "
            "match on.",
            "grey",
        )
    )
    print()

    # Baseline: OpenHands StuckDetector at its published defaults.
    baseline_turns = [
        BaselineTurn(action_name=a.split("(")[0], action_input={"raw": a}, observation=o)
        for a, o in trace
    ]
    baseline_trip = exact_match_detect(baseline_turns)

    detector = Detector(encoder=encoder, calibrator=Calibrator(), config=PlateauConfig())
    breaker = Breaker(encoder=encoder, classify=detector.classify,
                      calibrator=detector.calibrator)

    headers("  exact-match baseline (OpenHands)", "  Plateau")

    plateau_stop = None
    plateau_cost = baseline_cost = 0.0
    recovered_at = None
    escape_message = ""

    for index, (action, observation) in enumerate(trace):
        cost = turn_cost_usd(index)
        baseline_cost += cost

        # --- baseline pane: it just keeps going ---
        tripped_now = baseline_trip == index
        if tripped_now:
            left = paint(f"  {index:>2} TRIPPED", "green")
        elif index < PREAMBLE_LENGTH:
            left = paint(f"  {index:>2} ", "grey") + clip(action, PANE - 6)
            left = paint(f"  {index:>2} ", "grey") + paint(
                clip(action.split("(")[0], 18), "grey")
        else:
            left = (
                paint(f"  {index:>2} ", "grey")
                + clip(action.split("q=")[-1].rstrip("')"), PANE - 8)
            )

        # --- Plateau pane ---
        if plateau_stop is None:
            decision = breaker.observe(action, observation)
            reading = decision.reading
            if decision.state is State.OPEN and decision.transition == 4:
                plateau_stop = index
                escape_message = decision.message
                right = paint(f"  {index:>2} OPEN — breaker tripped", "red")
            elif reading is not None:
                q = reading.quadrant
                right = (
                    paint(f"  {index:>2} ", "grey")
                    + paint(cell(q.value, 8), QUADRANT_COLOR[q])
                    + paint(
                        f"sim {reading.action_sim:.2f}  nov {reading.obs_novelty:.2f}",
                        "grey",
                    )
                )
                if reading.loop_hits:
                    right += paint(f"  loop {reading.loop_hits}", "yellow")
            else:
                right = ""
            plateau_cost += cost
        else:
            # Breaker is open: refusals cost nothing, and no embedding happens.
            decision = breaker.observe(action, observation)
            if decision.transition == 5:
                right = paint(f"  {index:>2} refused (cooldown), 0 tokens", "grey")
            elif decision.transition == 6:
                right = paint(f"  {index:>2} probe allowed", "cyan")
            elif decision.transition == 7:
                recovered_at = index
                right = paint(f"  {index:>2} recovered — CLOSED", "green")
                plateau_cost += cost
            elif decision.transition == 8:
                right = paint(f"  {index:>2} probe learned nothing, backoff", "yellow")
                plateau_cost += cost
            else:
                right = paint(f"  {index:>2} held", "grey")

        emit(Row(left, right), delay)

    print()
    rule()
    burned = len(trace) - (plateau_stop or len(trace))
    print(
        cell(
            "  "
            + paint(
                f"ran all {len(trace)} turns"
                if baseline_trip is None
                else f"tripped at turn {baseline_trip}",
                "red" if baseline_trip is None else "green",
            )
        )
        + GAP
        + cell(
            "  "
            + paint(
                f"tripped at turn {plateau_stop}"
                if plateau_stop is not None
                else "did not trip",
                "green" if plateau_stop is not None else "red",
            )
        )
    )
    print(
        cell(f"  illustrative spend  ${baseline_cost:6.3f}")
        + GAP
        + cell(f"  illustrative spend  ${plateau_cost:6.3f}")
    )
    print()
    print(paint(f"  turns saved (measured): {burned} of {len(trace)}", "bold"))
    print(
        paint(
            f"  illustrative saving: ${baseline_cost - plateau_cost:.3f} "
            f"under the stated token assumption",
            "grey",
        )
    )
    if recovered_at is not None:
        print(paint(f"  recovered at turn {recovered_at} via an evaluated probe", "green"))

    if escape_message:
        print()
        print(paint("  escape vector handed back to the agent:", "bold"))
        for line in _wrap(escape_message, PANE * 2):
            print(paint("    " + line, "cyan"))

    return {
        "trace_turns": len(trace),
        "baseline_trip_turn": baseline_trip,
        "plateau_trip_turn": plateau_stop,
        "recovered_at": recovered_at,
        "turns_saved": burned,
        "baseline_cost_usd": round(baseline_cost, 4),
        "plateau_cost_usd": round(plateau_cost, 4),
        "encoder_calls": encoder.n_encode_calls,
    }


def _wrap(text: str, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        if len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines


# --- scene 2: the counter-demo ----------------------------------------------


def scene_batch(encoder: MiniLMEncoder, delay: float) -> dict:
    trace = HEALTHY_INVOICE_BATCH
    print()
    print(paint("  SCENE 2 — the counter-demo: a healthy batch job", "bold"))
    print(
        paint(
            f"  {len(trace)} turns of invoice extraction. Actions are 0.9913 "
            f"similar (measured).",
            "grey",
        )
    )
    print(
        paint(
            "  Left is Plateau with the observation half blinded — what an "
            "action-only detector sees.",
            "grey",
        )
    )
    print()

    ablated = Detector(
        encoder=encoder,
        calibrator=Calibrator(),
        config=PlateauConfig(action_only=True),
    )
    full = Detector(encoder=encoder, calibrator=Calibrator(), config=PlateauConfig())

    headers("  action-only ablation", "  Plateau (both dials)")

    ablated_trip = full_trip = None
    for index, (action, observation) in enumerate(trace):
        a_reading = ablated.evaluate(action, observation) if ablated_trip is None else None
        f_reading = full.evaluate(action, observation)

        if a_reading is not None and a_reading.is_trip and ablated_trip is None:
            ablated_trip = index
            left = paint(f"  {index:>2} TRIPPED — healthy job stopped", "red")
        elif a_reading is not None:
            left = (
                paint(f"  {index:>2} ", "grey")
                + paint(cell(a_reading.quadrant.value, 8), QUADRANT_COLOR[a_reading.quadrant])
                + paint(f"nov pinned {a_reading.obs_novelty:.2f}", "grey")
            )
        else:
            left = paint(f"  {index:>2} (stopped)", "grey")

        if f_reading.is_trip and full_trip is None:
            full_trip = index
        right = (
            paint(f"  {index:>2} ", "grey")
            + paint(cell(f_reading.quadrant.value, 8), QUADRANT_COLOR[f_reading.quadrant])
            + paint(
                f"sim {f_reading.action_sim:.2f}  nov {f_reading.obs_novelty:.2f}",
                "grey",
            )
        )
        emit(Row(left, right), delay)

    print()
    rule()
    print(
        cell(
            "  "
            + paint(
                f"tripped at turn {ablated_trip}" if ablated_trip is not None
                else "did not trip",
                "red" if ablated_trip is not None else "green",
            )
        )
        + GAP
        + cell(
            "  "
            + paint(
                "held for the whole run" if full_trip is None
                else f"tripped at turn {full_trip}",
                "green" if full_trip is None else "red",
            )
        )
    )
    print()
    if ablated_trip is not None and full_trip is None:
        print(
            paint(
                "  Similarity alone condemns this job: action_sim reaches 0.99, above "
                "the ceiling.",
                "bold",
            )
        )
        print(
            paint(
                "  Only observation novelty keeps it alive. That is the joint design "
                "earning its place.",
                "bold",
            )
        )

    # Be precise about what the ablation does and does not show.
    print()
    print(paint("  Two honest caveats on this scene:", "yellow"))
    print(
        paint(
            f"  1. The ablation trips at turn {ablated_trip} — inside the productive "
            f"preamble, not on the",
            "grey",
        )
    )
    print(
        paint(
            "     invoices. Pinning novelty to 0 makes every turn stagnant, so it "
            "trips on any",
            "grey",
        )
    )
    print(
        paint(
            "     trace whatsoever. It isolates the novelty dial's contribution; it is "
            "not a",
            "grey",
        )
    )
    print(paint("     stand-in for a shipped detector.", "grey"))

    # The shipped detectors, at their published defaults, on this same trace.
    baseline_turns = [
        BaselineTurn(action_name=a.split("(")[0], action_input={"raw": a}, observation=o)
        for a, o in trace
    ]
    shipped = {"exact-match (OpenHands)": exact_match_detect(baseline_turns)}
    from eval.baselines.exact_args import detect as exact_args_detect
    from eval.baselines.lexical import detect as lexical_detect
    from eval.baselines.step_cap import detect as step_cap_detect

    shipped["exact-args debounce"] = exact_args_detect(baseline_turns)
    shipped["lexical (agent-loop-detector)"] = lexical_detect(baseline_turns)
    shipped["step-cap (LangGraph 25)"] = step_cap_detect(baseline_turns)

    held = [name for name, trip in shipped.items() if trip is None]
    print(
        paint(
            f"  2. The shipped detectors do NOT false-trip here either "
            f"({len(held)} of {len(shipped)} hold):",
            "grey",
        )
    )
    for name, trip in shipped.items():
        verdict = "holds" if trip is None else f"trips at {trip}"
        print(paint(f"     {name:<32} {verdict}", "grey"))
    print(
        paint(
            "     So this scene is not a win over the incumbents — it is evidence that "
            "the",
            "grey",
        )
    )
    print(paint("     novelty dial is what makes Plateau safe on repetitive work.", "grey"))

    return {
        "trace_turns": len(trace),
        "action_only_trip_turn": ablated_trip,
        "full_plateau_trip_turn": full_trip,
        "counter_demo_holds": full_trip is None and ablated_trip is not None,
        "shipped_baselines": shipped,
    }


# --- entry point ------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=["loop", "batch", "both"], default="both")
    parser.add_argument("--no-anim", action="store_true", help="no per-turn delay")
    args = parser.parse_args()
    delay = 0.0 if args.no_anim else 0.035

    encoder = MiniLMEncoder().load()

    print()
    rule("═")
    print(paint("  PLATEAU — a semantic circuit breaker for autonomous agents", "bold"))
    print(
        paint(
            f"  encoder {encoder.model_id} @ {(encoder.revision or '')[:12]}  "
            f"offline, CPU, seed 1337",
            "grey",
        )
    )
    rule("═")

    results = {}
    if args.scene in ("loop", "both"):
        results["scene_loop"] = scene_loop(encoder, delay)
    if args.scene in ("batch", "both"):
        results["scene_batch"] = scene_batch(encoder, delay)

    print()
    rule()
    print(paint("  Cost figures are ILLUSTRATIVE, not measured.", "yellow"))
    print(
        paint(
            f"  Real pricing ({COST_MODEL['model']}: "
            f"${COST_MODEL['usd_per_1m_input']:.2f}/"
            f"${COST_MODEL['usd_per_1m_output']:.2f} per 1M in/out) applied to an "
            f"ASSUMED",
            "grey",
        )
    )
    print(
        paint(
            f"  {COST_MODEL['input_tokens_base']} input tokens + "
            f"{COST_MODEL['input_tokens_growth_per_turn']}/turn growth and "
            f"{COST_MODEL['output_tokens_per_turn']} output tokens per turn.",
            "grey",
        )
    )
    print(paint("  Turns saved is measured. Dollars are arithmetic over an assumption.", "grey"))
    rule()
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
