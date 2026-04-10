FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/
COPY config/ config/

RUN pip install --no-cache-dir uv && uv pip install --system ".[execution]"

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8084/health')" || exit 1

EXPOSE 8084 8888
CMD ["python", "-m", "uvicorn", "nexustrade.web.app:app", "--host", "0.0.0.0", "--port", "8084"]
