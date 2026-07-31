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
recall 1.00 with zero false trips. It is the only one.

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
true`. Neither sweep discriminates — every floor value is usable in both — so
this probe is the only measurement with anything to say about it.

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

6. **Non-synthetic evaluation is not yet complete.** Every trace measured above
   is hand-written by us, which means it can only confirm what we already
   believed when we wrote it. `scripts/fetch_trail.py` and
   `scripts/trail_comparison.py` run all nine detectors against
   [TRAIL](https://huggingface.co/datasets/PatronusAI/TRAIL) — 148 real agent
   traces, expert-annotated — and write `metrics.json → trail_comparison`. TRAIL
   is gated and is never committed; `data/trail/` is gitignored. **Until that
   block exists in `metrics.json`, no number on this page is evidence about real
   agent behaviour.**

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
| `NOVELTY_FLOOR` | 0.25 | `novelty_floor_probe` | only grid value inside the measured window |
| `WINDOW_SIZE` | 16 | `long_trace_sweep` | usable set {12, 16, 24}; provisional pending TRAIL |
| `K_SIGMA` | 1.0 | `long_trace_sweep` | every swept value usable |
| `TRIP_AFTER_LOOP` | 3 | `long_trace_sweep` | every swept value usable |
| `TRIP_AFTER_STALL` | 6 | `long_trace_sweep` | every swept value usable |

## Running it

```bash
python3.11 -m venv .venv-pinned && . .venv-pinned/bin/activate
pip install -e '.[dev,demo]'
python scripts/check_env.py --probe

python -m pytest                          # 162 passed, 2 skipped
python scripts/detector_fixtures.py       # the four §6 fixtures
python eval/sweep.py                      # 576 configs over the fixtures
python scripts/long_trace_sweep.py        # 576 configs over 16-61 turn traces
python scripts/long_trace_comparison.py   # nine detectors, five classes
python scripts/check_readme.py            # every figure above traces to a measurement

hf auth login                             # TRAIL is gated; approval is instant
python scripts/fetch_trail.py
python scripts/trail_comparison.py        # the only numbers about real agents
```
