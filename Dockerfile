# syntax=docker/dockerfile:1
# Multi-stage build (REQ-INF-02): dependencies are resolved from uv.lock in a builder stage;
# the runtime image has no build toolchain and runs as a non-root user (REQ-SEC-05).

FROM python:3.12.7-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /usr/local/bin/uv
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Test/lint image: runtime deps + dev group, plus git for repository hygiene checks.
FROM builder AS dev
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system safe.directory '*'
RUN uv sync --frozen --no-install-project
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/repo/src:/repo
WORKDIR /repo

FROM base AS runtime
RUN useradd --create-home --uid 10001 app \
    # Pre-cria .cache com o dono correto: quando o volume nomeado `models-cache` for montado
    # pela primeira vez, Docker copia o conteudo + perms da imagem — sem isso, o volume
    # nasce como root:root e o processo nao-root nao consegue baixar modelos (flashrank, HF).
    && mkdir -p /home/app/.cache/huggingface /home/app/.cache/flashrank \
    && chown -R app:app /home/app/.cache
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY src ./src
COPY prompts ./prompts
COPY scripts ./scripts
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/src:/app \
    HF_HOME=/home/app/.cache/huggingface
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
# Access log off: the app middleware logs each request (path only, no query string).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
