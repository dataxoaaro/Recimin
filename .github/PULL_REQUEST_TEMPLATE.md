## What and why

<!-- One concern per PR. The commit message should already tell the why;
     summarise it here. -->

## Checks

- [ ] `uv run ruff format . && uv run ruff check . && uv run pytest --cov=src`
- [ ] `cd frontend && pnpm exec tsc --noEmit && npx vitest run && pnpm build`
- [ ] Tests accompany the behaviour change
- [ ] Normaliser changes carry a fixture (see CONTRIBUTING)
