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

## Six-baseline comparison

Trip turn by variant and fixture (preamble + fixture turns; `---` = no trip):

| Variant | 1 — paraphrase (2t) | 2 — batch (2t) | 3a — identical (8t) | 3b — varied (3t) |
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

## Provisional parameters (pending sweep)

| Parameter | Current | Owned by |
|---|---|---|
| `NOVELTY_FLOOR` | 0.30 | `eval/sweep.py` |
| `K_SIGMA` | 1.0 | `eval/sweep.py` |
| `TRIP_AFTER_LOOP` | 3 | `eval/sweep.py` |
| `TRIP_AFTER_STALL` | 6 | `eval/sweep.py` |
