# Claude Code instructions for this repository

This repository is a research-grade engineering project: a sandboxed coding-agent runtime and evaluation platform for reproducible software-engineering agents.

## Public framing

Code Agent Runtime is a local-first runtime for running, tracing, sandboxing, replaying, and evaluating coding agents under controlled conditions.

This is not a tutorial repo and not a clone of any commercial tool. It is an independent systems/research platform for understanding the runtime infrastructure around coding agents: task setup, tools, permissions, execution, tracing, replay, scoring, regression comparison, and reports.

## Operating principles

- Build milestone by milestone.
- Commit locally after each coherent milestone.
- Do not push.
- Do not wait for human review.
- Create a human-review placeholder file for each milestone, but continue automatically.
- Keep default tests CPU-only and free.
- Do not require paid LLM API calls for normal tests.
- Keep Claude API integration optional, disabled by default, and protected by explicit cost guards.
- Prefer deterministic mock/scripted agents first.
- Add optional Claude API / Claude Code adapters only after the runtime, tracing, scoring, and sandboxing foundations exist.
- Do not commit secrets, API keys, private transcripts, `.claude/settings.local.json`, virtualenvs, caches, `node_modules`, model weights, or large generated artifacts.
- Be honest about security limitations. Do not claim production-grade sandboxing unless proven.
- Avoid marketing language. Documentation should be precise, technical, and readable.

## Quality bar

Every major claim should be backed by at least one of:

- tests;
- reproducible example task;
- trace artifact;
- result table;
- documented limitation;
- explicit non-goal.

The repo should be understandable to a strong senior engineer after 5 minutes and survive deeper technical questioning after 30 minutes.

## Required behavior after each milestone

After each milestone:

1. Run relevant tests.
2. Update the multi-page website.
3. Update `docs/RESULTS.md` or milestone docs if results changed.
4. Create or update a review placeholder under `docs/review_notes/`.
5. Create or update a milestone note under `docs/milestones/`.
6. Create or update a commit note under `docs/commits/`.
7. Commit locally.
8. Print:
   - commit hash;
   - tests run;
   - website pages updated;
   - next milestone.

Do not stop for review unless continuing would risk secrets, paid API spend, data loss, or repository corruption.

## Human review files

For every milestone, create:

```
docs/review_notes/XX-<milestone-name>-human-review.md
```

Use this structure:

```
Human review: <milestone title>
TL;DR
What changed
What should be checked later
Technical risks
Commands to verify
Human feedback
<!-- Human will fill this later. -->
```

Do not claim human review happened.

## Website requirements

Build a multi-page static website under `site/`.

Required pages:

- `index.html`
- `architecture.html`
- `task-format.html`
- `sandboxing.html`
- `tracing-replay.html`
- `evals.html`
- `results.html`
- `security.html`
- `limitations.html`
- `roadmap.html`

Each page should contain:

- Brief explanation.
- More detailed technical explanation.
- Current implementation status.
- Relevant files.
- Current test/result status.
- Open questions or limitations.

Update the website at every milestone.
