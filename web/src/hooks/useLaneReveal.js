import { useEffect } from "react";
import { useReducedMotion } from "framer-motion";
import { createTimeline, stagger } from "animejs";

/* ============================================================================
 * The second and last Anime.js hook.
 *
 * Anime is used here for the same reason as in useTripSequence: a staggered
 * multi-element reveal with a shared timeline is what it is good at, and
 * expressing the same thing in Motion means either variants threaded through
 * four components or four hand-offset transitions.
 *
 * Targets are plain elements carrying `data-plateau-lane`. Framer Motion does
 * not animate them — scripts/ownership.mjs enforces that, and enforces that
 * animejs stays confined to these hooks rather than leaking into components.
 * ========================================================================= */

const LANE_MS = 380;
const LANE_STAGGER_MS = 70;

/**
 * Reveal the detector lanes once, on mount.
 *
 * @param {number} count how many lanes are present, so the effect re-runs if
 *   the set ever changes rather than animating a stale node list
 */
export function useLaneReveal(count) {
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    if (reducedMotion || count === 0) return;

    const lanes = document.querySelectorAll("[data-plateau-lane]");
    if (lanes.length === 0) return;

    const tl = createTimeline({ defaults: { ease: "outQuad" } });
    tl.add(lanes, {
      opacity: [0, 1],
      y: [10, 0],
      duration: LANE_MS,
      delay: stagger(LANE_STAGGER_MS),
    });

    return () => tl.revert();
  }, [count, reducedMotion]);
}
