"""`agent-loop-detector` lexical baseline.

=============================================================================
PROVENANCE
-----------------------------------------------------------------------------
Ported from:
    agent-loop-detector 0.1.0 (PyPI sdist; no public VCS repository located)
    agent_loop_detector/similarity.py  (jaccard_similarity, tokenize)
    agent_loop_detector/detector.py    (LoopDetector.check, published defaults)
Licence: MIT

Rule 6 required reading this before describing it as lexical. It **is** lexical
and the technical approach's description is confirmed: `similarity.py` implements
Jaccard over word sets, a **term-frequency** cosine over bag-of-words counters,
and normalised Levenshtein, under a module docstring reading "no external
dependencies". No embedding model is involved.

Its `cosine_similarity` is TF-based. A source comment describes Jaccard and
TF-cosine as "both good for semantic similarity" — lexical token overlap is
precisely what Plateau argues is not semantic similarity, which is why this
baseline belongs in the comparison.

Published defaults (`LoopDetector.__init__`), used unmodified — no strawman:
    similarity_threshold = 0.85
    window_size          = 10
    max_consecutive      = 3
    algorithm            = 'jaccard'

IMPORTANT: upstream's entry point is `check(self, output)` — a **single**
argument. It reads only the observation and never sees the action, the mirror
image of an action-only detector. This port preserves that: it reads
`turn.observation` and ignores `turn.action_name` / `turn.action_input`
entirely. Feeding it the action would make it a different detector.

`tokenize` and `jaccard_similarity` are reimplemented here (four lines each)
rather than imported, so the evaluation has no runtime dependency on an
unpinnable sdist. The semantics are identical.
=============================================================================
"""

from __future__ import annotations

import re
from typing import Sequence

from eval.baselines._turn import BaselineTurn

# --- Published defaults ------------------------------------------------------
SIMILARITY_THRESHOLD = 0.85
WINDOW_SIZE = 10
MAX_CONSECUTIVE = 3
ALGORITHM = "jaccard"


def tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric. Upstream `similarity.py:12`."""
    return re.findall(r"\b\w+\b", text.lower())


def jaccard_similarity(text1: str, text2: str) -> float:
    """Upstream `similarity.py:18`, including its empty-string conventions."""
    tokens1 = set(tokenize(text1))
    tokens2 = set(tokenize(text2))
    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0
    return len(tokens1 & tokens2) / len(tokens1 | tokens2)


def detect(
    turns: Sequence[BaselineTurn],
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    window_size: int = WINDOW_SIZE,
    max_consecutive: int = MAX_CONSECUTIVE,
) -> int | None:
    """Return the 0-indexed turn at which `check()` would raise, else None.

    Mirrors upstream: each output is compared against the most recent one; a
    similarity at or above the threshold increments a consecutive counter, and
    anything below resets it. The detector fires when the counter reaches
    `max_consecutive` (upstream counts the current output in that total).
    """
    outputs: list[str] = []
    consecutive_similar = 0

    for index, turn in enumerate(turns):
        output = turn.observation

        if outputs:
            recent_similarity = jaccard_similarity(output, outputs[-1])
            if recent_similarity >= similarity_threshold:
                consecutive_similar += 1
            else:
                consecutive_similar = 0

        outputs.append(output)
        if len(outputs) > window_size:
            outputs.pop(0)

        # Upstream: "consecutive_similar includes current" (detector.py:165-166).
        if consecutive_similar + 1 >= max_consecutive and consecutive_similar > 0:
            return index

    return None
