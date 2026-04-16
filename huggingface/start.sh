#!/usr/bin/env bash
# Launch FastAPI backend (background) + Streamlit dashboard (foreground)
# for the Hugging Face Spaces single-container demo.
set -euo pipefail

API_PORT="${API_PORT:-8085}"
UI_PORT="${UI_PORT:-7860}"
CONFIG_PATH="${NEXUSTRADE_CONFIG:-config/demo.yaml}"

echo "[nexustrade] Starting FastAPI on :${API_PORT}"
uvicorn nexustrade.web.app:app \
    --host 0.0.0.0 \
    --port "${API_PORT}" \
    --log-level info &
API_PID=$!

# Wait for FastAPI to come up before launching the UI
for _ in {1..30}; do
    if curl --silent --fail "http://localhost:${API_PORT}/health" > /dev/null 2>&1; then
        echo "[nexustrade] FastAPI is healthy"
        break
    fi
    sleep 1
done

echo "[nexustrade] Starting Streamlit on :${UI_PORT}"
exec streamlit run src/nexustrade/web/dashboard.py \
    --server.port "${UI_PORT}" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false \
    --theme.base dark
