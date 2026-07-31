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
> task, same tools.
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
> By the cap we imposed it has spent roughly forty-six thousand tokens to make
> no progress at all — and it was not going to stop on its own.

---

## 1:20 – 2:00 · The right pane is the product

**On screen:** the trip. Let the REFUSED lines and the escape vector sit on
screen for a beat — do not talk over them.

> Now the right one. At turn twelve, Plateau opens the breaker.
>
> It reads both halves of every turn. Action similarity is one-point-zero
> against a learned ceiling — and it *learned* that ceiling from this agent's
> own productive turns, it is not a constant we picked. Observation novelty
> has collapsed to zero against a floor of 0.25.
>
> **Read the ceiling and the turn number off the screen, not off this page.**
> They move between runs — see the reproducibility note in the RUNBOOK.
>
> So it refuses the call, and it hands the agent back a reason and a route:
> the turn that produced the most new information in this run. Go back to that
> instead of re-asking.
>
> And here is the number I like most: **encoder calls equals turns executed,**
> not turns attempted. While the breaker is open, Plateau does no work at all.
> A tripped breaker is free — so leaving it tripped costs nothing.
>
> That invariant held on every run, on both machines. The turn numbers did not.

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

> Three things we measured that go against us.
>
> First, we found the reworded-stall miss ourselves and it turned out not to be
> a threshold problem at all. Our comparison window was eight turns, and it was
> the one parameter we had never swept. A loop longer than the window is
> invisible — the detector cannot see a repetition it has no memory of. At
> sixteen we catch it. Of five parameters, that is the *only* one that changes
> the outcome; the four we spent weeks tuning do not.
>
> Second, a 2019-era token-overlap baseline still detects sooner than we do —
> eight turns against our thirteen-point-seven. If you are counting tokens
> burned before the breaker opens, it beats us on every trace it can see. What
> it cannot see is the reworded stall, which it misses completely.
>
> Third, our zero false-trip rate depends on the tool author declaring polling
> tools idempotent. That is work we hand to whoever installs this. Forget it and
> a healthy poller trips at turn ten.
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
  eleven. Never read a number the viewer cannot see. This is not caution: the
  model is 5.9 GB against a 6 GB card, so ollama splits it across CPU and GPU
  and the split moves between runs. Different arithmetic, different sampled
  token, different trip turn — even at temperature 0 with a fixed seed. Check
  `ollama ps` before believing any specific turn.
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
