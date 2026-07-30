"""Plateau -- a semantic circuit breaker for autonomous AI agents.

Plateau watches progress instead of failures. It asks "is the agent still
learning anything new?" rather than "is the agent repeating itself?".
"""

from plateau.encoder import (
    ENCODER_DIM,
    MODEL_ID,
    SEED,
    MiniLMEncoder,
    TurnText,
    cosine,
    max_cosine,
    pinned_revision,
)

__version__ = "0.1.0"

__all__ = [
    "ENCODER_DIM",
    "MODEL_ID",
    "SEED",
    "MiniLMEncoder",
    "TurnText",
    "cosine",
    "max_cosine",
    "pinned_revision",
    "__version__",
]
