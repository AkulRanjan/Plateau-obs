import { useState, useEffect, useRef, useMemo, useCallback } from "react";

/* ------------------------------------------------------------------ *
 * Plateau — jury console
 *
 * A self-contained REPLAY of one autonomous-agent run. Every number in
 * TRACE is grounded in the project's metrics.json (paraphrase action-sim
 * 0.89, batch sim 0.99, poller/true-loop novelties 0.23→0.06→0.0, the
 * research-profile calibrated ceiling ~0.55, novelty floor 0.15).
 *
 * SEAM FOR THE LIVE BACKEND: replace TRACE with a stream. Each turn only
 * needs { tool, args, obs, sim, nov, isError }; deriveState() computes the
 * breaker decision (novelty gate / C1) client-side here, but in production
 * the backend owns that call and this view just renders it.
 * ------------------------------------------------------------------ */

const NOVELTY_FLOOR = 0.15;
const WARM_CEILING = 0.55;   // research_open_ended calibrated ceiling
const COLD_CEILING = 0.9;    // conservative default during warmup
const MIN_SAMPLES = 6;       // productive turns before "warm"
const TRIP_STREAK = 3;       // consecutive sub-floor turns that trip the breaker
const TOKENS_PER_TURN = 1850;
const STEP_CAP = 25;         // LangGraph default the run would otherwise reach

const TASK = "Agent task — find how to refresh an expired auth token";

// phase: research | batch | loop
const TRACE = [
  { tool: "search_docs", args: "q='auth token refresh'",            obs: "Auth tokens expire after 3600s.",                    sim: 0.00, nov: 1.00, phase: "research" },
  { tool: "search_docs", args: "q='how do I refresh a token'",      obs: "Refresh requires a client secret and rotates the token.", sim: 0.89, nov: 0.61, phase: "research" },
  { tool: "read_docs",   args: "page='oauth/refresh'",              obs: "POST /oauth/token with grant_type=refresh_token.",   sim: 0.42, nov: 0.72, phase: "research" },
  { tool: "read_config", args: "'/etc/app.yaml'",                   obs: "client_id set; client_secret missing.",              sim: 0.31, nov: 0.83, phase: "research" },
  { tool: "search_docs", args: "q='where is client secret stored'", obs: "Secrets live in the vault under app/oauth.",         sim: 0.55, nov: 0.66, phase: "research" },
  { tool: "vault_get",   args: "'app/oauth/client_secret'",         obs: "PermissionError: access denied to app/oauth.",       sim: 0.28, nov: 0.58, phase: "research", isError: true },
  { tool: "extract_text",args: "'invoice_041.pdf'",                 obs: "ACME Corp, Rs 84,200, due Aug 12",                   sim: 0.19, nov: 0.51, phase: "batch" },
  { tool: "extract_text",args: "'invoice_042.pdf'",                 obs: "Vertex Ltd, Rs 19,750, due Aug 30",                  sim: 0.99, nov: 0.44, phase: "batch" },
  { tool: "extract_text",args: "'invoice_043.pdf'",                 obs: "Nimbus LLC, Rs 51,300, due Sep 05",                  sim: 0.99, nov: 0.41, phase: "batch" },
  { tool: "search_docs", args: "q='vault access denied fix'",       obs: "No results found.",                                  sim: 0.71, nov: 0.23, phase: "loop" },
  { tool: "search_docs", args: "q='how to grant vault permission'", obs: "No results found.",                                  sim: 0.88, nov: 0.06, phase: "loop" },
  { tool: "search_docs", args: "q='oauth secret permission error'", obs: "No results found.",                                  sim: 0.90, nov: 0.00, phase: "loop" },
  { tool: "vault_get",   args: "'app/oauth/client_secret'",         obs: "PermissionError: access denied to app/oauth.",       sim: 0.85, nov: 0.00, phase: "loop", isError: true },
];

const TRIP_TURN = 13;     // 1-indexed — where the 3rd consecutive sub-floor turn lands
const SIM_ONLY_FIRE = 8;  // similarity-only (no C1 gate) false-trips the batch here

// ---- derive live breaker + calibrator state from revealed turns ----------
function deriveState(step) {
  // step = index of last revealed turn, -1 = idle
  let n = 0;                 // productive turns (passed novelty gate)
  let streak = 0;            // trailing consecutive sub-floor turns
  let tripTurn = null;

  const rows = [];
  for (let i = 0; i <= step; i++) {
    const t = TRACE[i];
    const warmBefore = n >= MIN_SAMPLES;
    if (t.nov >= NOVELTY_FLOOR) n += 1;         // C1 gate: only informative turns teach
    const warm = n >= MIN_SAMPLES;
    const ceiling = warm ? WARM_CEILING : COLD_CEILING;

    if (t.nov < NOVELTY_FLOOR) streak += 1; else streak = 0;
    if (warm && streak >= TRIP_STREAK && tripTurn === null) tripTurn = i + 1;

    const quadrant =
      t.nov < NOVELTY_FLOOR
        ? (t.sim >= ceiling ? "stuck" : "thrash")
        : (t.sim >= ceiling ? "batch" : "productive");

    rows.push({ ...t, turn: i + 1, ceiling, warm, quadrant, streak });
  }

  const warm = n >= MIN_SAMPLES;
  const ceiling = warm ? WARM_CEILING : COLD_CEILING;
  const last = rows[rows.length - 1];

  let state = "idle";
  if (step >= 0) {
    if (tripTurn !== null) state = "open";
    else if (!warm) state = "calibrating";
    else if (last && last.nov < NOVELTY_FLOOR) state = "watching";
    else state = "closed";
  }

  return { rows, n, warm, ceiling, state, tripTurn, streak };
}

