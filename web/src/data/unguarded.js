import { STEP_CAP, TRACE } from "./trace.js";

/* ------------------------------------------------------------------ *
 * What the run does if nobody stops it.
 *
 * The unguarded pane continues past turn 13 to the step-cap, and every turn
 * returns HTTP 200. That is the whole problem in one column: error rate zero,
 * latency normal, every dashboard green, and no progress whatsoever. The only
 * thing that eventually notices is the bill.
 *
 * THESE TURNS ARE INVENTED. They are a projection of the same loop continuing,
 * not a recording — the pane says so on screen. Their purpose is to show the
 * shape and the cost of not stopping, and every one of them is the agent asking
 * a variation of a question it has already failed to answer.
 * ------------------------------------------------------------------ */

/** Turns 14 through the step-cap. */
export const UNGUARDED_TAIL = [
  { tool: "search_docs",  args: "q='vault permission denied workaround'", obs: "No documents matched." },
  { tool: "vault_get",    args: "'app/oauth/client_secret'",             obs: "PermissionError: access denied to app/oauth." },
  { tool: "search_docs",  args: "q='oauth client secret rotation'",      obs: "Nothing relevant returned." },
  { tool: "read_docs",    args: "page='oauth/refresh'",                  obs: "POST /oauth/token with grant_type=refresh_token." },
  { tool: "vault_get",    args: "'app/oauth'",                           obs: "PermissionError: access denied to app/oauth." },
  { tool: "search_docs",  args: "q='how to read vault secret'",          obs: "No results found." },
  { tool: "read_config",  args: "'/etc/app.yaml'",                       obs: "client_id set; client_secret missing." },
  { tool: "search_docs",  args: "q='client secret missing error'",       obs: "No documents matched." },
  { tool: "vault_get",    args: "'app/oauth/client_secret'",             obs: "PermissionError: access denied to app/oauth." },
  { tool: "search_docs",  args: "q='grant vault read permission'",       obs: "Nothing matched that query." },
  { tool: "read_docs",    args: "page='vault/permissions'",              obs: "Permissions are managed by the platform team." },
  { tool: "search_docs",  args: "q='platform team vault request'",       obs: "No results found." },
];

/**
 * The full unguarded run: the real trace, then the projected tail, padded or
 * trimmed to exactly the step-cap so the pane always ends where a blind counter
 * would have stopped it.
 */
export const UNGUARDED_RUN = [
  ...TRACE.map((t) => ({ tool: t.tool, args: t.args, obs: t.obs, real: true })),
  ...UNGUARDED_TAIL.map((t) => ({ ...t, real: false })),
].slice(0, STEP_CAP);

/** Every call succeeds. That is the point. */
export const STATUS_OK = "200 OK";
