"""Collector + live dashboard for the two-laptop demo.

Run this on ONE machine (yours). Both agents POST their turns to it, and it
serves a single page showing both runs side by side, live.

    python demo/collector.py --host 0.0.0.0 --port 8080

Then, with <you> being this machine's LAN IP:

    # this laptop
    python demo/live_agent.py --mode plateau   --collector http://<you>:8080
    # your friend's laptop
    python demo/live_agent.py --mode unguarded --collector http://<you>:8080

Deliberately stdlib-only — http.server and json, no flask, no fastapi, nothing
to install on either machine. It holds state in memory; there is no database and
no persistence, because the JSONL each agent writes locally is the real record.

The dashboard polls /state. Polling rather than websockets is a choice: it
survives a laptop sleeping, a wifi blip, and a browser refresh, none of which a
long-lived socket does gracefully, and the demo runs on venue wifi.
"""

from __future__ import annotations

import argparse
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOKENS_PER_TURN = 1850

#: Written on boot so agents on THIS machine need no --collector argument, and
#: so the current LAN URL is discoverable after the wifi hands out a new address.
#: Machine-local, gitignored. It changed three times in one evening.
URL_FILE = Path(__file__).resolve().parent / "collector.url"

_LOCK = threading.Lock()
_STATE: dict[str, dict] = {
    "plateau": {"turns": [], "done": None, "summary": {}},
    "unguarded": {"turns": [], "done": None, "summary": {}},
}


