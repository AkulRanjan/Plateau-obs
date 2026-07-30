import { useEffect } from "react";
import { useReducedMotion } from "framer-motion";
import { createTimeline } from "animejs";

/* ============================================================================
 * The ONLY Anime.js in this application.
 *
 * Everything else animates through Framer Motion. Anime is here for the one
 * thing Motion expresses awkwardly: a multi-step timeline across three
 * unrelated, non-sibling DOM nodes with staggered offsets.
 *
 * Every target below is addressed by data attribute, and every one of them is
 * a node Framer Motion does not touch:
 *
 *   [data-plateau-tripmarker]  the curve's trip marker  (PlateauCurve)
 *   [data-plateau-pill]        the breaker state pill   (StatusBar)
 *   [data-plateau-flash]       the accent flash overlay (App)
 *
 * If a future edit makes Motion animate any of these, this hook must move to a
 * different target — two libraries writing one node's transform is a bug, not
 * a layering trick.
 *
 * anime.js v4 API: named `createTimeline` / `stagger` imports. There is no
 * `anime.timeline()` in the installed major.
 * ========================================================================= */

/** Timings, in ms. Short: this fires the instant the run halts. */
const MARKER_MS = 420;
const PILL_MS = 380;
const FLASH_MS = 620;

/**
 * Play the trip sequence once, when the breaker opens.
 *
 * @param {boolean} tripped
 */
export function useTripSequence(tripped) {
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    if (!tripped) return;

    const marker = document.querySelector("[data-plateau-tripmarker]");
    const pill = document.querySelector("[data-plateau-pill]");
    const flash = document.querySelector("[data-plateau-flash]");

    // Under reduced motion the trip must still be unmistakable, it just must
    // not move. Show the marker, skip the choreography.
    if (reducedMotion) {
      if (marker) marker.style.opacity = "1";
      return;
    }

    const targets = [marker, pill, flash].filter(Boolean);
    if (targets.length === 0) return;

    const tl = createTimeline({
      defaults: { ease: "outQuad" },
    });

    // 1. The marker drops onto the plateau.
    if (marker) {
      tl.add(marker, {
        opacity: [0, 1],
        y: [-14, 0],
        duration: MARKER_MS,
      });
    }

    // 2. The state pill flinches — the run just got stopped.
    if (pill) {
      tl.add(
        pill,
        {
          x: [0, -4, 4, -3, 3, 0],
          scale: [1, 1.05, 1],
          duration: PILL_MS,
        },
        // Overlap slightly with the marker so it reads as one event.
        `-=${Math.round(MARKER_MS * 0.4)}`
      );
    }

    // 3. A single accent wash across the console, then gone.
    if (flash) {
      tl.add(
        flash,
        {
          opacity: [0, 0.5, 0],
          duration: FLASH_MS,
        },
        `-=${PILL_MS}`
      );
    }

    return () => {
      // revert() restores every target to its pre-animation state, so a Reset
      // mid-sequence cannot leave a node stuck mid-transform.
      tl.revert();
    };
  }, [tripped, reducedMotion]);
}
