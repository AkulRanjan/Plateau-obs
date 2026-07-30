# Third-Party Notices

Plateau builds on other people's work. Everything below is either a runtime
dependency, a model used as published, or source we ported. Ported functions
also carry an inline provenance header at their definition site naming the
source repository, file, commit SHA, and licence.

This file is maintained **as work lands**, not at the end.

Status legend: `IN USE` — present in the tree now. `PLANNED` — named in the
technical approach, not yet in the tree. Nothing is listed as IN USE before it
exists.

---

## Models

### sentence-transformers/all-MiniLM-L6-v2 — `IN USE`

- **Source:** https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
- **Licence:** Apache-2.0
- **Pinned revision:** `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`
- **Used by:** `plateau/encoder.py`
- **Modifications:** none. The encoder is used exactly as published and is
  **not fine-tuned**. Weights are downloaded once into `models/` (gitignored)
  and loaded from that local snapshot thereafter.

Cite as Reimers & Gurevych, *Sentence-BERT: Sentence Embeddings using Siamese
BERT-Networks*, EMNLP 2019, arXiv:1908.10084.

---

## Runtime dependencies

| Package | Version | Licence |
| --- | --- | --- |
| `sentence-transformers` | 3.3.1 | Apache-2.0 |
| `transformers` | 4.57.6 | Apache-2.0 |
| `tokenizers` | 0.22.2 | Apache-2.0 |
| `safetensors` | 0.8.0 | Apache-2.0 |
| `torch` | 2.5.1 | BSD-3-Clause |
| `numpy` | 2.2.6 | BSD-3-Clause |
| `pytest` (dev only) | 8.3.4 | MIT |

---

## Ported baseline detectors — `PLANNED`

Plateau's evaluation compares against shipped detectors rather than strawmen.
Each is ported with its **published defaults**. None are in the tree yet; each
entry below is filled in with the cloned commit SHA at port time.

