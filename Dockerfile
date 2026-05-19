# syntax=docker/dockerfile:1.7

ARG UV_VERSION=0.11.8

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:3.14.3-alpine AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=uv /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY dashbox dashbox

# The admin UI and TVBox spider are architecture-independent release assets.
# Build them before docker build:
#   pnpm run build:spider
#   pnpm run build:admin
RUN test -f dashbox/assets/admin/index.html
RUN test -n "$(find dashbox/assets -maxdepth 1 -name 'dashbox.*.js' -print -quit)"

RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-emit-project --format requirements.txt --output-file requirements.txt \
    && uv pip install --system --requirements requirements.txt \
    && uv pip install --system --no-deps .


FROM python:3.14.3-alpine

ENV DASHBOX_DATA_DIR=/data \
    DASHBOX_HOST=0.0.0.0 \
    DASHBOX_PORT=18990 \
    PYTHONUNBUFFERED=1

RUN mkdir -p /data

WORKDIR /app

COPY --from=builder /usr/local/bin/dashbox /usr/local/bin/dashbox
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY LICENSE THIRD_PARTY_NOTICES.md ./

EXPOSE 18990
VOLUME ["/data"]

CMD ["dashbox"]
