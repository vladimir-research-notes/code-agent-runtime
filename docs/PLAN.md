# Code Agent Runtime: implementation plan

## TL;DR

This repository builds a local-first runtime for coding agents. It provides task definitions, tool execution, permission policies, sandboxing primitives, trace recording, replay, scoring, regression comparison, and reports.

The goal is not to build a toy LLM loop. The goal is to build the infrastructure around coding agents that makes them reproducible, inspectable, and evaluable.

## Core thesis

Modern coding agents need a runtime, not just a prompt.

A serious coding-agent system needs:

- versioned tasks;
- controlled workspaces;
- tool definitions;
- filesystem and shell permissions;
- command execution;
- patch/diff management;
- test execution;
- trace recording;
- replay and debugging;
- scoring;
- regression comparison;
- result reports;
- clear security limitations.

This repo builds that runtime under realistic personal-compute constraints.

## Constraints

- CPU-first by default.
- Suitable for a general CPU instance such as `m5.2xlarge`.
- No GPU required for core functionality.
- No paid LLM API required for tests.
- Mock and scripted agents are first-class.
- Claude API support is optional and cost-guarded.
- Claude Code integration is optional and should use stable surfaces only: imported logs, diffs, before/after directories, or documented CLI/SDK behavior.
- No private Claude Code internals should be required.
- No secrets or large artifacts should be committed.

## Non-goals

This repository is not:

- a production-secure sandbox;
- a replacement for Claude Code;
- a claim that a custom agent beats commercial coding agents;
- a benchmark leaderboard;
- a large-scale paid API evaluation;
- a web product;
- a tutorial.

## Target repository layout

```
src/code_agent_runtime/
  __init__.py
  cli.py

  tasks/
    schema.py
    loader.py
    fixtures.py

  runtime/
    agent_loop.py
    state.py
    context.py
    tool_registry.py
    execution.py

  agents/
    base.py
    mock_agent.py
    scripted_agent.py
    human_agent.py
    claude_api_agent.py
    claude_code_adapter.py

  tools/
    read_file.py
    write_file.py
    apply_patch.py
    run_shell.py
    git_diff.py
    run_tests.py
    search_repo.py

  sandbox/
    policy.py
    permissions.py
    secret_scanner.py
    local_runner.py
    docker_runner.py

  traces/
    schema.py
    recorder.py
    replay.py
    summarize.py

  scoring/
    scorer.py
    test_scorer.py
    diff_scorer.py
    regression.py

  reports/
    markdown.py
    html.py

tasks/
  smoke/
  bugfix/
  refactor/
  security/

examples/
  tiny_python_bug/
  tiny_cli_project/
  unsafe_command_demo/

results/
  raw/
  processed/
  reports/

docs/
  PLAN.md
  ARCHITECTURE.md
  METHODOLOGY.md
  SECURITY_MODEL.md
  LIMITATIONS.md
  RESULTS.md
  REPRODUCIBILITY.md
  RESEARCH_QUESTIONS.md
  prompts/
  milestones/
  commits/
  review_notes/

site/
  index.html
  architecture.html
  task-format.html
  sandboxing.html
  tracing-replay.html
  evals.html
  results.html
  security.html
  limitations.html
  roadmap.html

scripts/
  00_check_environment.py
  01_run_smoke_task.py
  02_generate_report.py
  03_generate_site.py
  04_check_repo_hygiene.py

tests/
```

## Milestones

### Milestone 0 — Scaffold and project foundations

Create package skeleton, documentation skeleton, static website skeleton, `.gitignore`, `pyproject.toml`, initial CLI, and a minimal smoke test.

Validation:

- `python -m pytest -q` passes.
- CLI help works.
- Website files exist.

Commit:

```
Initialize code-agent runtime scaffold
```

### Milestone 1 — Environment and repository hygiene

Add environment check and repository hygiene scanner.

The hygiene scanner should detect:

- secrets patterns;
- virtualenvs;
- caches;
- `node_modules`;
- large files;
- accidental result blobs;
- local Claude settings.

Validation:

- environment check runs;
- hygiene check runs;
- tests pass.

Commit:

```
Add environment and repository hygiene checks
```

### Milestone 2 — Versioned task format

Define YAML or JSON task files.

Task fields should include:

- task id;
- title;
- prompt;
- fixture path;
- allowed tools;
- timeout;
- scoring method;
- test command;
- resource limits;
- metadata;
- version.

Add example tasks for bugfix, CLI change, and unsafe-command demo.

Validation:

- valid tasks load;
- invalid tasks produce readable errors;
- CLI can list and inspect tasks.

Commit:

```
Add versioned coding-agent task format
```

### Milestone 3 — Tool registry and core tools

Implement structured tools:

- read file;
- write file;
- apply patch;
- run shell;
- git diff;
- run tests;
- search repo.

Tools must return structured results and expose metadata for tracing.

Validation:

- unit tests for tools;
- integration test on tiny fixture repo.

Commit:

```
Implement structured tool registry and core tools
```

### Milestone 4 — Local runtime state machine

