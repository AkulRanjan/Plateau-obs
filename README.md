# Plateau-obs

A semantic circuit breaker for autonomous AI agents. Detects when an agent has
stopped learning, even when its actions keep changing.

Every number below was produced by a script in this repository and written to
`metrics.json`. `scripts/check_readme.py` fails if a figure here is not backed
by a measurement there.

## Design

Two dials per turn:

| | **learned something** (novelty ≥ floor) | **learned nothing** (novelty < floor) |
|---|---|---|
| **confident** (action_sim ≥ ceiling) | **GRIND** — healthy batch job | **LOOP** — classic stall |
| **not confident** | **EXPLORE** — open-ended research | **THRASH** — varied actions, no progress |

Novelty is the trip axis. Similarity only sets the evidence bar. That revision
came from measurement: three genuinely different tools (`read_file`, `grep`,
`list_dir`) read `action_sim` 0.7397 against the same window, so MiniLM has no
low-similarity region for tool-call strings. Thrash is defined on the novelty
axis alone.

## The result that matters most

**`window_size` was the whole problem, and nobody had ever measured it.**

Both dials are `max_cosine` against the last `window_size` turns. That number
was hard-coded to 8 and was not one of the four swept parameters — so a
repetition whose period exceeds 8 turns was *structurally invisible*. The
detector could not see a loop longer than its own memory, and no threshold could
have fixed that.

`metrics.json → long_trace_sweep` sweeps all five parameters over the 16–61 turn
classes. Of 576 configurations, **432 are usable** (75.0%) — catch every stall,
false-trip on nothing. And the usable window per axis is:

| axis | values swept | values usable |
|---|---|---|
| `novelty_floor` | 0.25, 0.30, 0.35, 0.40 | **all four** |
| `k_sigma` | 0.5, 1.0, 1.5, 2.0 | **all four** |
| `trip_after_loop` | 2, 3, 4 | **all three** |
| `trip_after_stall` | 4, 6, 8 | **all three** |
| **`window_size`** | 8, 12, 16, 24 | **12, 16, 24 — 8 fails** |

All 144 failing configurations are exactly the `window_size = 8` ones. The one
positive ever missed is `paraphrase_loop_varied_wording`, missed in 144 of 576 —
the same 144. Zero false trips in all 576.

**The four parameters we swept for weeks do not change the outcome. The one we
never swept decides it.** That is not a flattering finding and it is the most
useful one in the project.

Default is now 16, not 12: the trace that discriminates cycles 12 phrasings, so
a window of exactly 12 sits on that boundary and would be a coincidence of the
fixture rather than a margin. **It remains provisional** — nothing here measures
what a *real* agent's rewording repertoire is, which is the number the window
has to exceed.

## Real traces: TRAIL

