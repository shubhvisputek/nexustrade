FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/

RUN uv sync --extra execution --no-dev

EXPOSE 8084 8888

CMD ["python", "-m", "nexustrade"]
