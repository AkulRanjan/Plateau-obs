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
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));

// `import()` of an absolute path is a URL, not a path. On POSIX the two happen
// to coincide; on Windows `resolve()` returns `C:\...` and the ESM loader
// rejects it as an unsupported `c:` scheme, so `npm run check` could not run on
// Windows at all. pathToFileURL is the portable spelling.
const importLocal = (rel) => import(pathToFileURL(resolve(HERE, rel)).href);

const { deriveState, TRIP_TURN } = await importLocal("../src/lib/deriveState.js");
const { TRACE, STEP_CAP, TOKENS_PER_TURN, NOVELTY_FLOOR } = await importLocal(
  "../src/data/trace.js"
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

// 7. Position must agree with colour. Every dot's quadrant, recomputed from its
//    plotted (novelty, similarity) coordinate, must match the label deriveState
//    gave that turn. A disagreement means a dot sits in a region that
//    contradicts its own colour, which breaks the chart's entire claim.
const geom = await importLocal("../src/lib/quadrantGeometry.js");
const allRows = deriveState(TRACE.length - 1).rows;
const mismatched = [];
const outOfBounds = [];

for (const r of allRows) {
  const implied = geom.quadrantAt(r.nov, r.sim, r.ceiling);
  if (implied !== r.quadrant) {
    mismatched.push(
      `turn ${r.turn}: plotted position implies '${implied}' but deriveState says '${r.quadrant}'`
    );
  }
  const x = geom.xOfNovelty(r.nov);
  const y = geom.yOfSimilarity(r.sim);
  const lo = geom.PAD;
  const hi = geom.PAD + geom.IW;
  if (x < lo || x > hi || y < lo || y > hi) {
    outOfBounds.push(
      `turn ${r.turn}: (${x.toFixed(1)}, ${y.toFixed(1)}) outside the plot box [${lo}, ${hi}]`
    );
  }
}

check(mismatched.length === 0, `quadrant/position disagreement:\n      ${mismatched.join("\n      ")}`);
check(outOfBounds.length === 0, `dots outside the plot box:\n      ${outOfBounds.join("\n      ")}`);

// 8. And the plotting itself must be invertible. Recovering (novelty,
//    similarity) back out of the plotted pixel must return the turn's real
//    readings. This is what actually catches an inverted or mis-scaled axis —
//    check 7 only proves deriveState agrees with itself.
const EPS = 1e-9;
const roundTripFailures = [];
for (const r of allRows) {
  const x = geom.xOfNovelty(r.nov);
  const y = geom.yOfSimilarity(r.sim);
  const novBack = (x - geom.PAD) / geom.IW;
  const simBack = 1 - (y - geom.PAD) / geom.IW;
  if (Math.abs(novBack - r.nov) > EPS || Math.abs(simBack - r.sim) > EPS) {
    roundTripFailures.push(
      `turn ${r.turn}: plotted (${x.toFixed(2)}, ${y.toFixed(2)}) inverts to ` +
        `nov ${novBack.toFixed(4)} / sim ${simBack.toFixed(4)}, ` +
        `but the reading is nov ${r.nov} / sim ${r.sim}`
    );
  }
}
check(
  roundTripFailures.length === 0,
  `plotted coordinates do not invert to the real readings:\n      ${roundTripFailures.join("\n      ")}`
);

// Orientation, stated as an explicit expectation rather than inferred: higher
// novelty must plot further right, higher similarity must plot higher (smaller
// y). An axis silently flipping would otherwise still round-trip.
check(
  geom.xOfNovelty(0.9) > geom.xOfNovelty(0.1),
  "novelty axis is inverted — higher novelty must plot further right"
);
check(
  geom.yOfSimilarity(0.9) < geom.yOfSimilarity(0.1),
  "similarity axis is inverted — higher similarity must plot higher (smaller y)"
);

// 9. The detector race must report computed results, and those results are the
//    demo's actual argument. Each one is asserted so a trace edit cannot
//    silently invert the story the panel tells.
const bl = await importLocal("../src/lib/baselines.js");
const race = bl.runAll(TRACE);

// The loop repeats one byte-identical non-answer, which is exactly what lexical
// Jaccard is built for — so it fires, and it fires BEFORE Plateau. That is the
// honest result and it is asserted rather than hidden, because the team measured
// that the paraphrased alternative is a class Plateau misses outright
// (metrics.json -> long_trace_comparison.paraphrase_loop_varied_wording).
check(
  race.lexical !== null && race.lexical < TRIP_TURN,
  `expected the lexical baseline to fire before Plateau on a byte-identical ` +
    `loop, got ${race.lexical} vs Plateau ${TRIP_TURN}. If this trace ever stops ` +
    `being a literal repeat the numbers must be re-measured, not re-asserted.`
);
check(
  race.exactMatch === null,
  `exact-match (OpenHands) fires at turn ${race.exactMatch}; expected never — the actions differ every turn`
);
check(
  race.exactArgs === null,
  `exact-args debounce fires at turn ${race.exactArgs}; expected never — the arguments differ every turn`
);
check(
  race.stepCap === null,
  `step-cap fires at turn ${race.stepCap}; expected never within a ${TRACE.length}-turn trace`
);

// The counter-demo: the action-only ablation must false-trip on healthy batch
// work that full Plateau leaves running.
const ablation = race.similarityOnly2;
check(ablation !== null, "the similarity-only ablation never fires — the counter-demo needs it to");
if (ablation !== null) {
  const ablationRow = allRows.find((r) => r.turn === ablation);
  check(
    ablationRow?.phase === "batch",
    `the similarity-only ablation fires at turn ${ablation} (${ablationRow?.phase} phase); ` +
      `the counter-demo requires it to false-trip during the BATCH phase`
  );
  check(
    ablation < TRIP_TURN,
    `the ablation fires at ${ablation}, not before Plateau's ${TRIP_TURN} — it must be the early false alarm`
  );
}

// 10. Recovery (claim 4) must hold, and must stay out of deriveState.
const rec = await importLocal("../src/lib/deriveRecovery.js");
const epi = await importLocal("../src/data/epilogue.js");
const route = rec.escapeVector();

check(
  epi.PROBE_NOVELTY >= NOVELTY_FLOOR,
  `probe novelty ${epi.PROBE_NOVELTY} is below the floor ${NOVELTY_FLOOR}; the probe must pass`
);
check(
  rec.COST_OF_A_FALSE_TRIP_IN_TURNS === 1,
  `a false trip costs ${rec.COST_OF_A_FALSE_TRIP_IN_TURNS} turns; the claim is one`
);
check(route !== null && route.hasRoute, "no escape vector clears the novelty floor");
check(
  route === null || route.turn > 1,
  `the escape vector points at turn ${route?.turn}. Turn 1 reads novelty 1.00 ` +
    `only because the window starts empty — pointing a stuck agent at the first ` +
    `thing it did is not a route.`
);
// The escape vector should be the best real reading, so verify nothing after
// turn 1 beats it.
const bestAfterOpening = Math.max(...allRows.filter((r) => r.turn > 1).map((r) => r.nov));
check(
  route === null || Math.abs(route.novelty - bestAfterOpening) < 1e-9,
  `escape vector novelty ${route?.novelty} is not the highest after turn 1 (${bestAfterOpening})`
);

// Structural: recovery must not reach into the frozen predicate.
const recSrc = readFileSync(
  resolve(HERE, "../src/lib/deriveRecovery.js"),
  "utf8"
);
// Comments may (and do) mention deriveState to explain the separation; what
// must not exist is a real dependency on it.
const recCode = recSrc
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/(^|[^:])\/\/.*$/gm, "$1");
check(
  !/deriveState/.test(recCode),
  "deriveRecovery.js depends on deriveState — recovery must stay a separate " +
    "reducer so the frozen trip predicate keeps its parity guarantee"
);
check(
  !/from\s+["'][^"']*deriveState/.test(recSrc),
  "deriveRecovery.js imports deriveState; the two reducers must not interleave"
);

// The recovery sequence must terminate in CLOSED, or the claim is unproven.
const finalRecovery = rec.deriveRecovery(epi.EPILOGUE.length - 1);
check(
  finalRecovery.done && finalRecovery.state === "CLOSED",
  `recovery ends in state ${finalRecovery.state}; it must reach CLOSED`
);
check(finalRecovery.probePassed, "the probe does not pass, so the breaker never closes");

// 11. The measured-fixtures panel must stay measured, and must stay honest.
const fixturesRaw = readFileSync(
  resolve(HERE, "../src/data/fixtures.json"),
  "utf8"
);
const fixturesDoc = JSON.parse(fixturesRaw);

// Not-yet-valid numbers must never reach a jury-facing panel. Fixtures 1 and 2
// are two turns long and cannot trip, so recall and the sweep built on them are
// artifacts rather than results.
// The SWEEP's recall is an artifact (two-turn fixtures cannot trip). The
// LONG-TRACE recall is measured on 16-61 turn traces and is valid, so it is
// allowed — and required, see below.
const FORBIDDEN = ["sweep", "usable_window", "n_usable_configs", "distinct_recall_values"];
const leaked = FORBIDDEN.filter((k) => fixturesRaw.includes(`"${k}"`));
check(
  leaked.length === 0,
  `fixtures.json contains not-yet-valid keys: ${leaked.join(", ")}. Recall and ` +
    `the sweep are artifacts of the two-turn fixtures and must not be shown.`
);

// And it must actually be in sync with metrics.json, or the panel is stale.
const metrics = JSON.parse(
  readFileSync(resolve(HERE, "../../metrics.json"), "utf8")
);
const srcFixtures = metrics.detector_fixtures;
// The long-trace block must be present AND must still carry the results that go
// against us. If a later edit quietly drops the paraphrase miss or Plateau's
// poller false trip, the panel stops being an honest report.
const lt = fixturesDoc.long_traces;
check(lt != null, "fixtures.json has no long_traces block — run npm run extract-metrics");
if (lt) {
  // These used to hard-code the specific ways Plateau lost: it must miss
  // paraphrase_loop_varied_wording, it must false-trip healthy_poller,
  // perfect_detectors must be empty. Those were true when they were written and
  // are no longer, so pinning them would now force the panel to display a
  // *stale* failure — which is its own kind of dishonesty, and would create
  // pressure to delete the check rather than re-measure.
  //
  // What replaces them is stricter, not looser: the panel must be a faithful
  // projection of metrics.json, field for field. A miss can only disappear from
  // the UI by disappearing from a measurement first.
  const src = metrics.long_trace_comparison;
  check(src != null, "metrics.json has no long_trace_comparison block");
  const SYNCED = ["recall", "false_trip_rate", "mean_turns_to_detection"];
  for (const [name, shown] of Object.entries(lt.detectors ?? {})) {
    const measured = src?.detectors?.[name];
    check(measured != null, `fixtures.json shows detector ${name}, metrics.json has no such row`);
    if (!measured) continue;
    for (const field of SYNCED) {
      check(
        shown[field] === measured[field],
        `${name}.${field} is ${shown[field]} in the UI but ${measured[field]} in ` +
          `metrics.json — run npm run extract-metrics`
      );
    }
    for (const field of ["missed", "false_trips"]) {
      check(
        JSON.stringify(shown[field] ?? []) === JSON.stringify(measured[field] ?? []),
        `${name}.${field} differs between fixtures.json and metrics.json — a miss ` +
          `may only leave the panel by leaving the measurement`
      );
    }
  }
  check(
    JSON.stringify(lt.perfect_detectors ?? []) ===
      JSON.stringify(src?.perfect_detectors ?? []),
    "perfect_detectors differs from metrics.json — run npm run extract-metrics"
  );

  // The durable honesty invariant, which survives the numbers moving: whatever
  // the `idempotent: true` declaration buys, the panel must never show only the
  // improved row. `plateau` is Plateau without the declaration and is the
  // number a deployer gets for free; `plateau_idempotent` is what they get
  // after doing work. Showing the second without the first would advertise a
  // capability as though it were a default.
  if (lt.detectors?.plateau_idempotent) {
    check(
      lt.detectors?.plateau != null,
      "the panel shows plateau_idempotent without the undeclared plateau row; " +
        "the declaration's cost must be as visible as its benefit"
    );
    check(
      lt.idempotent_note != null,
      "plateau_idempotent is shown with no idempotent_note explaining that the " +
        "declaration is made by the tool author, not detected"
    );
  }

  // The synthetic long traces are ones we wrote, so they can only agree with
  // what we already believed. If they are on screen, the real ones must be too:
  // on TRAIL nothing reaches recall 1.00 with zero false trips and Plateau
  // false-trips over half the healthy traces, and a jury console that showed
  // only the table above would be showing the evaluation that flatters us.
  const trail = fixturesDoc.trail;
  check(
    trail != null,
    "fixtures.json shows the hand-written long traces but carries no TRAIL " +
      "block. Run scripts/trail_comparison.py then npm run extract-metrics — " +
      "the synthetic table must never be the only detection evidence on screen."
  );
  if (trail) {
    const srcTrail = metrics.trail_comparison;
    check(srcTrail != null, "fixtures.json has a TRAIL block, metrics.json does not");
    for (const mapping of Object.keys(srcTrail?.mappings ?? {})) {
      check(
        trail.by_mapping?.[mapping] != null,
        `TRAIL mapping '${mapping}' is measured but not carried to the UI; all ` +
          `three are reported so the ground-truth choice stays visible`
      );
    }
    const shown = trail.by_mapping?.[trail.default_mapping];
    const measured =
      srcTrail?.results?.[trail.span_mode_shown]?.[trail.default_mapping];
    check(
      JSON.stringify(shown?.perfect_detectors ?? null) ===
        JSON.stringify(measured?.perfect_detectors ?? null),
      "TRAIL perfect_detectors differs from metrics.json — run extract-metrics"
    );
    for (const [name, row] of Object.entries(shown?.detectors ?? {})) {
      const src = measured?.detectors?.[name]?.all;
      check(
        src != null && row.recall === src.recall &&
          row.false_trip_rate === src.false_trip_rate,
        `TRAIL ${name} is ${row.recall}/${row.false_trip_rate} in the UI but ` +
          `${src?.recall}/${src?.false_trip_rate} in metrics.json`
      );
    }
    // The count of excluded traces is the benchmark's biggest caveat. It has to
    // travel with the numbers, or the sample looks larger than it is.
    check(
      typeof trail.corpus?.n_excluded_too_short === "number",
      "the TRAIL block carries no excluded-trace count; most traces are too " +
        "short to evaluate and the panel must be able to say so"
    );
  }

  // Plateau is not the fastest detector on byte-identical stalls and should not
  // be presented as though it were. Whichever detector has the lowest
  // turns-to-detection, its row has to be in the panel.
  const ttd = Object.entries(lt.detectors ?? {})
    .filter(([, v]) => typeof v.mean_turns_to_detection === "number")
    .sort((a, b) => a[1].mean_turns_to_detection - b[1].mean_turns_to_detection);
  check(
    ttd.length > 0,
    "no detector in the panel reports turns-to-detection, so the latency cost " +
      "of semantic comparison is invisible"
  );
}

check(
  fixturesDoc.encoder?.revision === srcFixtures?.encoder?.revision,
  `fixtures.json encoder revision ${fixturesDoc.encoder?.revision} != ` +
    `metrics.json ${srcFixtures?.encoder?.revision} — run npm run extract-metrics`
);
check(
  fixturesDoc.fixtures?.length === Object.keys(srcFixtures?.fixtures ?? {}).length,
  `fixtures.json has ${fixturesDoc.fixtures?.length} fixtures, metrics.json has ` +
    `${Object.keys(srcFixtures?.fixtures ?? {}).length} — run npm run extract-metrics`
);
for (const f of fixturesDoc.fixtures ?? []) {
  const orig = srcFixtures.fixtures[f.key];
  check(
    orig && orig.trip_turn === f.trip_turn,
    `fixtures.json ${f.key} trip_turn ${f.trip_turn} != metrics.json ${orig?.trip_turn}`
  );
}

// 12. Split-screen: the unguarded pane must run exactly to the step-cap, its
//     first turns must be the real trace, and — importantly — the cost gap it
//     shows must be the SAME number the hero reports as tokens saved. Two
//     panels quoting different savings would be the most damaging kind of
//     inconsistency on a projector.
const ung = await importLocal("../src/data/unguarded.js");

check(
  ung.UNGUARDED_RUN.length === STEP_CAP,
  `the unguarded run is ${ung.UNGUARDED_RUN.length} turns; it must reach exactly the step-cap (${STEP_CAP})`
);

const realPrefix = ung.UNGUARDED_RUN.slice(0, TRACE.length);
const prefixMatches = realPrefix.every(
  (t, i) => t.tool === TRACE[i].tool && t.args === TRACE[i].args && t.real === true
);
check(
  prefixMatches,
  "the unguarded pane's first turns are not the recorded trace — both panes must " +
    "start from the same run or the comparison is not the same trace"
);
check(
  ung.UNGUARDED_RUN.slice(TRACE.length).every((t) => t.real === false),
  "projected turns past the trace are not flagged real:false — the pane labels " +
    "them as a projection, so the data must say so too"
);

const splitSaving = (STEP_CAP - TRIP_TURN) * TOKENS_PER_TURN;
const heroSaving = turnsSpared * TOKENS_PER_TURN;
check(
  splitSaving === heroSaving,
  `split-screen shows ${splitSaving} tokens saved but the hero shows ${heroSaving}; ` +
    `the two panels must quote the same number`
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
    `\n  batch protected : ${batchRows.length} turns, sim ${batchSims} — all above the floor` +
    `\n  dot integrity   : ${allRows.length} turns, position agrees with quadrant, all in bounds` +
    `\n  race (computed) : Plateau ${TRIP_TURN} · ablation ${ablation} (batch, false trip) · ` +
    `lexical ${race.lexical} (before us) · exact-match/exact-args/step-cap never` +
    `\n  recovery        : escape -> turn ${route.turn} (nov ${route.novelty}), probe ${epi.PROBE_NOVELTY} passes, ` +
    `ends CLOSED, costs ${rec.COST_OF_A_FALSE_TRIP_IN_TURNS} turn` +
    `\n  measured panel  : ${fixturesDoc.fixtures.length} fixtures in sync with metrics.json, ` +
    `long-trace block present, misses and false trips intact` +
    `\n  split screen    : unguarded runs 1..${STEP_CAP}, guarded freezes at ${TRIP_TURN}, ` +
    `both panels quote ${splitSaving.toLocaleString("en-US")} tokens\n`
);
