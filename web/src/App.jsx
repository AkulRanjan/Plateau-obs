import AuroraBackground from "./components/AuroraBackground.jsx";
import GlassPanel, { PanelHead } from "./components/GlassPanel.jsx";

export default function App() {
  return (
    <div className="relative min-h-dvh font-display text-ink">
      <AuroraBackground />

      <div className="relative z-10 mx-auto max-w-[1180px] px-5 py-8">
        <GlassPanel blur className="mb-4">
          <PanelHead
            label="status bar"
            sub="one of only two surfaces permitted to use backdrop-filter"
          />
          <p className="font-mono text-xs text-muted">
            aurora + glass primitives in place
          </p>
        </GlassPanel>

        <div className="grid gap-4 md:grid-cols-2">
          <GlassPanel>
            <PanelHead label="solid panel" sub="no blur — data legibility first" />
            <p className="font-mono text-xs text-muted">
              telemetry-grade text on a solid fill
            </p>
          </GlassPanel>
          <GlassPanel>
            <PanelHead label="solid panel" sub="aurora shows through the gutters" />
            <p className="font-mono text-xs text-muted">
              contrast is independent of what drifts behind it
            </p>
          </GlassPanel>
        </div>
      </div>
    </div>
  );
}
