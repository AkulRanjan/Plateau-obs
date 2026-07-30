/* ------------------------------------------------------------------ *
 * What happens AFTER the breaker opens.
 *
 * This is claim 4 of the project's four: a false trip costs one turn, because
 * the agent recovers instead of dying. Nothing in the main console can show
 * that, because the main console stops — correctly — at the trip.
 *
 * These three entries are NOT part of TRACE and are not fed to deriveState.
 * They are a separate sequence driven by lib/deriveRecovery.js, so the trip
 * predicate stays exactly as it was. See the note in deriveRecovery.js.
 * ------------------------------------------------------------------ */

/**
 * Novelty returned by the probe turn.
 *
 * Above the floor, so the probe passes and the breaker closes. Chosen to match
 * the probe reading in the project's own simulator output (`sim_output.txt`,
 * the `recovers` trace: `HALF_OPEN 0.00 0.77 PROBE_PASS -> CLOSED`).
 */
export const PROBE_NOVELTY = 0.77;

export const EPILOGUE = [
  {
    phase: "cooldown",
    state: "OPEN",
    label: "refused",
    tool: "search_docs",
    args: "q='vault permission denied workaround'",
    obs: "Blocked by Plateau. No embedding computed — a tripped breaker costs nothing.",
    novelty: null,
    note: "The agent tried again anyway. While OPEN, Plateau does zero work: it refuses and hands back the reason and the escape vector.",
  },
  {
    phase: "probe",
    state: "HALF_OPEN",
    label: "one probe allowed",
    tool: "request_access",
    args: "scope='app/oauth'",
    obs: "Access request filed; temporary read granted for 1h.",
    novelty: PROBE_NOVELTY,
    note: "Cooldown spent, so exactly one probe gets through. It is judged on novelty alone — action similarity is not consulted, because we tripped for not learning and learning again is the only evidence that matters.",
  },
  {
    phase: "closed",
    state: "CLOSED",
    label: "probe passed",
    tool: null,
    args: null,
    obs: "Window cleared and reseeded with the probe. Run continues.",
    novelty: null,
    note: "The calibrator is deliberately NOT reset — throwing away the task adaptation on every trip would let a flapping agent reset itself into the conservative default forever.",
  },
];