Implement the coding-agent runtime loop with mock and scripted agents.

Runtime stages:

- load task;
- prepare workspace;
- run agent step;
- execute tool;
- run tests;
- score;
- report.

Validation:

- scripted agent completes smoke task;
- final diff captured;
- tests pass.

Commit:

```
Add local agent runtime state machine
```

### Milestone 5 — Trace recorder

Record every run in a structured trace.

Trace should include:

- task metadata;
- workspace metadata;
- agent actions;
- tool calls;
- command stdout/stderr;
- file diffs;
- test results;
- timestamps;
- exit status.

Validation:

- smoke run produces trace;
- trace schema tests pass.

Commit:

```
Add structured run tracing
```

### Milestone 6 — Replay and debugging tools

Add trace inspection and replay tooling.

Initial replay does not need to re-execute every command. It should reconstruct:

- action timeline;
- tool calls;
- diffs;
- tests;
- failure point.

Validation:

- sample trace can be summarized;
- Markdown report can be generated.

Commit:

```
Add trace inspection and replay tooling
```

### Milestone 7 — Permission policies and sandbox controls

Implement containment primitives:

- allowed read paths;
- allowed write paths;
- denied paths;
- command allowlist;
- command denylist;
- network policy flag;
- max runtime;
- max output size;
- secret scanner.

Add unsafe examples:

- reading `.env`;
- reading `~/.aws/credentials`;
- writing outside workspace;
- dangerous shell command.

Validation:

- blocked actions are blocked;
- allowed actions still work;
- threat model documented.

Commit:

```
Add permission policies and sandbox controls
```

### Milestone 8 — Scoring and evaluation reports

Implement scoring:

- test pass/fail;
- diff constraints;
- expected file checks;
- custom scorer hook.

Add suite runner and result files.

Result summary should include:

- task id;
- agent;
- pass/fail;
- runtime;
- tool-call count;
- command count;
- failure reason.

Validation:

- small suite runs with mock/scripted agents;
- Markdown/HTML report generated.

Commit:

```
Add evaluation scoring and reports
```

### Milestone 9 — Regression comparison and flakiness analysis

Compare two eval result files.

Report:

- improved tasks;
- regressed tasks;
- unchanged tasks;
- flaky tasks.

Add rerun mode for repeated task execution.

Validation:

- fake agent versions produce expected regression report;
- tests pass.

Commit:

```
Add regression comparison and flakiness analysis
```

### Milestone 10 — Optional cost-controlled LLM adapter

Add abstract LLM-agent interface and optional Claude API adapter.

Requirements:

- disabled by default;
- no paid calls in tests;
- fake client for unit tests;
- explicit `--max-cost-usd`;
- dry-run mode;
- caching;
- transcript redaction;
- hard stop on budget risk.

Validation:

- fake client tests pass;
- no API key required;
- docs explain optional real run.

Commit:

```
Add optional cost-controlled LLM adapter
```

### Milestone 11 — Claude Code trace importer

Add a best-effort importer for Claude-Code-like workflows.

Input may be:

- before/after directories;
- git diff plus command log;
- manually exported transcript;
- synthetic Claude-Code-like trace.

Convert imported run into this runtime's trace format and score it with the same scoring system.

Validation:

- synthetic imported run works;
- generated trace can be scored and reported.

Commit:

```
Add Claude Code trace importer
```

### Milestone 12 — Reproducible case study

Create 10–20 meaningful small coding tasks.

Include:

- bugfixes;
- refactors;
- CLI behavior changes;
- tests-must-pass tasks;
- security/sandbox tasks.

Run:

- mock baseline;
- scripted baseline;
- optional imported Claude Code run;
- optional cost-controlled API run.

Validation:

- result CSV exists;
- report exists;
- traces are inspectable;
- website updated.

Commit:

```
Add reproducible coding-agent case study
```

### Milestone 13 — Multi-page website polish

Ensure the website is serious, navigable, and technically useful.

Every page should include:

- brief explanation;
- deeper technical explanation;
- implementation status;
- relevant files;
- test/result status;
- limitations.

Add diagrams where helpful.

Commit:

```
Polish multi-page project website
```

### Milestone 14 — Final hardening

Run final checks:

- tests;
- lint;
- hygiene;
- docs consistency;
- website consistency;
- no secrets;
- no huge artifacts;
- README quality;
- reproducibility instructions.

Commit:

```
Finalize code-agent runtime research platform
```

## Research questions

- What runtime information is necessary to make coding-agent evals reproducible?
- How often do final pass/fail scores hide useful failure modes visible in traces?
- Which sandbox policies preserve agent usefulness while reducing blast radius?
- Can trace-level regression metrics catch failures before final task success changes?
- How much of coding-agent performance is model capability versus harness/tool/context design?

## Expected final artifact

A serious reviewer should be able to:

- install the repo;
- run a smoke coding task;
- inspect the trace;
- see tool calls;
- see what was allowed and blocked;
- run a small eval suite;
- compare two result files;
- read a clear website explaining the system;
- understand exactly what is proven and what is not.
