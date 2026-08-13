# Recimin

A self-hosted recipe library for one household, optimised for importing recipes from web pages, Instagram and TikTok on an iPhone.

## Documentation

| Document | Contents |
|---|---|
| [`claudedocs/recimin-design.md`](claudedocs/recimin-design.md) | Visual system — tokens, typography, components, layout, copy |
| [`claudedocs/recimin-technical.md`](claudedocs/recimin-technical.md) | Architecture, schema, import pipeline, extraction, deployment |
| [`claudedocs/recimin-implementation.md`](claudedocs/recimin-implementation.md) | Eleven phases with test criteria |

**Read [Appendix A of the technical doc](claudedocs/recimin-technical.md#appendix-a--measured-constraints) before touching the fetch layer.** It lists twenty measured constraints. Most of them look like over-engineering and are not.

## Stack

Python 3.12 / FastAPI / SQLite (WAL, no ORM) · React 19 / Vite / Tailwind v4 / shadcn-ui · Docker Compose on a Proxmox LXC behind a Cloudflare Tunnel.

Two services sharing one volume. `api` is slim; `worker` carries yt-dlp, gallery-dl and ffmpeg. They communicate only through the `jobs` table — no HTTP between them, no broker.

## Local development

```bash
uv sync
cp .env.example .env    # then set JWT_SECRET and SITE_PASSWORD
uv run uvicorn recimin.api.main:app --reload
uv run python -m recimin.worker.main
cd frontend && pnpm install && pnpm dev
```

## Configuration

One `.env`, gitignored, living in this directory. `scripts/deploy.sh` uploads
it to the server unchanged. Edit it here, never over ssh — a copy edited on the
server looks applied and silently is not.

The three values the server needs to differ on are in `docker-compose.yml`
under `environment:`, which overrides `env_file:`:

| Key | Local `.env` | Server, via compose |
|---|---|---|
| `DATA_DIR` | `./data` | `/data` |
| `ALLOWED_ORIGIN` | `http://localhost:5173` | `https://recimin.com` |
| `MAX_MEDIA_BYTES` | whatever suits the laptop | bounded by the host's 63 GB disk |

Keeping them there rather than in a second env file means they are committed
and reviewable instead of hidden in an untracked file that can drift.

`deploy.sh` refuses to run — before the slow frontend build — when a key from
`.env.example` is missing, still holds a placeholder, or when dropping
`CLOUDFLARE_TUNNEL_TOKEN` would take the live site offline.

## Checks

```bash
uv run ruff format . && uv run ruff check . --fix && uv run pytest -q
cd frontend && pnpm exec tsc --noEmit && pnpm build
```

Live tests hit the real network and are excluded from the default run. To include them:

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

The optional JS-rendering sidecar is off by default:

```bash
docker compose --profile render up -d
```

## Deployment

Not yet configured — Phase 11. `scripts/deploy.sh` expects `RECIMIN_HOST` and rsyncs to the LXC. **Migrations are not automatic**; apply them before deploying a schema change.
