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
| Step cap | `aws-samples/sample-why-agents-fail`, `stop-ai-agents-wasting-tokens/03-reasoning-loops-demo/hooks.py` (`LimitToolCounts`) | MIT-0 | `08beccadbf753b699465234e52c0a48e087c6606` | CLONED + READ, not yet ported |
| Lexical | `agent-loop-detector` 0.1.0 (PyPI sdist) — **read; the "lexical" description is confirmed** | MIT | sdist 0.1.0 (no public VCS ref found) | DOWNLOADED + READ, not yet ported |
| Exact args / debounce | **not located.** See "unresolved" below. | — | — | BLOCKED |
| Action-only Plateau | this repo (ablation, not a port) | Apache-2.0 | n/a | PLANNED |

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

#### Strands `LimitToolCounts` — step-cap baseline

The repository contains **no `DebounceHook`** and is not keyed on
`(tool_name, json.dumps(input))`. It contains `LimitToolCounts`, described in
its own docstring as "the official recipe from the Strands Hooks Cookbook —
copied here verbatim". A source comment in the same repo states explicitly:
"No DebounceHook."

`LimitToolCounts` is a **per-tool call-count cap**: it counts invocations per
tool name per agent invocation and cancels further calls via
`event.cancel_tool = "<message>"`. That makes it the **step-cap** baseline, not
the exact-args baseline.

`max_tool_counts` is a required constructor argument with **no default**. The
repository's own demos use `3` per tool (`chat_guarded.py`) and `2` per tool
(`test_reasoning_loops.py`); the port will use 3 and say so.

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

#### Unresolved

- **Exact-args / debounce baseline.** The cited source does not contain it.
  Either another upstream ships it or the technical approach conflated it with
  `LimitToolCounts`. Not ported until sourced; will not be hand-written and
  presented as someone else's shipped detector.
- **LangGraph.** Named as a fourth incumbent in the pitch but not yet cloned or
  read. Its mechanism is unverified and is described nowhere in this repo.

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
