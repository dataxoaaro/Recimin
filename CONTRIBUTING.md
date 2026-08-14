# Contributing

Recimin is a household app that happens to be public, not a product chasing
features. Fixes and import-coverage improvements are very welcome; large new
features are worth an issue first, because the answer may be "deliberately
not" (see the non-goals in the README's security model, and the six-category
decision in `src/recimin/db/categories.py`).

## Setup

The README's *Local development* section is the setup guide. In short: `uv
sync`, copy `.env.example` to `.env`, and `pnpm install` in `frontend/`.

## Checks

Everything CI runs, runnable locally:

```bash
uv run ruff format . && uv run ruff check . && uv run pytest --cov=src
cd frontend && pnpm exec tsc --noEmit && npx vitest run && pnpm build
```

All of it must pass. Backend coverage is gated at 80%.

## The rules that are actually about this codebase

- **The normaliser is fixture-driven.** Every branch in
  `src/recimin/importer/normalise.py` exists because a live recipe page
  needed it, and the page is saved under `tests/fixtures/pages/`. Do not add
  a defensive branch without a fixture proving the defect is real, and do not
  remove one without a fixture proving it is dead.
- **The fetch layer is full of measured constraints** — HTTP/1.1 not 2, a
  current Chrome UA, `description` never `title` from yt-dlp. When a comment
  says something was measured, treat it as load-bearing until you have
  re-measured.
- **Tests accompany the change, in the same commit.** Behaviour first, then
  implementation, is the house style.
- **No new dependencies casually.** SQLite with no ORM and a hand-rolled
  ingredient parser are decisions, not accidents.

## Pull requests

Branch from `main`, keep the diff to one concern, and write the commit
message as a short explanation of *why* — the history is written in that
voice and it is the project's real documentation.
