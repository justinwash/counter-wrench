# CounterWrench: one image serving the API and the built UI. `docker compose up` runs it next to
# Postgres. Every base image is pinned to an exact version.

# --- UI: build the static files -----------------------------------------------------------------
FROM node:24.20.0-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- App -----------------------------------------------------------------------------------------
FROM python:3.12.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    FASTEMBED_CACHE_PATH=/opt/fastembed PATH="/app/.venv/bin:$PATH" \
    CW_STATIC_DIR=/app/static
WORKDIR /app

# Dependencies first (cached until the lock file changes), then the project itself.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md ./
COPY src/ src/
COPY data/ data/
RUN uv sync --frozen --no-dev

# Bake the embedding model into the image, so containers start without downloading it.
RUN python -c "from counterwrench.rag.embed import default_embedder; default_embedder().embed_query('warm up')"

COPY --from=ui /ui/dist /app/static
COPY docker/app/start.sh /app/start.sh
EXPOSE 8000
CMD ["sh", "/app/start.sh"]
