/* ------------------------------------------------------------------ *
 * The replayed run.
 *
 * A self-contained REPLAY of one autonomous-agent run. Every number in
 * TRACE is grounded in the project's metrics.json (paraphrase action-sim
 * 0.89, batch sim 0.99, poller/true-loop novelties 0.23 -> 0.06 -> 0.0, the
 * research-profile calibrated ceiling ~0.55, novelty floor 0.15).
 *
 * SEAM FOR THE LIVE BACKEND: replace TRACE with a stream. Each turn only
 * needs { tool, args, obs, sim, nov, isError }; deriveState() computes the
 * breaker decision (novelty gate / C1) client-side here, but in production
 * the backend owns that call and this view just renders it.
 *
 * These four constants are calibrated to THIS trace and are load-bearing for
 * the demo: they are what put the trip on turn 13. They are deliberately not
 * the Python package's defaults (plateau/calibrator.py ships NOVELTY_FLOOR
 * 0.30). Do not "fix" them to match — the trip turn and every number in the
 * hero copy move if you do. scripts/parity.mjs fails loudly if they drift.
 * ------------------------------------------------------------------ */

export const NOVELTY_FLOOR = 0.15;
export const WARM_CEILING = 0.55; // research_open_ended calibrated ceiling
export const COLD_CEILING = 0.9; // conservative default during warmup
export const MIN_SAMPLES = 6; // productive turns before "warm"
export const TRIP_STREAK = 3; // consecutive sub-floor turns that trip the breaker
export const TOKENS_PER_TURN = 1850;
export const STEP_CAP = 25; // LangGraph default the run would otherwise reach

export const TASK = "Agent task — find how to refresh an expired auth token";

// phase: research | batch | loop
export const TRACE = [
  { tool: "search_docs", args: "q='auth token refresh'",            obs: "Auth tokens expire after 3600s.",                    sim: 0.00, nov: 1.00, phase: "research" },
  { tool: "search_docs", args: "q='how do I refresh a token'",      obs: "Refresh requires a client secret and rotates the token.", sim: 0.89, nov: 0.61, phase: "research" },
  { tool: "read_docs",   args: "page='oauth/refresh'",              obs: "POST /oauth/token with grant_type=refresh_token.",   sim: 0.42, nov: 0.72, phase: "research" },
  { tool: "read_config", args: "'/etc/app.yaml'",                   obs: "client_id set; client_secret missing.",              sim: 0.31, nov: 0.83, phase: "research" },
  { tool: "search_docs", args: "q='where is client secret stored'", obs: "Secrets live in the vault under app/oauth.",         sim: 0.55, nov: 0.66, phase: "research" },
  { tool: "vault_get",   args: "'app/oauth/client_secret'",         obs: "PermissionError: access denied to app/oauth.",       sim: 0.28, nov: 0.58, phase: "research", isError: true },
  { tool: "extract_text",args: "'invoice_041.pdf'",                 obs: "ACME Corp, Rs 84,200, due Aug 12",                   sim: 0.19, nov: 0.51, phase: "batch" },
  { tool: "extract_text",args: "'invoice_042.pdf'",                 obs: "Vertex Ltd, Rs 19,750, due Aug 30",                  sim: 0.99, nov: 0.44, phase: "batch" },
  { tool: "extract_text",args: "'invoice_043.pdf'",                 obs: "Nimbus LLC, Rs 51,300, due Sep 05",                  sim: 0.99, nov: 0.41, phase: "batch" },
  { tool: "search_docs", args: "q='vault access denied fix'",       obs: "No results found.",                                  sim: 0.71, nov: 0.23, phase: "loop" },
  { tool: "search_docs", args: "q='how to grant vault permission'", obs: "No results found.",                                  sim: 0.88, nov: 0.06, phase: "loop" },
  { tool: "search_docs", args: "q='oauth secret permission error'", obs: "No results found.",                                  sim: 0.90, nov: 0.00, phase: "loop" },
  { tool: "vault_get",   args: "'app/oauth/client_secret'",         obs: "PermissionError: access denied to app/oauth.",       sim: 0.85, nov: 0.00, phase: "loop", isError: true },
];

/** Similarity-only (no C1 gate) false-trips the healthy batch here. */
export const SIM_ONLY_FIRE = 8;

// ---- presentation maps ------------------------------------------------------

export const ACCENT = {
  idle: "var(--color-cyan)",
  calibrating: "var(--color-cyan)",
  closed: "var(--color-cyan)",
  watching: "var(--color-amber)",
  open: "var(--color-red)",
};

export const QUAD = {
  productive: { c: "var(--color-cyan)", label: "PRODUCTIVE" },
  batch: { c: "var(--color-violet)", label: "BATCH" },
  stuck: { c: "var(--color-red)", label: "STUCK" },
  thrash: { c: "var(--color-amber)", label: "THRASH" },
};

export const STATE_COPY = {
  idle: "STANDBY · press run",
  calibrating: "CALIBRATING · learning this agent's normal",
  closed: "CLOSED · agent is making progress",
  watching: "WATCHING · novelty falling toward the floor",
  open: "OPEN · plateau detected — run halted",
};

/** What each quadrant means, in the legend and the tooltips. */
export const QUAD_NOTE = {
  stuck: "repeats, learns nothing → trip",
  thrash: "flails, learns nothing → trip",
  batch: "same tool, new data → keep going",
  productive: "new move, new info → keep going",
};
