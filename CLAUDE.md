# Doomberg Invest — repo guide for Claude Code
Spec: docs/BRIEF.md (read §1, §2, §4 and your milestone in §8 before any change). Build as written; don't redesign.
Ambiguity → DEFAULT, else the simplest option that passes; log one line in docs/DECISIONS.log.
Spec problems → docs/SPEC_ISSUES.md; keep building as written.

## Commands
make setup | make test | make lint | make type | make guard | make migrate-dev | make verify-mN | make fixtures
make thesis-validate WEEK=YYYY-Www | Web: cd web && pnpm test && pnpm e2e

## Hard rules (guard and CI enforce; never weaken or work around)
- $0 running cost: free tiers only; no paid endpoints (api.anthropic.com, api.openai.com) in runtime code; no credit
  cards anywhere.
- Research tool: no broker SDKs, no order placement, no intraday data, no price alerts.
- Point-in-time: read fundamentals/ownership/events only through as_of(); never use data filed after the as-of date.
- Journal, positions and post-mortems never go to any LLM (llm/privacy.py).
- Every text fact is grounded by exact quote at stored offsets; thesis cards pass thesis/validate.py.
- Evidence score never uses price. Weights change only through a PR with the human-approved label.

## Conventions
Python 3.12 typed, pydantic for every JSON contract, ruff+mypy clean; polars/duckdb for bulk data; SQL only in
db/migrations; UTC; numeric types for money and ratios; tests offline with fixtures and cassettes (never hand-edit
cassettes); every external client has a mock (MOCK_EXTERNALS=true in cloud sessions).

## Workflow
One milestone per thread, branch mN-<slug>, draft PR "[MN] …". Run make verify-mN plus earlier verify targets and
paste the summary in the PR. Fix review findings with a regression test each. Never merge, never force-push.
