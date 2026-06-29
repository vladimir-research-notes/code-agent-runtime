"""The abstract LLM client interface and an offline fake (Milestone 10).

Every model-backed agent talks to the world through one narrow seam: an
:class:`LLMClient` that turns an :class:`LLMRequest` into an :class:`LLMResponse`.
Keeping that seam tiny is what makes the optional Claude adapter *optional* — the
runtime, the budget guard, the cache, and the agent all depend on this interface,
never on a network library, so the default test path needs no API key and no
``anthropic`` install.

Two concrete clients exist:

- :class:`FakeLLMClient` (here): deterministic and offline. It replays a fixed
  list of responses regardless of the prompt and derives heuristic token counts,
  so it can drive the whole agent loop — and exercise the budget guard, the
  cache, and transcript redaction — without a single paid call. This is the
  client the unit tests and the offline CLI/demo use.
- ``ClaudeAPIClient`` (in :mod:`.claude_client`): the real, network-backed
  adapter, lazily importing ``anthropic`` so importing this package never
  requires it.

Requests and responses are plain, JSON-serialisable data so a request can be
hashed for caching and a response can be persisted to a cache file.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from . import pricing


class LLMClientError(RuntimeError):
    """A client could not be constructed or a call could not be made.

    Used for *configuration* failures (missing dependency, missing API key) and
    transport failures, so the CLI can turn them into a clean message rather than
    a stack trace. Budget refusals are a separate hierarchy (see :mod:`.budget`).
    """


@dataclass(frozen=True)
class LLMMessage:
    """One turn in the conversation. ``role`` is ``"user"`` or ``"assistant"``."""

    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLMMessage":
        return cls(role=data["role"], content=data["content"])


@dataclass(frozen=True)
class LLMRequest:
    """A single completion request: the model, the system prompt, and the turns.

    The fields that affect the model's output are exactly the fields hashed by
    :meth:`cache_key`, so two byte-identical requests share a cached response and
    nothing else collides.
    """

    model: str
    system: str
    messages: tuple[LLMMessage, ...]
    max_tokens: int = 1024
    temperature: float = 0.0
    stop: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "system": self.system,
            "messages": [m.to_dict() for m in self.messages],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stop": list(self.stop),
        }

    def input_chars(self) -> int:
        """Total characters across the system prompt and every message."""
        return len(self.system) + sum(len(m.content) for m in self.messages)

    def estimated_input_tokens(self) -> int:
        """Heuristic input-token count, used for the pre-call cost bound."""
        return pricing.estimate_tokens(self.system) + sum(
            pricing.estimate_tokens(m.content) for m in self.messages
        )

    def cache_key(self) -> str:
        """Stable SHA-256 over the output-affecting fields (for response caching)."""
        payload = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LLMResponse:
    """A completion result: the text plus the authoritative token usage.

    ``input_tokens``/``output_tokens`` are what the *provider* reported (the fake
    client fills them with heuristic estimates). ``cached`` marks a response
    served from the cache, which by definition cost nothing this run.
    """

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None = None
    cached: bool = False

    def with_cached(self, cached: bool) -> "LLMResponse":
        """Return a copy with ``cached`` set (responses are frozen)."""
        if cached == self.cached:
            return self
        return LLMResponse(
            text=self.text,
            model=self.model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            stop_reason=self.stop_reason,
            cached=cached,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "stop_reason": self.stop_reason,
            "cached": self.cached,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLMResponse":
        return cls(
            text=data["text"],
            model=data["model"],
            input_tokens=int(data["input_tokens"]),
            output_tokens=int(data["output_tokens"]),
            stop_reason=data.get("stop_reason"),
            cached=bool(data.get("cached", False)),
        )


class LLMClient:
    """Base class for anything that can complete an :class:`LLMRequest`.

    Subclasses set :attr:`name` and :attr:`requires_network` and implement
    :meth:`complete`. ``requires_network`` lets callers (and the docs) reason
    about whether a client can spend money or reach the internet at all; it is
    ``False`` only for the deterministic offline fake.
    """

    name: ClassVar[str] = ""
    #: Whether :meth:`complete` reaches the network (and therefore can cost money).
    requires_network: ClassVar[bool] = True

    def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError


#: A responder may be a ready :class:`LLMResponse`, a plain string (token counts
#: are then estimated), or a callable ``(request, index) -> str | LLMResponse``.
FakeResponder = str | LLMResponse | Callable[[LLMRequest, int], "str | LLMResponse"]


@dataclass
class FakeLLMClient(LLMClient):
    """Deterministic, offline client that replays canned responses in order.

    Built from a sequence of responses (strings, ready :class:`LLMResponse`
    objects, or callables). Each :meth:`complete` pops the next one; once the
    list is exhausted it returns :attr:`exhausted_text` so a driving loop ends
    cleanly rather than raising. Every request is appended to :attr:`requests`,
    so a test can assert exactly what was (and was not) sent.

    Token usage is filled from :mod:`.pricing` heuristics — input from the
    request, output from the response text — unless a response provides its own
    counts. This is what lets the budget guard and cost accounting be exercised
    end to end with no network and no real tokenizer.
    """

    name: ClassVar[str] = "fake"
    requires_network: ClassVar[bool] = False

    responses: Sequence[FakeResponder] = field(default_factory=tuple)
    #: Returned (as text) once the canned responses run out. Defaults to a finish
    #: action so :class:`~.agent.LLMAgent` stops instead of looping.
    exhausted_text: str = '{"action": "finish", "message": "fake client exhausted"}'
    requests: list[LLMRequest] = field(default_factory=list)
    _cursor: int = 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        index = self._cursor
        self.requests.append(request)
        self._cursor += 1
        if index < len(self.responses):
            item = self.responses[index]
            if callable(item):
                item = item(request, index)
        else:
            item = self.exhausted_text
        if isinstance(item, LLMResponse):
            # Pin the model to the request's so cost accounting is consistent.
            return item if item.model == request.model else LLMResponse(
                text=item.text,
                model=request.model,
                input_tokens=item.input_tokens,
                output_tokens=item.output_tokens,
                stop_reason=item.stop_reason,
                cached=item.cached,
            )
        text = str(item)
        return LLMResponse(
            text=text,
            model=request.model,
            input_tokens=request.estimated_input_tokens(),
            output_tokens=pricing.estimate_tokens(text),
            stop_reason="end_turn",
        )
