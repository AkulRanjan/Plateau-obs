"""Long traces for the demo and for detection benchmarking.

The §6 fixtures are 2-7 turns and validate *classification*. They cannot
validate *detection*, because every trip threshold is >= 3 and two of them are
2 turns long. These traces are full-length runs of the same trace classes, so
turns-to-detection is a meaningful number.

Each trace is `list[tuple[action, observation]]`, the same shape the detector's
`run()` and the baselines' `detect()` consume.

Nothing here is captured from a real agent. These are hand-written and labelled
as such -- the non-synthetic traces come from TRAIL (gated, human-downloaded)
and are not in this repository.
"""

from __future__ import annotations

# A productive opening: varied actions, each returning genuinely new content.
# Six turns is exactly MIN_SAMPLES, so the calibrator arms right as the real
# behaviour starts.
PRODUCTIVE_PREAMBLE = [
    ("list_dir(path='src/')", "src/: auth.py, config.py, models.py, utils.py, api.py"),
    ("read_file(f='src/auth.py')", "def refresh_token(client_id, secret): expires_in=3600"),
    ("grep(pattern='TOKEN_TTL')", "src/config.py:14: TOKEN_TTL = 3600  # seconds"),
    ("read_file(f='src/config.py')", "TOKEN_TTL=3600, RATE_LIMIT=100, GATEWAY='api.internal'"),
    ("run_tests(suite='auth')", "12 passed, 1 failed: test_refresh_rotates_secret"),
    ("read_file(f='tests/test_auth.py')", "assert new_secret != old_secret  # line 88"),
]

# 55 rewordings of one question. Every action string is distinct, so exact-match
# and argument-debounce detectors never fire; every observation is the same
# non-answer, so novelty is 0.
_PARAPHRASES = [
    "auth token refresh", "how do I refresh a token", "refreshing auth tokens",
    "token refresh procedure", "refresh the auth token", "auth refresh flow",
    "how to refresh authentication token", "token renewal process",
    "renewing an auth token", "auth token renewal steps", "refresh access token",
    "access token refresh guide", "how does token refresh work",
    "token refresh implementation", "implementing auth token refresh",
    "auth token refresh example", "example of refreshing a token",
    "sample token refresh code", "token refresh code sample",
    "refresh token endpoint", "endpoint for refreshing tokens",
    "which endpoint refreshes tokens", "auth refresh endpoint docs",
    "documentation for token refresh", "docs on refreshing auth tokens",
    "where are the token refresh docs", "token refresh reference",
    "reference for auth token refresh", "auth token refresh api",
    "api for refreshing tokens", "refresh tokens via api",
    "programmatic token refresh", "refresh a token programmatically",
    "token refresh best practice", "best practices refreshing tokens",
    "recommended way to refresh tokens", "proper token refresh approach",
    "correct way to refresh auth token", "auth token refresh pattern",
    "pattern for token refresh", "token refresh design", "designing token refresh",
    "token refresh architecture", "how should tokens be refreshed",
    "when to refresh an auth token", "auth token expiry and refresh",
    "handling token expiration", "token expiry handling", "expired token refresh",
    "what to do when a token expires", "refresh on token expiry",
    "auto refresh auth tokens", "automatic token refresh",
    "automating token refresh", "token refresh automation",
]

#: The headline demo. A coding agent works productively for six turns, then
#: spends the remaining 55 rewording one search that never returns anything.
#: 61 turns total -- the length the pitch quotes.
RUNAWAY_PARAPHRASE_LOOP = PRODUCTIVE_PREAMBLE + [
    (f"search_docs(q='{q}')", "No relevant results found.") for q in _PARAPHRASES
]

_VENDORS = [
    "ACME Corp", "Vertex Ltd", "Bluewave Systems", "Orchid Traders",
    "Northgate Supply", "Quanta Metals", "Sunreef Logistics", "Peregrine Foods",
    "Ironwood Timber", "Calyx Chemicals", "Harbour Freight Co", "Meridian Print",
    "Copperline Tools", "Saffron Textiles", "Delta Ceramics", "Aurora Glassworks",
    "Kestrel Aviation", "Lantern Paper", "Mosaic Tiles", "Nimbus Cooling",
    "Obsidian Stone", "Pinegate Lumber", "Quarry Aggregates", "Riverbend Dairy",
    "Solstice Solar", "Tamarind Spice", "Umber Paints", "Vantage Optics",
    "Willowbrook Farms", "Xenon Lighting", "Yarrow Herbals", "Zephyr Fans",
    "Alloy Fasteners", "Basalt Concrete", "Cedar Joinery", "Dunes Hospitality",
    "Elmwood Furniture", "Fathom Marine", "Granite Counters", "Halcyon Travel",
    "Indigo Dyes", "Juniper Distillery", "Kiln Bricks", "Loamfield Seeds",
    "Marlin Nets", "Nectar Beverages", "Oakhill Cider", "Prism Acrylics",
    "Quill Stationery", "Ridgeline Roofing", "Sable Leather", "Thistle Wool",
    "Umbra Shades", "Verdant Nursery", "Wharf Cranes",
]

