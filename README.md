# Recimin

[![CI](https://github.com/dataxoaaro/Recimin/actions/workflows/ci.yml/badge.svg)](https://github.com/dataxoaaro/Recimin/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB.svg)](pyproject.toml)
[![React 19](https://img.shields.io/badge/react-19-61DAFB.svg)](frontend/package.json)

A self-hosted recipe library for one household, optimised for importing
recipes from web pages, Instagram and TikTok on an iPhone. Share a link, and
moments later the recipe is in the library: ingredients parsed, category
assigned, media archived.

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

## The LLM layer

At most **one model call per import**, and only when cheaper signals run out.
What gets sent for a social post: the caption, the subtitle transcript, and up
to 12 frames sampled evenly through the video — never the raw video (providers
sample video at a fixed rate and downscale each frame, which destroys exactly
the burned-in ingredient cards the frames exist to read). Web pages only reach
the model as a last resort, when a page has no structured data at all.

**It is optional.** Leave `OPENROUTER_API_KEY` empty (or set
`LLM_ENABLED=false`) and everything still works: web imports come from
schema.org structured data, social imports save the caption and archive the
media, and you finish the recipe by hand. The model adds parsing, category,
tags and a confidence verdict — not existence.

**Configuration** happens through [OpenRouter](https://openrouter.ai), so any
provider's models are available behind one key:

- `OPENROUTER_MODEL` (default `google/gemini-3.7-flash`) and
  `OPENROUTER_MODEL_FALLBACK` — swap in any model whose endpoint supports
  structured outputs. Requests set `require_parameters: true`, which routes
  away from endpoints that would treat the JSON schema as a suggestion; if a
  model "doesn't work", that guarantee is usually why.
- `OPENROUTER_REASONING_EFFORT` (`low`/`medium`/`high`, default `medium`) —
  extraction is a first-pass accuracy task, not hard reasoning; medium is
  right.

**Privacy and cost stance:** requests are sent with
`data_collection: "deny"`, refusing providers that train on the content. What
leaves your server is the content of a *public* social post or web page —
never your own notes or library. Temperature 0, capped output tokens, one
retry on schema violations. When the model's own confidence is below "high",
the recipe is flagged for a human look instead of being published silently.

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
in; the app refuses to start with a missing secret. Values a server needs to
differ on (data directory, public origin, storage cap) live in
`docker-compose.yml` under `environment:`, which **overrides** `env_file:` —
edit them there for your own instance, committed and reviewable rather than
hidden in a second untracked file. This override is the one mechanism
first-time deployers trip on: if a value from `.env` "doesn't apply" on the
server, the compose file is why.

| Key | Required | Default | What it does |
|---|---|---|---|
| `JWT_SECRET` | yes | — | Signs session cookies. At least 32 chars: `openssl rand -base64 48` |
| `SITE_PASSWORD` | yes | — | Shared registration gate — whoever knows it can create an account |
| `DATA_DIR` | no | `/data` | SQLite database and the media tree. One directory = the whole backup |
| `ALLOWED_ORIGIN` | no | `http://localhost:5173` | Public origin. Drives the CSRF origin check and the `Secure` cookie flag |
| `MAX_MEDIA_BYTES` | no | 80 GB | Total media cap; uploads past it get 507 |
| `SCRAPER_USER_AGENT` | no | a current Chrome | UA for web/social fetches. A stale UA silently breaks TikTok |
| `LLM_ENABLED` | no | `true` | Master switch for the LLM layer |
| `OPENROUTER_API_KEY` | no | empty | Empty keeps the model off; everything else still works |
| `OPENROUTER_MODEL` | no | `google/gemini-3.7-flash` | Primary extraction model |
| `OPENROUTER_MODEL_FALLBACK` | no | `google/gemini-3.5-flash-lite` | Tried when the primary is unavailable |
| `OPENROUTER_REASONING_EFFORT` | no | `medium` | `low` / `medium` / `high` |
| `CLOUDFLARE_TUNNEL_TOKEN` | no | empty | Enables the optional tunnel service (`--profile tunnel`) |

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

## First run

The five minutes after `docker compose up`:

1. Open the site and **register** — the form asks for the site password from
   your `.env` alongside your own email and password.
2. On the iPhone, **install the PWA**: share sheet → *Add to Home Screen* —
   full-screen app instead of a Safari tab.
3. In **Settings → Device tokens**, mint a token for the phone. It is shown
   exactly once — it goes straight into the Shortcut in the next step.
4. Build the share-sheet Shortcut from
   [`docs/shortcut-setup.md`](docs/shortcut-setup.md). From then on,
   importing is: share a post → *Recimin* → done.

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
