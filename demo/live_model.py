"""The model behind the live agents.

Deliberately a thin seam. Tonight it is ollama on localhost; tomorrow it is
Bedrock. Swapping is one class, not a rewrite — which is the point, because the
agent loop and Plateau itself do not care where the tokens come from.

DETERMINISM
-----------
Both agents must make the same decisions until Plateau intervenes, or the
comparison proves nothing. So: temperature 0, top_p 1, a fixed seed, and the
same model tag on both machines. That makes divergence *unlikely*, not
impossible — two machines can differ in ollama build or quantisation digest.
`scripts/check_model_digest.py` prints the digest so both laptops can be
compared before recording, and every agent writes a JSONL of its actions so the
runs can be diffed afterwards rather than assumed identical.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"
SEED = 1337


@dataclass
class Proposal:
    """What the model decided to do this turn."""

    tool: str | None
    args: dict
    text: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def is_tool_call(self) -> bool:
        return bool(self.tool)


class Model(Protocol):
    name: str

    def propose(self, messages: list[dict], tools: list[dict]) -> Proposal: ...


class OllamaModel:
    """Local ollama. No network beyond localhost, no API key, no cost."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        url: str = OLLAMA_URL,
        seed: int = SEED,
        timeout: float = 180.0,
    ) -> None:
        self.name = model
        self.url = url.rstrip("/")
        self.seed = seed
        self._client = httpx.Client(timeout=timeout)

    def digest(self) -> str:
        """The model's content digest, so two machines can prove they match."""
        try:
            r = self._client.post(f"{self.url}/api/show", json={"name": self.name})
            r.raise_for_status()
            body = r.json()
            return (body.get("digest") or body.get("details", {}).get("parent_model") or "")[:20]
        except Exception as exc:  # noqa: BLE001 - diagnostics only
            return f"unavailable ({exc.__class__.__name__})"

    def propose(self, messages: list[dict], tools: list[dict]) -> Proposal:
        payload = {
            "model": self.name,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": {
                # The determinism knobs. All three matter.
                "temperature": 0,
                "top_p": 1,
                "seed": self.seed,
            },
        }
        r = self._client.post(f"{self.url}/api/chat", json=payload)
        r.raise_for_status()
        body = r.json()
        message = body.get("message", {}) or {}

        calls = message.get("tool_calls") or []
        if calls:
            fn = calls[0].get("function", {}) or {}
            args = fn.get("arguments", {}) or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"query": args}
            if not isinstance(args, dict):
                args = {}
            return Proposal(
                tool=fn.get("name"),
                args=args,
                text=message.get("content", "") or "",
                raw=body,
            )

        return Proposal(tool=None, args={}, text=message.get("content", "") or "", raw=body)


class BedrockModel:
    """Tomorrow's path. Same interface, so nothing above it changes.

    Left unimplemented rather than half-written: a stub that silently returns
    nothing would be worse than one that says it is not wired yet.
    """

    def __init__(self, model_id: str = "anthropic.claude-3-5-haiku-20241022-v1:0") -> None:
        self.name = model_id

    def propose(self, messages: list[dict], tools: list[dict]) -> Proposal:
        raise NotImplementedError(
            "BedrockModel is not wired yet. Tonight's demo runs on OllamaModel. "
            "To switch: implement propose() with bedrock-runtime converse() and "
            "map its toolUse block onto Proposal. The agent loop needs no changes."
        )


def build_model(kind: str = "ollama", **kwargs: Any) -> Model:
    if kind == "ollama":
        return OllamaModel(**kwargs)
    if kind == "bedrock":
        return BedrockModel(**kwargs)
    raise ValueError(f"unknown model kind: {kind}")