def lan_ip() -> str:
    """Best-effort LAN address, so the script can print the URL to hand out."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:  # noqa: BLE001
        return "127.0.0.1"
    finally:
        s.close()


class Handler(BaseHTTPRequestHandler):
    # Quiet: the terminal is being recorded.
    def log_message(self, *_args) -> None:  # noqa: D102
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/state"):
            with _LOCK:
                body = json.dumps(_STATE).encode()
            self._send(200, body, "application/json")
            return
        if self.path in ("/", "/index.html"):
            self._send(200, DASHBOARD.encode(), "text/html; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, b'{"error":"bad json"}', "application/json")
            return

        mode = payload.get("mode")
        if mode not in _STATE:
            self._send(400, b'{"error":"unknown mode"}', "application/json")
            return

        with _LOCK:
            if self.path.startswith("/turn"):
                _STATE[mode]["turns"].append(payload)
            elif self.path.startswith("/done"):
                _STATE[mode]["done"] = True
                _STATE[mode]["summary"] = payload
            elif self.path.startswith("/reset"):
                _STATE[mode] = {"turns": [], "done": None, "summary": {}}

        self._send(200, b'{"ok":true}', "application/json")


DASHBOARD = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Plateau — recorder</title>
<style>
  /* A two-pen strip-chart recorder.
     Plateau's whole output is two traces against a printed threshold, so the
     page is built as the instrument that would draw them: ivory chart stock,
     engraved legend plates, annunciator lamps, ink. */
  :root{
    --paper:#e6e3da;        /* chart stock */
    --paper-2:#dcd8cc;      /* inset wells */
    --rule:#bdb7a6;         /* printed grid */
    --ink:#1c1b18;          /* plotter ink */
    --ink-soft:#5d594f;
    --ink-faint:#8a8477;
    --pen-a:#1b4b8f;        /* pen 1 — action similarity */
    --pen-b:#0e6f52;        /* pen 2 — observation novelty */
    --signal:#b3221b;       /* threshold, refusals, alarm */
    --amber:#9a6a0c;        /* learned ceiling */
    --display:"Helvetica Neue Condensed","HelveticaNeue-CondensedBold","Arial Narrow",
              "Nimbus Sans Narrow","DejaVu Sans Condensed",system-ui,sans-serif;
    --data:ui-monospace,"SF Mono",Menlo,"Liberation Mono","DejaVu Sans Mono",monospace;
  }
  *{box-sizing:border-box}
  html,body{background:var(--paper)}
  body{margin:0;color:var(--ink);font:13px/1.5 var(--data);
       padding:20px 26px 30px;
       background-image:linear-gradient(var(--rule) .5px,transparent .5px);
       background-size:100% 26px;background-position:0 -1px}

  /* masthead ------------------------------------------------------------ */
  .mast{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;
        border-bottom:1.5px solid var(--ink);padding-bottom:7px;margin-bottom:2px}
  .mast h1{margin:0;font:600 27px/.9 var(--display);letter-spacing:.34em;
           text-transform:uppercase}
  .mast .strap{font:11px/1.3 var(--display);letter-spacing:.13em;
               text-transform:uppercase;color:var(--ink-soft);margin-top:5px}
  .mast .meta{text-align:right;font:10.5px/1.6 var(--data);color:var(--ink-soft);
              white-space:nowrap}
  .mast .meta b{color:var(--ink);font-weight:400}
  .hair{border-bottom:.5px solid var(--ink);margin-bottom:16px}

  /* legend plate — the engraved label used everywhere a section starts --- */
  .plate{font:600 10px/1 var(--display);letter-spacing:.2em;text-transform:uppercase;
         color:var(--ink-soft)}

  /* the recorder -------------------------------------------------------- */
  .recorder{border:1px solid var(--ink);background:var(--paper-2);margin-bottom:16px}
  .rec-head{display:flex;justify-content:space-between;align-items:baseline;
            gap:14px;padding:7px 12px;border-bottom:.5px solid var(--rule);flex-wrap:wrap}
  .pens{display:flex;gap:16px;font:10.5px/1 var(--data);color:var(--ink-soft)}
  .pens i{display:inline-block;width:15px;height:0;border-top-width:2px;
          border-top-style:solid;vertical-align:middle;margin-right:5px}
  .chart{display:block;width:100%;height:168px}
  .rec-foot{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;
            padding:6px 12px;border-top:.5px solid var(--rule);
            font:10.5px/1.5 var(--data);color:var(--ink-soft)}
  .rec-foot b{color:var(--ink);font-weight:400}

  /* two channels -------------------------------------------------------- */
  .channels{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:stretch}
  .channels.solo{grid-template-columns:1fr}
  .channels.solo .ch.idle{display:none}
  /* Fixed height, not min-height: both channels stay the same size and the log
     roll takes whatever is left, so the page never grows past one screen and
     neither channel ends in dead space. */
  .ch{border:1px solid var(--ink);background:var(--paper-2);
      display:flex;flex-direction:column;height:64vh;min-height:420px}
  .ch-head{display:flex;justify-content:space-between;align-items:baseline;gap:10px;
           padding:8px 12px 7px;border-bottom:1px solid var(--ink)}
  .ch-head h2{margin:0;font:600 14px/1 var(--display);letter-spacing:.19em;
              text-transform:uppercase}
  .ch-head .sub{font:10px/1.4 var(--data);color:var(--ink-faint);margin-top:4px}
  .status{font:10px/1 var(--display);letter-spacing:.13em;text-transform:uppercase;
          padding:4px 8px;border:.5px solid var(--ink-soft);color:var(--ink-soft);
          white-space:nowrap}

  /* annunciator lamps --------------------------------------------------- */
  .lamps{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;
         background:var(--rule);border-bottom:1px solid var(--ink)}
  .lamps div{background:var(--paper-2);text-align:center;padding:7px 2px;
             font:600 9px/1.2 var(--display);letter-spacing:.11em;
             text-transform:uppercase;color:var(--ink-faint)}
  .lamps div.lit{background:var(--ink);color:var(--paper)}
  .lamps div.lit.alarm{background:var(--signal);color:#fff}
  .lamps div.lit.hold{background:var(--amber);color:#fff}

  /* counter windows ----------------------------------------------------- */
  .counts{display:grid;grid-template-columns:repeat(2,1fr);gap:1px;background:var(--rule)}
  .counts.four{grid-template-columns:repeat(4,1fr)}
  .cw{background:var(--paper);padding:8px 10px 9px}
  .cw u{display:block;text-decoration:none;font:600 8.5px/1.3 var(--display);
        letter-spacing:.14em;text-transform:uppercase;color:var(--ink-faint)}
  .cw b{display:block;font:400 25px/1.15 var(--data);font-variant-numeric:tabular-nums;
        letter-spacing:-.02em;margin-top:2px}
  .cw b.flag{color:var(--signal)}
  .cw small{display:block;font:10px/1.35 var(--data);color:var(--ink-faint)}

  /* the alarm slip ------------------------------------------------------ */
  .slip{display:none;margin:12px;border-left:3px solid var(--signal);
        background:var(--paper);padding:9px 12px}
  .slip.on{display:block}
  .slip h3{margin:0 0 5px;font:600 10px/1 var(--display);letter-spacing:.19em;
           text-transform:uppercase;color:var(--signal)}
  .slip p{margin:0;font:11px/1.6 var(--data);white-space:pre-wrap}
  .slip p+p{margin-top:6px;color:var(--amber)}

  /* the log roll -------------------------------------------------------- */
  .roll{flex:1;overflow-y:auto;min-height:0;padding:2px 12px 10px}
  .r{display:grid;grid-template-columns:22px 1fr;gap:9px;padding:5px 0;
     border-bottom:.5px solid var(--rule);font:11px/1.5 var(--data)}
  .r.pre{color:var(--ink-faint)}
  .r .idx{color:var(--ink-faint);text-align:right;font-variant-numeric:tabular-nums}
  .r .obs{color:var(--ink-soft)}
  .r .note{color:var(--signal);margin-top:2px}
  .r.cut .act{color:var(--signal)}
  .dial{color:var(--ink-faint)}
  .q-loop,.q-thrash{color:var(--signal)}
  .q-grind{color:var(--amber)}
  .q-explore{color:var(--pen-b)}
  .ch-foot{border-top:1px solid var(--ink);padding:7px 12px;
           font:10.5px/1.5 var(--data);color:var(--ink-soft)}
  .idlemsg{padding:30px 12px;text-align:center;color:var(--ink-faint);
           font:11px/1.6 var(--data)}
  .fine{margin-top:16px;border-top:.5px solid var(--ink);padding-top:8px;
        font:10.5px/1.65 var(--data);color:var(--ink-soft);max-width:112ch}

  @media (max-width:900px){
    .channels{grid-template-columns:1fr}
    .ch{height:auto;min-height:0}
    .roll{max-height:48vh}
    .counts.four{grid-template-columns:repeat(2,1fr)}
    .mast{flex-direction:column;align-items:flex-start}
    .mast .meta{text-align:left}
  }
  @media (prefers-reduced-motion:no-preference){
    .lamps div.lit.alarm{animation:lamp 1.9s ease-in-out infinite}
    @keyframes lamp{0%,100%{opacity:1}50%{opacity:.72}}
  }
</style>

<div class="mast">
  <div>
    <h1>Plateau</h1>
    <div class="strap">Circuit breaker for agents that stop making progress</div>
  </div>
  <div class="meta">
    <div>task &nbsp;<b id="m-task">—</b></div>
    <div>chart &nbsp;<b id="m-model">awaiting the guarded agent</b></div>
  </div>
</div>
<div class="hair"></div>

<div class="recorder">
  <div class="rec-head">
    <span class="plate">Recorder — with plateau</span>
    <div class="pens">
      <span><i style="border-color:var(--pen-a)"></i>action sim</span>
      <span><i style="border-color:var(--pen-b)"></i>obs novelty</span>
      <span><i style="border-color:var(--amber);border-top-style:dashed"></i>learned ceiling</span>
      <span><i style="border-color:var(--signal);border-top-style:dashed"></i>novelty floor</span>
    </div>
  </div>
  <svg class="chart" id="chart" preserveAspectRatio="none" viewBox="0 0 1000 168"></svg>
  <div class="rec-foot">
    <span id="rec-cal">Calibrating.</span>
    <span id="rec-quads"></span>
  </div>
</div>

<div class="channels" id="channels">
  <section class="ch idle" id="ch-unguarded">
    <div class="ch-head">
      <div><h2>Unguarded</h2><div class="sub" id="u-sub">no agent connected</div></div>
      <span class="status" id="u-status">standby</span>
    </div>
    <div class="counts" id="u-counts"></div>
    <div class="roll" id="u-roll"><div class="idlemsg">Waiting for the unguarded agent.</div></div>
    <div class="ch-foot" id="u-foot">Every call returns 200 OK. Nothing here is an error.</div>
  </section>

  <section class="ch idle" id="ch-plateau">
    <div class="ch-head">
      <div><h2>With Plateau</h2><div class="sub" id="p-sub">no agent connected</div></div>
      <span class="status" id="p-status">standby</span>
    </div>
    <div class="lamps" id="lamps">
      <div data-s="CALIBRATING">Calibrating</div><div data-s="CLOSED">Closed</div>
      <div data-s="OPEN">Open</div><div data-s="HALF_OPEN">Half_Open</div>
    </div>
    <div class="counts four" id="p-counts"></div>
    <div class="slip" id="slip">
      <h3>Breaker open</h3>
      <p id="slip-why"></p>
      <p id="slip-esc"></p>
    </div>
    <div class="roll" id="p-roll"><div class="idlemsg">Waiting for the guarded agent.</div></div>
    <div class="ch-foot" id="p-foot">Reading both halves of every turn.</div>
  </section>
</div>

<div class="fine">
  Turns and encoder calls are counted. Token figures are ILLUSTRATIVE — arithmetic over an
  assumed 1,850 per turn, not measured. Novelty collapses because the loop's non-answer is a
  constant string. The two agents run on different machines, so their trajectories are not
  expected to match turn for turn; compare the digests before reading anything into a
  difference.
</div>

<script>
const esc = s => (s||"").replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const num = n => (n==null ? '—' : n.toLocaleString());

/* Turns spent inside a stall: from the first run of three identical
   observations to the end of what that agent executed. This is the honest
   comparison — tokens dilute it, because a guarded agent spends its freed
   turns doing real work rather than not spending them. */
function stallSpan(turns){
  const ran = turns.filter(t => t.executed !== false && t.observation);
  for(let i=2;i<ran.length;i++){
    if(ran[i].observation===ran[i-1].observation && ran[i-1].observation===ran[i-2].observation){
      return {from: ran[i-2].n, spent: ran.length-(i-2)};
    }
  }
  return {from:null, spent:0};
}

function counter(label, value, sub, flag){
  return `<div class="cw"><u>${label}</u><b${flag?' class="flag"':''}>${value}</b>`+
         `<small>${sub||''}</small></div>`;
}

/* ---- the recorder ------------------------------------------------------ */
function drawChart(turns){
  const W=1000, H=168, L=8, R=64, T=10, B=26;
  const svg=document.getElementById('chart');
  if(!turns.length){ svg.innerHTML=''; return; }
  const n=turns.length;
  const x=i => L + (n<2 ? (W-L-R)/2 : (i/(n-1))*(W-L-R));
  const y=v => T + (1-Math.max(0,Math.min(1,v)))*(H-T-B);
  const last=turns[turns.length-1];
  const floor = last.novelty_floor!=null ? last.novelty_floor : 0.30;
  const ceiling = last.sim_ceiling;
  let o='';

  /* printed grid: the paper, before any ink */
  for(const v of [0,0.25,0.5,0.75,1]){
    o+=`<line x1="${L}" y1="${y(v)}" x2="${W-R}" y2="${y(v)}" stroke="var(--rule)" stroke-width=".5"/>`;
    o+=`<text x="${W-R+6}" y="${y(v)+3}" fill="var(--ink-faint)" font-size="9"
        font-family="var(--data)">${v.toFixed(2)}</text>`;
  }
  for(let i=0;i<n;i++){
    if(turns[i].n%5) continue;
    o+=`<line x1="${x(i)}" y1="${T}" x2="${x(i)}" y2="${H-B}" stroke="var(--rule)" stroke-width=".5"/>`;
    o+=`<text x="${x(i)}" y="${H-B+13}" fill="var(--ink-faint)" font-size="9"
        text-anchor="middle" font-family="var(--data)">${turns[i].n}</text>`;
  }

  /* the thresholds, printed on the stock rather than drawn by a pen */
  /* Threshold captions sit inside the plot at the left, clear of the axis
     numbers on the right — the two collided when both lived in the margin. */
  if(ceiling!=null){
    o+=`<line x1="${L}" y1="${y(ceiling)}" x2="${W-R}" y2="${y(ceiling)}"
        stroke="var(--amber)" stroke-width="1" stroke-dasharray="7 4"/>`;
    o+=`<text x="${W-R-6}" y="${y(ceiling)-5}" fill="var(--amber)" font-size="9"
        text-anchor="end" font-family="var(--data)">ceiling ${ceiling.toFixed(3)}</text>`;
  }
  o+=`<line x1="${L}" y1="${y(floor)}" x2="${W-R}" y2="${y(floor)}"
      stroke="var(--signal)" stroke-width="1.25" stroke-dasharray="7 4"/>`;
  o+=`<text x="${W-R-6}" y="${y(floor)+12}" fill="var(--signal)" font-size="9"
      text-anchor="end" font-family="var(--data)">floor ${floor.toFixed(2)}</text>`;

  /* two pens */
  for(const pen of [{k:'action_sim',c:'var(--pen-a)'},{k:'obs_novelty',c:'var(--pen-b)'}]){
    let run=[];
    const flush=()=>{ if(run.length>1) o+=`<polyline points="${run.join(' ')}" fill="none"
        stroke="${pen.c}" stroke-width="1.6" stroke-linejoin="round"/>`; run=[]; };
    for(let i=0;i<n;i++){
      const v=turns[i][pen.k];
      if(v==null){ flush(); continue; }
      run.push(`${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    }
    flush();
  }

  /* refusals print as a hatch on the bottom margin — work that never happened */
  for(let i=0;i<n;i++){
    if(turns[i].executed!==false) continue;
    o+=`<line x1="${x(i)}" y1="${H-B+1}" x2="${x(i)}" y2="${H-B+7}"
        stroke="var(--signal)" stroke-width="2"/>`;
  }
  /* and the trip is stamped where it happened */
  const trip=turns.findIndex(t => t.allowed===false);
  if(trip>=0){
    o+=`<line x1="${x(trip)}" y1="${T}" x2="${x(trip)}" y2="${H-B}"
        stroke="var(--signal)" stroke-width="1"/>`;
    /* Set along the line, the way an annotation is written on a chart roll.
       Horizontal, it landed on top of whichever trace was pinned at 1.0. */
    o+=`<text x="${x(trip)-4}" y="${H-B-4}" fill="var(--signal)" font-size="9.5"
        font-family="var(--data)" transform="rotate(-90 ${x(trip)-4} ${H-B-4})"
        >breaker open · turn ${turns[trip].n}</text>`;
  }
  svg.innerHTML=o;
}

/* ---- channels ---------------------------------------------------------- */
function renderUnguarded(d){
  const turns=d.turns||[];
  if(!turns.length) return;
  document.getElementById('ch-unguarded').classList.remove('idle');
  const ran=turns.filter(t=>t.executed!==false).length;
  const stall=stallSpan(turns);
  const last=turns[turns.length-1];

  document.getElementById('u-sub').textContent =
    `${last.model||'model unknown'}${last.digest?' · digest '+last.digest:''}`;
  document.getElementById('u-status').textContent =
    d.done ? (d.summary['ended because']||'finished') : 'running';
  document.getElementById('u-counts').innerHTML =
    counter('Turns run', ran, 'nothing stopped it') +
    counter('Spent stalled', stall.spent,
            stall.from ? `repeating since turn ${stall.from}` : 'no repeat yet', stall.spent>0) +
    counter('Tokens', num(ran*1850), 'illustrative') +
    counter('Refused', 0, 'no breaker attached');
  document.getElementById('u-counts').classList.add('four');
  document.getElementById('u-roll').innerHTML = turns.map(logRow).join('');
  scroll('u-roll');
  if(d.done) document.getElementById('u-foot').textContent =
    `${d.summary['turns executed']} turns · never tripped · ${d.summary['ended because']}`;
}

function renderPlateau(d){
  const turns=d.turns||[];
  if(!turns.length) return;
  document.getElementById('ch-plateau').classList.remove('idle');
  const ran=turns.filter(t=>t.executed!==false).length;
  const refused=turns.filter(t=>t.executed===false).length;
  const stall=stallSpan(turns);
  const last=turns[turns.length-1];
  const encoder=d.summary['encoder calls'];

  document.getElementById('m-task').textContent='refresh an expired auth token';
  document.getElementById('m-model').textContent=
    `${last.model||''}${last.digest?' · digest '+last.digest:''}`;
  document.getElementById('p-sub').textContent=
    `${last.model||'model unknown'}${last.digest?' · digest '+last.digest:''}`;
  document.getElementById('p-status').textContent =
    d.done ? (d.summary['ended because']||'finished') : last.state.toLowerCase();

  for(const lamp of document.querySelectorAll('#lamps div')){
    lamp.className = lamp.dataset.s===last.state
      ? 'lit '+(last.state==='OPEN'?'alarm':last.state==='HALF_OPEN'?'hold':'')
      : '';
  }

  document.getElementById('p-counts').innerHTML =
    counter('Turns run', ran, 'the ones that cost money') +
    counter('Refused', refused, 'never reached a tool', refused>0) +
    counter('Spent stalled', stall.spent,
            stall.from ? `repeating since turn ${stall.from}` : 'no repeat yet') +
    counter('Encoder calls', encoder!=null?encoder:'—',
            encoder!=null?'none on refused turns':'reported at end');

  drawChart(turns);
  if(last.calibrated_n!=null){
    const warm=last.calibrated_n>=last.min_samples;
    document.getElementById('rec-cal').innerHTML = warm
      ? `Calibrated on <b>${last.calibrated_n}</b> productive turns · ceiling <b>${last.sim_ceiling.toFixed(3)}</b> · floor <b>${(last.novelty_floor).toFixed(2)}</b>`
      : `Calibrating — <b>${last.calibrated_n} of ${last.min_samples}</b> productive turns. The breaker cannot arm yet.`;
  }
  const q={}; for(const t of turns) if(t.quadrant) q[t.quadrant]=(q[t.quadrant]||0)+1;
  document.getElementById('rec-quads').innerHTML =
    ['explore','grind','loop','thrash'].map(k=>`${k} <b>${q[k]||0}</b>`).join(' · ');

  const cut=turns.filter(t=>t.allowed===false&&t.message).slice(-1)[0];
  const slip=document.getElementById('slip');
  if(cut){
    slip.classList.add('on');
    const parts=cut.message.split('Escape:');
    document.getElementById('slip-why').textContent=parts[0].trim();
    document.getElementById('slip-esc').textContent=parts[1]?'Escape: '+parts[1].trim():'';
  } else slip.classList.remove('on');

  document.getElementById('p-roll').innerHTML=turns.map(logRow).join('');
  scroll('p-roll');
  if(d.done) document.getElementById('p-foot').textContent =
    `${d.summary['turns executed']} run, ${d.summary['turns refused']} refused · ` +
    `opened at turn ${d.summary['tripped at turn']} · ${d.summary['ended because']}`;
}

function logRow(t){
  const pre = t.phase==='survey' ? ' pre' : '';
  if(t.executed===false){
    return `<div class="r cut${pre}"><span class="idx">${t.n}</span><span>
      <span class="act">refused &nbsp;${esc(t.action)}</span>
      <div class="note">${esc(t.reason)}</div></span></div>`;
  }
  const dial = t.action_sim!=null
    ? `<span class="dial"> &nbsp;sim ${t.action_sim.toFixed(2)} &nbsp;nov ${t.obs_novelty.toFixed(2)} &nbsp;<span class="q-${t.quadrant||''}">${t.quadrant||''}</span></span>` : '';
  const note = (t.allowed===false && t.reason)
    ? `<div class="note">${esc(t.reason)}</div>` : '';
  return `<div class="r${pre}"><span class="idx">${t.n}</span><span>${esc(t.action)}${dial}
    <div class="obs">${esc((t.observation||'').split('\\n')[0].slice(0,108))}</div>${note}</span></div>`;
}

function scroll(id){const e=document.getElementById(id);e.scrollTop=e.scrollHeight;}

async function tick(){
  try{
    const r=await fetch('/state',{cache:'no-store'});
    const s=await r.json();
    renderUnguarded(s.unguarded); renderPlateau(s.plateau);
    const live=['unguarded','plateau'].filter(m=>(s[m].turns||[]).length).length;
    document.getElementById('channels').classList.toggle('solo',live===1);
  }catch(e){}
  setTimeout(tick,700);
}
tick();
</script>
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8080)
    a = p.parse_args()

    ip = lan_ip()
    url = f"http://{ip}:{a.port}"

    # Publish it. An agent on this machine can then omit --collector entirely,
    # and anyone can cat the file to get the address to hand to the other laptop.
    try:
        URL_FILE.write_text(url + "\n", encoding="utf-8")
        published = f"  published : {URL_FILE.name} (agents here can omit --collector)"
    except OSError as exc:
        published = f"  published : FAILED to write {URL_FILE.name}: {exc}"

    print(f"\n{'=' * 72}")
    print("  Plateau collector + dashboard")
    print(f"  dashboard : {url}/   (open this, record this)")
    print(f"  agents    : --collector {url}")
    print(published)
    print(f"  NOTE      : this IP changes when the wifi reassigns it. If an agent")
    print(f"              cannot post, re-read this banner before blaming the code.")
    print(f"{'=' * 72}\n")

    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
