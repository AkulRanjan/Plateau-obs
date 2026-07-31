/**
 * Extract the measured fixture readings out of metrics.json for the UI.
 *
 *   npm run extract-metrics
 *
 * metrics.json is ~282 KB and mostly `sweep.results` (144 configs x 4
 * fixtures). Importing it whole would put all of that in the bundle for the
 * sake of a dozen numbers, so this pulls out just what the panel renders and
 * writes src/data/fixtures.json, which IS committed.
 *
 * WHAT IS DELIBERATELY NOT EXTRACTED
 * ----------------------------------
 * `sweep` and anything derived from it — recall, the usable-configuration
 * count, the threshold window. Those numbers are not valid yet: fixtures 1 and
 * 2 are two turns long and every trip threshold is at least 3, so they cannot
 * physically trip, and the sweep's "0 of 144 usable" is an artifact of that
 * rather than a result. The repo's own README says so. Shipping them in a
 * jury-facing panel would be presenting an artifact as a finding.
 *
 * What IS extracted is per-fixture measured dial readings, which are real: they
 * came out of MiniLM at a pinned revision on a recorded run.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const METRICS = resolve(HERE, "../../metrics.json");
const OUT = resolve(HERE, "../src/data/fixtures.json");

/** The package names quadrants differently from the console. Same semantics. */
const QUADRANT_ALIAS = {
  loop: "stuck",
  grind: "batch",
  explore: "productive",
  thrash: "thrash",
};

const doc = JSON.parse(readFileSync(METRICS, "utf8"));
const src = doc.detector_fixtures;

if (!src?.fixtures) {
  console.error("metrics.json has no detector_fixtures.fixtures block");
  process.exit(1);
}

const round = (n) => (typeof n === "number" ? Number(n.toFixed(4)) : n);

const fixtures = Object.entries(src.fixtures).map(([key, f]) => {
  const readings = f.readings.map((r) => ({
    action_sim: round(r.action_sim),
    obs_novelty: round(r.obs_novelty),
    quadrant: r.quadrant,
    console_quadrant: QUADRANT_ALIAS[r.quadrant] ?? r.quadrant,
    is_trip: r.is_trip,
  }));

  return {
    key,
    label: key.replace(/^\d+[a-z]?_/, "").replace(/_/g, " "),
    expect: f.expect,
    note: f.note,
    final_quadrant: f.final_quadrant,
    console_quadrant: QUADRANT_ALIAS[f.final_quadrant] ?? f.final_quadrant,
    trip_turn: f.trip_turn,
    passed: f.passed,
    preamble_turns: src.preamble_turns,
    sim_ceiling: round(f.calibrator_after_preamble?.sim_ceiling),
    readings,
  };
});

// The long-trace comparison IS extracted, including the rows that go against us.
// This block is measured on 16-61 turn traces with the real encoder, so unlike
// the fixture sweep it means something. It is also the only place the UI can
// honestly report that Plateau currently misses the paraphrase class and
// false-trips the poller.
const lt = doc.long_trace_comparison;
const longTraces = lt
  ? {
      scope_note: lt.scope_note,
      traces: lt.traces,
      detectors: Object.fromEntries(
        Object.entries(lt.detectors).map(([name, v]) => [
          name,
          {
            recall: v.recall,
            false_trip_rate: v.false_trip_rate,
            mean_turns_to_detection: v.mean_turns_to_detection,
            missed: v.missed,
            false_trips: v.false_trips,
            detection_turn_index: v.detection_turn_index,
          },
        ])
      ),
      perfect_detectors: lt.perfect_detectors ?? [],
      // The `idempotent: true` declaration is a burden the deployer carries,
      // not a capability Plateau has. Carried through so the panel can never
      // show what the declaration buys without also saying what it costs.
      idempotent_note: lt.idempotent_note ?? null,
      idempotent_tools: lt.idempotent_tools ?? null,
    }
  : null;

// The TRAIL block: 148 real annotated agent traces. This is carried through
// even though it is the least flattering number in the project, because a jury
// console showing only the hand-written traces would be showing the evaluation
// that agreed with us. contract.mjs refuses to pass if long_traces is present
// and this is not.
const tc = doc.trail_comparison;
const MODE = "tool+llm";
const trail = tc
  ? {
      dataset: tc.dataset,
      scope_note: tc.scope_note,
      default_mapping: tc.default_mapping,
      mappings: tc.mappings,
      span_mode_shown: MODE,
      corpus: tc.corpus?.[MODE] ?? null,
      // Every mapping, not just the one that reads best.
      by_mapping: Object.fromEntries(
        Object.entries(tc.results?.[MODE] ?? {}).map(([mapping, m]) => [
          mapping,
          {
            categories: m.categories,
            n_positive: m.n_positive,
            n_negative: m.n_negative,
            perfect_detectors: m.perfect_detectors,
            detectors: Object.fromEntries(
              Object.entries(m.detectors).map(([name, v]) => [name, v.all])
            ),
          },
        ])
      ),
    }
  : null;

const out = {
  _comment:
    "GENERATED by web/scripts/extract_metrics.mjs from metrics.json. Do not " +
    "hand-edit. Contains per-fixture dial readings and the LONG-TRACE " +
    "comparison, which is measured on 16-61 turn traces and is valid. The " +
    "fixture parameter SWEEP is deliberately excluded: fixtures 1 and 2 are " +
    "two turns long and cannot trip, so its recall figures are an artifact.",
  encoder: {
    model_id: src.encoder?.model_id,
    revision: src.encoder?.revision,
    dim: src.encoder?.dim,
    seed: src.encoder?.seed,
  },
  novelty_floor: src.novelty_floor,
  novelty_floor_status: src.novelty_floor_status,
  preamble_turns: src.preamble_turns,
  all_passed: src.all_passed,
  counter_demo_holds: src.counter_demo_holds,
  quadrant_alias: QUADRANT_ALIAS,
  fixtures,
  long_traces: longTraces,
  trail: trail,
};

writeFileSync(OUT, JSON.stringify(out, null, 2) + "\n", "utf8");

const bytes = Buffer.byteLength(JSON.stringify(out));
console.log(
  `\nextracted -> src/data/fixtures.json` +
    `\n  fixtures : ${fixtures.length}` +
    `\n  readings : ${fixtures.reduce((n, f) => n + f.readings.length, 0)}` +
    `\n  size     : ${(bytes / 1024).toFixed(1)} kB (from ${(
      readFileSync(METRICS).length / 1024
    ).toFixed(0)} kB metrics.json)` +
    `\n  long     : ${longTraces ? Object.keys(longTraces.detectors).length + " detectors x " + Object.keys(longTraces.traces).length + " trace classes" : "ABSENT"}` +
    `\n  encoder  : ${out.encoder.model_id} @ ${out.encoder.revision?.slice(0, 8)}\n`
);
