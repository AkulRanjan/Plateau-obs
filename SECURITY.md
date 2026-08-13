# Security Policy

## Reporting a vulnerability

Please report security issues privately, not in the public issue tracker.

Use [GitHub's private vulnerability
reporting](https://github.com/AkulRanjan/Plateau-obs/security/advisories/new),
or email **akulranjan06@gmail.com**.

Include what you were running, what you observed, and what an attacker could do
with it. You will get an acknowledgement within a week. This is a small project
maintained by one person, so please be patient with the timeline; you will be
credited in the advisory unless you prefer otherwise.

## Supported versions

The project is pre-1.0 and unreleased. Only `main` receives fixes.

## What is in scope

Plateau is a library and a local evaluation harness, not a hosted service, so
the interesting surface is narrower than it looks:

- **`plateau/`** — the detector, calibrator, breaker and encoder. A crash, an
  unbounded allocation, or a path where untrusted agent output reaches something
  other than the embedding model.
- **`demo/collector.py`** — the only component that listens on a socket. It is a
  demo collector intended for a trusted local network, and it is not hardened;
  see the note below.
- **Dependency and supply-chain issues** in the pinned set in `pyproject.toml`
  and `web/package-lock.json`.
- **`scripts/fetch_trail.py`** — anything that would cause gated dataset content
  to be written somewhere it could be committed or shared (rule 5).

## What is not a vulnerability

- **A detector miss or a false trip.** Plateau's recall and false-trip rates are
  measured, published and imperfect; `README.md` lists the classes it misses.
  An agent trace that gets past the breaker is a measurement result, not a
  security finding. Open a measurement dispute issue instead.
- **The `idempotent: true` declaration being trusted.** It is a promise the tool
  author makes and Plateau cannot verify. The README documents this as a burden
  on the caller rather than a capability. A deployer who omits it gets a false
  trip; one who wrongly asserts it gets a missed stall. Both are the documented
  design.
- **`demo/collector.py` accepting unauthenticated posts.** It is a demonstration
  collector for a trusted local network, not a production endpoint. Do not
  expose it to the internet. If you find something that lets it reach beyond
  its own process — writing outside its output directory, executing input —
  that *is* in scope.
- **Anything requiring an already-compromised machine**, since the model,
  weights and metrics all live on local disk by design.

## What Plateau is not

Plateau detects *information stagnation*. It is not a safety filter, a
jailbreak detector, a content classifier or a sandbox. It will not stop an agent
from doing something harmful; it stops one that has stopped learning. Do not
deploy it as a security control.
