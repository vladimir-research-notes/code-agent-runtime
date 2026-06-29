"""A response cache so repeated requests never re-spend (Milestone 10).

A coding-agent run is often re-executed — to reproduce a result, to debug a
trace, to re-score the same task. Re-calling a paid model each time would be
both wasteful and a source of non-determinism. The cache keys a stored response
by the request's content hash (:meth:`~.client.LLMRequest.cache_key`), so an
identical request anywhere — later in the same run, or in a later run pointed at
the same directory — is served from disk for free.

The cache is keyed only by the *output-affecting* request fields (model, system,
messages, sampling params). A cache hit is marked ``cached=True`` so the budget
guard knows it cost nothing. The cache is purely an optimisation: deleting it
only forces fresh calls, never changes correctness.

Persistence is opt-in: with no ``directory`` the cache lives in memory for one
process (handy for tests); with a directory it also writes one JSON file per key
so the responses survive across runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .client import LLMRequest, LLMResponse


class ResponseCache:
    """In-memory cache of LLM responses, optionally backed by a directory."""

    def __init__(self, directory: str | Path | None = None) -> None:
        self._dir = Path(directory) if directory is not None else None
        if self._dir is not None:
            self._dir.mkdir(parents=True, exist_ok=True)
        self._mem: dict[str, LLMResponse] = {}
        self.hits = 0
        self.misses = 0
        self.writes = 0

    @property
    def persistent(self) -> bool:
        return self._dir is not None

    def _path(self, key: str) -> Path:
        assert self._dir is not None
        return self._dir / f"{key}.json"

    def get(self, request: LLMRequest) -> LLMResponse | None:
        """Return a cached response for ``request`` (marked cached), or ``None``."""
        key = request.cache_key()
        cached = self._mem.get(key)
        if cached is None and self._dir is not None:
            path = self._path(key)
            if path.exists():
                import json

                cached = LLMResponse.from_dict(json.loads(path.read_text(encoding="utf-8")))
                self._mem[key] = cached
        if cached is None:
            self.misses += 1
            return None
        self.hits += 1
        return cached.with_cached(True)

    def put(self, request: LLMRequest, response: LLMResponse) -> None:
        """Store ``response`` under ``request``'s key (stored as not-cached)."""
        key = request.cache_key()
        stored = response.with_cached(False)
        self._mem[key] = stored
        if self._dir is not None:
            import json

            self._path(key).write_text(
                json.dumps(stored.to_dict(), indent=2) + "\n", encoding="utf-8"
            )
            self.writes += 1

    def stats(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "writes": self.writes,
            "entries": len(self._mem),
            "persistent": self.persistent,
            "directory": str(self._dir) if self._dir is not None else None,
        }
