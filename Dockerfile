# NexusTrade — Hugging Face Spaces Demo Image
# ----------------------------------------------------------------------------
# Single-container deployment that runs both:
#   • FastAPI backend (uvicorn) on port 8085 (internal)
#   • Streamlit dashboard on port 7860 (HF Spaces default)
#
# The Streamlit dashboard talks to the FastAPI backend over localhost.
# Designed for the free CPU tier (16 GB RAM, 2 vCPU).
# ----------------------------------------------------------------------------

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    NEXUSTRADE_API_URL=http://localhost:8085 \
    NEXUSTRADE_DEMO_MODE=1 \
    HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# ---- System packages ------------------------------------------------------
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

# ---- Non-root user (HF Spaces requirement) -------------------------------
RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app

# ---- Install Python dependencies -----------------------------------------
# README.md and LICENSE are referenced from pyproject.toml metadata; hatchling
# validates them at build time, so they must be present before pip install.
COPY --chown=user:user pyproject.toml README.md LICENSE ./
COPY --chown=user:user src ./src

# Install with the extras needed for the demo:
#   • web      → FastAPI + Streamlit + httpx
#   • agents   → LiteLLM router (cloud LLMs)
#   • execution → prometheus-client for /metrics
RUN pip install --user --upgrade pip \
    && pip install --user ".[web,agents,execution]"

# ---- Copy remaining project files ----------------------------------------
COPY --chown=user:user config ./config
COPY --chown=user:user huggingface ./huggingface

# ---- Expose Streamlit's port (HF Spaces default) -------------------------
EXPOSE 7860

# ---- Launch both processes -----------------------------------------------
CMD ["bash", "huggingface/start.sh"]
