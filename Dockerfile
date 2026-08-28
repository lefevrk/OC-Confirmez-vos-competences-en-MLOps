FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=README.md,target=README.md \
    uv sync --locked --extra api --no-install-project

COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY src/api ./src/api
COPY src/ui ./src/ui
COPY migrations ./migrations
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --extra api

FROM python:3.12-slim-trixie

RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system api \
    && useradd --system --gid api --home-dir /app --no-create-home api

COPY --from=builder --chown=api:api /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app
USER api

EXPOSE 8000

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
