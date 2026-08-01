#!/usr/bin/env bash
#
# One command to run the demo. Starts the collector, waits for it to actually
# answer, then starts the agent.
#
#   demo/run_demo.sh                          # guarded agent, ollama, port 8090
#   demo/run_demo.sh --mode unguarded         # the other pane
#   demo/run_demo.sh --model-kind bedrock     # only if Bedrock access has landed
#   demo/run_demo.sh --collector-only         # just the dashboard, for laptop 2
#
# WHY THIS EXISTS
# ---------------
# Under presentation pressure nobody should be sequencing two processes by hand
# and guessing whether the collector is up yet. Every failure below is loud and
# happens BEFORE the first turn, because the expensive failure is the one that
# shows up halfway through a take.
#
# The collector publishes its address to demo/collector.url on boot and the
# agent reads it, so no IP is typed anywhere. This script deletes that file
# first: a collector that fails to start must not leave yesterday's address
# behind for the agent to find and believe.

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="plateau"
MODEL_KIND="ollama"
MODEL="llama3.1:8b"
MAX_TURNS="25"
DELAY="0"
PORT="8090"
COLLECTOR_ONLY="no"

die() { printf '\n  \033[31m%s\033[0m\n\n' "$*" >&2; exit 1; }
say() { printf '  %s\n' "$*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)            MODE="${2:?--mode needs a value}"; shift 2 ;;
    --model-kind)      MODEL_KIND="${2:?--model-kind needs a value}"; shift 2 ;;
    --model)           MODEL="${2:?--model needs a value}"; shift 2 ;;
    --max-turns)       MAX_TURNS="${2:?--max-turns needs a value}"; shift 2 ;;
    --delay)           DELAY="${2:?--delay needs a value}"; shift 2 ;;
    --port)            PORT="${2:?--port needs a value}"; shift 2 ;;
    --collector-only)  COLLECTOR_ONLY="yes"; shift ;;
    -h|--help)         sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *)                 die "unknown argument: $1" ;;
  esac
done

case "$MODE" in plateau|unguarded) ;; *) die "--mode must be plateau or unguarded, got: $MODE" ;; esac
case "$MODEL_KIND" in ollama|bedrock) ;; *) die "--model-kind must be ollama or bedrock, got: $MODEL_KIND" ;; esac

PYTHON="${PYTHON:-python}"
command -v "$PYTHON" >/dev/null 2>&1 || die "no python on PATH (set PYTHON=... to choose one)"

# ---------------------------------------------------------------------------
# 1. the model backend
# ---------------------------------------------------------------------------
# ollama is the ACTIVE path and is checked here, because "ollama isn't running"
# and "the model was never pulled" are the two failures that cost a take. The
# bedrock branch deliberately checks nothing: no AWS config, no credentials and
# no boto3 are required to run this script on ollama, which is the point.
if [[ "$MODEL_KIND" == "ollama" ]]; then
  tags="$(curl -fsS --max-time 5 http://localhost:11434/api/tags 2>/dev/null)" \
    || die "ollama is not answering on localhost:11434 — start it with:  ollama serve"
  if ! grep -q "\"$MODEL\"" <<<"$tags"; then
    die "ollama is up but '$MODEL' is not pulled — run:  ollama pull $MODEL"
  fi
  say "ollama      up, $MODEL present"
else
  say "model kind  bedrock (ollama not checked; nothing here needs AWS unless you asked for it)"
fi

# The guarded pane needs the encoder locally; the unguarded pane deliberately
# does not import plateau at all.
if [[ "$MODE" == "plateau" ]]; then
  # Output suppressed: this is a yes/no check, and its weight-loading bar and
  # transformers warnings would otherwise be the first thing on the recording.
  # The agent loads the encoder again for real, one line further down.
  "$PYTHON" - >/dev/null 2>&1 <<'PY' || die "the encoder will not load — the guarded pane cannot run. See demo/RUNBOOK.md."
import os, sys
os.environ.setdefault("HF_HUB_OFFLINE", "1")
from plateau.encoder import MiniLMEncoder
MiniLMEncoder().load()
PY
  say "encoder     loaded"
fi

# ---------------------------------------------------------------------------
# 2. the collector
# ---------------------------------------------------------------------------
URL_FILE="$ROOT/demo/collector.url"
rm -f "$URL_FILE"

COLLECTOR_PID=""
cleanup() {
  if [[ -n "$COLLECTOR_PID" ]] && kill -0 "$COLLECTOR_PID" 2>/dev/null; then
    kill "$COLLECTOR_PID" 2>/dev/null || true
    wait "$COLLECTOR_PID" 2>/dev/null || true
    say "collector   stopped (pid $COLLECTOR_PID)"
  fi
}
trap cleanup EXIT INT TERM

if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/state" >/dev/null 2>&1; then
  die "something is already listening on port $PORT. Stop it, or pass --port <other>."
fi

"$PYTHON" demo/collector.py --host 0.0.0.0 --port "$PORT" &
COLLECTOR_PID=$!

# Wait for it to ANSWER, not merely to have been spawned — via the agent's own
# preflight, so there is exactly one reachability check and one error message
# in this repo. It fails loudly on its own if the collector never comes up.
"$PYTHON" - "$PORT" <<'PY'
import sys
sys.path.insert(0, ".")
from demo.live_agent import preflight
preflight(f"http://127.0.0.1:{sys.argv[1]}", "run_demo.sh (collector just started)", wait=20.0)
PY

kill -0 "$COLLECTOR_PID" 2>/dev/null || die "the collector exited during startup"
[[ -s "$URL_FILE" ]] || die "the collector is up but published no address to demo/collector.url"

say "collector   $(cat "$URL_FILE") (pid $COLLECTOR_PID)"
say "dashboard   $(cat "$URL_FILE")/   <- open and record this"
# Read this line out to the other laptop. It carries the address this machine
# is actually reachable on, which beats anyone retyping an IP from memory or
# trusting mDNS to pick the right interface.
say "other laptop:  ./run_unguarded.sh $(cat "$URL_FILE")"

if [[ "$COLLECTOR_ONLY" == "yes" ]]; then
  say "collector-only: leave this running and start the agents elsewhere. Ctrl-C to stop."
  wait "$COLLECTOR_PID"
  exit 0
fi

# ---------------------------------------------------------------------------
# 3. the agent
# ---------------------------------------------------------------------------
# No --collector: the agent reads the address the collector just published, and
# runs its own preflight against it before turn 1.
printf '\n'
"$PYTHON" demo/live_agent.py \
  --mode "$MODE" \
  --model-kind "$MODEL_KIND" \
  --model "$MODEL" \
  --max-turns "$MAX_TURNS" \
  --delay "$DELAY"

printf '\n'
say "run complete. The dashboard is still live at $(cat "$URL_FILE")/"
say "Press Ctrl-C when you have finished recording."
wait "$COLLECTOR_PID"
