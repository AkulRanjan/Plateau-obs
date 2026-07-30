import { NOVELTY_FLOOR, TRACE } from "../data/trace.js";
import { EPILOGUE, PROBE_NOVELTY } from "../data/epilogue.js";

/* ============================================================================
 * Recovery, kept deliberately OUT of deriveState.
 *
 * deriveState's semantics are frozen (see the note at the top of that file and
 * scripts/parity.mjs). It knows nothing about cooldowns, probes or HALF_OPEN,
 * and it must stay that way — so recovery is a separate reducer that only runs
 * once deriveState has already returned a trip.
 *
 * The two never interleave: deriveState owns turns 1..13, this owns what comes
 * after. That separation is why the parity check still passes with recovery
 * shipped.
 * ========================================================================= */

/**
 * The escape vector: the turn that taught the agent the most.
 *
 * One subtlety, stated rather than hidden. Turn 1 always reads novelty 1.00,
 * because on the first turn the comparison window is empty — there is nothing
 * yet for the observation to be redundant with. That is correct behaviour (the
 * detector documents it) but it is an artifact of the start of the run, not a
 * measure of how informative the turn was. Pointing a stuck agent back at "the
 * first thing you did" is useless advice.
 *
 * So the escape vector is the highest-novelty turn *after* the opening one, and
 * the opening turn's reading is reported alongside it so the choice is visible
 * rather than quietly applied.
 */
export function escapeVector(trace = TRACE) {
  const candidates = trace
    .map((t, i) => ({ ...t, turn: i + 1 }))
    .filter((t) => t.turn > 1);

  if (candidates.length === 0) return null;

  // Ties break toward the earlier turn: less has been built on top of it.
  const best = candidates.reduce((a, b) => (b.nov > a.nov ? b : a));

  return {
    turn: best.turn,
    tool: best.tool,
    args: best.args,
    obs: best.obs,
    novelty: best.nov,
    hasRoute: best.nov >= NOVELTY_FLOOR,
    openingTurnNovelty: trace[0]?.nov ?? null,
  };
}

/**
 * Reveal the recovery sequence one step at a time.
 *
 * @param {number} step  -1 = not started; 0..2 index into EPILOGUE
 * @returns {{steps: Array, state: string, done: boolean, probePassed: boolean}}
 */
export function deriveRecovery(step) {
  const steps = EPILOGUE.slice(0, step + 1).map((entry, i) => ({
    ...entry,
    // Turns continue the run's numbering: the trace ends at 13, so the refused
    // turn is 14 and the probe is 15. The third entry is a state transition
    // rather than a turn, so it carries no number.
    turn: entry.phase === "closed" ? null : TRACE.length + 1 + i,
  }));

  const last = steps[steps.length - 1];
  const probePassed = PROBE_NOVELTY >= NOVELTY_FLOOR && step >= 1;

  return {
    steps,
    state: last?.state ?? "OPEN",
    done: step >= EPILOGUE.length - 1,
    probePassed,
    total: EPILOGUE.length,
  };
}

/** Turns the run cost by being wrong: the refused turn, and nothing else. */
export const COST_OF_A_FALSE_TRIP_IN_TURNS = EPILOGUE.filter(
  (e) => e.phase === "cooldown"
).length;
