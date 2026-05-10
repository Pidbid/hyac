# Base stage for shared dependencies
FROM python:3.12-slim AS base

WORKDIR /app

# Install Node.js for pyright-langserver and uv via the official standalone installer.
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends ca-certificates curl nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/0.8.2/install.sh | sh \
    && cp /root/.local/bin/uv /root/.local/bin/uvx /bin/

COPY requirements.txt ./
RUN uv pip install --system --no-cache -r requirements.txt

# Development stage
FROM base AS development

# The command for development will enable hot-reloading.
# Code will be mounted via docker-compose.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]

# Production stage
FROM base AS production

WORKDIR /app

COPY . .

EXPOSE 8001

CMD ["sh", "/app/start.sh"]
