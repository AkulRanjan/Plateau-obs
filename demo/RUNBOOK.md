# Two-laptop live demo — runbook

Two real agents, two machines, same model and seed, same impossible task. One
has Plateau attached. Both stream into one dashboard you record.

Measured on a dry run (llama3.1:8b, 22-turn cap):

| | unguarded | with Plateau |
|---|---|---|
| turns executed | 22 | **15** |
| turns refused | 0 | **7** |
| tripped at | never | **turn 11** |
| tokens (est.) | 40,700 | **18,500** |
| encoder calls | — | **15, not 22** |

That last row is the cost argument: Plateau did **zero embedding work on the 7
refused turns**. A tripped breaker is free.

---

## Setup

### Friend's laptop — the unguarded agent (5 minutes, very light)

It never imports `plateau`, so no MiniLM, no torch, no sentence-transformers.

```bash
ollama serve                  # if not already running
ollama pull llama3.1:8b       # ~4.9 GB — START THIS FIRST, it is the long pole
pip install httpx
```

Copy just these three files, keeping the paths:

```
demo/__init__.py
demo/live_agent.py
demo/live_model.py
demo/live_world.py
```

### Your laptop — Plateau + the collector

Already set up. Verify:

```bash
python -c "from plateau.encoder import MiniLMEncoder; MiniLMEncoder().load(); print('encoder ok')"
```

---

## Before recording: prove the two runs are comparable

Both agents must be on the same model build, or "same decisions until the
breaker fires" is an assumption rather than a fact. On **both** laptops:

```bash
ollama show llama3.1:8b | head -5
```

Confirm the parameter count and quantisation match. If they differ, the demo
still works — just say "both agents got stuck" rather than "identical runs".

---

## Running it

**1. Collector, on your laptop.** It prints the LAN URL to hand out.

```bash
python demo/collector.py --port 8080
```

**2. Open the dashboard** on your laptop and make it the recorded window:

```
http://<your-lan-ip>:8080/
```

**3. Start both agents.** Friend first, so the unguarded pane starts filling:

```bash
# friend's laptop
python demo/live_agent.py --mode unguarded --max-turns 22 \
    --collector http://<your-lan-ip>:8080

# your laptop
python demo/live_agent.py --mode plateau --max-turns 22 \
    --collector http://<your-lan-ip>:8080
```

Each run is roughly 25–30 seconds. `--delay 0.5` slows it for a calmer video.

---

## If the network fails

Both agents print a full live pane to their own terminal regardless — the
collector is optional. If wifi dies mid-take, record the two terminals side by
side instead. Nothing is lost; each agent also writes
`demo/run-<mode>-<time>.jsonl` locally.

If the live agents misbehave entirely, `python demo/demo.py` is the deterministic
replayed fallback and needs no network at all.

---

## What to say on camera

**The left pane is the problem.** Every line returns 200 OK. Error rate zero,
latency normal, every dashboard green — and the agent has learned nothing since
turn 10. The only thing that eventually notices is the bill.

**The right pane is the product.** Plateau reads both halves of every turn.
At turn 11 novelty has collapsed to 0.000 against a floor of 0.30 while action
similarity sits at 1.000 against a *learned* ceiling of 0.872 — it calibrated
that ceiling from this agent's own productive turns. It refuses, hands back the
reason, and points at turn 4 as the last thing that actually produced
information.

**The honest caveat, before anyone asks.** Plateau trips here because the search
tool returns a byte-identical "No results found." every time, which is what a
real search API does. The project measured the limit: when non-answers are
worded *differently* each time, MiniLM scores them 0.44–1.01 novelty and Plateau
does **not** trip (`metrics.json → long_trace_comparison`). So this is a real
detection on a real agent, and the semantic-paraphrase claim remains unproven.
Say it before a judge finds it.

---

## Tomorrow: AWS

`demo/live_model.py` has a `BedrockModel` stub with the same interface. Swapping
is one class — implement `propose()` against `bedrock-runtime converse()` and map
its `toolUse` block onto `Proposal`. The agent loop and Plateau need no changes.