const ACCENT = {
  idle: "var(--cyan)",
  calibrating: "var(--cyan)",
  closed: "var(--cyan)",
  watching: "var(--amber)",
  open: "var(--red)",
};

const QUAD = {
  productive: { c: "var(--cyan)",   label: "PRODUCTIVE" },
  batch:      { c: "var(--violet)", label: "BATCH" },
  stuck:      { c: "var(--red)",    label: "STUCK" },
  thrash:     { c: "var(--amber)",  label: "THRASH" },
};

const STATE_COPY = {
  idle:        "STANDBY · press run",
  calibrating: "CALIBRATING · learning this agent's normal",
  closed:      "CLOSED · agent is making progress",
  watching:    "WATCHING · novelty falling toward the floor",
  open:        "OPEN · plateau detected — run halted",
};

export default function PlateauConsole() {
  const [step, setStep] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [fast, setFast] = useState(false);
  const [tokens, setTokens] = useState(0);
  const feedRef = useRef(null);

  const S = useMemo(() => deriveState(step), [step]);
  const tripped = S.state === "open";

  // auto-advance
  useEffect(() => {
    if (!playing) return;
    if (step >= TRACE.length - 1) { setPlaying(false); return; }
    const id = setTimeout(() => setStep((s) => s + 1), fast ? 430 : 820);
    return () => clearTimeout(id);
  }, [playing, step, fast]);

  // halt the run the instant the breaker trips — that IS the product
  useEffect(() => { if (tripped) setPlaying(false); }, [tripped]);

  // kick off once on mount so the chat preview animates itself
  useEffect(() => {
    const id = setTimeout(() => { setStep(0); setPlaying(true); }, 650);
    return () => clearTimeout(id);
  }, []);

  // tokens-saved counter animates on trip
  useEffect(() => {
    if (!tripped) { setTokens(0); return; }
    const target = (STEP_CAP - TRIP_TURN) * TOKENS_PER_TURN;
    let raf, t0;
    const tick = (t) => {
      if (!t0) t0 = t;
      const p = Math.min(1, (t - t0) / 1100);
      const eased = 1 - Math.pow(1 - p, 3);
      setTokens(Math.round(target * eased));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [tripped]);

  // keep telemetry pinned to newest turn
  useEffect(() => {
    const el = feedRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [step]);

  const run = useCallback(() => {
    if (step >= TRACE.length - 1) { setStep(0); setPlaying(true); }
    else setPlaying(true);
  }, [step]);
  const reset = useCallback(() => { setPlaying(false); setStep(-1); setTokens(0); }, []);
  const stepOne = useCallback(() => { setPlaying(false); setStep((s) => Math.min(TRACE.length - 1, s + 1)); }, []);

  const accent = ACCENT[S.state] || "var(--cyan)";

  return (
    <div className="pl-root" style={{ ["--accent"]: accent }} data-open={tripped ? "1" : "0"}>
      <style>{CSS}</style>
      <div className="pl-grain" aria-hidden="true" />

      <div className="pl-wrap">
        {/* ---------------- header ---------------- */}
        <header className="pl-head">
          <div className="pl-brand">
            <span className="pl-mark" aria-hidden="true">
              <span className="pl-mark-line" />
              <span className="pl-mark-dot" />
            </span>
            <div>
              <h1 className="pl-title">PLATEAU</h1>
              <p className="pl-tag">A semantic circuit breaker for autonomous agents.</p>
            </div>
          </div>

          <div className={`pl-state pl-state-${S.state}`}>
            <span className="pl-state-led" />
            <span className="pl-state-txt">{STATE_COPY[S.state]}</span>
          </div>
        </header>

        <p className="pl-task">{TASK}</p>

        {/* ---------------- controls ---------------- */}
        <div className="pl-ctl">
          {playing
            ? <button className="pl-btn pl-btn-primary" onClick={() => setPlaying(false)}>Pause</button>
            : <button className="pl-btn pl-btn-primary" onClick={run}>{step >= TRACE.length - 1 ? "Replay" : "Run"}</button>}
          <button className="pl-btn" onClick={stepOne} disabled={tripped || step >= TRACE.length - 1}>Step</button>
          <button className="pl-btn" onClick={reset}>Reset</button>
          <button className={`pl-btn pl-toggle ${fast ? "on" : ""}`} onClick={() => setFast((f) => !f)}>
            {fast ? "2×" : "1×"}
          </button>
          <div className="pl-turnpill">
            <span className="pl-turnpill-k">turn</span>
            <span className="pl-turnpill-v">{step < 0 ? "—" : `${step + 1}`}<span className="pl-turnpill-tot"> / {TRACE.length}</span></span>
          </div>
        </div>

        {/* ---------------- signature: plateau curve ---------------- */}
        <section className="pl-panel pl-hero">
          <div className="pl-hero-copy">
            <div className="pl-eyebrow">signature · information gained per turn, accumulated</div>
            <h2 className="pl-hero-h">The curve tells you when to stop.</h2>
            <p className="pl-hero-p">
              It climbs while the agent learns, then flattens when it stops.
              The breaker trips at the flat — not at the first repeat.
            </p>
            <div className="pl-hero-stats">
              <Stat k="tokens saved" v={tripped ? tokens.toLocaleString() : "—"} accent big />
              <Stat k="tripped at" v={tripped ? `turn ${TRIP_TURN}` : "—"} />
              <Stat k="novelty floor" v={NOVELTY_FLOOR.toFixed(2)} mono />
            </div>
            {tripped && (
              <p className="pl-hero-note">
                est. vs. the run continuing to the step-cap ({STEP_CAP}), {TOKENS_PER_TURN.toLocaleString()} tok/turn
              </p>
            )}
          </div>
          <PlateauCurve rows={S.rows} tripTurn={S.tripTurn} />
        </section>

        {/* ---------------- quadrant map + telemetry ---------------- */}
        <div className="pl-grid2">
          <section className="pl-panel">
            <PanelHead label="semantic space" sub="every turn placed by what it repeats × what it learned" />
            <QuadrantMap rows={S.rows} ceiling={S.ceiling} warm={S.warm} />
            <Legend />
          </section>

          <section className="pl-panel pl-feedpanel">
            <PanelHead label="telemetry" sub="live turn stream" />
            <div className="pl-feed" ref={feedRef}>
              {S.rows.length === 0 && (
                <div className="pl-feed-empty">Press <b>Run</b> to replay the agent trace.</div>
              )}
              {S.rows.map((r) => (
                <TurnRow key={r.turn} r={r} />
              ))}
              {tripped && (
                <div className="pl-halt">
                  <span className="pl-halt-rule" />
                  <span className="pl-halt-txt">run halted by Plateau · {TRACE.length - TRIP_TURN + (STEP_CAP - TRACE.length)} further turns prevented</span>
                  <span className="pl-halt-rule" />
                </div>
              )}
            </div>
          </section>
        </div>

        {/* ---------------- detector race ---------------- */}
        <section className="pl-panel">
          <PanelHead label="detector race" sub="same trace, four detectors — who fired, and were they right" />
          <DetectorRace step={step} tripped={tripped} />
        </section>

        <footer className="pl-foot">
          <span>Replaying a recorded trace. In production, turns stream from the live agent — the breaker decision (the C1 novelty gate) is Plateau's.</span>
          <span className="pl-foot-dim">plateau · v0.1.0</span>
        </footer>
      </div>
    </div>
  );
}

/* ============================ sub-views ============================ */

function Stat({ k, v, accent, big, mono }) {
  return (
    <div className="pl-stat">
      <div className={`pl-stat-v ${big ? "big" : ""} ${mono ? "mono" : ""}`} style={accent ? { color: "var(--accent)" } : null}>{v}</div>
      <div className="pl-stat-k">{k}</div>
    </div>
  );
}

function PanelHead({ label, sub }) {
  return (
    <div className="pl-phead">
      <span className="pl-phead-l">{label}</span>
      <span className="pl-phead-s">{sub}</span>
    </div>
  );
}

function PlateauCurve({ rows, tripTurn }) {
  const W = 560, H = 240, PL = 40, PR = 16, PT = 20, PB = 28;
  const iw = W - PL - PR, ih = H - PT - PB;
  const maxTurn = STEP_CAP;                 // x-axis runs to the step-cap
  const maxCum = 7;                         // headroom above the ~6.05 plateau

  let cum = 0;
  const pts = rows.map((r) => {
    cum += r.nov;
    return { turn: r.turn, cum, x: PL + (iw * (r.turn - 1)) / (maxTurn - 1), y: PT + ih - (ih * cum) / maxCum, q: r.quadrant };
  });

  const line = pts.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const area = pts.length
    ? `${line} L${pts[pts.length - 1].x.toFixed(1)},${(PT + ih).toFixed(1)} L${pts[0].x.toFixed(1)},${(PT + ih).toFixed(1)} Z`
    : "";
  const last = pts[pts.length - 1];
  const flatStart = pts.find((p) => p.turn >= (tripTurn || 99) - 2);

  const gy = [0, 2, 4, 6];

  return (
    <div className="pl-curvewrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="pl-curve" preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="plfill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {gy.map((g) => {
          const y = PT + ih - (ih * g) / maxCum;
          return (
            <g key={g}>
              <line x1={PL} y1={y} x2={W - PR} y2={y} className="pl-grid-l" />
              <text x={PL - 8} y={y + 3} className="pl-axis-t" textAnchor="end">{g}</text>
            </g>
          );
        })}

        {/* step-cap marker — where a blind counter would have stopped */}
        <line x1={PL + iw} y1={PT} x2={PL + iw} y2={PT + ih} className="pl-capline" />
        <text x={PL + iw} y={PT - 6} className="pl-cap-t" textAnchor="end">step-cap {STEP_CAP}</text>

        {area && <path d={area} fill="url(#plfill)" className="pl-area" />}
        {line && <path d={line} className="pl-line" fill="none" />}

        {/* flat-segment emphasis */}
        {flatStart && last && last.turn >= (tripTurn || 99) && (
          <line x1={flatStart.x} y1={flatStart.y} x2={last.x} y2={last.y} className="pl-flat" />
        )}

        {pts.map((p) => (
          <circle key={p.turn} cx={p.x} cy={p.y} r={p.turn === last.turn ? 4.5 : 2.6}
            style={{ fill: QUAD[p.q].c }} className={p.turn === last.turn ? "pl-node pl-node-live" : "pl-node"} />
        ))}

        {tripTurn && last && last.turn >= tripTurn && (
          <g>
            <line x1={last.x} y1={PT} x2={last.x} y2={PT + ih} className="pl-trip-l" />
            <text x={last.x} y={PT + ih + 18} className="pl-trip-t" textAnchor="middle">plateau · trip</text>
          </g>
        )}
      </svg>
    </div>
  );
}

function QuadrantMap({ rows, ceiling, warm }) {
  const SZ = 300, P = 34;
  const iw = SZ - P * 2;
  const xN = (nov) => P + iw * nov;                 // novelty →
  const yS = (sim) => P + iw * (1 - sim);           // similarity ↑
  const fx = xN(NOVELTY_FLOOR);
  const fy = yS(ceiling);

  const corners = [
    { x: P + 6,        y: P + 14,       t: "STUCK",      c: "var(--red)",    a: "start" },
    { x: SZ - P - 6,   y: P + 14,       t: "BATCH",      c: "var(--violet)", a: "end" },
    { x: P + 6,        y: SZ - P - 6,   t: "THRASH",     c: "var(--amber)",  a: "start" },
    { x: SZ - P - 6,   y: SZ - P - 6,   t: "PRODUCTIVE", c: "var(--cyan)",   a: "end" },
  ];

  return (
    <div className="pl-quadwrap">
      <svg viewBox={`0 0 ${SZ} ${SZ}`} className="pl-quad" preserveAspectRatio="xMidYMid meet">
        {/* zone tints */}
        <rect x={P} y={P} width={fx - P} height={fy - P} className="z-stuck" />
        <rect x={fx} y={P} width={SZ - P - fx} height={fy - P} className="z-batch" />
        <rect x={P} y={fy} width={fx - P} height={SZ - P - fy} className="z-thrash" />
        <rect x={fx} y={fy} width={SZ - P - fx} height={SZ - P - fy} className="z-prod" />

        <rect x={P} y={P} width={iw} height={iw} className="pl-quad-frame" />

        {/* dividers */}
        <line x1={fx} y1={P} x2={fx} y2={SZ - P} className={`pl-div ${warm ? "" : "cold"}`} />
        <line x1={P} y1={fy} x2={SZ - P} y2={fy} className={`pl-div ${warm ? "" : "cold"}`} />
        <text x={fx + 4} y={SZ - P + 14} className="pl-div-t">novelty floor {NOVELTY_FLOOR.toFixed(2)}</text>
        <text x={P - 6} y={fy - 4} className="pl-div-t" textAnchor="end">sim ceiling {ceiling.toFixed(2)}</text>

        {corners.map((c) => (
          <text key={c.t} x={c.x} y={c.y} className="pl-corner" style={{ fill: c.c }} textAnchor={c.a}>{c.t}</text>
        ))}

        {/* axis labels */}
        <text x={P + iw / 2} y={SZ - 6} className="pl-axlabel" textAnchor="middle">observation novelty  →  did we learn?</text>
        <text x={12} y={P + iw / 2} className="pl-axlabel" textAnchor="middle" transform={`rotate(-90 12 ${P + iw / 2})`}>action similarity  ↑  same move?</text>

        {rows.map((r, i) => {
          const isLast = i === rows.length - 1;
          return (
            <g key={r.turn} className="pl-dotwrap">
              {isLast && <circle cx={xN(r.nov)} cy={yS(r.sim)} r="11" className="pl-dot-halo" style={{ stroke: QUAD[r.quadrant].c }} />}
              <circle cx={xN(r.nov)} cy={yS(r.sim)} r={isLast ? 5.5 : 3.6}
                className={`pl-dot ${isLast ? "live" : ""}`} style={{ fill: QUAD[r.quadrant].c }} />
              {isLast && <text x={xN(r.nov)} y={yS(r.sim) - 14} className="pl-dot-lab" style={{ fill: QUAD[r.quadrant].c }} textAnchor="middle">turn {r.turn}</text>}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function Legend() {
  return (
    <div className="pl-legend">
      {["stuck", "thrash", "batch", "productive"].map((q) => (
        <span key={q} className="pl-legend-i">
          <span className="pl-legend-sw" style={{ background: QUAD[q].c }} />
          {QUAD[q].label.toLowerCase()}
          <span className="pl-legend-note">
            {q === "stuck" && " · repeats, learns nothing → trip"}
            {q === "thrash" && " · flails, learns nothing → trip"}
            {q === "batch" && " · same tool, new data → keep going"}
            {q === "productive" && " · new move, new info → keep going"}
          </span>
        </span>
      ))}
    </div>
  );
}

function TurnRow({ r }) {
  const q = QUAD[r.quadrant];
  return (
    <div className={`pl-turn q-${r.quadrant}`} style={{ ["--q"]: q.c }}>
      <span className="pl-turn-n">{String(r.turn).padStart(2, "0")}</span>
      <div className="pl-turn-body">
        <div className="pl-turn-call">
          <span className="pl-turn-tool">{r.tool}</span>
          <span className="pl-turn-args">({r.args})</span>
        </div>
        <div className={`pl-turn-obs ${r.isError ? "err" : ""}`}>{r.isError ? "✕ " : "→ "}{r.obs}</div>
      </div>
      <div className="pl-turn-meta">
        <Meter label="sim" v={r.sim} c="var(--muted)" />
        <Meter label="nov" v={r.nov} c={r.nov < NOVELTY_FLOOR ? "var(--red)" : "var(--cyan)"} />
        <span className="pl-turn-quad" style={{ color: q.c, borderColor: q.c }}>{q.label}</span>
      </div>
    </div>
  );
}

function Meter({ label, v, c }) {
  return (
    <span className="pl-meter" title={`${label} ${v.toFixed(2)}`}>
      <span className="pl-meter-k">{label}</span>
      <span className="pl-meter-bar"><span className="pl-meter-fill" style={{ width: `${Math.max(2, v * 100)}%`, background: c }} /></span>
      <span className="pl-meter-v" style={{ color: c }}>{v.toFixed(2)}</span>
    </span>
  );
}

function DetectorRace({ step, tripped }) {
  const cur = step + 1;
  const dets = [
    { name: "Plateau", note: "semantic novelty · C1 gate", fire: TRIP_TURN, kind: "hit",
      verdict: "Tripped at turn 13. Caught the plateau; left the batch running." },
    { name: "Similarity-only", note: "drop C1 — no novelty gate", fire: SIM_ONLY_FIRE, kind: "false",
      verdict: "Tripped at turn 8. False alarm — killed a working batch job." },
    { name: "Exact-args debounce", note: "AWS spec · window 3", fire: null, kind: "miss",
      verdict: "Never tripped. The loop reworded its queries; the keys never repeated." },
    { name: "LangGraph step-cap", note: "counts steps, reads nothing", fire: null, kind: "miss",
      verdict: `Never tripped in-range. Fires blind at a fixed ${STEP_CAP}, regardless of content.` },
  ];

  const AX = STEP_CAP;
  return (
    <div className="pl-race">
      {dets.map((d) => {
        const revealed = d.fire !== null && cur >= d.fire;
        return (
          <div key={d.name} className={`pl-lane k-${d.kind} ${revealed ? "fired" : ""}`}>
            <div className="pl-lane-id">
              <span className="pl-lane-name">{d.name}</span>
              <span className="pl-lane-note">{d.note}</span>
            </div>
            <div className="pl-lane-track">
              <div className="pl-lane-line" />
              {/* progress so far */}
              <div className="pl-lane-prog" style={{ width: `${Math.min(100, (cur / AX) * 100)}%` }} />
              {d.fire !== null ? (
                <div className={`pl-lane-fire ${revealed ? "on" : ""}`} style={{ left: `${((d.fire - 1) / (AX - 1)) * 100}%` }}>
                  <span className="pl-lane-pin" />
                  <span className="pl-lane-firelab">turn {d.fire}</span>
                </div>
              ) : (
                <span className="pl-lane-never">never fires</span>
              )}
            </div>
            <div className="pl-lane-verdict">{revealed || d.fire === null ? d.verdict : <span className="pl-lane-wait">watching…</span>}</div>
          </div>
        );
      })}
      <div className="pl-race-foot">
        <span className="pl-chip hit">Plateau — right on both</span>
        <span className="pl-race-foot-t">the only detector that spared the batch <b>and</b> caught the loop</span>
      </div>
    </div>
  );
}

/* ============================ styles ============================ */
const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

.pl-root{
  --bg:#0A1417; --bg2:#0E1E23; --surface:#11272E; --line:#1C3B44; --line-soft:#16323A;
  --ink:#E6F1F3; --muted:#88A6AF; --faint:#5A7982;
  --cyan:#25E0C8; --violet:#9E86FF; --amber:#F5B23D; --red:#FF5A47;
  position:relative; overflow:hidden; border-radius:18px;
  background:radial-gradient(120% 80% at 50% -10%, #123039 0%, var(--bg) 55%);
  color:var(--ink); font-family:'Space Grotesk',system-ui,sans-serif;
  padding:22px; line-height:1.45;
  box-shadow:0 0 0 1px var(--line-soft), 0 40px 90px -40px #000 inset;
}
.pl-grain{position:absolute; inset:0; pointer-events:none; opacity:.4;
  background-image:linear-gradient(var(--line-soft) 1px,transparent 1px),linear-gradient(90deg,var(--line-soft) 1px,transparent 1px);
  background-size:32px 32px; mask-image:radial-gradient(120% 90% at 50% 0%,#000 30%,transparent 80%);}
.pl-wrap{position:relative; max-width:1120px; margin:0 auto;}
* :focus-visible{outline:2px solid var(--accent); outline-offset:2px; border-radius:4px;}

.pl-head{display:flex; align-items:flex-start; justify-content:space-between; gap:16px; flex-wrap:wrap;}
.pl-brand{display:flex; gap:14px; align-items:center;}
.pl-mark{position:relative; width:30px; height:30px; flex:none;}
.pl-mark-line{position:absolute; left:2px; right:2px; top:50%; height:2px; background:linear-gradient(90deg,transparent,var(--accent) 55%,var(--accent) 62%,var(--faint) 62%);}
.pl-mark-dot{position:absolute; left:60%; top:50%; width:7px; height:7px; margin:-3.5px 0 0 -3.5px; border-radius:50%; background:var(--accent); box-shadow:0 0 12px var(--accent);}
.pl-title{font-size:24px; font-weight:700; letter-spacing:.22em; margin:0;}
.pl-tag{margin:2px 0 0; color:var(--muted); font-size:12.5px; letter-spacing:.02em;}

.pl-state{display:flex; align-items:center; gap:9px; padding:8px 14px; border-radius:999px;
  border:1px solid var(--accent); background:color-mix(in srgb, var(--accent) 10%, transparent);
  font-family:'IBM Plex Mono',monospace; font-size:11.5px; letter-spacing:.06em; color:var(--accent);}
.pl-state-led{width:8px; height:8px; border-radius:50%; background:var(--accent); box-shadow:0 0 10px var(--accent); animation:pulse 1.6s ease-in-out infinite;}
.pl-state-open{animation:alarm .9s steps(2) infinite;}
@keyframes alarm{50%{background:color-mix(in srgb,var(--red) 22%,transparent);}}

.pl-task{font-family:'IBM Plex Mono',monospace; font-size:12px; color:var(--faint); margin:16px 0 12px; letter-spacing:.01em;}

.pl-ctl{display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:16px;}
.pl-btn{font-family:'IBM Plex Mono',monospace; font-size:12px; letter-spacing:.04em; color:var(--ink);
  background:var(--surface); border:1px solid var(--line); padding:8px 15px; border-radius:8px; cursor:pointer; transition:.16s;}
.pl-btn:hover:not(:disabled){border-color:var(--muted); transform:translateY(-1px);}
.pl-btn:disabled{opacity:.35; cursor:not-allowed;}
.pl-btn-primary{background:var(--accent); color:#06171a; border-color:var(--accent); font-weight:600; box-shadow:0 0 20px -6px var(--accent);}
.pl-toggle.on{color:var(--accent); border-color:var(--accent);}
.pl-turnpill{margin-left:auto; display:flex; gap:8px; align-items:baseline; font-family:'IBM Plex Mono',monospace;}
.pl-turnpill-k{font-size:10px; letter-spacing:.14em; color:var(--faint); text-transform:uppercase;}
.pl-turnpill-v{font-size:18px; color:var(--ink); font-weight:500;}
.pl-turnpill-tot{color:var(--faint); font-size:13px;}

.pl-panel{background:linear-gradient(180deg,var(--bg2),#0B1A1F); border:1px solid var(--line-soft); border-radius:14px; padding:18px; margin-bottom:16px;}
.pl-phead{display:flex; align-items:baseline; gap:12px; margin-bottom:14px;}
.pl-phead-l{font-family:'IBM Plex Mono',monospace; font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--accent);}
.pl-phead-s{font-size:12px; color:var(--faint);}

.pl-hero{display:grid; grid-template-columns:minmax(0,0.82fr) minmax(0,1.18fr); gap:22px; align-items:center;}
.pl-eyebrow{font-family:'IBM Plex Mono',monospace; font-size:10.5px; letter-spacing:.14em; text-transform:uppercase; color:var(--faint); margin-bottom:10px;}
.pl-hero-h{font-size:26px; line-height:1.12; font-weight:600; margin:0 0 8px; letter-spacing:-.01em;}
.pl-hero-p{color:var(--muted); font-size:13.5px; margin:0 0 18px; max-width:34ch;}
.pl-hero-stats{display:flex; gap:22px; flex-wrap:wrap;}
.pl-stat-v{font-size:18px; font-weight:600; font-variant-numeric:tabular-nums;}
.pl-stat-v.big{font-size:34px; font-family:'IBM Plex Mono',monospace; letter-spacing:-.02em;}
.pl-stat-v.mono{font-family:'IBM Plex Mono',monospace;}
.pl-stat-k{font-size:10.5px; letter-spacing:.12em; text-transform:uppercase; color:var(--faint); margin-top:3px;}
.pl-hero-note{font-size:11px; color:var(--faint); margin:14px 0 0; font-family:'IBM Plex Mono',monospace;}

.pl-curvewrap{width:100%;}
.pl-curve{width:100%; height:auto; display:block;}
.pl-grid-l{stroke:var(--line-soft); stroke-width:1;}
.pl-axis-t,.pl-cap-t,.pl-trip-t{font-family:'IBM Plex Mono',monospace; font-size:9px; fill:var(--faint);}
.pl-capline{stroke:var(--faint); stroke-width:1; stroke-dasharray:2 4; opacity:.6;}
.pl-line{stroke:var(--accent); stroke-width:2.5; stroke-linejoin:round; stroke-linecap:round; filter:drop-shadow(0 0 6px color-mix(in srgb,var(--accent) 60%,transparent));}
.pl-flat{stroke:var(--red); stroke-width:3; stroke-linecap:round; filter:drop-shadow(0 0 8px var(--red));}
.pl-node{transition:.3s;}
.pl-node-live{filter:drop-shadow(0 0 6px currentColor);}
.pl-trip-l{stroke:var(--red); stroke-width:1.2; stroke-dasharray:3 3; opacity:.8;}
.pl-trip-t{fill:var(--red); font-weight:600;}

.pl-grid2{display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.05fr); gap:16px;}
.pl-quadwrap{width:100%; max-width:340px; margin:0 auto;}
.pl-quad{width:100%; height:auto; display:block;}
.z-stuck{fill:color-mix(in srgb,var(--red) 8%,transparent);}
.z-batch{fill:color-mix(in srgb,var(--violet) 7%,transparent);}
.z-thrash{fill:color-mix(in srgb,var(--amber) 6%,transparent);}
.z-prod{fill:color-mix(in srgb,var(--cyan) 7%,transparent);}
.pl-quad-frame{fill:none; stroke:var(--line); stroke-width:1;}
.pl-div{stroke:var(--muted); stroke-width:1; stroke-dasharray:4 4; opacity:.7;}
.pl-div.cold{opacity:.3;}
.pl-div-t{font-family:'IBM Plex Mono',monospace; font-size:8px; fill:var(--faint);}
.pl-corner{font-family:'IBM Plex Mono',monospace; font-size:9.5px; font-weight:600; letter-spacing:.08em; opacity:.85;}
.pl-axlabel{font-size:8.5px; fill:var(--faint); letter-spacing:.02em;}
.pl-dot{transition:cx .5s cubic-bezier(.2,.7,.2,1), cy .5s cubic-bezier(.2,.7,.2,1);}
.pl-dot.live{filter:drop-shadow(0 0 6px currentColor);}
.pl-dot-halo{fill:none; stroke-width:1.5; opacity:.5; animation:halo 1.8s ease-out infinite;}
.pl-dot-lab{font-family:'IBM Plex Mono',monospace; font-size:8.5px; font-weight:600;}
@keyframes halo{0%{r:7px; opacity:.7;}100%{r:15px; opacity:0;}}

.pl-legend{display:flex; flex-wrap:wrap; gap:6px 16px; margin-top:14px; padding-top:14px; border-top:1px solid var(--line-soft);}
.pl-legend-i{display:inline-flex; align-items:center; gap:7px; font-size:11px; color:var(--muted); font-family:'IBM Plex Mono',monospace;}
.pl-legend-sw{width:9px; height:9px; border-radius:2px; flex:none;}
.pl-legend-note{color:var(--faint);}

.pl-feedpanel{display:flex; flex-direction:column;}
.pl-feed{flex:1; max-height:360px; overflow-y:auto; display:flex; flex-direction:column; gap:7px; padding-right:4px; scroll-behavior:smooth;}
.pl-feed::-webkit-scrollbar{width:6px;} .pl-feed::-webkit-scrollbar-thumb{background:var(--line); border-radius:3px;}
.pl-feed-empty{color:var(--faint); font-size:13px; padding:30px 4px; text-align:center;}
.pl-turn{display:grid; grid-template-columns:26px 1fr auto; gap:10px; padding:9px 11px; border-radius:9px;
  background:var(--surface); border-left:2px solid var(--q); animation:slidein .4s cubic-bezier(.2,.7,.2,1);}
@keyframes slidein{from{opacity:0; transform:translateX(-8px);}to{opacity:1; transform:none;}}
.pl-turn-n{font-family:'IBM Plex Mono',monospace; font-size:11px; color:var(--faint); padding-top:2px;}
.pl-turn-call{font-family:'IBM Plex Mono',monospace; font-size:12px;}
.pl-turn-tool{color:var(--ink); font-weight:500;}
.pl-turn-args{color:var(--faint);}
.pl-turn-obs{font-size:12px; color:var(--muted); margin-top:3px;}
.pl-turn-obs.err{color:var(--red);}
.pl-turn-meta{display:flex; flex-direction:column; gap:4px; align-items:flex-end; min-width:150px;}
.pl-meter{display:flex; align-items:center; gap:6px; font-family:'IBM Plex Mono',monospace; font-size:10px;}
.pl-meter-k{color:var(--faint); width:20px;}
.pl-meter-bar{width:56px; height:4px; border-radius:2px; background:var(--line); overflow:hidden;}
.pl-meter-fill{display:block; height:100%; border-radius:2px; transition:width .5s;}
.pl-meter-v{width:30px; text-align:right;}
.pl-turn-quad{font-family:'IBM Plex Mono',monospace; font-size:9px; letter-spacing:.06em; padding:2px 6px; border:1px solid; border-radius:5px; margin-top:2px;}
.pl-halt{display:flex; align-items:center; gap:10px; margin-top:4px; padding:4px 0;}
.pl-halt-rule{flex:1; height:1px; background:linear-gradient(90deg,transparent,var(--red),transparent);}
.pl-halt-txt{font-family:'IBM Plex Mono',monospace; font-size:10px; color:var(--red); letter-spacing:.04em; white-space:nowrap;}

.pl-race{display:flex; flex-direction:column; gap:10px;}
.pl-lane{display:grid; grid-template-columns:180px 1fr; grid-template-rows:auto auto; gap:6px 16px; padding:12px 14px; border-radius:10px; background:var(--surface); border:1px solid var(--line-soft); transition:.3s;}
.pl-lane.k-hit.fired{border-color:var(--cyan); box-shadow:0 0 24px -12px var(--cyan);}
.pl-lane.k-false.fired{border-color:var(--amber);}
.pl-lane-id{grid-row:1 / span 2; display:flex; flex-direction:column; gap:2px; align-self:center;}
.pl-lane-name{font-size:14px; font-weight:600;}
.pl-lane-note{font-family:'IBM Plex Mono',monospace; font-size:10px; color:var(--faint);}
.pl-lane-track{position:relative; height:20px;}
.pl-lane-line{position:absolute; left:0; right:0; top:50%; height:2px; background:var(--line); border-radius:2px;}
.pl-lane-prog{position:absolute; left:0; top:50%; height:2px; background:var(--faint); border-radius:2px; transform:translateY(-50%); transition:width .4s;}
.pl-lane-fire{position:absolute; top:50%; transform:translate(-50%,-50%); opacity:0; transition:.4s; text-align:center;}
.pl-lane-fire.on{opacity:1;}
.pl-lane-pin{display:block; width:13px; height:13px; border-radius:50%; margin:0 auto;}
.pl-lane-firelab{font-family:'IBM Plex Mono',monospace; font-size:9px; position:absolute; top:15px; left:50%; transform:translateX(-50%); white-space:nowrap;}
.k-hit .pl-lane-pin{background:var(--cyan); box-shadow:0 0 12px var(--cyan);} .k-hit .pl-lane-firelab{color:var(--cyan);}
.k-false .pl-lane-pin{background:var(--amber); box-shadow:0 0 12px var(--amber);} .k-false .pl-lane-firelab{color:var(--amber);}
.pl-lane-never{position:absolute; right:0; top:50%; transform:translateY(-50%); font-family:'IBM Plex Mono',monospace; font-size:10px; color:var(--faint); letter-spacing:.05em;}
.pl-lane-verdict{grid-column:2; font-size:12px; color:var(--muted);}
.k-hit .pl-lane-verdict{color:var(--ink);}
.pl-lane-wait{color:var(--faint);}
.pl-race-foot{display:flex; align-items:center; gap:12px; margin-top:4px; padding-top:12px; border-top:1px solid var(--line-soft); flex-wrap:wrap;}
.pl-chip{font-family:'IBM Plex Mono',monospace; font-size:11px; padding:5px 11px; border-radius:6px; letter-spacing:.03em;}
.pl-chip.hit{background:color-mix(in srgb,var(--cyan) 14%,transparent); color:var(--cyan); border:1px solid var(--cyan);}
.pl-race-foot-t{font-size:12px; color:var(--muted);}

.pl-foot{display:flex; justify-content:space-between; gap:14px; flex-wrap:wrap; font-size:11px; color:var(--faint); font-family:'IBM Plex Mono',monospace; padding-top:4px;}
.pl-foot-dim{opacity:.7;}

@keyframes pulse{0%,100%{opacity:1;}50%{opacity:.4;}}

@media (max-width:820px){
  .pl-hero{grid-template-columns:1fr;} .pl-grid2{grid-template-columns:1fr;}
  .pl-lane{grid-template-columns:1fr;} .pl-lane-id{grid-row:auto;} .pl-lane-verdict{grid-column:1;}
  .pl-quadwrap{max-width:300px;}
}
@media (prefers-reduced-motion:reduce){
  .pl-state-led,.pl-state-open,.pl-dot-halo,.pl-turn{animation:none !important;}
  *{transition:none !important;}
}
`;
