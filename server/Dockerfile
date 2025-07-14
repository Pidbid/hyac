# Base stage for shared dependencies
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /server

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
