import { motion } from "framer-motion";

/**
 * One dial reading: label, bar, number.
 *
 * The number is always printed. The bar is a fast read from the back of a room;
 * the number is what a judge leaning in actually checks, so it never gets
 * replaced by the bar.
 *
 * Framer Motion owns the fill width.
 */
export default function Meter({ label, value, color, title }) {
  return (
    <span
      className="flex items-center gap-1.5 font-mono text-[10px]"
      title={title ?? `${label} ${value.toFixed(2)}`}
    >
      <span className="w-5 text-faint">{label}</span>
      <span className="h-1 w-14 overflow-hidden rounded-sm bg-line">
        <motion.span
          className="block h-full rounded-sm"
          style={{ background: color }}
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(2, value * 100)}%` }}
          transition={{ duration: 0.45, ease: [0.2, 0.7, 0.2, 1] }}
        />
      </span>
      <span className="w-[30px] text-right tabular-nums" style={{ color }}>
        {value.toFixed(2)}
      </span>
    </span>
  );
}
