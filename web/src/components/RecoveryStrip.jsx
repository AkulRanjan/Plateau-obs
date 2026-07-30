import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, CircleCheck, ShieldOff, Compass } from "lucide-react";
import { NOVELTY_FLOOR } from "../data/trace.js";
import {
  COST_OF_A_FALSE_TRIP_IN_TURNS,
  deriveRecovery,
  escapeVector,
} from "../lib/deriveRecovery.js";
import { PANEL_SPRING } from "../lib/motionTokens.js";
import GlassPanel, { PanelHead } from "./GlassPanel.jsx";
import InfoTip from "./InfoTip.jsx";

const ROUTE = escapeVector();

const STATE_COLOR = {
  OPEN: "var(--color-red)",
  HALF_OPEN: "var(--color-amber)",
  CLOSED: "var(--color-cyan)",
};

const ICON = {
  cooldown: ShieldOff,
  probe: Compass,
  closed: CircleCheck,
};

/**
 * What the breaker does after it trips.
 *
 * This does not auto-play. The demo contract is mount → play → halt at the trip
 * → tokens-saved springs; nothing may interrupt that, so recovery waits for a
 * deliberate click and only offers itself once the payoff beat has landed.
 */
export default function RecoveryStrip({ step, ready, onAdvance }) {
  const R = deriveRecovery(step);
  const started = step >= 0;

  return (
    <GlassPanel className="mt-4">
      <PanelHead
        label="recovery"
        sub="a false trip costs one turn — every other detector stops the run"
        right={
          <span className="font-mono text-[10px] text-faint">
            {started ? `${R.steps.length} / ${R.total}` : "not started"}
          </span>
        }
      />

      {/* The escape vector goes back into the agent's context on trip. */}
      <div className="mb-3 rounded-xl border border-line-soft bg-surface px-3.5 py-3">
        <div className="mb-1.5 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
          escape vector
          <InfoTip label="the escape vector">
            The highest-novelty turn in the run, handed back with the refusal so
            the agent has a route rather than just a stop. Turn 1 is excluded: it
            reads novelty {ROUTE?.openingTurnNovelty?.toFixed(2)} only because
            the comparison window starts empty, which is an artifact of the start
            of a run rather than a measure of how much it taught.
          </InfoTip>
        </div>
        {ROUTE?.hasRoute ? (
          <p className="text-xs text-muted">
            <span className="font-mono text-ink">turn {ROUTE.turn}</span>
            <span className="font-mono text-faint">
              {" "}
              · {ROUTE.tool}({ROUTE.args})
            </span>{" "}
            produced the most new information in this run (novelty{" "}
            <span className="font-mono text-cyan">
              {ROUTE.novelty.toFixed(2)}
            </span>
            ). Return to that result and build on it instead of re-asking.
          </p>
        ) : (
          <p className="text-xs text-muted">
            No turn in this run cleared the floor of {NOVELTY_FLOOR.toFixed(2)}.
            There is no productive path to return to — the task premise or the
            tool set needs to change.
          </p>
        )}
      </div>

      <AnimatePresence initial={false}>
        {R.steps.map((s) => {
          const Icon = ICON[s.phase];
          const color = STATE_COLOR[s.state];
          return (
            <motion.div
              key={s.phase}
              layout
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={PANEL_SPRING}
              className="mb-1.5 grid grid-cols-[26px_1fr_auto] gap-2.5 rounded-lg bg-surface px-2.5 py-2.5"
              style={{ borderLeft: `2px solid ${color}` }}
            >
              <span className="pt-0.5 font-mono text-[11px] text-faint">
                {s.turn ?? "→"}
              </span>

              <div className="min-w-0">
                <div className="flex items-center gap-2 font-mono text-xs">
                  <span
                    className="inline-flex items-center gap-1 font-semibold"
                    style={{ color }}
                  >
                    <Icon size={12} aria-hidden="true" />
                    {s.state}
                  </span>
                  <span className="text-faint">· {s.label}</span>
                </div>
                {s.tool && (
                  <div className="mt-0.5 truncate font-mono text-xs">
                    <span className="text-ink">{s.tool}</span>
                    <span className="text-faint">({s.args})</span>
                  </div>
                )}
                <div className="mt-0.5 text-xs text-muted">→ {s.obs}</div>
                <p className="mt-1 text-[11px] leading-relaxed text-faint">
                  {s.note}
                </p>
              </div>

              <div className="flex flex-col items-end gap-1">
                {s.novelty !== null ? (
                  <span className="font-mono text-[10px] text-faint">
                    nov{" "}
                    <span className="text-cyan">{s.novelty.toFixed(2)}</span>{" "}
                    ≥ {NOVELTY_FLOOR.toFixed(2)}
                  </span>
                ) : (
                  <span className="font-mono text-[10px] text-faint">
                    no embedding
                  </span>
                )}
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>

      {!R.done && (
        <button
          type="button"
          onClick={onAdvance}
          disabled={!ready}
          className="mt-1 inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-3.5 py-2 font-mono text-xs tracking-[0.04em] text-ink transition-[border-color,transform] duration-150 hover:-translate-y-px hover:border-muted disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:translate-y-0 disabled:hover:border-line"
        >
          {started ? "Next" : "Recover"}
          <ArrowRight size={13} aria-hidden="true" />
        </button>
      )}

      {R.done && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mt-2 font-mono text-[11px] text-cyan"
        >
          Cost of being wrong: {COST_OF_A_FALSE_TRIP_IN_TURNS} turn. Every other
          detector in this comparison stops the run.
        </motion.p>
      )}
    </GlassPanel>
  );
}
