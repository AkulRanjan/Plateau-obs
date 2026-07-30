import { useCallback, useEffect, useMemo, useState } from "react";

import Controls from "./Controls.jsx";
import DetectorRace from "./DetectorRace.jsx";
import GlassPanel, { PanelHead } from "./GlassPanel.jsx";
import Hero from "./Hero.jsx";
import LongTraceTable from "./LongTraceTable.jsx";
import MeasuredFixtures from "./MeasuredFixtures.jsx";
import QuadrantMap, { Legend } from "./QuadrantMap.jsx";
import RecoveryStrip from "./RecoveryStrip.jsx";
import StatusBar from "./StatusBar.jsx";
import TelemetryFeed from "./TelemetryFeed.jsx";
import { usePlayback } from "../hooks/usePlayback.js";
import { useTripSequence } from "../hooks/useTripSequence.js";
import { deriveState } from "../lib/deriveState.js";
import { ACCENT, TRACE } from "../data/trace.js";
import { EPILOGUE } from "../data/epilogue.js";

/** Long enough for the tokens-saved spring to settle before Recover appears. */
const TICKER_SETTLE_MS = 1500;

/**
 * The main console: one run, played once, halted at the plateau.
 *
 * Owns the clock for this mode. Exactly one mode is mounted at a time, so
 * exactly one clock exists at a time — the console's clock stops at the trip,
 * the split-screen's runs on to the step-cap, and neither can interfere with
 * the other.
 */
export default function ConsoleView() {
  const playback = usePlayback({ length: TRACE.length });
  const { step, pause } = playback;

  const S = useMemo(() => deriveState(step), [step]);
  const tripped = S.state === "open";

  // Halt the run the instant the breaker trips. This IS the product, so it is
  // the one effect in the app that must never be debounced or deferred.
  useEffect(() => {
    if (tripped) pause();
  }, [tripped, pause]);

  // The one Anime.js trip timeline: marker drop, pill flinch, accent flash. It
  // runs alongside the tokens ticker rather than before it — nothing is allowed
  // to delay the payoff beat.
  useTripSequence(tripped);

  // --- recovery (claim 4) ---------------------------------------------------
  // Deliberately manual. The demo contract is mount -> play -> halt -> ticker,
  // and recovery must not compete with any part of it: the control only becomes
  // available once the tokens-saved spring has had time to land, and it never
  // advances on its own.
  const [recoveryStep, setRecoveryStep] = useState(-1);
  const [recoveryReady, setRecoveryReady] = useState(false);

  useEffect(() => {
    if (!tripped) {
      setRecoveryReady(false);
      setRecoveryStep(-1);
      return;
    }
    const id = setTimeout(() => setRecoveryReady(true), TICKER_SETTLE_MS);
    return () => clearTimeout(id);
  }, [tripped]);

  const advanceRecovery = useCallback(
    () => setRecoveryStep((s) => Math.min(EPILOGUE.length - 1, s + 1)),
    []
  );

  return (
    <div
      style={{ "--accent": ACCENT[S.state] || "var(--color-cyan)" }}
      data-open={tripped ? "1" : "0"}
    >
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
          <TelemetryFeed rows={S.rows} tripped={tripped} tripTurn={S.tripTurn} />
        </GlassPanel>
      </div>

      <GlassPanel className="mt-4">
        <PanelHead
          label="detector race"
          sub="same trace, six detectors — who fired, and were they right"
        />
        <DetectorRace turn={step} />
      </GlassPanel>

      {tripped && (
        <RecoveryStrip
          step={recoveryStep}
          ready={recoveryReady}
          onAdvance={advanceRecovery}
        />
      )}

      <LongTraceTable />

      <MeasuredFixtures />
    </div>
  );
}
