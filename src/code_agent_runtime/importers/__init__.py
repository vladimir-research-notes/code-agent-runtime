"""Claude Code trace importer (Milestone 11).

A best-effort importer that takes a coding-agent run this runtime did *not*
produce — a Claude-Code-like workflow — and converts it into this runtime's own
trace format so it can be **scored with the same scorer and replayed with the same
tools** as a native run. The point is to bring external runs under the same
microscope: one verdict mechanism, one trace shape, one set of reports.

The pipeline is two stages:

1. **Normalise** an external record into an :class:`ImportedRun` (the process, the
   change, and the declared outcome). Each input form the plan names has a builder
   in :mod:`.sources`:

   - :func:`import_before_after` — two directory snapshots (richest: supports
     verification);
   - :func:`import_diff_and_log` — a unified diff plus a command log;
   - :func:`import_transcript` — a manually exported transcript;
   - :func:`synthesize_import` — a deterministic, offline synthetic Claude-Code-like
     run this runtime generates itself (and the basis for the round-trip test).

2. **Convert and score** it with :func:`import_to_run`, which produces a
   :class:`~code_agent_runtime.runtime.state.RunResult` and a
   :class:`~code_agent_runtime.traces.schema.Trace`. In **verify** mode it
   reconstructs the workspace and re-runs the task's real test command (the
   high-signal path); in **trust** mode it scores the source's declared evidence.

Everything here is offline and free: no model, no network, no paid API. The
synthetic path runs a deterministic scripted agent on a CPU-only fixture; the
other paths only read files and parse text.
"""

from __future__ import annotations

from .convert import ImportOutcome, can_verify, import_to_run
from .diffs import parse_unified_diff, tree_diff
from .schema import (
    ACTION_KINDS,
    IMPORT_SCHEMA_VERSION,
    SOURCE_KINDS,
    TOOL_NAME_MAP,
    ImportedAction,
    ImportedRun,
    ImportSourceError,
    map_tool_name,
)
from .sources import (
    DEFAULT_AGENT_LABEL,
    export_run,
    import_before_after,
    import_diff_and_log,
    import_transcript,
    load_import_source,
    read_tree,
    synthesize_import,
    write_import_source,
)

__all__ = [
    # schema
    "ImportedRun",
    "ImportedAction",
    "ImportSourceError",
    "IMPORT_SCHEMA_VERSION",
    "SOURCE_KINDS",
    "ACTION_KINDS",
    "TOOL_NAME_MAP",
    "map_tool_name",
    # diff helpers
    "tree_diff",
    "parse_unified_diff",
    # sources / builders
    "import_before_after",
    "import_diff_and_log",
    "import_transcript",
    "synthesize_import",
    "export_run",
    "read_tree",
    "load_import_source",
    "write_import_source",
    "DEFAULT_AGENT_LABEL",
    # conversion / scoring
    "import_to_run",
    "can_verify",
    "ImportOutcome",
]