| Baseline | Upstream | Licence | Cloned commit SHA | Status |
| --- | --- | --- | --- | --- |
| Exact match | `OpenHands/software-agent-sdk`, `openhands-sdk/openhands/sdk/conversation/stuck_detector.py` (`StuckDetector`, `_event_eq`) | MIT | `4b132eddb6cf414841439a46ce42ed2cd66a628a` | CLONED + READ, not yet ported |
| Exact args / debounce | published spec at [dev.to/aws](https://dev.to/aws/how-to-prevent-ai-agent-reasoning-loops-from-wasting-tokens-2652); cross-referenced against `aws-samples/sample-why-agents-fail` where the hook is **referenced but not shipped** | MIT-0 (referenced repo) | `08beccadbf753b699465234e52c0a48e087c6606` | **PORTED** → `eval/baselines/exact_args.py` |
| Step cap | `langchain-ai/langgraph`, `libs/langgraph/langgraph/pregel/_loop.py` + `errors.py` + `_internal/_config.py` (recursion limit) | MIT | `41341457342327166d72fc11952ab28fb61ec0bf` | **PORTED** → `eval/baselines/step_cap.py` |
| Lexical | `agent-loop-detector` 0.1.0 (PyPI sdist) — **read; the "lexical" description is confirmed** | MIT | sdist 0.1.0 (no public VCS ref found) | DOWNLOADED + READ, not yet ported |
| Action-only Plateau | this repo (ablation, not a port) | Apache-2.0 | n/a | PLANNED |

Five baselines, not six. The LangGraph recursion limit **is** the step-cap
baseline; there is no separate generic step-cap entry. `LimitToolCounts` from
`sample-why-agents-fail` is a per-tool call-count cap that was read during this
work and is credited below as a **reference, not a baseline**.

Each entry below records what the source actually does, read at the SHA given.
Where that differs from the technical approach, the difference is stated here
rather than silently reconciled.

#### OpenHands `StuckDetector` — exact-match baseline

Retraction: an earlier revision of this file claimed no repository existed at
`software-agent-sdk`. That was wrong. The repository is
**`OpenHands/software-agent-sdk`** — the technical approach's name was correct;
the `All-Hands-AI` organisation was this file's own error. `All-Hands-AI/agent-sdk`
redirects to the same repository (verified: identical HEAD SHA and a
byte-identical `stuck_detector.py`).

**Published defaults**, from `openhands-sdk/openhands/sdk/conversation/types.py`
(`StuckDetectionThresholds`). These are the values the baseline gets — no strawmen:

| Parameter | Default |
| --- | --- |
| `action_observation` | 4 |
| `action_error` | 3 |
| `monologue` | 3 |
| `alternating_pattern` | 6 |
| `MAX_EVENTS_TO_SCAN_FOR_STUCK_DETECTION` | 20 |

It implements **five** scenarios, not one: repeating action-observation,
repeating action-error, agent monologue, alternating action-observation (an
A-B-A-B pattern), and a context-window-error loop. Scenario 1 requires
`actions_equal` **and** `observations_equal`, both via `_event_eq` — so it reads
**both halves** of a turn, using exact equality. The honest contrast with Plateau
is exact-string vs semantic, not action-only vs both-halves.

#### Exact-args debounce — implemented from a published specification

Ported to `eval/baselines/exact_args.py`. **No code was copied, because there is
no upstream source to copy.** It is an independent implementation of the
specification published at
<https://dev.to/aws/how-to-prevent-ai-agent-reasoning-loops-from-wasting-tokens-2652>,
written to the published parameters:

| Parameter | Published value |
| --- | --- |
| key | `(tool_use["name"], json.dumps(tool_use["input"]))` |
| `window_size` | 3 |
| block threshold | key appears ≥ 2 times in the window |

`json.dumps` is called **without** `sort_keys`, matching the published spec
verbatim. The key is therefore sensitive to dict insertion order. That is a real
property of the published design and is left intact; correcting it would make
this a different detector than the one being compared against.

**Discrepancy.** The technical approach cites this as a `DebounceHook` in
`aws-samples/sample-why-agents-fail`. That repository contains no such class and
states its absence outright. Verified by grep at
`08beccadbf753b699465234e52c0a48e087c6606` — one hit in the entire tree, and it
is a denial:

```
stop-ai-agents-wasting-tokens/03-reasoning-loops-demo/images/generate_ambiguous_feedback.py:5:
    SUCCESS/FAILED states + LimitToolCounts hard ceiling). No DebounceHook.
```

The spec for this baseline was written from the blog post, not from that
repository. Recorded here so the blog post is credited as the actual source.

#### LangGraph recursion limit — step-cap baseline

Ported to `eval/baselines/step_cap.py`. Verified by reading the source at
`41341457342327166d72fc11952ab28fb61ec0bf`:

| Fact | Source location | Value |
| --- | --- | --- |
| trip condition | `pregel/_loop.py:607` | `if self.step > self.stop:` → `status = "out_of_steps"` |
| bound | `pregel/_loop.py:1701`, `:1961` | `self.stop = self.step + self.config["recursion_limit"] + 1` |
| initial counters | `pregel/_loop.py:301-302` | `self.step = 0`, `self.stop = 0` |
| exception | `errors.py:67` | `class GraphRecursionError(RecursionError)` |
| default limit | `_internal/_config.py:32` | **10007**, env-overridable |

The `step > stop` check and the `step + recursion_limit + 1` bound are confirmed
exactly as specified. Note the consequence: steps `0` through `limit + 1` all
pass, so the trip lands on step `limit + 2` — an off-by-two against a naive
"stops after N steps" reading, reproduced faithfully in the port.

**CONFIRMED: it performs no comparison of action or observation content.**
`step` and `stop` are plain integers threaded through `prepare_next_tasks`. A
grep across `_loop.py` and `_algo.py` for similarity / jaccard / levenshtein /
embed / cosine / content comparison returns nothing. The single `deduplicate`
hit (`_loop.py:419`) is last-write-wins merging of channel writes — state
reconciliation, not turn comparison. LangGraph counts supersteps and stops.

**Discrepancy on the default.** The port instruction specified 25. The source
ships `DEFAULT_RECURSION_LIMIT = int(getenv("LANGGRAPH_DEFAULT_RECURSION_LIMIT", "10007"))`.
25 is widely documented for LangGraph and is retained as the harness default, but
10007 is what the source says at this commit and the port exposes both. A
`git log -S` over the shallow clone did not reach a revision where the value was
25, so no claim is made here that upstream changed it — only what the source says
now. This matters for the results table: at 10007 the detector never fires on any
trace of realistic length, so its recall is zero by construction; at 25 it fires
at a fixed offset regardless of agent behaviour.

Caveat carried into the port: `recursion_limit` counts **supersteps**, not tool
calls, and a superstep may run several nodes in parallel. The port maps one trace
turn to one superstep, which is the most favourable reading for the baseline —
any other mapping makes it fire later, not earlier.

#### Strands `LimitToolCounts` — reference, not a baseline

Read at `08beccadbf753b699465234e52c0a48e087c6606`, credited but **not** used as
a baseline. Its own docstring calls it "the official recipe from the Strands
Hooks Cookbook — copied here verbatim"; Strands does not ship it as an
importable symbol. It is a **per-tool call-count cap** — it counts invocations
per tool name per agent invocation and cancels further calls via
`event.cancel_tool = "<message>"`. `max_tool_counts` has no default; the
repository's own demos use 3 (`chat_guarded.py`) and 2
(`test_reasoning_loops.py`).

It is credited because it is where Plateau's escape-vector delivery mechanism
was confirmed in real shipped code rather than inferred from a dataclass: a
string assigned to `cancel_tool` becomes a tool result with error status and
returns to the agent.

#### `agent-loop-detector` — lexical baseline

Rule 6 required reading this before calling it lexical. **It is lexical**, and
the technical approach's description is confirmed. `similarity.py` implements
Jaccard over word sets, a **term-frequency** cosine (bag-of-words counters, not
embeddings), and normalised Levenshtein, with a module docstring stating "no
external dependencies". No embedding model is involved.

Note for the README's prior-art paragraph: its `cosine_similarity` is
TF-based, and a source comment calls Jaccard and TF-cosine "both good for
semantic similarity". Lexical overlap is precisely what Plateau argues is not
semantic similarity, so this is worth naming carefully and without mockery.

Its public entry point is `check(self, output)` — a **single** argument. It reads
only the observation and never sees the action, which is the mirror image of an
action-only detector.

**Published defaults**, from `LoopDetector.__init__`:

| Parameter | Default |
| --- | --- |
| `similarity_threshold` | 0.85 |
| `window_size` | 10 |
| `max_consecutive` | 3 |
| `algorithm` | `'jaccard'` |

---

## Corrections to our own pitch materials

Kept in this file, next to the attribution it corrects, so it cannot be lost
between the deck and the README. Every line below was verified by reading source
at the SHAs recorded above.

**1. "All four incumbents compare exact strings" — wrong.** Slides 02 and 06 of
`Plateau_FRONTIER_2026` claim all four shipped systems match exact strings.
LangGraph compares **nothing at all**. Its recursion limit is a pure superstep
counter with no inspection of action or observation content (confirmed above).
Two of the four do not compare strings in the claimed way either: LangGraph
compares nothing, and `agent-loop-detector` compares *lexical token overlap*
(Jaccard / TF-cosine / Levenshtein), which is not exact-string matching.

**2. "They all read only the action" — wrong, in two directions.** OpenHands
`StuckDetector` scenario 1 requires `actions_equal` **and** `observations_equal`,
so it reads both halves. `agent-loop-detector`'s entry point is `check(output)` —
a single argument — so it reads only the *observation* and never sees the action.

**The accurate claim, which is narrower and survives a judge opening the
source:** of the four shipped systems, one reads both halves but only by exact
equality, one reads only the observation and only lexically, one counts actions
per tool, and one counts supersteps and reads neither half. **None compares both
halves semantically.** That is the gap.

**3. Organisation-name retraction.** An earlier revision of *this file* claimed
no repository existed at `software-agent-sdk`. That was this file's error, not
the technical approach's: the repository is `OpenHands/software-agent-sdk` and
the cited name was correct. See the exact-match section above.

---

## Unresolved

- **`agent-loop-detector` upstream VCS.** Read from the PyPI sdist (0.1.0, MIT).
  No public source repository was located, so the sdist is the provenance anchor.
- **`DEFAULT_RECURSION_LIMIT` history.** The shallow clone could not establish
  whether LangGraph's default was ever 25. Stated as "10007 at this commit" only.

### Strands Agents SDK — `CLONED` (adapter reference, no code ported)

- **Source:** `strands-agents/sdk-python`
- **Cloned commit SHA:** `aae087d6d79d0107cc1f4385a463d188e85bcc50`
- **Read for:** the real `BeforeToolCallEvent` / `AfterToolCallEvent` signatures
  in `strands-py/src/strands/hooks/events.py`, and `ToolUse` / `ToolResult` in
  `strands-py/src/strands/types/tools.py`.
- **Modifications:** none; nothing ported. Plateau's adapter targets these
  signatures as read, not as assumed.

`BeforeToolCallEvent` carries `tool_use` (the action) but **no** observation; the
observation is on `AfterToolCallEvent.result`. An adapter must therefore register
on both events. `cancel_tool: bool | str` is writable and a string value becomes
a tool result with error status — a native channel for Plateau's escape vector,
confirmed in real use by `LimitToolCounts` above.

---

## Datasets

### PatronusAI/TRAIL — `PLANNED, NEVER VENDORED`

- **Paper:** Deshpande et al., *TRAIL: Trace Reasoning and Agentic Issue
  Localization*, 2025, arXiv:2505.08638
- **Dataset:** `PatronusAI/TRAIL` — 148 human-annotated agent traces
- **Access:** gated. Its terms forbid resharing.
- **Handling:** downloaded by a human into `data/trail/`, which is gitignored.
  This repository contains **no** TRAIL data and no script that downloads it.
  Derived numbers may be published; trace content may not.

---

## Referenced work (not code)

Cited for framing and prior art; no source ported from these.

- Cemri et al., *Why Do Multi-Agent LLM Systems Fail?*, 2025, arXiv:2503.13657.
  The MAST taxonomy; Step Repetition is failure mode 1.3.
- OpenHands issue [#5355](https://github.com/All-Hands-AI/OpenHands/issues/5355),
  "Loop detection kills agents that are waiting on long-running processes".
- OpenHands issue [#5480](https://github.com/All-Hands-AI/OpenHands/issues/5480),
  "Cannot recover from Agent stuck in loop".
