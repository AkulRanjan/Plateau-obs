import { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";

/**
 * Should decorative background motion run right now?
 *
 * False when the user asked for reduced motion, and false while the tab is
 * hidden. The aurora is the only thing in this app that animates continuously
 * rather than in response to a turn, so it is the only thing that can burn
 * frames while nothing is happening. It must never cost the data a frame.
 *
 * `useReducedMotion` comes from framer-motion — already a dependency, and it
 * subscribes to the media query rather than reading it once.
 */
export function useAuroraActive() {
  const reducedMotion = useReducedMotion();
  const [visible, setVisible] = useState(
    () => typeof document === "undefined" || !document.hidden
  );

  useEffect(() => {
    const onVisibility = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  return !reducedMotion && visible;
}
