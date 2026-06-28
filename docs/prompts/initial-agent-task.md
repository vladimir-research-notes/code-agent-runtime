# Initial build prompt for Claude Code

You are working in the `code-agent-runtime` repository.

Read:

- `CLAUDE.md`
- `docs/PLAN.md`

Then execute the plan milestone by milestone.

## Important instructions

- Do not push.
- Commit locally after each coherent milestone.
- Do not wait for human review.
- Create human-review placeholder files, but continue automatically.
- Keep all default tests CPU-only.
- Do not require paid LLM API calls.
- Do not use paid API calls unless explicitly requested later.
- Do not commit secrets, credentials, private Claude logs, `.claude/settings.local.json`, virtualenvs, caches, `node_modules`, model weights, or large generated artifacts.
- Update the multi-page website at every milestone.
- Keep documentation professional and precise.
- Avoid "learning project" tone.
- Be explicit about limitations and non-goals.

Start with Milestone 0 from `docs/PLAN.md`.

After each milestone, print:

- milestone title;
- commit hash;
- tests run;
- website pages updated;
- review placeholder path;
- next milestone.

Continue automatically unless there is a blocker that would risk secrets, paid API spend, data loss, or repository corruption.
