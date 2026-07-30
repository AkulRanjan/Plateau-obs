import { useEffect, useMemo } from "react";

import AuroraBackground from "./components/AuroraBackground.jsx";
import Controls from "./components/Controls.jsx";
import GlassPanel, { PanelHead } from "./components/GlassPanel.jsx";
import PlateauCurve from "./components/PlateauCurve.jsx";
import QuadrantMap, { Legend } from "./components/QuadrantMap.jsx";
import StatusBar from "./components/StatusBar.jsx";
import TelemetryFeed from "./components/TelemetryFeed.jsx";
import { usePlayback } from "./hooks/usePlayback.js";
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

  const accent = ACCENT[S.state] || "var(--color-cyan)";

  return (
    <div
      className="relative min-h-dvh font-display text-ink"
      style={{ "--accent": accent }}
      data-open={tripped ? "1" : "0"}
    >
      <AuroraBackground />

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

        {/* Hero copy + StatTicker land in the next commit. */}
        <GlassPanel className="mb-4">
          <PanelHead
            label="signature"
            sub="information gained per turn, accumulated"
          />
          <PlateauCurve rows={S.rows} tripTurn={S.tripTurn} />
        </GlassPanel>

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
      </div>
    </div>
  );
}
