"""Ported baseline detectors.

Every baseline exposes ``detect(turns) -> int | None``, the 0-indexed turn at
which it would have fired, or None. Each carries a provenance header naming its
source repository, file, commit SHA, and licence, and each is given its
published defaults.
"""

from eval.baselines._turn import BaselineTurn

__all__ = ["BaselineTurn"]
