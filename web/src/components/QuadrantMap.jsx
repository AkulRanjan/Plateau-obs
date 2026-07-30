import { useEffect, useState } from "react";
import { motion, useSpring } from "framer-motion";
import { NOVELTY_FLOOR, QUAD, QUAD_NOTE } from "../data/trace.js";
import { DOT_SPRING } from "../lib/motionTokens.js";
import {
  IW,
  PAD as P,
  SZ,
  xOfNovelty as xN,
  yOfSimilarity as yS,
} from "../lib/quadrantGeometry.js";

const CORNERS = [
  { key: "stuck", x: P + 6, y: P + 14, anchor: "start" },
  { key: "batch", x: SZ - P - 6, y: P + 14, anchor: "end" },
  { key: "thrash", x: P + 6, y: SZ - P - 6, anchor: "start" },
  { key: "productive", x: SZ - P - 6, y: SZ - P - 6, anchor: "end" },
];

/**
 * Every turn placed by what it repeated (y) against what it learned (x).
 *
 * Two deliberate choices about motion here:
 *
 *  - Dot coordinates are exact from the first frame. They are never sprung
 *    into place, because a dot in transit is a dot reporting a reading the
 *    agent never produced. Only scale and opacity animate on entrance.
 *  - The similarity-ceiling divider IS sprung, because that line genuinely
 *    moves: it sits at the conservative 0.90 while cold and drops to the
 *    learned 0.55 once the calibrator warms. That movement is the calibrator
 *    learning, so it is worth seeing.
 */
export default function QuadrantMap({ rows, ceiling, warm }) {
  const fx = xN(NOVELTY_FLOOR);
  const live = rows.length ? rows[rows.length - 1] : null;

  // The one quantity in this chart that genuinely moves. Framer Motion owns it;
  // every coordinate below is derived from the sprung value, so the zone tints,
  // the divider and its label all travel together as one piece of geometry.
  const ceilingSpring = useSpring(ceiling, DOT_SPRING);
  const [animatedCeiling, setAnimatedCeiling] = useState(ceiling);

  useEffect(
    () => ceilingSpring.on("change", setAnimatedCeiling),
    [ceilingSpring]
  );
  useEffect(() => {
    ceilingSpring.set(ceiling);
  }, [ceilingSpring, ceiling]);

  const fy = yS(animatedCeiling);

  return (
    <div className="mx-auto w-full max-w-[400px]">
      <svg
        viewBox={`0 0 ${SZ + 74} ${SZ}`}
        className="block h-auto w-full"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Quadrant map of agent turns by observation novelty and action similarity"
      >
        {/* Zone tints, frame and dividers are PLAIN SVG.
            An earlier version used motion.rect / motion.line with `animate` on
            height / y1 / y2. Motion overwrites the static attribute during its
            first pass, so SVG received height="undefined" and the console filled
            with "Expected length" errors on every render. Animating the single
            ceiling VALUE and deriving the geometry from it is both simpler and
            more honest: one quantity actually moves, so one spring drives it,
            and every attribute below is always a real number. */}
        <rect
          x={P}
          y={P}
          width={fx - P}
          height={fy - P}
          fill="color-mix(in srgb, var(--color-red) 8%, transparent)"
        />
        <rect
          x={fx}
          y={P}
          width={SZ - P - fx}
          height={fy - P}
          fill="color-mix(in srgb, var(--color-violet) 7%, transparent)"
        />
        <rect
          x={P}
          y={fy}
          width={fx - P}
          height={SZ - P - fy}
          fill="color-mix(in srgb, var(--color-amber) 6%, transparent)"
        />
        <rect
          x={fx}
          y={fy}
          width={SZ - P - fx}
          height={SZ - P - fy}
          fill="color-mix(in srgb, var(--color-cyan) 7%, transparent)"
        />

        <rect
          x={P}
          y={P}
          width={IW}
          height={IW}
          fill="none"
          stroke="var(--color-line)"
          strokeWidth="1"
        />

        {/* Novelty floor: fixed, never calibrated. */}
        <line x1={fx} y1={P} x2={fx} y2={SZ - P} className="pl-div" />
        {/* Similarity ceiling: learned, so it moves — 0.90 while cold, dropping
            to the calibrated value once warm. */}
        <line
          x1={P}
          y1={fy}
          x2={SZ - P}
          y2={fy}
          className={`pl-div ${warm ? "" : "pl-div--cold"}`}
        />

        <text x={fx + 4} y={SZ - P + 14} className="pl-div-t">
          novelty floor {NOVELTY_FLOOR.toFixed(2)}
        </text>
        {/* Right-hand gutter, not the left: anchored "end" at x = PAD - 6 it ran
            off the viewBox and rendered clipped. */}
        <text
          x={SZ - P + 6}
          y={fy - 4}
          className="pl-div-t"
          textAnchor="start"
        >
          sim ceiling {ceiling.toFixed(2)}
        </text>

        {CORNERS.map((c) => (
          <text
            key={c.key}
            x={c.x}
            y={c.y}
            className="pl-corner"
            style={{ fill: QUAD[c.key].c }}
            textAnchor={c.anchor}
          >
            {QUAD[c.key].label}
          </text>
        ))}

        <text x={P + IW / 2} y={SZ - 6} className="pl-axlabel" textAnchor="middle">
          observation novelty → did we learn?
        </text>
        <text
          x={12}
          y={P + IW / 2}
          className="pl-axlabel"
          textAnchor="middle"
          transform={`rotate(-90 12 ${P + IW / 2})`}
        >
          action similarity ↑ same move?
        </text>

        {rows.map((r) => {
          const isLive = live && r.turn === live.turn;
          const cx = xN(r.nov);
          const cy = yS(r.sim);
          return (
            <g key={r.turn}>
              <motion.circle
                cx={cx}
                cy={cy}
                r={isLive ? 5.5 : 3.6}
                style={{ fill: QUAD[r.quadrant].c, color: QUAD[r.quadrant].c }}
                className={isLive ? "pl-glow" : undefined}
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={DOT_SPRING}
              />
              {isLive && (
                // The live label has to dodge two things, and both matter most
                // at the trip — when novelty is 0.00 and similarity is high, the
                // dot lands in the top-left corner on top of the STUCK label.
                // So: drop the label below the dot when there is no room above,
                // and left-align it when the dot is against the left edge rather
                // than centring it into the margin.
                <text
                  x={cx}
                  // P + 46, not P + 30: the corner label's own glyphs reach
                  // roughly y = PAD + 16, so a threshold that only clears the
                  // baseline still overlaps. scripts/visual.mjs caught this.
                  y={cy > P + 46 ? cy - 14 : cy + 19}
                  className="font-mono text-[8.5px] font-semibold"
                  style={{ fill: QUAD[r.quadrant].c }}
                  textAnchor={
                    cx < P + 26 ? "start" : cx > SZ - P - 26 ? "end" : "middle"
                  }
                >
                  turn {r.turn}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/** Colour key, with what each quadrant means for the run. */
export function Legend() {
  return (
    <div className="mt-3.5 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-line-soft pt-3.5">
      {["stuck", "thrash", "batch", "productive"].map((key) => (
        <span
          key={key}
          className="inline-flex items-center gap-1.5 font-mono text-[11px] text-muted"
        >
          <span
            className="block h-2.5 w-2.5 shrink-0 rounded-sm"
            style={{ background: QUAD[key].c }}
          />
          {QUAD[key].label.toLowerCase()}
          <span className="text-faint">· {QUAD_NOTE[key]}</span>
        </span>
      ))}
    </div>
  );
}
