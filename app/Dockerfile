# Base stage for shared dependencies
FROM python:3.12-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/dependencies/python
ENV UV_CACHE_DIR=/tmp/uv-cache

# Install Node.js for pyright-langserver.
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends ca-certificates nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.8.2

COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/requirements.lock \
    && uv pip install --system --no-cache -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

RUN groupadd --system hyac \
    && useradd --system --gid hyac --home-dir /home/hyac --create-home hyac \
    && install -d -o hyac -g hyac /dependencies/python /tmp/uv-cache

# Development stage
FROM base AS development

# The command for development will enable hot-reloading.
# Code will be mounted via docker-compose.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]

# Production stage
FROM base AS production

WORKDIR /app

COPY --chown=hyac:hyac . .

EXPOSE 8001

USER hyac

CMD ["sh", "/app/start.sh"]
