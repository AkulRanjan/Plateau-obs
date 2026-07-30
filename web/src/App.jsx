import { useState } from "react";
import { Columns2, Gauge } from "lucide-react";

import AuroraBackground from "./components/AuroraBackground.jsx";
import ConsoleView from "./components/ConsoleView.jsx";
import SplitScreen from "./components/SplitScreen.jsx";

const MODES = [
  { key: "console", label: "Console", icon: Gauge },
  { key: "split", label: "Split screen", icon: Columns2 },
];

/**
 * Shell: backdrop, the trip flash overlay, and the mode switch.
 *
 * The two modes are mutually exclusive on purpose. Each owns its own clock —
 * the console's stops at the trip, the split-screen's runs on to the step-cap
 * so the unguarded pane can keep spending — and mounting only one at a time
 * means there is never more than one clock running.
 */
export default function App() {
  const [mode, setMode] = useState("console");

  return (
    <div className="relative min-h-dvh font-display text-ink">
      <AuroraBackground />

      {/* Accent wash on trip. Owned by the Anime.js timeline; pointer-events
          none and opacity 0 until it fires. */}
      <div
        data-plateau-flash
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 z-20 opacity-0"
        style={{
          background:
            "radial-gradient(60% 40% at 50% 45%, var(--color-red), transparent 70%)",
        }}
      />

      <div className="relative z-10 mx-auto max-w-[1180px] px-5 py-8">
        <div
          className="mb-4 inline-flex gap-1 rounded-xl border border-line-soft bg-surface p-1"
          role="tablist"
          aria-label="View"
        >
          {MODES.map(({ key, label, icon: Icon }) => {
            const active = mode === key;
            return (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setMode(key)}
                className="inline-flex items-center gap-2 rounded-lg px-3 py-1.5 font-mono text-[11px] tracking-[0.04em] transition-colors"
                style={
                  active
                    ? { background: "var(--color-cyan)", color: "#06171a" }
                    : { color: "var(--color-muted)" }
                }
              >
                <Icon size={13} aria-hidden="true" />
                {label}
              </button>
            );
          })}
        </div>

        {mode === "console" ? <ConsoleView /> : <SplitScreen />}

        <footer className="mt-4 flex flex-wrap justify-between gap-3.5 pt-1 font-mono text-[11px] text-faint">
          <span>
            Replaying a recorded trace. In production, turns stream from the live
            agent — the breaker decision (the C1 novelty gate) is Plateau's.
          </span>
          <span className="opacity-70">plateau · v0.1.0</span>
        </footer>
      </div>
    </div>
  );
}
