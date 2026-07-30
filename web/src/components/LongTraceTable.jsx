import fixturesDoc from "../data/fixtures.json";
import GlassPanel, { PanelHead } from "./GlassPanel.jsx";
import InfoTip from "./InfoTip.jsx";

const LT = fixturesDoc.long_traces;

/** Our own rows first, then the incumbents, so the comparison reads in order. */
const ORDER = [
  "plateau",
  "plateau_action_only",
  "plateau_novelty_only",
  "lexical",
  "exact_match",
  "exact_args",
  "step_cap_25",
  "step_cap_10007",
];

const LABEL = {
  plateau: "Plateau",
  plateau_action_only: "— ablation: action only",
  plateau_novelty_only: "— ablation: novelty only",
  lexical: "agent-loop-detector",
  exact_match: "OpenHands StuckDetector",
  exact_args: "exact-args debounce",
  step_cap_25: "LangGraph step-cap (25)",
  step_cap_10007: "LangGraph step-cap (10007)",
};

const pct = (n) => (n == null ? "—" : `${(n * 100).toFixed(0)}%`);

/**
 * The measured comparison on full-length traces.
 *
 * This is the panel that decides whether the rest of the page is credible. It is
 * measured with the real encoder over 16-61 turn traces, so turns-to-detection
 * means something — unlike the two-turn fixtures.
 *
 * It is also the panel where we lose. Plateau misses the paraphrase class, which
 * is the exact case it exists for, and it false-trips the healthy poller. The
 * lexical baseline matches its recall with zero false trips. Those rows are
 * rendered with the same weight as the favourable ones, and the contract check
 * fails the build if a later edit removes them.
 */
export default function LongTraceTable() {
  if (!LT) return null;

  const rows = ORDER.filter((k) => LT.detectors[k]).map((k) => ({
    key: k,
    label: LABEL[k] ?? k,
    ...LT.detectors[k],
  }));

  const traceNames = Object.keys(LT.traces);
  const plateau = LT.detectors.plateau;
  const lexical = LT.detectors.lexical;

  return (
    <GlassPanel className="mt-4">
      <PanelHead
        label="measured · long traces"
        sub="16–61 turn classes, real encoder — including the rows that go against us"
        right={
          <span className="font-mono text-[10px] text-faint">
            {traceNames.length} classes · {rows.length} detectors
          </span>
        }
      />

      <div className="overflow-x-auto">
        <table className="w-full min-w-[620px] border-collapse font-mono text-[11px]">
          <thead>
            <tr className="border-b border-line-soft text-left text-faint">
              <th className="pb-2 pr-3 font-normal uppercase tracking-[0.1em]">
                detector
              </th>
              <th className="pb-2 pr-3 font-normal uppercase tracking-[0.1em]">
                recall
              </th>
              <th className="pb-2 pr-3 font-normal uppercase tracking-[0.1em]">
                false-trip
              </th>
              <th className="pb-2 pr-3 font-normal uppercase tracking-[0.1em]">
                turns to detect
              </th>
              <th className="pb-2 font-normal uppercase tracking-[0.1em]">
                missed
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const ours = r.key.startsWith("plateau");
              const isAblation = r.key !== "plateau" && ours;
              return (
                <tr
                  key={r.key}
                  className="border-b border-line-soft/50"
                  style={
                    r.key === "plateau"
                      ? { background: "color-mix(in srgb, var(--color-cyan) 6%, transparent)" }
                      : undefined
                  }
                >
                  <td
                    className={`py-2 pr-3 ${
                      r.key === "plateau"
                        ? "font-semibold text-ink"
                        : isAblation
                          ? "text-faint"
                          : "text-muted"
                    }`}
                  >
                    {r.label}
                  </td>
                  <td className="py-2 pr-3 tabular-nums">
                    <span
                      style={{
                        color:
                          r.recall >= 1
                            ? "var(--color-cyan)"
                            : r.recall > 0
                              ? "var(--color-amber)"
                              : "var(--color-red)",
                      }}
                    >
                      {pct(r.recall)}
                    </span>
                  </td>
                  <td className="py-2 pr-3 tabular-nums">
                    <span
                      style={{
                        color:
                          r.false_trip_rate === 0
                            ? "var(--color-cyan)"
                            : r.false_trip_rate >= 1
                              ? "var(--color-red)"
                              : "var(--color-amber)",
                      }}
                    >
                      {pct(r.false_trip_rate)}
                    </span>
                  </td>
                  <td className="py-2 pr-3 tabular-nums text-muted">
                    {r.mean_turns_to_detection ?? "—"}
                  </td>
                  <td className="py-2 text-[10px] text-faint">
                    {r.missed?.length
                      ? r.missed.map((m) => m.replace(/_/g, " ")).join(", ")
                      : "nothing"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-3 space-y-1.5 border-t border-line-soft pt-3 font-mono text-[10px] leading-relaxed text-faint">
        <p>
          <span className="text-red">No detector achieves recall 100% with
          zero false trips</span>
          {" "}— including ours. {LABEL.lexical} matches Plateau&rsquo;s{" "}
          {pct(lexical?.recall)} recall with a {pct(lexical?.false_trip_rate)}{" "}
          false-trip rate and detects sooner (
          {lexical?.mean_turns_to_detection} turns vs{" "}
          {plateau?.mean_turns_to_detection}).
        </p>
        <p>
          <span className="text-muted">Plateau misses paraphrase loop varied
          wording</span>{" "}
          — the exact case it exists to catch.{" "}
          <InfoTip label="the paraphrase miss">
            Measured novelty between differently-worded non-answers is
            0.4366–1.0112, mean 0.6675. Zero of 11 pairs fall below the 0.30
            floor. MiniLM reads &ldquo;No relevant results found.&rdquo; and
            &ldquo;Nothing matched your query.&rdquo; as new information. They
            are not. This is the same limitation filed as fixture 3b, except it
            is not a corner case — it is the primary demo scenario, so the
            semantic advantage is currently unproven on anything but
            byte-identical observations.
          </InfoTip>
        </p>
        <p>
          Plateau&rsquo;s false trip is{" "}
          <span className="text-muted">healthy poller</span>, the documented
          idempotent case: a poller genuinely is informationally stalled, so no
          threshold separates it from a stuck agent. Polling tools must declare{" "}
          <span className="text-muted">idempotent: true</span>.
        </p>
        <p>
          <span className="text-cyan">The clean measured win:</span>{" "}
          {LABEL.step_cap_25} false-trips the healthy 61-turn invoice batch at
          turn 27 and the action-only ablation false-trips everything at turn 5.
          Plateau holds on both. Exact matching never fires at all.
        </p>
        <p className="text-faint/80">{LT.scope_note}</p>
      </div>
    </GlassPanel>
  );
}
