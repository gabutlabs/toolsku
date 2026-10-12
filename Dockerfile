# syntax=docker/dockerfile:1

FROM python:3.14-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ghostscript imagemagick qpdf webp \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

RUN groupadd --system app \
    && useradd --system --no-create-home --gid app --shell /usr/sbin/nologin app \
    && mkdir -p /app/logs \
    && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=4).close()"]

CMD ["/app/.venv/bin/uvicorn", "toolsku.web:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
