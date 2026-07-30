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

| Baseline | Upstream | Licence | Commit SHA | Status |
| --- | --- | --- | --- | --- |
| Exact match | OpenHands `software-agent-sdk`, `openhands-sdk/openhands/sdk/conversation/stuck_detector.py` (`_event_eq`) | MIT | TBD | PLANNED |
| Exact args / debounce | `aws-samples/sample-why-agents-fail`, Strands `DebounceHook`, keyed on `(tool_name, json.dumps(input))` | TBD | TBD | PLANNED |
| Step cap | TBD | TBD | TBD | PLANNED |
| Lexical | `agent-loop-detector` (PyPI) — **source to be read before it is described**; the technical approach calls it lexical and that claim gets verified, not assumed | TBD | TBD | PLANNED |
| Action-only Plateau | this repo (ablation, not a port) | Apache-2.0 | n/a | PLANNED |

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
