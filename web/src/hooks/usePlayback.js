import { useCallback, useEffect, useState } from "react";

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
  //
  // There is deliberately NO ref guard here. An earlier version had one, and
  // under StrictMode it stopped the demo starting at all: first mount set the
  // flag and scheduled the timer, StrictMode's cleanup cleared that timer, and
  // the second mount saw the flag already set and scheduled nothing. The result
  // auto-played in a production build and sat on STANDBY in dev — the worst
  // possible split, because dev is what you'd have open while rehearsing.
  //
  // The cleanup is sufficient on its own: the effect runs once per mount, each
  // cleanup cancels the previous timer, so exactly one survives. setStep(0) and
  // setPlaying(true) are idempotent, so a double invocation is harmless anyway.
  useEffect(() => {
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
