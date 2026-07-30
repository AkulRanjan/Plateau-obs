import {
  COLD_CEILING,
  MIN_SAMPLES,
  STEP_CAP,
  TRACE,
  TRIP_STREAK,
  WARM_CEILING,
} from "../data/trace.js";

/* ============================================================================
 * The competing detectors, COMPUTED on this trace rather than asserted.
 *
 * The draft carried each lane's fire turn as a hand-written literal. These are
 * ports of the real mechanisms, mirroring the Python ports in eval/baselines/
 * (which were themselves written against upstream source — see
 * THIRD_PARTY_NOTICES.md). Running them means the race table reports what the
 * mechanisms do on this trace instead of what we remember them doing.
 *
 * Each returns a 1-indexed turn number, or null for "never fired".
 * ========================================================================= */

const turnOf = (index) => index + 1;

/**
 * Exact-args debounce — AWS `sample-why-agents-fail` DebounceHook.
 *
 * Blocks a repeat of `(tool_name, json.dumps(input))` within a sliding window.
 * Rewording the arguments defeats it, which is the point of including it.
 */
export function exactArgs(turns, window = 3) {
  const seen = [];
  for (let i = 0; i < turns.length; i++) {
    const key = `${turns[i].tool}|${turns[i].args}`;
    if (seen.includes(key)) return turnOf(i);
    seen.push(key);
    if (seen.length > window) seen.shift();
  }
  return null;
}

/**
 * Exact match — OpenHands `StuckDetector`, scenario 1.
 *
 * Requires `actions_equal` AND `observations_equal`. It reads both halves,
 * which is more than most incumbents do, but only by exact equality.
 */
export function exactMatch(turns, repeats = 3) {
  let run = 1;
  for (let i = 1; i < turns.length; i++) {
    const a = turns[i];
    const b = turns[i - 1];
    const same =
      a.tool === b.tool && a.args === b.args && a.obs === b.obs;
    run = same ? run + 1 : 1;
    if (run >= repeats) return turnOf(i);
  }
  return null;
}

/** Lowercase, split on non-alphanumeric. Mirrors the upstream tokenizer. */
const tokenize = (text) => text.toLowerCase().match(/\b\w+\b/g) ?? [];

function jaccard(a, b) {
  const A = new Set(tokenize(a));
  const B = new Set(tokenize(b));
  if (A.size === 0 && B.size === 0) return 1;
  if (A.size === 0 || B.size === 0) return 0;
  let inter = 0;
  for (const t of A) if (B.has(t)) inter += 1;
  return inter / (A.size + B.size - inter);
}

/**
 * Lexical — `agent-loop-detector`.
 *
 * Its entry point is `check(output)`: a single argument. It reads the
 * OBSERVATION only and never sees the action — the mirror image of an
 * action-only detector. This port preserves that.
 *
 * Published defaults, used unmodified so it is not a strawman:
 * threshold 0.85, window 10, max_consecutive 3.
 */
export function lexical(turns, threshold = 0.85, window = 10, maxConsecutive = 3) {
  const outputs = [];
  let consecutive = 0;

  for (let i = 0; i < turns.length; i++) {
    const output = turns[i].obs;
    if (outputs.length) {
      consecutive = jaccard(output, outputs[outputs.length - 1]) >= threshold
        ? consecutive + 1
        : 0;
    }
    outputs.push(output);
    if (outputs.length > window) outputs.shift();
    // Upstream counts the current output in the total.
    if (consecutive + 1 >= maxConsecutive && consecutive > 0) return turnOf(i);
  }
  return null;
}

/**
 * Step cap — LangGraph `recursion_limit`.
 *
 * Counts supersteps and compares no content whatsoever. Reproduces upstream's
 * arithmetic including its off-by-two: with `stop = step + limit + 1` and a trip
 * on `step > stop`, the trip lands on step `limit + 2`.
 */
export function stepCap(turns, limit = STEP_CAP) {
  const stop = limit + 1;
  for (let i = 0; i < turns.length; i++) {
    if (i > stop) return turnOf(i);
  }
  return null;
}

/**
 * Our own ablation: Plateau with the C1 novelty gate removed.
 *
 * Identical accumulation to the real detector, except novelty is ignored
 * entirely — a turn counts as stagnant purely because its action resembles
 * recent ones. This is what every action-only repetition detector does, and its
 * purpose is to FAIL: it should trip on the healthy batch that full Plateau
 * leaves alone.
 *
 * `streak` is exposed because the honest streak length for a false trip on this
 * trace is 2, not 3 — see the note in DetectorRace.
 */
export function similarityOnly(turns, streakNeeded = TRIP_STREAK) {
  let n = 0;
  let streak = 0;
  for (let i = 0; i < turns.length; i++) {
    // No novelty gate: every turn teaches the baseline.
    n += 1;
    const ceiling = n >= MIN_SAMPLES ? WARM_CEILING : COLD_CEILING;
    streak = turns[i].sim >= ceiling ? streak + 1 : 0;
    if (streak >= streakNeeded) return turnOf(i);
  }
  return null;
}

/** Everything, computed on the default trace. */
export function runAll(turns = TRACE) {
  return {
    exactArgs: exactArgs(turns),
    exactMatch: exactMatch(turns),
    lexical: lexical(turns),
    stepCap: stepCap(turns),
    similarityOnly3: similarityOnly(turns, 3),
    similarityOnly2: similarityOnly(turns, 2),
  };
}
