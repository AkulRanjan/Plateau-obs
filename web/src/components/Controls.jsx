import { Pause, Play, RotateCcw, SkipForward, Zap } from "lucide-react";

const BTN =
  "inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-3.5 py-2 " +
  "font-mono text-xs tracking-[0.04em] text-ink transition-[border-color,transform] " +
  "duration-150 hover:-translate-y-px hover:border-muted disabled:cursor-not-allowed " +
  "disabled:opacity-35 disabled:hover:translate-y-0 disabled:hover:border-line";

/**
 * Transport for the replay.
 *
 * `Step` is disabled once the breaker is open: stepping past a trip would walk
 * the run straight through the thing the product exists to prevent, which is
 * exactly the wrong message on a projector. Reset and Replay remain available.
 */
export default function Controls({
  playing,
  atEnd,
  fast,
  tripped,
  turn,
  total,
  onRun,
  onPause,
  onStep,
  onReset,
  onToggleFast,
}) {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      {playing ? (
        <button
          type="button"
          onClick={onPause}
          className={`${BTN} border-transparent font-semibold`}
          style={{
            background: "var(--accent)",
            color: "#06171a",
            boxShadow: "0 0 20px -6px var(--accent)",
          }}
        >
          <Pause size={13} aria-hidden="true" /> Pause
        </button>
      ) : (
        <button
          type="button"
          onClick={onRun}
          className={`${BTN} border-transparent font-semibold`}
          style={{
            background: "var(--accent)",
            color: "#06171a",
            boxShadow: "0 0 20px -6px var(--accent)",
          }}
        >
          <Play size={13} aria-hidden="true" /> {atEnd || tripped ? "Replay" : "Run"}
        </button>
      )}

      <button
        type="button"
        onClick={onStep}
        disabled={tripped || atEnd}
        className={BTN}
      >
        <SkipForward size={13} aria-hidden="true" /> Step
      </button>

      <button type="button" onClick={onReset} className={BTN}>
        <RotateCcw size={13} aria-hidden="true" /> Reset
      </button>

      <button
        type="button"
        onClick={onToggleFast}
        aria-pressed={fast}
        className={BTN}
        style={fast ? { color: "var(--accent)", borderColor: "var(--accent)" } : null}
      >
        <Zap size={13} aria-hidden="true" /> {fast ? "2×" : "1×"}
      </button>

      <div className="ml-auto flex items-baseline gap-2 font-mono">
        <span className="text-[10px] uppercase tracking-[0.14em] text-faint">
          turn
        </span>
        <span className="text-lg font-medium tabular-nums text-ink">
          {turn < 0 ? "—" : turn + 1}
          <span className="text-[13px] text-faint"> / {total}</span>
        </span>
      </div>
    </div>
  );
}
