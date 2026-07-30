import {
  COLD_CEILING,
  MIN_SAMPLES,
  NOVELTY_FLOOR,
  TRACE,
  TRIP_STREAK,
  WARM_CEILING,
} from "../data/trace.js";

/* ============================================================================
 * VERBATIM PORT — DO NOT EDIT THE SEMANTICS.
 *
 * This is the breaker decision, moved out of the draft component unchanged.
 * The four thresholds it reads are calibrated to this trace and are what put
 * the trip on turn 13.
 *
 * `scripts/parity.mjs` extracts the original function straight out of
 * PlateauConsole.jsx and diffs every field of every row against this one over
 * every step. If you change anything here that alters behaviour, that script
 * fails. That is the intent: the demo's numbers are rehearsed, so this file is
 * frozen by test rather than by comment.
 *
 * Recovery (cooldown / HALF_OPEN / probe) is deliberately NOT modelled here.
 * It lives in deriveRecovery.js and runs only after this function has already
 * returned a trip, precisely so that this function stays untouched.
 * ========================================================================= */

/**
 * Derive live breaker + calibrator state from the revealed turns.
 *
 * @param {number} step  index of the last revealed turn; -1 = idle
 * @param {Array}  trace the trace to read. Defaults to the live one; the
 *   parameter exists so scripts/parity.mjs can run this function over the
 *   draft's original trace and prove the ALGORITHM is unchanged independently
 *   of the trace data having moved on. Behaviour with the default is identical.
 */
export function deriveState(step, trace = TRACE) {
  // step = index of last revealed turn, -1 = idle
  let n = 0; // productive turns (passed novelty gate)
  let streak = 0; // trailing consecutive sub-floor turns
  let tripTurn = null;

  const rows = [];
  for (let i = 0; i <= step; i++) {
    const t = trace[i];
    if (t.nov >= NOVELTY_FLOOR) n += 1; // C1 gate: only informative turns teach
    const warm = n >= MIN_SAMPLES;
    const ceiling = warm ? WARM_CEILING : COLD_CEILING;

    if (t.nov < NOVELTY_FLOOR) streak += 1;
    else streak = 0;
    if (warm && streak >= TRIP_STREAK && tripTurn === null) tripTurn = i + 1;

    const quadrant =
      t.nov < NOVELTY_FLOOR
        ? t.sim >= ceiling
          ? "stuck"
          : "thrash"
        : t.sim >= ceiling
          ? "batch"
          : "productive";

    rows.push({ ...t, turn: i + 1, ceiling, warm, quadrant, streak });
  }

  const warm = n >= MIN_SAMPLES;
  const ceiling = warm ? WARM_CEILING : COLD_CEILING;
  const last = rows[rows.length - 1];

  let state = "idle";
  if (step >= 0) {
    if (tripTurn !== null) state = "open";
    else if (!warm) state = "calibrating";
    else if (last && last.nov < NOVELTY_FLOOR) state = "watching";
    else state = "closed";
  }

  return { rows, n, warm, ceiling, state, tripTurn, streak };
}

/**
 * The turn the breaker trips on, derived rather than hardcoded.
 *
 * The draft carried `TRIP_TURN = 13` as a literal *and* computed `tripTurn`
 * inside deriveState. The two agreed only because the current thresholds
 * happened to make them agree; change a threshold and the copy silently
 * disagrees with the machine. One source of truth instead.
 */
export const TRIP_TURN = deriveState(TRACE.length - 1).tripTurn;
