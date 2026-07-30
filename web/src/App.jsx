/* SMOKE TEST — replaced in step 1.
 *
 * Its only job is to import every bleeding-edge dependency so that
 * `npm run build` actually proves the pinned set works together, rather than
 * proving that an empty React app works together. Every import below is
 * exercised, not just referenced. */
import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { animate, createTimeline, stagger } from "animejs";
import {
  useFloating,
  useHover,
  useInteractions,
  offset,
  flip,
  shift,
} from "@floating-ui/react";
import { Activity, CircleStop, Info } from "lucide-react";

export default function App() {
  const boxRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [animeOk, setAnimeOk] = useState("pending");

  const { refs, floatingStyles, context } = useFloating({
    open,
    onOpenChange: setOpen,
    placement: "top",
    middleware: [offset(8), flip(), shift({ padding: 8 })],
  });
  const { getReferenceProps, getFloatingProps } = useInteractions([
    useHover(context),
  ]);

  useEffect(() => {
    if (!boxRef.current) return;
    // anime.js v4 named-export API. v3's `anime.timeline()` does not exist here.
    const tl = createTimeline({ defaults: { duration: 400 } });
    tl.add(boxRef.current, { opacity: [0, 1] });
    animate(boxRef.current, { scale: [0.96, 1], duration: 400 });
    setAnimeOk(
      typeof animate === "function" &&
        typeof createTimeline === "function" &&
        typeof stagger === "function"
        ? "v4 ok"
        : "WRONG MAJOR"
    );
    return () => tl.revert();
  }, []);

  return (
    <div className="min-h-dvh bg-bg p-10 font-display text-ink">
      <h1 className="text-2xl font-bold tracking-[0.22em]">PLATEAU</h1>

      <div ref={boxRef} className="mt-6 rounded-xl border border-line-soft p-5">
        <p className="font-mono text-xs text-muted">build smoke test</p>
        <ul className="mt-3 space-y-1 font-mono text-xs">
          <li className="text-cyan">react 19 + tailwind v4 utilities</li>
          <li className="text-cyan">animejs: {animeOk}</li>
          <li className="flex items-center gap-2 text-cyan">
            lucide <Activity size={14} /> <CircleStop size={14} />
          </li>
          <li
            ref={refs.setReference}
            {...getReferenceProps()}
            className="flex w-fit items-center gap-2 text-cyan"
          >
            floating-ui (hover me) <Info size={14} />
          </li>
        </ul>
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 220, damping: 26 }}
          className="mt-3 font-mono text-xs text-violet"
        >
          framer-motion spring ok
        </motion.div>
      </div>

      {open && (
        <div
          ref={refs.setFloating}
          style={floatingStyles}
          {...getFloatingProps()}
          className="rounded-lg border border-line bg-surface px-3 py-2 font-mono text-xs text-ink"
        >
          tooltip renders
        </div>
      )}
    </div>
  );
}