`metrics.json → trail_comparison`. 148 expert-annotated agent traces from
[TRAIL](https://huggingface.co/datasets/PatronusAI/TRAIL) (arXiv:2505.08638) —
GAIA via OpenDeepResearch on o3-mini, SWE-Bench Lite via CodeAct on
claude-3-7-sonnet. Gated, MIT, never committed.

**This is the table to read first. The synthetic results in the next section
do not survive contact with it.**

| detector | recall | false-trip | mean TTD |
|---|---|---|---|
| plateau | **0.63** | **0.54** | 12.4 |
| exact-args debounce | 0.58 | 0.23 | 12.7 |
| plateau_novelty_only *(ablation)* | 0.45 | 0.38 | 14.1 |
| step-cap (LangGraph 25) | 0.12 | 0.00 | 27.0 |
| lexical (`agent-loop-detector`) | 0.07 | 0.00 | 22.8 |
| exact-match (OpenHands) | 0.00 | 0.00 | — |
| plateau_action_only *(ablation)* | 1.00 | 1.00 | 5.0 |

`tool+llm` spans, `primary` mapping, 60 positives / 13 negatives.

**`perfect_detectors` is empty in all six mode × mapping combinations.** On our
own traces Plateau reached recall 1.00 with zero false trips. On real ones
nothing does, and Plateau false-trips **more than half** the healthy traces.
The honest summary is that our synthetic evaluation was optimistic about us, and
we only know that because we went and got real traces.

What survives: Plateau has the highest recall of any non-degenerate detector,
and the gap is not small. The lexical baseline that matched us on synthetic
traces essentially **does not fire at all** on real ones — recall 0.07. Its
0.00 false-trip rate is the false-trip rate of a detector that never fires.
Exact-args is the real competitor here, not lexical.

By split (`primary`, `tool+llm`):

| detector | GAIA recall / false-trip | SWE-Bench recall / false-trip |
|---|---|---|
| plateau | 0.61 / 0.67 | 0.68 / 0.25 |
| exact-args | 0.45 / 0.11 | 0.82 / 0.50 |
| lexical | 0.11 / 0.00 | 0.00 / 0.00 |

Averaging these would hide that they are different problems.

### Everything wrong with this benchmark, listed

1. **Most traces are too short to evaluate.** A detector needing
   `trip_after_stall` consecutive stagnant turns cannot fire on a short trace,
   so including those would report trace length as recall — the mistake the
   two-turn fixtures made. At `MIN_TURNS = 8`, **75 of 148 traces are excluded**
   in `tool+llm` mode. In `tool`-spans-only mode just **14 of 148** survive, with
   a single negative — a false-trip rate over n=1 is not a measurement, and that
   mode should not be quoted.
2. **13 negatives is a small denominator.** One trace moves the false-trip rate
   by 8 points.
3. **Two normalisation decisions are ours, not TRAIL's.** Which spans become
   turns, and which error categories mean "should have tripped". Both are
   swept — 2 span modes × 3 mappings, all six reported — but the `primary`
   mapping quoted above is a judgement call about what "stopped learning" means.
   The full mapping and the raw→canonical category table are in `metrics.json`
   so you can disagree and recompute.
4. **The annotations needed repair.** The pinned revision holds **31 distinct
   category strings for ~19 leaves** — casing, pluralisation, a leading space,
   and one typo (`Instruction non complience`). Exact-string matching silently
   drops 8 labelled traces. One annotation file has a trailing comma and is not
   valid JSON; it is repaired on load, and the repair is recorded in
   `metrics.json → trail_comparison.repaired_source_files` rather than applied
   quietly.
5. **Treating an LLM completion as an observation overstates the environment.**
   In a CodeAct loop the model's output *is* the action. `tool` mode is the
   faithful reading, and it is the one with too little data.

## Detection on long traces

Five classes, 16–61 turns. `metrics.json → long_trace_comparison`.

| detector | recall | false-trip | mean turns-to-detect |
|---|---|---|---|
| **plateau + `idempotent`** | **1.00** | **0.00** | 13.67 |
| plateau (no declaration) | 1.00 | 0.50 | 13.67 |
| plateau_novelty_only *(ablation)* | 1.00 | 0.50 | 15.67 |
| plateau_action_only *(ablation)* | 1.00 | 1.00 | 5.00 |
| lexical (`agent-loop-detector`) | 0.67 | 0.00 | 8.00 |
| step-cap (LangGraph 25) | 0.67 | 1.00 | 27.00 |
| exact-args debounce | 0.00 | 0.50 | — |
| exact-match (OpenHands) | 0.00 | 0.00 | — |
| step-cap (LangGraph 10007) | 0.00 | 0.00 | — |

`plateau_idempotent` is the first detector in this project's history to reach
recall 1.00 with zero false trips on these traces. **It does not survive real
traces** — see TRAIL above, where nothing reaches recall 1.00 with zero false
trips and Plateau's false-trip rate is 0.54. Treat this table as a
statement about traces we wrote, because that is what it is.

### Our worst numbers, stated plainly

**Lexical still detects sooner than we do: 8.00 turns against 13.67.** On
`runaway_paraphrase_loop` it fires at turn 8 where we fire at 9; on
`unreachable_target`, turn 8 against our 12. If your cost model is tokens burned
before the breaker opens, a 2019-era Jaccard detector beats us on every trace it
can see at all. What it cannot see is the reworded stall — it misses
`paraphrase_loop_varied_wording` completely, where consecutive observations
share no vocabulary.

**The similarity dial still buys nothing but latency.** `plateau_novelty_only`
pins `action_sim` to 0 and matches full Plateau on recall (1.00), on false-trip
rate (0.50), and on every trip except turns-to-detection — 15.67 against 13.67.
Measured three times now, at two window sizes and two trace lengths, always the
same answer. The pitch is a two-dial design; the evidence supports a one-dial
detector with a similarity dial that saves about two turns. That gap is real and
we have not closed it.

**The `idempotent` declaration is a burden, not a capability.** It is what moves
false-trip from 0.50 to 0.00, and it is a promise the *tool author* makes, not
something Plateau detects. Nothing stops a deployer forgetting it, and if they
do, their healthy poller trips at turn 10. The same exemption offered to
`exact_args` would remove that baseline's poller false trip too. It is reported
as a separate row for exactly that reason.

**The paraphrase win may be an artifact of how we wrote the fixture.**
`paraphrase_loop_varied_wording` cycles 12 dead-end phrasings, so a window of 12
or more is guaranteed to see a repeat. Whether real agents cycle within a
bounded repertoire is not something any trace in this repository can answer.

## Fixture results

Six-turn productive preamble, then the pattern under test.
`metrics.json → detector_fixtures`.

| Fixture | Quadrant | Trip turn | Action sim | Obs novelty |
|---|---|---|---|---|
| 1 — paraphrase loop | LOOP | **3** | 0.8927 | 0.0000 |
| 2 — invoice batch (counter-demo) | GRIND | — | 0.9913 | 0.4392 |
| 3a — identical error strings | LOOP (migrates thrash→loop) | **6** | 0.7818 | 0.0000 |
| 3b — varied error strings | THRASH (does NOT trip) | — | 0.7397 | 0.2114 |

Fixture 2 is the counter-demo: action_sim 0.9913 clears the ceiling, so
similarity alone condemns it. It survives because novelty 0.4392 is above the
floor. That is the joint design earning its place.

### What changed, and why the old "0 of 144" was meaningless

Fixtures 1 and 2 used to be **two turns long**. Turn 0 of fixture 1 is not
stagnant — its non-answer is novel against the *preamble*, novelty 0.8974 — so
`loop_hits` peaked at 1 against a grid whose smallest threshold was 2. The
fixture could not trip at any setting, and the sweep dutifully reported **0
usable configurations out of 144**. That number measured trace length and
nothing else.

The old README gave the wrong reason for it, too. Limitation 4 claimed "every
trip threshold is ≥ 3"; `eval/sweep.py` sweeps `trip_after_loop = 2`. The stated
explanation was not the real one.

Both fixtures are now six turns — **both**, deliberately. Lengthening only the
positive one would have bought recall for free. `metrics.json → sweep` now
reports **416 of 576 configurations usable (72.2%)**, max recall 1.00.

Note that the fixture sweep still cannot decide `window_size`: the longest
fixture is 7 turns, so a window of 8 and a window of 24 hold identical contents
and every window value comes back usable for want of anything to disagree about.
That is why `long_trace_sweep` exists.

## The novelty floor: a contradiction, resolved

`NOVELTY_FLOOR` was 0.30, justified by a docstring saying it "sits above the
poller band and below batch." The second half was false against our own
measurement. `metrics.json → novelty_floor_probe`:

| class | n | min | max |
|---|---|---|---|
| true_loop | 3 | 0.0000 | 0.0000 |
| poller | 6 | 0.0067 | 0.2311 |
| batch | 5 | 0.2572 | 0.5063 |
| progress | 2 | 0.6100 | 0.9496 |

Batch *starts* at 0.2572, so 0.30 sat above the bottom of the batch band and
read three of five measured batch observations as stagnant. The usable window is
**(0.2311, 0.2572)**, width 0.0260, and of the four grid values only **0.25**
falls inside it.

The probe block had also gone stale — it still described a 0.15 candidate long
after the code moved to 0.30, so the one "survives" verdict in `metrics.json`
referred to a value no longer in the code. `scripts/novelty_floor_check.py` now
imports the constant instead of restating it.

The floor is now **0.25**, and the probe reports `candidate_floor_survives:
true`. Neither `sweep` nor `long_trace_sweep` discriminates — every floor value
is usable in both — but that is a property of their range, not of the floor:
both stop at 0.40. `eval/floor_sweep.py` pushes it to 0.80 and finds the edge.

### Where the floor actually stops working

`metrics.json → floor_sweep`. The same five axes as `long_trace_sweep`, over the
same 16–61 turn classes, with `novelty_floor` swept to 0.80 — 864 configurations.

| floor | usable configs (of 108) |
|---|---|
| 0.20 | 81 |
| **0.25** | **81** |
| 0.30 | 81 |
| 0.40 | 81 |
| 0.50 | 18 |
| 0.60, 0.70, 0.80 | **0** |

So the floor *is* load-bearing once you look above 0.40, and the shipped
configuration — floor 0.25, `trip_after_loop` 3, `trip_after_stall` 6, window 16
— is usable at every swept `k_sigma`. `metrics.json → floor_sweep_fine` resolves
the edge at 0.02: usable through **0.48**, nothing usable from **0.50** up.

**The floor and the window are not independent**, which is the part neither
earlier sweep could see. From `floor_sweep_fine`, holding `trip_after_loop` at
its committed 3:

| window | usable floors |
|---|---|
| 8 | 0.44 – 0.48 |
| 12 | 0.40 – 0.48 |
| 16 | 0.40 – 0.46 |
| 24 | 0.40 – 0.44 |

A short window needs a *higher* floor to see the repetition at all; a long window
needs a *lower* one, because more history means more chances for healthy work to
read as stagnant. `long_trace_sweep` reports every `window_size = 8`
configuration failing, and that is true — across the floors *it* sweeps. Raising
the floor to 0.44 buys window 8 back. That is not a recommendation to ship a
window of 8; it is the reason the two parameters have to be quoted together.

### The floor is not a separation margin

`metrics.json → separation_margin`. At the committed floor of 0.25 the healthy
and stalled novelty distributions do separate — but the number that matters is
how much room is left, and there is almost none:

| trace | min novelty | distance below floor | longest stagnant run | held by |
|---|---|---|---|---|
| `healthy_invoice_batch` | 0.24941 | **0.00059** | 1 (of 6) | counter margin |
| `healthy_poller` | 0.084191 | 0.165809 | 28 (of 6) | `idempotent` declaration |

The healthy batch's closest turn sits **0.00059 below** the floor — it already
reads as stagnant. It survives because that happens once in 55 turns and tripping
needs six *consecutive*. The safety of the design rests on a counter margin of
five turns, not on a threshold with room in it, and those are different claims.

The poller has no margin at all: a run of 28 against a threshold of 6. It is held
up entirely by its declaration, which is the same point made under
`long_trace_comparison` expressed as a quantity.

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

## Documented limitations

1. **Fixture 3b (varied error strings) is still a known miss.** At three turns
   it is too short for the window to help: lexically varied failure messages
   read as new information on short-string embeddings. Kept honest by
   `test_fixture_3b_varied_errors_is_a_known_miss`. The 61-turn version of the
   same pattern *is* now caught, which tells you the fix is length and memory,
   not thresholds.

2. **Polling tools must declare `idempotent: true`.** Measured pollers span
   0.0067–0.2311, overlapping the loop band, and no floor can separate them — a
   poller is informationally stalled by construction. This is now implemented
   (`Detector.evaluate(..., idempotent=True)` holds the hit counters rather than
   advancing or resetting them) rather than being prose, but it remains a
   deployment burden the caller carries. See "Our worst numbers" above.

3. **No thrash floor.** Three different tools score 0.7397, so `mu − k·σ` cannot
   find a low-similarity region that does not exist. Not patched with a
   constant.

4. **The embedding ceiling is real and unsolved.** MiniLM cannot distinguish
   `read_file` from `grep` from `list_dir` — they read 0.7397 mutual similarity.
   For tool-call strings, the exact domain where the novelty signal matters
   most, the encoder has no low-similarity region at all. Every result here
   inherits that limit.

5. **`window_size` is provisional.** The sweep says 12, 16 or 24; it cannot say
   which, because that depends on how many distinct ways a real agent rewords
   itself before repeating. See the caveat under "The result that matters most."

6. **On real traces, Plateau false-trips more than half of healthy runs.**
   Recall 0.63, false-trip 0.54 on TRAIL under the `primary` mapping — against
   0.00 false trips on our own traces. No detector reaches recall 1.00 with zero
   false trips on real data. This is the single biggest open problem and it is
   not close. See the TRAIL section for the five things wrong with the benchmark
   itself, which are also real.

7. **The synthetic traces flattered us and we could not have known that from
   them.** Every hand-written trace can only confirm what its author already
   believed. The gap between the two tables above is the argument for never
   quoting the synthetic ones alone.

## Reproducibility, and the limit of it

`scripts/check_env.py --probe` reports whether this machine can reproduce the
committed numbers. Two things it now gets right that it did not before:

- The **encoder revision has two homes** — `models/encoder_revision.txt`, which
  the runtime reads, and `pyproject.toml [tool.plateau]`, which only scripts
  read. They could silently disagree. That is now a failure, not a warning.
- **`probe_sha256` was overstating the problem.** It hashes raw float32 bytes,
  so a single last-bit difference from a different CPU or BLAS produces a
  completely unrelated digest. Measured across this project's two development
  machines the raw digests differ — while the published cosines differ by at
  most 1e-6 and every figure quoted to four decimal places is identical.
  `fingerprint()` now also records `probe_sha256_round6`, which survives float
  noise and still moves if the weights or pooling change.

So: **the numbers reproduce; a byte-identical `metrics.json` across machines
does not, and cannot.** Rule 3 holds per machine. The pins are still worth
having — `python3.11 -m venv .venv-pinned` and the set in `pyproject.toml` — but
they are not what makes the results stable, and it is better to say so than to
let a red check train people to ignore it.

## Parameters

| Parameter | Value | Owned by | Status |
|---|---|---|---|
| `NOVELTY_FLOOR` | 0.25 | `novelty_floor_probe` | only grid value inside the measured window; `floor_sweep` puts the usable range at 0.20–0.48 and confirms 0.25 |
| `WINDOW_SIZE` | 16 | `long_trace_sweep` | usable set {12, 16, 24}; provisional pending TRAIL. `floor_sweep` shows the usable floor range narrows as this grows |
| `K_SIGMA` | 1.0 | `long_trace_sweep` | every swept value usable |
| `TRIP_AFTER_LOOP` | 3 | `long_trace_sweep` | every swept value usable |
| `TRIP_AFTER_STALL` | 6 | `long_trace_sweep` | every swept value usable |

## Running it

```bash
python3.11 -m venv .venv-pinned && . .venv-pinned/bin/activate
pip install -e '.[dev,demo]'
python scripts/check_env.py --probe

python -m pytest                          # 165 passed, 2 skipped
python scripts/detector_fixtures.py       # the four §6 fixtures
python eval/sweep.py                      # 576 configs over the fixtures
python scripts/long_trace_sweep.py        # 576 configs over 16-61 turn traces
python eval/floor_sweep.py                # 864 configs, floor swept to 0.80
python eval/floor_sweep.py --fine         # the same edge resolved at 0.02
python eval/separation_margin.py          # what the floor's headroom actually is
python scripts/long_trace_comparison.py   # nine detectors, five classes
python scripts/check_readme.py            # every figure above traces to a measurement

hf auth login                             # TRAIL is gated; approval is instant
python scripts/fetch_trail.py
python scripts/trail_comparison.py        # the only numbers about real agents
```
