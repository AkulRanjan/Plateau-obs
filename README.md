# Plateau-obs

A semantic circuit breaker for autonomous AI agents. Detects when an agent has
stopped learning, even when its actions keep changing.

## Design

Two dials per turn:

| | **learned something** (novelty ≥ floor) | **learned nothing** (novelty < floor) |
|---|---|---|
| **confident** (action_sim ≥ ceiling) | **GRIND** — healthy batch job | **LOOP** — classic stall (trips at 3) |
| **not confident** | **EXPLORE** — open-ended research | **THRASH** — varied actions, no progress (trips at 6) |

Novelty is the trip axis. Similarity only sets the evidence bar. That revision
came from measurement: three genuinely different tools (`read_file`, `grep`,
`list_dir`) read `action_sim` 0.7397 against the same window, so MiniLM has no
low-similarity region for tool-call strings. Thrash is defined on the novelty
axis alone.

## Fixture results

Six-turn productive preamble, then the pattern under test. All four pass:

| Fixture | Quadrant | Trip turn | Action sim | Obs novelty |
|---|---|---|---|---|
| 1 — paraphrase loop | LOOP | — | 0.8927 | 0.0000 |
| 2 — invoice batch (counter-demo) | GRIND | — | 0.9913 | 0.4392 |
| 3a — identical error strings | LOOP (migrates thrash→loop) | **6** | 0.7818 | 0.0000 |
| 3b — varied error strings | THRASH (does NOT trip) | — | 0.7397 | 0.2114 |

Fixture 2 is the counter-demo: action_sim 0.9913 clears the ceiling, so
similarity alone condemns it. It survives because novelty 0.4392 is above the
floor. That is the joint design earning its place.

## Read this before the results table

**The fixtures below validate _classification_, not _detection_, and the
detection comparison that follows is not yet a valid benchmark.** Fixtures 1 and
2 are **two turns** long. Every trip threshold in the design is 3 or higher, so
neither fixture can physically trip regardless of parameters. Any row showing
`---` for them is measuring trace length, not detector behaviour.

This is stated up front because the sweep below reports **0 usable
configurations out of 144** and that number is an artifact of the above, not a
verdict on the design. Real per-class traces (§9) are required before any
detection claim here means anything.

## Six-baseline comparison

Trip turn by variant and fixture (preamble + fixture turns; `---` = no trip):

| Variant | 1 — paraphrase (2t) | 2 — batch (2t) | 3a — identical (7t) | 3b — varied (3t) |
|---|---|---|---|---|
| **Plateau (full)** | --- | --- | 6 | --- |
| **action_only** | --- | --- | 5 | --- |
| **novelty_only** | --- | --- | 6 | --- |
| exact-args debounce | --- | --- | --- | --- |
| exact-match (OpenHands) | --- | --- | --- | --- |
| lexical (agent-loop-detector) | --- | --- | 2 | --- |
| step-cap (LangGraph 25) | --- | --- | --- | --- |

*action_only* pins novelty to 0. The calibrator never warms (all turns
gated), so the ceiling stays at the conservative default 0.85. Trips at 5
on 3a vs 6 for full Plateau — marginally faster because turn 0 (novelty
0.6981 in reality) is also stagnant when novelty is blinded.

*novelty_only* pins action_sim to 0, so `confident` is never true and only
the `stall_hits` path fires. Matches full Plateau on detections; only
turns-to-detection differs.

Note: **step_cap (LangGraph 25)** requires 27 turns to fire, longer than
any fixture. At the source default of **10007** it never fires on any trace
up to 200 turns — recall is zero by construction.

### Our worst numbers, stated plainly

**On the only fixture where anything detects a stall, a 2019-era lexical
baseline beats us: `agent-loop-detector` fires at turn 2, Plateau at turn 6.**
That is the honest result on 3a, whose observations are byte-identical — exactly
the case exact and lexical matching are built for. Plateau's claimed advantage is
on *paraphrased* stagnation, and the fixture that would show it (fixture 1) is
too short to trip at all. So the advantage is currently **unmeasured**, not
demonstrated.

