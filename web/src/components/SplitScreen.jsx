import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useSpring } from "framer-motion";
import { CircleCheck, OctagonX } from "lucide-react";
import { STEP_CAP, TOKENS_PER_TURN } from "../data/trace.js";
import { STATUS_OK, UNGUARDED_RUN } from "../data/unguarded.js";
import { TRIP_TURN } from "../lib/deriveState.js";
import { PANEL_SPRING } from "../lib/motionTokens.js";
import { usePlayback } from "../hooks/usePlayback.js";
import GlassPanel, { PanelHead } from "./GlassPanel.jsx";
import Controls from "./Controls.jsx";

/**
 * Same trace, two runs, one clock.
 *
 * Both panes read `step` from a single usePlayback instance, so they cannot
 * drift — the entire point is that they are on the same turn at the same
 * instant. The halt is a property of the RIGHT pane, not of the clock: the clock
 * runs on to the step-cap so the left pane can keep spending, while the right
 * pane simply stops accepting turns after its trip.
 *
 * This is the only place the clock does not stop at the trip, and it is why the
 * console and the split-screen are separate modes with one clock alive at a
 * time rather than one clock shared across both.
 */
export default function SplitScreen() {
  const playback = usePlayback({ length: UNGUARDED_RUN.length });
  const { step } = playback;
  const shown = step + 1;

  const guardedTurns = Math.min(shown, TRIP_TURN);
  const tripped = shown >= TRIP_TURN;

  const unguardedCost = shown * TOKENS_PER_TURN;
  const guardedCost = guardedTurns * TOKENS_PER_TURN;

  return (
    <GlassPanel className="mt-4">
      <PanelHead
        label="same trace, two runs"
        sub="one clock drives both panes — every line on the left is a success"
        right={
          <span className="font-mono text-[10px] text-faint">
            projected to the step-cap ({STEP_CAP})
          </span>
        }
      />

      <Controls
        playing={playback.playing}
        atEnd={playback.atEnd}
        fast={playback.fast}
        tripped={false}
        turn={step}
        total={UNGUARDED_RUN.length}
        onRun={playback.run}
        onPause={playback.pause}
        onStep={playback.stepOne}
        onReset={playback.reset}
        onToggleFast={playback.toggleFast}
      />

      <div className="grid gap-3 lg:grid-cols-2">
        <Pane
          title="UNGUARDED"
          tone="var(--color-red)"
          cost={unguardedCost}
          costLabel={
            shown >= UNGUARDED_RUN.length ? "stopped at the cap" : "still climbing"
          }
          footer={
            shown >= UNGUARDED_RUN.length
              ? `Stopped only because the step-cap (${STEP_CAP}) was reached. Nothing was learned after turn ${TRIP_TURN}.`
              : "Every call returns 200 OK. No dashboard has anything to alarm on."
          }
        >
          <AnimatePresence initial={false}>
            {UNGUARDED_RUN.slice(0, shown).map((t, i) => (
              <Line
                key={i}
                turn={i + 1}
                tool={t.tool}
                args={t.args}
                right={STATUS_OK}
                rightTone="var(--color-cyan)"
                dim={!t.real}
              />
            ))}
          </AnimatePresence>
        </Pane>

        <Pane
          title="WITH PLATEAU"
          tone="var(--color-cyan)"
          cost={guardedCost}
          costLabel={tripped ? "frozen" : "climbing"}
          frozen={tripped}
          banner={
            tripped ? (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={PANEL_SPRING}
                className="mt-2 rounded-lg border px-2.5 py-2 font-mono text-[10.5px] leading-relaxed"
                style={{
                  borderColor: "var(--color-red)",
                  color: "var(--color-red)",
                  background:
                    "color-mix(in srgb, var(--color-red) 8%, transparent)",
                }}
              >
                <span className="flex items-center gap-1.5 font-semibold">
                  <OctagonX size={12} aria-hidden="true" /> OPEN · plateau detected
                </span>
                <span className="mt-1 block text-muted">
                  Reason and escape vector returned to the agent. No further turns
                  execute, and no further embedding is computed.
                </span>
              </motion.div>
            ) : null
          }
          footer={
            tripped
              ? `Halted at turn ${TRIP_TURN}. ${
                  STEP_CAP - TRIP_TURN
                } turns and ${(
                  (STEP_CAP - TRIP_TURN) * TOKENS_PER_TURN
                ).toLocaleString("en-US")} tokens never spent.`
              : "Watching both halves of every turn."
          }
        >
          <AnimatePresence initial={false}>
            {UNGUARDED_RUN.slice(0, guardedTurns).map((t, i) => (
              <Line
                key={i}
                turn={i + 1}
                tool={t.tool}
                args={t.args}
                right={STATUS_OK}
                rightTone="var(--color-cyan)"
              />
            ))}
          </AnimatePresence>

        </Pane>
      </div>

      <p className="mt-3 font-mono text-[10px] leading-relaxed text-faint">
        Turns 1–{TRIP_TURN} are the recorded trace. Turns {TRIP_TURN + 1}–
        {STEP_CAP} are a{" "}
        <span className="text-muted">projection</span> of the same loop
        continuing, shown dimmed — they are what the unguarded run would cost,
        not a measurement.
      </p>
    </GlassPanel>
  );
}

