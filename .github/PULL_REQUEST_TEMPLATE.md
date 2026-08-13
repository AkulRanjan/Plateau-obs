## What this changes

<!-- One or two sentences. If a measurement moved, lead with that. -->

## What you measured

<!--
Not "what you changed" — what you ran, and what it said. If this PR touches
nothing measurable (docs, tooling, a typo), write "nothing measurable" and
delete the metrics rows from the checklist below.

Before / after, where a number moved:

| metrics.json key | before | after |
|---|---|---|
|  |  |  |
-->

## Checklist

- [ ] `python -m pytest` passes
- [ ] `python scripts/check_readme.py` passes — every figure in the README
      traces to a measurement (rule 1)
- [ ] `cd web && npm run check` passes, if anything under `web/` changed
- [ ] I re-ran every script whose `metrics.json` block my change invalidates,
      and committed the regenerated `metrics.json`
- [ ] No number appears in a document that a script here did not produce
- [ ] Constants are imported, not restated
- [ ] New or changed dependencies are pinned to an exact version, and
      `THIRD_PARTY_NOTICES.md` is updated
- [ ] Ported code carries an inline provenance header (source repo, file,
      commit SHA, licence)
- [ ] No gated or large artefact is committed (rule 5 — TRAIL data especially)

## Anything that got worse

<!--
This project documents its own bad results; see "Our worst numbers, stated
plainly" in the README. If your change makes something slower, wider, less
accurate, or less certain, say so here. A tradeoff stated is reviewable. A
tradeoff omitted is the thing that gets found later.
-->
