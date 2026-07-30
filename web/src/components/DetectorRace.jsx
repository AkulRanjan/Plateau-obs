import { STEP_CAP } from "../data/trace.js";
import { TRIP_TURN } from "../lib/deriveState.js";
import { runAll } from "../lib/baselines.js";
import { useLaneReveal } from "../hooks/useLaneReveal.js";
import InfoTip from "./InfoTip.jsx";

/* Computed once at module load, not asserted. See lib/baselines.js. */
const RACE = runAll();

/**
 * The lanes.
 *
 * `fire` is a computed turn number or null — nothing here is a hand-written
 * result. `note` stays short enough to read from the back of a room; the
 * source-verified detail lives in the tooltip.
 */
const LANES = [
  {
    name: "Plateau",
    note: "semantic novelty · C1 gate",
    fire: TRIP_TURN,
    kind: "hit",
    verdict:
      "Caught the plateau at turn 13, and left the healthy batch job running. Not the fastest here — see the note below.",
    tip: (
      <>
        Embeds both halves of every turn and reads two dials: action similarity
        and observation novelty. Trips on <b className="text-ink">novelty</b>;
        similarity only sets how much evidence a stagnant turn carries. The
        baseline may only learn from turns that produced new information, so a
        stuck agent cannot teach it that being stuck is normal.
      </>
    ),
  },
  {
    name: "Similarity-only",
    note: "drop the C1 gate — one dial",
    fire: RACE.similarityOnly2,
    kind: "false",
    verdict:
      "False alarm at turn 9. Killed a healthy batch job, because near-identical actions look like a loop when you cannot see what came back.",
    tip: (
      <>
        Our own ablation, not a shipped system. Identical accumulation to
        Plateau with the novelty gate removed, so a turn counts as stagnant
        purely because its action resembles recent ones. Fires on the invoice
        batch at <b className="text-ink">sim 0.99</b> — which is what every
        action-only repetition detector does on healthy repetitive work.
      </>
    ),
  },
  {
    name: "Exact-args debounce",
    note: "exact (tool, args) key",
    fire: RACE.exactArgs,
    kind: "miss",
    verdict:
      "Never tripped. The loop reworded its queries, so the argument keys never repeated.",
    tip: (
      <>
        AWS <span className="text-ink">sample-why-agents-fail</span>,
        <span className="text-ink"> DebounceHook</span>. Blocks a repeat of{" "}
        <span className="text-ink">(tool_name, json.dumps(input))</span> inside a
        sliding window. Reads the action only, by exact equality — a reworded
        argument is a different key.
      </>
    ),
  },
  {
    name: "Exact-match",
    note: "OpenHands · both halves, exactly",
    fire: RACE.exactMatch,
    kind: "miss",
    verdict:
      "Never tripped. It compares more than the others do, but only character for character.",
    tip: (
      <>
        OpenHands <span className="text-ink">StuckDetector</span>. Scenario 1
        requires <span className="text-ink">actions_equal</span> AND{" "}
        <span className="text-ink">observations_equal</span> — so it does read{" "}
        <b className="text-ink">both halves</b>, which corrects a claim in our
        own earlier pitch deck. But equality is exact (
        <span className="text-ink">_event_eq</span>), so paraphrase defeats it.
      </>
    ),
  },
  {
    name: "Lexical overlap",
    note: "agent-loop-detector · observation only",
    fire: RACE.lexical,
    kind: "hit",
    verdict:
      "Caught it at turn 12 — one turn before Plateau. This loop repeats one byte-identical string, which is exactly what token overlap is built for.",
    tip: (
      <>
        <span className="text-ink">agent-loop-detector</span>. Its entry point is{" "}
        <span className="text-ink">check(output)</span> — a single argument — so
        it reads the <b className="text-ink">observation only</b> and never sees
        the action, the mirror image of an action-only detector. Jaccard /
        TF-cosine / Levenshtein at published defaults (0.85, window 10, 3
        consecutive). Lexical, not exact-string — and not semantic.
      </>
    ),
  },
  {
    name: "Step cap",
    note: "LangGraph · counts steps, reads neither half",
    fire: RACE.stepCap,
    kind: "miss",
    verdict: `Never tripped in range. Fires blind at a fixed ${STEP_CAP} regardless of what the agent is doing.`,
    tip: (
      <>
        LangGraph <span className="text-ink">recursion_limit</span>. A superstep
        counter: <span className="text-ink">stop = step + limit + 1</span>, trip
        on <span className="text-ink">step &gt; stop</span> (
        <span className="text-ink">_loop.py:607</span>). Compares{" "}
        <b className="text-ink">no content at all</b> — not the action, not the
        observation. Note the documented default is 25, but the source at commit{" "}
        <span className="text-ink">41341457</span> ships{" "}
        <span className="text-ink">10007</span>, at which it never fires on any
        realistic run.
      </>
    ),
  },
];

