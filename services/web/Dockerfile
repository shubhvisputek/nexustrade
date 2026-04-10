FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/
COPY config/ config/

RUN pip install --no-cache-dir uv && uv pip install --system ".[web,data,agents,execution,notifications]"

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8085/health')" || exit 1

EXPOSE 8085 8501

# Start both FastAPI and Streamlit via a simple shell wrapper
CMD ["sh", "-c", "python -m uvicorn nexustrade.web.app:app --host 0.0.0.0 --port 8085 & python -m streamlit run src/nexustrade/web/dashboard.py --server.port 8501 --server.address 0.0.0.0 --server.headless true && wait"]
