"""Deterministic, offline, in-process sentence encoder.

Plateau's whole claim is that it reads *meaning*, not strings. Everything
downstream (novelty, similarity, the four quadrants, the breaker) is a function
of the vectors this module produces, so this module has three hard obligations:

1. Offline after first use. `load()` resolves the model from a local snapshot
   under ``models/``. Once that snapshot exists there is no network call in the
   decision path, and no LLM API is involved at any point (rule 2).
2. Deterministic. Fixed seed 1337, pinned model revision, ``eval()`` mode,
   ``inference_mode``, single-threaded, CPU. Two runs must produce identical
   vectors bit-for-bit (rule 3).
3. Countable. Every encode increments ``n_encode_calls`` / ``n_texts_encoded``.
   The breaker must prove it performs *zero* embedding work while OPEN, and the
   only honest way to prove that is to count.

The encoder is used as published and is not fine-tuned.
"""

from __future__ import annotations

import hashlib
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

# --- Determinism contract ----------------------------------------------------
# Mirrors [tool.plateau] in pyproject.toml. Kept as module constants so that
# importing plateau.encoder is enough to reproduce a run.
SEED = 1337
MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
ENCODER_DIM = 384

#: Absolute path to the local weight cache. Gitignored (rule 5).
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

#: Written by ``scripts/pin_encoder.py`` after the one-time download, read back
#: here. ``None`` means "not yet pinned" -- never a plausible-looking guess.
_REVISION_FILE = MODELS_DIR / "encoder_revision.txt"


def pinned_revision() -> str | None:
    """Return the pinned encoder commit SHA, or None if not yet recorded."""
    if not _REVISION_FILE.exists():
        return None
    text = _REVISION_FILE.read_text(encoding="utf-8").strip()
    return text or None


def _seed_everything(seed: int = SEED) -> None:
    """Pin every RNG that could touch a forward pass."""
    import torch

    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    # Single thread: multi-threaded CPU reduction order is not reproducible.
    torch.set_num_threads(1)


@dataclass(frozen=True)
class TurnText:
    """The two halves of an agent turn, rendered to text for embedding.

    Plateau reads *both* halves. Action similarity alone cannot distinguish a
    stuck loop from a batch job, which is precisely the gap in every shipped
    repetition detector.
    """

    action: str
    observation: str


