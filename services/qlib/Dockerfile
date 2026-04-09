FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir \
    pyqlib \
    grpcio \
    grpcio-tools

EXPOSE 50053

CMD ["python", "-m", "nexustrade"]
