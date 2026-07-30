import GlassPanel from "./GlassPanel.jsx";
import { STATE_COPY, TASK } from "../data/trace.js";

/**
 * Brand, one-line pitch, and the breaker's current state.
 *
 * This is one of only two surfaces that may use backdrop-filter (see
 * GlassPanel). It earns it: it sits at the top over the brightest part of the
 * aurora and it does not re-render per turn beyond a text swap.
 *
 * The state pill carries `data-plateau-pill`, which is how the Anime.js trip
 * timeline finds it. Framer Motion does not touch this node — that separation
 * is the one-animation-owner rule, and the data attribute is the seam.
 */
export default function StatusBar({ state }) {
  return (
    <GlassPanel blur className="mb-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <span className="relative block h-[30px] w-[30px] shrink-0" aria-hidden="true">
            {/* The mark: a rising line that flattens. */}
            <span
              className="absolute inset-x-0.5 top-1/2 h-0.5"
              style={{
                background:
                  "linear-gradient(90deg, transparent, var(--accent) 55%, var(--accent) 62%, var(--color-faint) 62%)",
              }}
            />
            <span
              className="absolute left-[60%] top-1/2 -ml-[3.5px] -mt-[3.5px] block h-[7px] w-[7px] rounded-full"
              style={{
                background: "var(--accent)",
                boxShadow: "0 0 12px var(--accent)",
              }}
            />
          </span>
          <div>
            <h1 className="m-0 text-2xl font-bold tracking-[0.22em]">PLATEAU</h1>
            <p className="mt-0.5 text-[12.5px] text-muted">
              A semantic circuit breaker for autonomous agents.
            </p>
          </div>
        </div>

        <div
          data-plateau-pill
          data-state={state}
          className="flex items-center gap-2.5 rounded-full border px-3.5 py-2 font-mono text-[11.5px] tracking-[0.06em]"
          style={{
            borderColor: "var(--accent)",
            color: "var(--accent)",
            background: "color-mix(in srgb, var(--accent) 10%, transparent)",
          }}
        >
          <span className="pl-led block h-2 w-2 rounded-full" />
          <span>{STATE_COPY[state]}</span>
        </div>
      </div>

      <p className="mt-4 font-mono text-xs text-faint">{TASK}</p>
    </GlassPanel>
  );
}
