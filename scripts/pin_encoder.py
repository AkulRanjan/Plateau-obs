"""One-time encoder download + revision pin.

This is the ONLY script in the repo permitted to touch the network. It downloads
the pinned snapshot into ``models/`` and writes the SHA to
``models/encoder_revision.txt`` and into ``[tool.plateau] encoder_revision`` in
pyproject.toml.

The SHA is *read from the resolved snapshot*, never typed by hand. After this
runs, every other entry point can operate with HF_HUB_OFFLINE=1.

    python scripts/pin_encoder.py            # fetch the revision already pinned
    python scripts/pin_encoder.py --repin    # resolve a NEW revision from the Hub

RE-PINNING IS NOT THE DEFAULT, AND THAT MATTERS
-----------------------------------------------
This script used to resolve the Hub's *current* default-branch SHA on every run
and rewrite pyproject.toml with it. That is right exactly once — the first time.
On any later run, if upstream had moved, it would silently re-pin to a different
revision than the one every number in metrics.json was generated against, and
nothing would fail. The determinism contract (rule 3) would be quietly void:
`encoder.fingerprint()`'s probe_sha256 would no longer match the committed one,
and no test asserts that it does.

So the default is now: if pyproject.toml already carries a revision, fetch
exactly that. Getting a new one requires ``--repin``, which says out loud that
metrics.json has to be regenerated afterwards.

This came up for real — a teammate needed the weights on a second machine, and
running this script unguarded would have re-pinned the project as a side effect
of what looked like a download.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from plateau.encoder import MODEL_ID, MODELS_DIR  # noqa: E402


def resolve_revision(model_id: str) -> str:
    """Ask the Hub for the current commit SHA of the default branch."""
    from huggingface_hub import HfApi

    info = HfApi().model_info(model_id)
    sha = info.sha
    if not sha:
        raise RuntimeError(f"Hub returned no commit SHA for {model_id}")
    return sha


def download_snapshot(model_id: str, revision: str) -> Path:
    """Download exactly ``revision`` into models/ and return the snapshot path."""
    from huggingface_hub import snapshot_download

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = snapshot_download(
        repo_id=model_id,
        revision=revision,
        cache_dir=str(MODELS_DIR),
        # Skip the duplicate weight formats; sentence-transformers prefers
        # safetensors and we do not want a 400 MB cache for a 90 MB model.
        ignore_patterns=["*.onnx", "*.ot", "*openvino*", "*.msgpack", "*.h5"],
    )
    return Path(path)


def pinned_revision() -> str | None:
    """The revision pyproject.toml already commits to, or None if unpinned."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^encoder_revision\s*=\s*"([^"]*)"', text, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("could not find encoder_revision in pyproject.toml")
    return match.group(1) or None


def write_revision_file(revision: str) -> Path:
    target = MODELS_DIR / "encoder_revision.txt"
    target.write_text(revision + "\n", encoding="utf-8")
    return target


def patch_pyproject(revision: str) -> bool:
    """Replace the encoder_revision value in pyproject.toml. Returns True if changed."""
    pyproject = ROOT / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    new_text, n = re.subn(
        r'^(encoder_revision\s*=\s*)"[^"]*"',
        lambda m: f'{m.group(1)}"{revision}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n != 1:
        raise RuntimeError("could not find encoder_revision in pyproject.toml")
    if new_text == text:
        return False
    pyproject.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and pin the encoder.")
    parser.add_argument(
        "--repin",
        action="store_true",
        help=(
            "resolve a NEW revision from the Hub and rewrite the pin. Every "
            "number in metrics.json must be regenerated afterwards."
        ),
    )
    args = parser.parse_args()

    print(f"model            : {MODEL_ID}")
    existing = pinned_revision()

    if existing and not args.repin:
        # The common case: someone needs the weights on another machine. Fetch
        # exactly what the project already commits to and change nothing.
        revision = existing
        print(f"pinned revision  : {revision}  (from pyproject.toml)")
    else:
        revision = resolve_revision(MODEL_ID)
        print(f"resolved revision: {revision}  (from the Hub)")
        if existing and revision != existing:
            print(
                f"\n  !! RE-PINNING {existing} -> {revision}\n"
                f"  !! Every number in metrics.json was produced by {existing[:12]}.\n"
                f"  !! They are now unreproducible until you re-run the harness.\n"
            )

    snapshot = download_snapshot(MODEL_ID, revision)
    print(f"snapshot         : {snapshot}")

    size = sum(f.stat().st_size for f in snapshot.rglob("*") if f.is_file())
    print(f"snapshot size    : {size / 1e6:.1f} MB")

    write_revision_file(revision)
    changed = patch_pyproject(revision)
    print(f"pyproject.toml   : {'updated' if changed else 'already pinned'}")

    print("\nPinned. All other entry points can now run with HF_HUB_OFFLINE=1.")
    if changed:
        print(
            "pyproject.toml changed, so metrics.json is now stale. Regenerate it\n"
            "before trusting any committed number."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
