/**
 * Shared motion constants.
 *
 * One place for every duration and spring so the whole console moves with one
 * character, and so a single edit can slow everything down if the projector
 * turns out to be slower than the laptop.
 *
 * Framer Motion owns everything in this file. Anime.js timings live in
 * hooks/useTripSequence.js and nowhere else.
 */

/** Dots settling into a new (novelty x similarity) coordinate. */
export const DOT_SPRING = {
  type: "spring",
  stiffness: 260,
  damping: 30,
  mass: 0.7,
};

/** Panels and list rows arriving. Quick, no bounce — this is instrumentation. */
export const PANEL_SPRING = {
  type: "spring",
  stiffness: 240,
  damping: 28,
};

/** The tokens-saved counter. Deliberately springy: it is the payoff beat. */
export const TICKER_SPRING = {
  type: "spring",
  stiffness: 90,
  damping: 14,
  mass: 1.1,
};

/** Curve line draw-on, via pathLength. */
export const CURVE_DRAW = {
  duration: 0.55,
  ease: [0.2, 0.7, 0.2, 1],
};

/** Telemetry row entrance. */
export const ROW_IN = {
  initial: { opacity: 0, x: -8 },
  animate: { opacity: 1, x: 0 },
  transition: PANEL_SPRING,
};
