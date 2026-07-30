/**
 * A panel. Solid by default.
 *
 * `blur` opts into `backdrop-filter`, and it is permitted on exactly two
 * surfaces in this app: StatusBar and Hero. Everything else takes the solid
 * `--bg-glass` fill. Stacked backdrop-blur over the animating aurora is the
 * single most reliable way to lose framerate on integrated graphics, and the
 * data panels are the ones that must never stutter.
 *
 * If you are about to pass `blur` to a third surface, don't — solidify it
 * instead. The look survives; the framerate does not.
 */
export default function GlassPanel({
  as: Tag = "section",
  blur = false,
  className = "",
  children,
  ...rest
}) {
  return (
    <Tag
      className={`pl-panel ${blur ? "pl-panel--blur" : ""} ${className}`}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/** Panel header: mono eyebrow label plus a plain-language subtitle. */
export function PanelHead({ label, sub, right = null }) {
  return (
    <div className="mb-3.5 flex items-baseline gap-3">
      <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-[var(--accent)]">
        {label}
      </span>
      {sub && <span className="text-xs text-faint">{sub}</span>}
      {right && <span className="ml-auto">{right}</span>}
    </div>
  );
}
