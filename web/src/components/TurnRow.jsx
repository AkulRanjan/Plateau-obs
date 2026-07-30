import { motion } from "framer-motion";
import { NOVELTY_FLOOR, QUAD } from "../data/trace.js";
import { PANEL_SPRING } from "../lib/motionTokens.js";
import Meter from "./Meter.jsx";

/**
 * One turn in the telemetry stream: the call, what came back, both dials, and
 * the quadrant it landed in.
 *
 * The novelty number turns red below the floor. That is the only colour change
 * carrying state here — similarity stays neutral, because similarity is the
 * evidence bar and not the trip axis, and colouring it would imply otherwise.
 */
export default function TurnRow({ row }) {
  const q = QUAD[row.quadrant];
  const belowFloor = row.nov < NOVELTY_FLOOR;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={PANEL_SPRING}
      className="grid grid-cols-[26px_1fr_auto] gap-2.5 rounded-lg bg-surface px-2.5 py-2.5"
      style={{ borderLeft: `2px solid ${q.c}` }}
    >
      <span className="pt-0.5 font-mono text-[11px] text-faint">
        {String(row.turn).padStart(2, "0")}
      </span>

      <div className="min-w-0">
        <div className="truncate font-mono text-xs">
          <span className="font-medium text-ink">{row.tool}</span>
          <span className="text-faint">({row.args})</span>
        </div>
        <div
          className={`mt-0.5 text-xs ${row.isError ? "text-red" : "text-muted"}`}
        >
          {row.isError ? "✕ " : "→ "}
          {row.obs}
        </div>
      </div>

      <div className="flex min-w-[150px] flex-col items-end gap-1">
        <Meter
          label="sim"
          value={row.sim}
          color="var(--color-muted)"
          title={`action similarity ${row.sim.toFixed(2)} vs ceiling ${row.ceiling.toFixed(2)}`}
        />
        <Meter
          label="nov"
          value={row.nov}
          color={belowFloor ? "var(--color-red)" : "var(--color-cyan)"}
          title={`observation novelty ${row.nov.toFixed(2)} vs floor ${NOVELTY_FLOOR.toFixed(2)}`}
        />
        <span
          className="mt-0.5 rounded-md border px-1.5 py-0.5 font-mono text-[9px] tracking-[0.06em]"
          style={{ color: q.c, borderColor: q.c }}
        >
          {q.label}
        </span>
      </div>
    </motion.div>
  );
}