function Pane({ title, tone, cost, costLabel, frozen, footer, banner, children }) {
  const scroller = useRef(null);

  // Follow the newest line, like the telemetry feed. Without this the pane sits
  // at turn 1 while the interesting part — the dimmed projection past the trip —
  // scrolls out of sight below.
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  });

  return (
    <div
      className="flex flex-col rounded-xl border bg-surface p-3"
      style={{ borderColor: `color-mix(in srgb, ${tone} 35%, transparent)` }}
    >
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <span
          className="font-mono text-[11px] font-semibold tracking-[0.14em]"
          style={{ color: tone }}
        >
          {title}
        </span>
        <span className="flex items-baseline gap-1.5 font-mono text-[10px] text-faint">
          {frozen && <CircleCheck size={11} aria-hidden="true" />}
          {costLabel}
        </span>
      </div>

      <div className="mb-2 font-mono text-2xl font-semibold tabular-nums" style={{ color: tone }}>
        <CostCounter value={cost} /> <span className="text-[11px] text-faint">tok</span>
      </div>

      <div
        ref={scroller}
        className="flex max-h-[280px] flex-col gap-1 overflow-y-auto pr-1 [scrollbar-color:var(--color-line)_transparent] [scrollbar-width:thin]"
      >
        {children}
      </div>

      {/* Outside the scroller on purpose: this is the most important thing in
          the pane, and inside it the banner scrolled out of view / clipped. */}
      {banner}

      <p className="mt-2 border-t border-line-soft pt-2 text-[11px] leading-relaxed text-muted">
        {footer}
      </p>
    </div>
  );
}

/** Framer Motion owns this, same as StatTicker. */
function CostCounter({ value }) {
  const spring = useSpring(0, { stiffness: 120, damping: 22 });
  const [shown, setShown] = useState(0);

  useEffect(() => spring.on("change", (v) => setShown(Math.round(v))), [spring]);
  useEffect(() => {
    spring.set(value);
  }, [spring, value]);

  return <>{shown.toLocaleString("en-US")}</>;
}

function Line({ turn, tool, args, right, rightTone, dim }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: dim ? 0.55 : 1, x: 0 }}
      transition={PANEL_SPRING}
      className="grid grid-cols-[22px_1fr_auto] items-baseline gap-2 font-mono text-[11px]"
    >
      <span className="text-faint">{String(turn).padStart(2, "0")}</span>
      <span className="truncate">
        <span className="text-ink">{tool}</span>
        <span className="text-faint">({args})</span>
      </span>
      <span style={{ color: rightTone }}>{right}</span>
    </motion.div>
  );
}
