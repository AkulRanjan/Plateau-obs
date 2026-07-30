import { motion } from "framer-motion";
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
  const fy = yS(ceiling);
  const live = rows.length ? rows[rows.length - 1] : null;

  return (
    <div className="mx-auto w-full max-w-[340px]">
      <svg
        viewBox={`0 0 ${SZ} ${SZ}`}
        className="block h-auto w-full"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Quadrant map of agent turns by observation novelty and action similarity"
      >
        {/* Zone tints. They resize with the ceiling, so they spring with it. */}
        <motion.rect
          x={P}
          y={P}
          width={fx - P}
          animate={{ height: fy - P }}
          transition={DOT_SPRING}
          fill="color-mix(in srgb, var(--color-red) 8%, transparent)"
        />
        <motion.rect
          x={fx}
          y={P}
          width={SZ - P - fx}
          animate={{ height: fy - P }}
          transition={DOT_SPRING}
          fill="color-mix(in srgb, var(--color-violet) 7%, transparent)"
        />
        <motion.rect
          x={P}
          width={fx - P}
          animate={{ y: fy, height: SZ - P - fy }}
          transition={DOT_SPRING}
          fill="color-mix(in srgb, var(--color-amber) 6%, transparent)"
        />
        <motion.rect
          x={fx}
          width={SZ - P - fx}
          animate={{ y: fy, height: SZ - P - fy }}
          transition={DOT_SPRING}
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
        {/* Similarity ceiling: learned, so it moves. */}
        <motion.line
          x1={P}
          x2={SZ - P}
          animate={{ y1: fy, y2: fy }}
          transition={DOT_SPRING}
          className={`pl-div ${warm ? "" : "pl-div--cold"}`}
        />

        <text x={fx + 4} y={SZ - P + 14} className="pl-div-t">
          novelty floor {NOVELTY_FLOOR.toFixed(2)}
        </text>
        <motion.text
          x={P - 6}
          animate={{ y: fy - 4 }}
          transition={DOT_SPRING}
          className="pl-div-t"
          textAnchor="end"
        >
          sim ceiling {ceiling.toFixed(2)}
        </motion.text>

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
                <text
                  x={cx}
                  y={cy - 14}
                  className="font-mono text-[8.5px] font-semibold"
                  style={{ fill: QUAD[r.quadrant].c }}
                  textAnchor="middle"
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
