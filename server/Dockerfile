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

RUN pip install uv

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

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