const PIN = {
  hit: "var(--color-cyan)",
  false: "var(--color-amber)",
  miss: "var(--color-faint)",
};

export default function DetectorRace({ turn }) {
  useLaneReveal(LANES.length);
  const current = turn + 1;

  return (
    <div className="flex flex-col gap-2.5">
      {LANES.map((lane) => {
        const fired = lane.fire !== null && current >= lane.fire;
        const accent = PIN[lane.kind];

        return (
          <div
            key={lane.name}
            data-plateau-lane
            className="grid gap-x-4 gap-y-1.5 rounded-xl border bg-surface px-3.5 py-3 transition-colors duration-300 md:grid-cols-[190px_1fr]"
            style={{
              borderColor: fired ? accent : "var(--color-line-soft)",
              boxShadow:
                fired && lane.kind === "hit"
                  ? `0 0 24px -12px ${accent}`
                  : undefined,
            }}
          >
            <div className="flex flex-col gap-0.5 self-center md:row-span-2">
              <span className="flex items-center gap-1.5 text-sm font-semibold">
                {lane.name}
                <InfoTip label={lane.name}>{lane.tip}</InfoTip>
              </span>
              <span className="font-mono text-[10px] text-faint">{lane.note}</span>
            </div>

            <div className="relative h-5 md:col-start-2">
              <div className="absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 rounded-sm bg-line" />
              <div
                className="absolute left-0 top-1/2 h-0.5 -translate-y-1/2 rounded-sm bg-faint transition-[width] duration-400"
                style={{ width: `${Math.min(100, (current / STEP_CAP) * 100)}%` }}
              />
              {lane.fire !== null ? (
                <div
                  // Intentionally invisible until this detector's fire turn is
                  // reached. `data-plateau-gated` tells scripts/visual.mjs that
                  // opacity 0 is the designed state here, not an animation that
                  // failed to finish — otherwise every mid-play run reports these
                  // six pins as bugs and the check stops being worth reading.
                  data-plateau-gated
                  className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 text-center transition-opacity duration-400"
                  style={{
                    left: `${((lane.fire - 1) / (STEP_CAP - 1)) * 100}%`,
                    opacity: fired ? 1 : 0,
                  }}
                >
                  <span
                    className="mx-auto block h-3 w-3 rounded-full"
                    style={{ background: accent, boxShadow: `0 0 12px ${accent}` }}
                  />
                  <span
                    className="absolute left-1/2 top-[15px] -translate-x-1/2 whitespace-nowrap font-mono text-[9px]"
                    style={{ color: accent }}
                  >
                    turn {lane.fire}
                  </span>
                </div>
              ) : (
                <span className="absolute right-0 top-1/2 -translate-y-1/2 font-mono text-[10px] tracking-[0.05em] text-faint">
                  never fires
                </span>
              )}
            </div>

            <div
              className={`text-xs md:col-start-2 ${
                lane.kind === "hit" ? "text-ink" : "text-muted"
              }`}
            >
              {fired || lane.fire === null ? (
                lane.verdict
              ) : (
                <span className="text-faint">watching…</span>
              )}
            </div>
          </div>
        );
      })}

      <div className="mt-1 flex flex-wrap items-center gap-3 border-t border-line-soft pt-3">
        <span
          className="rounded-md border px-2.5 py-1 font-mono text-[11px] tracking-[0.03em]"
          style={{
            borderColor: "var(--color-amber)",
            color: "var(--color-amber)",
            background: "color-mix(in srgb, var(--color-amber) 12%, transparent)",
          }}
        >
          our worst number, stated plainly
        </span>
        <span className="text-xs text-muted">
          on this trace a 2019-era token-overlap baseline beats us by a turn
        </span>
      </div>

      <p className="mt-1 font-mono text-[10px] leading-relaxed text-faint">
        This loop repeats one byte-identical non-answer, which is the case exact
        and lexical matching are built for — so lexical wins here, and we say so
        rather than picking a trace that hides it. Plateau&rsquo;s claimed
        advantage is on <span className="text-muted">paraphrased</span> stalls,
        and the measured panel below shows that class is currently an{" "}
        <span className="text-muted">open miss</span>. What this trace does show
        is the counter-demo: the action-only ablation kills the healthy batch at
        turn 9 and Plateau does not.
      </p>

      <p className="mt-1.5 font-mono text-[10px] leading-relaxed text-faint">
        Every fire turn above is computed by running these mechanisms over this
        trace (<span className="text-muted">src/lib/baselines.js</span>), not
        asserted. Hover any detector for what it actually reads, verified against
        upstream source.
      </p>
    </div>
  );
}
