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
<title>Plateau — two agents, one task</title>
<style>
  :root{--bg:#0a1417;--panel:#0f2228;--sunk:#0b1b20;--line:#1c3b44;--ink:#e6f1f3;
        --muted:#88a6af;--faint:#7b949b;--cyan:#25e0c8;--red:#ff5a47;--amber:#f5b23d;
        --violet:#9d7cf4;--mono:ui-monospace,SFMono-Regular,Menlo,monospace}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:14px/1.45 ui-sans-serif,system-ui,sans-serif;padding:18px 22px 26px}
  h1{font-size:19px;letter-spacing:.2em;margin:0 0 2px}
  .sub{color:var(--muted);font-size:12.5px}
  .bar{display:flex;gap:18px;align-items:baseline;flex-wrap:wrap;
       margin:12px 0 14px;padding:9px 12px;background:var(--sunk);
       border:1px solid var(--line);border-radius:10px;font:11.5px/1.4 var(--mono)}
  .bar b{color:var(--muted);font-weight:400;letter-spacing:.08em}
  .bar span{color:var(--ink)}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  .grid.solo{grid-template-columns:1fr}
  .grid.solo .pane.empty{display:none}
  .pane{background:var(--panel);border:1px solid var(--line);border-radius:12px;
        padding:14px;display:flex;flex-direction:column;min-height:72vh}
  .head{display:flex;justify-content:space-between;align-items:baseline;
        font:600 12px/1 var(--mono);letter-spacing:.14em;margin-bottom:9px}
  .pill{font:11px var(--mono);padding:3px 9px;border-radius:99px;border:1px solid}
  .machine{font:10.5px var(--mono);color:var(--faint);margin:-4px 0 9px;
           white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  /* state machine strip */
  .fsm{display:flex;gap:4px;margin-bottom:10px}
  .fsm div{flex:1;text-align:center;font:10px/1 var(--mono);letter-spacing:.06em;
           padding:6px 2px;border-radius:5px;border:1px solid var(--line);
           color:var(--faint);background:var(--sunk)}
  .fsm div.on{color:var(--bg);font-weight:700}
  .fsm div.on.calm{background:var(--cyan);border-color:var(--cyan)}
  .fsm div.on.hot{background:var(--red);border-color:var(--red)}
  .fsm div.on.warm{background:var(--amber);border-color:var(--amber)}
  /* counters */
  .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin-bottom:10px}
  .stat{background:var(--sunk);border:1px solid var(--line);border-radius:8px;padding:7px 8px}
  .stat u{display:block;text-decoration:none;color:var(--faint);
          font:9.5px/1.3 var(--mono);letter-spacing:.09em}
  .stat b{display:block;font:600 19px/1.25 var(--mono);font-variant-numeric:tabular-nums}
  .stat small{display:block;color:var(--faint);font:10px/1.35 var(--mono)}
  /* dials */
  .dialwrap{background:var(--sunk);border:1px solid var(--line);border-radius:8px;
            padding:8px 9px 4px;margin-bottom:10px}
  .dialrow{display:flex;align-items:center;gap:8px;margin-bottom:3px}
  .dialrow em{font:9.5px var(--mono);color:var(--faint);font-style:normal;
              letter-spacing:.08em;width:74px;flex:none}
  .dialrow svg{flex:1;height:34px;display:block}
  .warm{font:10px var(--mono);color:var(--faint);margin-top:2px}
  .warmbar{height:3px;background:#16323a;border-radius:2px;overflow:hidden;margin-top:3px}
  .warmbar i{display:block;height:100%;background:var(--cyan)}
  /* quadrants */
  .quads{display:flex;gap:5px;margin-bottom:10px;font:10px var(--mono)}
  .quads span{flex:1;text-align:center;padding:4px 2px;border-radius:5px;
              background:var(--sunk);border:1px solid var(--line);color:var(--faint)}
  .quads span b{display:block;font-size:13px;color:var(--ink);
                font-variant-numeric:tabular-nums}
  /* feed */
  /* Bounded, so a long run cannot push the trip card off the bottom of a
     screen that is being recorded. The feed scrolls itself instead. */
  .feed{flex:1;overflow-y:auto;min-height:110px;max-height:34vh;
        font:11.5px/1.5 var(--mono)}
  .t{display:grid;grid-template-columns:26px 1fr;gap:8px;padding:4px 0;
     border-bottom:1px solid #16323a}
  .t.survey{opacity:.72}
  .n{color:var(--faint)}
  .obs{color:var(--muted)}
  .dials{color:var(--faint);font-size:10.5px}
  .q-loop,.q-thrash{color:var(--red)}
  .q-grind{color:var(--amber)}
  .q-explore{color:var(--cyan)}
  .refused{color:var(--red)}
  .msg{color:var(--amber);font-size:10.5px;white-space:pre-wrap;margin-top:3px}
  .foot{margin-top:10px;padding-top:9px;border-top:1px solid var(--line);
        color:var(--muted);font-size:11.5px}
  .waiting{color:var(--faint);padding:26px 0;text-align:center}
  /* trip card */
  .trip{margin:0 0 10px;border:1px solid var(--red);border-left-width:4px;
        border-radius:10px;background:#1a1013;padding:11px 13px;display:none}
  .trip.on{display:block}
  .trip h2{margin:0 0 6px;font:600 12px/1 var(--mono);letter-spacing:.14em;color:var(--red)}
  .trip .why{font:11.5px/1.55 var(--mono);color:var(--ink);white-space:pre-wrap}
  .trip .esc{margin-top:7px;font:11.5px/1.5 var(--mono);color:var(--amber)}
  .note{color:var(--faint);font-size:11.5px;margin-top:14px;line-height:1.5}
</style>
<h1>PLATEAU</h1>
<div class="sub">Two agents. Same task, same tools. One has a circuit breaker.</div>

<div class="bar">
  <span><b>TASK</b> <span id="b-task">—</span></span>
  <span><b>UNGUARDED</b> <span id="b-u">waiting</span></span>
  <span><b>GUARDED</b> <span id="b-p">waiting</span></span>
  <span><b>FLOOR</b> <span id="b-floor">—</span></span>
</div>

<div class="grid" id="grid">
  <div class="pane empty" id="pane-unguarded">
    <div class="head"><span style="color:var(--red)">UNGUARDED</span>
      <span id="s-unguarded" class="pill" style="border-color:var(--red);color:var(--red)">waiting</span></div>
    <div class="machine" id="m-unguarded">no agent connected</div>
    <div class="stats" id="k-unguarded"></div>
    <div class="feed" id="f-unguarded"><div class="waiting">waiting for the agent…</div></div>
    <div class="foot" id="x-unguarded">Every call returns 200 OK. No dashboard has anything to alarm on.</div>
  </div>

  <div class="pane empty" id="pane-plateau">
    <div class="head"><span style="color:var(--cyan)">WITH PLATEAU</span>
      <span id="s-plateau" class="pill" style="border-color:var(--cyan);color:var(--cyan)">waiting</span></div>
    <div class="machine" id="m-plateau">no agent connected</div>
    <div class="fsm" id="fsm">
      <div data-s="CALIBRATING">CALIBRATING</div><div data-s="CLOSED">CLOSED</div>
      <div data-s="OPEN">OPEN</div><div data-s="HALF_OPEN">HALF_OPEN</div>
    </div>
    <div class="stats" id="k-plateau"></div>
    <div class="dialwrap" id="dials">
      <div class="dialrow"><em>action sim</em><svg id="sv-sim" viewBox="0 0 300 34" preserveAspectRatio="none"></svg></div>
      <div class="dialrow"><em>obs novelty</em><svg id="sv-nov" viewBox="0 0 300 34" preserveAspectRatio="none"></svg></div>
      <div class="warm" id="warmtext"></div>
      <div class="warmbar" id="warmbar"><i id="warmfill" style="width:0%"></i></div>
    </div>
    <div class="quads" id="quads"></div>
    <div class="trip" id="trip">
      <h2>BREAKER OPEN</h2>
      <div class="why" id="trip-why"></div>
      <div class="esc" id="trip-esc"></div>
    </div>
    <div class="feed" id="f-plateau"><div class="waiting">waiting for the agent…</div></div>
    <div class="foot" id="x-plateau">Watching both halves of every turn.</div>
  </div>
</div>

<div class="note">
  Token figures are ILLUSTRATIVE: turns are measured, tokens are arithmetic over an
  assumed 1,850/turn. Encoder calls are counted, not assumed. Plateau trips on
  observation novelty; the loop's non-answer is a constant string, which is what
  makes novelty collapse. The two agents run on different machines, so their
  trajectories are not expected to match turn for turn — compare the digests above.
</div>

<script>
const esc = s => (s||"").replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const num = n => (n==null ? '—' : n.toLocaleString());
const FLOOR_DEFAULT = 0.30;

function statCard(label, value, sub){
  return `<div class="stat"><u>${label}</u><b>${value}</b>${sub?`<small>${sub}</small>`:''}</div>`;
}

/* A sparkline over one dial, with reference lines drawn from the values the
   agent posted rather than from constants duplicated here. */
function spark(svg, series, refs, colour){
  const W=300, H=34, n=series.length;
  if(!n){ svg.innerHTML=''; return; }
  const x = i => n<2 ? W/2 : (i/(n-1))*W;
  const y = v => H - 2 - Math.max(0, Math.min(1, v))*(H-4);
  let out='';
  for(const r of refs){
    if(r.v==null) continue;
    out += `<line x1="0" y1="${y(r.v).toFixed(1)}" x2="${W}" y2="${y(r.v).toFixed(1)}"
            stroke="${r.c}" stroke-width="1" stroke-dasharray="3 3" opacity=".65"></line>`;
  }
  const pts = series.map((v,i)=> v==null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
  let run=[];
  for(const p of pts.concat([null])){
    if(p){ run.push(p); }
    else { if(run.length>1) out += `<polyline points="${run.join(' ')}" fill="none"
             stroke="${colour}" stroke-width="1.6"></polyline>`;
           else if(run.length===1) out += `<circle cx="${run[0].split(',')[0]}"
             cy="${run[0].split(',')[1]}" r="1.6" fill="${colour}"></circle>`;
           run=[]; }
  }
  const last = series.filter(v=>v!=null).slice(-1)[0];
  if(last!=null){
    const li = series.length-1;
    out += `<circle cx="${x(li).toFixed(1)}" cy="${y(last).toFixed(1)}" r="2.4" fill="${colour}"></circle>`;
  }
  svg.innerHTML = out;
}

function renderUnguarded(d){
  const turns = d.turns||[];
  const pane = document.getElementById('pane-unguarded');
  if(!turns.length) return;
  pane.classList.remove('empty');
  const executed = turns.filter(t => t.executed !== false).length;
  document.getElementById('k-unguarded').innerHTML =
    statCard('TURNS EXECUTED', executed, 'nothing stopped it') +
    statCard('TURNS REFUSED', 0, 'no guard attached') +
    statCard('TOKENS (EST)', num(executed*1850), 'illustrative') +
    statCard('STALLED SINCE', firstStall(turns) ?? '—', 'same observation repeating');
  const last = turns[turns.length-1];
  document.getElementById('s-unguarded').textContent =
    d.done ? 'finished · '+(d.summary['ended because']||'') : 'running';
  document.getElementById('b-u').textContent =
    d.done ? `${executed} turns, never tripped` : `${executed} turns, running`;
  document.getElementById('m-unguarded').textContent =
    `${last.model||''} ${last.digest? '· digest '+last.digest : ''}`.trim() || 'agent connected';
  document.getElementById('f-unguarded').innerHTML = turns.map(row).join('');
  scrollFeed('f-unguarded');
  if(d.done && d.summary) document.getElementById('x-unguarded').textContent =
    `${d.summary['turns executed']} turns executed · tripped at turn ${d.summary['tripped at turn']} · ${d.summary['ended because']}`;
}

/* The turn at which the observation stopped changing. Computed, not assumed. */
function firstStall(turns){
  for(let i=2;i<turns.length;i++){
    if(turns[i].observation && turns[i].observation===turns[i-1].observation
       && turns[i-1].observation===turns[i-2].observation) return turns[i-2].n;
  }
  return null;
}

function renderPlateau(d){
  const turns = d.turns||[];
  const pane = document.getElementById('pane-plateau');
  if(!turns.length) return;
  pane.classList.remove('empty');
  const executed = turns.filter(t => t.executed !== false).length;
  const refused  = turns.filter(t => t.executed === false).length;
  const judged   = turns.filter(t => t.allowed === false && t.executed !== false);
  const last     = turns[turns.length-1];
  const encoder  = d.summary['encoder calls'];

  document.getElementById('s-plateau').textContent =
    d.done ? 'finished · '+(d.summary['ended because']||'') : (last.state||'running');
  document.getElementById('b-p').textContent = d.done
    ? `${executed} executed, ${refused} refused, tripped at ${d.summary['tripped at turn']}`
    : `${executed} executed, ${refused} refused, ${last.state}`;
  document.getElementById('b-task').textContent = 'refresh the expired auth token';
  document.getElementById('m-plateau').textContent =
    `${last.model||''} ${last.digest? '· digest '+last.digest : ''}`.trim() || 'agent connected';
  if(last.novelty_floor!=null)
    document.getElementById('b-floor').textContent = last.novelty_floor.toFixed(2)+' novelty';

  /* state machine */
  for(const cell of document.querySelectorAll('#fsm div')){
    const on = cell.dataset.s === last.state;
    cell.className = on ? 'on '+(last.state==='OPEN'?'hot':last.state==='HALF_OPEN'?'warm':'calm') : '';
  }

  document.getElementById('k-plateau').innerHTML =
    statCard('TURNS EXECUTED', executed, 'the ones that cost money') +
    statCard('TURNS REFUSED', refused, 'never reached a tool') +
    statCard('TOKENS (EST)', num(executed*1850), 'illustrative') +
    /* Counted by the encoder itself, and only reported when the run ends.
       Nothing here infers it from turn counts — the whole claim is that it
       does NOT track turns once the breaker is open. */
    statCard('ENCODER CALLS', encoder!=null?encoder:'—',
             encoder!=null ? 'zero on refused turns' : 'counted, reported at end');

  /* dials, with the ceiling and floor the agent actually reported */
  const sim = turns.map(t => t.action_sim);
  const nov = turns.map(t => t.obs_novelty);
  const ceiling = last.sim_ceiling;
  const floor = last.novelty_floor!=null ? last.novelty_floor : FLOOR_DEFAULT;
  spark(document.getElementById('sv-sim'), sim,
        [{v:ceiling, c:'#f5b23d'}], '#9d7cf4');
  spark(document.getElementById('sv-nov'), nov,
        [{v:floor, c:'#ff5a47'}], '#25e0c8');

  const warm = document.getElementById('warmtext');
  if(last.calibrated_n!=null && last.min_samples!=null){
    const done = last.calibrated_n >= last.min_samples;
    warm.innerHTML = done
      ? `calibrated on ${last.calibrated_n} productive turns · ceiling ${ceiling!=null?ceiling.toFixed(3):'—'} (amber) · floor ${floor.toFixed(2)} (red)`
      : `calibrating — ${last.calibrated_n}/${last.min_samples} productive turns, the breaker cannot arm yet`;
    // The meter is only meaningful while warming; once armed it would just be
    // a permanently full bar competing with the sparklines for attention.
    document.getElementById('warmbar').style.display = done ? 'none' : 'block';
    document.getElementById('warmfill').style.width =
      Math.min(100, 100*last.calibrated_n/last.min_samples)+'%';
  }

  /* quadrant tally */
  const counts = {};
  for(const t of turns) if(t.quadrant) counts[t.quadrant]=(counts[t.quadrant]||0)+1;
  document.getElementById('quads').innerHTML =
    ['explore','grind','loop','thrash'].map(q =>
      `<span class="q-${q}"><b>${counts[q]||0}</b>${q}</span>`).join('');

  document.getElementById('f-plateau').innerHTML = turns.map(row).join('');
  scrollFeed('f-plateau');

  /* the trip card: the newest verdict the breaker produced */
  const opened = judged[judged.length-1] || turns.filter(t=>t.executed===false).slice(-1)[0];
  const card = document.getElementById('trip');
  if(opened && opened.message){
    card.classList.add('on');
    const parts = opened.message.split('Escape:');
    document.getElementById('trip-why').textContent = parts[0].trim();
    document.getElementById('trip-esc').textContent = parts[1] ? 'Escape: '+parts[1].trim() : '';
  } else { card.classList.remove('on'); }

  if(d.done && d.summary) document.getElementById('x-plateau').textContent =
    `${d.summary['turns executed']} executed, ${d.summary['turns refused']} refused · ` +
    `tripped at turn ${d.summary['tripped at turn']} · ${d.summary['ended because']}`;
}

function row(t){
  const cls = t.phase==='survey' ? 't survey' : 't';
  if(t.executed === false){
    return `<div class="${cls}"><span class="n">${t.n}</span><span>
      <span class="refused">REFUSED ${esc(t.action)}</span>
      <div class="msg">${esc(t.reason)}</div></span></div>`;
  }
  const dials = (t.action_sim!=null)
    ? `<span class="dials q-${t.quadrant||''}"> sim ${t.action_sim.toFixed(2)} · nov ${t.obs_novelty.toFixed(2)} · ${t.quadrant||''}</span>` : '';
  const verdict = (t.allowed === false && t.reason)
    ? `<div class="msg">breaker: ${esc(t.reason)}</div>` : '';
  return `<div class="${cls}"><span class="n">${t.n}</span><span>${esc(t.action)}${dials}
    <div class="obs">→ ${esc((t.observation||'').split('\\n')[0].slice(0,110))}</div>${verdict}</span></div>`;
}

function scrollFeed(id){ const f=document.getElementById(id); f.scrollTop=f.scrollHeight; }

async function tick(){
  try{
    const r = await fetch('/state', {cache:'no-store'});
    const s = await r.json();
    renderUnguarded(s.unguarded); renderPlateau(s.plateau);
    /* solo mode: one pane connected, so give it the whole width */
    const live = ['unguarded','plateau'].filter(m => (s[m].turns||[]).length).length;
    document.getElementById('grid').classList.toggle('solo', live===1);
  }catch(e){}
  setTimeout(tick, 700);
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
