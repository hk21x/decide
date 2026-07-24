# ---- frontend build ----
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

# ---- backend runtime ----
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist ./static
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV DATA_DIR=/data \
    STATIC_DIR=/app/static \
    PORT=8080 \
    PATH="/app/.venv/bin:$PATH"

VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD \
    python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/api/healthz')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sh", "-c", "uvicorn decide.main:app --host 0.0.0.0 --port ${PORT}"]
