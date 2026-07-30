import { useEffect, useState } from "react";
import { useSpring } from "framer-motion";
import { TICKER_SPRING } from "../lib/motionTokens.js";

/**
 * The payoff number: tokens not spent because the run stopped.
 *
 * Framer Motion owns this. It is a spring rather than a linear count-up
 * because the number arriving with a little overshoot is what makes it read as
 * a result rather than a loading indicator.
 *
 * `active` gates it so the count starts on the trip and not on mount.
 */
export default function StatTicker({ value, active, format = true }) {
  const spring = useSpring(0, TICKER_SPRING);
  const [shown, setShown] = useState(0);

  useEffect(() => spring.on("change", (v) => setShown(Math.round(v))), [spring]);

  useEffect(() => {
    spring.set(active ? value : 0);
  }, [spring, value, active]);

  if (!active) return <span className="text-faint">—</span>;

  return (
    <span className="tabular-nums">
      {format ? shown.toLocaleString("en-US") : shown}
    </span>
  );
}

/** Label-under-value stat block, used across the hero. */
export function Stat({ label, children, accent = false, big = false, mono = false }) {
  return (
    <div>
      <div
        className={[
          "font-semibold tabular-nums",
          big ? "font-mono text-[34px] tracking-[-0.02em]" : "text-lg",
          mono && !big ? "font-mono" : "",
        ].join(" ")}
        style={accent ? { color: "var(--accent)" } : undefined}
      >
        {children}
      </div>
      <div className="mt-0.5 text-[10.5px] uppercase tracking-[0.12em] text-faint">
        {label}
      </div>
    </div>
  );
}