#: The counter-demo. Near-identical actions (action_sim 0.9913 measured at gate
#: 1) but a genuinely different record every turn. A healthy batch job that
#: must NOT trip.
HEALTHY_INVOICE_BATCH = PRODUCTIVE_PREAMBLE + [
    (
        f"extract_text(f='invoice_{41 + i:03d}.pdf')",
        f"{vendor}, Rs {(i * 7919 + 4200) % 250000 + 1500:,}, "
        f"due {['Aug', 'Sep', 'Oct'][i % 3]} {(i * 3) % 28 + 1}",
    )
    for i, vendor in enumerate(_VENDORS)
]

#: A healthy poller. A poller is genuinely informationally stalled, so no floor
#: separates it from a loop -- the measured novelty distribution has pollers at
#: 0.0067-0.2311, inside the loop band. This is what the required
#: `idempotent: true` declaration exists for, and it is declared in
#: IDEMPOTENT_TOOLS below. Without that declaration this trace is a standing
#: false trip, which is exactly the point: the burden is on the caller.
HEALTHY_POLLER = PRODUCTIVE_PREAMBLE + [
    (
        "check_build_status(job='deploy-4471')",
        f"Job still running, {i * 30 + 30}s elapsed",
    )
    for i in range(30)
]

#: Unreachable target: different tools, byte-identical failure. Trips via the
#: stall path.
UNREACHABLE_TARGET = PRODUCTIVE_PREAMBLE + [
    (action, "Error: not found")
    for action in [
        "read_file(f='deploy/config.yaml')", "grep(pattern='deploy_key')",
        "list_dir(path='deploy/')", "read_file(f='deploy/keys.json')",
        "grep(pattern='DEPLOY_KEY')", "list_dir(path='deploy/secrets/')",
        "read_file(f='deploy/.env')", "grep(pattern='deploy')",
        "list_dir(path='.')", "read_file(f='deploy/Makefile')",
    ]
]

# Differently-worded non-answers. Every one means "nothing found", but no two
# share vocabulary.
_DEAD_END_PHRASINGS = [
    "No relevant results found.",
    "Nothing matched your query.",
    "0 results returned.",
    "No matches in the index.",
    "Search returned nothing useful.",
    "Query produced an empty set.",
    "Could not locate anything on that topic.",
    "The lookup came back blank.",
    "Zero hits for those terms.",
    "That search yielded no documents.",
    "Nothing on file corresponds to this.",
    "Came up empty-handed.",
]

#: ADDED AFTER MEASUREMENT, AND SAID SO PLAINLY.
#:
#: The first run of scripts/long_trace_comparison.py showed the lexical baseline
#: beating Plateau outright: recall 1.00, zero false trips. The cause was a flaw
#: in RUNAWAY_PARAPHRASE_LOOP, not a property of the detectors -- its
#: observations are byte-identical, so Jaccard scores 1.0 and a lexical detector
#: wins trivially. That is lexical's home turf, and the original trace never
#: left it.
#:
#: This class removes that artefact: the actions are still rewordings of one
#: question, but each non-answer is worded differently. Measured Jaccard between
#: consecutive observations is 0.000, so a lexical detector at its published
#: 0.85 threshold cannot see it at all, while the observations remain
#: semantically identical -- they all mean "nothing found".
#:
#: It is kept as an ADDITIONAL class, never a replacement, and the original
#: stays in the table. Both numbers are published. If this trace is the only one
#: Plateau wins, that is the finding, not a headline.
RUNAWAY_PARAPHRASE_LOOP_VARIED_WORDING = PRODUCTIVE_PREAMBLE + [
    (
        f"search_docs(q='{q}')",
        _DEAD_END_PHRASINGS[i % len(_DEAD_END_PHRASINGS)],
    )
    for i, q in enumerate(_PARAPHRASES)
]

#: name -> (trace, should_the_detector_trip)
TRACES: dict[str, tuple[list[tuple[str, str]], bool]] = {
    "runaway_paraphrase_loop": (RUNAWAY_PARAPHRASE_LOOP, True),
    "paraphrase_loop_varied_wording": (RUNAWAY_PARAPHRASE_LOOP_VARIED_WORDING, True),
    "healthy_invoice_batch": (HEALTHY_INVOICE_BATCH, False),
    "unreachable_target": (UNREACHABLE_TARGET, True),
    "healthy_poller": (HEALTHY_POLLER, False),
}

#: name -> the tools that trace declares `idempotent: true`.
#:
#: Kept as a separate mapping rather than a third tuple element so the
#: `(trace, should_trip)` shape every existing consumer unpacks stays intact.
#: A trace absent from this mapping declares nothing, which is the default and
#: the unsafe case.
IDEMPOTENT_TOOLS: dict[str, frozenset[str]] = {
    "healthy_poller": frozenset({"check_build_status"}),
}

#: Turn index at which the productive preamble ends and the class begins.
PREAMBLE_LENGTH = len(PRODUCTIVE_PREAMBLE)
