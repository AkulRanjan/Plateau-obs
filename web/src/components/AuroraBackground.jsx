import { useAuroraActive } from "../hooks/useAuroraActive.js";

/**
 * Decorative backdrop. Three radial gradients, and that is the cap.
 *
 * Performance contract, because this thing sits behind live data on a
 * projector:
 *
 *  - Three blobs, no more. Each one is a full-viewport compositor layer.
 *  - Animated with `transform` and `opacity` ONLY, so every frame is
 *    GPU-composited and nothing hits layout or paint.
 *  - No `filter: blur()`. A radial gradient with a soft falloff already looks
 *    like a blurred blob and costs a fraction of what a real blur pass costs.
 *  - Fully stopped — not slowed, stopped — under prefers-reduced-motion and
 *    while the tab is hidden. `will-change` is dropped at the same time so the
 *    layers can be discarded.
 *
 * The static grid overlay is the draft's `.pl-grain`, kept because it gives the
 * glass something to refract. It never animates.
 */
export default function AuroraBackground() {
  const active = useAuroraActive();

  return (
    <div
      className="pl-aurora"
      data-active={active ? "1" : "0"}
      aria-hidden="true"
    >
      <span className="pl-aurora-blob pl-aurora-blob--1" />
      <span className="pl-aurora-blob pl-aurora-blob--2" />
      <span className="pl-aurora-blob pl-aurora-blob--3" />
      <span className="pl-aurora-grid" />
    </div>
  );
}
