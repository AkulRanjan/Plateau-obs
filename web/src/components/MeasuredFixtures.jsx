import { QUAD } from "../data/trace.js";
import fixturesDoc from "../data/fixtures.json";
import GlassPanel, { PanelHead } from "./GlassPanel.jsx";
import InfoTip from "./InfoTip.jsx";

/**
 * The real measured readings, as distinct from the replay.
 *
 * Everything else on this page is a recorded trace with hand-set dials. This
 * panel is the one place showing numbers that actually came out of MiniLM at a
 * pinned revision, extracted from the repo's metrics.json by
 * scripts/extract_metrics.mjs.
 *
 * Two things are deliberately surfaced rather than smoothed over:
 *
 *  - Fixtures 1 and 2 are two turns long. Every trip threshold in the package
 *    is at least 3, so they CANNOT trip, and their empty trip column measures
 *    trace length rather than detector behaviour. Saying that is the difference
 *    between a limitation and a misleading table.
 *  - The measured floor is 0.30 — the package default — whereas the replay
 *    above is calibrated to 0.15 for this trace. Both numbers appear, each
 *    labelled with where it comes from.
 *
 * Recall, the parameter sweep, and anything derived from them are not here.
 * They are not valid yet, for the reason in the first bullet.
 */
export default function MeasuredFixtures() {
  const { fixtures, encoder, novelty_floor, novelty_floor_status } = fixturesDoc;

  return (
    <GlassPanel className="mt-4">
      <PanelHead
        label="measured · metrics.json"
        sub="real encoder output on the package's own fixtures — not the replay"
        right={
          <span className="font-mono text-[10px] text-faint">
            MiniLM-L6-v2 @ {encoder.revision?.slice(0, 8)} · seed {encoder.seed}
          </span>
        }
      />

      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse font-mono text-[11px]">
          <thead>
            <tr className="border-b border-line-soft text-left text-faint">
              <th className="pb-2 pr-3 font-normal uppercase tracking-[0.1em]">
                fixture
              </th>
              <th className="pb-2 pr-3 font-normal uppercase tracking-[0.1em]">
                action_sim
              </th>
              <th className="pb-2 pr-3 font-normal uppercase tracking-[0.1em]">
                obs_novelty
              </th>
              <th className="pb-2 pr-3 font-normal uppercase tracking-[0.1em]">
                quadrant
              </th>
              <th className="pb-2 font-normal uppercase tracking-[0.1em]">
                trip
              </th>
            </tr>
          </thead>
          <tbody>
            {fixtures.map((f) => {
              const last = f.readings[f.readings.length - 1];
              const q = QUAD[f.console_quadrant] ?? {
                c: "var(--color-muted)",
                label: f.final_quadrant.toUpperCase(),
              };
              const tooShort = f.readings.length < 3;

              return (
                <tr key={f.key} className="border-b border-line-soft/50">
                  <td className="py-2 pr-3">
                    <span className="flex items-center gap-1.5">
                      <span className="text-ink">{f.label}</span>
                      <InfoTip label={f.label}>
                        {f.note}
                        <br />
                        <br />
                        Package quadrant:{" "}
                        <span className="text-ink">{f.final_quadrant}</span>{" "}
                        (shown here as {q.label.toLowerCase()} to keep one
                        vocabulary on screen). Warm ceiling {f.sim_ceiling} after
                        a {f.preamble_turns}-turn productive preamble.
                      </InfoTip>
                    </span>
                    <span className="mt-0.5 block text-[10px] text-faint">
                      {f.readings.length} turn
                      {f.readings.length === 1 ? "" : "s"}
                    </span>
                  </td>
                  <td className="py-2 pr-3 tabular-nums text-muted">
                    {last.action_sim.toFixed(4)}
                  </td>
                  <td className="py-2 pr-3 tabular-nums">
                    <span
                      style={{
                        color:
                          last.obs_novelty < novelty_floor
                            ? "var(--color-red)"
                            : "var(--color-cyan)",
                      }}
                    >
                      {last.obs_novelty.toFixed(4)}
                    </span>
                  </td>
                  <td className="py-2 pr-3">
                    <span
                      className="rounded-md border px-1.5 py-0.5 text-[9px] tracking-[0.06em]"
                      style={{ color: q.c, borderColor: q.c }}
                    >
                      {q.label}
                    </span>
                  </td>
                  <td className="py-2 tabular-nums">
                    {f.trip_turn !== null ? (
                      <span className="text-red">turn {f.trip_turn}</span>
                    ) : tooShort ? (
                      <span className="text-faint" title="Too short to trip">
                        n/a
                      </span>
                    ) : (
                      <span className="text-faint">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-3 space-y-1.5 border-t border-line-soft pt-3 font-mono text-[10px] leading-relaxed text-faint">
        <p>
          Floor <span className="text-muted">{novelty_floor.toFixed(2)}</span> —{" "}
          {novelty_floor_status.toLowerCase()}. This is the package default; the
          replay above is calibrated to 0.15 for its own trace.
        </p>
        <p>
          <span className="text-muted">n/a</span> means the fixture is two turns
          long and every trip threshold is ≥3, so it{" "}
          <span className="text-muted">cannot</span> trip — that column measures
          trace length, not detector behaviour. Those two fixtures validate
          classification, which they pass.
        </p>
        <p>
          Recall and the parameter sweep are deliberately not shown: they are not
          valid until the short fixtures are replaced with real per-class traces.
        </p>
      </div>
    </GlassPanel>
  );
}
