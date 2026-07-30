import { motion } from "framer-motion";
import { QUAD, STEP_CAP } from "../data/trace.js";
import { CURVE_DRAW } from "../lib/motionTokens.js";

const W = 560;
const H = 240;
const PAD = { l: 40, r: 16, t: 20, b: 28 };
const IW = W - PAD.l - PAD.r;
const IH = H - PAD.t - PAD.b;

/** Headroom above the ~6.05 plateau this trace settles at. */
const MAX_CUM = 7;
const GRID = [0, 2, 4, 6];

const xOf = (turn) => PAD.l + (IW * (turn - 1)) / (STEP_CAP - 1);
const yOf = (cum) => PAD.t + IH - (IH * cum) / MAX_CUM;

/**
 * Accumulated observation novelty per turn — the signature shape.
 *
 * It climbs while the agent learns and flattens when it stops. The flat is the
 * plateau, and the trip sits on it.
 *
 * The x-axis runs to the step-cap (25) rather than to the end of the trace, so
 * the gap between where Plateau stops and where a blind counter would have
 * stopped is visible as distance rather than asserted in copy.
 *
 * Framer Motion owns the line via `pathLength`: it draws on once, then the path
 * simply extends as turns arrive. The trip marker is intentionally NOT animated
 * here — it carries `data-plateau-tripmarker` and belongs to the Anime.js trip
 * timeline. One owner per element.
 */
export default function PlateauCurve({ rows, tripTurn }) {
  let cum = 0;
  const pts = rows.map((r) => {
    cum += r.nov;
    return {
      turn: r.turn,
      x: xOf(r.turn),
      y: yOf(cum),
      quadrant: r.quadrant,
    };
  });

  const line = pts
    .map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");

  const baseline = (PAD.t + IH).toFixed(1);
  const area = pts.length
    ? `${line} L${pts[pts.length - 1].x.toFixed(1)},${baseline} L${pts[0].x.toFixed(1)},${baseline} Z`
    : "";

  const last = pts.length ? pts[pts.length - 1] : null;
  const tripped = Boolean(tripTurn && last && last.turn >= tripTurn);
  const flatStart = pts.find((p) => p.turn >= (tripTurn ?? Infinity) - 2);

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="block h-auto w-full"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Cumulative information gained per turn, flattening at the plateau"
      >
        <defs>
          <linearGradient id="pl-area-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {GRID.map((g) => {
          const y = yOf(g);
          return (
            <g key={g}>
              <line x1={PAD.l} y1={y} x2={W - PAD.r} y2={y} className="pl-grid-l" />
              <text x={PAD.l - 8} y={y + 3} className="pl-axis-t" textAnchor="end">
                {g}
              </text>
            </g>
          );
        })}

        {/* Where a blind step counter would have stopped instead. */}
        <line
          x1={PAD.l + IW}
          y1={PAD.t}
          x2={PAD.l + IW}
          y2={PAD.t + IH}
          stroke="var(--color-faint)"
          strokeWidth="1"
          strokeDasharray="2 4"
          opacity="0.6"
        />
        <text
          x={PAD.l + IW}
          y={PAD.t - 6}
          className="pl-axis-t"
          textAnchor="end"
        >
          step-cap {STEP_CAP}
        </text>

        {area && <path d={area} fill="url(#pl-area-fill)" />}

        {line && (
          <motion.path
            d={line}
            className="pl-line"
            fill="none"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={CURVE_DRAW}
          />
        )}

        {/* The plateau itself, called out once the trip lands on it. */}
        {tripped && flatStart && (
          <line
            x1={flatStart.x}
            y1={flatStart.y}
            x2={last.x}
            y2={last.y}
            stroke="var(--color-red)"
            strokeWidth="3"
            strokeLinecap="round"
          />
        )}

        {pts.map((p) => {
          const isLive = last && p.turn === last.turn;
          return (
            <circle
              key={p.turn}
              cx={p.x}
              cy={p.y}
              r={isLive ? 4.5 : 2.6}
              style={{ fill: QUAD[p.quadrant].c, color: QUAD[p.quadrant].c }}
              className={isLive ? "pl-glow" : undefined}
            />
          );
        })}

        {/* Anime.js owns this group. Motion must not touch it. */}
        {tripped && (
          <g data-plateau-tripmarker>
            <line
              x1={last.x}
              y1={PAD.t}
              x2={last.x}
              y2={PAD.t + IH}
              stroke="var(--color-red)"
              strokeWidth="1.2"
              strokeDasharray="3 3"
              opacity="0.85"
            />
            <text
              x={last.x}
              y={PAD.t + IH + 18}
              className="font-mono text-[9px] font-semibold"
              style={{ fill: "var(--color-red)" }}
              textAnchor="middle"
            >
              plateau · trip
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}
