# Contributing to Plateau

Thanks for taking an interest. Before anything else, the one thing that makes
this repository different from most:

> **No number appears in any document unless a script in this repository
> produced it and wrote it into `metrics.json`.**

That is not a style preference. `scripts/check_readme.py` fails the build if a
figure in `README.md` is not backed by a measurement in `metrics.json`. If you
want to claim something is faster, tighter, or more accurate, the contribution
is the script that measures it. The prose comes after.

The project also documents its own bad results. `README.md` has a section called
"Our worst numbers, stated plainly" and another called "Everything wrong with
this benchmark, listed". A pull request that quietly drops an unflattering
measurement will not be merged; one that adds an unflattering measurement is
exactly what this project is for.

---

## The rules

Five rules govern this codebase. They are cited by number throughout the source,
and until this file existed they were never written down in one place — you
would meet "Rule 1 says…" in a docstring with nothing to look up. Here they are,
with the code that enforces each.

| # | Rule | Enforced by |
|---|---|---|
| 1 | No number appears in any document unless a script in this repo produced it and wrote it into `metrics.json`. | `scripts/check_readme.py`, `scripts/gate1_check.py` |
| 2 | No LLM API is involved in the decision path. The detector runs on local embeddings only. | `plateau/encoder.py` |
| 3 | Two harness runs must produce a byte-identical `metrics.json`. | `scripts/check_env.py`, `scripts/pin_encoder.py`, `[tool.plateau]` in `pyproject.toml` |
| 4 | *No citation for this number exists anywhere in the tree.* | — |
| 5 | Gated, third-party and large artefacts are never committed. | `.gitignore` |

**On rule 4:** it is referred to by the others' numbering but never quoted in
any file here. Rather than invent one, it is left open. If you know what it was,
a PR that fills this row in — and cites where the rule came from — is welcome.

**On rule 3:** it holds *per machine*, and the README says so plainly. A pinned
`torch` build that differs by CUDA suffix will shift the last decimal places.
`scripts/check_env.py` surfaces that drift rather than hiding it; a reported
difference is information, not necessarily a failure.

**On rule 5:** the TRAIL dataset is gated and its terms forbid resharing. It is
downloaded locally by `scripts/fetch_trail.py` into `data/trail/`, which is
ignored. Never commit it, never paste its contents into an issue.

---

## Setting up

### Python

`torch==2.5.1` publishes no wheel for Python 3.13+, so use **3.10 – 3.12**.

```bash
python3.11 -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev,demo]"
python scripts/check_env.py --probe
```

The `demo` extra is not optional in practice: `tests/test_live_demo.py` imports
`demo.live_agent`, so a dev environment without `httpx` and `python-pptx` cannot
even collect the suite. That omission is how the extra was found.

The MiniLM weights (~90 MB) download once into `models/`, which is ignored.

### Web console

```bash
cd web
npm ci
npm run check
```

`npm ci` rather than `npm install` — `package-lock.json` is committed
deliberately, and every version is pinned without a range.

---

## The checks

Run these before opening a pull request. All of them pass on `main`.

| Command | What it guards |
|---|---|
| `python -m pytest` | 165 passed, 2 skipped. The two skips are `test_langgraph_example.py`; LangGraph lives in a separate environment. |
| `python scripts/check_readme.py` | Rule 1. Every decimal figure in `README.md` traces to `metrics.json`. |
| `python scripts/check_env.py` | Rule 3. Reports pin drift in the installed stack. |
| `cd web && npm run check` | Parity, demo contract, ownership, contrast, SSR render, build, offline. |
| `cd web && npm run verify` | The above plus the two visual checks, which drive real headless Chrome. |

`npm run verify` needs Chrome. It is found automatically on Linux, macOS and
Windows; set `CHROME_BIN` if yours lives somewhere unusual.

All of these run on Windows, macOS and Linux. If you hit a path- or
spawn-related failure on your platform, that is a bug in the check, not in your
setup — please report it.

---

## Adding a measurement

This is the main workflow, and it has a fixed shape.

1. **Write a script** in `eval/` or `scripts/`. `eval/` is for sweeps and trace
   corpora; `scripts/` is for probes, comparisons and repo checks.
2. **Open with a docstring that states the question the script exists to
   answer**, not a description of its mechanics. Look at
   `eval/floor_sweep.py` or `scripts/long_trace_sweep.py` for the register: they
   say what the other sweeps cannot see and why this one is entitled to a
   conclusion the others are not.
