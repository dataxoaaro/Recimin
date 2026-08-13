# recimin-worker — carries the media toolchain. Deliberately fat; the api image stays slim.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# ffmpeg for frame and audio extraction. curl for the impersonation self-check.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Media tooling lives outside the locked project deps on purpose.
#
#   - yt-dlp tracks NIGHTLY, not stable: stable went 84 days without a release in
#     2026 and left Instagram broken for 3-4 weeks. Rebuild this image weekly.
#   - The extra is spelled `curl-cffi` WITH A HYPHEN. Installing curl_cffi yourself
#     pulls 0.16.0, which yt-dlp silently rejects (its pin is <0.16), leaving every
#     impersonate target "(unavailable)" with no error. Without impersonation the
#     Instagram GraphQL path is skipped entirely and you fall back to HTML scraping
#     that hits the login redirect.
RUN uv pip install --system --no-cache --pre "yt-dlp[default,curl-cffi]" gallery-dl

# Fail the build rather than ship a worker that cannot reach Instagram.
RUN yt-dlp --list-impersonate-targets | grep -q curl_cffi \
 || (echo "FATAL: no curl_cffi impersonate targets; the curl-cffi extra did not install" && exit 1)

COPY src/ ./src/
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

VOLUME ["/data"]

CMD ["python", "-m", "recimin.worker.main"]
