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
  :root{--bg:#0a1417;--panel:#0f2228;--line:#1c3b44;--ink:#e6f1f3;
        --muted:#88a6af;--faint:#7b949b;--cyan:#25e0c8;--red:#ff5a47;--amber:#f5b23d}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:14px/1.45 ui-sans-serif,system-ui,sans-serif;padding:22px}
  h1{font-size:19px;letter-spacing:.2em;margin:0 0 2px}
  .sub{color:var(--muted);font-size:12.5px;margin-bottom:16px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  .pane{background:var(--panel);border:1px solid var(--line);border-radius:12px;
        padding:14px;display:flex;flex-direction:column;min-height:70vh}
  .head{display:flex;justify-content:space-between;align-items:baseline;
        font:600 12px/1 ui-monospace,monospace;letter-spacing:.14em;margin-bottom:8px}
  .cost{font:600 26px/1.2 ui-monospace,monospace;font-variant-numeric:tabular-nums;
        margin-bottom:10px}
  .feed{flex:1;overflow-y:auto;max-height:60vh;font:11.5px/1.5 ui-monospace,monospace}
  .t{display:grid;grid-template-columns:26px 1fr;gap:8px;padding:4px 0;
     border-bottom:1px solid #16323a}
  .n{color:var(--faint)}
  .obs{color:var(--muted)}
  .dials{color:var(--faint);font-size:10.5px}
  .refused{color:var(--red)}
  .msg{color:var(--amber);font-size:10.5px;white-space:pre-wrap;margin-top:3px}
  .foot{margin-top:10px;padding-top:9px;border-top:1px solid var(--line);
        color:var(--muted);font-size:11.5px}
  .pill{font:11px ui-monospace,monospace;padding:3px 9px;border-radius:99px;border:1px solid}
  .waiting{color:var(--faint);padding:26px 0;text-align:center}
</style>
<h1>PLATEAU</h1>
<div class="sub">Two agents. Same model, same seed, same task. One has a circuit breaker.</div>
<div class="grid">
  <div class="pane"><div class="head"><span style="color:var(--red)">UNGUARDED</span>
    <span id="s-unguarded" class="pill" style="border-color:var(--red);color:var(--red)">waiting</span></div>
    <div class="cost" style="color:var(--red)" id="c-unguarded">0 <span style="font-size:11px;color:var(--faint)">tok</span></div>
    <div class="feed" id="f-unguarded"><div class="waiting">waiting for the agent…</div></div>
    <div class="foot" id="x-unguarded">Every call returns 200 OK. No dashboard has anything to alarm on.</div>
  </div>
  <div class="pane"><div class="head"><span style="color:var(--cyan)">WITH PLATEAU</span>
    <span id="s-plateau" class="pill" style="border-color:var(--cyan);color:var(--cyan)">waiting</span></div>
    <div class="cost" style="color:var(--cyan)" id="c-plateau">0 <span style="font-size:11px;color:var(--faint)">tok</span></div>
    <div class="feed" id="f-plateau"><div class="waiting">waiting for the agent…</div></div>
    <div class="foot" id="x-plateau">Watching both halves of every turn.</div>
  </div>
</div>
<div class="sub" style="margin-top:14px">
  Token figures are ILLUSTRATIVE: turns are measured, tokens are arithmetic over an
  assumed 1,850/turn. Plateau trips on observation novelty; the loop's non-answer is a
  constant string, which is what makes novelty collapse.
</div>
<script>
const esc = s => (s||"").replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function render(mode, d){
  const feed = document.getElementById('f-'+mode);
  const turns = d.turns || [];
  if(!turns.length) return;
  const executed = turns.filter(t => t.allowed !== false).length;
  document.getElementById('c-'+mode).innerHTML =
    (executed*1850).toLocaleString() + ' <span style="font-size:11px;color:var(--faint)">tok</span>';
  const pill = document.getElementById('s-'+mode);
  const last = turns[turns.length-1];
  pill.textContent = d.done ? 'finished · ' + (d.summary['ended because']||'') : (last.state||'running');
  feed.innerHTML = turns.map(t => {
    if(t.allowed === false){
      return `<div class="t"><span class="n">${t.n}</span><span>
        <span class="refused">REFUSED ${esc(t.action)}</span>
        <div class="msg">${esc(t.reason)}</div>
        ${t.message ? `<div class="msg">${esc(t.message)}</div>` : ''}</span></div>`;
    }
    const dials = (t.action_sim!=null)
      ? `<span class="dials"> sim ${t.action_sim.toFixed(2)} · nov ${t.obs_novelty.toFixed(2)} · ${t.quadrant||''}</span>` : '';
    return `<div class="t"><span class="n">${t.n}</span><span>${esc(t.action)}${dials}
      <div class="obs">→ ${esc((t.observation||'').split('\\n')[0].slice(0,110))}</div></span></div>`;
  }).join('');
  feed.scrollTop = feed.scrollHeight;
  if(d.done && d.summary){
    document.getElementById('x-'+mode).textContent =
      `${d.summary['turns executed']} turns executed, ${d.summary['turns refused']} refused · ` +
      `tripped at turn ${d.summary['tripped at turn']} · ${d.summary['ended because']}`;
  }
}
async function tick(){
  try{
    const r = await fetch('/state', {cache:'no-store'});
    const s = await r.json();
    render('unguarded', s.unguarded); render('plateau', s.plateau);
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
    print(f"\n{'=' * 72}")
    print("  Plateau collector + dashboard")
    print(f"  dashboard : http://{ip}:{a.port}/   (open this, record this)")
    print(f"  agents    : --collector http://{ip}:{a.port}")
    print(f"{'=' * 72}\n")

    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
