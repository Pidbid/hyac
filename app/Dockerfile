# Base stage for shared dependencies
FROM python:3.12-slim AS base

WORKDIR /app

RUN pip install uv

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
