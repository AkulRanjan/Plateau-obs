import { useState } from "react";
import {
  FloatingPortal,
  autoUpdate,
  flip,
  offset,
  shift,
  useDismiss,
  useFloating,
  useFocus,
  useHover,
  useInteractions,
  useRole,
} from "@floating-ui/react";
import { Info } from "lucide-react";

/**
 * A small source-of-truth tooltip.
 *
 * Used on the detector lanes to carry what each incumbent *actually* does,
 * verified by reading its source — see THIRD_PARTY_NOTICES.md. The lane
 * subtitles stay short for the projector; the checkable detail lives here.
 *
 * Focus and dismiss interactions are wired alongside hover so it is reachable
 * by keyboard and closes on Escape, rather than being hover-only.
 */
export default function InfoTip({ label, children }) {
  const [open, setOpen] = useState(false);

  const { refs, floatingStyles, context } = useFloating({
    open,
    onOpenChange: setOpen,
    placement: "top-start",
    middleware: [offset(8), flip({ padding: 8 }), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  });

  const { getReferenceProps, getFloatingProps } = useInteractions([
    useHover(context, { move: false, delay: { open: 80, close: 60 } }),
    useFocus(context),
    useDismiss(context),
    useRole(context, { role: "tooltip" }),
  ]);

  return (
    <>
      <button
        type="button"
        ref={refs.setReference}
        {...getReferenceProps()}
        aria-label={`What ${label} actually reads`}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-faint transition-colors hover:text-muted"
      >
        <Info size={12} aria-hidden="true" />
      </button>

      {open && (
        <FloatingPortal>
          <div
            ref={refs.setFloating}
            style={floatingStyles}
            {...getFloatingProps()}
            className="z-50 max-w-[320px] rounded-lg border border-line bg-[#0c1d22] px-3 py-2.5 font-mono text-[10.5px] leading-relaxed text-muted shadow-[0_18px_40px_-18px_#000]"
          >
            {children}
          </div>
        </FloatingPortal>
      )}
    </>
  );
}
