FROM node:23-alpine3.20

WORKDIR /app

# Install daisyui
COPY package.json package.json
COPY package-lock.json package-lock.json
RUN npm install

# Setup python
FROM python:3.12-alpine AS linux-amd64
WORKDIR /app
RUN apk add --no-cache curl gcompat build-base
RUN curl https://github.com/tailwindlabs/tailwindcss/releases/download/v4.0.6/tailwindcss-linux-x64-musl -L -o /bin/tailwindcss

FROM python:3.12-alpine AS linux-arm64
WORKDIR /app
RUN apk add --no-cache curl gcompat build-base
RUN curl https://github.com/tailwindlabs/tailwindcss/releases/download/v4.0.6/tailwindcss-linux-arm64-musl -L -o /bin/tailwindcss

FROM ${TARGETOS}-${TARGETARCH}${TARGETVARIANT}
WORKDIR /app

RUN chmod +x /bin/tailwindcss

COPY --from=0 /app/node_modules/ node_modules/
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY uv.lock pyproject.toml /app/
RUN uv sync --frozen --no-cache

COPY alembic/ alembic/
COPY alembic.ini alembic.ini
COPY static/ static/
COPY templates/ templates/
COPY app/ app/
COPY CHANGELOG.md CHANGELOG.md

RUN /bin/tailwindcss -i static/tw.css -o static/globals.css -m
# Fetch all the required js files
RUN uv run python /app/app/util/fetch_js.py

ENV ABR_APP__PORT=8000
ARG VERSION
ENV ABR_APP__VERSION=$VERSION

#CMD /app/.venv/bin/alembic upgrade heads && /app/.venv/bin/fastapi run --port $ABR_APP__PORT
CMD /app/.venv/bin/alembic upgrade heads && \
    /app/.venv/bin/uvicorn app.main:app \
        --host 0.0.0.0 \
        --port $ABR_APP__PORT \
        --workers 1 \
        --log-level debug

