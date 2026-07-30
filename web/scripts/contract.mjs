/**
 * Demo contract check.
 *
 * The brief has one non-negotiable sequence: auto-play on mount, halt exactly
 * at the trip, tokens-saved springs up. The halt is the product, so it gets an
 * automated guard rather than a hand check that only happens when someone
 * remembers.
 *
 * This walks the trace the way usePlayback does and asserts the properties App
 * relies on, at the logic level, with no DOM involved.
 *
 *   npm run contract
 */
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const { deriveState, TRIP_TURN } = await import(
  resolve(HERE, "../src/lib/deriveState.js")
);
const { TRACE, STEP_CAP, TOKENS_PER_TURN, NOVELTY_FLOOR } = await import(
  resolve(HERE, "../src/data/trace.js")
);

const problems = [];
const check = (ok, msg) => {
  if (!ok) problems.push(msg);
};

// --- walk the run exactly as the clock does --------------------------------
let firstOpenStep = null;
const states = [];
for (let step = 0; step < TRACE.length; step++) {
  const s = deriveState(step);
  states.push(s.state);
  if (s.state === "open" && firstOpenStep === null) firstOpenStep = step;
}

// 1. It must trip at all.
check(firstOpenStep !== null, "the run never reaches state 'open' — nothing halts the demo");

// 2. It must trip on the rehearsed turn.
check(
  firstOpenStep !== null && firstOpenStep + 1 === TRIP_TURN,
  `first 'open' lands on turn ${firstOpenStep + 1}, but TRIP_TURN is ${TRIP_TURN}`
);

// 3. Once open, it must stay open. A state that recovers by itself would let
//    the clock keep running straight through the halt.
if (firstOpenStep !== null) {
  const after = states.slice(firstOpenStep);
  check(
    after.every((s) => s === "open"),
    `state leaves 'open' after the trip: ${after.join(" -> ")}`
  );
}

// 4. The halt must leave turns on the table, or "tokens saved" is zero and the
//    payoff beat has nothing to count.
const turnsSpared = STEP_CAP - TRIP_TURN;
check(
  turnsSpared > 0,
  `trip at ${TRIP_TURN} spares no turns against the step-cap of ${STEP_CAP}`
);

// 5. The healthy batch phase must never be classified as stagnant. This is the
//    counter-demo: similarity alone would condemn those turns (sim 0.99).
const batchRows = deriveState(TRACE.length - 1).rows.filter(
  (r) => r.phase === "batch"
);
check(batchRows.length > 0, "no batch-phase turns found in the trace");
const misread = batchRows.filter(
  (r) => r.quadrant === "stuck" || r.quadrant === "thrash"
);
check(
  misread.length === 0,
  `batch turns misread as stagnant: ${misread.map((r) => `turn ${r.turn} (${r.quadrant})`).join(", ")}`
);

// 6. And the batch must clear the floor on novelty, not on similarity — the
//    joint design earning its place.
const batchBelowFloor = batchRows.filter((r) => r.nov < NOVELTY_FLOOR);
check(
  batchBelowFloor.length === 0,
  `batch turns below the novelty floor: ${batchBelowFloor.map((r) => r.turn).join(", ")}`
);

// --- report ----------------------------------------------------------------
if (problems.length) {
  console.error(`\ndemo CONTRACT FAILED — ${problems.length} problem(s):\n`);
  for (const p of problems) console.error(`  · ${p}`);
  console.error("");
  process.exit(1);
}

const batchSims = batchRows.map((r) => r.sim.toFixed(2)).join(", ");
console.log(
  `\ndemo contract OK` +
    `\n  trips at        : turn ${TRIP_TURN} of ${TRACE.length}` +
    `\n  stays open      : yes, through the end of the trace` +
    `\n  turns spared    : ${turnsSpared} vs the step-cap of ${STEP_CAP}` +
    `\n  tokens saved    : ${(turnsSpared * TOKENS_PER_TURN).toLocaleString("en-US")}` +
    `\n  batch protected : ${batchRows.length} turns, sim ${batchSims} — all above the floor\n`
);