3. **Write one top-level key into `metrics.json`**, merging rather than
   replacing:

   ```python
   path = ROOT / "metrics.json"
   doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
   doc["your_key"] = { ... }
   path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
   ```

4. **Record the encoder fingerprint** (`encoder.fingerprint()`) in the block, so
   a result can always be tied to the model that produced it.
5. **Record the full grid and the raw per-configuration results**, not just the
   summary. Someone will want to re-derive your headline from the rows.
6. **Then**, and only then, quote the numbers in `README.md`, and run
   `python scripts/check_readme.py`.

### Things that have already gone wrong here

These are real failures this repository has recorded against itself. Do not
reintroduce them.

- **Do not restate a constant.** Import it. A probe once hard-coded a candidate
  floor of 0.15, the code moved to 0.30, and the stored verdict silently came to
  describe a value that no longer existed. `scripts/novelty_floor_check.py`
  imports the constant instead.
- **Do not report a metric a fixture cannot produce.** The sweep once reported
  "0 usable configurations out of 144". Two fixtures were two turns long and
  could not trip at any setting, so the number measured trace length and nothing
  else.
- **Do not sweep four parameters and conclude about five.** `window_size` was
  hard-coded to 8 and left out of the grid; it turned out to be the only
  load-bearing parameter of the five.
- **Do not quote a negative measurement in prose.** `check_readme.py` matches
  unsigned figures, so a stored `-0.00059` cannot back a README that says
  "0.00059". Record the magnitude as its own field if that is the sentence you
  need — see `distance_below_floor` in `eval/separation_margin.py`.

### Changing a parameter default

A default in `plateau/` may only change with a measurement behind it. The
`## Parameters` table in `README.md` names the metrics block that owns each one,
and your PR must update that table. "It felt better on the fixture" is not an
owner.

---

## Third-party code

`THIRD_PARTY_NOTICES.md` is maintained **as work lands**, not at the end. Its
status legend is strict: nothing is listed as `IN USE` before it exists in the
tree.

- Upstream trees are **not vendored**. `third_party/` is ignored; clone baseline
  repos there locally.
- Functions ported from another project carry an **inline provenance header at
  the definition site** naming the source repository, file, commit SHA and
  licence — and an entry in `THIRD_PARTY_NOTICES.md`.
- New runtime dependencies are pinned to an exact version, no ranges, in
  `pyproject.toml` or `web/package.json`.

---

## Code style

Nothing here is enforced by a formatter; match the surrounding code.

- **Python**: 4 spaces, type hints on public functions, `from __future__ import
  annotations` at the top of scripts. Scripts insert the repo root on
  `sys.path` and set `HF_HUB_OFFLINE=1` before importing `plateau`.
- **JavaScript**: ES modules, Node built-ins only in `web/scripts/`. Use
  `pathToFileURL()` for dynamic `import()` of a resolved path — a bare Windows
  path is not a valid module URL.
- **Comments explain why, not what.** This codebase uses them to record the
  reasoning and the failure that motivated a line. A comment saying what the
  next line does will be asked for changes; one saying why the obvious approach
  was wrong is the house style.

---

## Commits and pull requests

Commit subjects are lowercase, prefixed with an area, and describe the change in
prose rather than in categories:

```
web: separate the desk from the stock
scripts: check_env.py — surface the determinism drift instead of hiding it
tests: cover the live demo stack — 21 tests, 100 -> 121
```

Areas in use: `plateau`, `eval`, `scripts`, `tests`, `web`, `demo`, `examples`.
A finding significant enough to reframe the project may drop the prefix and
state itself — `The window was the whole problem, and nobody had ever swept it`.

For pull requests:

- Branch off `main`.
- Say what you measured, not only what you changed.
- If a measurement moved, include the before and after, and re-run every script
  whose block in `metrics.json` your change invalidates.
- Fill in the checklist in the PR template.

---

## Reporting bugs and asking questions

Open an issue using one of the templates. For anything involving a wrong
*number* rather than a crash, the "Measurement dispute" template exists
specifically for that — it asks which `metrics.json` key you believe is wrong
and what you ran to get a different answer.

Security issues go to `SECURITY.md`, not to the public tracker.

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Licence

By contributing you agree that your contributions are licensed under the
Apache-2.0 licence, as in [LICENSE](LICENSE).