**Sweep: 0 of 144 configurations are usable.** A configuration is usable only if
it catches every stall and false-trips on nothing.

| Sweep result | Value |
|---|---|
| Configurations evaluated | 144 |
| Usable configurations | **0 (0.0%)** |
| Max recall observed | **0.5** |
| Usable threshold window width | **empty — undefined** |
| False-trip rate (fixture 2, all configs) | **0.0** |
| `1_paraphrase_loop` missed in | **144/144 configs** |
| `3a_thrash_identical_errors` missed in | 28/144 configs |

The one genuinely good number there is the false-trip rate: **0.0 across all 144
configurations** — the healthy batch job was never tripped on, at any parameter
setting. The counter-demo is the most robust result in the project.

Everything else is pending real traces. `metrics.json` → `sweep.summary`.

## Documented limitations

1. **Fixture 3b (varied error strings) is a known miss.** Lexically varied
   failure messages read as new information on short-string embeddings, so an
   agent failing in differently-worded ways evades detection. Not tuned away,
   kept honest by `test_fixture_3b_varied_errors_is_a_known_miss`.

2. **Polling tools must declare `idempotent: true`.** The measured novelty
   distribution shows pollers spanning 0.0067–0.2311, overlapping with the
   loop band. A poller is informationally stalled ("still running, 4m" → "still
   running, 9m"), so no threshold can separate it from a stuck agent. Any tool
   that legitimately returns near-identical observations must declare itself
   idempotent.

3. **No thrash floor.** Three different tools score 0.7397, so
   `mu − k·σ` cannot find a low-similarity region that does not exist. Not
   patched with a constant.

4. **Fixtures 1 and 2 are two turns long and cannot trip.** Every threshold is
   ≥3. They test quadrant classification, which they pass, and nothing else. The
   detection comparison and the sweep are therefore not yet valid benchmarks.

5. **No non-synthetic evaluation yet.** Every trace above is hand-written. The
   TRAIL dataset (gated, `PatronusAI/TRAIL`) is downloaded separately by a human
   and is never committed; `data/trail/` is gitignored. Until those traces are
   loaded, no number here is evidence about real agent behaviour.

## Prior art, as actually read

Four shipped systems guard against agent loops. We read each one's source rather
than its README, and two claims in our own pitch deck turned out to be wrong —
the corrections are recorded in `THIRD_PARTY_NOTICES.md`.

| System | Reads | Mechanism |
|---|---|---|
| OpenHands `StuckDetector` | **both halves** | exact equality (`_event_eq`), 5 scenarios |
| `agent-loop-detector` | **observation only** (`check(output)`) | Jaccard / TF-cosine / Levenshtein |
| Strands `LimitToolCounts` | action count per tool | per-tool call cap |
| LangGraph `recursion_limit` | **neither half** | superstep counter, no content comparison |

**None compares both halves semantically.** That is the gap Plateau targets — a
narrower claim than "they all compare exact strings," which is false: LangGraph
compares nothing at all, and `agent-loop-detector` compares lexical overlap.

Both open OpenHands issues we cite as motivation are real and unresolved:
[#5355](https://github.com/All-Hands-AI/OpenHands/issues/5355) (loop detection
kills agents waiting on long-running processes) and
[#5480](https://github.com/All-Hands-AI/OpenHands/issues/5480) (cannot recover
from a stuck loop). The second is why recovery here is an evaluated probe rather
than a hard stop.

## Provisional parameters (pending sweep)

| Parameter | Current | Owned by |
|---|---|---|
| `NOVELTY_FLOOR` | 0.30 | `eval/sweep.py` |
| `K_SIGMA` | 1.0 | `eval/sweep.py` |
| `TRIP_AFTER_LOOP` | 3 | `eval/sweep.py` |
| `TRIP_AFTER_STALL` | 6 | `eval/sweep.py` |
