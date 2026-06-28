# Research questions

> **Status:** framing document (Milestone 0). These questions motivate the
> platform. They are not yet answered; each will be revisited with evidence as
> the relevant milestones land.

The platform exists to probe questions about the *runtime and harness* around
coding agents, independent of any single model.

1. **What runtime information is necessary to make coding-agent evals
   reproducible?**
   Hypothesis: a trace capturing task, workspace, tool calls, command I/O,
   diffs, and test results is sufficient to replay a run faithfully.

2. **How often do final pass/fail scores hide useful failure modes visible in
   traces?**
   Hypothesis: trace-level signals (wasted tool calls, denied actions, partial
   diffs) reveal failure structure that a single pass/fail bit discards.

3. **Which sandbox policies preserve agent usefulness while reducing blast
   radius?**
   Hypothesis: path allowlists plus a command denylist block most accidental
   damage while leaving common workflows intact.

4. **Can trace-level regression metrics catch failures before final task
   success changes?**
   Hypothesis: tool-call and command-count deltas regress earlier than
   pass/fail flips.

5. **How much of coding-agent performance is model capability versus
   harness/tool/context design?**
   Hypothesis: deterministic scripted baselines plus controlled tool/context
   variation isolate a measurable harness contribution.

## How questions map to milestones

| Question | Primarily addressed by |
| --- | --- |
| 1 | Tracing (M5), Replay (M6) |
| 2 | Tracing (M5), Reports (M8), Case study (M12) |
| 3 | Sandbox controls (M7) |
| 4 | Regression analysis (M9) |
| 5 | Scoring (M8), Case study (M12), optional adapters (M10–M11) |

## Relevant files

- `docs/METHODOLOGY.md`, `docs/RESULTS.md`, `docs/PLAN.md`
