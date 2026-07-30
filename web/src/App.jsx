import { useEffect, useMemo } from "react";

import AuroraBackground from "./components/AuroraBackground.jsx";
import Controls from "./components/Controls.jsx";
import DetectorRace from "./components/DetectorRace.jsx";
import GlassPanel, { PanelHead } from "./components/GlassPanel.jsx";
import Hero from "./components/Hero.jsx";
import QuadrantMap, { Legend } from "./components/QuadrantMap.jsx";
import StatusBar from "./components/StatusBar.jsx";
import TelemetryFeed from "./components/TelemetryFeed.jsx";
import { usePlayback } from "./hooks/usePlayback.js";
import { useTripSequence } from "./hooks/useTripSequence.js";
import { deriveState } from "./lib/deriveState.js";
import { ACCENT, TRACE } from "./data/trace.js";

export default function App() {
  const playback = usePlayback({ length: TRACE.length });
  const { step, pause } = playback;

  const S = useMemo(() => deriveState(step), [step]);
  const tripped = S.state === "open";

  // Halt the run the instant the breaker trips. This IS the product, so it is
  // the one effect in the app that must never be debounced or deferred.
  useEffect(() => {
    if (tripped) pause();
  }, [tripped, pause]);

  // The one Anime.js timeline: marker drop, pill flinch, accent flash. It runs
  // alongside the tokens ticker rather than before it — nothing is allowed to
  // delay the payoff beat.
  useTripSequence(tripped);

  const accent = ACCENT[S.state] || "var(--color-cyan)";

  return (
    <div
      className="relative min-h-dvh font-display text-ink"
      style={{ "--accent": accent }}
      data-open={tripped ? "1" : "0"}
    >
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
        <StatusBar state={S.state} />

        <Controls
          playing={playback.playing}
          atEnd={playback.atEnd}
          fast={playback.fast}
          tripped={tripped}
          turn={step}
          total={TRACE.length}
          onRun={playback.run}
          onPause={playback.pause}
          onStep={playback.stepOne}
          onReset={playback.reset}
          onToggleFast={playback.toggleFast}
        />

        <Hero rows={S.rows} tripTurn={S.tripTurn} tripped={tripped} />

        <div className="grid gap-4 lg:grid-cols-2">
          <GlassPanel>
            <PanelHead
              label="semantic space"
              sub="every turn placed by what it repeats × what it learned"
            />
            <QuadrantMap rows={S.rows} ceiling={S.ceiling} warm={S.warm} />
            <Legend />
          </GlassPanel>

          <GlassPanel className="flex flex-col">
            <PanelHead
              label="telemetry"
              sub="live turn stream"
              right={
                <span className="font-mono text-[10px] text-faint">
                  n={S.n} · streak={S.streak}
                </span>
              }
            />
            <TelemetryFeed
              rows={S.rows}
              tripped={tripped}
              tripTurn={S.tripTurn}
            />
          </GlassPanel>
        </div>

        <GlassPanel className="mt-4">
          <PanelHead
            label="detector race"
            sub="same trace, six detectors — who fired, and were they right"
          />
          <DetectorRace turn={step} />
        </GlassPanel>

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