class MiniLMEncoder:
    """all-MiniLM-L6-v2, in process, on CPU, normalised output.

    Vectors are L2-normalised at encode time, so cosine similarity is a plain
    dot product and ``cosine()`` never re-normalises. Callers may rely on
    ``float32`` output of shape ``(n, 384)``.
    """

    def __init__(
        self,
        model_id: str = MODEL_ID,
        revision: str | None = None,
        cache_dir: Path | None = None,
        allow_download: bool = False,
    ) -> None:
        self.model_id = model_id
        self.revision = revision if revision is not None else pinned_revision()
        self.cache_dir = Path(cache_dir) if cache_dir else MODELS_DIR
        self.allow_download = allow_download
        self._model = None

        # Instrumentation. Read by the breaker's zero-encode invariant test.
        self.n_encode_calls = 0
        self.n_texts_encoded = 0

    # -- lifecycle ------------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> "MiniLMEncoder":
        """Materialise the model. Idempotent.

        Raises if the local snapshot is missing and ``allow_download`` is False,
        rather than silently reaching for the network in a decision path.
        """
        if self._model is not None:
            return self

        _seed_everything(SEED)

        if not self.allow_download:
            # HF_HUB_OFFLINE makes any accidental fetch fail loudly instead of
            # quietly succeeding and breaking the offline-first guarantee.
            os.environ.setdefault("HF_HUB_OFFLINE", "1")

        from sentence_transformers import SentenceTransformer

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = SentenceTransformer(
            self.model_id,
            revision=self.revision,
            cache_folder=str(self.cache_dir),
            device="cpu",
        )
        self._model.eval()

        dim = self._model.get_sentence_embedding_dimension()
        if dim != ENCODER_DIM:
            raise RuntimeError(
                f"encoder dimension {dim} != pinned {ENCODER_DIM}; "
                "the pinned revision does not match the loaded model"
            )
        return self

    # -- encoding -------------------------------------------------------------

    def encode(self, texts: str | Sequence[str]) -> np.ndarray:
        """Encode text(s) to L2-normalised float32 vectors of shape (n, 384)."""
        import torch

        if isinstance(texts, str):
            texts = [texts]
        else:
            texts = list(texts)
        if not texts:
            return np.zeros((0, ENCODER_DIM), dtype=np.float32)

        self.load()
        self.n_encode_calls += 1
        self.n_texts_encoded += len(texts)

        with torch.inference_mode():
            vecs = self._model.encode(
                texts,
                batch_size=len(texts),
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        return np.ascontiguousarray(vecs, dtype=np.float32)

    def encode_one(self, text: str) -> np.ndarray:
        """Encode a single string to a 1-D vector of shape (384,)."""
        return self.encode([text])[0]

    def encode_turn(self, turn: TurnText) -> tuple[np.ndarray, np.ndarray]:
        """Encode both halves of a turn in one batched forward pass.

        Batching the pair keeps it at one encode call per turn, which is what
        the cost story in the README claims.
        """
        vecs = self.encode([turn.action, turn.observation])
        return vecs[0], vecs[1]

    # -- introspection --------------------------------------------------------

    def reset_counters(self) -> None:
        self.n_encode_calls = 0
        self.n_texts_encoded = 0

    def fingerprint(self) -> dict[str, object]:
        """Provenance block for metrics.json.

        Two hashes of the same fixed probe vector, because one was not enough to
        tell two very different failures apart.

        ``probe_sha256`` hashes the raw float32 bytes. It is exact, and that is
        both its value and its flaw: SHA-256 turns a one-ULP difference into a
        completely unrelated digest. Measured across this repo's two development
        machines, the raw hash differs (024c4c5f... vs aaca066b...) while the
        published cosines differ by at most 1e-6 and every figure quoted at four
        decimal places is identical. The exact hash was therefore reporting
        reproducible results as unreproducible, which is the failure mode most
        likely to get a determinism check switched off.

        ``probe_sha256_round6`` hashes the vector rounded to six decimals. It
        survives last-bit float noise from a different CPU or BLAS, and still
        moves if the weights, the revision or the pooling ever change -- which
        is the drift the check exists to catch.

        Both are recorded. Neither is dropped: an exact match is still the
        strongest signal available, it just is not the only meaningful one.
        """
        probe = self.encode_one("plateau determinism probe")
        rounded = np.round(probe.astype(np.float64), 6)
        return {
            "model_id": self.model_id,
            "revision": self.revision,
            "dim": ENCODER_DIM,
            "seed": SEED,
            "probe_sha256": hashlib.sha256(probe.tobytes()).hexdigest(),
            "probe_sha256_round6": hashlib.sha256(rounded.tobytes()).hexdigest(),
        }


# --- vector helpers ----------------------------------------------------------


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D vectors.

    Handles un-normalised input for safety, but is a dot product for vectors
    produced by :meth:`MiniLMEncoder.encode`.
    """
    a = np.asarray(a, dtype=np.float32).ravel()
    b = np.asarray(b, dtype=np.float32).ravel()
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def max_cosine(vec: np.ndarray, others: Iterable[np.ndarray]) -> float:
    """Highest cosine similarity between ``vec`` and any vector in ``others``.

    Returns 0.0 for an empty ``others`` -- the neutral "nothing to compare
    against yet" reading, used on the first turn of a run.
    """
    best = 0.0
    seen = False
    for other in others:
        seen = True
        best = max(best, cosine(vec, other))
    return best if seen else 0.0
