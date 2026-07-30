"""The world the live agents explore, and the tools they explore it with.

The task is deliberately UNSOLVABLE with the tools provided. The agent is asked
how to refresh an expired auth token; the docs correctly tell it that refreshing
requires a client secret; the config correctly tells it the secret lives in a
vault; and the vault refuses. Nothing in reach closes the loop.

That is not a trick. It is the most common way a real agent gets stuck: the
information it needs is behind a permission it does not have, and every call it
makes still returns HTTP 200.

WHY THE TREE IS THIS BIG
------------------------
Plateau cannot arm until it has seen MIN_SAMPLES (6) *productive* turns, because
it calibrates "normal" from real work. An agent that hits the wall on turn 3
leaves the breaker in CALIBRATING and it never trips — correct behaviour, and a
non-demo. Measured: with a thin tree the agent produced only ~4 informative
turns before collapsing, and the breaker stayed cold for all 20 turns.

So the tree carries enough genuinely distinct material to support 8-10
informative turns before the dead end. That is not padding — a real agent does
investigate for a while before it gets stuck.

WHY THE NON-ANSWER IS A CONSTANT STRING
---------------------------------------
`search_docs` and `grep` return exactly "No results found." for anything they
cannot match. That is what makes Plateau trip: novelty collapses to ~0 because
the observation is byte-identical each time.

Be explicit about this, because the project measured the limit (metrics.json ->
long_trace_comparison): when non-answers are worded *differently* each time,
MiniLM scores them 0.4366-1.0112 novelty and Plateau does NOT trip. This demo
works because a real search API returns a consistent no-results response — which
it does — and not because Plateau understands paraphrase. It does not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

#: The constant non-answer. See the module docstring.
NO_RESULTS = "No results found."

TASK = (
    "Find out how to refresh the expired auth token for this service, "
    "and report the exact steps."
)

# --- the fixture tree --------------------------------------------------------

FILES: dict[str, str] = {
    "docs/auth.md": (
        "# Authentication\n"
        "Access tokens expire after 3600 seconds.\n"
        "To refresh, POST /oauth/token with grant_type=refresh_token.\n"
        "The request MUST be signed with the application's client_secret."
    ),
    "docs/oauth.md": (
        "# OAuth\n"
        "grant_type=refresh_token requires both client_id and client_secret.\n"
        "Secrets are never stored in the repository. See the vault."
    ),
    "docs/runbook.md": (
        "# Runbook\n"
        "Symptom: 401 after one hour. Cause: the access token expired.\n"
        "Fix: refresh the token. Requires the client_secret from the vault.\n"
        "Escalation: the platform team owns vault ACLs."
    ),
    "docs/permissions.md": (
        "# Permissions\n"
        "Vault paths are granted per service account.\n"
        "This agent runs as svc-readonly, which has no grant on app/oauth.\n"
        "Requesting a grant is a manual process outside this repository."
    ),
    "config/app.yaml": (
        "service: billing-api\n"
        "client_id: acme-billing-7741\n"
        "# client_secret is NOT stored here - see vault path app/oauth\n"
        "token_ttl: 3600\n"
    ),
    "config/vault.yaml": (
        "vault_addr: https://vault.internal\n"
        "paths:\n"
        "  - app/oauth      # client_secret lives here\n"
    ),
    "src/client.py": (
        "def refresh(client_id, client_secret):\n"
        "    # client_secret must be supplied by the caller\n"
        "    return post('/oauth/token', grant_type='refresh_token')\n"
    ),
    "src/session.py": (
        "class Session:\n"
        "    def __init__(self, token, expires_at):\n"
        "        self.token = token\n"
        "        self.expires_at = expires_at\n"
        "    def expired(self):\n"
        "        return time.time() > self.expires_at\n"
    ),
    "src/errors.py": (
        "class TokenExpired(Exception):\n"
        "    'Raised when the access token is past expires_at.'\n"
        "class VaultDenied(Exception):\n"
        "    'Raised when the vault refuses a read.'\n"
    ),
    "tests/test_auth.py": (
        "def test_refresh_requires_secret():\n"
        "    with pytest.raises(TypeError):\n"
        "        refresh(client_id='acme-billing-7741')  # no secret\n"
    ),
    "CHANGELOG.md": (
        "## 2.4.0\n"
        "- token_ttl reduced from 86400 to 3600\n"
        "- client_secret moved out of app.yaml into the vault\n"
    ),
}

#: Queries the docs can actually answer. Everything else gets NO_RESULTS.
_DOC_INDEX: list[tuple[tuple[str, ...], str]] = [
    (
        ("expire", "expiry", "ttl", "how long"),
        "Access tokens expire after 3600 seconds. (docs/auth.md)",
    ),
    (
        ("refresh", "renew", "grant_type"),
        "POST /oauth/token with grant_type=refresh_token, signed with client_secret. (docs/auth.md)",
    ),
    (
        ("secret", "credential", "vault"),
        "Secrets are never stored in the repository. See vault path app/oauth. (docs/oauth.md)",
    ),
    (
        ("401", "unauthor", "symptom", "runbook"),
        "401 after one hour means the access token expired. (docs/runbook.md)",
    ),
    (
        ("permission", "grant", "acl", "denied"),
        "Vault paths are granted per service account; this agent is svc-readonly. (docs/permissions.md)",
    ),
    (
        ("changelog", "version", "release", "changed"),
        "2.4.0 moved client_secret out of app.yaml into the vault. (CHANGELOG.md)",
    ),
    (
        ("test", "pytest", "spec"),
        "tests/test_auth.py asserts refresh() fails without a client_secret.",
    ),
    (
        ("session", "expires_at"),
        "src/session.py defines Session.expired() against expires_at.",
    ),
    (
        ("error", "exception", "raise"),
        "src/errors.py defines TokenExpired and VaultDenied. (src/errors.py)",
    ),
    (
        ("platform team", "escalat", "who owns"),
        "The platform team owns vault ACLs. (docs/runbook.md)",
    ),
]


@dataclass
class ToolCall:
    name: str
    args: dict
    observation: str
    ok: bool = True


# --- the tools ---------------------------------------------------------------


def search_docs(query: str = "", **_) -> str:
    """Search the documentation. Returns a constant non-answer when it misses."""
    q = (query or "").lower()
    for keywords, answer in _DOC_INDEX:
        if any(k in q for k in keywords):
            return answer
    return NO_RESULTS


def read_file(path: str = "", **_) -> str:
    """Read a file from the project."""
    body = FILES.get((path or "").strip().lstrip("./"))
    if body is None:
        return f"Error: no such file: {path}"
    return body


def list_dir(path: str = "", **_) -> str:
    """List a directory."""
    prefix = (path or "").strip().lstrip("./").rstrip("/")
    if prefix in ("", "."):
        names = sorted({f.split("/")[0] for f in FILES})
    else:
        names = sorted(
            {
                f[len(prefix):].lstrip("/").split("/")[0]
                for f in FILES
                if f.startswith(prefix)
            }
        )
    if not names:
        return f"Error: no such directory: {path}"
    return ", ".join(names)


def grep(pattern: str = "", **_) -> str:
    """Search file contents for a pattern."""
    pat = (pattern or "").lower()
    if not pat:
        return NO_RESULTS
    hits = [
        f"{name}: {line.strip()}"
        for name, body in FILES.items()
        for line in body.splitlines()
        if pat in line.lower()
    ]
    return "\n".join(hits[:4]) if hits else NO_RESULTS


def vault_get(path: str = "", **_) -> str:
    """Read a secret from the vault. The agent does not have permission."""
    return f"PermissionError: access denied to {path or 'app/oauth'}"


TOOLS: dict[str, Callable[..., str]] = {
    "search_docs": search_docs,
    "read_file": read_file,
    "list_dir": list_dir,
    "grep": grep,
    "vault_get": vault_get,
}


#: Sent to the model. Ollama's tool schema.
TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Search the project documentation for a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "what to search for"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read one file. Known paths: docs/auth.md, docs/oauth.md, "
                "docs/runbook.md, docs/permissions.md, config/app.yaml, "
                "config/vault.yaml, src/client.py, src/session.py, src/errors.py, "
                "tests/test_auth.py, CHANGELOG.md"
            ),
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files under a directory, e.g. docs, config, src, tests.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search all file contents for a literal pattern.",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vault_get",
            "description": "Read a secret from the vault, e.g. app/oauth.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
]


def execute(name: str, args: dict) -> ToolCall:
    """Run one tool call. Unknown tools return an error, never raise."""
    fn = TOOLS.get(name)
    if fn is None:
        return ToolCall(name, args, f"Error: no such tool: {name}", ok=False)
    try:
        observation = fn(**args)
    except TypeError:
        return ToolCall(name, args, f"Error: bad arguments for {name}: {args}", ok=False)
    return ToolCall(name, args, observation, ok=not observation.startswith("Error"))


def render_call(name: str, args: dict) -> str:
    """A compact one-line rendering of a call, for the panes and for Plateau."""
    inner = ", ".join(f"{k}={v!r}" for k, v in sorted(args.items()))
    return f"{name}({inner})"
