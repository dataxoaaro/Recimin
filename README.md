# Recimin

A self-hosted recipe library for one household, optimised for importing
recipes from web pages, Instagram and TikTok on an iPhone. Share a link, and a
minute later the recipe is in the library: ingredients parsed, category
assigned, media archived, and a push notification when it lands.

## Stack

Python 3.12 / FastAPI / SQLite (WAL, no ORM) · React 19 / Vite / Tailwind v4 /
shadcn-ui · Docker Compose, typically behind a Cloudflare Tunnel.

Two services sharing one volume. `api` is slim; `worker` carries yt-dlp,
gallery-dl and ffmpeg. They communicate only through the `jobs` table — no
HTTP between them, no broker.

## How importing works

- **Web pages** are read from their schema.org structured data first (which
  covers nearly every recipe site with zero site-specific code), then
  recipe-scrapers, then — only if both fail — one LLM call over the readable
  text.
- **Instagram and TikTok** posts have their caption checked first: if it
  already contains the recipe, nothing else needs downloading. Otherwise the
  media is fetched and archived (source posts get deleted; the archive is the
  point), frames are sampled from the video, and an LLM turns caption,
  subtitles and frames into a structured recipe.
- Extractions the model is confident in publish directly; uncertain ones are
  flagged for a human look on the recipe page itself.
- The LLM layer is optional. Without an OpenRouter key, web imports still work
  via structured data and social imports save a caption draft plus the media.

## Local development

```bash
uv sync
cp .env.example .env    # then set JWT_SECRET and SITE_PASSWORD
uv run uvicorn recimin.api.main:app --reload
uv run python -m recimin.worker.main
cd frontend && pnpm install && pnpm dev
```

## Configuration

One `.env`, gitignored, holding the secrets — copy `.env.example` and fill it
in; the app refuses to start with a missing or placeholder secret. Values a
server needs to differ on (data directory, public origin, storage cap) live in
`docker-compose.yml` under `environment:`, which overrides `env_file:` — edit
them there for your own instance, committed and reviewable rather than hidden
in a second untracked file.

## Checks

```bash
uv run ruff format . && uv run ruff check . --fix && uv run pytest -q
cd frontend && pnpm exec tsc --noEmit && pnpm build
```

Live tests hit the real network and are excluded from the default run. To
include them:

```bash
uv run pytest -m live
```

## Docker

**On macOS, use the override:**

```bash
docker compose -f docker-compose.yml -f docker-compose.macos.yml up -d --build
```

Docker Desktop's macOS bind mounts do not share SQLite's WAL index between
containers, so the worker never sees jobs the api writes — silently, with no
error. `docker-compose.macos.yml` swaps `./data` for a named volume and
explains the whole thing. On Linux, the plain file is correct:

```bash
docker compose up -d --build
curl localhost:8850/health
```

## Deployment

Any Linux host that runs Docker Compose will do. The api container applies
pending migrations as it starts, so a deploy is: sync the repo and your `.env`
to the host, then `docker compose up -d --build`.

To expose the instance without opening any inbound port, the compose file
ships an optional Cloudflare Tunnel service: create a tunnel in the Cloudflare
Zero Trust dashboard, point its public hostname at `http://api:8000` (the
container, not the host port), set `CLOUDFLARE_TUNNEL_TOKEN` in `.env`, and
start with `docker compose --profile tunnel up -d`.

## Security model

One household, one shared library — deliberately. Registration is gated by a
shared site password; every signed-in user can read, edit and delete every
recipe. That is the product, not an oversight, so there is no per-recipe
ownership. Device tokens (for the iOS Shortcut) are per-phone and individually
revocable; sessions are stateless 30-day JWTs, so logout clears the cookie
rather than revoking it server-side — a household-scale tradeoff, made
knowingly. Imported URLs are refused if they resolve to private or internal
addresses, on every redirect hop, so an import can never probe the network the
worker runs on.

## Importing from an iPhone

[`docs/shortcut-setup.md`](docs/shortcut-setup.md) builds the share-sheet
Shortcut: share a post from Instagram, TikTok or Safari, and it POSTs the URL
to your instance with a device token. The Settings screen mints the tokens.
