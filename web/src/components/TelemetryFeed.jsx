import { useEffect, useRef } from "react";
import { AnimatePresence } from "framer-motion";
import { STEP_CAP, TRACE } from "../data/trace.js";
import TurnRow from "./TurnRow.jsx";

/**
 * The live turn stream, pinned to the newest turn.
 *
 * When the breaker opens, the feed closes with an explicit halt rule stating
 * how many turns were prevented. Without that line the panel just stops, and
 * "stopped" and "finished" look identical in a log — which is the whole
 * complaint the project opens with.
 */
export default function TelemetryFeed({ rows, tripped, tripTurn }) {
  const scroller = useRef(null);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [rows.length, tripped]);

  const prevented = tripTurn ? STEP_CAP - tripTurn : 0;

  return (
    <div
      ref={scroller}
      className="flex max-h-[360px] flex-1 flex-col gap-1.5 overflow-y-auto pr-1 [scrollbar-color:var(--color-line)_transparent] [scrollbar-width:thin]"
    >
      {rows.length === 0 && (
        <div className="px-1 py-8 text-center text-[13px] text-faint">
          Press <b className="text-muted">Run</b> to replay the agent trace.
        </div>
      )}

      <AnimatePresence initial={false}>
        {rows.map((row) => (
          <TurnRow key={row.turn} row={row} />
        ))}
      </AnimatePresence>

      {tripped && (
        <div className="mt-1 flex items-center gap-2.5 py-1">
          <span
            className="h-px flex-1"
            style={{
              background:
                "linear-gradient(90deg, transparent, var(--color-red), transparent)",
            }}
          />
          <span className="whitespace-nowrap font-mono text-[10px] tracking-[0.04em] text-red">
            run halted by Plateau · {prevented} further turns prevented
          </span>
          <span
            className="h-px flex-1"
            style={{
              background:
                "linear-gradient(90deg, transparent, var(--color-red), transparent)",
            }}
          />
        </div>
      )}
    </div>
  );
}

/** Total turns in the replay, for the panel subtitle. */
export const TOTAL_TURNS = TRACE.length;
