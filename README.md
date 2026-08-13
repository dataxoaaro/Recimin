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

Two gitignored files, both edited here, never over ssh:

| File | Used by |
|---|---|
| `.env` | local development — Vite's origin, `./data`, its own `JWT_SECRET` |
| `.env.production` | the server; `scripts/deploy.sh` uploads it as `/opt/app/.env` |

They cannot be one file: `ALLOWED_ORIGIN`, `DATA_DIR` and `JWT_SECRET` must
differ between them, the last so a session minted locally is not valid in
production.

`deploy.sh` validates `.env.production` before doing anything slow, and refuses
to deploy on a missing key or a leftover placeholder.

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
