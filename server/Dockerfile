# Base stage for shared dependencies
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /server

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc \
    && chmod +x /usr/local/bin/mc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.8.2

COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/requirements.lock \
    && uv pip install --system --no-cache -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

# Development stage
FROM base AS development

# The command for development will enable hot-reloading.
# Code will be mounted via docker-compose.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production stage
FROM base AS production

WORKDIR /server

COPY . .

COPY ./healthcheck.py /healthcheck.py
RUN chmod +x /healthcheck.py

EXPOSE 8000

CMD ["sh", "/server/start.sh"]
