import GlassPanel from "./GlassPanel.jsx";
import PlateauCurve from "./PlateauCurve.jsx";
import StatTicker, { Stat } from "./StatTicker.jsx";
import {
  NOVELTY_FLOOR,
  STEP_CAP,
  TOKENS_PER_TURN,
} from "../data/trace.js";

/**
 * The signature panel: what the curve means, and what stopping was worth.
 *
 * This is the second and last surface permitted to use backdrop-filter. The
 * curve itself sits in an inset SOLID well rather than directly on the blurred
 * glass — data legibility is a hard requirement and hero blur is an optional
 * effect, so where they compete the data wins. The glass still reads as glass
 * around it.
 */
export default function Hero({ rows, tripTurn, tripped }) {
  const turnsSpared = tripTurn ? STEP_CAP - tripTurn : 0;
  const tokensSaved = turnsSpared * TOKENS_PER_TURN;

  return (
    <GlassPanel
      blur
      className="mb-4 grid items-center gap-6 lg:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)]"
    >
      <div>
        <div className="mb-2.5 font-mono text-[10.5px] uppercase tracking-[0.14em] text-faint">
          signature · information gained per turn, accumulated
        </div>
        <h2 className="m-0 mb-2 text-[26px] font-semibold leading-[1.12] tracking-[-0.01em]">
          The curve tells you when to stop.
        </h2>
        <p className="m-0 mb-4 max-w-[34ch] text-[13.5px] text-muted">
          It climbs while the agent learns, then flattens when it stops. The
          breaker trips at the flat — not at the first repeat.
        </p>

        {/* items-end so the uppercase labels form one line; baselining the
            values instead leaves the 34px "tokens saved" label sitting lower
            than its neighbours. */}
        <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
          <Stat label="tokens saved" accent big>
            <StatTicker value={tokensSaved} active={tripped} />
          </Stat>
          <Stat label="tripped at">
            {tripped ? `turn ${tripTurn}` : <span className="text-faint">—</span>}
          </Stat>
          <Stat label="novelty floor" mono>
            {NOVELTY_FLOOR.toFixed(2)}
          </Stat>
        </div>

        {tripped && (
          <p className="mt-3.5 font-mono text-[11px] text-faint">
            est. vs. the run continuing to the step-cap ({STEP_CAP}),{" "}
            {TOKENS_PER_TURN.toLocaleString("en-US")} tok/turn
          </p>
        )}
      </div>

      {/* Inset solid well: the curve never sits on blurred glass. */}
      <div className="rounded-xl bg-[var(--bg-glass)] p-2">
        <PlateauCurve rows={rows} tripTurn={tripTurn} />
      </div>
    </GlassPanel>
  );
}
