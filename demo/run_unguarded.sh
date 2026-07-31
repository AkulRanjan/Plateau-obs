#!/usr/bin/env bash
#
# The OTHER laptop. Runs the unguarded agent and streams it to the dashboard.
#
#   ./run_unguarded.sh                          # finds the collector by name
#   ./run_unguarded.sh http://192.168.1.20:8090 # or tell it exactly where
#
# It needs these four files and finds them whether this script sits INSIDE the
# demo/ directory (as it does in the repo) or beside it (as it will once it has
# been copied to the other laptop):
#   __init__.py  live_agent.py  live_model.py  live_world.py
#
# This side never imports plateau: no torch, no MiniLM, no weights, no ~90 MB
# download. That is deliberate — it is half the point that guarding an agent
# costs the guarded machine something and the other machine nothing.
#
# THE ADDRESS
# -----------
# Prefer the address run_demo.sh prints on the collector machine — it says
# exactly what to type here, and it is always right.
#
# The fallback default is fedora.local, mDNS/Bonjour, which macOS resolves
# natively and which follows the machine across DHCP leases. Be aware it is
# not unconditionally safe: avahi advertises every interface, so on a host with
# docker installed fedora.local also answers as 172.17.0.1, a bridge address
# unreachable from the LAN. Measured on this setup — the name resolved to the
# docker bridge first. If the name resolves but nothing answers, that is why:
# pass the IP explicitly. On the collector machine the permanent fix is
# deny-interfaces=docker0 in /etc/avahi/avahi-daemon.conf.
#
# Written for bash 3.2, because that is what macOS still ships. No associative
# arrays, no ${var,,}, nothing from bash 4.

set -u

COLLECTOR="${1:-${PLATEAU_COLLECTOR:-http://fedora.local:8090}}"
MODEL="${PLATEAU_MODEL:-llama3.1:8b}"
MAX_TURNS="${PLATEAU_MAX_TURNS:-25}"

PY="python3"
command -v "$PY" >/dev/null 2>&1 || PY="python"

red() { printf '\n  \033[31m%s\033[0m\n\n' "$1" >&2; }
say() { printf '  %s\n' "$1"; }

# Absolute path to the agent, so the working directory never matters.
# live_agent.py resolves its own project root from __file__, not from cwd.
HERE=$(cd "$(dirname "$0")" && pwd)
if [ -f "$HERE/live_agent.py" ]; then
  AGENT="$HERE/live_agent.py"          # this script is inside demo/
elif [ -f "$HERE/demo/live_agent.py" ]; then
  AGENT="$HERE/demo/live_agent.py"     # this script is beside demo/
else
  red "cannot find live_agent.py — copy the four demo/ files next to this script"
  exit 1
fi

# --- 1. ollama -------------------------------------------------------------
TAGS=$(curl -fsS --max-time 5 http://localhost:11434/api/tags 2>/dev/null)
if [ -z "$TAGS" ]; then
  red "ollama is not answering on localhost:11434 — run 'ollama serve' and try again"
  exit 1
fi
case "$TAGS" in
  *"\"$MODEL\""*) : ;;
  *) red "ollama is up but '$MODEL' is not pulled — run: ollama pull $MODEL"; exit 1 ;;
esac

# --- 2. the digest, printed BEFORE anything runs ---------------------------
# The other laptop prints the same string. If they differ, the two agents are
# not running the same thing and nobody should pretend otherwise afterwards.
DIGEST=$("$PY" - "$MODEL" <<'PY' 2>/dev/null
import json, sys, urllib.request
want = sys.argv[1]
body = json.load(urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5))
for m in body.get("models", []):
    if m.get("name") == want or m.get("model") == want:
        print(m.get("digest", "")[:12], (m.get("details") or {}).get("quantization_level") or "?")
        break
PY
)
say "ollama      up, $MODEL present"
say "digest      ${DIGEST:-unknown}   <- compare this with the other laptop"

# --- 3. httpx --------------------------------------------------------------
if ! "$PY" -c "import httpx" >/dev/null 2>&1; then
  red "httpx is missing. Install it:
    $PY -m pip install --user httpx
  or, if macOS refuses with 'externally-managed-environment':
    $PY -m venv .venv && .venv/bin/pip install httpx
  then re-run this with:  PY=.venv/bin/python ./run_unguarded.sh"
  exit 1
fi

# --- 4. the collector ------------------------------------------------------
if ! curl -fsS --max-time 6 "$COLLECTOR/state" >/dev/null 2>&1; then
  red "cannot reach the collector at $COLLECTOR
  Checked: $COLLECTOR/state

  If the name did not resolve, the venue wifi is probably blocking mDNS.
  Ask for the collector's current IP and pass it directly:
    ./run_unguarded.sh http://<ip>:8090
  The other laptop prints that address in its boot banner."
  exit 1
fi
say "collector   $COLLECTOR  [reachable]"

# --- 5. go -----------------------------------------------------------------
printf '\n'
exec "$PY" "$AGENT" \
  --mode unguarded \
  --collector "$COLLECTOR" \
  --model "$MODEL" \
  --max-turns "$MAX_TURNS"
