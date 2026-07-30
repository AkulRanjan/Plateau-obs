# Plateau — demo video script

**Target: 2 min 45 s.** Every number below is measured from the live run, not
estimated. If a take produces different numbers, read the numbers on screen —
never the ones written here.

Team ABCD · Nithish Kannan M, Akul Rajan, Tejasvin S, Sriram Prasanna
Track: AI Safety and Observability

---

## 0:00 – 0:25 · The problem

**On screen:** the dashboard, both panes empty, agents about to start.

> An autonomous agent can get stuck without ever crashing.
>
> It rephrases the same request every turn. Every call returns 200 OK. Error
> rate zero, latency normal, every dashboard green.
>
> Nothing built for reliability watches the *sequence* of requests an agent
> makes — only whether each one succeeded. The only thing that eventually
> notices is the bill.

---

## 0:25 – 0:50 · The setup

**On screen:** start both agents. Turns begin filling both panes.

> Two laptops. Two real agents. Same model — Llama 3.1 8B running locally — same
> seed, same task, same tools.
>
> The task is one they cannot finish: find how to refresh an expired auth token.
> The documentation is honest, and it dead-ends. Refreshing needs a client
> secret. The secret is in a vault. The vault denies this service account.
>
> The only difference between the two agents is that the right one has Plateau
> attached.

---

## 0:50 – 1:20 · The left pane is the problem

**On screen:** point at the unguarded pane as it climbs past turn 12, 15, 20.

> Watch the left one. It is still going. Every single line says 200 OK.
>
> It has learned nothing since turn seven — it is calling the same tool with the
> same argument and getting the same answer back — and there is nothing in that
> log that a monitor could alarm on. Nothing is red. That is the entire problem
> in one column.
>
> By turn 22 it has spent roughly forty thousand tokens to make no progress at
> all.

---

## 1:20 – 2:00 · The right pane is the product

**On screen:** the trip. Let the REFUSED lines and the escape vector sit on
screen for a beat — do not talk over them.

> Now the right one. At turn twelve, Plateau opens the breaker.
>
> It reads both halves of every turn. Action similarity is one-point-zero
> against a ceiling of **0.744** — and it *learned* that ceiling from this
> agent's own productive turns, it is not a constant we picked. Observation
> novelty has collapsed to zero against a floor of 0.30.
>
> So it refuses the call, and it hands the agent back a reason and a route:
> turn eight produced the most new information in this run. Go back to that
> instead of re-asking.
>
> Fifteen turns executed. Seven refused. And here is the number I like most:
> **fifteen encoder calls, not twenty-two.** While the breaker is open, Plateau
> does no work at all. A tripped breaker is free — so leaving it tripped costs
> nothing.

---

## 2:00 – 2:25 · What is actually new

**On screen:** the 2×2 quadrant, or the detector-race panel.

> A stuck agent is not one that repeats itself. An agent working through five
> hundred invoices looks nearly identical every turn and is doing exactly what
> it should.
>
> A stuck agent is one that stops *learning*. So Plateau trips on information
> gain, not on repetition — and it calibrates what normal looks like for this
> agent, updating that baseline only from turns that actually produced new
> information. A stuck agent can never teach it that being stuck is normal.

---

## 2:25 – 2:45 · The honest part

**On screen:** the measured long-traces table. Do not rush this.

> Two things we measured that go against us.
>
> Plateau trips here because the search tool returns the same "no results"
> string every time — which is what a real search API does. When we varied the
> wording, our own encoder scored those non-answers as *new information*, and
> Plateau missed the stall entirely. The semantic-paraphrase claim is unproven,
> and it is in our repo in writing.
>
> On our long traces a 2019-era token-overlap baseline matches our recall with
> fewer false trips. What we do have is this: LangGraph's step cap false-trips a
> healthy sixty-one turn batch job at turn twenty-seven. Plateau holds.
>
> Nobody else in this space publishes their false-trip rate. We do.

---

## Closing card

```
PLATEAU — a semantic circuit breaker for autonomous agents
Trips when the agent stops learning, not when it starts repeating.
Team ABCD · github.com/AkulRanjan/Plateau-obs
```

---

## Delivery notes

- **Do not talk over the trip.** Two seconds of silence when the REFUSED lines
  appear is worth more than another sentence.
- **Read numbers off the screen.** If a take gives turn 11 instead of 12, say
  eleven. Never read a number the viewer cannot see.
- The honest section is not a disclaimer, it is the pitch. Deliver it at the
  same pace as everything else — no apology in the voice.
- If asked "why not just cap the steps": that is the LangGraph row. It fires
  blind at a fixed number and kills healthy work.
- Total runtime target 2:45. If you must cut, cut section 2:00–2:25, not the
  honest part.

## Fallbacks

- Live agents misbehave → `python demo/demo.py`, the deterministic replay, no
  network needed.
- Wifi dies → both agents still print full local panes; record the two terminals.
- Everything breaks → `web/` console replay at `npm run dev`.
