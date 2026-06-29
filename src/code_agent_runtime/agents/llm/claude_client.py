"""Optional, network-backed Claude API client (Milestone 10).

This is the only file in the package that knows about a real provider. It is
written so that **importing it costs nothing**: the ``anthropic`` SDK is imported
lazily inside the constructor, and the API key is checked first, so:

- ``import code_agent_runtime`` never requires ``anthropic`` or a key;
- the default test suite never instantiates this client;
- a misconfiguration (no key, package not installed) surfaces as a clean
  :class:`~.client.LLMClientError`, not an import crash.

The client maps the runtime's neutral :class:`~.client.LLMRequest` onto the
Anthropic Messages API and maps the reply (text + token usage) back to an
:class:`~.client.LLMResponse`. Cost control is **not** this client's job — the
:class:`~.budget.BudgetGuard` gates every call before it reaches here. To enable
a real run, install the extra (``pip install -e '.[claude]'``) and set
``ANTHROPIC_API_KEY``; see ``docs/METHODOLOGY.md`` and the CLI's ``run --agent
llm --allow-paid``.
"""

from __future__ import annotations

import os
from typing import Any, ClassVar

from .client import LLMClient, LLMRequest, LLMResponse, LLMClientError

#: Environment variable consulted for the API key when one is not passed in.
API_KEY_ENV = "ANTHROPIC_API_KEY"


class ClaudeAPIClient(LLMClient):
    """A real Claude client backed by the ``anthropic`` SDK (paid; opt-in)."""

    name: ClassVar[str] = "claude-api"
    requires_network: ClassVar[bool] = True

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        sdk_client: Any = None,
        max_retries: int = 2,
    ) -> None:
        self.model = model
        self._max_retries = max_retries
        if sdk_client is not None:
            # Dependency-injected client (used so the mapping can be tested
            # without the SDK or the network); skip key/SDK discovery entirely.
            self._client = sdk_client
            return
        key = api_key or os.environ.get(API_KEY_ENV)
        if not key:
            raise LLMClientError(
                f"no Claude API key: pass api_key= or set {API_KEY_ENV}. "
                "The real adapter is opt-in; the offline fake client needs neither."
            )
        try:
            import anthropic  # noqa: PLC0415 - lazy: never required for import/tests
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise LLMClientError(
                "the 'anthropic' package is not installed; install the optional "
                "extra with: pip install -e '.[claude]'"
            ) from exc
        self._client = anthropic.Anthropic(api_key=key, max_retries=max_retries)

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Send ``request`` to the Messages API and return an :class:`LLMResponse`."""
        try:
            message = self._client.messages.create(
                model=request.model,
                system=request.system,
                messages=[m.to_dict() for m in request.messages],
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                **({"stop_sequences": list(request.stop)} if request.stop else {}),
            )
        except Exception as exc:  # pragma: no cover - network/SDK failure path
            raise LLMClientError(f"Claude API call failed: {exc}") from exc
        return _to_response(message, request.model)


def _to_response(message: Any, model: str) -> LLMResponse:
    """Map an Anthropic ``Message`` onto an :class:`LLMResponse`.

    Concatenates the text blocks of ``message.content`` and reads token usage
    from ``message.usage``; tolerant of missing fields so a partial/odd reply
    still yields a usable response rather than crashing.
    """
    parts: list[str] = []
    for block in getattr(message, "content", None) or []:
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text")
        if text:
            parts.append(text)
    usage = getattr(message, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    return LLMResponse(
        text="".join(parts),
        model=getattr(message, "model", None) or model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        stop_reason=getattr(message, "stop_reason", None),
    )


def build_claude_client(
    model: str,
    *,
    api_key: str | None = None,
    sdk_client: Any = None,
) -> ClaudeAPIClient:
    """Construct a :class:`ClaudeAPIClient`, raising :class:`LLMClientError` early.

    The key is validated and the SDK imported here, so a missing key or missing
    dependency fails before any run begins rather than mid-loop.
    """
    return ClaudeAPIClient(model, api_key=api_key, sdk_client=sdk_client)
