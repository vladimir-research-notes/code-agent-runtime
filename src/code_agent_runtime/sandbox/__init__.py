"""Permission policies and sandbox controls (Milestone 7).

The sandbox is the *policy* layer over the tools' *mechanism*. A
:class:`SandboxPolicy` declares what an agent may read, write, and run, plus the
network posture and the runtime/output caps; a :class:`Sandbox` enforces it —
gating each agent tool call before it runs and redacting credential-shaped output
afterwards. The runtime loop builds a policy per run (default:
:meth:`SandboxPolicy.from_task`), enforces it on every *agent* tool call, and
redacts the results that land in steps and traces.

Honest scope (see ``docs/SECURITY_MODEL.md``): this reduces blast radius and adds
observability for a semi-trusted, deterministic agent on a developer machine. It
is **not** a production-grade jail — command matching is by program name, network
enforcement is a heuristic denylist, and there is no process/namespace isolation.
A containerised runner for stronger isolation remains a documented non-goal for
this milestone.

Public API:

- :class:`SandboxPolicy` and the default vocabularies
  (:data:`DEFAULT_DENIED_PATHS`, :data:`DEFAULT_COMMAND_DENYLIST`,
  :data:`NETWORK_PROGRAMS`);
- :class:`Sandbox` and :class:`PolicyDecision`;
- :func:`redact_text` / :func:`count_secrets` from the secret scanner.
"""

from __future__ import annotations

from .permissions import PolicyDecision, Sandbox
from .policy import (
    DEFAULT_COMMAND_DENYLIST,
    DEFAULT_DENIED_PATHS,
    DEFAULT_MAX_RUNTIME_SECONDS,
    NETWORK_PROGRAMS,
    SandboxPolicy,
)
from .secret_scanner import count_secrets, redact_text

__all__ = [
    "SandboxPolicy",
    "Sandbox",
    "PolicyDecision",
    "DEFAULT_DENIED_PATHS",
    "DEFAULT_COMMAND_DENYLIST",
    "DEFAULT_MAX_RUNTIME_SECONDS",
    "NETWORK_PROGRAMS",
    "redact_text",
    "count_secrets",
]
