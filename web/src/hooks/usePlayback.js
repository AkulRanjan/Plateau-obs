import { useCallback, useEffect, useRef, useState } from "react";

/** Per-turn dwell, in ms. */
const TICK_NORMAL = 820;
const TICK_FAST = 430;

/** Delay before the run starts itself on mount. */
const AUTOSTART_MS = 650;

/**
 * The single clock.
 *
 * Every view — console, split-screen, recovery — reads `step` from here. No
 * view gets its own timer: two timers would drift, and the split-screen's whole
 * point is that both panes are on the same turn at the same moment.
 *
 * Auto-play on mount is part of the demo contract: the page starts running by
 * itself, and the caller halts it at the trip by calling `pause`.
 *
 * @param {object}  opts
 * @param {number}  opts.length total turns in the trace
 */
export function usePlayback({ length }) {
  const [step, setStep] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [fast, setFast] = useState(false);

  // Auto-start must fire once per mount, not once per StrictMode pass.
  const started = useRef(false);

  const atEnd = step >= length - 1;

  const pause = useCallback(() => setPlaying(false), []);

  const run = useCallback(() => {
    // Restart from the top if the run is already finished.
    setStep((s) => (s >= length - 1 ? 0 : s));
    setPlaying(true);
  }, [length]);

  const stepOne = useCallback(() => {
    setPlaying(false);
    setStep((s) => Math.min(length - 1, s + 1));
  }, [length]);

  const reset = useCallback(() => {
    setPlaying(false);
    setStep(-1);
  }, []);

  const toggleFast = useCallback(() => setFast((f) => !f), []);

  // --- advance ---
  useEffect(() => {
    if (!playing) return;
    if (step >= length - 1) {
      setPlaying(false);
      return;
    }
    const id = setTimeout(
      () => setStep((s) => s + 1),
      fast ? TICK_FAST : TICK_NORMAL
    );
    return () => clearTimeout(id);
  }, [playing, step, fast, length]);

  // --- kick off once on mount so the console animates itself ---
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const id = setTimeout(() => {
      setStep(0);
      setPlaying(true);
    }, AUTOSTART_MS);
    return () => clearTimeout(id);
  }, []);

  return {
    step,
    playing,
    fast,
    atEnd,
    run,
    pause,
    stepOne,
    reset,
    toggleFast,
  };
}
