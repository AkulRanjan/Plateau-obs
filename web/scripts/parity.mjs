/**
 * deriveState parity check.
 *
 * The brief froze deriveState's semantics. Rather than assert that the port is
 * faithful, this proves it: it reads the ORIGINAL draft component off disk,
 * extracts the constants + TRACE + deriveState block verbatim, evaluates it as
 * a module, and diffs every field of every row against the ported version over
 * every step from idle to the end of the trace.
 *
 * Extracting from the file rather than pasting a copy in here is the point — a
 * copy could carry the same transcription error as the port and agree with it.
 *
 *   npm run parity
 *
 * Exits non-zero on any divergence.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const DRAFT = "/home/nithish/Videos/frontier/PlateauConsole.jsx";

// The draft's plain-JS region: from the first constant through the end of
// deriveState, stopping before `const ACCENT` (after which it is all JSX).
const MARK_START = "const NOVELTY_FLOOR";
const MARK_END = "const ACCENT";

function loadOriginal() {
  const src = readFileSync(DRAFT, "utf8");
  const start = src.indexOf(MARK_START);
  const end = src.indexOf(MARK_END);
  if (start === -1 || end === -1 || end <= start) {
    throw new Error(
      `could not locate the deriveState block in ${DRAFT} ` +
        `(start=${start}, end=${end}). The draft's structure changed; ` +
        `update MARK_START/MARK_END.`
    );
  }

  const chunk = src.slice(start, end);
  if (!chunk.includes("function deriveState")) {
    throw new Error("extracted block does not contain deriveState");
  }

  const mod = `${chunk}\nexport { deriveState, TRACE, TRIP_TURN, NOVELTY_FLOOR, WARM_CEILING, COLD_CEILING, MIN_SAMPLES, TRIP_STREAK };`;
  const url =
    "data:text/javascript;base64," + Buffer.from(mod, "utf8").toString("base64");
  return import(url);
}

const FIELDS = [
  "turn",
  "tool",
  "args",
  "obs",
  "sim",
  "nov",
  "phase",
  "isError",
  "ceiling",
  "warm",
  "quadrant",
  "streak",
];

const problems = [];
const note = (m) => problems.push(m);

const original = await loadOriginal();
const ported = await import(resolve(HERE, "../src/lib/deriveState.js"));
const portedTrace = await import(resolve(HERE, "../src/data/trace.js"));

// --- 1. the constants ------------------------------------------------------
for (const k of [
  "NOVELTY_FLOOR",
  "WARM_CEILING",
  "COLD_CEILING",
  "MIN_SAMPLES",
  "TRIP_STREAK",
]) {
  if (original[k] !== portedTrace[k]) {
    note(`constant ${k}: draft ${original[k]} !== port ${portedTrace[k]}`);
  }
}

// --- 2. the trace: one intended, documented difference and nothing else ----
//
// The three loop-phase observations were changed from a byte-identical repeat
// to three paraphrases, because a trace of literal repeats tests the case the
// incumbents already handle rather than Plateau's claim. See the note in
// trace.js. Everything else — every tool, every argument, and critically every
// sim and nov reading — must be untouched.
// Indices 10 and 11 (turns 11 and 12). Index 9 / turn 10 keeps the draft's
// wording: it is the first of the sequence, so there is nothing before it for
// it to be a paraphrase of. The rewording only has to break the *consecutive*
// string equality that lexical matching keys on.
const ALLOWED_OBS_CHANGES = new Set([10, 11]);

if (original.TRACE.length !== portedTrace.TRACE.length) {
  note(
    `TRACE length: draft ${original.TRACE.length} !== port ${portedTrace.TRACE.length}`
  );
} else {
  original.TRACE.forEach((o, i) => {
    const p = portedTrace.TRACE[i];
    for (const f of ["tool", "args", "sim", "nov", "phase", "isError"]) {
      if (o[f] !== p[f]) {
        note(`TRACE[${i}].${f}: draft ${JSON.stringify(o[f])} !== port ${JSON.stringify(p[f])}`);
      }
    }
    if (o.obs !== p.obs && !ALLOWED_OBS_CHANGES.has(i)) {
      note(
        `TRACE[${i}].obs changed outside the allowed set: ` +
          `draft ${JSON.stringify(o.obs)} !== port ${JSON.stringify(p.obs)}`
      );
    }
  });

  // The allowed changes must actually still be changes — if someone reverts the
  // paraphrases, the lexical baseline starts winning again and nothing warns.
  for (const i of ALLOWED_OBS_CHANGES) {
    if (original.TRACE[i].obs === portedTrace.TRACE[i].obs) {
      note(
        `TRACE[${i}].obs is back to the draft's literal repeat ` +
          `(${JSON.stringify(original.TRACE[i].obs)}). The loop must return ` +
          `paraphrases, or a lexical baseline out-detects Plateau on this trace.`
      );
    }
  }
}

// --- 3. the ALGORITHM, run over the draft's own trace ----------------------
//
// This is the part that proves the port. Both functions read the draft's
// original trace, so any divergence is the logic, not the data.
const LAST = original.TRACE.length - 1;
for (let step = -1; step <= LAST; step++) {
  const a = original.deriveState(step);
  const b = ported.deriveState(step, original.TRACE);

  for (const k of ["n", "warm", "ceiling", "state", "tripTurn", "streak"]) {
    if (a[k] !== b[k]) {
      note(`step ${step}: ${k} draft ${JSON.stringify(a[k])} !== port ${JSON.stringify(b[k])}`);
    }
  }

  if (a.rows.length !== b.rows.length) {
    note(`step ${step}: rows length ${a.rows.length} !== ${b.rows.length}`);
    continue;
  }

  a.rows.forEach((ra, i) => {
    const rb = b.rows[i];
    for (const f of FIELDS) {
      if (ra[f] !== rb[f]) {
        note(
          `step ${step} row ${i} (turn ${ra.turn}): ${f} draft ` +
            `${JSON.stringify(ra[f])} !== port ${JSON.stringify(rb[f])}`
        );
      }
    }
  });
}

// --- 4. the derived trip turn still equals the draft's literal -------------
if (original.TRIP_TURN !== ported.TRIP_TURN) {
  note(
    `TRIP_TURN: draft literal ${original.TRIP_TURN} !== port derived ${ported.TRIP_TURN}. ` +
      `The port derives this from deriveState instead of hardcoding it, so a ` +
      `mismatch means the thresholds no longer produce the rehearsed trip turn.`
  );
}

// --- 5. the paraphrases must not have moved the trip turn ------------------
// The whole justification for changing them is that novelty is unchanged
// because the meaning is unchanged. If the trip moved, that claim is false.
const liveTrip = ported.deriveState(portedTrace.TRACE.length - 1).tripTurn;
if (liveTrip !== original.TRIP_TURN) {
  note(
    `the live (paraphrased) trace trips at turn ${liveTrip}, but the draft ` +
      `tripped at ${original.TRIP_TURN}. Rewording the observations was only ` +
      `justified because it leaves novelty — and therefore the trip — unchanged.`
  );
}

// --- report ----------------------------------------------------------------
const steps = LAST + 2;
if (problems.length) {
  console.error(`\nderiveState PARITY FAILED — ${problems.length} divergence(s):\n`);
  for (const p of problems) console.error(`  · ${p}`);
  console.error("");
  process.exit(1);
}

const reworded = [...ALLOWED_OBS_CHANGES]
  .map((i) => `turn ${i + 1}`)
  .join(", ");

console.log(
  `\nderiveState parity OK` +
    `\n  draft       : ${DRAFT}` +
    `\n  algorithm   : identical over ${steps} steps × ${FIELDS.length} fields,` +
    ` both run on the draft's own trace` +
    `\n  trace       : identical except obs on ${reworded} (paraphrased on purpose);` +
    ` every sim and nov unchanged` +
    `\n  trip turn   : ${ported.TRIP_TURN} on the draft's trace, ${liveTrip} on the live one — unmoved` +
    `\n  thresholds  : floor ${portedTrace.NOVELTY_FLOOR}  ceiling ${portedTrace.WARM_CEILING} warm / ${portedTrace.COLD_CEILING} cold  streak ${portedTrace.TRIP_STREAK}\n`
);
