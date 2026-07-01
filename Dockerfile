# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first (Docker cache), then the code.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=build /app /app
ENV PATH="/app/.venv/bin:$PATH" RSF_HOST=0.0.0.0 RSF_PORT=8000
EXPOSE 8000

# Credentials are injected at run time via --env-file .env (never baked in the image).
CMD ["rsf-stats"]
